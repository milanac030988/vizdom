"""Exported locators use only what the locator language understands (ADR-028)."""

from visual_dom_viewer.core.element_definition import ElementDefinition
from visual_dom_viewer.core.tree import BoundingBox, DOMElement, ElementType
from visual_dom_viewer.export.locators import (
    build_locator,
    definition_locator,
    element_locator,
)
from visual_dom_viewer.export.robot_exporter import RobotResourceExporter
from visual_gui_library.locators import LocatorParser, LocatorResolver


def _element(text="Save", role="button", eid="E7"):
    return DOMElement(id=eid, type=ElementType.BUTTON, text=text,
                      bbox=BoundingBox(x=10, y=10, width=40, height=20),
                      properties={"role": role, "visual_type": "button"})


def _definition(props, **values):
    base = {"text": "Save", "type": "button", "role": "button", "id": "E7",
            "bbox": [10, 10, 40, 20], "center": [30, 20], "x": 10,
            "confidence": 0.9}
    base.update(values)
    return ElementDefinition(element_id="E7", name="SaveButton",
                             selected_properties=set(props), property_values=base)


def _parses_fully(locator):
    """Every part of every alternative survived parsing (nothing silently dropped)."""
    for raw in LocatorParser.split_alternatives(locator):
        parsed = LocatorParser.parse(raw)
        assert parsed, raw
        assert all(not loc.modifiers for loc in parsed), raw


def test_element_locator_is_semantic_then_id():
    assert element_locator(_element()) == "text=Save role=button || id=E7"


def test_element_locator_quotes_spaces():
    loc = element_locator(_element(text="Save as"))
    assert loc == 'text="Save as" role=button || id=E7'
    _parses_fully(loc)


def test_element_without_text_uses_hint_then_id():
    elem = _element(text="", role="edittext")
    elem.properties["hint"] = "Email"
    assert element_locator(elem) == "hint=Email role=edittext || id=E7"


def test_definition_skips_properties_without_a_locator():
    loc, skipped = definition_locator(_definition(["text", "bbox", "confidence"]))
    assert loc == "text=Save"
    assert sorted(skipped) == ["bbox", "confidence"]
    _parses_fully(loc)


def test_definition_type_maps_to_dom_role():
    loc, _ = definition_locator(_definition(["type"], role="Button"))
    assert loc == "role=Button"


def test_definition_id_is_a_fallback_not_an_and():
    loc, _ = definition_locator(_definition(["text", "id"]))
    assert loc == "text=Save || id=E7"


def test_definition_with_only_geometry_falls_back_to_id():
    loc, skipped = definition_locator(_definition(["bbox", "center"]))
    assert loc == "id=E7"
    assert sorted(skipped) == ["bbox", "center"]


def test_chain_separator_in_text_is_quoted():
    loc = build_locator([("text", "a||b")], "E1")
    assert loc == 'text="a||b" || id=E1'
    assert len(LocatorParser.split_alternatives(loc)) == 2


def test_exported_locator_resolves_after_ids_shift():
    """The point of the semantic primary: a re-analysis that renumbers elements."""
    loc = element_locator(_element())
    shifted = {"elements": [
        {"id": "E1", "text": "Open", "role": "button", "bounds": [0, 0, 1, 1]},
        {"id": "E9", "text": "Save", "role": "button", "bounds": [10, 10, 50, 30]},
    ]}
    assert LocatorResolver.for_dom(shifted).resolve(loc)["id"] == "E9"


def test_resource_uses_the_real_library_and_keywords():
    exporter = RobotResourceExporter()
    variables = exporter._generate_definition_variables([_definition(["text", "bbox"])])
    assert "${SAVEBUTTON}    text=Save" in variables
    assert "left out: bbox" in variables
    keywords = "\n".join(exporter._generate_definition_keyword(
        _definition(["text"]), "SaveButton", "button", "Save"))
    assert "Click Visual    ${SaveButton}" in keywords
    assert "Click Element" not in keywords
    assert "Library          VisualGuiLibrary" in exporter.RESOURCE_TEMPLATE
