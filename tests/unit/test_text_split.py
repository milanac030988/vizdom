"""
`_split_by_text_positions` guards (Step 4b).

The splitter exists for UIED's merged blobs - two buttons detected as one box.
Its failure mode is splitting a SINGLE control whose caption happens to contain
several OCR boxes. Two guards prevent that:

* the element's own `interactable=True` flag (ADR/IMPROVEMENTS §3b), and
* coincidence with a detector-marked interactable (IoU >= 0.8) - because
  rescan/merge stages emit copies of detector boxes with `interactable=None`,
  and splitting the copy is splitting the control. The motivating case is the
  IWT "Send Logfiles" tile (session 20260810_160751): icon glyph OCR-reads as
  'LoG' above the caption, and the rescan copy of the tile was cut at the
  icon/caption boundary into two half-tiles.

Geometry from that real session.
"""

import pytest

from visual_dom.core.domain.pipeline import UIElement, VisualDOMPipeline


@pytest.fixture
def pipeline():
    return VisualDOMPipeline(ocr_engine="easyocr", detector="uied", use_gpu=False)


def elem(id_, bounds, vtype="button", interactable=None, text=None, source="uied"):
    return UIElement(id=id_, bounds=bounds, visual_type=vtype, confidence=0.9,
                     ocr_text=text, interactable=interactable, source=source)


def text_box(id_, bounds, text):
    return elem(id_, bounds, vtype="text", text=text, source="text")


# Real geometry: the tile, its icon glyph text, and its caption.
TILE = (273, 60, 392, 179)
ICON_TEXT = (303, 90, 361, 112)      # OCR reads the LOG glyph as text
CAPTION = (297, 144, 370, 162)


def split_ids(result):
    return [e.id for e in result if e.source == "text_split"]


def test_own_interactable_flag_blocks_split(pipeline):
    tile = elem("tile", TILE, interactable=True, text="LoG", source="omniparser")
    texts = [text_box("t1", ICON_TEXT, "LoG"), text_box("t2", CAPTION, "Send Logfiles")]
    result = pipeline._split_by_text_positions([tile] + texts, texts)
    assert split_ids(result) == []
    assert tile in result


def test_coincident_detector_box_blocks_split(pipeline):
    """
    The regression: a rescan copy (interactable=None) of a detector-marked
    tile must not be split - the detector's segmentation is the authority,
    whichever element happens to carry the flag.
    """
    detector_tile = elem("op", (273, 60, 393, 181), vtype="block",
                         interactable=True, source="omniparser")
    rescan_copy = elem("rescan", TILE, interactable=None, text="LoG", source="rescan")
    texts = [text_box("t1", ICON_TEXT, "LoG"), text_box("t2", CAPTION, "Send Logfiles")]

    result = pipeline._split_by_text_positions(
        [detector_tile, rescan_copy] + texts, texts)

    assert split_ids(result) == [], "rescan copy of a detector tile was split"
    assert rescan_copy in result
    assert rescan_copy.visual_type != "block", "copy was demoted despite the guard"


def test_true_merged_blob_still_splits(pipeline):
    """
    The splitter's actual job survives the new guard: two side-by-side controls
    detected as one UIED blob, with NO coincident detector interactable, split.
    """
    blob = elem("blob", (100, 100, 300, 140))
    texts = [text_box("t1", (110, 110, 150, 130), "+"),
             text_box("t2", (250, 110, 290, 130), "-")]

    result = pipeline._split_by_text_positions([blob] + texts, texts)

    pieces = [e for e in result if e.source == "text_split"]
    assert len(pieces) == 2, "genuine merged blob no longer splits"
    assert sorted(p.ocr_text for p in pieces) == ["+", "-"]


def test_distant_detector_box_does_not_block(pipeline):
    """The guard is coincidence (IoU), not mere existence of interactables."""
    far_away = elem("far", (800, 400, 900, 450), interactable=True,
                    source="omniparser")
    blob = elem("blob", (100, 100, 300, 140))
    texts = [text_box("t1", (110, 110, 150, 130), "+"),
             text_box("t2", (250, 110, 290, 130), "-")]

    result = pipeline._split_by_text_positions([far_away, blob] + texts, texts)

    assert len(split_ids(result)) == 2
