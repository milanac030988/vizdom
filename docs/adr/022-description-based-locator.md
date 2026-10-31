# ADR-022: Description-Based Locator (`desc=`) via Tiered Grounding

## Status

Accepted (Tiers 0–1 implemented and measured, 0.934 / 0.964 / 0.000 on the lifecycle benchmark after the shortlist fix; Tier 2 implemented behind config and measured 2026-10-27: not an oracle, stays opt-in)

## Date

2026-07-30

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-30 | 1.0 | Design + Tiers 0/1 implemented (`desc=` strategy, lexical matcher, SLM-over-DOM resolver, `grounding` config, RF wiring). Tier 2 (VLM Set-of-Mark) implemented behind `grounding.tiers`, disabled by default. |
| 2026-10-27 | 1.1 | Measured on the lifecycle benchmark (`benchmarks/README.md` §6, runs 4–5, 514 steps): default chain lexical→slm 0.930 action-hit / 0.954 verify / 0.003 false-pass (lexical answers 398 of 514, the SLM 3); SLM alone over the whole DOM 0.634; VLM Set-of-Mark alone 0.117 (20-mark cap, harness limit); VLM behind the lexical shortlist keeps the hits (0.930) but passes 34 of the 40 nonsense captions it was shown (false-pass 0.113). Tier 2 stays out of the default chain and must not be used for verification until the prompt has a real null option. Resolver now records every tier's verdict in the miss reason. |
| 2026-10-28 | 1.2 | The one false pass traced to a one-row SLM table (the other button's caption unread → one scored element). Shortlist padded to ≥ 3 candidates; SLM/VLM prompts state that null is expected and a matching role alone is no match. Benchmark runner keeps every parsed DOM. |
| 2026-10-28 | 1.3 | Run 6 (full sweep, `ca1f0f7`): the padding holds — default chain 0.934 / 0.964 / **0.000**, the one-row step declines at 0.00. The explanatory SLM wording of 1.2 is a regression on long tables (SLM-only column 0.020 → 0.126 false-pass; reproduced on the laptop: 6 of 6 nonsense captions answered over the whole DOM, 1 of 6 with the plain wording, 0 of 6 either way over the padded shortlist) and is reverted to the plain "use null if no element matches"; the VLM wording stays (17 of 30 answered negatives passed against 34 of 40). The vision rows' "Ollama 500" steps (68–394 per column, the same block of states per card) are `qwen2.5vl:3b` collapsing into a repeated token on those overlays, aborted by the server's repeat guard — a model failure, recorded as errors. |
| 2026-10-28 | 1.4 | Paraphrase check (`benchmarks/README.md` §6, `paraphrases.json`, `visual_dom.evaluation.lifecycle.paraphrase`): the 514 steps re-resolved over the run-6 DOMs with hand-written wordings. Terse (`Save`, `search box`) 0.901 / 0.967 / 0.000; wordy, label or role word dropped (`the button that saves the changes`) 0.709 / 0.860 / 0.000 — the SLM lifts the wordy set from 0.113 (lexical alone) to 0.709 and answers 24 of 213 actions with a wrong element at 0.85–1.00. The oracle property holds under every wording; the generated-description figure is the upper bound of a 3-to-22-point range (wordy row ±1 point between runs of the laptop model). |
| 2026-10-28 | 1.5 | Review of 1.2–1.4 found that the position-word filter ran *after* the shortlist padding and could hand the model a one-row table again (`top left Purple Elephant button` → a table of `E1` alone), and that the lexical tier resolved such positional nonsense confidently on its own (role 1.0 + two position words 1.0 = 2.0 ≥ 1.5; one real case in the wordy paraphrase set). Fixed: the filter runs inside the shortlist, padding prefers in-place elements, a model answer outside the described position is rejected with its own reason; role and position words earn half credit (capped at 1.0) when the description names something the element does not carry, while position-only descriptions (`the button at the top left`) still resolve. Benchmark rows unchanged for generated and terse wording; wordy re-measured above. |
| 2026-10-28 | 1.6 | Second review round: (a) `right` in `right now` was read as a position (cx > 0.66) and filtered all four *Check Now* targets out of the model's shortlist — eight parser-caused misses in the wordy row. A position word now counts only inside a positional phrase (next to another position word, after a preposition or article, before a part or role word: `on the right`, `top left`, `right side`, `left button`; not `right now`, `right click`); `parse_description()` is the one place both the scorer and the shortlist filter read the description. (b) Qualifiers (`small`, `blue`, `main`, `upper`, …) no longer make a description "naming", so `the small button at the top left` resolves again; an unknown adjective still counts as a name and makes the tier decline rather than guess. Wordy re-measured: 0.709 / 0.860 / 0.000, all four Check Now states hit. |
| 2026-10-28 | 1.7 | Third review round: a position word right before the role word (`Align Left button`, `Turn Right button`, `Scroll Left icon`) was read as a position, so the lexical tier lost the word from the name (a tie with `Align Center`) and `_enforce_position` rejected the correct SLM answer when the button was not in the left third. The parser now walks the description left to right: a position word that follows a naming word continues the caption; a bare `Left button` is a caption when an element on the screen reads `Left` (`element_tokens`), the leftmost button otherwise. No benchmark description is affected (the only two with position words, `right now` and `the first page number`, parse as before), so no row moved. |
| 2026-10-28 | 1.8 | Run 7 (RTX A6000, `c6b8e72`, Tesseract present for the first time on a rented host — ADR-012 1.1): default chain **0.958 / 0.973 / 0.000** (lexical 408, slm 2, none 104; six hits gained, one lost, 499 of 514 steps identical to run 6), above UI-TARS (0.944) and ELAM (0.930) on action-hit on the same host while still passing 0 of 88 negatives. SLM-only re-measured with the plain prompt: 0.639 / 0.877 / 0.017 (5 of 88), the 1.3 regression closed. The stage ablation (`benchmarks/README.md` §7) reproduced the laptop figures to three decimals on the card. |

## Context

All existing locators identify elements by **DOM properties** (`id=`, `text=`,
`role=`, spatial relations). They are deterministic but brittle exactly where
perception is weakest: an icon whose caption is unstable ("Maximize" vs "Page",
see the caption-instability finding) or a key whose OCR is garbage is unfindable
by property. Meanwhile, the grounder model family (Aria-UI, ELAM-7B — surveyed in
the project report) resolves *natural-language intent* directly but re-infers per
instruction, returns a bare point, and produces no reusable artifact.

Users should be able to say what they mean — `desc="settings button"` — and have
the system find the best-matching element, while the generated DOM remains the
single source of truth.

## Decision

Add a `desc=` locator strategy resolved by a **tiered escalation chain**, each
tier cheaper and more deterministic than the next, stopping at the first
confident hit:

- **Tier 0 — lexical over DOM (no model, always on).** Tokenize the description;
  score every element on token/synonym overlap with `label`/`text`/`hint`, role
  words ("button", "icon", "field", …) against `role`/`visual_type`, and
  positional words ("top left", "right") against normalized bounds. Accept on a
  clear score margin. Deterministic and explainable.
- **Tier 1 — SLM over DOM.** Serialize a compact element table (id, role, text,
  label, normalized bounds) + the description; a small text LM (existing
  `SLMAdvisor` backend, e.g. `qwen2.5:3b` at temperature 0) returns
  `{id, confidence, reason}`. The id is validated against the DOM (hallucinated
  ids are rejected). Handles paraphrase and relational wording.
- **Tier 2 — VLM over image via Set-of-Mark (SoM).** The DOM's candidate boxes
  are drawn on the screenshot with numeric marks; a vision model is asked *which
  number* matches the description. Multiple-choice grounding is far more
  reliable for small VLMs than coordinate regression, and the answer is a DOM
  element **by construction** (snapping is built in). Only if the model insists
  nothing marked matches does the tier fail (no raw-point fallback in v1).

Cross-cutting rules:

1. **Cache** per `(DOM identity, description)` — one resolution per screen.
2. **Fail loud on ambiguity**: a tie in Tier 0 escalates rather than guesses;
   if the chain ends without a confident answer, the keyword fails with the
   candidate list.
3. **Determinism policy**: `grounding.tiers` in the session config selects the
   chain (default `["lexical", "slm"]`; CI can pin `["lexical"]`; `"vlm"` is
   opt-in). Every resolution logs which tier answered.
4. **Injection guard**: screen-derived text enters prompts, so model output is
   constrained to the id schema and never executed as instructions.

## Consequences

- Users get intent-level location that survives caption/OCR noise and UI
  restyling; property locators remain the deterministic default.
- The parser-vs-grounder dichotomy becomes a spectrum: parse once, ground only
  the long tail. The per-tier resolution rate is measurable and reportable.
- Tier ≥1 needs a running Ollama; Tier 0 is the model-free floor, so `desc=`
  always works (with reduced power) offline.
- Non-determinism is contained by config (tier pinning), temperature 0, and the
  cache; a `desc=` locator is still less deterministic than `text=` and is
  documented as such.
- The tier order is load-bearing, not cosmetic (measured 2026-10-27): the
  lexical tier answers 77 % of the benchmark steps on its own and turns the
  3B text model from a 0.634 whole-DOM grounder into a 0.930 chain by handing
  it a shortlist of eight. The same shortlist does not rescue the vision tier
  as an oracle: `qwen2.5vl:3b` answers "mark 1, confidence 0.99" to most
  nonsense captions, where the text model declines 87 of 88. A `verify`
  keyword must therefore never run a chain that ends in `vlm` until the
  Set-of-Mark prompt has a null option the model actually uses (candidate
  fix: ask for the caption of the chosen mark and cross-check it lexically).
- The model tiers never see a shortlist of one (2026-10-28). The benchmark's
  single false pass was a one-row candidate table: on a dialog whose other
  button OCR had not read, "Purple Elephant button" scored exactly one
  element by role word, and a 3B model asked "which of these?" about one row
  answers "this one" at 0.85, where it declines with two rows. The shortlist
  is padded from the pool to at least three candidates
  (`SHORTLIST_MIN`). A paraphrase ("close button" → the `×` icon)
  still resolves: padding adds choice, it does not remove the candidate.
  Confirmed on the lifecycle benchmark (run 6, 2026-10-27): the chain passes
  none of 88 negatives at 0.934 action-hit.
- The SLM prompt stays plain (2026-10-28). An explanatory null rule ("answer
  null unless text or role clearly corresponds; a matching role alone is
  NOT a match") made `qwen2.5:3b` *more* willing to answer when the table is
  long: it quotes the rule back as its justification ("role=button
  text='Files'") and picks any button. Over a whole-DOM table it answered 6
  of 6 nonsense captions where "use null if no element matches" answers 1;
  over the padded shortlist both decline. Prompt rules are not a substitute
  for a short candidate list with a 3B model; the shortlist is the control.
- Future: an embedding tier between 0 and 1 (semantic similarity, no
  generation); a dedicated grounder model as an alternative Tier 2 backend;
  caching successful resolutions as persistent aliases ("self-healing"
  locators).
