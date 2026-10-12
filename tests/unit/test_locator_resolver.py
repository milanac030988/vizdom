"""Shared locator resolution (ADR-028): one resolver for the RF library and the Viewer."""

import json

import pytest

from visual_gui_library.keywords.capture import CaptureKeywords
from visual_gui_library.locators import ElementFinder, LocatorResolver


def _dom():
    return {
        "image_size": [400, 300],
        "elements": [
            {"id": "E1", "text": "Save", "role": "button", "bounds": [0, 0, 40, 20]},
            {"id": "E2", "text": "+", "role": "button", "bounds": [50, 0, 70, 20]},
            {"id": "E3", "text": "+", "role": "button", "bounds": [80, 0, 100, 20]},
            {"id": "E4", "hint": "Email", "role": "edittext", "bounds": [0, 40, 200, 60]},
        ],
    }


class _StubDesc:
    """Stands in for DescriptionResolver: picks a fixed id when it is a candidate."""

    def __init__(self, pick):
        self.pick = pick
        self.calls = []

    def resolve(self, description, within=None):
        self.calls.append((description, within))
        pool = within if within is not None else _dom()["elements"]
        for e in pool:
            if e["id"] == self.pick:
                return e, {"tier": "stub", "reason": "picked"}
        return None, {"tier": "stub", "reason": "no", "candidates": []}


def _resolver(pick=None):
    stub = _StubDesc(pick)
    return LocatorResolver(ElementFinder(_dom()), lambda: stub), stub


def test_single_alternative_resolves():
    r, _ = _resolver()
    assert r.resolve("text=Save")["id"] == "E1"


def test_fallback_alternative_wins_and_is_reported():
    r, _ = _resolver()
    result = r.explain("text=Missing || id=E4")
    assert result.ok and result.element["id"] == "E4"
    assert result.alternative == 1 and result.used_fallback
    assert result.attempts == [("text=Missing", "not found")]


def test_ambiguous_alternative_falls_through():
    r, _ = _resolver()
    assert r.resolve("text=+ || id=E3")["id"] == "E3"


def test_desc_disambiguates_an_ambiguous_match():
    r, stub = _resolver(pick="E3")
    element = r.resolve('text=+ || desc="plus key on the right"')
    assert element["id"] == "E3"
    # arbitration grounds over just the two "+" candidates, not the whole DOM
    _, within = stub.calls[0]
    assert sorted(e["id"] for e in within) == ["E2", "E3"]


def test_not_found_message_is_unchanged():
    r, _ = _resolver()
    with pytest.raises(ValueError, match=r"^Element not found: text=Nope$"):
        r.resolve("text=Nope")


def test_ambiguity_message_names_the_contract():
    r, _ = _resolver()
    with pytest.raises(ValueError, match="did not resolve to exactly one element"):
        r.resolve("text=+")


def test_unparseable_locator():
    r, _ = _resolver()
    result = r.explain("type=button")
    assert not result.ok
    with pytest.raises(ValueError, match="Could not parse locator"):
        r.resolve("type=button")


def test_resolve_all_returns_every_match_of_first_matching_alternative():
    r, _ = _resolver()
    assert [e["id"] for e in r.resolve_all("text=Nope || text=+")] == ["E2", "E3"]


def test_keyword_delegates_to_the_shared_resolver(tmp_path):
    path = tmp_path / "dom.json"
    path.write_text(json.dumps(_dom()))
    kw = CaptureKeywords()
    kw.load_visual_dom(str(path))
    assert kw.get_visual_element("text=Missing || hint=Email")["id"] == "E4"
    assert [e["id"] for e in kw.get_visual_elements("role=button")] == ["E1", "E2", "E3"]
    with pytest.raises(ValueError, match="Element not found"):
        kw.get_visual_element("text=Nope")


def test_for_dom_builds_a_working_resolver():
    r = LocatorResolver.for_dom(_dom())
    assert r.resolve("hint=Email")["id"] == "E4"
