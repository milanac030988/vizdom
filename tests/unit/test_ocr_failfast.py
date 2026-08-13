"""
OCR failure must be loud, not silent.

Two layers (parked item #2 from the demo freeze, IMPROVEMENTS.md §3b):

* `Session._probe_ocr_engine` - refuses a configured-but-missing engine before
  anything heavy is built (ADR-020). Used by `connect()` and by the Viewer's
  analyze path.
* `VisualDOMPipeline.process` - when the engine exists but dies at runtime, the
  run degrades to 0 text (deliberately, so headless batches survive), and the
  failure is recorded in `stats["text_error"]` so a caller can tell a dead OCR
  engine from a genuinely text-free screen. Session 20260806_195229 is the
  motivating case: paddleocr configured but absent, 0 text boxes, no explanation.
"""

import numpy as np
import pytest

from visual_dom.context import Session
from visual_dom.core.domain.pipeline import VisualDOMPipeline


# --------------------------------------------------------------------------
# the pre-flight probe
# --------------------------------------------------------------------------

def test_probe_accepts_installed_engine():
    Session._probe_ocr_engine("easyocr")        # installed in this project


def test_probe_accepts_none():
    """Disabling text detection is a valid choice, not an error."""
    Session._probe_ocr_engine("none")
    Session._probe_ocr_engine(None)
    Session._probe_ocr_engine("")


def test_probe_rejects_missing_engine(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(ValueError, match="not installed"):
        Session._probe_ocr_engine("easyocr")


def test_probe_names_the_package(monkeypatch):
    """The message must be actionable: name the missing package."""
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(ValueError, match="paddleocr"):
        Session._probe_ocr_engine("paddleocr")


# --------------------------------------------------------------------------
# the runtime failure record
# --------------------------------------------------------------------------

@pytest.fixture
def pipeline():
    # uied needs no model files; ocr_engine won't actually run (we patch it).
    return VisualDOMPipeline(ocr_engine="easyocr", detector="uied", use_gpu=False)


def _image():
    """A tiny synthetic UI: one dark rectangle on white, enough for UIED."""
    img = np.full((120, 200, 3), 255, dtype=np.uint8)
    img[30:70, 40:160] = (40, 40, 40)
    return img


def test_ocr_death_is_recorded_in_stats(pipeline):
    def boom(image, **kwargs):
        raise RuntimeError("engine exploded mid-run")

    pipeline.text_detector.detect = boom
    result = pipeline.process(_image())

    assert result["stats"]["text_detected"] == 0
    assert "engine exploded mid-run" in result["stats"]["text_error"]
    # the run still degrades gracefully: detection output survives
    assert "elements" in result


def test_healthy_run_has_no_error_key(pipeline):
    pipeline.text_detector.detect = lambda image, **kwargs: []
    result = pipeline.process(_image())

    assert result["stats"]["text_detected"] == 0
    assert "text_error" not in result["stats"], \
        "0 text with no failure is a text-free screen, not an error"
