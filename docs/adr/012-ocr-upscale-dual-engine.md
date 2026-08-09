# ADR-012: OCR Upscaling and Dual-Engine Strategy

## Status

Accepted

## Date

2026-03-30

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-03-30 | 1.0 | Initial version |

## Context

Testing with the CMST application (Bosch IT Workplace Toolkit, WPF/.NET) revealed two OCR accuracy issues:

1. **Small text misread**: 12-14px text labels ("IP Address", "MAC Address") were garbled by EasyOCR (e.g., `~ddress`, `Mas; Storaze`, `Untruszed`)
2. **Low-contrast text invisible**: Gray text on white background (e.g., "APAC\UGC1HC", "HC-C-004CE") detected with confidence <0.15, filtered out

Root cause analysis:
- EasyOCR's CRNN model was trained on larger text; small text at 12px produces unreliable features
- The Bosch Sans Regular custom font is not in EasyOCR's training distribution
- Gray-on-white contrast ratio is too low for reliable detection

Testing showed Tesseract reads the same regions much more accurately (e.g., "HC-C-004CE" at conf=75) but has weaker text region detection (misses regions that EasyOCR finds).

## Decision

### 1. Image Upscaling Before OCR

In `TextDetector.detect()`:

- Images with height below `UPSCALE_THRESHOLD` (1500px) are auto-upscaled
- Scale factor: `min(1500/height, 3.0)` — capped at 3x to limit memory
- Uses `cv2.INTER_CUBIC` for quality upscaling
- Bounding boxes scaled back to original coordinates after detection
- Configurable via `upscale=True/False` parameter

For the CMST screenshot (562px), 12px text becomes ~32px after 2.7x upscale — significantly easier for OCR.

### 2. CLAHE Contrast Enhancement

New `_enhance_for_ocr()` method:

- Converts to LAB color space
- Applies CLAHE (Contrast Limited Adaptive Histogram Equalization) to luminance channel
- Improves visibility of gray text on white backgrounds without distorting colors

### 3. Dual-Engine OCR (EasyOCR + Tesseract Fallback)

New `_retry_low_confidence_with_tesseract()` method:

- After EasyOCR detection, identifies results with confidence < 0.5
- For each low-confidence region, runs Tesseract in single-line mode (`--psm 7`)
- If Tesseract returns valid text, replaces EasyOCR's garbled result
- Boosts confidence to 0.3 so the result survives the filter

This combines EasyOCR's strength (text region detection) with Tesseract's strength (font recognition accuracy).

### 4. Lowered Confidence Threshold

Default TextDetector confidence threshold lowered: 0.5 → 0.2

- Allows low-confidence but correct detections to pass through
- Tesseract fallback can rescue these with better text
- Pipeline's later NMS and dedup stages handle any noise

### 5. OCR Engine Selector in Viewer

Added OCR dropdown in viewer toolbar:
- `easyocr` (default) — best text region detection
- `tesseract` — better for system/custom fonts
- `paddleocr` — fast, multi-language

## Alternatives Considered

- **Tesseract as primary engine**: Tested, but misses too many text regions compared to EasyOCR
- **PaddleOCR**: Not tested extensively yet, could be a good middle ground
- **Fine-tuning EasyOCR on Bosch Sans**: Possible but requires significant training effort
- **Fine-tuning Tesseract on Bosch Sans**: Feasible via `tesstrain`, deferred for now

## Consequences

### Positive
- CMST app: 25/46 → improved text detection on form labels
- Garbled text reduced: EasyOCR misreads retried by Tesseract
- Works without any model training — pure preprocessing + dual engine
- Upscaling is automatic and transparent

### Negative
- Upscaling increases OCR processing time (~2-3x slower due to larger image)
- Tesseract fallback adds ~50-100ms per low-confidence region
- CLAHE may slightly alter colors (applied before OCR only, not before UIED)
- Requires Tesseract installed for fallback to work

## Files Changed

- `src/visual_dom/cv/text_detector.py` — Added `upscale` param, `UPSCALE_THRESHOLD`, `_enhance_for_ocr()`, `_retry_low_confidence_with_tesseract()`, lowered default confidence
- `tools/visual_dom_viewer/ui/main_window.py` — Added OCR engine dropdown
