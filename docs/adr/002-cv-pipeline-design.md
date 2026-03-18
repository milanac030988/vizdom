# ADR-002: CV Pipeline Design - EasyOCR + UIED Detection

## Status

Accepted

## Date

2025-01-26

## Author

Development Team

## Reviewer

- Project Lead

## History

| Date | Version | Description |
|------|---------|-------------|
| 2025-01-26 | 1.0 | Initial version |

## Context

The Visual DOM system needs to detect UI elements from screenshots. This requires:

1. **Text Detection**: Find and recognize text in the UI (buttons labels, input values, etc.)
2. **Non-Text Element Detection**: Find icons, checkboxes, input fields, containers
3. **Element Classification**: Determine element types (button, input, checkbox, etc.)

Key requirements:
- Must work offline (no cloud API dependencies)
- Should support GPU acceleration for performance
- Need reasonable accuracy without extensive training
- Must handle various UI styles and resolutions

## Decision

Implement a two-stage CV pipeline combining:

1. **EasyOCR** for text detection and recognition
2. **UIED-style detection** for non-text UI elements

### Pipeline Architecture

```
Screenshot Input
       │
       ▼
┌──────────────────────────────────────────┐
│            Stage 1: Detection            │
├────────────────────┬─────────────────────┤
│   Text Detector    │  UIED Detector      │
│   (EasyOCR)        │  (OpenCV-based)     │
├────────────────────┴─────────────────────┤
│     • OCR text      │  • Edge detection  │
│     • Bounding box  │  • Contour finding │
│     • Confidence    │  • Color analysis  │
│     • Language      │  • Shape classify  │
└────────────────────┴─────────────────────┘
       │                      │
       ▼                      ▼
┌──────────────────────────────────────────┐
│         Stage 2: Merge & Filter          │
├──────────────────────────────────────────┤
│  • Non-Maximum Suppression (NMS)         │
│  • Containment filtering                 │
│  • Text-to-element association           │
│  • Confidence thresholding               │
└──────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│       Stage 3: Hierarchy Building        │
├──────────────────────────────────────────┤
│  • Containment-based parenting           │
│  • Spatial grouping (rows/columns)       │
│  • Label association                     │
└──────────────────────────────────────────┘
       │
       ▼
    Elements with hierarchy
```

### Text Detection (EasyOCR)

```python
from visual_dom.cv.text_detector import TextDetector

detector = TextDetector(
    ocr_engine="easyocr",  # or "paddleocr", "tesseract"
    languages=["en"],
    confidence_threshold=0.3,
    gpu=True
)

text_elements = detector.detect(image)
# Returns: [TextElement(text, bbox, confidence), ...]
```

### UIED Detection

Uses UIED (UI Element Detection) algorithm:
1. **Coarse detection**: Find large blocks via edge detection
2. **Fine detection**: Detect small elements within blocks
3. **Classification**: Classify by shape, color, aspect ratio

```python
from visual_dom.cv.uied_detection import UIEDDetector

detector = UIEDDetector(
    min_element_area=100,
    nms_threshold=0.5
)

elements = detector.detect(image)
# Returns: [DetectedElement(bbox, type, confidence), ...]
```

### Element Types Detected

| Type | Detection Method | Visual Cues |
|------|------------------|-------------|
| `button` | UIED + shape | Rounded corners, solid fill |
| `text` | OCR | Text content |
| `input_field` | UIED + shape | Rectangular, border |
| `checkbox` | UIED + shape | Small square |
| `icon` | UIED + color | Small, often colorful |
| `container` | UIED + size | Large rectangular areas |
| `divider` | UIED + shape | Thin lines |

## Consequences

### Positive

- **Offline operation**: No cloud dependencies
- **GPU acceleration**: Fast processing with CUDA
- **Multi-language support**: EasyOCR supports 80+ languages
- **No training required**: Works out-of-box with pre-trained models
- **Flexible engines**: Can swap OCR engines (EasyOCR, PaddleOCR, Tesseract)

### Negative

- **Model download**: First run downloads ~100-200MB models
- **Memory usage**: GPU memory required for best performance (~2-5GB)
- **Accuracy trade-offs**: May miss subtle UI elements
- **Processing time**: 10-30 seconds per image depending on complexity

### Neutral

- Results vary based on screenshot quality
- Different OCR engines have different strengths
- Element classification accuracy varies by UI style

## Alternatives Considered

### 1. Deep Learning Object Detection (YOLO, Faster R-CNN) (Deferred)

Train a custom object detection model on UI element datasets.

Deferred because:
- Requires large annotated dataset
- Training infrastructure needed
- UIED approach works well for initial implementation
- Can add trained models later as enhancement

### 2. Cloud OCR APIs (Google Vision, AWS Textract) (Rejected)

Use cloud-based OCR services.

Rejected because:
- Adds external dependency
- Per-request costs
- Privacy concerns (sending screenshots to cloud)
- Latency for automation use cases

### 3. Tesseract Only (Rejected)

Use only Tesseract OCR without deep learning.

Rejected because:
- Lower accuracy than EasyOCR
- Worse performance on complex UIs
- No built-in text detection (requires preprocessing)

## References

- EasyOCR: https://github.com/JaidedAI/EasyOCR
- UIED Paper: "Object Detection for Graphical User Interface"
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
- Source: `src/visual_dom/cv/pipeline.py`
- Source: `src/visual_dom/cv/text_detector.py`
- Source: `src/visual_dom/cv/uied_detection.py`
