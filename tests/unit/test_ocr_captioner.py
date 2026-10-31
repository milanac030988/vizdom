"""
The reading captioner (modular stage 3, "ocr"): a lone "7" or "1" on a key that
the whole-screen text detector never localises is read by the recogniser on
the tightened glyph, and recorded as literal text, not as a caption.
"""
import cv2
import numpy as np
import pytest

from visual_dom.adapters.outbound.detectors.modular_backend import (
    ModularDetectorBackend, NoneCaptioner, OcrCaptioner, RegionProposal, RegionProposer,
    create_captioner,
)
from visual_dom.adapters.outbound.ocr.text_detector import TextDetector


def _key(glyph="7", size=(110, 110), dark=True):
    """A calculator key: a rounded dark tile with one white glyph."""
    bg, fg = ((40, 40, 40), (240, 240, 240)) if dark else ((235, 235, 235), (30, 30, 30))
    img = np.full((size[1], size[0], 3), bg, dtype=np.uint8)
    cv2.rectangle(img, (0, 0), (size[0] - 1, size[1] - 1), (90, 90, 90), 2)   # the key's edge
    (tw, th), _ = cv2.getTextSize(glyph, cv2.FONT_HERSHEY_SIMPLEX, 1.6, 3)
    cv2.putText(img, glyph, ((size[0] - tw) // 2, (size[1] + th) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.6, fg, 3, cv2.LINE_AA)
    return img


def test_tighten_glyph_cuts_the_glyph_out_of_the_key_as_dark_on_light():
    patch = TextDetector.tighten_glyph(_key("7"))
    assert patch is not None and patch.ndim == 2
    assert patch.shape[0] == 64 + 32                     # 64 px glyph + 16 px borders
    assert patch.shape[1] < patch.shape[0] * 2           # a digit, not the whole key
    assert np.median(patch) > 128, "the recogniser wants dark ink on a light ground"
    assert (patch < 128).sum() > 50, "the glyph's ink survived"
    # the same for a light theme
    assert TextDetector.tighten_glyph(_key("1", dark=False)) is not None


def test_tighten_glyph_returns_none_for_a_blank_key_and_an_empty_crop():
    blank = np.full((80, 80, 3), 40, dtype=np.uint8)
    assert TextDetector.tighten_glyph(blank) is None
    assert TextDetector.tighten_glyph(np.zeros((0, 0, 3), dtype=np.uint8)) is None


class _Recognizer:
    """A fake text detector: reads what the test says per call."""

    ocr_engine = "easyocr"

    def __init__(self, reads):
        self.reads = list(reads)
        self.crops = []

    def recognize_crop(self, crop, min_confidence=0.6):
        self.crops.append(crop.shape)
        read = self.reads.pop(0)
        return read if read and read[1] >= min_confidence else None

    def detect(self, image):
        return []


def test_ocr_captioner_reads_each_box_and_drops_low_confidence_and_long_reads():
    fake = _Recognizer([("7", 1.0), ("1", 0.95), ("B", 0.3), ("Calculator", 0.9), None])
    cap = OcrCaptioner(text_detector=fake)
    image = np.zeros((300, 300, 3), dtype=np.uint8)
    out = cap.caption(image, [(0, 0, 50, 50), (60, 0, 110, 50), (0, 60, 50, 110),
                              (60, 60, 110, 110), (120, 120, 170, 170)])
    assert out == ["7", "1", None, None, None]
    assert cap.literal is True and cap.name == "ocr"
    assert len(fake.crops) == 5


class _Regions(RegionProposer):
    name = "fake"

    def __init__(self, boxes):
        self.boxes = boxes

    def propose(self, image):
        return [RegionProposal(bounds=b, confidence=0.9) for b in self.boxes]


def test_backend_records_a_reading_captioner_as_text_and_a_predicting_one_as_label():
    img = np.zeros((100, 300, 3), dtype=np.uint8)
    boxes = [(0, 0, 100, 100), (150, 0, 250, 100)]

    reading = OcrCaptioner(text_detector=_Recognizer([("7", 1.0), None]))
    out = ModularDetectorBackend(region_proposer=_Regions(boxes), captioner=reading,
                                 text_detector=_Recognizer([])).detect(img)
    assert [(d.text, d.label) for d in out] == [("7", None), (None, None)]

    class _Guess(NoneCaptioner):
        name = "guess"

        def caption(self, image, boxes):
            return ["seven"] * len(boxes)

    out = ModularDetectorBackend(region_proposer=_Regions(boxes), captioner=_Guess(),
                                 text_detector=_Recognizer([])).detect(img)
    assert [(d.text, d.label) for d in out] == [(None, "seven"), (None, "seven")]


def test_ocr_captioner_by_name_shares_the_backend_text_detector():
    fake = _Recognizer([("1", 1.0)])
    backend = ModularDetectorBackend(region_proposer=_Regions([(0, 0, 50, 50)]),
                                     captioner="ocr", text_detector=fake)
    assert isinstance(backend._captioner, OcrCaptioner)
    assert backend._captioner._text is fake, "one recogniser, not a second engine"
    assert isinstance(create_captioner("ocr", text_detector=fake), OcrCaptioner)


def test_recognize_crop_is_easyocr_only():
    td = TextDetector(ocr_engine="tesseract", gpu=False)
    assert td.recognize_crop(_key("7")) is None


def test_hollow_frame_is_rejected_but_an_oval_zero_is_not():
    frame = np.full((110, 110, 3), 40, dtype=np.uint8)
    cv2.rectangle(frame, (30, 30), (80, 80), (240, 240, 240), 4)          # a maximize square
    patch = TextDetector.tighten_glyph(frame)
    assert patch is not None and TextDetector.is_hollow_frame(patch)
    zero = np.full((110, 110, 3), 40, dtype=np.uint8)
    cv2.ellipse(zero, (55, 55), (18, 30), 0, 0, 360, (240, 240, 240), 5)   # a "0"
    patch = TextDetector.tighten_glyph(zero)
    assert patch is not None and not TextDetector.is_hollow_frame(patch)
    assert not TextDetector.is_hollow_frame(TextDetector.tighten_glyph(_key("7")))


def test_recognize_crop_skips_a_hollow_frame_before_calling_the_engine():
    td = TextDetector(ocr_engine="easyocr", gpu=False)
    calls = []
    td._engine = type("E", (), {"recognize": lambda self, *a, **k: calls.append(1) or [([], "0", 0.95)]})()
    frame = np.full((110, 110, 3), 40, dtype=np.uint8)
    cv2.rectangle(frame, (30, 30), (80, 80), (240, 240, 240), 4)
    assert td.recognize_crop(frame) is None and calls == []
    assert td.recognize_crop(_key("7")) == ("0", 0.95) and calls == [1]


def test_ocr_captioner_lets_the_symbol_reader_answer_first(monkeypatch):
    from visual_dom.adapters.outbound.detectors import modular_backend as mb
    import visual_dom.core.domain.cvops.symbol_detector as sd
    monkeypatch.setattr(sd, "detect_symbol",
                        lambda image, bbox, min_score=None: "±" if bbox[0] == 0 else None)
    fake = _Recognizer([("7", 1.0)])
    out = OcrCaptioner(text_detector=fake).caption(np.zeros((100, 300, 3), dtype=np.uint8),
                                                   [(0, 0, 50, 50), (60, 0, 110, 50)])
    assert out == ["±", "7"], "the structural read wins; the recogniser sees only the rest"
    assert len(fake.crops) == 1


def test_ocr_captioner_keeps_only_reads_with_a_letter_or_digit(monkeypatch):
    """A hamburger icon the symbol reader vetoed came back as "=" from the
    recogniser and made the equals key ambiguous: symbol-only reads are the
    symbol reader's call, the recogniser adds letters and digits."""
    import visual_dom.core.domain.cvops.symbol_detector as sd
    monkeypatch.setattr(sd, "detect_symbol", lambda image, bbox, min_score=None: None)
    fake = _Recognizer([("=", 0.98), ("x2", 0.9), ("--", 0.9), ("C", 0.87)])
    out = OcrCaptioner(text_detector=fake).caption(
        np.zeros((100, 400, 3), dtype=np.uint8),
        [(0, 0, 50, 50), (60, 0, 110, 50), (120, 0, 170, 50), (180, 0, 230, 50)])
    assert out == [None, "x2", None, "C"]
