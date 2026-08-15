# ADR-027: Modular Three-Stage Detector (a new `modular` strategy beside OmniParser)

## Status

Proposed

## Date

2026-08-13

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-08-13 | 1.0 | Initial evaluation (three boundaries, contracts, candidate models, benchmark plan) |
| 2026-08-15 | 1.1 | Skeleton implemented: ports, fusion port, `modular` backend registered, pipeline integration; no-weights combo verified end-to-end |

## Context

OmniParser is integrated as one monolithic `DetectorBackend`, but internally it
is three models plus fusion logic. The boundaries are verifiable in the vendored
code (`third_party/OmniParser/util/utils.py`):

| Stage | Function | Model | What crosses the boundary |
|---|---|---|---|
| 1. Interactable-region proposal | `predict_yolo` | YOLOv8 fine-tune (`icon_detect`, **AGPL-3.0**) | boxes (px) + confidence logits, `interactivity=True` |
| 2. Text reading | `check_ocr_box` | EasyOCR / PaddleOCR | text boxes + strings (no confidence channel) |
| 3. Semantic captioning | `get_parsed_content_icon` | Florence-2 (`icon_caption`, **MIT**) | caption string per still-unlabelled box, batched crops |
| — Fusion (no model) | `remove_overlap_new` + content assignment in `get_som_labeled_img` | pure logic | keep-smaller-box overlap removal; OCR boxes absorbed into icon boxes (`is_inside` > 0.80); text→`content` |

Three observations from work already done make the decomposition more than
theoretical:

1. **Stage 2 is already externally replaceable — and better.** The ADR-016
   text ensemble feeds our upscaling `TextDetector` into OmniParser, and the
   prefer-external union measurably beat OmniParser's internal OCR
   (IMPROVEMENTS §3b). Stage 2 as an independent component is proven, not
   speculative.
2. **The stage outputs are separable in practice.** The confidence-recovery
   work (IMPROVEMENTS §3d) intercepts stage 1's boxes+logits and stage 2's
   scores at the call boundary and matches them back — i.e., we already
   operate on the per-stage contracts, just wrapped around the monolith.
3. **The stages have different costs and licences.** Stage 1 is a small,
   fast YOLO but AGPL; stage 3 is the heavyweight (Florence-2 dominates
   latency and VRAM) but MIT; stage 2 is CPU-friendly. A monolith forces one
   deployment shape and the union of all licence obligations.

Driver from the task (and the standing constraint from the user): the modular
path must be **an additional strategy** — the existing `omniparser`, `uied`,
`yolo` and `grpc` backends must be untouched and remain the baseline/fallback.

## Considered options

### Option A — Keep the monolith, keep patching at the boundary

- ✓ Zero new code; the ensemble and confidence recovery already work this way.
- ✗ Every improvement is a wrap-around (monkeypatching `predict_yolo`,
  round-tripping OCR through a channel with no confidence field). Each new need
  adds another interception.
- ✗ Cannot swap stage 1 or 3 at all; AGPL stays whenever OmniParser is used.
- ✗ Deployment is all-or-nothing: the light YOLO cannot run without loading
  Florence-2.

### Option B — Fork/patch OmniParser itself into three modules

- ✗ The repo is vendored outside git (ignored); patches do not survive a
  re-clone (the same reason confidence recovery avoided touching it).
- ✗ Tracks upstream churn forever; `util.utils` signatures already vary across
  releases (see the backend's VERSION CAVEAT).

### Option C — A new composite `modular` backend with three per-stage ports (proposed)

- ✓ Isolation by construction: a separate registry entry
  (`register("modular", ...)`), selected only by `detector.backend=modular`.
  No line of the existing backends changes; `omniparser` remains available for
  every benchmark as the baseline.
- ✓ Each stage becomes independently replaceable/configurable through the same
  registry pattern used for detectors (ADR-015), capture (ADR-018) and
  actuators (ADR-019).
- ✓ Reuses what exists instead of inventing: stage 2 **is** `TextDetector`
  (ADR-012, engines already pluggable); one stage-3 candidate **is** the
  Ollama vision adapter already shipped for the SLM refiner (ADR-009).
- ✓ The common intermediate representation already exists: `Detection`
  (detector_port.py). All combinations emit the same IR, so the evaluation
  framework and lifecycle benchmark compare combos without adaptation.
- ✗ Fusion logic becomes ours to own and keep correct (see Consequences).

## Decision (proposed)

Adopt **Option C**: a `ModularDetectorBackend` registered as `"modular"`,
composing three sub-ports:

```
core/ports/outbound/
  region_proposer_port.py   RegionProposer.propose(image)  -> [(bounds, confidence)]
  (text: existing TextDetector / ocr engine, ADR-012)      -> [TextElement(bounds, text, confidence)]
  captioner_port.py         Captioner.caption(image, boxes) -> [str | None]   (batched)

adapters/outbound/detectors/modular_backend.py
  1. regions  = region_proposer.propose(image)          # interactable candidates
  2. texts    = text_detector.detect(image)             # full-image OCR (reused)
  3. fused    = fuse(regions, texts)                    # port of remove_overlap_new semantics:
                                                        #   keep-smaller on region/region overlap,
                                                        #   absorb OCR boxes inside a region (>0.80),
                                                        #   standalone text boxes pass through
  4. captions = captioner.caption(image, unlabelled)    # optional stage — skippable
  5. emit List[Detection]  (bounds, visual_type, REAL confidence, text, label,
                            interactable, source="modular")
```

Configuration extends the existing `detector` section without touching current
keys — e.g. `detector.backend: modular`, `detector.region_model`,
`detector.captioner`, `detector.captioner_model`. Stage plugins discover via
the same `plugins/` auto-discovery as capture/actuator strategies.

Notable properties:

- **Confidence is native**, not recovered: stage 1 returns logits directly and
  the OCR scores never round-trip through a channel that drops them — the §3d
  interception becomes unnecessary *in this backend* (it stays for
  `omniparser`).
- **Stage 3 is optional.** Without a captioner, icons get no `label`; `desc=`
  locators then fall back to tier-2 VLM grounding (ADR-022) instead of tier-1
  label matching. That trade (no GPU captioner vs. slower desc resolution) is
  exactly the kind of choice modularity exists to offer.
- **Distribution falls out for free**: each stage can later sit behind the
  existing gRPC service pattern (ADR-017) — e.g. captioner on the GPU box,
  region+OCR local — without new architecture.

## Candidate models per stage

Licence/runtime claims to be re-verified at selection time; ✱ = needs
fine-tuning, no off-the-shelf UI model.

**Stage 1 — interactable-region proposal**

| Candidate | Licence | Runtime | Notes |
|---|---|---|---|
| OmniParser `icon_detect` (baseline) | AGPL-3.0 | GPU, fast | proven on UI; keeps AGPL |
| UIED (in-house, classical CV) | project | CPU | no weights, no licence cost; weaker on stylised UIs |
| Our `yolo_ui_best.pt` | AGPL-3.0 (ultralytics) | GPU | already trained; same licence problem |
| RT-DETR / D-FINE ✱ | Apache-2.0 | GPU | **clears AGPL** — requires fine-tuning on UI data (RICO/ScreenSpot + our annotator) |

**Stage 2 — text reading** (already pluggable; measured better than
OmniParser's internal OCR)

| Candidate | Licence | Runtime | Notes |
|---|---|---|---|
| EasyOCR (baseline) | Apache-2.0 | CPU/GPU | current default; upscaling + tesseract retry already built |
| PaddleOCR | Apache-2.0 | CPU/GPU | fast, multi-language |
| Tesseract | Apache-2.0 | CPU | best on system fonts |

**Stage 3 — semantic captioning**

| Candidate | Licence | Runtime | Notes |
|---|---|---|---|
| Florence-2-base (baseline) | MIT | GPU ~1 GB | current captioner; batched crops |
| Qwen2-VL-2B (via Ollama) | Apache-2.0 | GPU ~2.4 GB | **reuses the ADR-009 Ollama adapter**; per-crop calls — batching cost to measure |
| MiniCPM-V (via Ollama) | OpenBMB (academic free; verify commercial) | GPU ~5.5 GB | best UI understanding in our SLM trials |
| *(none)* | — | — | skip captions; desc falls to ADR-022 tier-2 |

## Evaluation plan

Same data, same metrics, same harness — the point of the shared IR:

1. **Baseline**: current `omniparser` backend on the unified benchmark dataset.
2. **Combos** (each just a config change): `icon_detect + easyocr + florence2`
   (parity check — should match baseline within noise), `uied + easyocr +
   florence2`, `icon_detect + easyocr + (none)`, `icon_detect + easyocr +
   qwen2-vl`.
3. **Metrics**: detection F1 / mIoU, element-type accuracy, actionable
   center-hit, lifecycle action-hit / verify / false-pass, latency with load vs
   parse split, peak VRAM.
4. **Decision gate**: migrate / partially replace / keep, written back into
   this ADR's status.

**Hold inherited from the grounder benchmark:** combos involving new large
models (Qwen2-VL, fine-tuned RT-DETR) wait on the open "where do the big models
run" hardware decision. The parity check and the UIED/no-captioner combos have
no such dependency.

## Consequences

**Positive**

- Per-stage replacement and per-stage deployment; AGPL isolation becomes
  *possible* (stage 1 is the only AGPL component).
- Native confidences and native OCR quality — two existing workarounds become
  unnecessary in the new path.
- Baseline preserved untouched: every change is behind `backend=modular`, so
  the demo path (`omniparser`) carries zero risk.

**Negative / limits**

- **Fusion becomes ours.** `remove_overlap_new` semantics (keep-smaller,
  absorb-inside > 0.80) must be ported faithfully and regression-tested against
  the parity combo — the "two bugs cancelling" episode (IMPROVEMENTS §3c) shows
  how subtle fused-box behaviour is.
- Caption batching: OmniParser batches 128 crops through Florence-2; a naive
  per-crop Ollama call may be an order of magnitude slower — must be measured
  before Qwen2-VL is declared viable.
- More configuration surface to validate (three stage choices instead of one
  backend name); the schema-generated ConfigDialog and `gen_config_reference`
  keep the docs/UI in sync automatically, but invalid combos need real errors.
- Benchmarks for the heavy combos are gated on the hardware decision; until
  then this ADR cannot honestly move past Proposed.

## Implementation status (v1.1)

Skeleton in place, all combos behind `detector.backend=modular`:

- Ports: `core/ports/outbound/region_proposer_port.py`, `captioner_port.py`.
- Fusion: `adapters/outbound/detectors/modular_fusion.py` — faithful port of
  `remove_overlap_new` including its order-dependent quirks (each pinned by a
  unit test, e.g. an absorbed text still labels a second containing region).
- Backend: `modular_backend.py` — stage factories (`omniparser`/`uied`
  proposers; `florence`/`none` captioners), instances injectable for tests.
  Registered additively in the detector registry; existing backends untouched.
- Pipeline integration: `modular` joins `omniparser` in
  `_BACKEND_THRESHOLDED_SOURCES` (confidence-gate exemption + ranking-as-1.0),
  and the pipeline shares its `TextDetector` instance with the backend's
  stage 2 (one OCR model load per process).
- Verified: no-weights combo (`uied + easyocr + none`) through the full
  pipeline on a real IWT capture — 72 elements, native confidences, smart-merge
  and rescan stages operating on the output. 15 unit tests
  (`tests/unit/test_modular_detector.py`).

Known inefficiency, accepted for parity: OCR *runs* twice per frame (pipeline
Step 1 + backend stage 2), the same cost shape as the omniparser ensemble.
Folding them into one pass is a part-2 optimization.

Not yet: the parity benchmark run, Ollama captioner, non-AGPL region model
(gated on the hardware decision).

## Trigger conditions (Proposed → Accepted)

- The parity combo reproduces the `omniparser` baseline within agreed noise on
  the unified benchmark, and
- at least one alternative combo shows a concrete win (licence, latency,
  quality, or deployment shape) worth the fusion-ownership cost, and
- the hardware decision for large-model benchmarking is made.

## References

- Task: Notion "Evaluate splitting OmniParser into 3 modular components"
- Boundaries: `third_party/OmniParser/util/utils.py` (`predict_yolo`,
  `check_ocr_box`, `get_parsed_content_icon`, `remove_overlap_new`)
- Extension point: `core/ports/outbound/detector_port.py`,
  `adapters/outbound/detectors/registry.py` (ADR-015)
- Reused pieces: `TextDetector` (ADR-012), Ollama adapter (ADR-009),
  service pattern (ADR-017), plugin discovery (ADR-018/019)
- Evidence: IMPROVEMENTS §3b (external OCR beats internal), §3d (stage
  outputs separable and confidences recoverable)
