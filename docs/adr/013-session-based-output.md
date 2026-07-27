# ADR-013: Session-Based Output and Window Client Area Capture

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

### Session Output

During development and debugging, comparing detection results across runs was difficult:
- Each analysis overwrote the same `cv_pipeline_result.json`
- No way to correlate a screenshot with its detection results
- Settings used (OCR engine, SLM model) were not recorded

### Window Capture

The Windows desktop capture used `GetWindowRect` which includes window frame, title bar, and Windows 10/11 shadow borders (~7px each side). These extra pixels added noise to element detection at the image edges.

## Decision

### 1. Session-Based Output

Each Capture & Analyze creates a timestamped session folder:

```
output/sessions/20260329_195905/
├── screenshot.png          # Captured screenshot
├── cv_pipeline_result.json # CV pipeline output (before hierarchy)
├── dom_result.json         # Final compiled DOM (after hierarchy + SLM)
└── session_info.json       # Session metadata
```

Session metadata includes:
- `session_id`, `timestamp`
- `ocr_engine`, `slm_enabled`, `slm_model`
- `gpu_available`, `element_count`, `cv_stats`
- `image_size`

Session ID format: `YYYYMMDD_HHMMSS`, shown in the viewer status bar.

### 2. Client Area Capture

Replaced `GetWindowRect` (full window including frame) with `GetClientRect` + `ClientToScreen`:

- `GetClientRect` returns the client area size (content only)
- `ClientToScreen` converts client (0,0) to screen coordinates
- Falls back to `GetWindowRect` if client area capture fails

This produces a clean screenshot of just the application content, excluding the window frame and shadow borders.

## Consequences

### Positive
- Full traceability: every analysis has a complete artifact set
- Easy comparison across runs (different OCR engines, SLM on/off)
- Cleaner screenshots without window chrome artifacts
- Session info enables automated regression testing

### Negative
- Disk usage increases (~1-5MB per session)
- `output/sessions/` excluded from git via `.gitignore`

## Files Changed

- `tools/visual_dom_viewer/ui/main_window.py` — Session folder creation, artifact export, session info recording
- `tools/visual_dom_viewer/plugins/windows_handler.py` — Added `_get_client_rect_on_screen()`, updated `capture_screenshot()` to use client area, added `ClientToScreen` WinAPI binding
