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
    # both read exactly "1", so both take the exact-name bonus: still a tie
    assert "lexical: tie at 3.50 between 2 candidates" in info["reason"]


def _txt(eid, text, x=0):
    return {"id": eid, "role": "staticText", "visual_type": "text", "text": text,
            "bounds": [x, 0, x + 10, 10]}


def test_exact_text_breaks_a_tie_with_a_longer_caption():
    # run 8, Windows Settings: "Display" against "Select a display to change"
    # both scored 2.0 and the margin refused to choose (ADR-022 1.13)
    r = DescriptionResolver(_dom(_txt("E1", "Select a display to change"),
                                 _txt("E2", "Display", x=50)), tiers=["lexical"])
    elem, info = r.resolve("Display button")
    assert elem["id"] == "E2" and info["tier"] == "lexical"


def test_exact_text_needs_the_same_word_order():
    # PuTTY: "Implicit LF in every CR" must not take the bonus from the
    # caption that holds the same words in another order
    r = DescriptionResolver(_dom(_txt("E1", "Implicit CR in every LF"),
                                 _txt("E2", "Implicit LE in every CR", x=50)),
                            tiers=["lexical"])
    elem, _ = r.resolve("Implicit LF in every CR checkbox")
    assert elem is None or elem["id"] != "E1"


def test_exact_text_bonus_cannot_lift_a_partial_match_over_the_floor():
    # the bonus needs the whole name, so an absent caption stays absent
    r = DescriptionResolver(_dom(_txt("E1", "Import")), tiers=["lexical"])
    elem, _ = r.resolve("Export button")
    assert elem is None


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


def _slm_answer(monkeypatch, r, reply):
    class _Advisor:
        def _call_llm(self, prompt, image_b64=None):
            return reply
    monkeypatch.setattr(r, "_make_advisor", lambda model: _Advisor())


def test_slm_answer_with_the_rows_id_prefix_is_read(monkeypatch):
    # real-world baseline 2026-11-09, winsettings__power: two 'Power & battery'
    # candidates tie, qwen2.5:3b answers "id=E38" (the table row's prefix) and
    # the resolver threw the right answer away as an unknown id
    dom = _dom(_btn("E37", "Power & battery"), _btn("E38", "Power & battery", x=50))
    for reply in ('{"id": "id=E38", "confidence": 0.9, "reason": "x"}',
                  '{"id": "ID: E38", "confidence": 0.9, "reason": "x"}'):
        r = DescriptionResolver(dom, tiers=["slm"])
        _slm_answer(monkeypatch, r, reply)
        elem, info = r.resolve("Power & battery button")
        assert elem is not None and elem["id"] == "E38", info["reason"]


def test_slm_prefixed_answers_are_still_validated(monkeypatch):
    dom = _dom(_btn("E1", "Save"), _btn("E2", "Cancel", x=50))
    # an id that is not in the DOM stays rejected; "id=null" is a decline
    for reply, verdict in (('{"id": "id=E99", "confidence": 0.9}', "slm returned unknown id 'E99'"),
                           ('{"id": "id=null", "confidence": 0.9}', "slm not confident (0.90)")):
        r = DescriptionResolver(dom, tiers=["slm"])
        _slm_answer(monkeypatch, r, reply)
        elem, info = r.resolve("frobnicate button")
        assert elem is None and verdict in info["reason"]
    # the prefix is stripped only at the start: an id that merely contains it
    # is not rewritten
    assert DescriptionResolver._parse_id_json('{"id": "grid=E1", "confidence": 1}')[0] == "grid=E1"


def test_confident_answers_are_unchanged():
    r = DescriptionResolver(_dom(_btn("E1", "Save"), _btn("E2", "Cancel", x=50)), tiers=["lexical"])
    elem, info = r.resolve("save button")
    # 2.0 overlap + 0.5 exact name ("Save") + 1.0 role
    assert elem["id"] == "E1" and info["tier"] == "lexical" and info["reason"] == "score=3.50"


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


def test_model_answer_without_the_named_number_is_rejected(monkeypatch):
    """Run-7 DOMs, '1 button' on a pager the parser had not read: with digits
    out of the substring bonus the shortlist held only role-matched buttons
    and the SLM picked 'Add New'. A number has no paraphrase."""
    dom = _dom(_btn("E2", "Add New"), _btn("E3", "Export", x=20),
               _text("E15", "+1.234 567 890", 50), _text("E33", "1,234", 70))
    r = DescriptionResolver(dom, tiers=["lexical", "slm"])
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: (dom["elements"][0], "conf=1.00: a button"))
    elem, info = r.resolve("1 button")
    assert elem is None and info["tier"] is None
    assert "slm picked E2 without the named number(s) 1 (conf=1.00: a button)" in info["reason"]


def test_model_answer_carrying_the_named_number_is_kept(monkeypatch):
    dom = _dom(_btn("E2", "Add New"), _btn("E9", "Page 2", x=20), _btn("E10", "Page 2", x=40))
    r = DescriptionResolver(dom, tiers=["lexical", "slm"])
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: (dom["elements"][1], "conf=0.90: page two"))
    elem, info = r.resolve("page 2 button")
    assert elem["id"] == "E9" and info["tier"] == "slm"
    assert DescriptionResolver._named_numbers("the 100% zoom button at the top") == ["100"]


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


# -- third review round (2026-10-28): captions that contain a position word --

def _toolbar():
    # three alignment buttons, all in the right third of the screen
    return _dom(_btn("E1", "Align Left", x=70), _btn("E2", "Align Center", x=80),
                _btn("E3", "Align Right", x=90), _btn("E4", "Save", x=0))


def test_caption_with_a_position_word_is_a_name_for_the_lexical_tier():
    from visual_gui_library.locators.desc_resolver import parse_description
    for desc in ("Align Left button", "Turn Right button", "Scroll Left icon",
                 "Align Right button", "Top Up button"):
        assert parse_description(desc)[3] == [], desc
    r = DescriptionResolver(_toolbar(), tiers=["lexical"])
    elem, info = r.resolve("Align Left button")
    assert elem is not None and elem["id"] == "E1" and info["tier"] == "lexical"
    elem, info = r.resolve("Align Right button")
    assert elem is not None and elem["id"] == "E3"


def test_caption_with_a_position_word_is_not_geometry_filtered(monkeypatch):
    dom = _toolbar()
    r = DescriptionResolver(dom, tiers=["slm"])
    monkeypatch.setattr(r, "_resolve_slm",
                        lambda description, candidates: (dom["elements"][0], "conf=0.9"))
    elem, info = r.resolve("Align Left button")
    assert elem is not None and elem["id"] == "E1", info


def test_bare_position_word_before_a_role_is_a_caption_only_when_the_screen_has_it():
    # a button that reads "Left" sits at the right; "Left button" means it
    with_caption = _dom(_btn("E1", "Save", x=0), _btn("E2", "Left", x=90))
    elem, info = DescriptionResolver(with_caption, tiers=["lexical"]).resolve("Left button")
    assert elem is not None and elem["id"] == "E2"
    # no element reads "Left": the leftmost button
    without = _dom(_btn("E1", "Save", x=0), _btn("E2", "Cancel", x=90))
    elem, info = DescriptionResolver(without, tiers=["lexical"]).resolve("left button")
    assert elem is not None and elem["id"] == "E1"


def _text(eid, text, y):
    return {"id": eid, "role": "staticText", "visual_type": "text", "text": text,
            "bounds": [0, y, 40, y + 8]}


def test_entry_role_words_are_roles_not_names():
    # real-application set, lexical run 1: "General tree item" scored a third
    # of the overlap because "tree" and "item" counted as name words
    from visual_gui_library.locators.desc_resolver import parse_description
    for desc in ("General tree item", "Editing list item", "File menu item",
                 "Auto radio button"):
        name_tokens, naming, roles, _ = parse_description(desc)
        assert len(naming) == 1, (desc, naming)
        assert roles, desc
    tree = _dom(_text("E1", "General", 10), _text("E2", "Editor", 30),
                _btn("E3", "Cancel", x=60))
    elem, info = DescriptionResolver(tree, tiers=["lexical"]).resolve("General tree item")
    assert elem is not None and elem["id"] == "E1" and info["tier"] == "lexical"
    radio = _dom({"id": "E1", "role": "button", "visual_type": "checkbox", "text": "Auto",
                  "bounds": [0, 0, 30, 10]}, _btn("E2", "Close", x=60))
    elem, _ = DescriptionResolver(radio, tiers=["lexical"]).resolve("Auto radio button")
    assert elem is not None and elem["id"] == "E1"


def test_entry_role_word_does_not_resolve_an_absent_caption():
    # the role is "which kind", never "which one": an absent name still declines
    tree = _dom(_text("E1", "General", 10), _text("E2", "Editor", 30))
    elem, _ = DescriptionResolver(tree, tiers=["lexical"]).resolve("Shortcuts tree item")
    assert elem is None


def test_a_number_is_not_part_of_another_number():
    # real-application set: a saturation field reading 100, OCR'd as "1001",
    # passed the absent "100% button" through the substring bonus
    dom = _dom(_btn("E1", "1001"), _btn("E2", "Cancel", x=60))
    elem, _ = DescriptionResolver(dom, tiers=["lexical"]).resolve("100% button")
    assert elem is None
    # words keep their substring bonus ("setting" -> "Settings")
    dom = _dom(_btn("E1", "Settings"), _btn("E2", "Cancel", x=60))
    elem, _ = DescriptionResolver(dom, tiers=["lexical"]).resolve("setting button")
    assert elem is not None and elem["id"] == "E1"
