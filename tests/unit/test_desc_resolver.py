"""
DescriptionResolver (ADR-022): a miss must explain itself per tier.

Lifecycle run 4 (2026-10-27) left 401 of 514 steps of the vlm-only column
with the bare "no tier produced a confident match", so the result file could
not tell a null answer from an out-of-range mark or a low confidence. The
chain now reports each tier's own verdict in the reason.
"""

from visual_gui_library.locators.desc_resolver import DescriptionResolver


def _dom(*elements):
    return {"image_size": {"width": 100, "height": 100}, "elements": list(elements)}


def _btn(eid, text, x=0):
    return {"id": eid, "role": "button", "visual_type": "button", "text": text,
            "bounds": [x, 0, x + 10, 10]}


def test_lexical_reports_no_candidate():
    r = DescriptionResolver(_dom(_btn("E1", "Save")), tiers=["lexical"])
    elem, info = r.resolve("frobnicate icon")
    assert elem is None and info["tier"] is None
    assert "lexical: no element shares a token or role word" in info["reason"]
    assert info["reason"].startswith("no confident match (")


def test_lexical_reports_score_below_floor():
    # role word only, and the description names something the button does
    # not carry: the role earns half credit, 0.5 < 1.5
    r = DescriptionResolver(_dom(_btn("E1", "Save")), tiers=["lexical"])
    elem, info = r.resolve("frobnicate button")
    assert elem is None
    assert "lexical: best score 0.50 < 1.5" in info["reason"]


def test_lexical_reports_tie_between_repeated_captions():
    # two buttons that both read "1": the table-digit case of run 4
    r = DescriptionResolver(_dom(_btn("E1", "1"), _btn("E2", "1", x=50)), tiers=["lexical"])
    elem, info = r.resolve("1 button")
    assert elem is None
    assert "lexical: tie at 3.00 between 2 candidates" in info["reason"]


def test_every_tier_leaves_its_own_verdict(monkeypatch):
    r = DescriptionResolver(_dom(_btn("E1", "Save")), screenshot=None,
                            tiers=["lexical", "slm", "vlm"])
    # the SLM declines with a low confidence; no screenshot, so the VLM is skipped
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: (None, "slm not confident (0.30)"))
    elem, info = r.resolve("frobnicate button")
    assert elem is None
    assert info["reason"] == ("no confident match (lexical: best score 0.50 < 1.5; "
                              "slm not confident (0.30); vlm skipped: no screenshot)")


def test_vlm_verdict_is_kept(monkeypatch):
    import numpy as np
    r = DescriptionResolver(_dom(_btn("E1", "Save")),
                            screenshot=np.zeros((100, 100, 3), dtype=np.uint8), tiers=["vlm"])
    monkeypatch.setattr(r, "_resolve_vlm",
                        lambda description, candidates: (None, "vlm returned out-of-range mark 37"))
    elem, info = r.resolve("save button")
    assert elem is None
    assert info["reason"] == "no confident match (vlm returned out-of-range mark 37)"


def test_dead_ollama_is_named_in_the_reason():
    # nothing listens on port 9: the tier's "unavailable" verdict must survive
    # into the reason, so preflight and the bench can tell it from a miss
    r = DescriptionResolver(_dom(_btn("E1", "Save")), tiers=["slm"],
                            host="http://127.0.0.1:9")
    elem, info = r.resolve("save button")
    assert elem is None and info["tier"] is None
    assert "slm unavailable:" in info["reason"]


def _text(eid, s, y=0):
    return {"id": eid, "role": "text", "visual_type": "text", "text": s,
            "bounds": [0, y, 100, y + 10]}


def test_model_tiers_never_see_a_single_candidate(monkeypatch):
    """Lifecycle run 4's one false pass: 'Purple Elephant button' on a dialog
    whose only scored element was the Retry button (the Cancel caption was
    unread), so the SLM got a ONE-row table and said yes at 0.85. The
    shortlist is now padded from the pool to at least three rows."""
    dom = _dom(_text("E3", "An error occurred", 20), _text("E4", "request:", 30),
               _btn("E6", "Retry", 60))
    r = DescriptionResolver(dom, tiers=["lexical", "slm"])
    seen = {}
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: seen.update(c=list(candidates)) or (None, "slm not confident (0.00)"))
    elem, info = r.resolve("Purple Elephant button")
    assert elem is None
    ids = [e["id"] for e in seen["c"]]
    assert ids[0] == "E6", "the lexical top stays first"
    assert len(ids) >= 3 and set(ids) == {"E6", "E3", "E4"}


def test_shortlist_is_whole_pool_when_it_is_small():
    dom = _dom(_btn("E6", "Retry"), _text("E3", "oops", 20))
    cands = DescriptionResolver._shortlist([(1.0, dom["elements"][0])], dom["elements"])
    assert [e["id"] for e in cands] == ["E6", "E3"]
    # nothing scored at all: the whole pool, unchanged
    assert DescriptionResolver._shortlist([], dom["elements"]) == dom["elements"]


def test_shortlist_keeps_lexical_top_eight_and_pads_only_below_three():
    pool = [_btn(f"E{i}", f"b{i}", x=i * 12) for i in range(12)]
    ranked = [(1.0, e) for e in pool[:10]]
    assert [e["id"] for e in DescriptionResolver._shortlist(ranked, pool)] == [f"E{i}" for i in range(8)]
    ranked2 = [(1.0, pool[5]), (0.9, pool[7])]
    ids = [e["id"] for e in DescriptionResolver._shortlist(ranked2, pool)]
    assert ids == ["E5", "E7", "E0"]


def test_slm_prompt_offers_null_plainly_without_an_explanatory_rule(monkeypatch):
    # Lifecycle run 6: an explanatory null rule ("answer null unless text or
    # role clearly corresponds; role alone is NOT a match") made qwen2.5:3b
    # answer six of six nonsense captions over a whole-DOM table. The plain
    # "Use null if no element matches" wording declines; keep it plain.
    dom = _dom(_btn("E6", "Retry"))
    r = DescriptionResolver(dom, tiers=["slm"])
    captured = {}

    class _Advisor:
        def _call_llm(self, prompt, image_b64=None):
            captured["prompt"] = prompt
            return '{"id": null, "confidence": 0.0, "reason": "none"}'
    monkeypatch.setattr(r, "_make_advisor", lambda model: _Advisor())
    r.resolve("Purple Elephant button")
    p = captured["prompt"]
    assert "or to none" in p and "Use null if no element matches" in p
    assert "role alone" not in p and "clearly corresponds" not in p


def test_confident_answers_are_unchanged():
    r = DescriptionResolver(_dom(_btn("E1", "Save"), _btn("E2", "Cancel", x=50)), tiers=["lexical"])
    elem, info = r.resolve("save button")
    assert elem["id"] == "E1" and info["tier"] == "lexical" and info["reason"] == "score=3.00"


# -- position words (review, 2026-10-28) --------------------------------------

def _corner_dom():
    # E1: a button top-left; E2, E3: text bottom-right; E4: a button bottom-right
    return _dom(_btn("E1", "Retry"),
                {"id": "E2", "role": "text", "visual_type": "text", "text": "oops",
                 "bounds": [80, 80, 100, 90]},
                {"id": "E3", "role": "text", "visual_type": "text", "text": "again",
                 "bounds": [80, 90, 100, 100]},
                _btn("E4", "Close", x=90) | {"bounds": [90, 90, 100, 100]})


def test_position_filter_cannot_leave_the_model_a_single_row(monkeypatch):
    """The position filter used to run after the padding and could cut the
    table back to one row - the case SHORTLIST_MIN exists for."""
    r = DescriptionResolver(_corner_dom(), tiers=["slm"])
    seen = {}
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: seen.update(c=list(candidates)) or (None, "slm not confident (0.00)"))
    elem, info = r.resolve("top left Purple Elephant button")
    assert elem is None
    ids = [e["id"] for e in seen["c"]]
    assert ids[0] == "E1", "the only element in place stays first"
    assert len(ids) >= DescriptionResolver.SHORTLIST_MIN


def test_model_answer_outside_the_described_position_is_rejected(monkeypatch):
    dom = _corner_dom()
    r = DescriptionResolver(dom, tiers=["slm"])
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: (dom["elements"][3], "conf=0.95: close"))
    elem, info = r.resolve("top left Purple Elephant button")
    assert elem is None and info["tier"] is None
    assert "slm picked E4 outside the described position (conf=0.95: close)" in info["reason"]


def test_lexical_does_not_resolve_positional_nonsense():
    """'top left Purple Elephant button': position + role used to score 2.0 on
    their own and resolve the top-left button confidently - a false pass with
    no model involved. Role and position now earn half credit when the
    description names something the element does not carry."""
    r = DescriptionResolver(_corner_dom(), tiers=["lexical"])
    elem, info = r.resolve("top left Purple Elephant button")
    assert elem is None
    assert "lexical: best score 1.00 < 1.5" in info["reason"]


def test_lexical_still_resolves_a_position_only_description():
    # no name token: role + position are the whole description, and resolve
    r = DescriptionResolver(_corner_dom(), tiers=["lexical"])
    elem, info = r.resolve("the button at the top left")
    assert elem is not None and elem["id"] == "E1" and info["tier"] == "lexical"
    elem, info = r.resolve("bottom right button")
    assert elem is not None and elem["id"] == "E4"


def test_named_description_still_resolves_by_name_with_position():
    r = DescriptionResolver(_corner_dom(), tiers=["lexical"])
    elem, info = r.resolve("top left Retry button")
    assert elem is not None and elem["id"] == "E1"


# -- second review round (2026-10-28): "right now" and qualifiers ------------

def test_right_now_is_not_a_position():
    """'the button that checks for updates right now' filtered out every
    candidate with cx <= 0.66, the 4 Check Now targets included, before the
    model saw them. A position word counts only inside a positional phrase."""
    from visual_gui_library.locators.desc_resolver import parse_description
    assert parse_description("the button that checks for updates right now")[3] == []
    assert len(parse_description("the button on the right")[3]) == 1
    assert len(parse_description("top left Purple Elephant button")[3]) == 2
    assert len(parse_description("right side panel")[3]) == 1
    assert len(parse_description("left button")[3]) == 1
    assert len(parse_description("right click menu")[3]) == 0
    assert parse_description("left")[3] != []


def test_check_now_target_stays_in_the_shortlist(monkeypatch):
    # Check Now sits at the left (cx 0.06-0.26 in the benchmark); the wordy
    # paraphrase must not geometry-filter it away
    dom = _dom(_btn("E1", "Check Now"), _btn("E2", "Refresh", x=90),
               _text("E3", "Updates", 50))
    r = DescriptionResolver(dom, tiers=["lexical", "slm"])
    seen = {}
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: seen.update(c=[e["id"] for e in candidates]) or (dom["elements"][0], "conf=0.9"))
    elem, info = r.resolve("the button that checks for updates right now")
    assert "E1" in seen["c"]
    assert elem is not None and elem["id"] == "E1" and info["tier"] == "slm"


def test_qualifiers_do_not_make_a_description_naming():
    r = DescriptionResolver(_corner_dom(), tiers=["lexical"])
    for desc in ("the small button at the top left", "the big blue button at the top left",
                 "the main button, top left"):
        elem, info = r.resolve(desc)
        assert elem is not None and elem["id"] == "E1", desc
    # an unknown adjective still names something the element does not carry:
    # the safe side is a decline, not a guess
    elem, info = r.resolve("the frobnicating button at the top left")
    assert elem is None
