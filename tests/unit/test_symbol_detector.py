"""
Data-driven regression test for the symbol detector (ADR-011).

The manifest under tests/samples/symbols/ holds four real Windows 11 Calculator
renderings (Scientific + Standard, 100% and 125% display scaling) with every key
cell labelled: the operator keys with their expected glyph, and everything else
(digits, word keys like "mod"/"exp", icon keys like the backspace, the maximize
square) with expect=null — meaning detect_symbol MUST return None for them.

The rejection cases are the point. Historically the detector's failures were not
misses but confident misreads (a backspace icon as "=", "mod" as "-"), which
poison element text and make locators ambiguous. Any change to the detector has
to keep this at 100%: a new theme that fails belongs IN the manifest, with the
fix measured against all renderings at once.

To extend: capture a window (`CaptureStrategy.capture_window`), add the labelled
cells to manifest.json, and re-run.
"""

import json
from pathlib import Path

import cv2
import pytest

from visual_dom.core.domain.cvops.symbol_detector import detect_symbol

_SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "symbols"


def _load_cases():
    manifest = json.loads((_SAMPLES / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest:
        image_path = Path(entry["image"])
        if not image_path.is_absolute():
            # manifest paths are repo-relative; resolve against the samples dir
            image_path = _SAMPLES / image_path.name
        for case in entry["cases"]:
            yield image_path, case


_CASES = list(_load_cases())


@pytest.fixture(scope="module")
def images():
    cache = {}
    for path, _ in _CASES:
        if path not in cache:
            img = cv2.imread(str(path))
            assert img is not None, f"missing sample image: {path}"
            cache[path] = img
    return cache


@pytest.mark.parametrize(
    "image_path,case",
    _CASES,
    ids=[f"{p.stem}-{c['key']}" for p, c in _CASES],
)
def test_symbol_detection(images, image_path, case):
    got = detect_symbol(images[image_path], tuple(case["bbox"]))
    assert got == case["expect"], (
        f"{image_path.name} / {case['key']}: expected {case['expect']!r}, "
        f"got {got!r} (bbox={case['bbox']})")
