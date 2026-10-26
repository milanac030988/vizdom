"""
Step 6b2: a text element inside a control that already carries the same
literal is dropped, so a `text=` locator resolves to exactly one element.

Lifecycle benchmark 2026-10-26 (RTX 4090, a4cb85e): the modular backend was
32 click steps behind the omniparser column, every one of them "2 matches" on
a value-bearing input field. Both backends fuse the value's OCR box into the
field; the modular backend reports it as `text` (a literal read) where the
monolith adapter reports it as `label`. Step 1 then adds the value again as a
standalone text element, which the wide field cannot absorb in Step 4
(max_merge_area). With this rule both columns yield the same DOM.
"""

import pytest

from visual_dom.core.domain.pipeline import UIElement, VisualDOMPipeline


@pytest.fixture
def pipeline():
    return VisualDOMPipeline(ocr_engine="easyocr", detector="uied", use_gpu=False)


def elem(id_, bounds, vtype, text=None, conf=0.9, source="modular"):
    return UIElement(id=id_, bounds=bounds, visual_type=vtype,
                     confidence=conf, ocr_text=text, source=source)


def test_value_text_inside_field_with_same_text_is_dropped(pipeline):
    # form_sidebar_0007: field (353,315,1106,376) reads "Online"; the OCR box
    # of the value (365,337,406,352) comes back as a standalone text element.
    field = elem("f", (353, 315, 1106, 376), "input_field", "Online")
    value = elem("v", (365, 337, 406, 352), "text", "Online", conf=0.99, source="text")

    kept = pipeline._drop_absorbed_text_duplicates([value, field])

    assert kept == [field]


def test_match_is_case_and_space_insensitive(pipeline):
    field = elem("f", (0, 0, 800, 60), "input_field", "Online ")
    value = elem("v", (10, 20, 60, 40), "text", "online", source="text")

    assert pipeline._drop_absorbed_text_duplicates([value, field]) == [field]


def test_text_with_different_content_stays(pipeline):
    field = elem("f", (0, 0, 800, 60), "input_field", "Online Offline")
    value = elem("v", (10, 20, 60, 40), "text", "Online", source="text")

    kept = pipeline._drop_absorbed_text_duplicates([value, field])

    assert value in kept and field in kept


def test_text_outside_the_control_stays(pipeline):
    field = elem("f", (0, 0, 800, 60), "input_field", "Online")
    sibling = elem("s", (0, 100, 60, 120), "text", "Online", source="text")

    kept = pipeline._drop_absorbed_text_duplicates([sibling, field])

    assert sibling in kept and field in kept


def test_block_containers_do_not_absorb(pipeline):
    """A block is a layout container, not a control; text inside it stays."""
    block = elem("b", (0, 0, 1900, 1000), "block", "Online")
    value = elem("v", (10, 20, 60, 40), "text", "Online", source="text")

    kept = pipeline._drop_absorbed_text_duplicates([value, block])

    assert value in kept and block in kept


def test_control_without_text_keeps_its_text_child(pipeline):
    """The monolith shape (field text=None, label only) is untouched: the
    value text is the only element the locator can find and must survive."""
    field = elem("f", (353, 315, 1106, 376), "input_field", None)
    field.label = "Online "
    value = elem("v", (365, 337, 406, 352), "text", "Online", source="text")

    kept = pipeline._drop_absorbed_text_duplicates([value, field])

    assert value in kept and field in kept


def test_no_op_on_empty(pipeline):
    assert pipeline._drop_absorbed_text_duplicates([]) == []
