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
   - a *description* for VizDOM's `desc=` tier chain (ADR-022): `Save button`
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

Every step carries the same intent in **three forms** derived from one
caption — locator, instruction, description — which is what makes parser-based
systems, VizDOM's own language tier and per-step grounding models directly
comparable: each receives the task in its native input form and is scored on
the same outcome, and none gets information the others lack.

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
        VizDomDescExecutor (per tier chain)
        ─ same DOM; per STEP: resolve the step's
          description through the desc= chain
          (lexical / SLM over DOM / VLM Set-of-Mark,
          one Ollama call per model tier), fresh
          resolver per step ..... timed as "resolution"
          action → chosen element's centre
          verify → confident resolution = PASSED
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
| (`desc=` columns) **Resolved by tier** | how many steps each tier of the chain answered (`none` = no confident match) | the per-tier resolution rate ADR-022 promised to report |
| (grounders) **Inference / step** | one model call per step | the cost model being compared against |

The cost columns make the parse-once economics **measured rather than
argued**: a DOM system pays `load + N_states × parse + N_steps × lookup`; a
grounder pays `load + N_steps × inference`. Test suites revisit the same
screens constantly, which is the regime the comparison is about.

---

## 6. Test plan

### Measured: the full comparison (rented RTX 6000 Ada 48 GB, 2026-10-26)

One machine, one commit (`82f0b45`, which includes the Step 6b2 fix), 514
steps over 44 states. Raw files: `benchmarks/results/gpu-20261026_212923/`
(gitignored; keep the tarball). The run kit is `deploy/gpu/`. Full analysis
with charts and the test configuration: `benchmarks/report_gpu_20261026_run3.html`
(run 2, with the modular root cause: `benchmarks/report_gpu_20261026.html`).

| Column | Weights | Action-hit | Verify acc | False-pass (of 301 verifies) | Cost |
|---|---|---|---|---|---|
| `vizdom-uied` | CV, no LLM | 0.822 | 0.934 | **0.000** | load 2.6 s + parse **0.39 s/state** |
| `vizdom-omniparser` | CV + Florence-2 | 0.883 | 0.934 | **0.000** | load 8.1 s + parse **1.02 s/state** |
| `vizdom-modular` | CV, captioner off | 0.883 | 0.934 | **0.000** | load 4.2 s + parse **0.62 s/state** |
| `elam-7b` | bf16 | **0.930** | 0.704 | 0.286 (86 of 88 negatives passed) | **4.00 s/step** |
| `ui-tars-1.5-7b` | bf16 | **0.944** | 0.801 | 0.199 (60 of 88 negatives passed) | **2.72 s/step** |
| `aria-ui` (run 3a, 96 GB card) | bf16 | **0.962** | 0.708 | 0.292 (88 of 88 negatives passed) | **1.57 s/step** (other host) |

Run history, same 514 steps (action-hit / verify acc / false-pass):

| Run | Card, commit | uied | omniparser | modular | elam-7b | ui-tars-1.5-7b | aria-ui |
|---|---|---|---|---|---|---|---|
| 1, 2026-10-25 | RTX 4090, commit not recorded | 0.779 / 0.934 / 0 | 0.883 / 0.934 / 0 | — | 0.0 (prompt bug, rescored 0.916) | 4-bit: 0.845 / 0.797 / 0.199 | — |
| 2, 2026-10-26 | RTX 4090, `a4cb85e` | 0.779 / 0.934 / 0 | 0.883 / 0.934 / 0 | 0.732 / 0.934 / 0 | 0.939 / 0.701 / 0.289 | 0.934 / 0.807 / 0.193 | OOM (4-bit, 24 GB) |
| 3, 2026-10-26 | RTX 6000 Ada, `82f0b45` | 0.822 / 0.934 / 0 | 0.883 / 0.934 / 0 | 0.883 / 0.934 / 0 | 0.930 / 0.704 / 0.286 | 0.944 / 0.801 / 0.199 | skipped (gate) |
| 3a, 2026-10-26 | RTX PRO 6000 Blackwell 96 GB, `411873c` | — | — | — | — | — | 0.962 / 0.708 / 0.292 |

Run 3a is the Aria-UI column alone (`ONLY="aria-ui"`), same manifest and
adapter, on a second rental two hours after run 3; raw files in
`benchmarks/results/gpu-20261026_233909/`. Its accuracy is comparable with
the run 3 rows; its latency is from another card and host.

Interpretation, column by column:

- **Action-hit.** The end-to-end grounders win over OmniParser-VizDOM:
  Aria-UI by 8 points (0.962 vs 0.883), UI-TARS and ELAM by 5–6 (0.944 /
  0.930), and all three by 11–14 over UIED-VizDOM. Our misses are
  resolution misses: the locator finds 0 or 2+ matches on a fragmented or
  merged element; the grounders have no such failure mode. Quantization
  matters for UI-TARS (+9 points from 4-bit to bf16, run 1 vs 2).
- **Verify / false-pass — the testing row.** All three grounders say
  `PASSED` to statements about elements that are *not on the screen*:
  Aria-UI accepts all 88 negative statements (it returns a point for
  everything it is asked), ELAM 86 of 88 (its native verdict mode
  rationalises the nonsense label into a nearby element), UI-TARS 60 of 88.
  VizDOM's 20 verify errors are all the other direction — a present caption
  the OCR cannot read, so the oracle says `FAILED` on a true statement — and
  it never passes an absent target, by construction of the exactly-one
  resolution contract. For a test oracle the false-pass column is the one
  that matters, and it is 0 vs 0.20–0.29; the best clicker is the worst
  oracle.
- **Cost.** Per step, amortised over this suite: VizDOM-OmniParser spends
  53 s in total (load + 44 parses) for 514 steps, i.e. ~0.1 s/step, the
  modular backend 31 s; UI-TARS spends 2.72 s on every step (1 400 s), ELAM
  4.00 s (2 055 s), Aria-UI 1.57 s (826 s, on the faster 96 GB card with
  3.9 B active parameters per token). The DOM systems pay once per screen
  state; the grounders pay once per step, and a test suite revisits the
  same states constantly.
- **Modular vs monolith.** In run 2 the modular backend (same YOLO regions,
  same OCR, same fusion port, captioner off) was 15 points behind OmniParser
  on action-hit, and the gap was exactly 32 steps, all `2 matches`, all on
  `form_sidebar`/`login` input fields with a value (`text="Online"`). Cause:
  `modular_backend` emits absorbed OCR as the field's `text`, while the
  monolith adapter emits it as `label` (`text=None`). The pipeline's own OCR
  then adds the value as a separate text element in both cases, so the
  modular DOM had two elements with `text="Online"` (field + value) and the
  exactly-one contract refused to click; the monolith DOM had one. Verified
  by diffing both DOMs on `form_sidebar_0007`. Not the captioner: the
  toolbar family, where captions matter, scores the same for all three
  VizDOM columns. **Fixed** (pipeline Step 6b2, ADR-010): a text element
  inside a control that carries the same literal is dropped. Run 3 confirms
  it on the GPU: exactly those 32 steps flipped `2 matches` → `resolved`,
  `vizdom-modular` and `vizdom-omniparser` are step-identical on all 514
  steps, and modular parses in 61 % of the monolith's time (0.62 vs
  1.02 s/state). The same fix lifted UIED by 9 steps (0.779 → 0.822): UIED's
  own text-into-component merge produced the same field+value duplicate on
  `form_sidebar_0031/0103` and `login_0137`.
- **Run-to-run stability.** Between runs 2 and 3 (different card, same
  steps) the OmniParser column changed on 0 of 514 steps and every VizDOM
  change is accounted for by the fix. The grounders moved on their own even
  with greedy decoding: ELAM on 3 steps, UI-TARS on 6 (bf16 kernels differ
  between GPU generations), i.e. ±1 point of noise on their numbers.

Numbers drift slightly with the environment (easyocr, torch and OpenCV
versions): the same VizDOM columns on the laptop gave uied 0.803 / omniparser
0.916, verify 0.957 — always quote the commit and the machine. Per-step
latencies of the grounders also depend on the box (ELAM 5.15 → 4.00 s,
UI-TARS 1.68 → 2.72 s from the 4090 to the 6000 Ada host).

### Aria-UI: measured on a 96 GB card (run 3a)

Aria-UI (25.3 B MoE) does not fit a 24 GB card even in 4-bit (OOM at shard
5/12, measured 2026-10-26; bitsandbytes leaves the expert weights in bf16,
and the allocation rate extrapolates to ~53 GB, beyond a 48 GB card too), so
the column runs bf16, the model card's recipe, behind a 70 GB gate. Run 3
(RTX 6000 Ada 48 GB) was skipped by the gate as designed; the same night a
second rental on an RTX PRO 6000 Blackwell (96 GB, commit `411873c`) ran the
column alone in 14 minutes: shards loaded in 6 s, the whole model on the
GPU, 1.57 s per step. Result: action-hit 0.962 (205 of 213, the best of all
columns; misses are five form_sidebar fields, one table control and two
toolbar buttons that OCR cannot read either), verify 0.708, false-pass
0.292 — it returned a point for every one of the 301 statements, so all 88
absent targets passed. The opt-in CPU-offload path for 40–70 GB cards is
implemented but still unexercised (the card was above the gate).

### Prepared, not yet run: the `desc=` columns (run 4)

The six columns above resolve VizDOM steps with `text=` only, so the table
compares *VizDOM without its language tier* against grounders that are all
language tier — and VizDOM's zero false-pass rate is partly structural, since
a nonsense caption can never match OCR output. The `desc=` columns close that
gap. Each step now also carries a description derived from the same caption
(`Save button`, `Remember me checkbox`, `Warp Cores button` for the
negatives), and `vizdom-<detector>+desc` resolves it through the ADR-022 tier
chain behind `Get Visual Element  desc="..."`, over the same parse-once DOM as
`vizdom-modular`. The chain is pinned per column (`--grounding-tiers`):

| Column | Chain | Question it answers |
|---|---|---|
| `vizdom-modular+desc[lexical+slm]` | production default | what `desc=` gives a test author today, and how often each tier answers |
| `vizdom-modular+desc[slm]` | text LM over the DOM table | can a 3B text model pick the element from the DOM alone |
| `vizdom-modular+desc[vlm]` | VLM Set-of-Mark over the screenshot | the head-to-head with the grounders: both resolve language, VizDOM by choosing among its DOM candidates, the grounders by regressing a point |

Expectations to test, not claims: action-hit should sit between the `text=`
column (0.883) and the grounders, because the DOM candidates already contain
the right element in ≥ 88 % of cases and the model only has to choose; the
false-pass rate is the real question — a model asked "which numbered box is
the *Warp Cores* button" may rationalise one, which is exactly the failure
the grounders show at 0.20–0.29, and the `conf ≥ 0.5` gate in the resolver
is what stands against it. Models: `qwen2.5:3b` and `qwen2.5vl:3b` through
Ollama (the kit installs and pulls them; `deploy/gpu/README.md`). A fresh
resolver is built per step so the production cache cannot answer a verify
step from its action step.

Harness verified locally (laptop, `uied` DOM): the model-free lexical tier
over all 514 steps gives action-hit **0.911** / verify 0.944 / false-pass
0 — already above the `text=` figure for the same DOM (0.822), because token
overlap plus the role word tolerates the OCR noise that an exact `text=`
cannot — and both model tiers ran end to end on state samples through the
laptop's Ollama. The headline numbers will come from the next rental on the
`modular` DOM with the intended 3B models.

### Planned extensions (in priority order)

1. **Real-application states** in the same schema (the headline caveat).
2. **Defect injection**: mutate a state (shift a button, change a caption) and
   measure whether the suite *catches* it — mutation testing for GUI
   automation; the false-pass machinery already supports it.
3. **Hierarchy axis** once tree-bearing ground truth exists (register D-01).

---

## 7. Reproducing and extending

```bash
# regenerate the step set (deterministic; only needed after GT changes)
python -m visual_dom.evaluation.lifecycle.generate

# run executors (comma list); results land in benchmarks/results/<timestamp>.{json,md}
python -m visual_dom.evaluation.lifecycle.runner --executors vizdom-uied,vizdom-omniparser
python -m visual_dom.evaluation.lifecycle.runner --executors elam-7b --limit-states 10

# the desc= column (ADR-022): same DOM, each step resolves its description
# through the pinned tier chain; model tiers need a running Ollama with
# qwen2.5:3b / qwen2.5vl:3b (the runner refuses to start otherwise)
python -m visual_dom.evaluation.lifecycle.runner --executors vizdom-modular+desc --grounding-tiers lexical,slm
python -m visual_dom.evaluation.lifecycle.runner --executors vizdom-modular+desc --grounding-tiers vlm

# per-stage evaluation (detection/OCR/type metrics)
python -m visual_dom.evaluation.cli --help
```

Every result file records the dataset id, the git commit, and per-step
outcomes — keep the JSON when quoting a number in the report.

**Adding states**: drop `image + label` pairs into a labels/images pair and
regenerate; real applications can be captured with
`CaptureStrategy.capture_window` and annotated with the tooling under
`scripts/annotation/`.

**Adding an executor**: DOM-based systems get a `VizDomExecutor(detector=...)`
(`VizDomDescExecutor` for a `desc=` chain); grounding models implement the two-method `Grounder` interface
(`ground(image, instruction) → (x, y)`, `judge(image, statement) → verdict`)
in `src/visual_dom/evaluation/lifecycle/grounders.py` — adapters stay thin
prompt-and-parse shims, and `available()` must say honestly whether the model
can run here.

The harness itself is under test: `tests/unit/test_lifecycle_bench.py` pins the
generator's contract (uniqueness, negatives, determinism) and the scoring
semantics, so benchmark bugs don't masquerade as model results.
