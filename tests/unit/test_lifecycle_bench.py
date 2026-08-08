"""
Unit tests for the full-lifecycle benchmark harness.

The harness itself must be trustworthy before its numbers are: these tests pin
the step generator's contract (uniqueness rule, dual representation, negative
oracle steps) and the scoring semantics (action-hit, verdicts, false-pass)
using a synthetic manifest and a scripted executor — no models, no images.
"""

import json

from visual_dom.evaluation.lifecycle.generate import generate_steps
from visual_dom.evaluation.lifecycle.runner import _inside, _score, run_benchmark


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
