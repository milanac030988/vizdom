# ADR-022: Description-Based Locator (`desc=`) via Tiered Grounding

## Status

Accepted (Tiers 0–1 implemented; Tier 2 implemented behind config, needs a vision model)

## Date

2026-07-30

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-30 | 1.0 | Design + Tiers 0/1 implemented (`desc=` strategy, lexical matcher, SLM-over-DOM resolver, `grounding` config, RF wiring). Tier 2 (VLM Set-of-Mark) implemented behind `grounding.tiers`, disabled by default. |

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
- Future: an embedding tier between 0 and 1 (semantic similarity, no
  generation); a dedicated grounder model as an alternative Tier 2 backend;
  caching successful resolutions as persistent aliases ("self-healing"
  locators).
