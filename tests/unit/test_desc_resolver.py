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
    # role word only: score 1.0 < 1.5
    r = DescriptionResolver(_dom(_btn("E1", "Save")), tiers=["lexical"])
    elem, info = r.resolve("frobnicate button")
    assert elem is None
    assert "lexical: best score 1.00 < 1.5" in info["reason"]


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
    assert info["reason"] == ("no confident match (lexical: best score 1.00 < 1.5; "
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


def test_confident_answers_are_unchanged():
    r = DescriptionResolver(_dom(_btn("E1", "Save"), _btn("E2", "Cancel", x=50)), tiers=["lexical"])
    elem, info = r.resolve("save button")
    assert elem["id"] == "E1" and info["tier"] == "lexical" and info["reason"] == "score=3.00"
