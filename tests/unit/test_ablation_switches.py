"""
The stage switches behind the ablation columns (benchmarks/README.md sec. 7),
the column spec that reaches them, and the compiler bug the ablation found.
"""
import json

import numpy as np
import pytest

from visual_dom.config import VizDomConfig
from visual_dom.core.domain.compiler.dom_compiler import DOMCompiler
from visual_dom.evaluation.evaluator import VisualDOMEvaluator
from visual_dom.evaluation.lifecycle import ablation
from visual_dom.evaluation.lifecycle.runner import (
    ABLATION_SWITCHES, VizDomDescExecutor, VizDomExecutor, parse_vizdom_spec,
)


# -- the compiler kept the previous screen's tree ----------------------------

def _elems(ids):
    return [{"id": i, "bounds": [n * 10, 0, n * 10 + 8, 8], "visual_type": "button", "text": i}
            for n, i in enumerate(ids)]


def _hier(ids):
    return {"id": "ROOT", "bounds": [0, 0, 100, 100], "visual_type": "container",
            "children": [{"id": i, "bounds": [0, 0, 8, 8], "visual_type": "button"} for i in ids]}


def _tree_ids(node):
    out = [] if node["id"].upper() == "ROOT" else [node["id"]]
    for c in node.get("children", []):
        out += _tree_ids(c)
    return out


def test_one_compiler_compiles_many_screens_without_carrying_the_tree_over():
    """Run-6 dumps: screen 2's hierarchy held screen 1's nodes as well (71,
    then 119, then 154 nodes) because nodes_map survived between compile()
    calls and handed the old ROOT to _build_hierarchy_tree."""
    c = DOMCompiler()
    first = c.compile(_elems(["E1", "E2"]), _hier(["E1", "E2"]), (100, 100))
    second = c.compile(_elems(["E1", "E2", "E3"]), _hier(["E1", "E2", "E3"]), (100, 100))
    third = c.compile(_elems(["E1"]), _hier(["E1"]), (100, 100))
    assert _tree_ids(first["hierarchy"]) == ["E1", "E2"]
    assert _tree_ids(second["hierarchy"]) == ["E1", "E2", "E3"]
    assert _tree_ids(third["hierarchy"]) == ["E1"]
    assert [e["id"] for e in third["elements"]] == ["E1"]


def test_evaluator_prefers_the_flat_list_over_the_tree():
    ev = VisualDOMEvaluator()
    dom = {"elements": _elems(["E1"]), "hierarchy": _hier(["E1", "E2", "E3"])}
    assert [e["id"] for e in ev._extract_elements(dom)] == ["E1"]
    assert [e["id"] for e in ev._extract_elements({"dom": dom})] == ["E1"]
    assert [e["id"] for e in ev._extract_elements({"hierarchy": _hier(["E4"])})] == ["E4"]


# -- the column spec ----------------------------------------------------------

def test_spec_without_brackets_is_the_plain_column():
    assert parse_vizdom_spec("modular") == ("modular", {}, "")


def test_every_named_switch_maps_to_a_valid_config_override():
    for (key, value), override in ABLATION_SWITCHES.items():
        detector, overrides, suffix = parse_vizdom_spec(f"modular[{key}={value}]")
        assert detector == "modular" and suffix == f"[{key}={value}]"
        assert overrides == override
        VizDomConfig.load({"detector": {"backend": "modular"}, **overrides})  # must validate


def test_spec_combines_switches_and_accepts_dotted_keys():
    detector, overrides, suffix = parse_vizdom_spec(
        "modular[roles=off, ocr=plain, merge.nms_iou_threshold=0.7, hierarchy.use_llm=true]")
    assert overrides == {"detector": {"infer_roles": False},
                         "ocr": {"upscale": False, "retry_low_confidence": False},
                         "merge": {"nms_iou_threshold": 0.7},
                         "hierarchy": {"use_llm": True}}
    assert suffix.startswith("[roles=off")


def test_unknown_switch_and_bad_syntax_are_errors():
    with pytest.raises(ValueError, match="unknown switch"):
        parse_vizdom_spec("modular[captions=off]")
    with pytest.raises(ValueError, match="expected detector"):
        parse_vizdom_spec("modular[roles=off")


def test_executor_names_carry_the_suffix_and_the_overrides_reach_connect(monkeypatch):
    ex = VizDomExecutor("modular", overrides={"symbols": {"enabled": False}}, suffix="[symbols=off]")
    assert ex.name == "vizdom-modular[symbols=off]"
    seen = {}

    class _Session:
        def analyze(self, img):
            return {"elements": []}

    import visual_dom
    monkeypatch.setattr(visual_dom, "connect", lambda cfg: seen.update(cfg=cfg) or _Session())
    ex._connect()
    assert seen["cfg"] == {"detector": {"backend": "modular"}, "ocr": {"engine": "easyocr"},
                           "symbols": {"enabled": False}}
    # the overrides dict itself is not mutated by the merge
    assert ex.overrides == {"symbols": {"enabled": False}}

    d = VizDomDescExecutor("modular", tiers=["lexical"], overrides={}, suffix="[labels=off]")
    assert d.name == "vizdom-modular[labels=off]+desc[lexical]"


# -- the switches themselves --------------------------------------------------

def test_config_carries_the_new_fields_with_the_production_defaults():
    cfg = VizDomConfig.default()
    assert cfg.detector.infer_roles is True
    assert cfg.ocr.upscale is True and cfg.ocr.retry_low_confidence is True
    assert cfg.hierarchy.label_max_distance == 50


def test_ocr_switches_reach_the_text_detector_through_the_session_config():
    from visual_dom.context import Session
    cfg = VizDomConfig.load({"detector": {"backend": "uied"},
                             "ocr": {"engine": "none", "upscale": False, "retry_low_confidence": False},
                             "hierarchy": {"label_max_distance": 0}})
    pipeline = Session._build_pipeline(cfg)
    assert pipeline.text_detector.upscale is False
    assert pipeline.text_detector.retry_low_confidence is False
    on = Session._build_pipeline(VizDomConfig.load({"ocr": {"engine": "none"}}))
    assert on.text_detector.upscale is True and on.text_detector.retry_low_confidence is True


def test_modular_backend_keeps_raw_kinds_when_roles_are_off():
    from visual_dom.adapters.outbound.detectors.modular_backend import (
        ModularDetectorBackend, NoneCaptioner, RegionProposal, RegionProposer,
    )

    class _Regions(RegionProposer):
        name = "fake"

        def propose(self, image):
            return [RegionProposal(bounds=(0, 0, 100, 40), confidence=0.9)]   # a button's shape

    class _Text:
        ocr_engine = "fake"

        def detect(self, image):
            from visual_dom.adapters.outbound.ocr.text_detector import TextElement
            return [TextElement(id="T1", text="Save", bounds=(10, 5, 60, 25), confidence=0.9)]

    img = np.zeros((100, 200, 3), dtype=np.uint8)
    on = ModularDetectorBackend(region_proposer=_Regions(), captioner=NoneCaptioner(),
                                text_detector=_Text()).detect(img)
    off = ModularDetectorBackend(region_proposer=_Regions(), captioner=NoneCaptioner(),
                                 text_detector=_Text(), infer_roles=False).detect(img)
    assert [d.visual_type for d in on] == ["button"]
    assert [d.visual_type for d in off] == ["icon"]
    assert [d.text for d in off] == ["Save"], "the switch changes the role only"


def test_label_association_is_off_at_distance_zero():
    from visual_dom.core.domain.hierarchy import CoarseHierarchyBuilder
    elements = [{"id": "E1", "bounds": [0, 0, 40, 10], "visual_type": "text", "text": "City"},
                {"id": "E2", "bounds": [0, 14, 100, 34], "visual_type": "input_field", "text": None}]
    on = CoarseHierarchyBuilder().build([dict(e) for e in elements])
    assert on["label_associations"] == {"E2": "E1"}
    off_elems = [dict(e) for e in elements]
    off = CoarseHierarchyBuilder(label_max_distance=0).build(off_elems)
    assert off["label_associations"] == {}
    assert off_elems[1].get("label") is None


# -- the report ---------------------------------------------------------------

def test_report_puts_the_control_first_with_deltas(tmp_path):
    rows = {
        "modular[roles=off]": {"column": "vizdom-modular[roles=off]", "overrides": {},
                               "lifecycle": {"action_hit_rate": 0.5, "verify_accuracy": 0.9,
                                             "false_pass_rate": 0.0, "cost": {"parse_seconds_mean": 1.2}},
                               "stage": {"mean_f1": 0.5, "mean_recall": 0.6, "mean_iou": 0.7,
                                         "mean_char_accuracy": 0.9,
                                         "recall_by_type": {"button": 1.0}, "type_accuracy": {"button": 0.0}}},
        "modular": {"column": "vizdom-modular", "overrides": {},
                    "lifecycle": {"action_hit_rate": 0.883, "verify_accuracy": 0.934,
                                  "false_pass_rate": 0.0, "cost": {"parse_seconds_mean": 1.3}},
                    "stage": {"mean_f1": 0.58, "mean_recall": 0.6, "mean_iou": 0.7,
                              "mean_char_accuracy": 0.95,
                              "recall_by_type": {"button": 1.0}, "type_accuracy": {"button": 0.9}}},
    }
    (tmp_path / "ablation-1.json").write_text(json.dumps({"results": rows}), encoding="utf-8")
    table = ablation.report(tmp_path)
    lines = table.splitlines()
    assert "`vizdom-modular`" in lines[2] and "`vizdom-modular[roles=off]`" in lines[3]
    assert "0.500 (-0.383)" in lines[3] and "0.883" in lines[2]
    assert "| 1.00 / - / - | 0.00 / - / - |" in lines[3]
    assert (tmp_path / "ablation-report.md").exists()


# -- the Tesseract retry that never ran on Linux ------------------------------

def test_tesseract_lookup_tries_path_first_and_warns_once_when_missing(monkeypatch, caplog):
    """Runs 1-6 measured the OCR stage without its second engine: the retry
    looked for a Windows install only, so on every rented Linux host it
    silently returned the easyocr reads. PATH first, and say so when absent."""
    import logging
    import shutil
    from visual_dom.adapters.outbound.ocr import text_detector as td_mod
    from visual_dom.adapters.outbound.ocr.text_detector import TextDetector, TextElement

    td = TextDetector(ocr_engine="easyocr", gpu=False)
    reads = [TextElement(id="T1", text="x", bounds=(0, 0, 5, 5), confidence=0.2)]
    img = np.zeros((20, 20, 3), dtype=np.uint8)

    import os
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(os.path, "exists",
                        lambda p, _e=os.path.exists: False if "Tesseract-OCR" in str(p) else _e(p))
    with caplog.at_level(logging.WARNING):
        out1 = td._retry_low_confidence_with_tesseract(img, reads, 1.0)
        out2 = td._retry_low_confidence_with_tesseract(img, reads, 1.0)
    assert out1 is reads and out2 is reads
    warnings = [r for r in caplog.records if "Tesseract is on but" in r.getMessage()]
    assert len(warnings) == 1, "warned once, not per frame"

    # a binary on PATH is used even when no Windows folder exists
    seen = {}
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/tesseract")

    class _PT:
        class pytesseract:
            tesseract_cmd = None

        @staticmethod
        def image_to_string(region, config=""):
            seen["called"] = True
            return "x"

    monkeypatch.setitem(__import__("sys").modules, "pytesseract", _PT)
    td2 = TextDetector(ocr_engine="easyocr", gpu=False)
    td2._retry_low_confidence_with_tesseract(img, [TextElement(id="T1", text="x", bounds=(0, 0, 5, 5), confidence=0.2)], 1.0)
    assert _PT.pytesseract.tesseract_cmd == "/usr/bin/tesseract"
