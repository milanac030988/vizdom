# ADR-023: Post-Action Recap for Property Verification

## Status

Accepted (implemented)

## Date

2026-07-31

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-31 | 1.0 | `refresh=none|element|screen` on property getters; element-region re-OCR; stale-DOM marking after actions; new `Get Element Value` / `Verify Element Value` keywords (default `refresh=element`). |

## Context

The Visual DOM is a snapshot: `Dump Visual DOM` captures and analyses once, and
every subsequent query reads that cache. After an action changes the screen —
typing into a field, toggling a control — the cache is stale, so
`Type Text Visual` followed by `Get Element Text` returns the *pre-typing* OCR.
That is a silent correctness trap for the most common verification pattern
(act → read back → assert). Only the `Wait Until Visual …` keywords refresh
today, and they rebuild the entire DOM on every poll — too heavy to be the
default for a single property read.

## Decision

1. **Three refresh levels**, selectable per call on the property getters
   (`Get Element Property/Text/Label`):
   - `none` (default for existing getters — backward compatible): read the cache.
   - `element`: re-capture the screen, **crop the element's bounds (+8 px pad)**,
     re-run **OCR only** on the crop, and update that element's `text` in the
     cached DOM (finder index rebuilt). No detector, no hierarchy rebuild.
   - `screen`: full `Dump Visual DOM`, then re-resolve the locator.
2. **New value keywords** with `refresh=element` as the default, because a
   *verification* keyword that can read stale data is a footgun:
   - `Get Element Value  <locator>` → the element's current (re-OCR'd) text.
   - `Verify Element Value  <locator>  <expected>` → normalized comparison
     (whitespace-collapsed; `exact=True` for strict equality, `ignore_case=True`
     available), with an actual-vs-expected failure message.
3. **Stale marking.** Every action keyword marks the DOM stale; a getter that
   reads the cache (`refresh=none`) while the DOM is stale logs a warning naming
   the fix. `Dump/Load Visual DOM` (and the waits, via dump) clear the flag.

## Rationale for element-region re-OCR as the verification default

- **Cost**: a crop re-OCR is milliseconds-to-a-second versus the multi-second
  full pipeline — cheap enough to be a default.
- **Accuracy**: the small crop gets the OCR upscaling treatment (~3x), so the
  region read is typically *better* than the same element's text from the
  full-screen pass — exactly what an input-field value needs.
- **Scope honesty**: region refresh updates one element's `text` and nothing
  else. It is for value reads. If the action may have changed *other* elements
  (a Submit button enabling, a dialog appearing), that is what `refresh=screen`
  and the existing waits are for — the keyword docs say so explicitly.

## Consequences

- The act → read-back → assert pattern is correct by default via
  `Verify Element Value`, at region-OCR cost.
- Existing suites are unaffected (`refresh=none` default on existing getters);
  the stale warning surfaces latent traps in them without breaking anything.
- Known limitation (documented): if the layout shifted since the dump (element
  moved, dialog covering it), the region crop reads the wrong pixels — the
  remedy is `refresh=screen`. A future guard could compare the crop against the
  cached screenshot's same region and auto-escalate; deferred to keep v1 simple
  and predictable.
- OCR reads the *rendered* value; passwords/masked fields read the mask
  characters, and fonts with OCR-hostile styling read imperfectly — comparison
  is therefore normalized by default.
