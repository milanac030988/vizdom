"""
Real key crops of the Windows Calculator at 640 px (RobotFramework AIO demo,
2026-10-29), kept as regression fixtures for the glyph readers:

- the symbol reader must read every operator key, in particular the minus
  key, whose thin bar an adaptive binarization turns into a halo blob that
  used to pass as "." and outrank the true "-";
- the lone "7" and "1" are not symbols (the recogniser reads them, see
  test_ocr_captioner.py), and the maximize icon is a hollow frame the
  recogniser must never be asked about.
"""
from pathlib import Path

import cv2
import pytest

from visual_dom.adapters.outbound.ocr.text_detector import TextDetector
from visual_dom.core.domain.cvops.symbol_detector import detect_symbol

KEYS = Path(__file__).resolve().parents[1] / "fixtures" / "calculator_keys"


def _crop(name):
    img = cv2.imread(str(KEYS / f"{name}.png"))
    assert img is not None, f"fixture {name}.png missing"
    return img


@pytest.mark.parametrize("name, symbol", [
    ("minus", "-"), ("decimal", "."), ("plus", "+"), ("equals", "="),
    ("divide", "÷"), ("multiply", "×"), ("plus_minus", "±"),
])
def test_operator_keys_read_as_their_symbol(name, symbol):
    img = _crop(name)
    assert detect_symbol(img, (0, 0, img.shape[1], img.shape[0])) == symbol


@pytest.mark.parametrize("name", ["seven", "one", "maximize_icon"])
def test_digits_and_the_maximize_icon_are_not_symbols(name):
    img = _crop(name)
    assert detect_symbol(img, (0, 0, img.shape[1], img.shape[0])) is None


def test_digit_glyphs_tighten_and_the_maximize_icon_is_a_hollow_frame():
    for name in ("seven", "one"):
        patch = TextDetector.tighten_glyph(_crop(name))
        assert patch is not None and not TextDetector.is_hollow_frame(patch), name
    patch = TextDetector.tighten_glyph(_crop("maximize_icon"))
    assert patch is not None and TextDetector.is_hollow_frame(patch)
