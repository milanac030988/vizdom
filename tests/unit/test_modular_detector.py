"""
Modular three-stage detector (ADR-027): fusion semantics + orchestration.

The fusion tests pin the ported `remove_overlap_new` behaviour - including its
deliberate quirks - because the parity combo depends on the port being
faithful, not pretty. The backend tests run the full orchestration with fake
stages: no model, no weights, no OCR engine.
"""

import numpy as np
import pytest

from visual_dom.adapters.outbound.detectors.modular_backend import (
    ModularDetectorBackend, NoneCaptioner, create_captioner,
    create_region_proposer,
)
from visual_dom.adapters.outbound.detectors.modular_fusion import FusedBox, fuse
from visual_dom.core.ports.outbound.captioner_port import Captioner
from visual_dom.core.ports.outbound.region_proposer_port import (
    RegionProposal, RegionProposer,
)


# --------------------------------------------------------------------------
# fusion: the ported remove_overlap_new semantics
# --------------------------------------------------------------------------

def kinds(fused):
    return [(f.kind, f.content) for f in fused]


def test_texts_pass_through_and_regions_append():
    fused = fuse(
        regions=[((500, 500, 600, 560), 0.4)],
        texts=[((10, 10, 100, 30), "File", 0.9)],
    )
    assert kinds(fused) == [("text", "File"), ("icon", None)]
    assert fused[0].interactable is False
    assert fused[1].interactable is True
    assert fused[1].confidence == pytest.approx(0.4)


def test_larger_of_overlapping_region_pair_is_dropped():
    """'Keep the smaller box': the big near-duplicate goes, the small stays."""
    small = ((100, 100, 200, 150), 0.3)
    large = ((95, 95, 210, 160), 0.9)      # fully contains small -> hybrid overlap 1.0
    fused = fuse(regions=[large, small], texts=[])
    assert len(fused) == 1
    assert fused[0].bounds == small[0]
    assert fused[0].confidence == pytest.approx(0.3)


def test_ocr_inside_region_is_absorbed():
    """The tile case: caption text inside a button becomes the button's content
    (a literal read), and the standalone text box disappears."""
    fused = fuse(
        regions=[((100, 100, 300, 200), 0.8)],
        texts=[((150, 140, 250, 160), "Send Logfiles", 0.95)],
    )
    assert len(fused) == 1
    icon = fused[0]
    assert icon.kind == "icon"
    assert icon.content == "Send Logfiles"
    assert icon.source == "box_yolo_content_ocr"


def test_region_inside_ocr_is_dropped():
    """A tiny region proposal inside a big text line loses to the text."""
    fused = fuse(
        regions=[((120, 105, 140, 118), 0.5)],
        texts=[((100, 100, 400, 120), "a long line of text", 0.9)],
    )
    assert kinds(fused) == [("text", "a long line of text")]


def test_multiple_ocr_boxes_concatenate():
    fused = fuse(
        regions=[((100, 100, 300, 200), 0.8)],
        texts=[((110, 110, 160, 130), "Send", 0.9),
               ((170, 110, 260, 130), "Logfiles", 0.9)],
    )
    assert len(fused) == 1
    assert fused[0].content == "Send Logfiles"


def test_absorbed_text_still_labels_a_second_region():
    """
    Ported quirk: absorption checks run against the FULL OCR list, so a text
    absorbed by one region still contributes its label to a later region that
    also contains it - only the text box's removal happens once. The original
    achieves this via a swallowed ValueError; the port does it on purpose.
    """
    text = ((140, 140, 160, 150), "OK", 0.9)
    region_a = ((100, 100, 200, 200), 0.8)          # contains the text
    region_b = ((130, 130, 180, 180), 0.7)          # also contains it, low mutual overlap? -> ensure both survive
    # region_b is inside region_a -> hybrid overlap 1.0 would drop region_a
    # (the larger). Use side-by-side overlapping boxes instead:
    region_a = ((100, 100, 165, 200), 0.8)
    region_b = ((135, 100, 300, 200), 0.7)
    fused = fuse(regions=[region_a, region_b], texts=[text])
    icons = [f for f in fused if f.kind == "icon"]
    assert len(icons) == 2
    assert all(f.content == "OK" for f in icons)
    assert not any(f.kind == "text" for f in fused), "absorbed text box survived"


def test_no_texts_no_crash():
    fused = fuse(regions=[((0, 0, 10, 10), 0.5)], texts=[])
    assert kinds(fused) == [("icon", None)]


def test_empty_everything():
    assert fuse(regions=[], texts=[]) == []


# --------------------------------------------------------------------------
# backend orchestration with fake stages
# --------------------------------------------------------------------------

class FakeProposer(RegionProposer):
    name = "fake"

    def __init__(self, proposals):
        self._proposals = proposals

    def propose(self, image):
        return self._proposals


class FakeText:
    ocr_engine = "fake"

    def __init__(self, results):
        self._results = results

    def detect(self, image, **kwargs):
        return self._results


class FakeTextElement:
    def __init__(self, bounds, text, confidence):
        self.bounds, self.text, self.confidence = bounds, text, confidence


class EchoCaptioner(Captioner):
    name = "echo"

    def caption(self, image, boxes):
        return [f"icon at {b[0]},{b[1]}" for b in boxes]


@pytest.fixture
def image():
    return np.full((400, 600, 3), 255, dtype=np.uint8)


def make_backend(proposals, texts, captioner):
    return ModularDetectorBackend(
        region_proposer=FakeProposer(proposals),
        text_detector=FakeText(texts),
        captioner=captioner,
    )


def test_end_to_end_with_fakes(image):
    backend = make_backend(
        proposals=[RegionProposal((500, 300, 560, 350), 0.42)],
        texts=[FakeTextElement((10, 10, 100, 30), "File", 0.91)],
        captioner=EchoCaptioner(),
    )
    detections = backend.detect(image)

    assert len(detections) == 2
    text = next(d for d in detections if d.text == "File")
    icon = next(d for d in detections if d.label)

    # native confidences, straight from the stages - no 1.0 defaults
    assert text.confidence == pytest.approx(0.91)
    assert icon.confidence == pytest.approx(0.42)
    # text/label separation: OCR is literal text, a caption is a label
    assert text.label is None
    assert icon.text is None
    assert icon.label == "icon at 500,300"
    assert all(d.source == "modular" for d in detections)


def test_captioner_only_sees_unlabelled_icons(image):
    seen = []

    class SpyCaptioner(Captioner):
        name = "spy"

        def caption(self, _image, boxes):
            seen.extend(boxes)
            return [None] * len(boxes)

    backend = make_backend(
        # this region absorbs the text below -> already labelled -> not captioned
        proposals=[RegionProposal((100, 100, 300, 200), 0.8),
                   RegionProposal((400, 300, 460, 350), 0.5)],
        texts=[FakeTextElement((150, 140, 250, 160), "Send Logfiles", 0.95)],
        captioner=SpyCaptioner(),
    )
    detections = backend.detect(image)

    assert seen == [(400, 300, 460, 350)], "captioner saw the wrong boxes"
    absorbed = next(d for d in detections if d.text == "Send Logfiles")
    # absorbed OCR is a literal read on an interactable region
    assert absorbed.interactable is True
    assert absorbed.label is None


def test_none_captioner_leaves_icons_unlabelled(image):
    backend = make_backend(
        proposals=[RegionProposal((400, 300, 460, 350), 0.5)],
        texts=[],
        captioner=NoneCaptioner(),
    )
    detections = backend.detect(image)
    assert len(detections) == 1
    assert detections[0].text is None and detections[0].label is None


# --------------------------------------------------------------------------
# registry integration
# --------------------------------------------------------------------------

def test_registered_in_detector_registry():
    from visual_dom.adapters.outbound.detectors.registry import list_detectors

    names = {d["name"] for d in list_detectors()}
    assert "modular" in names
    # the isolation constraint: existing backends still registered untouched
    assert {"uied", "yolo", "omniparser", "grpc"} <= names


def test_stage_factories_reject_unknown_names():
    with pytest.raises(ValueError, match="region proposer"):
        create_region_proposer("nonesuch")
    with pytest.raises(ValueError, match="captioner"):
        create_captioner("nonesuch")


def test_none_captioner_via_factory():
    captioner = create_captioner("none")
    assert captioner.caption(None, [(0, 0, 1, 1)] * 3) == [None, None, None]


# --------------------------------------------------------------------------
# pipeline integration: modular elements are backend-thresholded
# --------------------------------------------------------------------------

def test_pipeline_confidence_gate_exempts_modular_source():
    """
    Modular-backend elements carry real per-stage scores (icon_detect logits
    can be 0.05-0.3). The pipeline's generic 0.3 gate must not re-filter them,
    exactly as it already exempts the omniparser monolith - otherwise the
    parity combo silently loses the faint controls the backend was configured
    to keep.
    """
    from visual_dom.core.domain.pipeline import UIElement, VisualDOMPipeline

    pipeline = VisualDOMPipeline(ocr_engine="easyocr", detector="uied",
                                 use_gpu=False)
    faint = UIElement(id="m", bounds=(10, 10, 60, 40), visual_type="button",
                      confidence=0.07, source="modular")
    kept = pipeline._filter_elements([faint])
    assert faint in kept

    # ...and ranking treats it as a detector-backend element (ties resolved as
    # if it were 1.0), not as a low-confidence heuristic box.
    assert pipeline._ranking_confidence(faint) == 1.0
