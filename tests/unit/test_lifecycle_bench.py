"""
Unit tests for the full-lifecycle benchmark harness.

The harness itself must be trustworthy before its numbers are: these tests pin
the step generator's contract (uniqueness rule, dual representation, negative
oracle steps) and the scoring semantics (action-hit, verdicts, false-pass)
using a synthetic manifest and a scripted executor — no models, no images.
"""

import json

import pytest

from visual_dom.evaluation.lifecycle.generate import generate_steps
from visual_dom.evaluation.lifecycle.runner import (
    VizDomDescExecutor, _inside, _require_descriptions, _score, run_benchmark)


# --------------------------------------------------------------------------- #
# generator
# --------------------------------------------------------------------------- #

def _write_state(tmp_path, name, elements, size=(200, 100)):
    labels = tmp_path / "labels"
    images = tmp_path / "images"
    labels.mkdir(exist_ok=True)
    images.mkdir(exist_ok=True)
    (labels / f"{name}.json").write_text(json.dumps({
        "image_size": {"width": size[0], "height": size[1]},
        "elements": elements,
    }), encoding="utf-8")
    import numpy as np
    import cv2
    cv2.imwrite(str(images / f"{name}.png"),
                np.zeros((size[1], size[0], 3), dtype=np.uint8))
    return labels, images


def test_generator_uses_only_unique_captions(tmp_path):
    labels, images = _write_state(tmp_path, "s1", [
        {"id": "E1", "visual_type": "button", "bounds": [0, 0, 50, 20],
         "ocr_text": "Save"},
        {"id": "E2", "visual_type": "button", "bounds": [60, 0, 110, 20],
         "ocr_text": "Delete"},
        # duplicated caption: a text elsewhere also says "Delete"
        {"id": "E3", "visual_type": "text", "bounds": [0, 50, 40, 60],
         "ocr_text": "Delete"},
    ])
    manifest = generate_steps(labels, images)
    actions = [s for s in manifest["steps"] if s["kind"] == "action"]
    assert [a["target_id"] for a in actions] == ["E1"], (
        "'Delete' appears twice in the state, so it must not become a step")
    assert actions[0]["locator"] == 'text="Save"'
    assert "Save" in actions[0]["instruction"]


def test_generator_takes_caption_from_child_text(tmp_path):
    labels, images = _write_state(tmp_path, "s1", [
        {"id": "E1", "visual_type": "button", "bounds": [0, 0, 50, 20],
         "children_ids": ["E2"]},
        {"id": "E2", "visual_type": "text", "bounds": [5, 5, 45, 15],
         "ocr_text": "Login", "parent_id": "E1"},
    ])
    manifest = generate_steps(labels, images)
    actions = [s for s in manifest["steps"] if s["kind"] == "action"]
    assert actions and actions[0]["target_id"] == "E1"
    assert actions[0]["locator"] == 'text="Login"'


def test_generator_emits_negative_oracle_steps(tmp_path):
    labels, images = _write_state(tmp_path, "s1", [])
    manifest = generate_steps(labels, images)
    negatives = [s for s in manifest["steps"] if s.get("expect") == "FAILED"]
    assert len(negatives) == 2
    assert all(s["target_bounds"] is None for s in negatives)


def test_generator_is_deterministic(tmp_path):
    labels, images = _write_state(tmp_path, "s1", [])
    assert generate_steps(labels, images, seed=7) == generate_steps(
        labels, images, seed=7)


def test_generator_emits_desc_form_of_every_step(tmp_path):
    """The desc= column (ADR-022) resolves a description derived from the same
    caption as the locator and the instruction - no executor gets more."""
    labels, images = _write_state(tmp_path, "s1", [
        {"id": "E1", "visual_type": "input_field", "bounds": [0, 0, 50, 20],
         "ocr_text": "Username"},
    ])
    steps = generate_steps(labels, images)["steps"]
    by_kind = {}
    for s in steps:
        by_kind.setdefault((s["kind"], s.get("expect")), s)
    assert by_kind[("action", None)]["description"] == "Username input field"
    assert by_kind[("verify", "PASSED")]["description"] == "Username input field"
    negative = by_kind[("verify", "FAILED")]
    assert negative["description"].endswith(" button")
    assert negative["description"].split(" button")[0] in negative["locator"]
    assert all(s["description"] for s in steps)


def test_require_descriptions_rejects_old_manifest():
    old = {"steps": [{"id": "s/act/E1", "locator": "text=x", "instruction": "click x"}]}
    with pytest.raises(SystemExit, match="regenerate"):
        _require_descriptions(old)
    _require_descriptions({"steps": [{"id": "a", "description": "x button"}]})


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #

def test_action_hit_requires_point_inside_bounds():
    step = {"kind": "action", "target_bounds": [10, 10, 30, 30]}
    assert _score(step, (20, 20)) == {"hit": True}
    assert _score(step, (31, 20)) == {"hit": False}
    assert _score(step, None) == {"hit": False}
    assert _inside((10, 10), [10, 10, 30, 30])          # boundary counts


def test_false_pass_is_only_passed_on_absent_target():
    negative = {"kind": "verify", "expect": "FAILED"}
    positive = {"kind": "verify", "expect": "PASSED"}
    assert _score(negative, "PASSED") == {"correct": False, "false_pass": True}
    assert _score(negative, "FAILED") == {"correct": True, "false_pass": False}
    assert _score(positive, "FAILED") == {"correct": False, "false_pass": False}
    assert _score(positive, None) == {"correct": False, "false_pass": False}


# --------------------------------------------------------------------------- #
# runner end to end with a scripted executor
# --------------------------------------------------------------------------- #

class _ScriptedExecutor:
    """Answers from a lookup table; failures on unknown steps."""

    name = "scripted"

    def __init__(self, answers):
        self.answers = answers

    def run_step(self, state, step):
        return {"outcome": self.answers[step["id"]], "latency": 0.01,
                "detail": "scripted"}

    def cost_summary(self):
        return {"inferences": len(self.answers)}


def test_runner_aggregates_and_writes_results(tmp_path):
    manifest = {
        "benchmark": "unit",
        "states": [{"id": "s", "image": "none.png", "gt": "none.json"}],
        "steps": [
            {"id": "a1", "state": "s", "kind": "action", "locator": "text=x",
             "instruction": "click x", "target_id": "E1",
             "target_bounds": [0, 0, 10, 10]},
            {"id": "v1", "state": "s", "kind": "verify", "locator": "text=x",
             "instruction": "x visible", "expect": "PASSED",
             "target_id": "E1", "target_bounds": [0, 0, 10, 10]},
            {"id": "v2", "state": "s", "kind": "verify", "locator": "text=y",
             "instruction": "y visible", "expect": "FAILED",
             "target_id": None, "target_bounds": None},
        ],
    }
    ex = _ScriptedExecutor({"a1": (5, 5), "v1": "PASSED", "v2": "PASSED"})
    payload = run_benchmark(manifest, [ex], out_dir=str(tmp_path))

    s = payload["results"]["scripted"]["summary"]
    assert s["action_hit_rate"] == 1.0
    assert s["verify_accuracy"] == 0.5          # v2 judged PASSED, expected FAILED
    assert s["false_pass_rate"] == 0.5
    assert list(tmp_path.glob("*.json")) and list(tmp_path.glob("*.md"))


# --------------------------------------------------------------------------- #
# the desc= column (ADR-022 resolver behind the same DOM)
# --------------------------------------------------------------------------- #

_DESC_MANIFEST = {
    "benchmark": "unit",
    "states": [{"id": "s", "image": "none.png", "gt": "none.json"}],
    "steps": [
        {"id": "a1", "state": "s", "kind": "action", "locator": 'text="x"',
         "instruction": "click the 'x' button", "description": "x button",
         "target_id": "E1", "target_bounds": [0, 0, 10, 10]},
        {"id": "v1", "state": "s", "kind": "verify", "locator": 'text="x"',
         "instruction": "the 'x' button is visible", "description": "x button",
         "expect": "PASSED", "target_id": "E1", "target_bounds": [0, 0, 10, 10]},
        {"id": "v2", "state": "s", "kind": "verify", "locator": 'text="Warp Cores"',
         "instruction": "the 'Warp Cores' button is visible",
         "description": "Warp Cores button", "expect": "FAILED",
         "target_id": None, "target_bounds": None},
    ],
}


class _FakeResolver:
    """Stands in for DescriptionResolver: knows one element, by its description."""

    made = 0

    def __init__(self, dom, screenshot):
        _FakeResolver.made += 1
        self.dom = dom

    def resolve(self, description):
        if description == "x button":
            return self.dom["elements"][0], {"tier": "slm", "reason": "conf=0.90: it says x"}
        return None, {"tier": None, "reason": "no tier produced a confident match",
                      "candidates": []}


def _desc_executor(tiers, **kw):
    ex = VizDomDescExecutor(detector="modular", tiers=tiers,
                            resolver_factory=_FakeResolver, **kw)
    # the DOM the pipeline would have produced for state "s" - no models here
    ex._dom_cache["s"] = {"image_size": {"width": 100, "height": 50},
                          "elements": [{"id": "E1", "role": "button",
                                        "visual_type": "button", "text": "x",
                                        "bounds": [0, 0, 10, 10]}]}
    return ex


def test_desc_executor_scores_like_the_other_columns(tmp_path):
    _FakeResolver.made = 0
    ex = _desc_executor(["lexical", "slm"])
    assert ex.name == "vizdom-modular+desc[lexical+slm]"
    payload = run_benchmark(_DESC_MANIFEST, [ex], out_dir=str(tmp_path))
    s = payload["results"][ex.name]["summary"]
    assert (s["action_hit_rate"], s["verify_accuracy"], s["false_pass_rate"]) == (1.0, 1.0, 0.0)
    rows = {r["step"]: r for r in payload["results"][ex.name]["steps"]}
    assert rows["a1"]["outcome"] == [5, 5] and rows["a1"]["detail"].startswith("tier=slm")
    assert rows["v1"]["outcome"] == "PASSED"
    assert rows["v2"]["outcome"] == "FAILED" and rows["v2"]["detail"].startswith("tier=none")
    assert s["cost"]["resolved_by_tier"] == {"slm": 2, "none": 1}
    assert s["cost"]["tiers"] == ["lexical", "slm"]
    # one resolver per step: the verify step must not be answered from the
    # action step's cached resolution
    assert _FakeResolver.made == 3


def test_desc_executor_rejects_unknown_tier():
    with pytest.raises(ValueError, match="lexical"):
        VizDomDescExecutor(detector="modular", tiers=["lexical", "magic"])
    with pytest.raises(ValueError):
        VizDomDescExecutor(detector="modular", tiers=[])


def test_desc_executor_availability_is_honest():
    # the model-free chain never needs a server
    ok, why = _desc_executor(["lexical"]).available()
    assert ok and "no model" in why
    # a model tier with no Ollama behind it says so and names the fix
    ok, why = _desc_executor(["slm"], host="http://127.0.0.1:9").available()
    assert not ok and "ollama serve" in why


def test_desc_executor_needs_description_on_the_step():
    ex = _desc_executor(["lexical"])
    with pytest.raises(RuntimeError, match="regenerate"):
        ex.run_step({"id": "s", "image": "none.png"},
                    {"id": "a", "kind": "action", "locator": 'text="x"'})


class _BrokenExecutor:
    """Every step raises - a broken environment, not a measured zero."""

    name = "boom"

    def run_step(self, state, step):
        # Shaped like a transformers import error: two lines and a '|'.
        raise RuntimeError("no module named nothing\n"
                           "requires: torch>=2.6 | got 2.5.1")

    def cost_summary(self):
        return {}


def test_runner_marks_all_errored_column_failed_not_zero(tmp_path):
    """A column whose every step errored exits 1 AND writes a FAILED row:
    the sweep's summary.md is built from these .md files, and a 0.0 row
    there would look like a measurement (GPU kit review, 2026-10-26)."""
    manifest = {
        "benchmark": "unit",
        "states": [{"id": "s", "image": "none.png", "gt": "none.json"}],
        "steps": [
            {"id": "a1", "state": "s", "kind": "action", "locator": "text=x",
             "instruction": "click x", "target_id": "E1",
             "target_bounds": [0, 0, 10, 10]},
        ],
    }
    with pytest.raises(SystemExit) as info:
        run_benchmark(manifest, [_BrokenExecutor()], out_dir=str(tmp_path))
    assert info.value.code == 1

    md = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    body = md.splitlines()[2:]
    assert len(body) == 1, f"error text must not spill into extra rows: {body}"
    row = body[0]
    assert row.startswith("| boom |")
    assert "FAILED" in row and "0.0" not in row
    assert "no module named nothing" in row and "got 2.5.1" in row
    assert row.count("|") == 7, "a '|' in the error text must not add a cell"
    payload = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["results"]["boom"]["summary"]["all_steps_errored"] is True
