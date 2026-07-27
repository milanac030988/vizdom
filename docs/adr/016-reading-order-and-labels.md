# ADR-016: Reading-Order Sorting and Element Labels

## Status

Accepted

## Date

2026-07-25

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-25 | 1.0 | Reading-order sort + `label` property (association-based). Text ensemble and SLM label refinement noted as follow-ups. |
| 2026-07-25 | 1.1 | Text ensemble implemented: OmniParser backend accepts an `ocr_provider`; pipeline feeds its upscaling TextDetector in. Measured 20→42 text boxes on the calculator sample. |
| 2026-07-25 | 1.2 | Ensemble dedup changed from IoU to **gap-fill** (overlap-over-smaller-box) after A/B showed doubled text ("5 5", "10* 10*"). Gained now shows real button glyphs (7,8,9,+,C,n!) vs original's Florence caption hallucinations ("7, September, 2024", "Hyperlink"), with no duplication. |
| 2026-07-26 | 1.3 | Over-segmentation **smart-merge** + SLM merge/label refinement. Rule-based Step 6c merges a multi-word "full text" anchor with same-line fragment boxes (fixes OmniParser splitting a 2-line button into halves + a full-text box), guarded by spatial fill-ratio ≥0.5 and a breadcrumb-delimiter skip. SLM gains `merge`/`label` actions (fed geometric merge candidates) for ambiguous cases. CLI `--no-merge`, pipeline `merge_oversegmented`. |
| 2026-07-26 | 1.4 | Added `_find_line_text_candidates`: groups consecutive same-line non-interactable **text** pieces (split into runs by horizontal gap ≤ 2.5×median height) as **SLM merge candidates**. Handles the "sentence split into disjoint pieces, no full-text anchor" pattern that the anchor-containment rule can't catch. Candidates only (SLM decides — geometry can't distinguish one wrapped sentence from separate labels); not auto-merged. Also fixed: ensemble OCR provider now uses a dedicated easyocr detector when the pipeline's ocr_engine is None. |
| 2026-07-26 | 1.5 | **Live SLM finding + fix.** Ran minicpm-v (VLM) live via Ollama. It proposed ~23 merges, ~22 of them BAD (merging separate buttons/labels) — a 7B VLM over-merges badly with free rein. Fix: **SLM merges are now gated to the geometric candidate groups** (subset check) — the SLM may only confirm/reject proposed over-segmentation, not invent merges. Ungated 71→57 (mostly wrong); gated 72 with only the 1 legit text-line merge applied, 22 rejected. Confirms the rules-propose / SLM-confirms architecture. |
| 2026-07-26 | 1.6 | **Label now surfaces to the Viewer.** The `label` was computed on coarse_builder nodes but lost before display. Fixed the whole chain: coarse_builder writes resolved labels back onto the source element dicts (Step 3c); `DOMCompiler` DOMNode gains `label` (in `to_dict` + read from elem); the Viewer's `_parse_visual_dom_element` carries `label` + `interactable` into `element.properties` so the PropertyTable shows them. |
| 2026-07-26 | 1.7 | **False-merge guard for distinct buttons.** A spanning text label ("Session Servers") over two adjacent clickable buttons ("Session", "Servers") matched the anchor rule and fused them. Geometry can't distinguish that from a wrapped 2-line button. Fix: smart-merge now **skips any group with ≥2 independently-interactable members** (distinct controls) and defers them to the SLM; wrapped-button halves (interactable=None) still auto-merge. Note: separately, OmniParser sometimes fuses adjacent buttons at *detection* time (one icon box, OCR "Session Servers") — that's upstream, not our merge. |

## Context

With OmniParser adopted as the strongest detector backend (ADR-015), three
weaknesses of the raw detection output were identified:

1. **No reading order.** Detected elements come out in detector/area order, not
   the order a person reads a screen. This produced non-deterministic-looking
   output, made diffs/tests noisy, and gave the optional SLM reviewer spatially
   incoherent input (harder to reason about).
2. **Missing text.** Even the best detector misses some text.
3. **No semantic label.** Elements had `ocr_text` (raw text on the element) but
   no resolved *name* — the thing that makes an element identifiable for a
   locator (e.g. "the field labelled Username").

These are a dependency chain: reading order enables reliable label association,
and text completeness feeds both. This ADR covers items 1 and 3. Item 2 (text
ensemble) and SLM-based label refinement are follow-ups.

## Decision

### 1. Reading-order sorting (`src/visual_dom/reading_order.py`)

A geometry-only, model-free, deterministic module:

- `sort_reading_order(items, get_bounds)` — row-bands elements (group by vertical
  centre within a tolerance = `max(4px, 0.6 * median height)`), orders rows
  top→bottom, and orders within each row left→right. A lightweight XY-cut. A
  naive `sort((y, x))` is explicitly avoided because same-row elements rarely
  share an exact top-y. The size-relative tolerance keeps it resolution-aware
  (consistent with ADR-008).
- `order_tree(children, ...)` — applies the sort recursively per level, so a
  container's children read in order *within* that container; parents are never
  interleaved with descendants.

**Pipeline integration** (`cv/pipeline.py`): reading order is applied twice —
once before the SLM review (Step 7b, so the reviewer sees ordered input) and
once after hierarchy building (Step 9b), because `_build_hierarchy` re-sorts by
area. The post-hierarchy sort means the sequential IDs assigned next follow
reading order (**E1 = top-left**).

**Hierarchy integration** (`hierarchy/coarse_builder.py`): `order_tree` reorders
the tree's children after containment is built.

### 2. `label` property

- Added a `label` string to the pipeline `UIElement`, the `coarse_builder`
  `TreeNode`, and the DOM schema (element + node). Distinct from `ocr_text`:
  `ocr_text`/`text` is the raw text *on* the element; `label` is its identifying
  *name*.
- Resolution rule (in `coarse_builder`, which already did label association):
  - a control with an associated nearby text **above/left** takes that text as
    its label (extends the existing `_associate_labels` / `associated_label_id`);
  - otherwise an element with its own text takes that as its label (a button
    reading "OK" → `label = "OK"`), via `_assign_own_text_labels`.
- Reading order improves label association by making "the text immediately
  before/above" well-defined.

## Alternatives Considered

- **Naive `sort((y, x))`** — rejected: scrambles rows under sub-pixel/again
  jitter in top-y.
- **Compute labels in the pipeline instead of the hierarchy builder** — rejected:
  association needs the full element set and neighbour geometry, which is the
  hierarchy builder's job; the pipeline `UIElement.label` field exists mainly for
  future SLM refinement.
- **XY-cut (full recursive projection)** — deferred: row-banding is simpler and
  sufficient for UI layouts; can revisit if complex multi-column layouts need it.

## Consequences

### Positive
- Deterministic, reading-ordered output; stable IDs (E1 = top-left) → cleaner
  diffs and tests.
- Better SLM input (ordered) → better suggestions.
- Elements gain a semantic `label` usable directly by Robot Framework locators.
- Reuses existing label-association code rather than duplicating it.

### Negative / limitations
- Row-banding can mis-split when a tall element sits between two rows; tolerance
  is heuristic.
- Label quality depends on text completeness — a missing label text yields no
  label (motivates the text-ensemble follow-up).
- The pipeline `UIElement.label` is not yet populated by the pipeline itself
  (only the hierarchy builder populates labels today).

### Follow-ups
- **Text ensemble** (original point 2) — **DONE (v1.1)**. `OmniParserBackend`
  gained an optional `ocr_provider` callable (image → [(bbox, text)]) plus
  `ocr_ensemble`/`ocr_dedup_iou`. In `detect()` the provider's boxes are unioned
  with OmniParser's own OCR, deduped by IoU, before `get_som_labeled_img`. The
  pipeline injects its upscaling `TextDetector` as the provider for the
  omniparser path. Measured on the calculator sample: 20 → 42 text boxes, all 53
  elements text-covered. Note: the provider adds an OCR pass; within the full
  pipeline (Step 1 text detection also on) OCR effectively runs twice —
  acceptable for now (OmniParser inference dominates), optimisation deferred.
  **Switchable:** pipeline `text_ensemble` (default True) toggles original vs
  gained; exposed as CLI `--no-text-ensemble` and a Viewer "Text+" checkbox — so
  the two can be A/B compared (useful for the planned UIED-vs-OmniParser eval).
- **SLM label refinement**: use the SLM to suggest labels for ambiguous/missing
  cases, leveraging the now-ordered, structured context.

## Files Changed

- `src/visual_dom/reading_order.py` — New: `sort_reading_order`, `order_tree`
- `src/visual_dom/cv/pipeline.py` — apply reading order (Steps 7b, 9b);
  `UIElement.label`
- `src/visual_dom/hierarchy/coarse_builder.py` — `order_tree` in `build`;
  `TreeNode.label`; `_assign_own_text_labels`; label set in `_associate_labels`
- `src/visual_dom/schema/dom_schema.py` — `label` (+ `interactable`) properties
