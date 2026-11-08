"""The step-by-step run comparison (compare.py) on hand-written result files."""

import json
import tarfile

import pytest

from visual_dom.evaluation.lifecycle.compare import (
    diff,
    load_sets,
    match_key,
    model_twins,
    report,
    summarize,
    unpack,
)

DESC = "vizdom-modular+desc[lexical+slm]"


def _act(sid, hit, outcome=(1, 1)):
    return {"step": sid, "kind": "action", "outcome": list(outcome), "hit": hit, "detail": ""}


def _ver(sid, outcome, correct, false_pass=False, detail=""):
    return {"step": sid, "kind": "verify", "outcome": outcome, "correct": correct,
            "false_pass": false_pass, "detail": detail}


def _result(steps, verify=None):
    cost = {"verify": verify} if verify else {}
    return {"summary": {"cost": cost}, "steps": steps}


def _write(d, stamp, benchmark, results):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stamp}.json").write_text(json.dumps(
        {"benchmark": benchmark, "commit": "abc", "generated_steps": 0, "results": results}),
        encoding="utf-8")


def test_old_desc_rows_pair_with_the_verify_chain_twin():
    # runs before ADR-022 1.9 recorded no verify mode and scored with the chain
    old = match_key(DESC, _result([]))
    assert old == (DESC, "chain")
    assert match_key(DESC + "[verify=chain]", _result([], verify="chain")) == old
    assert match_key(DESC, _result([], verify="keyword")) != old
    assert match_key("vizdom-uied", _result([])) == ("vizdom-uied", None)


def test_diff_counts_identical_gains_and_losses():
    ref = _result([_act("a", True), _act("b", False), _ver("c", "PASSED", True)])
    new = _result([_act("a", True), _act("b", True, (5, 5)), _ver("c", "FAILED", False)])
    same, gains, losses = diff(new, ref)
    assert (same, gains, losses) == (1, ["b"], ["c"])


def test_twins_differ_only_in_a_model_or_verify_suffix():
    names = {DESC, DESC + "[verify=chain]", "vizdom-modular+desc[lexical+vlm]",
             "vizdom-modular+desc[lexical+vlm][vlm=qwen2.5vl:7b]", "vizdom-uied"}
    assert sorted(model_twins(names)) == [
        (DESC, DESC + "[verify=chain]"),
        ("vizdom-modular+desc[lexical+vlm]", "vizdom-modular+desc[lexical+vlm][vlm=qwen2.5vl:7b]")]


def test_false_passes_are_counted_over_the_negatives_by_kind():
    manifest = {"n1": {"expect": "FAILED", "negative_kind": "same-app"},
                "n2": {"expect": "FAILED"},
                "p1": {"expect": "PASSED"}}
    res = _result([_ver("n1", "PASSED", False, True), _ver("n2", "FAILED", True),
                   _ver("p1", "PASSED", True), _act("x", False)])
    s = summarize(res, manifest)
    assert (s["false_passes"], s["negatives"]) == (1, 2)
    assert s["fp_by_kind"] == {"same-app": 1}
    assert s["neg_kinds"] == {"same-app": 1, "nonsense": 1}
    assert s["action_hit"] == 0.0 and s["verify_acc"] == pytest.approx(2 / 3)


def test_a_rerun_replaces_the_row_and_realworld_is_its_own_set(tmp_path):
    _write(tmp_path, "20261101_000000", "syn", {"vizdom-uied": _result([_act("a", False)])})
    _write(tmp_path, "20261102_000000", "syn", {"vizdom-uied": _result([_act("a", True)])})
    _write(tmp_path / "realworld", "20261102_000000", "rw",
           {"vizdom-uied": _result([_act("app__s/act/E1", True)])})
    sets = load_sets(tmp_path)
    assert set(sets) == {"syn", "rw"}
    assert sets["syn"]["vizdom-uied"]["steps"][0]["hit"] is True


def test_report_from_a_tarball_against_a_reference(tmp_path):
    run = tmp_path / "gpu-20261110_000000"
    _write(run / "realworld", "20261110_000001", "rw", {
        DESC + "[verify=chain]": _result([_act("app__s/act/E1", True),
                                          _ver("app__s/verify-neg/X", "PASSED", False, True,
                                               "tier=slm picked | E9")], verify="chain")})
    (run / "gpu.txt").write_text("commit: abc", encoding="utf-8")
    tgz = tmp_path / "gpu-20261110_000000.tar.gz"
    with tarfile.open(tgz, "w:gz") as tar:
        tar.add(run, arcname=run.name)
    ref = tmp_path / "local"
    _write(ref, "20261102_000000", "rw", {DESC: _result([_act("app__s/act/E1", False)])})
    # unpack next to the tarball, once
    import shutil
    shutil.rmtree(run)
    text = report(tgz, [ref], manifest_root=tmp_path / "none")
    assert unpack(tgz) == run and run.is_dir()
    assert "| " + DESC + "[verify=chain] | " + DESC + " | 0/1 | +1 | -0 |" in text
    assert "action-hit per application" in text and "| app |" in text
    # the detail's '|' would break the Markdown table
    assert "tier=slm picked / E9" in text


def test_unpack_refuses_member_paths_outside_the_run(tmp_path):
    evil = tmp_path / "x.tar.gz"
    payload = tmp_path / "p.txt"
    payload.write_text("x")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="../escape.txt")
    with pytest.raises(ValueError, match="unsafe"):
        unpack(evil)
