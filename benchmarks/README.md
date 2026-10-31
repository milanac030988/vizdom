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
| `vizdom-uied` (run 7) | CV, no LLM | 0.850 (run 3: 0.822) | 0.957 (0.934) | **0.000** | load 7.2 s + parse **1.1 s/state** (run 3: 2.6 s + 0.39 s on the Ada) |
| `vizdom-omniparser` (run 7) | CV + Florence-2 | 0.916 (0.883) | 0.957 (0.934) | **0.000** | load 14.7 s + parse **3.0 s/state** (run 3: 8.1 s + 1.02 s) |
| `vizdom-modular` (run 7) | CV, captioner off | 0.916 (0.883) | 0.957 (0.934) | **0.000** | load 12.2 s + parse **1.9 s/state** (run 3: 4.2 s + 0.62 s) |
| `vizdom-modular+desc[lexical+slm]` (run 7) | + qwen2.5:3b via Ollama | **0.958** (run 6: 0.934) | **0.973** (0.964) | **0.000** (0 of 88; run 4, before the shortlist fix: 0.003) | parse + 0.2 ms median resolve (SLM called on 106 steps) |
| `vizdom-modular+desc[slm]` (run 7, plain prompt) | qwen2.5:3b over the DOM table | 0.639 | 0.877 | 0.017 (5 of 88; run 6 with the explanatory prompt: 0.126, see below) | parse + **0.60 s/step** |
| `vizdom-modular+desc[vlm]` (run 6) | qwen2.5vl:3b Set-of-Mark | 0.113 | 0.203 | 0.043 (13 of the 30 negatives the VLM answered; 394 of 514 steps errored) | parse + 0.28 s per answered call |
| `vizdom-modular+desc[lexical+vlm]` (run 6) | qwen2.5vl:3b Set-of-Mark behind the lexical shortlist | 0.925 | 0.714 | 0.057 (17 of the 30 negatives the VLM answered; 58 more errored) | parse + **0.04 s/step** (0.6 s per answered VLM call; 80 of 116 calls lost to Ollama HTTP 500) |
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
| 4, 2026-10-27 | RTX PRO 5000 Blackwell 48 GB, `3fb0924` | — | — | 0.883 / 0.934 / 0 (control) + `desc=` columns, see below | — | — | — |
| 5, 2026-10-27 | RTX PRO 5000 Blackwell 48 GB, `c03c438` | — | — | 0.883 / 0.934 / 0 (control); `desc=` lexical+slm reproduced run 4 on 514 of 514; lexical+vlm 0.930 / 0.691 / 0.113, see below | — | — | — |
| 6, 2026-10-27 | RTX 6000 Ada, `ca1f0f7` | 0.822 / 0.934 / 0 | 0.883 / 0.934 / 0 | 0.883 / 0.934 / 0 (all three bit-identical to run 3); `desc=` lexical+slm **0.934 / 0.964 / 0** after the shortlist fix, see below | 0.930 / 0.704 / 0.286 (bit-identical to run 3) | 0.944 / 0.801 / 0.199 (bit-identical to run 3) | skipped (gate) |
| 7, 2026-10-28 | RTX A6000, `c6b8e72`, **Tesseract present** | **0.850 / 0.957 / 0** | **0.916 / 0.957 / 0** | **0.916 / 0.957 / 0**; `desc=` lexical+slm **0.958 / 0.973 / 0**; slm-only 0.639 / 0.877 / 0.017 (plain prompt); + the stage ablation (sec. 7) | not rerun (bit-identical twice) | not rerun | — |

Run 6 is the full default sweep after the shortlist fix, on the run-3 card
model (`ca1f0f7`, 2026-10-27 22:47 UTC, 72 minutes of sweep). Every control
and grounder column reproduced run 3 on 514 of 514 steps, outcome *and*
per-step detail, so the run-3 rows above stand as reproduced; the four
`desc=` columns are the ones that moved. Raw files in
`benchmarks/results/gpu-20261027_224706/` (an 18 MB tarball, the first that
carries every parsed DOM under `<stamp>-doms/`).

Run 7 (`c6b8e72`, 2026-10-28 12:08 UTC, RTX A6000 49 GB, 31 minutes) is the
VizDOM columns alone after the stage ablation (sec. 7) found that the OCR
stage's Tesseract retry had never run on a Linux host: `gpu.txt` now records
`tesseract 5.3.4`. Every VizDOM column gained six or seven hits and lost
none against run 6 (499–501 of 514 steps identical per column), the gains
being the captions the second engine reads; the SLM-only row was re-measured
with the restored plain prompt. The grounder columns were not rerun: they
reproduced bit for bit on the Ada card twice and the OCR change cannot
touch them. The main table above quotes run 7 for the VizDOM rows with the
run-3 / run-6 figures in parentheses; raw files in
`benchmarks/results/gpu-20261028_120820/`.

Run 3a is the Aria-UI column alone (`ONLY="aria-ui"`), same manifest and
adapter, on a second rental two hours after run 3; raw files in
`benchmarks/results/gpu-20261026_233909/`. Its accuracy is comparable with
the run 3 rows; its latency is from another card and host. Run 4 is the
`desc=` columns with `vizdom-modular` as the control, which reproduced run 3
on all 514 steps; raw files in `benchmarks/results/gpu-20261027_062331/`.
Run 5 is the vision tier behind the lexical shortlist (`lexical,vlm`), with
the control and the production chain re-run on a second rental of the same
card model; both reproduced run 4 step for step; raw files in
`benchmarks/results/gpu-20261027_111610/`.

Interpretation, column by column:

- **Action-hit.** On the run-3 host the end-to-end grounders won over
  OmniParser-VizDOM: Aria-UI by 8 points (0.962 vs 0.883), UI-TARS and ELAM
  by 5–6 (0.944 / 0.930), and all three by 11–14 over UIED-VizDOM. With the
  second OCR engine in place (run 7) the gap is 4.6 points to Aria-UI and
  1.4–2.8 to UI-TARS and ELAM for the `text=` rows, and the `desc=` chain
  (0.958) is above both 7B grounders. Our misses are resolution misses: the
  locator finds 0 or 2+ matches on a fragmented or merged element (run 7's
  18 modular misses: the `Search...` placeholder whose dots OCR drops ×8,
  repeated table digits ×4, `APAC\USER01` ×3, three others); the grounders
  have no such failure mode. Quantization matters for UI-TARS (+9 points
  from 4-bit to bf16, run 1 vs 2).
- **Verify / false-pass — the testing row.** All three grounders say
  `PASSED` to statements about elements that are *not on the screen*:
  Aria-UI accepts all 88 negative statements (it returns a point for
  everything it is asked), ELAM 86 of 88 (its native verdict mode
  rationalises the nonsense label into a nearby element), UI-TARS 60 of 88.
  VizDOM's 20 verify errors (13 in run 7) are all the other direction — a present caption
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

### Measured: the `desc=` columns, VizDOM's language tier (runs 4 and 5, 2026-10-27)

The six columns above resolve VizDOM steps with `text=` only, so they
compare *VizDOM without its language tier* against grounders that are all
language tier — and VizDOM's zero false-pass rate is partly structural, since
a nonsense caption can never match OCR output. Run 4 closes that gap. Each
step also carries a description derived from the same caption (`Save
button`, `Remember me checkbox`, `Warp Cores button` for the negatives), and
`vizdom-modular+desc` resolves it through the ADR-022 tier chain behind
`Get Visual Element  desc="..."`, over the same parse-once DOM as
`vizdom-modular`, with a fresh resolver per step so the production cache
cannot answer a verify step from its action step. The chain is pinned per
column (`--grounding-tiers`); models `qwen2.5:3b` and `qwen2.5vl:3b` through
Ollama. Measured three times: run 4 (RTX PRO 5000 Blackwell 48 GB, commit
`3fb0924`, 11 minutes of sweep, raw files
`benchmarks/results/gpu-20261027_062331/`), run 5 (same card model,
`c03c438`, the lexical+vlm chain) and run 6 (RTX 6000 Ada, `ca1f0f7`, the
resolver after the shortlist fix, all four chains inside the full sweep,
`benchmarks/results/gpu-20261027_224706/`). In every run the
`vizdom-modular` control column reproduced run 3 on 514 of 514 steps. The
table quotes run 6 and keeps the earlier row of each column underneath it.

| Column | Chain | Action-hit | Verify | False-pass | Resolved by tier | Resolve / step |
|---|---|---|---|---|---|---|
| `vizdom-modular+desc[lexical+slm]` (run 6) | production default | **0.934** (199) | **0.964** | **0.000** (0 of 88) | lexical 398, slm 6, none 110 | 0.0001 s median, 0.03 s mean (18 s for 514 steps) |
| same, run 4 (before the shortlist fix) | | 0.930 (198) | 0.954 | 0.003 (1 of 88) | lexical 398, slm 3, none 113 | 0.03 s mean (16 s) |
| `vizdom-modular+desc[lexical+slm]` (run 7, Tesseract present) | production default | **0.958** (204) | **0.973** | **0.000** (0 of 88) | lexical 408, slm 2, none 104 | 0.2 ms median |
| `vizdom-modular+desc[slm]` (run 7, plain prompt restored) | 3B text LM over the DOM table | 0.639 (136) | 0.877 | **0.017** (5 of 88) | slm 365, none 149 | 0.60 s |
| `vizdom-modular+desc[slm]` (run 6, explanatory prompt) | 3B text LM over the DOM table | 0.667 (142) | 0.867 | 0.126 (38 of 88) | slm 459, none 55 | 0.19 s |
| same, run 4 (plain prompt) | | 0.634 (135) | 0.877 | 0.020 (6 of 88) | slm 372, none 142 | 0.21 s |
| `vizdom-modular+desc[vlm]` (run 6) | 3B VLM, Set-of-Mark over the screenshot | 0.113 (24) | 0.203 | 0.043 (13 of 88) | vlm 101, none 19, **error 394** | 0.28 s per answered call |
| same, run 4 | | 0.117 (25) | 0.365 | 0.076 (23 of 88) | vlm 113, none 401 (the same outage, recorded as "none") | 0.49 s |
| `vizdom-modular+desc[lexical+vlm]` (run 6) | the VLM behind the lexical shortlist, as in production | 0.925 (197) | 0.714 | 0.057 (17 of 88) | lexical 398, vlm 23, none 13, **error 80** | 0.6 s per answered VLM call |
| same, run 5 | | 0.930 (198) | 0.691 | 0.113 (34 of 88) | lexical 398, vlm 40, none 8, error 68 | 0.83 s per VLM call |

What the rows say:

- **The production chain beats `text=` on the same DOM and keeps the
  oracle.** 198 hits against 188: eleven gained, one lost. Every gain is an
  OCR-noisy caption that exact text cannot match but token overlap plus the
  role word can — the placeholder `Search...` (OCR drops the dots; seven
  steps), the path-like values `APAC\USER01` and `C:\Users\admin` (partial
  overlap, scores 1.7–2.6). The loss is one table digit (`2 button`, where
  the lexical margin between repeated digits is zero). Verify follows the
  same pattern, 0.954 against 0.934. Action-hit now equals ELAM's 0.930 and
  false-pass stays at 1 of 88 against the grounders' 60–88: the SLM, asked
  about `Purple Elephant button` on `dialog_0141`, rationalised it onto the
  *Retry* button at confidence 0.85. The other 87 negatives it declined.
  Root cause (diagnosed 2026-10-28, reproduced byte for byte with the same
  model on the laptop): the dialog's other button, *Cancel*, is one of the
  nine captions OCR never read, so the lexical ranking left exactly one
  scored element and the SLM was handed a **one-row table**. With one row,
  "which of these matches?" becomes "is this it?", and the 3B model says
  yes to a plausible-sounding name; with two or more rows it declines on
  the same dialog and the same phrase. Fixed in the resolver: the model
  tiers' shortlist is padded from the pool to at least three candidates; the
  runner now also keeps every parsed DOM in the tarball (`<stamp>-doms/`),
  which is what this diagnosis was missing. **Run 6 confirms the fix**: the
  same step now ends `lexical: best score 1.00 < 1.5; slm not confident
  (0.00)`, the chain passes none of the 88 negatives, and nothing else got
  worse (509 of 514 outcomes identical to run 4, the other five all gains).
  The padded shortlist let the SLM answer 6 of its 116 calls instead of 3:
  one new hit (`settings_0042` *Save*, whose caption OCR read as a single
  letter), its verify twin, and `dialog_0141` *Cancel* (the unread caption
  itself), which the SLM resolved to the dialog's `×` icon — the wrong
  element, so the action step stays a miss, while the verify step counts as
  correct because a positive verify only asks whether *some* element was
  confidently resolved. That is a limit of the verify-pos scoring worth
  knowing: a wrong-element pass on a true statement is invisible to it (the
  action-hit column is what catches it). So 0.934 / 0.964 / 0.000: the chain
  beats `text=` by eleven hits, verifies best of the table, and is an oracle
  again on the same terms as `text=`. **Run 7 (Tesseract present, sec. 7)
  lifts the chain to 0.958 / 0.973 / 0.000**: six more hits (`Confirm`,
  `Cancel`, three `Save`s and two value fields whose captions the second
  OCR engine now reads), one loss (`form_sidebar_0015` *admin*), 499 of 514
  steps identical to run 6, still 0 of 88 negatives passed, the lexical tier
  now answering 408 steps and the SLM called on 106. On the same host that
  is above UI-TARS (0.944) and ELAM (0.930) on action-hit as well.
- **The lexical tier does the work; the SLM is a rarely consulted
  tie-breaker.** 398 of 514 steps are answered without a model, at 0.2 ms.
  The SLM is called on the remaining 116 (the 88 negatives plus 28 positives
  where lexical had no confident top) and answers 3, so the whole column costs
  16 s of resolver time on top of the parse. The 13 remaining action misses
  are the OCR floor (nine captions never read at all, so there is no token
  to overlap: `Save` ×3, `Confirm`, `Cancel`, `Download`, three value fields
  on `form_sidebar_0103`) and four repeated table digits. Part of that floor
  was the host, not the screens: the Tesseract retry never ran on the rented
  Linux hosts (sec. 7), and on the laptop with it `Confirm` and `Cancel` are
  read.
- **The SLM alone is a poor grounder.** Over the full DOM table (30–110
  rows) the 3B text model picks a *wrong* element on 49 of its 78 action
  misses, at confidence 1.00, and semantically unrelated (`Prev button` →
  a static text `John Doe`; `Search... input field` → the number `70`); it
  declines on 29. Worst on form_sidebar (33 of 62) and settings (33 of 57),
  fine on toolbar (16 of 17) and login (11 of 12). Its 6 false passes are
  the same rationalisation the grounders show (`Zylophone button` → the
  *Zip Code* button, `Warp Cores button` → the *Time* button, all at 1.00).
  The lexical tier in front of it is what turns this into a 0.930 column:
  it answers the easy 77 % itself and hands the SLM a shortlist of eight.
  **Run 6 made this column worse, and the reason is the prompt, not the
  padding.** With the fix commit's wording ("the description may refer to
  nothing in this list; answer null unless an element's text or role clearly
  corresponds to it; a matching role alone is NOT a match") the column
  passed 38 of 88 negatives at confidence 1.00 (`Frobnicate button` → the
  *Files* button, `Quantum Sync button` → a text field), against 6 with the
  plain run-4 wording; action-hit rose a little (142 against 135) on the same
  steps. Reproduced on the laptop against the same `qwen2.5:3b` with the
  DOMs from the tarball: over the whole-DOM table the explanatory wording
  answers 6 of 6 nonsense captions, the plain wording 1 of 6; over a padded
  3-to-5-row shortlist both decline 6 of 6; three other explanatory
  phrasings behave like the first. A 3B model handed a long table and a rule
  about "text or role" copies the rule into a justification ("role=button
  text='Files'") instead of applying it. The chain never saw this because
  its shortlist is short. The wording is reverted to the plain form in the
  resolver (the padding, which is what fixed the one-row case, stays).
  **Run 7 re-measured the row with the plain prompt: 0.639 / 0.877 /
  0.017**, five false passes of 88 (`Frobnicate button` → a *Save* or
  *Reset* button on three forms, `Warp Cores` and `Zylophone` → the *Time*
  button, all at 0.90–1.00), the run-4 behaviour back to within one step.
  The row is noisy at the step level (34 verify gains and 31 losses against
  run 6) but its false-pass rate is not: 38 with the explanatory wording,
  5 and 6 with the plain one.
- **The VLM-only column measures the harness more than the model.** The
  Set-of-Mark overlay draws at most 20 numbered boxes, in DOM order, and
  the pinned `vlm` chain has no lexical shortlist in front of it, so the
  marks are simply the first 20 elements of a DOM that has a median of 33
  (5 to 112) per state; on the laptop parse only 102 of the 213 action
  targets fall inside the first 20 marks at all. On 30 of the 44 states the
  model returned no usable answer on any step. **Run 6 shows what those 30
  states were: the vision model collapsing into a repeated token (below),
  which the run-4 harness recorded as "no confident match".** Run 6's same column, with the error
  path in place, errored on 394 of 514 steps covering exactly those states
  (`dashboard_0195` to `settings_0050`), and answered the same 14. The
  run-4 figure 0.117 therefore measures mostly the outage, and only then
  the 20-mark cap. On the 14 states where the model did answer (all four
  toolbars, six settings, four dashboards) it answered almost every step,
  hit 25 of 45 actions in run 4 and 24 of 44 in run 6, and passed all 23
  negatives it was asked in run 4 at confidence 0.95–1.00; in run 6, with
  the prompt that says null is expected, it passed 13 of the 30 it was
  asked and declined 17 — within its answered set it still behaves like
  the grounders, a little less so with the explicit null. The intended
  head-to-head therefore did not happen: the tier was built as a
  disambiguator over a short candidate list, and this column asked it to be
  a whole-screen grounder with a 3B model on a 1920×1080 frame. Both
  harness gaps were closed in the kit after run 4: the sweep gained a
  `vizdom-modular-desc-vlm-chain` column (`lexical,vlm`, the vision tier
  behind the lexical shortlist, as in production), a missed step's `detail`
  carries every tier's own verdict (`lexical: tie at 3.00 between 2
  candidates`, `vlm returned out-of-range mark 37`), and a tier that cannot
  reach its model is a step *error*, not a miss.
- **Run 5 puts the vision tier where production puts it, and it fails as
  an oracle.** Second rental of the same card model, commit `c03c438`,
  2026-10-27 11:16 UTC; the control and the lexical+slm column reproduced
  run 4 on 514 of 514 steps, so the row is comparable step for step. The
  `lexical,vlm` chain hands the VLM the 116 steps the lexical tier cannot
  settle, with a shortlist of at most eight marks. Two things happened. For
  two minutes in the middle of the column (11:19:22 to 11:21:13 UTC) Ollama
  answered HTTP 500 to every VLM call, 68 of the 116: 10 actions, 10 positive
  and 48 negative verifies. The new error path records them as errors,
  scored as misses and wrong verdicts, so the row is a partial measurement;
  under the run-4 harness those 48 negatives would have counted as *correct*
  and the column would have looked better than it is. On the 48 calls that
  did go through, the model behaved like the grounders: asked about a
  nonsense caption with a numbered overlay in front of it, it answered a
  mark on 34 of 40 negatives at confidence 0.90–0.99 (22 of them mark #1)
  and declined 6. Of its 4 action answers, 1 hit (`settings_0042` Save,
  mark #6 at 1.00), 2 chose mark #1 for "Save button" and 1 was out of
  range. So the chain keeps the lexical tier's hits (198: one gained, one
  lost to the outage) and loses the oracle: false-pass 0.113 as measured,
  which is also the floor had every errored negative been declined, and
  about 0.25 had they followed the answered rate. The action-side question
  run 5 was meant to settle, whether the VLM recovers the OCR floor of nine
  unread captions and four repeated digits, is still open: 10 of those 14
  steps fell in the outage. The verify-side question is closed: a
  Set-of-Mark tier with a null option is not a usable oracle with this
  model, and `vlm` stays out of the production default (ADR-022).
- **Run 6 repeats the vision chain with the null-aware prompt, and the
  outage repeats with it.** 0.925 / 0.714 / 0.057 with 80 of the 116 VLM
  calls refused (11 actions, 11 positive and 58 negative verifies). On the
  30 negatives it did answer the model passed 17 and declined 13 — 57 %
  against run 5's 85 % with the older prompt, so the wording helps a vision
  model where it hurts the text model, and it is still far from an oracle
  (17 false passes of 30 answered; 14 of them at 0.95, 10 of them mark #1).
  Its three action answers all missed (run 5: one hit in four), and one hit
  was lost to the outage (`settings_0042` *Save*), hence 197 against the
  lexical tier's 199. **The "outage" is the model, not the server.** In
  run 4 (where the harness hid it as "none"), run 5 and both run-6 vision
  columns the first refused call is the eleventh VLM call of the column,
  `dashboard_0195/verify-neg/Antigravity`, and the refusals then cover a
  fixed block of states — `dashboard_0195` to `settings_0050` on the RTX
  6000 Ada host in all three of its columns, 394 and 80 steps alike over
  4.4 and 1.7 minutes, up to `login_0137` on the Blackwell host — after
  which the same server answers again; neither wall time nor call count
  explains a window that ends at the same state in columns making 514 and
  116 calls. Replaying the column's calls on the laptop against the same
  `qwen2.5vl:3b` under Ollama 0.40, with the client now keeping the
  server's reply, names the 500: `prediction aborted, token repeat limit
  reached`, Ollama's guard against a model that loops. On these Set-of-Mark
  prompts the 3B vision model at temperature 0 either answers `{"number":
  null, ...}` or emits `888888…` until the guard aborts it, and which
  prompts collapse depends on the image and on the card's numerics, not on
  the server's state. It is not the context window (2 785 prompt tokens,
  no truncation, the same output at `num_ctx` 8 192 to 32 768), not the
  request path (the same images through a different local vision model
  answer every state in the window), and not the overlay's size or mark
  count (with 8 marks instead of 20, or the image downscaled to 1 280 or
  960 px wide, the same prompts collapse; sampling at temperature 0.3
  collapses into `@@@@…` instead). On the laptop the same prompt answered
  in one session and collapsed in the next, so which inputs are safe is not
  predictable from the input, only observable per card. The next experiment
  is a different vision model (7B, or a small one that does not loop), not
  a different prompt; a client-side token cap would make each collapse
  cheaper but must still be scored as an error, not as a decline. The
  kit discarded Ollama's own log (`ollama serve >/dev/null`); from run 7 on
  the sweep keeps `ollama-serve.log` and every step detail carries the
  server's reason. The lexical+vlm row is therefore a measurement of the
  36 calls the model did not loop on, and the OCR-floor question stays open
  (again 10 of its 14 steps collapsed).
- **Caveat on the descriptions, and a paraphrase check (2026-10-28).** They
  are generated as caption plus role word, which is the lexical tier's ideal
  input; a tester's own wording would exercise the model tiers more and the
  lexical tier less, so the chain's figure is an upper bound for this
  phrasing. To put a number on the gap, every one of the 76 distinct
  descriptions was rewritten by hand in two styles
  (`lifecycle-synthetic-v1/paraphrases.json`): **terse**, what a tester
  types in a hurry (`Save`, `search box`, `the field that says Enabled`,
  `page 1`), and **wordy**, the purpose or the look with the label or the
  role word often dropped (`the button that saves the changes`, `the search
  bar where you type a query`, `the previous-page control of the pager`).
  `python -m visual_dom.evaluation.lifecycle.paraphrase` re-resolves all 514
  steps over the run-6 DOM dumps through the same resolver and the same
  scoring, so the DOM is held fixed and only the wording moves; it also
  reports a *strict* verify-pos that requires the resolved element to be the
  target. Laptop, `qwen2.5:3b` Q4 on a mobile GPU, 2.7 s per SLM call:

  | Wording | Tiers | Action-hit | Verify | False-pass | Strict verify-pos | Resolved by tier |
  |---|---|---|---|---|---|---|
  | generated (`Save button`) | lexical | 0.925 | 0.954 | 0.000 | 0.925 | lexical 398, none 116 |
  | generated | lexical+slm | 0.930 | 0.960 | 0.000 | 0.930 | lexical 398, slm 4, none 112 |
  | terse (`Save`) | lexical | 0.864 | 0.907 | 0.000 | 0.864 | lexical 370, none 144 |
  | terse | lexical+slm | **0.901** | **0.967** | **0.000** | 0.901 | lexical 370, slm 36, none 108 |
  | wordy (`the button that saves the changes`) | lexical | 0.113 | 0.372 | 0.000 | 0.113 | lexical 48, none 466 |
  | wordy | lexical+slm | **0.709** | **0.860** | **0.000** | 0.695 | lexical 48, slm 298, none 168 |

  Three readings. (1) **The oracle property does not depend on the
  wording**: 0 false passes of 88 in every row, including the wordy
  paraphrases of the nonsense captions (`the button that frobnicates the
  record`), all 88 declined by the lexical tier and the SLM alike. (2)
  **Wording that keeps the label costs three points, wording that drops it
  costs twenty-two.** Terse loses six hits to the generated form, mostly
  where the paraphrase removed the only token the DOM has (`page 1` for a
  pager button whose text is `1`) or left the SLM to choose between
  look-alike value fields (`the Connected field` on a form with three status
  boxes). Wordy is where the model tier earns its place: the lexical tier
  alone answers 48 steps and hits 0.113; the SLM behind it lifts that to
  0.709 with 298 answers, and the 62 remaining action misses split into 38
  declines (`the previous-page control of the pager`, `the search bar where
  you type a query`: no token in common with `Prev` or `Search...`) and 24
  wrong elements. (3) **The wrong elements are the SLM's known weakness, now
  visible on the verify side.** The strict column is what the plain verify
  metric hides: on the wordy set 23 positive verifies passed on a *different*
  element than the target, all of them SLM answers, 20 at confidence 0.85–1.00
  (`the first page number in the pagination` → the text `Showing 1-9 of
  204`; `the box whose value is Enabled` → the field reading `Stopped`), the
  same rationalisation the SLM-only column shows over a whole DOM, here over
  an eight-row shortlist whose rows are all plausible. For a test that only
  asserts existence this is a correct verdict on the wrong evidence;
  action-hit and the strict column are the metrics that see it. The
  paraphrases were written by the project's assistant and reviewed by the
  author, not collected from other testers; descriptions by other people
  remain the stronger version of this check. The rows are measured on the
  resolver after the 2026-10-28 review fixes (ADR-022 1.5): the first pass
  had one *lexical* wrong-element pass in the wordy set, `the button that
  checks for updates right now` resolved on role plus the position word
  `right` at 1.50 to another button; role and position words now earn half
  credit when the description names something the element does not carry,
  so that step declines, and the position filter runs before the shortlist
  is padded. The second round of the review found the opposite error on the
  same phrase: `right` in `right now` was read as a position and filtered
  all four *Check Now* targets (cx 0.06–0.26) out of the model's shortlist,
  eight guaranteed misses from the parser, not the model. A position word
  now counts only inside a positional phrase (`on the right`, `top left`,
  `right side`, `left button`), and all four states hit; a third round
  made a position word that follows a naming word part of the caption
  (`Align Left button`), which touches no benchmark description. The
  generated and terse rows did not move through any round. Two measurements of the
  wordy chain on the same code also differ on 11 of 514 steps (the laptop
  model's answers are not bit-stable between runs at temperature 0, mostly
  verify steps flipping between a wrong-element pass and a decline), so the
  wordy row is good to about ±1 point; the GPU-measured columns above
  reproduced bit for bit.

Cost on this host: the modular parse took 1.26 s per state (run 3: 0.62 s on
the RTX 6000 Ada host; this card's CPU side is slower), so the chain column
amortises to about 0.16 s per step including its 16 s of resolver time,
against 1.57–4.00 s for the grounders. Per-step latency of the model-only
columns is the Ollama call: 0.21 s for the 3B text model, 0.49 s for the 3B
VLM with the image. In run 5 the lexical+vlm chain spent 40 s on resolution
(0.83 s per answered VLM call, with the overlay image attached) on top of a
1.34 s parse, about 0.21 s per step amortised; the production chain
reproduced its run-4 cost. Run 6, on the run-3 host, puts the production
chain on the same footing as the `text=` rows: 4.2 s load, 44 parses at
0.63 s and 18 s of resolver time, **0.10 s per step** for the whole suite,
against the grounders' 2.79–4.24 s median step on that host that night
(UI-TARS 1 433 s, ELAM 2 110 s for the same 514 steps).

### Planned extensions (in priority order)

1. **Real-application states** in the same schema (the headline caveat).
2. **Defect injection**: mutate a state (shift a button, change a caption) and
   measure whether the suite *catches* it — mutation testing for GUI
   automation; the false-pass machinery already supports it.
3. **Hierarchy axis** once tree-bearing ground truth exists (register D-01).

---

## 7. Ablation: what each stage of VizDOM's own pipeline adds

The columns above compare detectors and grounders. This table holds the
detector fixed (modular, captioner off, the run-3 control) and turns one
stage of VizDOM's own code off at a time through the session config, the
runner's column spec `vizdom-modular[roles=off]`
(`visual_dom.evaluation.lifecycle.ablation`, 2026-10-28: first on the
laptop, then as the `ablation` column of run 7 on the RTX A6000, where every
accuracy figure reproduced to three decimals; the table quotes run 7, whose
parse times are the A6000's). Every column is
scored on both levels: the lifecycle metrics say what the stage is worth to
a test suite, the per-stage metrics (detection F1 / recall / mean IoU, OCR
character accuracy, and per GT type *found* = matched by any box, *typed* =
matched by a box of the right role) say what it does to the DOM.

| Column | What is off | Action-hit | Verify | False-pass | Parse s/state | F1 | Recall | mIoU | Char acc | Typed button / input / checkbox |
|---|---|---|---|---|---|---|---|---|---|---|
| `modular` (control) | nothing | **0.915** | **0.957** | 0.000 | 1.89 | 0.638 | 0.632 | 0.688 | 0.975 | 0.91 / 0.99 / 0.00 |
| `[roles=off]` | role recovery (slide 23) | 0.915 | 0.957 | 0.000 | 1.89 | 0.638 | 0.632 | 0.688 | 0.975 | **0.00 / 0.00 / 0.00** |
| `[labels=off]` | label association (ADR-016) | 0.915 | 0.957 | 0.000 | 1.91 | 0.638 | 0.632 | 0.688 | 0.975 | 0.91 / 0.99 / 0.00 |
| `[symbols=off]` | glyph reader (ADR-011) | 0.915 | 0.957 | 0.000 | 1.86 | 0.638 | 0.632 | 0.688 | 0.975 | 0.91 / 0.99 / 0.00 |
| `[merge=off]` | smart merge (ADR-010) | 0.915 | 0.957 | 0.000 | 1.86 | **0.655** | 0.664 | 0.683 | 0.975 | 0.91 / 0.99 / 0.00 |
| `[ocr=plain]` | OCR upscale + Tesseract retry (ADR-012) | **0.859** | **0.930** | 0.000 | 1.15 | 0.607 | 0.598 | 0.687 | 0.947 | 0.89 / 0.99 / 0.00 |
| `[ocr=none]` | OCR entirely | **0.000** | **0.292** | 0.000 | 0.09 | 0.406 | 0.316 | 0.791 | 0.023 | 0.00 / 0.99 / 0.00 |
| `[refiner=on]` | (SLM review ON, ADR-007) | 0.915 | 0.957 | 0.000 | **2.17** | 0.638 | 0.632 | 0.688 | 0.975 | 0.91 / 0.99 / 0.00 |
| `+desc` (control) | nothing, `desc=` chain | **0.958** | **0.973** | 0.000 | 1.93 | same DOM | | | | lexical 408, slm 2, none 104 |
| `[roles=off]+desc` | role recovery, `desc=` chain | **0.944** | 0.964 | 0.000 | 1.93 | same DOM | | | | lexical 402, slm 2, none 110 |
| `[labels=off]+desc` | label association, `desc=` chain | 0.958 | 0.973 | 0.000 | 1.94 | same DOM | | | | lexical 408, slm 2, none 104 |

What the rows say:

- **Language carries the test; the OCR stage is the one that matters most.**
  Without OCR the DOM still boxes every button and input (found 1.00 / 0.99)
  and not one `text=` step resolves: 0.000 action-hit, and the 0.292 verify
  accuracy is the 88 negatives failing for the right reason. Plain OCR, one
  engine at native resolution, costs 12 hits and 8 verifies against the
  ADR-012 pair (upscale to 1500 px, Tesseract re-read of easyocr's
  low-confidence boxes): character accuracy 0.947 against 0.975, 28 captions
  recovered, among them `Confirm` on `dialog_0037` and `Cancel` on
  `dialog_0141`.
- **Role recovery is invisible to `text=` and visible everywhere else.** The
  lifecycle `text=` steps never read a role, so the row does not move; the
  typed column drops from 0.91 / 0.99 to 0 / 0 (every control is `icon`
  again, as OmniParser tags it), and under the `desc=` chain the role word in
  the description stops scoring: 0.958 → 0.944, six fewer lexical
  resolutions. `role=` locators, the `clickable` / `editable` flags and the
  Viewer's tree are the other consumers.
- **Label association, the glyph reader and the refiner change nothing on
  this set.** The benchmark's descriptions name a field by its own text
  (`Online input field`), never by a label beside it; the synthetic screens
  have no glyph-only keys; and the SLM review proposes nothing the rules did
  not already do, at 1.15× the parse time on the A6000 (2.17 s against
  1.89 s per state; 3.2× on the laptop, where the Ollama calls are slower),
  which is why ADR-007 leaves it off. The first two stages were built for
  real screens (the calculator's operator keys, the enterprise form's
  labelled fields on slide 26) that this set does not contain: a zero here is
  "not exercised", not "useless", and the real-application states are what
  would exercise them.
- **Smart merge costs detection F1 on this set and buys nothing a test
  sees.** With it off, F1 rises 0.018 and text recall 0.65 → 0.69: the
  merge fuses text lines the synthetic ground truth keeps separate. It was
  built for OmniParser's split two-line buttons; on clean screens it
  over-merges, which is the parked "over-merge heuristic" item.
- **A host finding.** The control here, 0.915 / 0.957, is above the same
  column's 0.883 / 0.934 on the rented RTX 6000 Ada (runs 3 and 6), and the
  `desc=` chain 0.958 / 0.973 above 0.934 / 0.964. The difference is the
  Tesseract retry: the detector looked for a Windows install only, so on
  every Linux host the retry silently never ran, and `tesseract-ocr` was not
  in the kit's apt list. The lookup now tries PATH first and warns once when
  it finds nothing; the kit installs the binary. **Run 7 (RTX A6000,
  `c6b8e72`, 2026-10-28 12:08 UTC, Tesseract 5.3.4 recorded in `gpu.txt`)
  confirmed it**: every VizDOM column gained six or seven hits and lost
  none, 499–501 of 514 steps identical to run 6 per column, and the gains
  are exactly the captions the retry reads (`Confirm`, `Cancel`, three
  `Save`s, `C:\Users\admin`, `10001`): uied 0.822 → 0.850, omniparser and
  modular 0.883 → 0.916, the chain 0.934 → 0.958, verify 0.934 → 0.957
  everywhere, false-pass 0 throughout. The run-3 and run-6 rows stay quoted
  in the history as measured; the main table carries run 7. The grounder
  rows are unaffected.

Caveats: one laptop, one run per column, and the lifecycle `text=` steps
cannot see roles, labels or glyphs by construction, so the per-stage columns
and the `desc=` rows carry those stages. A real-application set is what
would make the three "no effect" rows informative.

```bash
# one column per process (the parse holds the OCR + detector models in memory)
python -m visual_dom.evaluation.lifecycle.ablation --columns "modular"
python -m visual_dom.evaluation.lifecycle.ablation --columns "modular[ocr=plain]"
python -m visual_dom.evaluation.lifecycle.ablation --columns "modular[roles=off]+desc"
python -m visual_dom.evaluation.lifecycle.ablation --columns "modular[roles=off,ocr=plain]"   # switches combine
python -m visual_dom.evaluation.lifecycle.ablation --report     # merges ablation-*.json -> ablation-report.md
```

The result file is rewritten after every column, and a column that cannot
run (no Ollama for `refiner=on`, every step erroring) is recorded as an
error row and the batch goes on; the driver exits non-zero at the end if any
column failed.

Switches: `roles=off`, `labels=off`, `symbols=off`, `merge=off`, `ocr=plain`,
`ocr=none`, `ensemble=off` (OmniParser backend), `refiner=on`, or any
`section.key=value` of the session config; `+desc` runs the column under
the default `desc=` chain.

---

## 8. Reproducing and extending

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
python -m visual_dom.evaluation.lifecycle.runner --executors vizdom-modular+desc --grounding-tiers lexical,vlm   # the vision tier as production uses it (run 5)

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
