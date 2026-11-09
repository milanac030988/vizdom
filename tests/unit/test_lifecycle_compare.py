"""The step-by-step run comparison (compare.py) on hand-written result files."""

import json
import tarfile

import pytest

from visual_dom.evaluation.lifecycle.compare import (
    diff,
    load_sets,
    match_key,
    mcnemar,
    model_twins,
    report,
    summarize,
    unpack,
    wilson,
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


def test_wilson_bounds_zero_of_n_and_stays_in_range():
    lo, hi = wilson(0, 92)
    assert lo == 0.0 and abs(hi - 0.0401) < 0.0005      # 0 false passes of 92
    lo, hi = wilson(360, 453)                            # action-hit 0.795
    assert abs(lo - 0.755) < 0.002 and abs(hi - 0.829) < 0.002
    assert wilson(5, 5)[1] == 1.0 and wilson(0, 0) == (None, None)


def _steps(oks, kind="action"):
    return [{"step": f"s{i}", "kind": kind, "hit": ok, "correct": ok} for i, ok in enumerate(oks)]


def test_mcnemar_counts_only_discordant_steps():
    # 6 steps only a got right, 1 only b, 3 both: p = 2 * P(X <= 1 | n=7) = 16/128
    a = _steps([True] * 6 + [False] + [True] * 3)
    b = _steps([False] * 6 + [True] + [True] * 3)
    only_a, only_b, p = mcnemar(a, b)
    assert (only_a, only_b) == (6, 1) and abs(p - 0.125) < 1e-9
    assert mcnemar(a, a)[2] == 1.0
    # steps the other run did not score are ignored
    assert mcnemar(a, b[:5])[:2] == (5, 0)


def test_summary_splits_verify_into_present_and_absent():
    manifest = {"p1": {"expect": "PASSED"}, "p2": {"expect": "PASSED"},
                "n1": {"expect": "FAILED", "negative_kind": "same-app"}}
    yes_to_all = {"steps": [
        {"step": "p1", "kind": "verify", "correct": True},
        {"step": "p2", "kind": "verify", "correct": True},
        {"step": "n1", "kind": "verify", "correct": False, "false_pass": True}]}
    s = summarize(yes_to_all, manifest)
    assert s["present_pass"] == 1.0 and s["absent_fail"] == 0.0 and s["balanced"] == 0.5
    assert s["false_passes"] == 1 and s["fp_ci"][0] > 0
    # an errored negative is not a false pass, and not in its interval
    errored = {"steps": yes_to_all["steps"][:2] + [
        {"step": "n1", "kind": "verify", "correct": False, "detail": "error: timeout"}]}
    s = summarize(errored, manifest)
    assert s["false_passes"] == 0 and s["fp_ci"][0] == 0.0 and s["absent_fail"] == 0.0


def test_unpack_renames_folders_windows_cannot_create(tmp_path):
    tgz = tmp_path / "gpu-x.tar.gz"
    payload = tmp_path / "p.json"
    payload.write_text("{}")
    with tarfile.open(tgz, "w:gz") as tar:
        tar.add(payload, arcname="gpu-x/s-doms/m_desc[lexical_vlm][vlm=qwen2.5vl:7b]/a.json")
    run = unpack(tgz)
    assert (run / "s-doms" / "m_desc[lexical_vlm][vlm=qwen2.5vl_7b]" / "a.json").is_file()
    assert not (tmp_path / "gpu-x.unpacking").exists()


def test_unpack_refuses_member_paths_outside_the_run(tmp_path):
    evil = tmp_path / "x.tar.gz"
    payload = tmp_path / "p.txt"
    payload.write_text("x")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="../escape.txt")
    with pytest.raises(ValueError, match="unsafe"):
        unpack(evil)
