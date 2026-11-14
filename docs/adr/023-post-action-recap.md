# ADR-023: Post-Action Recap for Property Verification

## Status

Accepted (implemented)

## Date

2026-07-31

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-31 | 1.0 | <code>refresh=none&#124;element&#124;screen</code> on property getters; element-region re-OCR; stale-DOM marking after actions; new `Get Element Value` / `Verify Element Value` keywords (default `refresh=element`). |
| 2026-11-14 | 1.1 | **Region guard** for `refresh=element`, off by default (`recap.region_guard`, library argument `region_guard`, keyword `Set Region Guard`): the band around the element is compared with the screenshot the DOM was built from; a changed band or an empty read re-analyses the whole screen. Closes the limitation v1.0 deferred. |

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

## Region guard (1.1)

`refresh=element` reuses the bounds found by the last dump: the DOM is the
cache, and a value check costs one grab and one crop OCR. The cache is wrong
when the layout changed since the dump. Version 1.0 left that to the tester
(`refresh=screen`). Version 1.1 adds an optional check.

- **What is compared.** The element's own pixels are expected to change, so
  the check looks at the band around its padded bounds (`guard_margin_px`,
  default 24): the border neighbourhood, the label, the controls beside it.
  The reference is the screenshot the DOM was built from.
- **The measure.** Changed pixels over the band's structure (edge pixels of
  either image plus the changed ones). A share of the band's area lets a moved
  one-pixel border disappear in an empty neighbourhood; relative to the
  structure that is there, the same move is nearly total. Above
  `guard_tolerance` (default 0.2) the bounds are not trusted. Changes below
  0.5 % of the band are treated as noise.
- **Second rule.** A region that reads empty is not a verdict: an emptied field
  and a field that slid away look the same in the crop. It also triggers the
  full scan.
- **Fallback.** One full analysis of the same grab, then the element is read
  where it is now. An element that is gone fails as any unresolved locator.
  The new screenshot becomes the reference.
- **Switch.** Off by default, and with it off the code path is the one of 1.0
  (`tests/unit/test_region_guard.py` pins both). On through the config, the
  import argument or `Set Region Guard`. `refresh=screen` forces a full scan
  for one check either way.
- **Scope.** Value reads only. Existence and absence checks never use a cached
  region; they need the whole screen.

Measured on the target elements of the two real-application sets (453 and 81
elements, simulated changes, band check alone):

| Change | Main set | Held-out set |
|---|---|---|
| nothing changed: guard quiet | 453 / 453 | 81 / 81 |
| only the element's pixels changed: quiet | 453 / 453 | 81 / 81 |
| JPEG quality 85 capture noise: quiet | 453 / 453 | 81 / 81 |
| screen shifted 12 px down: tripped | 444 / 453 | 81 / 81 |
| screen shifted 12 px right: tripped | 431 / 453 | 74 / 81 |
| screen shifted 40 px down / right: tripped | 453 / 445 | 81 / 77 |
| a dialog over the element: tripped | 441 / 453 | 76 / 81 |

The check itself takes about 0.3 ms. The misses are elements whose
neighbourhood is uniform or runs unbroken along the direction of the shift (a
full-width row moved sideways); a covered element in a blank neighbourhood is
still caught by the empty-read rule. The guard is therefore a strong check, not
a proof, and it is not on by default. It has not yet been timed or exercised on
a live application; the figures above are simulated on saved screenshots.

Limits: a DOM loaded from a file has no screenshot to compare with and is read
unchecked, with one warning. A field that is legitimately empty costs a full
scan on every read. A noisy capture (a camera) may trip the guard on every
read, which is slow but not wrong.

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
