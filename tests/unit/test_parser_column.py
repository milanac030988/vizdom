"""A whole-screen parser (ScreenVLM) as a benchmark column (lifecycle/parsers.py)."""

import json

import numpy as np
import pytest

from visual_dom.evaluation.lifecycle.parsers import (
    CLASS_MAP,
    ParserExecutor,
    ScreenVlmParser,
    build_executor,
    detection_scores,
    detection_table,
    class_key,
    parse_parser_spec,
    screentag_to_dom,
)
from visual_dom.evaluation.lifecycle.runner import run_benchmark

W, H = 1000, 500        # one grid unit is 2 px wide and 1 px high


def _tag(label, l, t, r, b, text=""):
    return f"<{label}><loc_{l}><loc_{t}><loc_{r}><loc_{b}>{text}</{label}>"


def test_screentag_becomes_a_dom_in_pixels_with_the_seven_types():
    raw = "<screentag>" + "".join([
        _tag("Button", 10, 20, 60, 40, "Submit"),
        _tag("Navigation Bar", 0, 0, 500, 15),
        _tag("Text Input", 100, 100, 200, 120),
        _tag("Heading", 100, 50, 300, 70, " Sign  in \n"),
        _tag("Radiobox", 10, 200, 20, 210),
        _tag("Logo", 0, 0, 20, 10, "Acme"),
    ]) + "</screentag><|end_of_text|>"
    dom = screentag_to_dom(raw, (W, H))
    got = [(e["id"], e["visual_type"], e["bounds"], e.get("text")) for e in dom["elements"]]
    assert got == [("E1", "button", [20, 20, 120, 40], "Submit"),
                   ("E2", "block", [0, 0, 1000, 15], None),
                   ("E3", "input_field", [200, 100, 400, 120], None),
                   ("E4", "text", [200, 50, 600, 70], "Sign in"),
                   ("E5", "checkbox", [20, 200, 40, 210], None),
                   ("E6", "icon", [0, 0, 40, 10], "Acme")]
    button = dom["elements"][0]
    assert button["center"] == [70, 30] and button["clickable"] and button["role"] == "button"
    assert button["source_label"] == "Button"
    assert dom["image_size"] == [W, H] and dom["element_count"] == 6
    assert dom["parser"]["complete"] is True


def test_repeats_empty_boxes_and_untyped_classes_are_dropped_and_counted():
    raw = "<screentag>" + "".join([
        _tag("Text", 0, 0, 500, 500, "Home About"),
        _tag("Text", 0, 0, 500, 500, "Home About"),          # a looping model
        _tag("Text", 0, 0, 500, 500),                        # same box, no caption: kept
        _tag("Link", 50, 50, 50, 60, "nowhere"),             # no width
        _tag("Scroll", 490, 0, 500, 500),
        _tag("Gauge", 300, 300, 200, 200),                   # corners swapped, class unknown
        _tag("Button", 10, 10, 900, 20, "wide"),             # off the grid: clamped
    ])                                                       # and the output was cut off
    dom = screentag_to_dom(raw, (W, H))
    assert [(e["visual_type"], e["bounds"], e.get("text")) for e in dom["elements"]] == [
        ("text", [0, 0, 1000, 500], "Home About"), ("text", [0, 0, 1000, 500], None),
        ("block", [400, 200, 600, 300], None), ("button", [20, 10, 1000, 20], "wide")]
    assert dom["parser"]["dropped"] == {"repeats": 1, "empty_boxes": 1,
                                        "no_type": {"Scroll": 1}, "unmapped": {"Gauge": 1}}
    assert dom["parser"]["complete"] is False


def test_every_class_of_the_dataset_card_has_a_mapping():
    card = """Button, Link, Checkbox, Radiobox, Switch, Select, Text Input, Search Field,
        Search Bar, Date-Time picker, Slider, Stepper, Toggle, Rating Indicator,
        Navigation Bar, Menu, Tab Bar, Tab, Breadcrumb, Pagination, Bottom navigation, Sidebar,
        Text, Heading, Image, Video, Code snippet, Chart, Table, List, List Item, Carousel,
        Window, Screen, Column/Browser, Toolbar, Card, Modal, Popup Menu, Context Menu,
        Dock Menu, Edit Menu, Logo, Badge, Avatar, Notification, Alert, Progress bar, Tooltip,
        Page control, Status Bar, App Icon, File Icon, Utility Button, Scroll, Picker, Calendar,
        Steppers, Side Bar, PopUp Menu, Toggles, ContextMenu"""
    missing = [c.strip() for c in card.split(",") if class_key(c) not in CLASS_MAP]
    assert missing == []
    assert set(CLASS_MAP.values()) == {"button", "checkbox", "input_field", "text", "icon",
                                       "container", "block", None}


def test_column_names():
    assert parse_parser_spec("screenvlm") == ("screenvlm", {}, "")
    assert parse_parser_spec("screenvlm[pick=first]") == ("screenvlm", {"pick": "first"},
                                                          "[pick=first]")
    for bad in ("screenvlm[pick=any]", "screenvlm[mode=x]", "screenvlm[pick=first", "otherparser"):
        with pytest.raises(ValueError):
            parse_parser_spec(bad)


class _FakeParser:
    name = "fake"
    load_seconds = 0.0

    def __init__(self, raw):
        self.raw, self.calls = raw, 0

    def parse(self, image_bgr):
        self.calls += 1
        h, w = image_bgr.shape[:2]
        return screentag_to_dom(self.raw, (w, h))


RAW = "<screentag>" + "".join([
    _tag("Button", 10, 20, 60, 40, "Save"),
    _tag("Link", 100, 20, 150, 40, "Help"),
    _tag("Text", 100, 100, 150, 120, "Help"),
]) + "</screentag>"


def _manifest(tmp_path):
    import cv2
    image = tmp_path / "s1.png"
    cv2.imwrite(str(image), np.zeros((H, W, 3), dtype=np.uint8))
    steps = [
        {"id": "a1", "state": "s1", "kind": "action", "locator": 'text="Save"',
         "instruction": "click Save", "target_bounds": [20, 20, 120, 40]},
        {"id": "a2", "state": "s1", "kind": "action", "locator": 'text="Help"',
         "instruction": "click Help", "target_bounds": [200, 20, 300, 40]},
        {"id": "v1", "state": "s1", "kind": "verify", "locator": 'text="Help"',
         "instruction": "Help is shown", "expect": "PASSED"},
        {"id": "v2", "state": "s1", "kind": "verify", "locator": 'text="Delete"',
         "instruction": "Delete is shown", "expect": "FAILED"},
    ]
    return {"benchmark": "t", "states": [{"id": "s1", "image": str(image)}], "steps": steps}


def test_steps_resolve_from_the_parsed_dom_under_the_vizdom_contract(tmp_path):
    parser = _FakeParser(RAW)
    out = run_benchmark(_manifest(tmp_path), [ParserExecutor(parser)], out_dir=str(tmp_path / "r"))
    res = out["results"]["fake"]
    by_id = {r["step"]: r for r in res["steps"]}
    assert by_id["a1"]["hit"] is True and by_id["a1"]["outcome"] == [70, 30]
    assert by_id["a2"]["hit"] is False and by_id["a2"]["detail"] == "2 matches"
    assert by_id["v1"]["correct"] and by_id["v2"]["correct"] and not by_id["v2"]["false_pass"]
    assert parser.calls == 1, "one parse per state, whatever the number of steps"
    assert res["summary"]["cost"]["parses"] == 1
    dumped = list((tmp_path / "r").glob("*-doms/fake/s1.json"))
    assert len(dumped) == 1 and json.loads(dumped[0].read_text(encoding="utf-8"))["element_count"] == 3


def test_pick_first_takes_the_first_match_in_reading_order(tmp_path):
    ex = ParserExecutor(_FakeParser(RAW), pick="first", suffix="[pick=first]")
    out = run_benchmark(_manifest(tmp_path), [ex], out_dir=str(tmp_path / "r"))
    by_id = {r["step"]: r for r in out["results"]["fake[pick=first]"]["steps"]}
    assert by_id["a2"]["hit"] is True and by_id["a2"]["detail"] == "first of 2 matches"
    with pytest.raises(ValueError):
        ParserExecutor(_FakeParser(RAW), pick="best")


def test_saved_doms_are_written_once_and_then_replace_the_model(tmp_path):
    manifest, doms = _manifest(tmp_path), tmp_path / "doms"
    first = _FakeParser(RAW)
    run_benchmark(manifest, [ParserExecutor(first, dom_cache_dir=str(doms))],
                  out_dir=str(tmp_path / "r1"))
    assert first.calls == 1 and (doms / "s1.json").is_file()
    second = _FakeParser("<screentag></screentag>")       # would find nothing if it were asked
    out = run_benchmark(manifest, [ParserExecutor(second, dom_cache_dir=str(doms))],
                        out_dir=str(tmp_path / "r2"))
    res = out["results"]["fake"]
    assert second.calls == 0 and res["summary"]["cost"] == {
        "parses": 0, "doms_reused": 1, "model_load_seconds": 0.0,
        "parse_seconds_total": 0, "parse_seconds_mean": None}
    assert res["summary"]["action_hit_rate"] == 0.5


def test_a_column_without_model_or_saved_doms_stops_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(ScreenVlmParser, "available", lambda self: (False, "too old"))
    with pytest.raises(SystemExit, match="too old"):
        build_executor("screenvlm")
    with pytest.raises(SystemExit, match="too old"):
        build_executor("screenvlm", dom_cache_dir=str(tmp_path))      # an empty directory
    (tmp_path / "s1.json").write_text("{}", encoding="utf-8")
    ex = build_executor("screenvlm[pick=first]", dom_cache_dir=str(tmp_path))
    assert ex.name == "screenvlm[pick=first]" and ex.pick == "first"


def test_detection_scores_of_saved_doms_against_the_labels(tmp_path):
    labels, doms = tmp_path / "labels", tmp_path / "doms"
    labels.mkdir()
    doms.mkdir()
    gt = {"elements": [
        {"id": "E1", "bounds": [0, 0, 100, 40], "visual_type": "button"},
        {"id": "E2", "bounds": [0, 100, 100, 140], "visual_type": "button"},
        {"id": "E3", "bounds": [200, 0, 300, 20], "visual_type": "text"}]}
    pred = {"elements": [
        {"id": "E1", "bounds": [0, 0, 100, 40], "visual_type": "button"},       # exact
        {"id": "E2", "bounds": [200, 0, 300, 25], "visual_type": "button"},     # IoU 0.8, wrong type
        {"id": "E3", "bounds": [500, 500, 600, 600], "visual_type": "icon"}]}   # nothing there
    (labels / "s1.json").write_text(json.dumps(gt), encoding="utf-8")
    (doms / "s1.json").write_text(json.dumps(pred), encoding="utf-8")
    (doms / "unlabelled.json").write_text(json.dumps(pred), encoding="utf-8")
    got = detection_scores(labels, doms)
    assert got == {"screens": 1, "predicted": 3, "labelled": 3, "precision": 0.667,
                   "recall": 0.667, "f1": 0.667, "miou_matched": 0.9,
                   "type_accuracy_matched": 0.5,
                   "recall_by_type": {"button": [1, 2], "text": [1, 1]}}
    table = detection_table({"mine": got}).splitlines()
    assert table[0].endswith("| button recall | text recall |")
    assert table[2].endswith("| 0.500 (1/2) | 1.000 (1/1) |")
