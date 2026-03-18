# ADR-001: Visual DOM System Architecture

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

Traditional UI automation relies on platform-specific accessibility APIs (UIAutomator for Android, WinAPI for Windows, etc.) to extract DOM information. However, these approaches have limitations:

- **Platform dependency**: Each platform requires different tooling
- **Accessibility limitations**: Not all UI elements expose accessibility properties
- **Cross-platform inconsistency**: Same app on different platforms yields different DOM structures
- **Legacy app support**: Older applications may lack proper accessibility implementation

We needed a universal approach that could:
1. Work across any platform (Windows, Android, Linux, Web)
2. Handle applications without accessibility support
3. Produce consistent, automation-friendly output
4. Support Robot Framework integration

## Decision

Implement a **Visual DOM Generator** that uses Computer Vision (CV) and OCR to analyze screenshots and produce UIAutomator-like DOM JSON, independent of platform accessibility APIs.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Visual DOM System                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Platform   │  │   CV/OCR     │  │   Output     │      │
│  │   Handlers   │  │   Pipeline   │  │   Layer      │      │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤      │
│  │ • Windows    │  │ • EasyOCR    │  │ • DOM JSON   │      │
│  │ • Android    │  │ • UIED       │  │ • Locators   │      │
│  │ • Linux      │  │ • Hierarchy  │  │ • Robot FW   │      │
│  │ • Web        │  │   Builder    │  │   Library    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│                    Tools & Utilities                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Viewer     │  │  Evaluation  │  │   Research   │      │
│  │   (PyQt5)    │  │  Framework   │  │   Scripts    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

1. **CV Pipeline** (`src/visual_dom/cv/`)
   - Text detection using EasyOCR/PaddleOCR
   - UI element detection using UIED-style algorithms
   - Element merging and deduplication

2. **Hierarchy Builder** (`src/visual_dom/hierarchy/`)
   - Containment-based parent-child relationships
   - Alignment grouping (rows, columns)
   - Label association for form elements

3. **DOM Compiler** (`src/visual_dom/compiler/`)
   - Generates UIAutomator-compatible JSON
   - Creates multiple locator strategies
   - Adds semantic roles and interaction flags

4. **Platform Handlers** (`tools/visual_dom_viewer/plugins/`)
   - Pluggable architecture for different platforms
   - Window enumeration and capture
   - Target application management

5. **Evaluation Framework** (`src/visual_dom/evaluation/`)
   - Element detection metrics (Precision, Recall, F1, IoU)
   - OCR accuracy metrics (CER, WER)
   - Hierarchy structure metrics
   - Locator quality metrics

## Consequences

### Positive

- **Platform agnostic**: Works with any application that can be screenshotted
- **No accessibility dependency**: Detects elements visually
- **Consistent output**: Same JSON format regardless of source platform
- **Extensible**: Easy to add new platforms, detection models, or output formats
- **Testable**: Comprehensive evaluation framework for quality measurement

### Negative

- **Performance overhead**: CV processing is slower than native APIs
- **GPU recommended**: Best performance requires CUDA-capable GPU
- **Accuracy limitations**: CV detection may miss some elements or produce false positives
- **No semantic information**: Cannot determine element functionality without visual cues

### Neutral

- Requires ground truth annotations for evaluation
- Model downloads required on first run (~100-200MB for OCR models)
- Output quality depends on screenshot quality and resolution

## Alternatives Considered

### 1. Pure LLM Approach (Rejected)

Use large language models (GPT-4V, Claude) directly for element detection.

Rejected because:
- High API costs for frequent automation tasks
- Latency too high for real-time automation
- Inconsistent bbox coordinate formats
- Privacy concerns with sending screenshots to external APIs

### 2. Native Accessibility APIs Only (Rejected)

Use only platform-specific accessibility APIs (UIAutomator, AT-SPI, etc.).

Rejected because:
- Not all applications expose accessibility information
- Requires different implementations per platform
- Legacy applications often lack proper accessibility support
- Cannot work with custom UI frameworks

### 3. Hybrid CV + Accessibility (Deferred)

Combine CV detection with native accessibility APIs when available.

Deferred because:
- Increases complexity significantly
- CV-only approach sufficient for initial implementation
- Can be added later as enhancement

## References

- UIED Paper: "Object Detection for Graphical User Interface"
- EasyOCR: https://github.com/JaidedAI/EasyOCR
- UIAutomator JSON format reference
- Source: `src/visual_dom/cv/pipeline.py`
- Source: `src/visual_dom/compiler/dom_compiler.py`
