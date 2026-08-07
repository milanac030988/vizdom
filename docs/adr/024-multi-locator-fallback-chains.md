# ADR-024: Multi-Locator Fallback Chains (`||`)

## Status

Accepted (implemented)

## Date

2026-08-06

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-08-07 | 1.1 | **Ambiguity arbitration**: when an alternative matches *several* elements and the chain contains a `desc=`, the description is grounded over just those candidates to judge which was meant — before falling through. Rescues `text=+ \|\| desc="plus button"` where the `±` key's composite glyph also OCRs as `+`. Unconfident arbitration falls through unchanged. |
| 2026-08-06 | 1.0 | `||` separates ordered alternatives in a locator string; the first alternative resolving to exactly one element wins. Falls through on **not found** *and* **ambiguous**. Warning names the failed primary (stale-locator signal); a failed chain reports every attempt with its reason. Honoured by `Get Visual Element` (and therefore all actions), `Get Visual Elements`, and the assertion/wait keywords. |

## Context

Property locators are deterministic but brittle where perception is weakest: an
OCR misread or an unstable icon caption breaks `text=`, and the test simply fails
(both failure modes were measured in this project — see the caption-instability
finding and the real-application comparison). `desc=` (ADR-022) is resilient but
less deterministic and may invoke a model.

Users want to combine them: *try the cheap deterministic locator, and only if
that fails use the resilient one.* The obstacle is that multiple locators in one
string **already mean AND** (`text=Login role=button` is an intersection), so
fallback cannot reuse that syntax without silently changing the meaning of
existing suites.

## Decision

Introduce an explicit second combinator, so both compose:

```
role=button text=Save || desc="save button in the toolbar"
└── alternative 1 (AND) ──┘    └───────── alternative 2 ─────────┘
```

- **space** = AND within an alternative (unchanged, fully backward compatible)
- **`||`** = ordered OR: alternatives are tried left to right, and the first that
  resolves to **exactly one** element wins. Splitting is quote-aware, so
  `text="a || b"` is not split.

Rules:

1. **Fall through on both failure kinds** — *not found* and *ambiguous*. An
   ambiguous `text=Delete` is as unusable as a missing one, and a more specific
   later alternative may disambiguate it.
2. **A later win is reported at WARN**, naming the alternative(s) that failed:
   it means the primary locator has probably gone stale. Silent healing would
   hide rot.
3. **A failed chain reports every attempt and its reason**
   (`#1 'text=Save' -> not found; #2 'desc=…' -> no grounding tier confident`),
   so chains stay debuggable.
4. **Existence checks accept many matches.** For `Visual Should Exist` /
   `Get Visual Elements`, the first alternative that matches *anything* wins —
   ambiguity is not a failure when the question is "does it exist".
5. **Ordering is the user's cost control**: deterministic/free first (`text=`,
   `role=`), model-backed last (`desc=`). The happy path costs nothing extra.

### Ambiguity arbitration (v1.1)

An ambiguous match carries real information: the wanted element is almost
certainly *among* the matches. So before an ambiguous alternative falls through,
any `desc=` in the chain is resolved **restricted to those candidates**
(`DescriptionResolver.resolve(desc, within=...)`). Grounding over 2–3 elements is
where every tier is at its most reliable — the model-free lexical tier usually
separates "Plus" from "±" by label alone, and the SLM/VLM tiers judge a short,
focused list instead of the whole DOM (with Set-of-Mark, the VLM sees the actual
glyphs, which distinguishes candidates whose *DOM data* is identical).

The arbitration is logged (`matched N elements; desc=... disambiguated to ...`),
and an unconfident result falls through to the ordinary chain — it can rescue a
resolution, never corrupt one. Limits are inherited from the grounding data: if
OCR read the `±` key as `+` and no visual tier is configured, no resolver can
know it is not the plus key.

## Consequences

- Tests survive caption/OCR drift and minor UI relabelling without becoming
  non-deterministic on the happy path — the fallback only runs when the primary
  fails.
- The WARN is a measurable signal: how often a fallback rescues a run quantifies
  locator rot, and is the natural input to the **self-healing locators** roadmap
  item (cache the resolution, or suggest the updated primary).
- Risk: a chain can mask a genuinely broken primary. Mitigated by the WARN level
  and by reporting the failed alternative explicitly.
- `LocatorParser.parse()` keeps its exact contract (one AND-group);
  `parse_alternatives()` is additive, so nothing existing changes behaviour.
- Slight determinism cost only when a chain reaches `desc=`; CI can still pin
  `grounding.tiers` to the model-free tier (ADR-022).
