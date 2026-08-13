"""
Confidence must be a real score, not a default.

Before this fix every OmniParser element carried confidence 1.0: OmniParser
computes YOLO logits but drops them before building its box dicts, and our
backend's `item.get("confidence", 1.0)` always took the fallback. Ensemble OCR
confidences were also lost, because OmniParser's ocr_bbox/ocr_text lists carry
no confidence channel. The DOM's Confidence column was provenance masquerading
as certainty (1.0 = "came from OmniParser").

Recovery happens at the boundaries, entirely in our code (the OmniParser repo
is vendored outside git): YOLO scores are recorded by wrapping predict_yolo,
OCR scores ride along as 3-tuples from the provider, and both are matched back
onto parsed items by IoU.

Ranking (NMS / dedup / top-N) deliberately still treats OmniParser elements as
1.0 (`_ranking_confidence`): raw logits are not on the same scale as the UIED
heuristic constants, and re-ranking with them would change which box survives a
conflict. Only the *reported* number changed.
"""

import pytest

from visual_dom.adapters.outbound.detectors.omniparser_backend import (
    OmniParserBackend, _iou,
)
from visual_dom.core.domain.pipeline import UIElement, VisualDOMPipeline


def backend() -> OmniParserBackend:
    """A bare instance - no weights, no models; only the parsing methods."""
    b = OmniParserBackend.__new__(OmniParserBackend)
    b._ocr_ensemble = True
    b._ocr_dedup_iou = 0.5
    return b


def item(bbox_ratio, type_="icon", content=None, interactivity=True):
    return {"type": type_, "bbox": bbox_ratio, "content": content,
            "interactivity": interactivity}


# --------------------------------------------------------------------------
# score recovery in _parse_content_list
# --------------------------------------------------------------------------

def test_icon_gets_matched_yolo_score():
    # 1000x500 image; icon at px (100,100,200,150) == ratio (0.1,0.2,0.2,0.3)
    parsed = [item([0.1, 0.2, 0.2, 0.3], content="settings icon")]
    yolo = [((100.0, 100.0, 200.0, 150.0), 0.37)]

    dets = backend()._parse_content_list(parsed, 1000, 500, yolo_scores=yolo)

    assert len(dets) == 1
    assert dets[0].confidence == pytest.approx(0.37)


def test_text_gets_matched_ocr_score():
    parsed = [item([0.1, 0.2, 0.2, 0.3], type_="text", content="Send Logfiles",
                   interactivity=False)]
    ocr = [([100, 100, 200, 150], 0.82)]

    dets = backend()._parse_content_list(parsed, 1000, 500, ocr_scores=ocr)

    assert dets[0].confidence == pytest.approx(0.82)


def test_unmatched_item_keeps_the_fallback():
    """No source box within IoU 0.5 -> the historical 1.0 ('score unknown')."""
    parsed = [item([0.1, 0.2, 0.2, 0.3], content="icon")]
    far_away = [((800.0, 400.0, 900.0, 450.0), 0.9)]

    dets = backend()._parse_content_list(parsed, 1000, 500, yolo_scores=far_away)

    assert dets[0].confidence == 1.0


def test_best_iou_wins_among_candidates():
    """A slightly shifted box (OmniParser absorbing an OCR box) still matches;
    the closest candidate provides the score."""
    parsed = [item([0.1, 0.2, 0.2, 0.3], content="icon")]
    yolo = [
        ((104.0, 103.0, 206.0, 152.0), 0.41),   # shifted a few px - the real one
        ((100.0, 100.0, 300.0, 300.0), 0.90),   # much larger box, low IoU
    ]

    dets = backend()._parse_content_list(parsed, 1000, 500, yolo_scores=yolo)

    assert dets[0].confidence == pytest.approx(0.41)


def test_text_and_icon_scores_do_not_cross():
    """A text item never takes a YOLO score and vice versa."""
    parsed = [
        item([0.1, 0.2, 0.2, 0.3], type_="text", content="Low", interactivity=False),
        item([0.5, 0.5, 0.6, 0.6], content="icon"),
    ]
    yolo = [((100.0, 100.0, 200.0, 150.0), 0.11)]   # overlaps the TEXT item
    ocr = [([500, 250, 600, 300], 0.77)]            # overlaps the ICON item

    dets = backend()._parse_content_list(parsed, 1000, 500,
                                         yolo_scores=yolo, ocr_scores=ocr)

    assert dets[0].confidence == 1.0    # text item: no OCR box matches it
    assert dets[1].confidence == 1.0    # icon item: no YOLO box matches it


# --------------------------------------------------------------------------
# provider confidences through _apply_ocr_provider
# --------------------------------------------------------------------------

def test_provider_3tuples_yield_scores():
    b = backend()
    b._ocr_provider = lambda img: [((10, 10, 50, 20), "Hello", 0.91),
                                   ((60, 10, 90, 20), "World", 0.45)]
    texts, boxes, scores = b._apply_ocr_provider(None, [], [])

    assert texts == ["Hello", "World"]
    assert scores == [([10, 10, 50, 20], 0.91), ([60, 10, 90, 20], 0.45)]


def test_provider_2tuples_still_work():
    """Older providers / plugins that return (bbox, text) contribute no score
    but must not break."""
    b = backend()
    b._ocr_provider = lambda img: [((10, 10, 50, 20), "Hello")]
    texts, boxes, scores = b._apply_ocr_provider(None, [], [])

    assert texts == ["Hello"]
    assert scores == []


def test_provider_failure_returns_no_scores():
    def boom(img):
        raise RuntimeError("provider died")

    b = backend()
    b._ocr_provider = boom
    texts, boxes, scores = b._apply_ocr_provider(None, ["kept"], [[1, 2, 3, 4]])

    assert texts == ["kept"]
    assert scores is None


# --------------------------------------------------------------------------
# pipeline: real scores must not change filtering or ranking
# --------------------------------------------------------------------------

@pytest.fixture
def pipeline():
    return VisualDOMPipeline(ocr_engine="easyocr", detector="uied", use_gpu=False)


def elem(id_, bounds, conf, source, vtype="button", text=None):
    return UIElement(id=id_, bounds=bounds, visual_type=vtype,
                     confidence=conf, ocr_text=text, source=source)


def test_filter_keeps_low_score_omniparser_elements(pipeline):
    """The backend already applied its own box_threshold (as low as 0.03);
    the generic 0.3 gate must not delete its detections."""
    faint = elem("f", (10, 10, 60, 40), 0.07, "omniparser")
    kept = pipeline._filter_elements([faint])
    assert faint in kept


def test_filter_still_gates_other_sources(pipeline):
    noise = elem("n", (10, 10, 60, 40), 0.07, "uied")
    assert pipeline._filter_elements([noise]) == []


def test_nms_winner_unchanged_by_real_scores(pipeline):
    """Overlapping omniparser (real score 0.2) vs uied (constant 0.6): the
    omniparser box must still win, exactly as it did when it carried 1.0."""
    op = elem("op", (10, 10, 100, 50), 0.2, "omniparser")
    ui = elem("ui", (12, 12, 102, 52), 0.6, "uied")

    kept = pipeline._apply_cross_type_nms([ui, op])

    assert op in kept
    assert ui not in kept


def test_dedup_prefers_omniparser_over_heuristic_constant(pipeline):
    op = elem("op", (10, 10, 100, 50), 0.15, "omniparser", text="OK")
    ui = elem("ui", (11, 11, 101, 51), 0.8, "uied", text="OK")

    kept = pipeline._remove_duplicates([ui, op])

    assert len(kept) == 1
    assert kept[0].id == "op"


def test_iou_helper():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert _iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert _iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)
