# ADR-011: Symbol Detector for UI Elements

## Status

Accepted (with limitations)

## Date

2026-03-30

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-03-30 | 1.0 | Initial version |

## Context

OCR engines (EasyOCR, Tesseract) frequently fail to detect small single-character UI symbols like `+`, `-`, `=`, `×`, `÷` in button elements. These symbols are:

- Too small for reliable OCR (12-20px)
- Often rendered as thin strokes that OCR interprets as noise
- Critical for calculator-type UIs and toolbar buttons

After CV detection, many button-sized elements had correct bounding boxes but no OCR text.

## Decision

Created `src/visual_dom/cv/symbol_detector.py` using projection-based pattern matching:

### Detection Strategy

1. **Multi-strategy binarization**: Try Otsu (both polarities) and adaptive threshold, pick the candidate with density closest to 0.10 (typical for a clean symbol stroke)
2. **Center cropping**: Analyze inner 60% of region to ignore borders/shadows
3. **Projection analysis**: Compute horizontal and vertical projections (row/column sums)
4. **Pattern matching**:
   - `+` → horizontal peak AND vertical peak (crossing strokes)
   - `-` → horizontal peak only, centered vertically
   - `=` → two horizontal stroke segments, no vertical peak
   - `×` → diagonal stroke detection (no clear h/v peaks)
   - `÷` → horizontal peak with dot clusters above and below
   - `.` → small cluster near bottom of region

### Pipeline Integration

- Runs as Step 4c, after text-position split
- Only processes textless elements in button-sized range: `scaled(200) < area < scaled(40000)`
- Assigns detected symbol as `ocr_text`

## Alternatives Considered

- **Template matching**: Rejected — requires maintaining templates for each size/font/theme
- **CNN classifier**: Considered for future — would need training data
- **VLM-based**: Tested with minicpm-v, but VLM responses were too slow and unreliable for per-element detection

## Consequences

### Positive
- Detects `+`, `-`, `=`, `×`, `.` on synthetic images at 36-77px sizes
- Works for both light and dark themes via multi-strategy binarization
- Zero external dependencies (pure OpenCV + numpy)
- Fast (~1ms per element)

### Negative
- Limited accuracy on real-world UIs with gradient backgrounds and anti-aliased strokes (Windows Calculator: 5/15 symbols detected)
- Projection-based approach struggles with custom icon fonts
- Not a replacement for proper OCR — works best as a fallback

### Known Limitations

- Cannot distinguish similar shapes (e.g., `x` letter vs `×` multiply) when the
  glyph is genuinely ambiguous in isolation

## Revisions

The original projection-rule design was replaced twice (see
`IMPROVEMENTS.md` §3 for the full account):

1. **v2 — template matching** (Dice against font-rendered templates on the
   tight, scale-normalised glyph), which fixed the theme-dependence above;
2. **v3 — structure first** (2026-08-07): connected-component structural
   classification (`÷` = bar + dot above + dot below, `=` = two stacked bars,
   `+` = centred cross with empty corners, ...) with templates demoted to
   supporting evidence, candidate binarizations ranked by *specificity* (the
   reading that explains more components wins), and rejection when no structure
   fits — which is what stops word keys, icons, and digits from being misread as
   operators. Verified 130/130 on a four-rendering labelled set
   (`tests/unit/test_symbol_detector.py`, data in `tests/samples/symbols/`).

## Files Changed

- `src/visual_dom/core/domain/cvops/symbol_detector.py` — symbol detection module
- `src/visual_dom/core/domain/pipeline.py` — `_detect_symbols()` as Step 4c
- `tests/unit/test_symbol_detector.py` + `tests/samples/symbols/` — labelled
  regression set (four real renderings, 130 cases)
