# ADR-009: SLM Advisor with VLM Support for CV Review

## Status

Accepted

## Date

2026-03-30

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-03-30 | 1.0 | Initial version |

## Context

The CV pipeline (ADR-002) sometimes produces incorrect results that pure rule-based logic cannot fix:

- **Merged elements**: Adjacent buttons (e.g., "+" and "-") detected as one element
- **Mistyped elements**: `unknown` type for elements that are clearly buttons (e.g., "MC", "MR")
- **Split text**: OCR reading two adjacent button labels as one combined string

The LLM hierarchy refiner (ADR-007) operates after the pipeline, too late to fix CV-level merge/split errors. A review step was needed between CV detection and hierarchy building.

## Decision

### 1. SLM Advisor Module

Created `src/visual_dom/cv/slm_advisor.py` — a lightweight review layer that:

- Receives detected elements from the CV pipeline
- Sends only **suspicious elements** to the LLM (text with spaces, mixed chars, wrong types)
- Parses JSON suggestions: `split` (create child elements) and `retype` (change visual_type)
- Integrated as optional Step 8 in the pipeline

### 2. VLM (Vision Language Model) Support

Extended the advisor to support vision models that can see the actual screenshot:

- Auto-detects vision models (`minicpm-v`, `llava`, `qwen2.5-vl`) from model name
- Encodes screenshot as base64 for Ollama vision API (`images` field)
- OpenAI-compatible vision API support (image_url content type)
- Vision prompt asks VLM to compare elements against what it sees

### 3. Viewer Integration

- **SLM checkbox** in toolbar to enable/disable
- **Model dropdown** with options: `qwen2.5:3b` (text), `minicpm-v` (VLM), `qwen2.5-vl:3b` (VLM), `llava:7b` (VLM)
- **OCR engine dropdown**: `easyocr`, `tesseract`, `paddleocr`

### 4. Backends

- **Ollama** (primary): Local inference, supports both text and vision models
- **OpenAI** (secondary): Cloud API, supports GPT-4o vision

## Alternatives Considered

- **Text-only SLM without VLM**: Implemented first, but 3B text models returned empty suggestions — they couldn't reason about merged elements from text descriptions alone
- **Running SLM before CV**: Rejected — SLM needs CV results to review, not raw images
- **Fine-tuning SLM**: Deferred — prompt engineering with VLM is faster to iterate

## Consequences

### Positive
- Optional step — zero performance impact when disabled
- VLM can detect issues invisible to text-only models (merged buttons, misclassification)
- Model warmup prevents timeout on first request
- Suspicious-element filtering keeps prompt short for small models

### Negative
- Requires Ollama running with a pulled model
- VLM models need 3-8GB VRAM
- Response quality varies by model — 3B models are often too conservative
- First-call latency ~20-30s for model loading

## Files Changed

- `src/visual_dom/cv/slm_advisor.py` — New: SLM/VLM advisor module
- `src/visual_dom/cv/pipeline.py` — Added `slm_backend`/`slm_model` params, `_slm_review()`, `_apply_slm_split()`
- `src/visual_dom/cv/__init__.py` — Export `SLMAdvisor`
- `tools/visual_dom_viewer/ui/main_window.py` — SLM checkbox, model dropdown, OCR dropdown
- `scripts/process_gui_image.py` — Added `--slm`, `--slm-model` arguments
