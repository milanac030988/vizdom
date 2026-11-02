"""
The real-application harvester (harvest.py) and the same-app negatives
(generate.py): conversion from a UIA dump is pure, so it is pinned here on
hand-written trees; the Windows capture itself is exercised by hand.
"""

import json

import cv2
import numpy as np
import pytest

from visual_dom.evaluation.lifecycle.generate import generate_steps
from visual_dom.evaluation.lifecycle.harvest import (
    confirm_printed,
    looks_icon_only,
    name_is_printed,
    review_sheet,
    uia_to_gt,
)

CLIENT = (100, 200, 400, 300)          # x, y, w, h on the screen


def _n(name, ctype, rect, parent=None, visible=True):
    return {"name": name, "control_type": ctype, "rect": rect,
            "parent": parent, "visible": visible}


def _by_text(gt):
    return {e.get("ocr_text"): e for e in gt["elements"] if e.get("ocr_text")}


def test_rects_become_image_pixels_and_scale_with_dpi():
    nodes = [_n("Win", "Window", (100, 200, 500, 500)),
             _n("Save", "Button", (110, 210, 190, 240), parent=0)]
    gt = uia_to_gt(nodes, CLIENT, (400, 300))
    assert _by_text(gt)["Save"]["bounds"] == [10, 10, 90, 40]
    # a 150 % screenshot of the same client area
    gt = uia_to_gt(nodes, CLIENT, (600, 450))
    assert _by_text(gt)["Save"]["bounds"] == [15, 15, 135, 60]


def test_button_text_child_is_folded_into_the_button():
    nodes = [_n("Win", "Window", (100, 200, 500, 500)),
             _n("Save", "Button", (110, 210, 190, 240), parent=0),
             _n("Save", "Text", (120, 215, 180, 235), parent=1)]
    gt = uia_to_gt(nodes, CLIENT, (400, 300))
    saves = [e for e in gt["elements"] if e.get("ocr_text") == "Save"]
    assert len(saves) == 1 and saves[0]["visual_type"] == "button"
    assert saves[0]["role_word"] == "button"


def test_invisible_outside_and_unnamed_wrappers_are_dropped():
    nodes = [_n("Win", "Window", (100, 200, 500, 500)),
             _n("", "Pane", (100, 200, 500, 500), parent=0),
             _n("Hidden", "Button", (110, 210, 190, 240), parent=1, visible=False),
             _n("Away", "Button", (900, 900, 980, 930), parent=1),
             _n("Open", "Button", (110, 250, 190, 280), parent=1)]
    gt = uia_to_gt(nodes, CLIENT, (400, 300))
    names = set(_by_text(gt))
    assert names == {"Open"}
    # the unnamed pane was skipped: Open hangs off the window directly
    win = gt["elements"][0]
    assert _by_text(gt)["Open"]["parent_id"] == win["id"]
    assert "Hidden" in gt["all_names"] and "Away" in gt["all_names"]


def test_icon_only_buttons_and_fields_are_not_stepped():
    assert looks_icon_only("Bold", [0, 0, 24, 24])
    assert not looks_icon_only("OK", [0, 0, 24, 24])
    assert not looks_icon_only("Save", [0, 0, 75, 23])
    nodes = [_n("Win", "Window", (100, 200, 500, 500)),
             _n("Bold", "Button", (110, 210, 134, 234), parent=0),
             _n("File name", "Edit", (110, 250, 300, 272), parent=0)]
    gt = uia_to_gt(nodes, CLIENT, (400, 300))
    els = {e.get("uia_type"): e for e in gt["elements"]}
    assert els["Button"]["visual_type"] == "icon"
    assert els["Edit"]["visual_type"] == "block" and "ocr_text" not in els["Edit"]


def test_name_is_printed_tolerates_case_punctuation_and_ocr_slips():
    assert name_is_printed("Save", "Save As...")
    assert name_is_printed("Find Next", "find  next")
    assert name_is_printed("Replace All", "Replace Al1")
    assert not name_is_printed("Memory recall", "MR")
    assert not name_is_printed("Seven", "7")
    assert not name_is_printed("Open", "")
    # several readings: each is judged on its own, not their concatenation
    assert name_is_printed("settings", "settinas | settinas | settinas")
    assert not name_is_printed("Memory recall", "MR | M R | MR")


def test_spoken_names_are_demoted_with_the_reading_attached():
    gt = {"elements": [
        {"id": "E1", "bounds": [0, 0, 60, 30], "visual_type": "button", "ocr_text": "Memory recall"},
        {"id": "E2", "bounds": [0, 40, 60, 70], "visual_type": "button", "ocr_text": "Cancel"},
        {"id": "E3", "bounds": [0, 80, 60, 99], "visual_type": "text", "ocr_text": "Ready"}]}
    reads = {0: "MR", 40: "Cancel", 80: "never asked"}
    confirm_printed(gt, None, lambda img, b: reads[b[1]])
    e1, e2, e3 = gt["elements"]
    assert (e1["visual_type"], e1["review"], e1["printed"]) == ("icon", "name not printed", "MR")
    assert e2["visual_type"] == "button" and "review" not in e2
    assert "printed" not in e3


def test_guessed_icon_only_is_restored_when_its_name_is_printed():
    gt = {"elements": [
        {"id": "E1", "bounds": [0, 0, 30, 24], "visual_type": "icon", "ocr_text": "Bell",
         "uia_type": "TreeItem", "review": "icon-only?"},
        {"id": "E2", "bounds": [0, 30, 24, 54], "visual_type": "icon", "ocr_text": "Bold",
         "uia_type": "Button", "review": "icon-only?"}]}
    reads = {0: "Bell", 30: ""}
    confirm_printed(gt, None, lambda img, b: reads[b[1]])
    bell, bold = gt["elements"]
    assert (bell["visual_type"], bell["role_word"]) == ("button", "tree item")
    assert "review" not in bell
    assert bold["visual_type"] == "icon" and bold["review"] == "icon-only?"


def _state(root, sid, captions, extra_names=()):
    (root / "labels").mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(parents=True, exist_ok=True)
    els = [{"id": f"E{i + 1}", "bounds": [10, 10 + 30 * i, 90, 35 + 30 * i],
            "visual_type": "button", "ocr_text": c, "role_word": "button"}
           for i, c in enumerate(captions)]
    (root / "labels" / f"{sid}.json").write_text(json.dumps({
        "image_size": {"width": 200, "height": 400}, "elements": els,
        "all_names": list(captions) + list(extra_names)}), encoding="utf-8")
    cv2.imwrite(str(root / "images" / f"{sid}.png"), np.zeros((400, 200, 3), np.uint8))


def _negatives(manifest, sid):
    return [s for s in manifest["steps"] if s["state"] == sid and s.get("expect") == "FAILED"]


def test_same_app_negatives_come_from_other_screens_of_that_app(tmp_path):
    _state(tmp_path, "editor__main", ["Import", "Save As"])
    _state(tmp_path, "editor__export", ["Export", "Save", "Close"])
    _state(tmp_path, "other__main", ["Launch"])
    m = generate_steps(tmp_path / "labels", tmp_path / "images", negatives="same-app",
                       benchmark="t")
    negs = _negatives(m, "editor__main")
    caps = {s["locator"] for s in negs}
    # "Save" is contained in "Save As" on this screen: never claimed absent;
    # "Launch" belongs to another application
    assert caps == {'text="Export"', 'text="Close"'}
    assert all(s["negative_kind"] == "same-app" for s in negs)
    assert m["benchmark"] == "t"


def test_names_off_the_label_list_are_never_negatives(tmp_path):
    _state(tmp_path, "editor__main", ["Import"], extra_names=["Export"])
    _state(tmp_path, "editor__export", ["Export", "Close"])
    m = generate_steps(tmp_path / "labels", tmp_path / "images", negatives="same-app")
    caps = {s["locator"] for s in _negatives(m, "editor__main")}
    assert 'text="Export"' not in caps
    # one same-app caption left, so one nonsense word tops it up
    kinds = sorted(s["negative_kind"] for s in _negatives(m, "editor__main"))
    assert kinds == ["nonsense", "same-app"]


def test_same_app_negatives_are_deterministic(tmp_path):
    _state(tmp_path, "a__one", ["Alpha", "Beta", "Gamma", "Delta"])
    _state(tmp_path, "a__two", ["Epsilon", "Zeta", "Eta", "Theta"])
    args = (tmp_path / "labels", tmp_path / "images")
    assert generate_steps(*args, seed=3, negatives="same-app") == \
        generate_steps(*args, seed=3, negatives="same-app")


def test_dedupe_keeps_each_caption_once_per_app(tmp_path):
    _state(tmp_path, "dlg__a", ["General", "Editor", "Apply"])
    _state(tmp_path, "dlg__b", ["General", "Editor", "Fonts"])
    _state(tmp_path, "other__a", ["General"])
    args = (tmp_path / "labels", tmp_path / "images")
    m = generate_steps(*args, negatives="same-app", dedupe_app=True)
    acts = sorted((s["state"], s["locator"]) for s in m["steps"] if s["kind"] == "action")
    assert acts == [("dlg__a", 'text="Apply"'), ("dlg__a", 'text="Editor"'),
                    ("dlg__a", 'text="General"'), ("dlg__b", 'text="Fonts"'),
                    ("other__a", 'text="General"')]
    # without the flag every page keeps its own copy
    full = generate_steps(*args, negatives="same-app")
    assert sum(s["kind"] == "action" for s in full["steps"]) == 7


def test_unknown_negative_kind_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        generate_steps(tmp_path, tmp_path, negatives="hard")


def test_review_sheet_lists_boxes_and_negatives(tmp_path):
    _state(tmp_path, "editor__main", ["Import"])
    _state(tmp_path, "editor__export", ["Export"])
    steps = tmp_path / "steps.json"
    steps.write_text(json.dumps(generate_steps(
        tmp_path / "labels", tmp_path / "images", negatives="same-app")), encoding="utf-8")
    page = review_sheet(tmp_path, steps).read_text(encoding="utf-8")
    assert "editor__main" in page and "Export button (same-app)" in page
