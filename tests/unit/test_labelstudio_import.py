"""Label Studio exports into the benchmark's dataset layout (labelstudio.py)."""

import json

import numpy as np
import pytest

from visual_dom.evaluation.lifecycle.generate import generate_steps
from visual_dom.evaluation.lifecycle.labelstudio import (
    add_ocr_captions,
    boxes_of,
    convert,
    read_export,
    state_id_for,
    to_gt,
)

W, H = 400, 200


def _box(label, x, y, w, h, origin="manual"):
    """A rectangle label as Label Studio stores it: percentages of the image."""
    return {"type": "rectanglelabels", "origin": origin, "original_width": W,
            "original_height": H,
            "value": {"x": 100.0 * x / W, "y": 100.0 * y / H, "width": 100.0 * w / W,
                      "height": 100.0 * h / H, "rectanglelabels": [label]}}


def _task_export(image, result, when="2026-01-01T00:00:00Z"):
    return [{"data": {"image": f"s3://bucket/some/path/{image}"},
             "annotations": [{"result": result, "created_at": when}],
             "meta": {"source_annotation_id": 7}}]


def _annotation_export(image, result, when, ann_id=9):
    return {"id": ann_id, "result": result, "updated_at": when, "was_cancelled": False,
            "created_username": "someone@example.com",
            "task": {"data": {"image": f"s3://bucket/other/{image}"}}}


def _write_image(folder, name):
    import cv2
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / name), np.zeros((H, W, 3), dtype=np.uint8))


def test_state_ids_follow_the_app_state_convention():
    assert state_id_for("Climate_10_1.jpg") == "climate__10-1"
    assert state_id_for("image (26).png") == "image__26"
    assert state_id_for("home_screen.png.png") == "home__screen"
    assert state_id_for("1.png") == "screen__1"


def test_both_export_shapes_are_read_and_cancelled_ones_skipped(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps(_task_export("s.png", [_box("text", 0, 0, 10, 10)])), encoding="utf-8")
    b = tmp_path / "1000"                      # the storage sync writes no extension
    b.write_text(json.dumps(_annotation_export("s.png", [], "2026-02-01T00:00:00Z")),
                 encoding="utf-8")
    c = tmp_path / "c.json"
    cancelled = _annotation_export("s.png", [], "2026-03-01T00:00:00Z")
    cancelled["was_cancelled"] = True
    c.write_text(json.dumps(cancelled), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not json", encoding="utf-8")
    got = [x for p in (a, b, c, tmp_path / "notes.txt") for x in read_export(p)]
    assert [(g["image"], g["annotation_id"]) for g in got] == [("s.png", 7), ("s.png", 9)]


def test_boxes_are_pixels_of_the_actual_image_and_filtered_by_origin():
    result = [_box("Button", 40, 20, 100, 40), _box("text", 50, 30, 60, 20, "prediction"),
              _box("icon", 0, 0, 1, 1)]                       # degenerate: dropped
    assert boxes_of(result, (W, H)) == [([40, 20, 140, 60], "button", "manual"),
                                        ([50, 30, 110, 50], "text", "prediction")]
    assert [b[1] for b in boxes_of(result, (W, H), {"manual"})] == ["button"]
    # the picture on disk is twice the size the annotator saw: boxes scale with it
    assert boxes_of(result[:1], (2 * W, 2 * H))[0][0] == [80, 40, 280, 120]


def test_ground_truth_has_types_tree_flags_and_reading_order():
    boxes = [([40, 100, 140, 140], "button", "manual"),
             ([50, 110, 110, 130], "text", "prediction"),
             ([40, 100, 140, 140], "button", "prediction"),      # the same box twice
             ([38, 98, 142, 142], "selected", "manual"),
             ([0, 0, 400, 30], "header", "manual"),
             ([10, 5, 30, 25], "icon", "manual"),
             ([0, 150, 400, 152], "line", "manual"),
             ([300, 100, 320, 120], "gauge", "manual")]
    gt, dropped = to_gt(boxes, (W, H))
    el = {e["id"]: e for e in gt["elements"]}
    assert [(e["id"], e["visual_type"], e["ls_label"]) for e in gt["elements"]] == [
        ("E1", "block", "header"), ("E2", "icon", "icon"),
        ("E3", "button", "button"), ("E4", "text", "text")]
    assert el["E3"]["selected"] is True and el["E3"]["role_word"] == "button"
    assert el["E4"]["parent_id"] == "E3" and el["E3"]["children_ids"] == ["E4"]
    assert el["E2"]["parent_id"] == "E1"
    assert el["E4"]["origin"] == "prediction"
    assert dropped == {"line": 1, "button (duplicate box)": 1, "gauge (no mapping)": 1}
    assert gt["image_size"] == {"width": W, "height": H} and gt["source"] == "label-studio"


def test_ocr_captions_are_proposals_marked_for_review():
    gt, _ = to_gt([([0, 0, 50, 20], "text", "manual"), ([0, 30, 50, 50], "text", "manual"),
                   ([0, 60, 50, 80], "text", "manual"), ([0, 90, 20, 110], "icon", "manual")],
                  (W, H))
    reads = {0: "Climate | Climate | climate", 30: "AUTO | AUT0 | AUTO", 60: ""}
    add_ocr_captions(gt, None, lambda image, b: reads[b[1]])
    a, b, c, icon = gt["elements"]
    assert a["ocr_text"] == "Climate" and "review" not in a and a["caption_source"] == "ocr"
    assert b["ocr_text"] == "AUTO" and b["review"] == "ocr readings differ"
    assert "ocr_text" not in c and c["review"] == "nothing read"
    assert "ocr_text" not in icon and "printed" not in icon
    # every reading, so a negative is never drawn from a caption one mode did read
    assert gt["all_names"] == ["AUT0", "AUTO", "Climate", "climate"]


def test_convert_keeps_the_latest_version_and_feeds_the_step_generator(tmp_path):
    exports, images, out = tmp_path / "exports", tmp_path / "pictures", tmp_path / "set"
    exports.mkdir()
    _write_image(images, "Climate_1.jpg")
    _write_image(images, "Climate_2.png")
    _write_image(images, "Unlabelled_1.png")
    old = [_box("button", 40, 100, 100, 40)]
    new = [_box("button", 40, 100, 100, 40), _box("text", 50, 110, 60, 20, "prediction")]
    (exports / "a.json").write_text(json.dumps(_task_export("Climate_1.jpg", old)), encoding="utf-8")
    (exports / "1000").write_text(json.dumps(
        _annotation_export("Climate_1.jpg", new, "2026-02-01T00:00:00Z")), encoding="utf-8")
    (exports / "1001").write_text(json.dumps(_annotation_export(
        "Climate_2.png", [_box("button", 200, 100, 100, 40), _box("text", 210, 110, 60, 20)],
        "2026-02-01T00:00:00Z")), encoding="utf-8")
    (exports / "1002").write_text(json.dumps(
        _annotation_export("Gone_1.png", new, "2026-02-01T00:00:00Z")), encoding="utf-8")

    captions = {50: "Auto | Auto | Auto", 210: "Sync | Sync | Sync"}
    index = convert([exports], images, out, ocr=True, read=lambda image, b: captions[b[0]])

    assert [s["id"] for s in index["states"]] == ["climate__1", "climate__2"]
    assert index["missing_images"] == ["Gone_1.png"] and index["unlabelled_images"] == 1
    assert index["boxes_by_origin"] == {"manual": 3, "prediction": 1}
    gt = json.loads((out / "labels" / "climate__1.json").read_text(encoding="utf-8"))
    assert len(gt["elements"]) == 2 and gt["provenance"]["versions"] == 2
    assert gt["provenance"]["annotation_id"] == 9
    assert (out / "images" / "climate__1.png").is_file(), "a jpg is re-written as png"
    # nothing that identifies a person or a storage location is copied
    written = (out / "labels" / "climate__1.json").read_text(encoding="utf-8") + \
        (out / "index.json").read_text(encoding="utf-8")
    assert "example.com" not in written and "s3://" not in written

    manifest = generate_steps(out / "labels", out / "images", negatives="same-app",
                              benchmark="lifecycle-imported-v1", dedupe_app=True)
    assert [s["id"] for s in manifest["states"]] == ["climate__1", "climate__2"]
    clicks = [s for s in manifest["steps"] if s["kind"] == "action"]
    assert [(s["locator"], s["target_bounds"]) for s in clicks] == [
        ('text="Auto"', [40, 100, 140, 140]), ('text="Sync"', [200, 100, 300, 140])]
    negatives = [s for s in manifest["steps"] if s.get("negative_kind") == "same-app"]
    assert {(s["state"], s["locator"]) for s in negatives} == {
        ("climate__1", 'text="Sync"'), ("climate__2", 'text="Auto"')}


def test_convert_can_keep_only_what_a_person_drew(tmp_path):
    exports, images, out = tmp_path / "exports", tmp_path / "pictures", tmp_path / "set"
    exports.mkdir()
    _write_image(images, "Home_1.png")
    _write_image(images, "Home_2.png")
    (exports / "1").write_text(json.dumps(_annotation_export("Home_1.png", [
        _box("button", 40, 100, 100, 40), _box("icon", 10, 10, 20, 20, "prediction"),
        _box("text", 200, 10, 60, 20, "prediction-changed")], "2026-02-01T00:00:00Z")),
        encoding="utf-8")
    (exports / "2").write_text(json.dumps(_annotation_export("Home_2.png", [
        _box("icon", 10, 10, 20, 20, "prediction")], "2026-02-01T00:00:00Z")), encoding="utf-8")
    index = convert([exports], images, out, origins={"manual", "prediction-changed"})
    assert [s["id"] for s in index["states"]] == ["home__1"], "a screen left empty is not written"
    assert index["boxes_by_origin"] == {"manual": 1, "prediction-changed": 1}
    assert index["origins_kept"] == ["manual", "prediction-changed"]


def test_ocr_without_tesseract_stops_with_a_reason(tmp_path, monkeypatch):
    import visual_dom.evaluation.lifecycle.harvest as harvest
    monkeypatch.setattr(harvest, "tesseract_reader", lambda: None)
    (tmp_path / "e").mkdir()
    (tmp_path / "i").mkdir()
    with pytest.raises(SystemExit, match="Tesseract"):
        convert([tmp_path / "e"], tmp_path / "i", tmp_path / "o", ocr=True)
