"""
Bring a Label Studio box-labelling export into the benchmark's dataset layout.

The lifecycle benchmark reads one layout, whatever the screens are:

    <root>/images/<app>__<state>.png
    <root>/labels/<app>__<state>.json     (the ground-truth schema of data/README.md)

Synthetic screens are written in it, real desktop applications are harvested
into it (harvest.py). This module converts a third source: screenshots someone
labelled by hand in Label Studio with rectangle labels. After conversion the
ordinary tools apply unchanged:

    python -m visual_dom.evaluation.lifecycle.labelstudio convert \
        --exports <dir> [<dir> ...] --images <dir> --out <root> [--ocr]
    python -m visual_dom.evaluation.lifecycle.generate --labels <root>/labels \
        --images <root>/images --negatives same-app --dedupe-app \
        --benchmark <name> --out <root>/steps.json
    python -m visual_dom.evaluation.lifecycle.harvest review --root <root> \
        --steps <root>/steps.json

What a Label Studio export gives, and what it does not:

- **Boxes and a class per box.** Kept as they are, in pixels. The class is
  mapped onto the schema's ``visual_type`` (``CLASS_MAP``); the original class
  stays in ``ls_label`` so a different mapping can be applied later without
  the export.
- **Who drew each box.** Label Studio records ``origin``: ``manual`` (a person
  drew it), ``prediction`` (a model proposed it and the annotator left it) or
  ``prediction-changed`` (a model proposed it and the annotator moved it).
  Kept per element, because a detector must not be scored against boxes a
  related detector proposed. ``--origins manual prediction-changed`` drops the
  untouched proposals.
- **Several versions of one image.** An image annotated more than once keeps
  the most recent annotation; the others are counted in the index.
- **No captions.** A box says "text" or "button", not what the text reads, and
  the step generator needs a caption to build a click or verify step. With
  ``--ocr`` each text box is read by Tesseract and the reading stored as
  ``ocr_text`` with ``caption_source: "ocr"``. That reading is a PROPOSAL: the
  engine is one the pipeline under test can also use, so a lifecycle number
  on OCR captions that nobody reviewed measures agreement with Tesseract, not
  truth. Readings that differ between page modes are marked ``review``.
  Icons get no caption at all; naming them is manual work.

Annotator names, e-mail addresses and storage paths in the export are not
copied to the output.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

# Label Studio class (lower case) -> visual_type of the ground-truth schema.
# None = not an element of the schema (a separator line, a scroll bar); such a
# box is dropped from ``elements`` and counted in the index. ``selected`` is a
# state marker drawn over another element and becomes that element's flag.
CLASS_MAP = {
    "button": "button",
    "text": "text",
    "icon": "icon",
    "input": "input_field",
    "checkbox": "checkbox",
    "card": "container",
    "header": "block",
    "sidebar": "block",
    "keyboard": "block",
    "pagenav": "block",
    "image": "block",
    "line": None,
    "scrolling": None,
    "progressbar": None,
}
STATE_MARKERS = ("selected",)
ROLE_WORDS = {"button": "button", "input_field": "input field", "checkbox": "checkbox"}
# types that can own children in the containment tree
_PARENTS = ("button", "input_field", "checkbox", "container", "block")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def state_id_for(image_name: str) -> str:
    """``Climate_10_1.jpg`` -> ``climate__10-1``: the part before the first
    separator is the application, the rest the state (generate.app_of)."""
    stem = Path(image_name).name
    while Path(stem).suffix.lower() in IMAGE_SUFFIXES:     # "home.png.png"
        stem = Path(stem).stem
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", stem.lower()) if p]
    if not parts:
        return "screen__unnamed"
    if len(parts) == 1:
        return f"screen__{parts[0]}"
    return f"{parts[0]}__{'-'.join(parts[1:])}"


def read_export(path):
    """
    The annotations in one export file, as dicts with ``image`` (base name),
    ``result``, ``when`` and ``annotation_id``.

    Two shapes occur: a task list (``[{"data": {"image": ..}, "annotations":
    [{"result": [..]}]}]``, the JSON export) and a single annotation carrying
    its task (``{"result": [..], "task": {"data": {"image": ..}}}``, the
    per-annotation storage sync). A file that is neither yields nothing.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    out = []
    for item in data if isinstance(data, list) else [data]:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("task"), dict) and "result" in item:
            image = (item["task"].get("data") or {}).get("image")
            anns = [item]
        else:
            image = (item.get("data") or {}).get("image")
            anns = item.get("annotations") or []
        if not image:
            continue
        for a in anns:
            if a.get("was_cancelled") or not isinstance(a.get("result"), list):
                continue
            out.append({
                "image": re.split(r"[\\/]", str(image))[-1],
                "result": a["result"],
                "when": a.get("updated_at") or a.get("created_at") or "",
                "annotation_id": a.get("id") or (item.get("meta") or {}).get("source_annotation_id"),
            })
    return out


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _overlap(a, b):
    return _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def _iou(a, b):
    inter = _overlap(a, b)
    return inter / float(_area(a) + _area(b) - inter) if inter else 0.0


def boxes_of(result, image_size, origins=None):
    """Pixel boxes of one annotation: ``(bounds, class, origin)``; rectangle
    labels only, scaled from the percentages Label Studio stores to the actual
    image, clipped to it, degenerate boxes dropped."""
    w, h = image_size
    out = []
    for r in result:
        v = r.get("value") or {}
        labels = v.get("rectanglelabels") or []
        if r.get("type") != "rectanglelabels" or not labels:
            continue
        origin = r.get("origin") or "manual"
        if origins and origin not in origins:
            continue
        x1, y1 = v.get("x", 0) * w / 100.0, v.get("y", 0) * h / 100.0
        x2, y2 = x1 + v.get("width", 0) * w / 100.0, y1 + v.get("height", 0) * h / 100.0
        b = [max(0, int(round(x1))), max(0, int(round(y1))),
             min(w, int(round(x2))), min(h, int(round(y2)))]
        if b[2] - b[0] < 2 or b[3] - b[1] < 2:
            continue
        out.append((b, str(labels[0]).strip().lower(), origin))
    return out


def to_gt(boxes, image_size, class_map=None):
    """
    The ground-truth dict for one screen from its ``(bounds, class, origin)``
    boxes: mapped types, duplicate boxes folded, ``selected`` markers turned
    into a flag on the element they sit on, reading-order ids and the
    containment tree (``parent_id`` / ``children_ids``).

    Returns ``(gt, dropped)`` where ``dropped`` counts the classes left out.
    """
    class_map = CLASS_MAP if class_map is None else class_map
    dropped = Counter()
    kept, markers = [], []
    for b, cls, origin in boxes:
        if cls in STATE_MARKERS:
            markers.append(b)
            continue
        vt = class_map.get(cls, "unmapped")
        if vt is None or vt == "unmapped":
            dropped[cls if vt is None else f"{cls} (no mapping)"] += 1
            continue
        if any(k["visual_type"] == vt and _iou(k["bounds"], b) > 0.9 for k in kept):
            dropped[f"{cls} (duplicate box)"] += 1
            continue
        kept.append({"bounds": b, "visual_type": vt, "confidence": 1.0,
                     "ls_label": cls, "origin": origin})

    kept.sort(key=lambda e: (e["bounds"][1], e["bounds"][0], -_area(e["bounds"])))
    for i, e in enumerate(kept, 1):
        e["id"] = f"E{i}"
        if e["visual_type"] in ROLE_WORDS:
            e["role_word"] = ROLE_WORDS[e["visual_type"]]

    for m in markers:
        best = max(kept, key=lambda e: _iou(e["bounds"], m), default=None)
        if best is not None and _iou(best["bounds"], m) > 0.3:
            best["selected"] = True
        else:
            dropped["selected (no element under it)"] += 1

    # parent = the smallest container-capable box holding at least 90 % of it
    for e in kept:
        a = _area(e["bounds"])
        holders = [p for p in kept if p is not e and p["visual_type"] in _PARENTS
                   and _area(p["bounds"]) > a and _overlap(e["bounds"], p["bounds"]) >= 0.9 * a]
        if holders:
            parent = min(holders, key=lambda p: _area(p["bounds"]))
            e["parent_id"] = parent["id"]
            parent.setdefault("children_ids", []).append(e["id"])

    w, h = image_size
    return {"image_size": {"width": w, "height": h}, "elements": kept,
            "all_names": [], "source": "label-studio"}, dropped


def _norm(s):
    return " ".join(re.sub(r"[^\w]+", " ", (s or "").casefold()).split())


def add_ocr_captions(gt, image, read, workers=1):
    """
    Propose a caption for every text box from ``read(image, bounds)`` (the
    harvester's Tesseract reader: several page modes joined by " | ").

    The reading most page modes agree on becomes ``ocr_text``; ``printed``
    keeps all of them. Where the modes disagree, or nothing is read, the
    element is marked ``review``. ``all_names`` collects every reading, so the
    step generator never calls a caption absent that some mode did read.
    """
    names = []
    texts = [e for e in gt["elements"] if e["visual_type"] == "text"]
    if workers and workers > 1 and len(texts) > 1:
        # each read is a Tesseract process: threads wait on them in parallel
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            readings = list(pool.map(lambda e: read(image, e["bounds"]), texts))
    else:
        readings = [read(image, e["bounds"]) for e in texts]
    for e, got in zip(texts, readings):
        got = got or ""
        reads = [r.strip() for r in got.split(" | ") if r.strip()]
        e["printed"] = got
        e["caption_source"] = "ocr"
        if not reads:
            e["review"] = "nothing read"
            continue
        votes = Counter(_norm(r) for r in reads)
        top, n = votes.most_common(1)[0]
        e["ocr_text"] = " ".join(next(r for r in reads if _norm(r) == top).split())
        if n < len(reads) or len(reads) < 2:
            e["review"] = "ocr readings differ"
        names += reads
    gt["all_names"] = sorted({" ".join(n.split()) for n in names})
    return gt


def convert(exports, images, out, origins=None, ocr=False, class_map=None, read=None,
            workers=1):
    """
    Convert every annotated image found in ``exports`` (directories or files)
    whose picture exists in ``images``. Writes ``<out>/images``, ``<out>/labels``
    and ``<out>/index.json``; returns the index.
    """
    import cv2

    images, out = Path(images), Path(out)
    files = []
    for e in exports:
        e = Path(e)
        files += sorted(p for p in e.iterdir() if p.is_file()) if e.is_dir() else [e]
    files = [p for p in files if p.suffix.lower() not in IMAGE_SUFFIXES + (".txt",)]

    by_image = {}
    for p in files:
        for ann in read_export(p):
            by_image.setdefault(ann["image"], []).append(ann)

    if ocr and read is None:
        from .harvest import tesseract_reader
        read = tesseract_reader()
        if read is None:
            raise SystemExit("--ocr needs Tesseract, and none was found")

    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    on_disk = {p.name.lower(): p for p in images.iterdir()
               if p.suffix.lower() in IMAGE_SUFFIXES}
    index = {"source": "label-studio", "origins_kept": sorted(origins) if origins else "all",
             "ocr_captions": bool(ocr), "states": [], "missing_images": [],
             "unreadable_images": [], "dropped": {}, "boxes_by_origin": {},
             "unlabelled_images": 0}
    dropped_all, origin_all, used = Counter(), Counter(), {}

    for name in sorted(by_image):
        src = on_disk.get(name.lower())
        if src is None:
            index["missing_images"].append(name)
            continue
        image = cv2.imread(str(src))
        if image is None:
            index["unreadable_images"].append(name)
            continue
        h, w = image.shape[:2]
        versions = sorted(by_image[name], key=lambda a: (a["when"], len(a["result"])))
        latest = versions[-1]
        boxes = boxes_of(latest["result"], (w, h), origins)
        gt, dropped = to_gt(boxes, (w, h), class_map)
        if not gt["elements"]:
            dropped_all["(image left with no element)"] += 1
            continue
        if ocr:
            add_ocr_captions(gt, image, read, workers=workers)

        sid = state_id_for(name)
        if sid in used:                       # two pictures, one name once normalised
            n = 2
            while f"{sid}-{n}" in used:
                n += 1
            sid = f"{sid}-{n}"
        used[sid] = name
        by_origin = Counter(e["origin"] for e in gt["elements"])
        gt["provenance"] = {"original_image": name, "annotation_id": latest["annotation_id"],
                            "annotated_at": latest["when"], "versions": len(versions),
                            "boxes_by_origin": dict(by_origin)}
        cv2.imwrite(str(out / "images" / f"{sid}.png"), image)
        (out / "labels" / f"{sid}.json").write_text(
            json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")
        dropped_all.update(dropped)
        origin_all.update(by_origin)
        index["states"].append({"id": sid, "original_image": name,
                                "elements": len(gt["elements"]),
                                "versions": len(versions)})

    labelled = {n.lower() for n in by_image}
    index["unlabelled_images"] = sum(1 for n in on_disk if n not in labelled)
    index["dropped"] = dict(dropped_all)
    index["boxes_by_origin"] = dict(origin_all)
    index["types"] = dict(Counter(
        e["visual_type"]
        for s in index["states"]
        for e in json.loads((out / "labels" / f"{s['id']}.json").read_text(encoding="utf-8"))["elements"]))
    (out / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="write <out>/images, <out>/labels, <out>/index.json")
    c.add_argument("--exports", nargs="+", required=True,
                   help="export files, or directories of them")
    c.add_argument("--images", required=True, help="directory holding the pictures")
    c.add_argument("--out", required=True, help="dataset root to write")
    c.add_argument("--origins", nargs="+", choices=("manual", "prediction", "prediction-changed"),
                   help="keep only boxes of these origins (default: all)")
    c.add_argument("--ocr", action="store_true",
                   help="propose a caption for every text box with Tesseract (to be reviewed)")
    c.add_argument("--workers", type=int, default=8,
                   help="text boxes read at once with --ocr (default 8)")
    args = parser.parse_args()

    index = convert(args.exports, args.images, args.out,
                    origins=set(args.origins) if args.origins else None, ocr=args.ocr,
                    workers=args.workers)
    print(f"states written     : {len(index['states'])}  -> {args.out}")
    print(f"element types      : {index['types']}")
    print(f"boxes by origin    : {index['boxes_by_origin']}")
    print(f"left out           : {index['dropped']}")
    print(f"labels w/o picture : {len(index['missing_images'])}")
    print(f"pictures w/o label : {index['unlabelled_images']}")


if __name__ == "__main__":
    main()
