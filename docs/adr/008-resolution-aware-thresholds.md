# ADR-008: Resolution-Aware Thresholds and Color Features

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

The CV pipeline (ADR-002) used hardcoded pixel thresholds for element classification in `uied_detection.py` (e.g., checkbox: 15-30px, input max height: 60px, button max area: 50000px). These values were tuned for 1080p screenshots but failed on different resolutions:

- **Low-res images** (400-800px): Thresholds were too large, missing real elements
- **High-res images** (2K/4K): Thresholds were too small, detecting noise

Additionally, element classification relied solely on grayscale features (edge density, intensity std), missing important color-based cues like button background contrast and border detection.

## Decision

### 1. Resolution-Aware Scaling

Introduce a reference resolution (1080p) and compute a scale factor for all pixel thresholds:

```python
scale = max(1.0, image_height / 1080)
```

- `_scaled(px)` — scales linear dimensions (width, height)
- `_scaled_area(px²)` — scales area thresholds (quadratic)
- Clamped to `min 1.0` so small images keep original thresholds (prevents over-shrinking)

Applied to both `UIEDDetector` and `VisualDOMPipeline`.

### 2. Color Feature Extraction

Added `ColorFeatures` dataclass and `extract_color_features()` in `image_processing.py`:

- `bg_contrast` — contrast against surrounding background
- `is_uniform` — low color variation (button-like solid fill)
- `has_border` — distinct border detected (input fields)
- `saturation_mean` — vivid vs gray
- `distinct_colors` — number of color clusters

Color features are computed **lazily** — only when grayscale features are ambiguous (medium-sized rectangles), to avoid performance overhead.

## Consequences

### Positive
- Pipeline works correctly across 400px to 4K screenshots without parameter tuning
- Better button detection via color contrast (uniform + high bg_contrast)
- Better input field detection via border presence
- Minimal performance impact (color only computed on ambiguous cases)

### Negative
- Scale clamping at 1.0 means small images don't benefit from downscaled thresholds
- Color extraction adds ~1ms per ambiguous element

## Files Changed

- `src/visual_dom/cv/uied_detection.py` — Added `_scale`, `_scaled()`, `_scaled_area()`, updated `_classify_element`, `_detect_rectangles`, `_detect_blocks`, `_detect_elements_in_blocks`
- `src/visual_dom/cv/pipeline.py` — Added scaling in `VisualDOMPipeline`, updated `_filter_elements`, `_merge_text_and_elements`
- `src/visual_dom/cv/image_processing.py` — Added `ColorFeatures`, `extract_color_features()`
