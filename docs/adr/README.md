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
