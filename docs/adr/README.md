# Architecture Decision Records (ADR)

This directory contains Architecture Decision Records for the Visual DOM project.

## What is an ADR?

An Architecture Decision Record (ADR) captures an important architectural decision made along with its context and consequences. ADRs help:

- Document why decisions were made
- Onboard new team members
- Avoid repeating past discussions
- Track evolution of the architecture

## ADR Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](001-visual-dom-architecture.md) | Visual DOM System Architecture | Accepted | 2025-01-26 |
| [002](002-cv-pipeline-design.md) | CV Pipeline Design - EasyOCR + UIED | Accepted | 2025-01-26 |
| [003](003-platform-handler-architecture.md) | Platform Handler Plugin Architecture | Accepted | 2025-01-26 |
| [004](004-dom-compiler-json-format.md) | DOM Compiler and JSON Output Format | Accepted | 2025-01-26 |
| [005](005-evaluation-framework.md) | Evaluation Framework and Metrics | Accepted | 2025-01-26 |
| [006](006-viewer-workflow-design.md) | Visual DOM Viewer Workflow Design | Accepted | 2025-01-26 |
| [007](007-cv-pipeline-with-llm-refinement.md) | CV Pipeline with LLM Refinement | Accepted | 2025-01-26 |
| [008](008-resolution-aware-thresholds.md) | Resolution-Aware Thresholds and Color Features | Accepted | 2026-03-30 |
| [009](009-slm-advisor-vlm-support.md) | SLM Advisor with VLM Support | Accepted | 2026-03-30 |
| [010](010-smart-merge-split-dedup.md) | Smart Merge, Text-Position Split, Redundancy Removal | Accepted | 2026-03-30 |
| [011](011-symbol-detector.md) | Symbol Detector for UI Elements | Accepted | 2026-03-30 |
| [012](012-ocr-upscale-dual-engine.md) | OCR Upscaling and Dual-Engine Strategy | Accepted | 2026-03-30 |
| [013](013-session-based-output.md) | Session-Based Output and Client Area Capture | Accepted | 2026-03-30 |
| [014](014-project-restructure.md) | Project Restructure and Repository Setup | Accepted | 2026-03-30 |
| [015](015-pluggable-detector-backends.md) | Pluggable Detector Backends (UIED / YOLO / OmniParser) | Accepted | 2026-07-24 |
| [016](016-reading-order-and-labels.md) | Reading-Order Sorting and Element Labels | Accepted | 2026-07-25 |
| [017](017-distributed-hexagonal-grpc.md) | Distributed Hexagonal Architecture with gRPC Model Services | Proposed | 2026-07-26 |
| [018](018-pluggable-capture-service.md) | Pluggable Screenshot Capture (Strategy + Auto-Discovery + Service) | Accepted | 2026-07-26 |
| [019](019-pluggable-actuator-service.md) | Pluggable Input Actuation (Strategy + Auto-Discovery + Service) | Accepted | 2026-07-27 |
| [020](020-client-session-config.md) | Client Session Configuration (`connect` + JSON config) | Accepted | 2026-07-29 |
| [021](021-application-targeting-and-focus.md) | Application Targeting and Focus (`focus_target` on both ports, `Focus` RPC) | Accepted | 2026-08-06 |
| [022](022-description-based-locator.md) | Description-Based Locator (`desc=`) via Tiered Grounding | Accepted | 2026-07-30 |
| [023](023-post-action-recap.md) | Post-Action Recap for Property Verification | Accepted | 2026-07-31 |
| [024](024-multi-locator-fallback-chains.md) | Multi-Locator Fallback Chains (`||`) | Accepted | 2026-08-06 |
| [025](025-session-orchestrator-service.md) | Session Orchestrator Service (forwarding gateway rejected; orchestrator deferred against trigger conditions) | **Proposed** | 2026-08-09 |

## Summary

### ADR-001: Visual DOM System Architecture

Defines the overall system architecture using Computer Vision and OCR to generate UIAutomator-like DOM JSON from screenshots, independent of platform accessibility APIs.

**Key Decision**: Use CV-based detection instead of relying on platform accessibility APIs.

### ADR-002: CV Pipeline Design

Implements a two-stage detection pipeline:
1. EasyOCR for text detection
2. UIED-style algorithms for non-text UI elements

**Key Decision**: Combine OCR + UIED detection with post-processing merge and hierarchy building.

### ADR-003: Platform Handler Architecture

Implements a plugin architecture for supporting multiple platforms (Windows, Android, Linux) with a unified interface.

**Key Decision**: Use abstract base handler with concrete implementations per platform.

### ADR-004: DOM Compiler and JSON Format

Defines the output JSON format compatible with UIAutomator, including multiple locator strategies for element identification.

**Key Decision**: Use UIAutomator-compatible JSON with enhanced locators (id, text, type_index, bounds, center).

### ADR-005: Evaluation Framework

Implements comprehensive metrics for measuring detection quality:
- Element detection (Precision, Recall, F1, IoU)
- OCR accuracy (CER, WER)
- Hierarchy structure
- Locator quality

**Key Decision**: Use standard object detection and OCR metrics with custom hierarchy metrics.

### ADR-006: Viewer Workflow Design

Redesigns the Visual DOM Viewer around a Connect → Capture & Analyze → Define → Export workflow.

**Key Decision**: Combine capture and analyze into single action, add connection management.

### ADR-007: CV Pipeline with LLM Refinement

Documents the complete Visual DOM pipeline architecture with optional LLM-based hierarchy refinement.

**Key Decision**: Two-stage hierarchy building (rule-based + optional LLM), LLM implemented but not integrated into viewer yet.

### ADR-008: Resolution-Aware Thresholds and Color Features

All hardcoded pixel thresholds scaled relative to 1080p reference. Added color feature extraction (contrast, uniformity, border detection) for improved element classification.

**Key Decision**: Scale factor `max(1.0, height/1080)` applied to all pixel thresholds; color features computed lazily only for ambiguous elements.

### ADR-009: SLM Advisor with VLM Support

Optional SLM/VLM review step between CV detection and hierarchy building. Supports text-only (qwen2.5:3b) and vision models (minicpm-v, llava) via Ollama.

**Key Decision**: SLM reviews suspicious elements only (text with spaces, wrong types), VLM can see the screenshot for better accuracy.

### ADR-010: Smart Merge, Text-Position Split, Redundancy Removal

Rewrote merge logic to prevent large containers from swallowing text. Added rule-based splitting using OCR text positions. Priority-based NMS and near-duplicate removal.

**Key Decision**: Containers (>30000 area) never merge text; smallest elements claim text first; elements with text have priority over textless overlaps.

### ADR-011: Symbol Detector for UI Elements

Projection-based pattern matching to detect +, -, =, ×, ÷, . symbols in textless button-sized elements where OCR fails.

**Key Decision**: Multi-strategy binarization + projection analysis. Works well on synthetic/clean UIs, limited on gradient-heavy real-world UIs.

### ADR-012: OCR Upscaling and Dual-Engine Strategy

Auto-upscale small images before OCR, CLAHE contrast enhancement, and EasyOCR + Tesseract dual-engine fallback for low-confidence detections.

**Key Decision**: EasyOCR for region detection + Tesseract for font recognition accuracy on low-confidence results. Default confidence lowered to 0.2.

### ADR-013: Session-Based Output and Client Area Capture

Each analysis creates a timestamped session folder with screenshot, CV result, DOM result, and session metadata. Window capture uses client area (no frame/shadow).

**Key Decision**: Session ID = YYYYMMDD_HHMMSS, all artifacts in `output/sessions/<id>/`.

### ADR-014: Project Restructure and Repository Setup

Moved output files to `output/`, created layered requirements files, set up GitHub repo as `vizdom`, updated README.

**Key Decision**: Clean project root, layered requirements, private GitHub repository.

## ADR Lifecycle

```
Proposed → Accepted → [Deprecated | Superseded]
```

- **Proposed**: Under discussion
- **Accepted**: Decision approved and implemented
- **Deprecated**: No longer valid (kept for history)
- **Superseded**: Replaced by newer ADR

## Creating a New ADR

1. Copy `000-template.md` to `NNN-short-title.md`
2. Fill in all sections
3. Update this README index
4. Submit for review

## References

- [ADR GitHub Organization](https://adr.github.io/)
- [Michael Nygard's ADR article](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
