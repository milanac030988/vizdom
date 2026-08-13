"""
OCR line-merge policy (`TextDetector._merge_text_boxes`).

The rule decides whether two OCR fragments are one phrase or two independent
labels. Getting it wrong in the permissive direction is expensive: three links
fused into one 295 px element cannot be clicked by any locator, and nothing
downstream can undo the fusion because the fragments no longer exist.

Pure geometry over `TextElement`s - no OCR engine is constructed, so these run
anywhere. The coordinates in `test_quick_links_stay_separate` are the real ones
from session 20260807_094630, the failure this rule was written for.
"""

import pytest

from visual_dom.adapters.outbound.ocr.text_detector import TextDetector, TextElement


@pytest.fixture
def detector():
    # No engine is loaded until detect() is called, so this is cheap.
    return TextDetector(ocr_engine="easyocr", gpu=False)


def box(text, x1, y1, x2, y2, conf=0.99, id_=None):
    return TextElement(id=id_ or text[:4], text=text, bounds=(x1, y1, x2, y2),
                       confidence=conf)


def texts(elements):
    return sorted(e.text for e in elements)


# --------------------------------------------------------------------------
# the regression this rule exists for
# --------------------------------------------------------------------------

def test_quick_links_stay_separate(detector):
    """
    Three distinct links on one row, 13 px apart at 15 px text height.

    Real geometry from session 20260807_094630. The old fixed 20 px threshold
    chained all three into 'Printer Management > Docupedia > My IT Profile >'
    spanning x=82..377 (element E71).
    """
    links = [
        box("Printer Management >", 82, 468, 203, 483),
        box("Docupedia >", 216, 468, 284, 483),
        box("My IT Profile >", 297, 468, 377, 483),
    ]
    result = detector._merge_text_boxes(links)

    assert len(result) == 3, f"links were fused: {texts(result)}"
    assert texts(result) == texts(links)
    assert max(e.width for e in result) < 130


def test_two_links_stay_separate(detector):
    """The same row's other over-merge: 'IT Incidents >' + 'NG Portal >'."""
    result = detector._merge_text_boxes([
        box("IT Incidents >", 390, 465, 465, 483),
        box("NG Portal >", 478, 465, 543, 483),
    ])
    assert len(result) == 2


# --------------------------------------------------------------------------
# what must still merge
# --------------------------------------------------------------------------

def test_character_split_merges(detector):
    """OCR splitting one word must still be repaired: a 2 px gap at 14 px text."""
    result = detector._merge_text_boxes([
        box("Docu", 216, 468, 250, 482),
        box("pedia", 252, 468, 284, 482),
    ])
    assert len(result) == 1
    assert result[0].text == "Docu pedia"
    assert result[0].bounds == (216, 468, 284, 482)


def test_chain_of_fragments_merges(detector):
    """A phrase broken into three tight fragments merges into one box."""
    result = detector._merge_text_boxes([
        box("Add", 121, 468, 145, 482),
        box("Remove", 148, 468, 200, 482),
        box("Software", 203, 468, 246, 482),
    ])
    assert len(result) == 1
    assert result[0].bounds == (121, 468, 246, 482)


def test_threshold_scales_with_text_height(detector):
    """
    The same 13 px gap is one phrase in a 40 px heading and two labels in
    15 px body text - which is the whole point of a ratio.
    """
    heading = detector._merge_text_boxes([
        box("Workplace", 100, 100, 200, 140),
        box("Toolkit", 213, 100, 290, 140),
    ])
    body = detector._merge_text_boxes([
        box("Workplace", 100, 300, 200, 315),
        box("Toolkit", 213, 300, 290, 315),
    ])
    assert len(heading) == 1, "a 13 px gap in 40 px text is a word space"
    assert len(body) == 2, "a 13 px gap in 15 px text separates two labels"


def test_tiny_text_uses_the_pixel_floor(detector):
    """At 6 px text the ratio is under 3 px, so the floor keeps splits merging."""
    result = detector._merge_text_boxes([
        box("ab", 10, 10, 20, 16),
        box("cd", 22, 10, 32, 16),
    ])
    assert len(result) == 1


# --------------------------------------------------------------------------
# line membership
# --------------------------------------------------------------------------

def test_different_lines_never_merge(detector):
    """Vertically disjoint boxes are separate however close horizontally."""
    result = detector._merge_text_boxes([
        box("first line", 10, 10, 100, 24),
        box("second line", 102, 40, 200, 54),
    ])
    assert len(result) == 2


def test_partial_vertical_overlap_is_not_a_line(detector):
    """
    A short label and a taller neighbour that dips below it share only 43% of
    the shorter box - similar top edges (8 px apart) used to be enough.
    """
    result = detector._merge_text_boxes([
        box("label", 10, 20, 50, 34),
        box("other", 55, 28, 120, 58),
    ])
    assert len(result) == 2


def test_row_does_not_drift_into_the_next_line(detector):
    """
    Row membership is judged against the row's band, not the last member.

    Real IWT geometry: a taller neighbour ('Application Control', y=400..417)
    overlaps '(BlackList)' on the line BELOW (y=409..421). Chaining member-to-
    member pulled '(BlackList)' into the row, where it sat between 'Low' and
    'Protection' in x-order and broke their merge.
    """
    result = detector._merge_text_boxes([
        box("Application Control", 23, 398, 122, 412),
        box("User Info", 179, 398, 226, 409),
        box("Application Control", 669, 400, 768, 417, id_="AC2"),
        box("Low", 814, 396, 838, 409),
        box("(BlackList)", 814, 409, 871, 421),
        box("Protection", 838, 397, 891, 407),
    ])
    texts_out = texts(result)
    assert "Low Protection" in texts_out, f"status text split: {texts_out}"
    assert "(BlackList)" in texts_out, "next line was merged into the row"


def test_overlapping_boxes_are_left_alone(detector):
    """A negative gap means the boxes overlap; that is dedup's job, not ours."""
    result = detector._merge_text_boxes([
        box("Printer Management", 82, 468, 203, 483),
        box("Management", 150, 468, 203, 483),
    ])
    assert len(result) == 2


# --------------------------------------------------------------------------
# edges
# --------------------------------------------------------------------------

def test_empty_input(detector):
    assert detector._merge_text_boxes([]) == []


def test_single_element_passes_through_unchanged(detector):
    only = box("Enabled", 815, 465, 857, 483)
    result = detector._merge_text_boxes([only])
    assert result == [only]


def test_merge_keeps_union_box_and_averages_confidence(detector):
    result = detector._merge_text_boxes([
        box("Add", 121, 468, 145, 482, conf=1.0),
        box("Remove", 148, 466, 200, 484, conf=0.6),
    ])
    assert len(result) == 1
    assert result[0].bounds == (121, 466, 200, 484)
    assert result[0].confidence == pytest.approx(0.8)


def test_caller_can_override_the_policy(detector):
    """The thresholds are parameters, so a caller can restore old behaviour."""
    links = [
        box("Printer Management >", 82, 468, 203, 483),
        box("Docupedia >", 216, 468, 284, 483),
    ]
    assert len(detector._merge_text_boxes(links)) == 2
    assert len(detector._merge_text_boxes(links, gap_height_ratio=2.0)) == 1
