# ADR-020: Client Session Configuration (`connect` + JSON config)

## Status

Accepted (implemented)

## Date

2026-07-29

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-29 | 1.0 | `VizDomConfig` dataclass tree + `connect()` session API + Robot Framework `Connect` keyword + annotated JSON template (`python -m visual_dom.config --init`). Stage 2.5 / Stage 3 tunables previously hardcoded in the pipeline are now config-driven. Verified end-to-end (config load/validate/round-trip; `connect().analyze()` on the synthetic benchmark; RF library import + keyword). |

## Context

The pipeline exposes many knobs — detector backend, OCR engine, Stage 2.5
merge/deduplicate thresholds, Stage 3 hierarchy thresholds, size filters, an
optional SLM refiner, and the capture strategy. Before this ADR they were reachable
only as scattered `VisualDOMPipeline(...)` constructor arguments, and the Robot
Framework layer forwarded almost none of them (`Dump Visual DOM` only took
`ocr_engine`). Several Stage 2.5 / Stage 3 parameters (`cross_type_iou`,
duplicate-box tolerance, merge-group fill ratio, in-pipeline containment
threshold) were **hardcoded** and not reachable at all.

A client — a Python caller or a Robot Framework suite — needs a **single, explicit,
reproducible** way to select models and tune every stage for its target UI, and to
do so **once per session** rather than per call.

## Decision

Introduce one JSON configuration object and a session entry point.

1. **`visual_dom.config.VizDomConfig`** — a tree of plain dataclasses
   (`detector`, `ocr`, `refiner`, `merge`, `hierarchy`, `filter`, `capture`,
   `output`) with defaults everywhere. It loads from a file/dict/None, **rejects
   unknown keys** (typos fail loudly), ignores `_`-prefixed comment keys, and can
   emit an **annotated template** via `python -m visual_dom.config --init` and
   validate via `--check`.

2. **`visual_dom.connect(config) -> Session`** — the client's first call. It
   resolves the config and builds the detector/OCR/refiner **once**; `Session.
   analyze(image)` reuses them across images so batch/suite runs pay model-load
   cost once.

3. **Robot Framework `Connect` keyword** — the same object behind a keyword.
   After `Connect  vizdom.config.json`, `Dump Visual DOM` uses the configured
   session for all stages, and the config's `capture` section is applied to the
   library's capture port so one file configures both DOM generation and screen
   acquisition. Calling `Dump Visual DOM` with no prior `Connect` keeps the old
   ad-hoc behaviour.

4. **Expose the hardcoded stage params.** `VisualDOMPipeline` gains
   `cross_type_iou`, `duplicate_tolerance_px`, `group_fill_ratio_min`, and
   `hierarchy_containment_threshold` constructor arguments (defaults unchanged), so
   the config can drive Stage 2.5 and Stage 3.

## Consequences

- **Reproducible & shareable.** A run is fully described by one committed file;
  `vizdom.config.example.json` is the tracked template, users' own
  `vizdom.config.json` is gitignored.
- **Uniform surface.** Python and Robot Framework read the same schema; there is
  one place to document every knob (see `docs/CONFIGURATION.md`).
- **Backwards compatible.** No `Connect` / no config → previous defaults and the
  ad-hoc `Dump Visual DOM` path are unchanged.
- **No new dependency.** Dataclasses + `json` only; validation is hand-rolled.
- Future work: JSON-Schema export for editor autocompletion; per-keyword config
  overrides layered on top of the session config.
