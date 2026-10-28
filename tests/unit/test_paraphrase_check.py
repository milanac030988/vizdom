"""The paraphrase check: table coverage and the scoring path (lexical tier only)."""
import json
from pathlib import Path

import pytest

from visual_dom.evaluation.lifecycle import paraphrase as pc

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not (ROOT / pc.MANIFEST).exists(), reason="benchmark manifest not checked out")
def test_every_manifest_description_has_both_paraphrases():
    manifest = json.loads((ROOT / pc.MANIFEST).read_text(encoding="utf-8"))
    table = json.loads((ROOT / pc.PARAPHRASES).read_text(encoding="utf-8"))
    descriptions = {s["description"] for s in manifest["steps"]}
    for variant in ("terse", "wordy"):
        missing = descriptions - set(table[variant])
        assert not missing, f"{variant} lacks {sorted(missing)[:5]}"
        # a paraphrase that equals the original would measure nothing
        same = [d for d in descriptions if table[variant][d].strip().lower() == d.lower()]
        assert not same, f"{variant} repeats the original for {same[:5]}"


def _dom():
    return {"image_size": [200, 100], "elements": [
        {"id": "E1", "bounds": [0, 0, 50, 20], "role": "button", "text": "Save"},
        {"id": "E2", "bounds": [60, 0, 110, 20], "role": "button", "text": "Cancel"},
        {"id": "E3", "bounds": [0, 40, 100, 60], "role": "input_field", "text": "Search..."},
    ]}


def test_scoring_matches_the_runner_on_a_fake_dom(tmp_path):
    (tmp_path / "s1.json").write_text(json.dumps(_dom()), encoding="utf-8")
    manifest = {"steps": [
        {"id": "s1/act/E1", "state": "s1", "kind": "action", "description": "Save button",
         "target_bounds": [0, 0, 50, 20]},
        {"id": "s1/verify/E1", "state": "s1", "kind": "verify", "description": "Save button",
         "expect": "PASSED", "target_bounds": [0, 0, 50, 20]},
        {"id": "s1/verify-neg/X", "state": "s1", "kind": "verify", "description": "Frobnicate button",
         "expect": "FAILED", "target_bounds": None},
    ]}
    mapping = {"Save button": "Save", "Frobnicate button": "the Frobnicate button"}
    summary, rows = pc.run_variant(manifest, tmp_path, mapping, ["lexical"], "m", "http://x")
    assert summary["action_hit_rate"] == 1.0 and summary["actions"] == 1
    assert summary["verify_accuracy"] == 1.0 and summary["false_pass_rate"] == 0.0
    assert summary["strict_verify_pos"] == 1.0 and summary["verify_pos"] == 1
    assert summary["resolved_by_tier"] == {"lexical": 2, "none": 1}
    assert [r["description"] for r in rows] == ["Save", "Save", "the Frobnicate button"]


def test_original_variant_uses_the_manifest_wording(tmp_path):
    (tmp_path / "s1.json").write_text(json.dumps(_dom()), encoding="utf-8")
    manifest = {"steps": [{"id": "s1/act/E3", "state": "s1", "kind": "action",
                           "description": "Search... input field",
                           "target_bounds": [0, 40, 100, 60]}]}
    summary, rows = pc.run_variant(manifest, tmp_path, None, ["lexical"], "m", "http://x")
    assert rows[0]["description"] == "Search... input field" and rows[0]["hit"]


def test_missing_paraphrase_is_an_error(tmp_path):
    (tmp_path / "s1.json").write_text(json.dumps(_dom()), encoding="utf-8")
    manifest = {"steps": [{"id": "s1/act/E1", "state": "s1", "kind": "action",
                           "description": "Save button", "target_bounds": [0, 0, 50, 20]}]}
    with pytest.raises(SystemExit, match="no paraphrase"):
        pc.run_variant(manifest, tmp_path, {}, ["lexical"], "m", "http://x")
