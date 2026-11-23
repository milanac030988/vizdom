"""
Fine-tune the icon model (OmniParser icon_detect, YOLO11m, one class) on a
labelled set in the benchmark layout, and measure it before and after.

Why (2026-11-23): on automotive HMI screens the stock model misses dimmed,
inactive icons (a fan icon scored 0.004 against a 0.05 cut-off). The contour
pass (detector.contour_pass) patches that without a model; this script is the
other fix: teach the model those screens.

Four steps, each one sub-command, so the first can run on the machine that
holds the data and the rest on a rented card:

    pack     benchmark layout (images/ + labels/*.json) -> a YOLO dataset with
             a train / val / test split. Boxes and pixels only: no annotator,
             no e-mail, no storage path leaves the source folder.
    prepare  on the training machine: add dimmed copies of the training
             screens (the failure this is about) and "replay" screens labelled
             by the stock model itself, so desktop behaviour is kept.
    train    ultralytics fine-tune from the stock weights.
    eval     stock against fine-tuned at the operating point VizDOM uses
             (confidence 0.05, NMS IoU 0.1): recall, boxes per screen, recall
             on dimmed icons, and the same on guard sets that were not
             trained on.

Needs only ultralytics, opencv and numpy (no visual_dom import), so a small
environment is enough on the rented machine. Rental recipe:
deploy/gpu/train_icon.sh.

The stock weights are AGPL-3.0 and so is anything fine-tuned from them. A
model trained on internal screens stays internal as well: keep the result
out of the public repository.
"""

import argparse
import hashlib
import json
import random
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Box = Tuple[float, float, float, float]

# What the stock model was trained to find: interactable regions.
DEFAULT_TYPES = ("icon", "button", "input_field", "checkbox")
BOX_THRESHOLD = 0.05      # VizDOM's operating point (detector.omniparser_box_threshold)
NMS_IOU = 0.1             # as OmniParser's predict_yolo is called by the backends
DIM_ALPHA_PROBE = 0.45    # the fan icon of 2026-11-23 kept about half of its contrast


# --------------------------------------------------------------------------
# geometry and labels
# --------------------------------------------------------------------------

def iou(a: Sequence[float], b: Sequence[float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / float((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def match(pred: Sequence[Sequence[float]], truth: Sequence[Sequence[float]],
          threshold: float = 0.5) -> List[Optional[int]]:
    """Greedy one-to-one matching; returns, per truth box, the predicted index or None."""
    pairs = sorted(((iou(p, t), pi, ti) for pi, p in enumerate(pred)
                    for ti, t in enumerate(truth)), reverse=True)
    out: List[Optional[int]] = [None] * len(truth)
    used = set()
    for score, pi, ti in pairs:
        if score < threshold:
            break
        if out[ti] is None and pi not in used:
            out[ti] = pi
            used.add(pi)
    return out


def label_boxes(label_file: Path, types: Iterable[str]) -> List[List[int]]:
    """Pixel boxes [x1, y1, x2, y2] of the wanted visual types in a benchmark label."""
    wanted = set(types)
    data = json.loads(Path(label_file).read_text(encoding="utf-8"))
    boxes = []
    for element in data.get("elements", []):
        if element.get("visual_type") not in wanted:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in element["bounds"])
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            boxes.append([x1, y1, x2, y2])
    return boxes


def to_yolo_lines(boxes: Sequence[Sequence[float]], width: int, height: int) -> List[str]:
    lines = []
    for x1, y1, x2, y2 in boxes:
        x1, x2 = max(0, min(width, x1)), max(0, min(width, x2))
        y1, y2 = max(0, min(height, y1)), max(0, min(height, y2))
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        lines.append("0 %.6f %.6f %.6f %.6f" % (
            (x1 + x2) / 2.0 / width, (y1 + y2) / 2.0 / height,
            (x2 - x1) / float(width), (y2 - y1) / float(height)))
    return lines


def from_yolo_file(label_file: Path, width: int, height: int) -> List[List[float]]:
    boxes = []
    if not Path(label_file).is_file():
        return boxes
    for line in Path(label_file).read_text(encoding="utf-8").split("\n"):
        parts = line.split()
        if len(parts) < 5:
            continue
        cx, cy, w, h = (float(v) for v in parts[1:5])
        boxes.append([(cx - w / 2) * width, (cy - h / 2) * height,
                      (cx + w / 2) * width, (cy + h / 2) * height])
    return boxes


# --------------------------------------------------------------------------
# pack: benchmark layout -> YOLO dataset
# --------------------------------------------------------------------------

def family(name: str) -> str:
    """
    Screens that are variants of one another share a family and so a split:
    'apps__1-2' and 'apps__1-3' are the same page in two states. Without this
    the test split would hold near-copies of training screens.
    """
    return re.sub(r"-\d+$", "", name)


def split_of(name: str, val: float, test: float, seed: int = 0) -> str:
    digest = hashlib.sha1(("%d:%s" % (seed, family(name))).encode("utf-8")).hexdigest()
    u = int(digest[:8], 16) / float(0xFFFFFFFF)
    if u < test:
        return "test"
    if u < test + val:
        return "val"
    return "train"


def write_data_yaml(out: Path) -> None:
    # No 'path' key on purpose: ultralytics then takes the yaml's own folder as
    # the root, so the dataset can be moved between machines as it is. A
    # relative 'path: .' is NOT that: it resolves against the ultralytics
    # datasets directory, and training stops with "images not found".
    (out / "data.yaml").write_text(
        "train: images/train\nval: images/val\ntest: images/test\n"
        "nc: 1\nnames:\n  0: icon\n", encoding="utf-8")


def pack(source: Path, out: Path, types: Sequence[str] = DEFAULT_TYPES,
         val: float = 0.15, test: float = 0.15, seed: int = 0) -> Dict:
    import cv2

    source, out = Path(source), Path(out)
    counts = {s: {"screens": 0, "boxes": 0} for s in ("train", "val", "test")}
    skipped = []
    for image_file in sorted((source / "images").glob("*.png")):
        name = image_file.stem
        label_file = source / "labels" / (name + ".json")
        if not label_file.is_file():
            skipped.append(name)
            continue
        image = cv2.imread(str(image_file))
        if image is None:
            skipped.append(name)
            continue
        height, width = image.shape[:2]
        lines = to_yolo_lines(label_boxes(label_file, types), width, height)
        split = split_of(name, val, test, seed)
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(image_file), str(out / "images" / split / image_file.name))
        (out / "labels" / split / (name + ".txt")).write_text("\n".join(lines), encoding="utf-8")
        counts[split]["screens"] += 1
        counts[split]["boxes"] += len(lines)
    write_data_yaml(out)
    info = {"types": list(types), "val": val, "test": test, "seed": seed,
            "splits": counts, "skipped": skipped}
    (out / "pack_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


# --------------------------------------------------------------------------
# prepare: dimmed copies and replay screens
# --------------------------------------------------------------------------

def dim_box(image, box: Sequence[float], alpha: float) -> None:
    """
    Pull a box's pixels towards its own background, in place: what an
    inactive icon looks like. ``alpha`` is the share of contrast that is kept.
    """
    import numpy as np

    height, width = image.shape[:2]
    x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
    x2, y2 = min(width, int(round(box[2]))), min(height, int(round(box[3])))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    pad = 2
    ox1, oy1 = max(0, x1 - pad), max(0, y1 - pad)
    ox2, oy2 = min(width, x2 + pad), min(height, y2 + pad)
    outer = image[oy1:oy2, ox1:ox2].reshape(-1, image.shape[2]).astype(np.float32)
    keep = np.ones((oy2 - oy1, ox2 - ox1), dtype=bool)
    keep[y1 - oy1:y2 - oy1, x1 - ox1:x2 - ox1] = False
    ring = outer[keep.reshape(-1)]
    background = np.median(ring if len(ring) else outer, axis=0)
    region = image[y1:y2, x1:x2].astype(np.float32)
    image[y1:y2, x1:x2] = np.clip(background + alpha * (region - background), 0, 255).astype(np.uint8)


def small_boxes(boxes: Sequence[Sequence[float]], height: int, max_side: float = 0.2):
    """Icon-sized boxes: the ones a screen can show dimmed."""
    limit = height * max_side
    return [b for b in boxes if (b[2] - b[0]) <= limit and (b[3] - b[1]) <= limit]


def add_dim_copies(dataset: Path, copies: int = 2, seed: int = 0) -> int:
    """Per training screen, ``copies`` versions with a random part of its icons dimmed."""
    import cv2

    dataset = Path(dataset)
    rng = random.Random(seed)
    made = 0
    for image_file in sorted((dataset / "images" / "train").glob("*.png")):
        if "__dim" in image_file.stem or image_file.stem.startswith("replay__"):
            continue
        label_file = dataset / "labels" / "train" / (image_file.stem + ".txt")
        image = cv2.imread(str(image_file))
        if image is None or not label_file.is_file():
            continue
        height, width = image.shape[:2]
        candidates = small_boxes(from_yolo_file(label_file, width, height), height)
        if not candidates:
            continue
        for n in range(1, copies + 1):
            target = dataset / "images" / "train" / ("%s__dim%d.png" % (image_file.stem, n))
            if target.is_file():
                continue
            copy = image.copy()
            for box in candidates:
                if rng.random() < rng.uniform(0.3, 0.6):
                    dim_box(copy, box, rng.uniform(0.3, 0.6))
            cv2.imwrite(str(target), copy)
            shutil.copyfile(str(label_file),
                            str(dataset / "labels" / "train" / (target.stem + ".txt")))
            made += 1
    return made


def predict_boxes(model, image, conf: float = BOX_THRESHOLD) -> Tuple[List[List[float]], List[float]]:
    result = model.predict(image, conf=conf, iou=NMS_IOU, verbose=False)[0]
    return result.boxes.xyxy.cpu().numpy().tolist(), result.boxes.conf.cpu().numpy().tolist()


def add_replay(dataset: Path, images: Path, weights: str, conf: float = 0.3,
               limit: int = 0) -> int:
    """
    Add screens of another kind, labelled by the stock model itself (its
    confident boxes). They teach nothing new; they keep the fine-tuned model
    from drifting on the screens the stock model already handles.
    """
    import cv2
    from ultralytics import YOLO

    dataset = Path(dataset)
    model = YOLO(weights)
    files = sorted(Path(images).glob("*.png"))
    if limit:
        files = files[:limit]
    made = 0
    for image_file in files:
        target = dataset / "images" / "train" / ("replay__%s.png" % image_file.stem)
        if target.is_file():
            continue
        image = cv2.imread(str(image_file))
        if image is None:
            continue
        height, width = image.shape[:2]
        boxes, _scores = predict_boxes(model, image, conf=conf)
        shutil.copyfile(str(image_file), str(target))
        (dataset / "labels" / "train" / (target.stem + ".txt")).write_text(
            "\n".join(to_yolo_lines(boxes, width, height)), encoding="utf-8")
        made += 1
    return made


# --------------------------------------------------------------------------
# train
# --------------------------------------------------------------------------

def train(data: Path, weights: str, out: Path, epochs: int, imgsz: int, batch: int,
          lr0: float, freeze: int, device: str, fraction: float, workers: int) -> Path:
    from ultralytics import YOLO

    out = Path(out).resolve()
    model = YOLO(weights)
    model.train(
        data=str(Path(data).resolve()), epochs=epochs, imgsz=imgsz, batch=batch,
        device=device, project=str(out.parent), name=out.name, exist_ok=True,
        optimizer="AdamW", lr0=lr0, lrf=0.1, warmup_epochs=2, cos_lr=True,
        patience=max(10, epochs // 3), freeze=freeze or None, fraction=fraction,
        workers=workers, seed=0, deterministic=True, plots=False,
        # Screens are not natural images: no rotation, no mirror, little
        # geometry. Brightness is the one axis this fine-tune is about.
        degrees=0.0, shear=0.0, perspective=0.0, fliplr=0.0, flipud=0.0,
        translate=0.05, scale=0.25, mosaic=0.3, close_mosaic=max(5, epochs // 5),
        mixup=0.0, hsv_h=0.01, hsv_s=0.3, hsv_v=0.5)
    return out / "weights" / "best.pt"


# --------------------------------------------------------------------------
# eval
# --------------------------------------------------------------------------

def _score(model, samples, dim_alpha: Optional[float] = None) -> Dict:
    """
    samples: [(image path, [truth boxes in pixels])]. With ``dim_alpha`` every
    icon-sized truth box is dimmed first and only those boxes are scored.
    """
    import cv2

    truth_total = found = predicted = matched_pred = screens = 0
    for image_file, truth in samples:
        image = cv2.imread(str(image_file))
        if image is None:
            continue
        if dim_alpha is not None:
            truth = small_boxes(truth, image.shape[0])
            for box in truth:
                dim_box(image, box, dim_alpha)
        boxes, _scores = predict_boxes(model, image)
        hits = match(boxes, truth)
        screens += 1
        truth_total += len(truth)
        found += sum(h is not None for h in hits)
        predicted += len(boxes)
        matched_pred += len({h for h in hits if h is not None})
    return {
        "screens": screens, "labelled": truth_total, "found": found,
        "recall": round(found / truth_total, 4) if truth_total else None,
        "boxes_per_screen": round(predicted / screens, 1) if screens else None,
        "precision": round(matched_pred / predicted, 4) if predicted else None,
    }


def yolo_samples(dataset: Path, split: str):
    import cv2

    out = []
    for image_file in sorted((Path(dataset) / "images" / split).glob("*.png")):
        image = cv2.imread(str(image_file))
        if image is None:
            continue
        height, width = image.shape[:2]
        out.append((image_file, from_yolo_file(
            Path(dataset) / "labels" / split / (image_file.stem + ".txt"), width, height)))
    return out


def layout_samples(root: Path, types: Sequence[str]):
    root = Path(root)
    return [(f, label_boxes(root / "labels" / (f.stem + ".json"), types))
            for f in sorted((root / "images").glob("*.png"))
            if (root / "labels" / (f.stem + ".json")).is_file()]


def evaluate(dataset: Path, weights: Dict[str, str], guards: Dict[str, Path],
             types: Sequence[str] = DEFAULT_TYPES, split: str = "test") -> Dict:
    from ultralytics import YOLO

    sets = {"%s split" % split: yolo_samples(dataset, split)}
    for name, root in guards.items():
        sets["guard: " + name] = layout_samples(root, types)
    report: Dict = {"operating_point": {"conf": BOX_THRESHOLD, "nms_iou": NMS_IOU,
                                        "match_iou": 0.5, "dim_alpha": DIM_ALPHA_PROBE},
                    "models": {}}
    for label, path in weights.items():
        model = YOLO(path)
        rows = {}
        for set_name, samples in sets.items():
            rows[set_name] = _score(model, samples)
        rows["%s split, icons dimmed" % split] = _score(
            model, sets["%s split" % split], dim_alpha=DIM_ALPHA_PROBE)
        report["models"][label] = rows
    return report


def report_table(report: Dict) -> str:
    lines = ["| Set | Model | Labelled | Found | Recall | Precision | Boxes per screen |",
             "|---|---|---|---|---|---|---|"]
    models = report["models"]
    for set_name in next(iter(models.values())):
        for label, rows in models.items():
            r = rows[set_name]
            lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                set_name, label, r["labelled"], r["found"], r["recall"],
                r["precision"], r["boxes_per_screen"]))
    lines.append("")
    lines.append("Confidence %(conf)s, NMS IoU %(nms_iou)s, a box counts as found at IoU >= "
                 "%(match_iou)s. Dimmed: every icon-sized labelled box keeps %(dim_alpha)s of "
                 "its contrast." % report["operating_point"])
    lines.append("Precision on a guard set is against that set's own labels, which do not "
                 "mark every interactable region: read its recall and box count instead.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def _named(pairs: Sequence[str], what: str) -> Dict[str, str]:
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit("%s must be name=path, got %r" % (what, pair))
        name, path = pair.split("=", 1)
        out[name] = path
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pack", help="benchmark layout -> YOLO dataset with a split")
    p.add_argument("--source", required=True, help="folder with images/ and labels/*.json")
    p.add_argument("--out", required=True)
    p.add_argument("--types", default=",".join(DEFAULT_TYPES))
    p.add_argument("--val", type=float, default=0.15)
    p.add_argument("--test", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("prepare", help="add dimmed copies and replay screens to train")
    p.add_argument("--data", required=True, help="the packed dataset folder")
    p.add_argument("--dim-copies", type=int, default=2)
    p.add_argument("--replay-images", default=None,
                   help="screens of another kind, labelled by the stock model")
    p.add_argument("--replay-limit", type=int, default=0)
    p.add_argument("--replay-conf", type=float, default=0.3)
    p.add_argument("--weights", default="models/omniparser/icon_detect/model.pt")
    p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("train", help="fine-tune from the stock weights")
    p.add_argument("--data", required=True, help="the packed dataset folder")
    p.add_argument("--weights", default="models/omniparser/icon_detect/model.pt")
    p.add_argument("--out", required=True, help="run folder; weights/best.pt appears in it")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--imgsz", type=int, default=1280, help="keep the stock model's 1280")
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--lr0", type=float, default=3e-4)
    p.add_argument("--freeze", type=int, default=0, help="first N layers kept fixed (10 = backbone)")
    p.add_argument("--device", default="0")
    p.add_argument("--fraction", type=float, default=1.0, help="share of train used (smoke: 0.1)")
    p.add_argument("--workers", type=int, default=4)

    p = sub.add_parser("eval", help="stock against fine-tuned at VizDOM's operating point")
    p.add_argument("--data", required=True, help="the packed dataset folder")
    p.add_argument("--weights", nargs="+", required=True, metavar="NAME=PATH")
    p.add_argument("--guard", nargs="*", default=[], metavar="NAME=DIR",
                   help="benchmark-layout sets that were not trained on")
    p.add_argument("--types", default=",".join(DEFAULT_TYPES))
    p.add_argument("--split", default="test")
    p.add_argument("--out", default=None, help="writes <out>.json and <out>.md")

    args = ap.parse_args(argv)
    if args.command == "pack":
        info = pack(Path(args.source), Path(args.out), args.types.split(","),
                    args.val, args.test, args.seed)
        for split, c in info["splits"].items():
            print("%-5s %4d screens %6d boxes" % (split, c["screens"], c["boxes"]))
        if info["skipped"]:
            print("skipped (no label or unreadable): %d" % len(info["skipped"]))
        if not info["splits"]["train"]["screens"]:
            raise SystemExit("no training screens found under %s" % args.source)
    elif args.command == "prepare":
        made = add_dim_copies(Path(args.data), args.dim_copies, args.seed) if args.dim_copies else 0
        print("dimmed copies added: %d" % made)
        if args.replay_images:
            made = add_replay(Path(args.data), Path(args.replay_images), args.weights,
                              args.replay_conf, args.replay_limit)
            print("replay screens added: %d" % made)
        write_data_yaml(Path(args.data))
    elif args.command == "train":
        write_data_yaml(Path(args.data))      # a pack made by an older version
        best = train(Path(args.data) / "data.yaml", args.weights, Path(args.out), args.epochs,
                     args.imgsz, args.batch, args.lr0, args.freeze, args.device,
                     args.fraction, args.workers)
        print("best weights: %s" % best)
        if not best.is_file():
            raise SystemExit("training ended without %s" % best)
    elif args.command == "eval":
        report = evaluate(Path(args.data), _named(args.weights, "--weights"),
                          {k: Path(v) for k, v in _named(args.guard, "--guard").items()},
                          args.types.split(","), args.split)
        table = report_table(report)
        print(table)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out + ".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            Path(args.out + ".md").write_text(table + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
