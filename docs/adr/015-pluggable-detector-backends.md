# ADR-015: Pluggable Detector Backends (UIED / YOLO / OmniParser)

## Status

Accepted

## Date

2026-07-24

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-24 | 1.0 | Initial version — introduces the detector-backend abstraction and adds OmniParser as an option |

## Context

A July 2026 review of the GUI-understanding landscape (see
`docs/discussion/landscape-comparison-*.html`) found that Microsoft's **OmniParser**
independently implements our detection architecture (YOLO icon detection + OCR +
a captioning model → boxes with labels and interactability). Two conclusions followed:

1. Element detection has become a commoditised layer; our differentiation lies
   in hierarchy construction, the DOM representation and the Robot Framework
   testing integration — not in the detector itself.
2. We should be able to **compare** our own CV detector against OmniParser
   empirically, and to **swap** detectors for licensing reasons.

Before this change, the pipeline hard-coded detector choice as `if/elif` branches
over a `detector` string ("uied" | "yolo" | "hybrid"), with YOLO initialised
inline. Adding OmniParser that way would have compounded the branching and mixed
heavy optional dependencies (torch, ultralytics, OmniParser) into pipeline import.

### Licensing driver

Our detection stack is already on **AGPL-3.0** through the existing Ultralytics
dependency (`pyproject.toml`, `inference_yolo.py`, `cv_model_registry.py`).
OmniParser's `icon_detect` component is likewise AGPL-3.0 (`icon_caption` is MIT).
Adopting OmniParser therefore introduces **no new licence class**, but the ability
to swap to a permissively licensed detector (RT-DETR upstream, YOLOX, DETR — all
Apache 2.0) later must not require rewriting the pipeline.

## Decision

### 1. Detector backend interface

Added `src/visual_dom/cv/detectors/` defining:

- `Detection` — a neutral dataclass (bounds, visual_type, confidence, optional
  text, optional `interactable`, source, containment, `extra`). Independent of
  the pipeline so backends carry no dependency on `pipeline.py`.
- `DetectorBackend` (ABC) — `detect(image) -> List[Detection]`, plus declarative
  metadata: `name`, `description`, `license`, `requires_gpu`, and a cheap
  `is_available()` classmethod that never raises.

### 2. Backends

- `UIEDBackend` — adapter over the existing `UIEDDetector` (default; CPU; no weights).
- `YOLOBackend` — Ultralytics YOLO; carries an explicit AGPL-3.0 warning.
- `OmniParserBackend` — Microsoft OmniParser; configurable repo/weights paths
  (constructor args or `OMNIPARSER_ROOT` / `OMNIPARSER_ICON_DETECT` /
  `OMNIPARSER_ICON_CAPTION`); normalizes OmniParser's `[0,1]` bboxes to pixels.

### 3. Registry

`create_detector(name, **kwargs)` and `list_detectors()` in `registry.py`. Lazy
factories keep torch/ultralytics/OmniParser out of import time — a heavy backend
is imported only when actually constructed.

### 4. Pipeline integration

`VisualDOMPipeline` gains `detector_kwargs` and now builds a `_primary_backend`
via the registry for single-backend modes ("uied", "yolo", "omniparser"),
converting `Detection -> UIElement` in one place (`_convert_detections`). The
legacy `"hybrid"` mode (YOLO + UIED merge) is left on its bespoke path to avoid
regressions. On backend init failure the pipeline degrades gracefully (UIED
failure is fatal; others log and yield zero elements).

### 5. CLI

`scripts/process_gui_image.py` gains `--detector {uied,yolo,omniparser,hybrid}`,
`--omniparser-root`, `--omniparser-icon-detect`, `--omniparser-icon-caption` and
`--yolo-model`.

## Alternatives Considered

- **Extend the if/elif chain with an OmniParser branch** — rejected: worsens
  branching and couples optional heavy deps to pipeline import.
- **Replace UIED with OmniParser outright** — rejected: loses the CPU-only path
  (a genuine differentiator for test rigs) and the ability to compare.
- **Depend on OmniParser as a pip package** — not viable: it is a repo + weights
  with an API that has drifted across versions; hence the isolated
  `_parse_content_list` and configurable paths.

## Consequences

### Positive

- Detectors are interchangeable behind one interface → enables the planned
  empirical comparison and licence flexibility.
- Optional heavy dependencies stay out of import time.
- `Detection.interactable` preserves OmniParser's interactability signal, newly
  surfaced in element output.
- Licences are explicit in code and in `list_detectors()`.

### Negative

- Two detection code paths remain (pluggable single-backend + legacy hybrid).
- `OmniParserBackend` is coupled to OmniParser's output format; version drift
  requires updating `_parse_content_list` (isolated for this reason).
- Backend metadata (licence/gpu) is duplicated between the class and the registry.

### Follow-ups

- Verify `OmniParserBackend` against a real OmniParser install (output format,
  exact `util.utils` signatures).
- Add hierarchy-correctness metrics for the UIED-vs-OmniParser comparison.
- If commercial/network reuse is required, add a permissive (Apache) detector
  backend and confirm AGPL implications with the university/employer.

## Files Changed

- `src/visual_dom/cv/detectors/` — New: `base.py`, `registry.py`,
  `uied_backend.py`, `yolo_backend.py`, `omniparser_backend.py`, `__init__.py`
- `src/visual_dom/cv/pipeline.py` — `detector_kwargs`, `_init_backend`,
  `_convert_detections`, `_primary_backend`; `UIElement.interactable`
- `src/visual_dom/cv/__init__.py` — export detector API
- `scripts/process_gui_image.py` — detector CLI arguments
