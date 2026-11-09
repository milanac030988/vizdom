"""The audit's statistics and its two offline constructions (no model, no OCR)."""
import inspect

import pytest

from visual_dom.evaluation.lifecycle import audit as au


# -- clusters ----------------------------------------------------------------

def test_state_and_group_of_real_and_synthetic_step_ids():
    assert au.state_of("7zip__about/act/E2") == "7zip__about"
    assert au.group_of("7zip__about/act/E2") == "7zip"
    assert au.group_of("form_sidebar_0007/verify/E3") == "form_sidebar"


def test_cluster_bootstrap_is_wider_than_independence_when_clusters_disagree():
    # two screens all right, two all wrong: 50 % with no within-screen noise
    rows = [(f"s{c}/act/E{i}", c < 2) for c in range(4) for i in range(25)]
    lo, hi = au.cluster_bootstrap(rows, au.state_of, n_boot=2000, seed=1)
    wlo, whi = au.wilson(50, 100)
    assert lo < wlo and hi > whi, "100 steps on 4 screens are 4 observations, not 100"
    # and it is deterministic for a seed
    assert (lo, hi) == au.cluster_bootstrap(rows, au.state_of, n_boot=2000, seed=1)
    assert au.cluster_bootstrap([], au.state_of) == (None, None)


def test_zero_of_clusters_bound():
    assert au.zero_of_clusters_bound(46) == pytest.approx(0.0630, abs=1e-3)
    assert au.zero_of_clusters_bound(0) is None


def test_cluster_permutation_exact_for_few_clusters():
    # A right and B wrong on every step of 5 screens: the only sign pattern as
    # extreme as the observed one is all-plus or all-minus -> 2 / 32
    a = [(f"s{c}/v/{i}", True) for c in range(5) for i in range(3)]
    b = [(s, False) for s, _ in a]
    total, p = au.cluster_permutation(a, b, au.state_of)
    assert total == 15 and p == pytest.approx(2 / 32)
    # no difference at all
    assert au.cluster_permutation(a, a, au.state_of) == (0.0, 1.0)


def test_cluster_permutation_discounts_a_difference_that_lives_on_one_screen():
    # 20 steps better, all on one screen: McNemar sees 20 coins, the screen test sees 1
    a = [(f"s0/v/{i}", True) for i in range(20)] + [(f"s{c}/v/0", True) for c in range(1, 6)]
    b = [(f"s0/v/{i}", False) for i in range(20)] + [(f"s{c}/v/0", True) for c in range(1, 6)]
    rows = lambda r: [{"step": s, "kind": "verify", "correct": ok} for s, ok in r]   # noqa: E731
    assert au.mcnemar(rows(a), rows(b))[2] < 0.001
    assert au.cluster_permutation(a, b, au.state_of)[1] == 1.0


def test_holm_adjusts_in_order_and_never_below_the_raw_value():
    assert au.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert au.holm([0.5]) == [0.5] and au.holm([]) == []


# -- the scorer patch --------------------------------------------------------

def test_scorer_settings_changes_the_constants_only_inside_the_block():
    from visual_gui_library.locators import desc_resolver as dr
    before = (dr.lexical_rank, dr.lexical_confident, dr.EXACT_NAME_BONUS)
    elems = [{"id": "E1", "role": "button", "text": "Save As", "bounds": [0, 0, 10, 10]},
             {"id": "E2", "role": "button", "text": "Open", "bounds": [20, 0, 30, 10]}]
    assert dr.lexical_rank(elems, "Save button")[0][0] == 3.0
    with au.scorer_settings(name=1.0, role=0.5, floor=9.0):
        ranked = dr.lexical_rank(elems, "Save button")
        assert ranked[0][0] == 1.5
        assert dr.lexical_confident(ranked) is None, "the floor was raised to 9"
    assert (dr.lexical_rank, dr.lexical_confident, dr.EXACT_NAME_BONUS) == before
    assert dr.lexical_confident(dr.lexical_rank(elems, "Save button")) is elems[0]
    with pytest.raises(ValueError, match="unknown constants"):
        with au.scorer_settings(nonsense=1):
            pass


def test_every_weight_literal_the_sweep_replaces_still_occurs_exactly_once():
    from visual_gui_library.locators import desc_resolver as dr
    src = inspect.getsource(dr.lexical_rank)
    for key, (literal, _) in au._WEIGHT_PATTERNS.items():
        assert src.count(literal) == 1, f"{key}: the sweep would silently sweep something else"
    sig = inspect.signature(dr.lexical_confident).parameters
    assert sig["min_score"].default == au.DEFAULTS["floor"]
    assert sig["min_margin"].default == au.DEFAULTS["margin"]
    assert dr.EXACT_NAME_BONUS == au.DEFAULTS["exact_bonus"]


# -- near-miss negatives -----------------------------------------------------

def _labels():
    return {
        "app__main": {"elements": [{"ocr_text": "Save As"}, {"ocr_text": "Find Next"}],
                      "all_names": ["Save As", "Find Next", "Help"]},
        "app__other": {"elements": [{"ocr_text": "Save"}, {"ocr_text": "Export"}],
                       "all_names": ["Save", "Export"]},
    }


def _steps():
    def pos(state, cap, word="button"):
        return {"id": f"{state}/verify/{cap}", "state": state, "kind": "verify",
                "locator": f'text="{cap}"', "description": f"{cap} {word}", "expect": "PASSED"}
    return [pos("app__main", "Save As"), pos("app__main", "Find Next"),
            pos("app__other", "Save"), pos("app__other", "Export")]


def test_near_miss_negatives_are_built_without_looking_at_any_scorer():
    negs = au.near_miss_negatives(_labels(), _steps())
    got = {(n["state"], n["negative_kind"], n["description"]) for n in negs}
    assert ("app__main", "sibling", "Save button") in got       # "Save" is elsewhere, "Save As" here
    assert ("app__main", "truncation", "Find button") in got    # "Find Next" minus its last word
    assert ("app__other", "sibling", "Save As button") in got   # contains this screen's "Save"
    # "Export" shares no word sequence with app__main: an ordinary negative, not a near miss
    assert not any(s == "app__main" and "Export" in d for s, _, d in got)
    # never a caption the screen itself carries, and never the same one twice
    assert not any(s == "app__main" and d.startswith("Save As") for s, _, d in got)
    assert len(negs) == len({n["id"] for n in negs})
    assert all(n["expect"] == "FAILED" for n in negs)


def test_near_miss_is_scored_as_the_locators_score_and_under_the_exact_rule():
    dom = {"image_size": [200, 100], "elements": [
        {"id": "E1", "role": "button", "visual_type": "button", "text": "Save As", "bounds": [0, 0, 60, 20]},
        {"id": "E2", "role": "button", "visual_type": "button", "text": "Open", "bounds": [70, 0, 120, 20]}]}
    assert au.text_matches(dom, "Save"), "text= falls back to a substring match"
    elem = au.desc_match(dom, "Save button")
    assert elem is not None and elem["text"] == "Save As"
    assert not au.exact_name(elem, "Save button", dom)
    assert au.exact_name(au.desc_match(dom, "Save As button"), "Save As button", dom)
    c = au.lexical_scores([{"state": "s", "kind": "verify", "expect": "FAILED",
                            "description": "Save button"}], {"s": dom})
    assert c["false_pass"] == 1
    c = au.lexical_scores([{"state": "s", "kind": "verify", "expect": "FAILED",
                            "description": "Save button"}], {"s": dom}, strict=True)
    assert c["false_pass"] == 0


def test_contains_sequence_is_adjacent_and_ordered():
    assert au.contains_sequence(["save", "as", "copy"], ["save", "as"])
    assert not au.contains_sequence(["save", "the", "as"], ["save", "as"])
    assert not au.contains_sequence(["as", "save"], ["save", "as"])
    assert not au.contains_sequence(["save"], [])


def test_near_miss_manifest_is_one_the_runner_takes():
    data = {"benchmark": "lifecycle-realworld-v1", "seed": 42, "steps": _steps(),
            "states": [{"id": "app__main", "image": "i/app__main.png", "gt": "l/app__main.json"},
                       {"id": "app__other", "image": "i/app__other.png", "gt": "l/app__other.json"},
                       {"id": "app__unused", "image": "i/u.png", "gt": "l/u.json"}]}
    m = au.near_miss_manifest(data, _labels())
    assert m["benchmark"] == au.NEAR_MISS_BENCHMARK and m["source"] == "lifecycle-realworld-v1"
    assert {s["id"] for s in m["states"]} == {"app__main", "app__other"}
    assert all(s["negative_kind"] == "sibling" for s in m["steps"]), "truncations are opt-in"
    step = next(s for s in m["steps"] if s["state"] == "app__main")
    assert step == {"id": "app__main/near-miss/Save", "state": "app__main", "kind": "verify",
                    "locator": 'text="Save"', "instruction": "the 'Save' button is visible",
                    "description": "Save button", "expect": "FAILED",
                    "target_id": None, "target_bounds": None, "negative_kind": "sibling"}
    both = au.near_miss_manifest(data, _labels(), kinds=("sibling", "truncation"))
    assert {s["negative_kind"] for s in both["steps"]} == {"sibling", "truncation"}
    assert au.state_of(step["id"]) == "app__main"


def test_the_committed_near_miss_manifest_matches_its_source():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    bench = root / "benchmarks"
    src = json.loads((bench / "lifecycle-realworld-v1" / "steps.json").read_text(encoding="utf-8"))
    saved = json.loads((bench / au.NEAR_MISS_BENCHMARK / "steps.json").read_text(encoding="utf-8"))
    labels = {s["id"]: json.loads((root / s["gt"]).read_text(encoding="utf-8"))
              for s in src["states"]}
    assert saved == au.near_miss_manifest(src, labels)
    assert len(saved["steps"]) == 168
    assert {s["state"] for s in saved["steps"]} <= {s["id"] for s in src["states"]}
