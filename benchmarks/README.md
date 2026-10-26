# VizDOM Evaluation — Mechanism, Test Plan, Flow, and Metrics

This README explains **how VizDOM is evaluated**: what is measured, on what
data, by what mechanism, and how to read and reproduce the numbers. The
API-level reference for the metric implementations lives in
[`docs/EVALUATION.md`](../docs/EVALUATION.md).

---

## 1. Philosophy: two levels, one dataset

A test-automation system can fail at any stage — detection, OCR, merging,
locator resolution, coordinate mapping, verification — so we evaluate at **two
levels over the same artifacts**:

| Level | Question it answers | Unit |
|---|---|---|
| **Per-stage** | *which component* is weak, and by how much | one element / one glyph / one box |
| **Full lifecycle** | *would a test suite work*, end to end, at what cost | one test **step** (locate → act / verify) |

Neither alone is sufficient. A lifecycle score without stage ground truth tells
you *that* a step failed but not *why*; stage scores without a lifecycle view
let a system look good while being unusable for testing (e.g. accurate boxes
but ambiguous texts). Because both levels share the same states and ground
truth, **every end-to-end failure remains attributable to a stage**.

A further principle separates this from agent benchmarks: **testing needs
oracles**. An agent benchmark asks "did it click the right place"; a *testing*
benchmark must also ask "does it judge correctly" — including whether it
reports success on things that are **not there** (a false pass, the worst
failure a test system can produce).

---

## 2. The dataset

```
data/synthetic/test/
  images/<state>.png        44 rendered UI states (dashboards, forms, ...)
  labels/<state>.json       per-element ground truth:
                              id, visual_type (button / input_field / checkbox /
                              text / icon / block / divider), bounds,
                              ocr_text, parent_id / children_ids
tests/samples/symbols/      130 labelled key-cells across 4 real Calculator
                            renderings (glyph reading ground truth)
benchmarks/
  lifecycle-synthetic-v1/steps.json   the generated lifecycle step set (committed)
  results/                            timestamped result files (gitignored)
```

Content: 1,074 texts, 183 buttons, 135 input fields, 76 checkboxes, 36 icons
across the 44 states. **Caveat, stated up front:** the set is synthetic and
clean; absolute scores will be lower on gradient-heavy real-world UIs. Adding
real states is the top roadmap item — the schema already accommodates them.

---

## 3. Mechanism: how lifecycle steps are derived (no manual annotation)

`python -m visual_dom.evaluation.lifecycle.generate` turns element ground truth
into test steps automatically:

1. **Action steps** — every actionable element (button / input field /
   checkbox) whose caption is **unique within its state** becomes:
   - a *locator* for DOM-based systems: `text="Save"`
   - an *instruction* for grounding models: `click the 'Save' button`
   - the GT target bounds to score against.
2. **Positive verify steps** — the same elements: `the 'Save' button is
   visible` → expected verdict `PASSED`.
3. **Negative verify steps** — two deliberately **absent** captions per state
   ("Frobnicate", "Purple Elephant", …) → expected verdict `FAILED`. These
   measure **false passes**.

The uniqueness rule exists because VizDOM's resolution contract fails
*by design* on ambiguity; grading systems on deliberately ambiguous input would
measure the benchmark, not the system. Captions come from the element's own
`ocr_text` or a child text element's. Generation is seeded and deterministic;
the resulting `steps.json` is committed so results are reproducible.

Current set (`lifecycle-synthetic-v1`): **514 steps** = 213 action +
213 positive verify + 88 negative verify, over 44 states.

Every step carries a **dual representation**, which is what makes parser-based
systems and per-step grounding models directly comparable — they receive the
same task in their native input form and are scored on the same outcome.

---

## 4. The flow

```
                    ┌──────────────────────────────────────────────┐
 labels/*.json ───► │ generate.py  → benchmarks/.../steps.json     │  (once, committed)
                    └──────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴──────────────────────────┐
                    ▼                                              ▼
        VizDomExecutor  (per detector)                GrounderExecutor (per model)
        ─ connect + WARM-UP  ..... timed as           ─ load model  .... timed as
          "model load" (incl. lazy inits)               "model load"
        ─ per STATE: analyze once → DOM               ─ per STEP: one inference
          ..... timed as "parse"                        image + instruction → point
        ─ per STEP: resolve locator in the              or statement → PASSED/FAILED
          cached DOM  ..... timed as "resolution"       ..... timed as step latency
          action → element centre = click point
          verify → exactly-one contract answers
                                        │
                    ┌───────────────────┴──────────────────────────┐
                    ▼                                              ▼
                _score() per step                      benchmarks/results/<ts>.json
                action: point inside GT bounds?        (per-step detail, dataset id,
                verify: verdict == expected?            git commit)  +  <ts>.md table
                        false pass tracked separately
```

Key timing rule (learned the hard way): **one-time model load is timed
separately from parsing**, and the load phase includes a dummy-frame warm-up
analyze so *lazily* initialized components (the EasyOCR reader loads on first
use, not at connect) land in the load figure — otherwise they inflate one
arbitrary state's parse time. Warm-model amortization is itself a claim under
test (NFR3), so the split is not cosmetic.

Failures never crash a run: a model exception scores as a miss with the error
recorded in that step's detail.

---

## 5. Metrics

### Per-stage (see `docs/EVALUATION.md` for implementations)

| Metric | Definition | Why it exists |
|---|---|---|
| Precision / Recall / **F1** | greedy box matching at IoU ≥ 0.5, pooled over elements | standard detection quality |
| **mIoU** | mean IoU of matched boxes | localisation tightness |
| **Center-hit** | GT centre inside the predicted box (and vice versa) | *click-targetability* — the operationally relevant lens; a box can fail IoU 0.5 yet be perfectly clickable |
| **Char accuracy** | 1 − character error rate on matched text | OCR quality |
| **Type accuracy** (per class) | correct `visual_type` on matched elements | role-based locators depend on it; aggregates hide per-class collapse |
| **Glyph accuracy** | 130-case labelled set incl. required *rejections* | the symbol reader's confident misreads poison `text=` |

Aggregate F1 is dominated by text fragmentation (63 % of GT elements are
text), so **per-type recall and center-hit are the testing-relevant figures**
— this is why one number misleads, and why we report several.

### Lifecycle

| Metric | Definition | Why it exists |
|---|---|---|
| **Action-hit rate** | produced click point lies inside the GT element's bounds | did the *whole* pipeline put the click on the right element |
| **Verify accuracy** | verdict (`PASSED`/`FAILED`) equals expectation | oracle quality |
| **False-pass rate** | `PASSED` on an absent target | the worst testing failure; agent benchmarks do not measure it |
| **Resolution / step** | locator lookup time in the cached DOM | the "cheap lookup" half of the cost claim |
| **Model load** | one-time connect + warm-up | amortized cost, reported separately |
| **Parse / state** | mean full-pipeline time per screen state | the "pay once per screen" half of the cost claim |
| (grounders) **Inference / step** | one model call per step | the cost model being compared against |

The cost columns make the parse-once economics **measured rather than
argued**: a DOM system pays `load + N_states × parse + N_steps × lookup`; a
grounder pays `load + N_steps × inference`. Test suites revisit the same
screens constantly, which is the regime the comparison is about.

---

## 6. Test plan

### Measured: the full comparison (rented RTX 4090, 2026-10-26)

One machine, one commit (`a4cb85e`), 514 steps over 44 states. Raw files:
`benchmarks/results/gpu-20261026_040622/` (gitignored; keep the tarball).
The run kit is `deploy/gpu/`.

| Column | Weights | Action-hit | Verify acc | False-pass (of 301 verifies) | Cost |
|---|---|---|---|---|---|
| `vizdom-uied` | CV, no LLM | 0.779 | 0.934 | **0.000** | load 6.4 s + parse **0.85 s/state** |
| `vizdom-omniparser` | CV + Florence-2 | 0.883 | 0.934 | **0.000** | load 12.7 s + parse **2.21 s/state** |
| `vizdom-modular` | CV, captioner off | 0.732 | 0.934 | **0.000** | load 10.0 s + parse 1.29 s/state |
| `elam-7b` | bf16 | **0.939** | 0.701 | 0.289 (87 of 88 negatives passed) | **5.15 s/step** |
| `ui-tars-1.5-7b` | bf16 | **0.934** | 0.807 | 0.193 (58 of 88 negatives passed) | **1.68 s/step** |
| `ui-tars-1.5-7b` | 4-bit (2026-10-25) | 0.845 | 0.797 | 0.199 | 1.76 s/step |
| `aria-ui` | — | not run | | | 25 B MoE, bf16 only (~50 GB): bnb leaves the experts unquantized, OOM on 24 GB; needs an 80 GB card |

Interpretation, column by column:

- **Action-hit.** The end-to-end grounders win by 5–6 points over
  OmniParser-VizDOM (0.939 / 0.934 vs 0.883) and by 16 over UIED-VizDOM.
  Our misses are resolution misses: the locator finds 0 or 2+ matches on a
  fragmented or merged element; the grounders have no such failure mode.
  Quantization matters for UI-TARS (+9 points from 4-bit to bf16).
- **Verify / false-pass — the testing row.** Both grounders say `PASSED` to
  statements about elements that are *not on the screen*: ELAM accepts 87 of
  the 88 negative statements (its native verdict mode rationalises the
  nonsense label into a nearby element), UI-TARS 58 of 88 (it grounds
  whatever it is asked to ground). VizDOM's 20 verify errors are all the
  other direction — a present caption the OCR cannot read, so the oracle
  says `FAILED` on a true statement — and it never passes an absent target,
  by construction of the exactly-one resolution contract. For a test oracle
  the false-pass column is the one that matters, and it is 0 vs 0.19–0.29.
- **Cost.** Per step, amortised over this suite: VizDOM-OmniParser spends
  110 s in total (load + 44 parses) for 514 steps, i.e. ~0.2 s/step; UI-TARS
  spends 1.68 s on every step (863 s), ELAM 5.15 s (2 650 s). The DOM systems
  pay once per screen state; the grounders pay once per step, and a test
  suite revisits the same states constantly.
- **Modular vs monolith.** The modular backend (same YOLO regions, same
  OCR, same fusion port, captioner off) is 15 points behind OmniParser on
  action-hit, and the gap is exactly 32 steps, all `2 matches`, all on
  `form_sidebar`/`login` input fields with a value (`text="Online"`). Cause:
  `modular_backend` emits absorbed OCR as the field's `text`, while the
  monolith adapter emits it as `label` (`text=None`). The pipeline's own OCR
  then adds the value as a separate text element in both cases, so the
  modular DOM has two elements with `text="Online"` (field + value) and the
  exactly-one contract refuses to click; the monolith DOM has one. Verified
  by diffing both DOMs on `form_sidebar_0007` locally. Not the captioner:
  the toolbar family, where captions matter, scores the same for all three
  VizDOM columns. **Fixed after this run** (pipeline Step 6b2, ADR-010): a
  text element inside a control that carries the same literal is dropped.
  Re-run on the laptop with the fix, `vizdom-modular` and
  `vizdom-omniparser` are step-identical on all 514 steps (action-hit
  0.916, verify 0.957, false-pass 0.000), with modular parsing at 62 % of
  the monolith's time (3.1 vs 5.0 s/state). The 0.732 above is what commit
  `a4cb85e` produced; the next GPU run will carry the corrected column.

Numbers drift slightly with the environment (easyocr, torch and OpenCV
versions): the same VizDOM columns on the laptop gave uied 0.803 / omniparser
0.916, verify 0.957 — always quote the commit and the machine.

### Not run: Aria-UI

Aria-UI (25.3 B MoE) does not fit a 24 GB card even in 4-bit (OOM at shard
5/12, measured 2026-10-26; bitsandbytes leaves the expert weights in bf16,
and the allocation rate extrapolates to ~53 GB, beyond a 48 GB card too).
The column runs bf16, the model card's recipe, and needs an 80 GB rental
(A100 80 GB / H100). The adapter is implemented and preflight-tested up to
the load step; the column is cited from published numbers until that run is
paid for. Plan (2026-10-26): one 80 GB run of the full sweep once the
pipeline is frozen, which also refreshes `vizdom-modular` after Step 6b2.

### Planned extensions (in priority order)

1. **Real-application states** in the same schema (the headline caveat).
2. **`desc=` per-tier accuracy** as an additional locator column
   (auto-generated descriptions per labelled element).
3. **Defect injection**: mutate a state (shift a button, change a caption) and
   measure whether the suite *catches* it — mutation testing for GUI
   automation; the false-pass machinery already supports it.
4. **Hierarchy axis** once tree-bearing ground truth exists (register D-01).

---

## 7. Reproducing and extending

```bash
# regenerate the step set (deterministic; only needed after GT changes)
python -m visual_dom.evaluation.lifecycle.generate

# run executors (comma list); results land in benchmarks/results/<timestamp>.{json,md}
python -m visual_dom.evaluation.lifecycle.runner --executors vizdom-uied,vizdom-omniparser
python -m visual_dom.evaluation.lifecycle.runner --executors elam-7b --limit-states 10

# per-stage evaluation (detection/OCR/type metrics)
python -m visual_dom.evaluation.cli --help
```

Every result file records the dataset id, the git commit, and per-step
outcomes — keep the JSON when quoting a number in the report.

**Adding states**: drop `image + label` pairs into a labels/images pair and
regenerate; real applications can be captured with
`CaptureStrategy.capture_window` and annotated with the tooling under
`scripts/annotation/`.

**Adding an executor**: DOM-based systems get a `VizDomExecutor(detector=...)`;
grounding models implement the two-method `Grounder` interface
(`ground(image, instruction) → (x, y)`, `judge(image, statement) → verdict`)
in `src/visual_dom/evaluation/lifecycle/grounders.py` — adapters stay thin
prompt-and-parse shims, and `available()` must say honestly whether the model
can run here.

The harness itself is under test: `tests/unit/test_lifecycle_bench.py` pins the
generator's contract (uniqueness, negatives, determinism) and the scoring
semantics, so benchmark bugs don't masquerade as model results.
