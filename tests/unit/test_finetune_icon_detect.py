"""Dataset side of the icon-model fine-tune (scripts/training/cv/finetune_icon_detect.py)."""

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

_SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "training" / "cv"
           / "finetune_icon_detect.py")
_spec = importlib.util.spec_from_file_location("finetune_icon_detect", _SCRIPT)
ft = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ft)

W, H = 400, 200


def _layout(root, names):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir()
    for name in names:
        image = np.full((H, W, 3), 20, dtype=np.uint8)
        cv2.rectangle(image, (40, 40), (80, 80), (255, 255, 255), -1)
        cv2.imwrite(str(root / "images" / (name + ".png")), image)
        label = {
            "provenance": {"annotator": "someone@example.com"},
            "elements": [
                {"id": "E1", "bounds": [40, 40, 80, 80], "visual_type": "icon"},
                {"id": "E2", "bounds": [100, 40, 300, 90], "visual_type": "button"},
                {"id": "E3", "bounds": [100, 120, 300, 140], "visual_type": "text"},
                {"id": "E4", "bounds": [0, 0, 400, 200], "visual_type": "block"},
                {"id": "E5", "bounds": [10, 10, 11, 60], "visual_type": "icon"},     # no width
            ]}
        (root / "labels" / (name + ".json")).write_text(json.dumps(label), encoding="utf-8")


def test_variants_of_one_screen_share_a_split_and_the_split_is_stable():
    assert ft.family("apps__1-2") == ft.family("apps__1-13") == "apps__1"
    assert ft.family("climate__main") == "climate__main"
    names = ["apps__%d-%d" % (page, state) for page in range(40) for state in range(3)]
    by_family = {}
    for name in names:
        by_family.setdefault(ft.family(name), set()).add(ft.split_of(name, 0.15, 0.15))
    assert all(len(s) == 1 for s in by_family.values())
    splits = [ft.split_of(n, 0.15, 0.15) for n in names]
    assert splits == [ft.split_of(n, 0.15, 0.15) for n in names]
    assert {"train", "val", "test"} == set(splits) and splits.count("train") > len(names) / 2
    assert ft.split_of("apps__1-2", 0.15, 0.15, seed=0) in ("train", "val", "test")


def test_boxes_round_trip_through_the_yolo_format():
    boxes = [[40, 40, 80, 80], [100, 40, 300, 90]]
    lines = ft.to_yolo_lines(boxes, W, H)
    assert lines[0] == "0 0.150000 0.300000 0.100000 0.200000"
    back = [[round(v) for v in box] for box in _read(lines, W, H)]
    assert back == boxes
    assert ft.to_yolo_lines([[390, 190, 500, 300], [5, 5, 6, 50]], W, H) == \
        ["0 0.987500 0.975000 0.025000 0.050000"], "clamped to the image; slivers dropped"


def _read(lines, width, height):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        return ft.from_yolo_file(path, width, height)


def test_pack_keeps_interactable_boxes_only_and_no_provenance(tmp_path):
    source, out = tmp_path / "set", tmp_path / "pack"
    names = ["app__s%d" % i for i in range(30)]
    _layout(source, names)
    (source / "images" / "orphan.png").write_bytes((source / "images" / "app__s0.png").read_bytes())
    info = ft.pack(source, out, val=0.2, test=0.2)
    assert sum(c["screens"] for c in info["splits"].values()) == 30
    assert info["skipped"] == ["orphan"]
    assert all(c["boxes"] == 2 * c["screens"] for c in info["splits"].values())
    some = next((out / "labels" / "train").glob("*.txt"))
    assert some.read_text(encoding="utf-8").split("\n") == [
        "0 0.150000 0.300000 0.100000 0.200000", "0 0.500000 0.325000 0.500000 0.250000"]
    assert (out / "images" / "train" / (some.stem + ".png")).is_file()
    assert "path: ." in (out / "data.yaml").read_text(encoding="utf-8")
    everything = "".join(p.read_text(encoding="utf-8", errors="ignore")
                         for p in out.rglob("*") if p.suffix in (".txt", ".json", ".yaml"))
    assert "example.com" not in everything and "annotator" not in everything


def test_dimming_pulls_a_box_towards_its_background_and_nothing_else():
    image = np.full((H, W, 3), 20, dtype=np.uint8)
    cv2.rectangle(image, (40, 40), (79, 79), (220, 220, 220), -1)
    cv2.rectangle(image, (200, 40), (239, 79), (220, 220, 220), -1)
    ft.dim_box(image, [40, 40, 80, 80], alpha=0.5)
    assert abs(int(image[60, 60, 0]) - 120) <= 1          # 20 + 0.5 * (220 - 20)
    assert image[60, 220, 0] == 220 and image[10, 10, 0] == 20
    ft.dim_box(image, [390, 190, 391, 250], alpha=0.5)    # a sliver: ignored


def test_dimmed_copies_are_added_once_with_the_labels_of_the_original(tmp_path):
    source, out = tmp_path / "set", tmp_path / "pack"
    _layout(source, ["app__s%d" % i for i in range(12)])
    ft.pack(source, out, val=0.0, test=0.0)
    made = ft.add_dim_copies(out, copies=2, seed=1)
    assert made == 24 and ft.add_dim_copies(out, copies=2, seed=1) == 0
    original = (out / "labels" / "train" / "app__s0.txt").read_text(encoding="utf-8")
    assert (out / "labels" / "train" / "app__s0__dim1.txt").read_text(encoding="utf-8") == original
    stack = [cv2.imread(str(out / "images" / "train" / ("app__s%d__dim%d.png" % (i, n))))[60, 60, 0]
             for i in range(12) for n in (1, 2)]
    assert min(stack) < 255, "some icon was dimmed"
    assert all(cv2.imread(str(out / "images" / "train" / ("app__s%d.png" % i)))[60, 60, 0] == 255
               for i in range(12)), "the originals are untouched"
    # only icon-sized boxes are dimmed: the wide button (200 px of 400) is not
    assert ft.small_boxes([[40, 40, 80, 80], [100, 40, 300, 90]], H) == [[40, 40, 80, 80]]


def test_matching_is_one_to_one():
    truth = [[0, 0, 10, 10], [100, 100, 110, 110]]
    pred = [[0, 0, 10, 10], [1, 0, 11, 10], [300, 300, 310, 310]]
    assert ft.match(pred, truth) == [0, None]
    assert ft.match([], truth) == [None, None]
    assert ft.iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)


def test_report_table_and_named_arguments():
    report = {"operating_point": {"conf": 0.05, "nms_iou": 0.1, "match_iou": 0.5, "dim_alpha": 0.45},
              "models": {
                  "stock": {"test split": {"labelled": 10, "found": 6, "recall": 0.6,
                                           "precision": 0.5, "boxes_per_screen": 12.0}},
                  "tuned": {"test split": {"labelled": 10, "found": 9, "recall": 0.9,
                                           "precision": 0.75, "boxes_per_screen": 12.0}}}}
    lines = ft.report_table(report).split("\n")
    assert lines[2] == "| test split | stock | 10 | 6 | 0.6 | 0.5 | 12.0 |"
    assert lines[3] == "| test split | tuned | 10 | 9 | 0.9 | 0.75 | 12.0 |"
    assert ft._named(["a=x/y.pt", "b=C:/z=1.pt"], "--weights") == {"a": "x/y.pt", "b": "C:/z=1.pt"}
    with pytest.raises(SystemExit):
        ft._named(["nopath"], "--weights")
