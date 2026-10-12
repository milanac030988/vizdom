# ADR-028: Viewer "Click via Actuator" on a Shared Locator Resolver

## Status

Accepted (implemented)

## Date

2026-10-12

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-10-12 | 1.0 | Viewer can try an element's locator through the configured actuator. Locator chain resolution moved out of the RF keyword class into `LocatorResolver`; exported locators restricted to what the parser understands; trials re-capture before resolving by default. |

## Context

The Viewer could define and export locators but never *try* one: the first time a
locator was exercised was at Robot Framework runtime (Notion task "Viewer: try an
action through the actuator"). Adding a "click" button looks small, but three facts
about the code shaped it:

1. **The resolution logic lived inside Robot.** `||` fallback chains (ADR-024),
   `desc=` escalation (ADR-022) and `desc=` ambiguity arbitration ran inside
   `CaptureKeywords.get_visual_element`, not in `ElementFinder`. A Viewer feature
   built on `ElementFinder` alone would try a *different* resolver than the test runs.
2. **Exported locators were not what the parser reads.** The exporter wrote
   `bbox=[…]`, `center=[…]`, `x=…`, `confidence=…` and `type=button`. `LocatorParser`
   only knows `id/text/hint/role/desc` and the relative strategies; unknown keys
   become modifiers nobody applies, so they were silently ignored (`type=button` on
   its own parses to nothing at all). Every default export also AND-ed the element
   id in (`text=… type=… id=E7`); ids are assigned in order by the compiler, so a
   re-analysis that adds one element renumbers the rest, and the AND made the whole
   locator as fragile as the id. The generated resource also imported a
   non-existent `VisualLibrary` and called SeleniumLibrary keyword names
   (`Click Element`, `Input Text`, `Element Should Be Visible`).
3. **Trying on the defining DOM proves little.** A locator always finds its own
   element in the DOM it was built from; that only checks uniqueness. What the
   suite sees is a *fresh* analysis.

## Considered options

### Option A — Viewer clicks the element's stored bounds

- ✓ trivial, no capture needed
- ✗ verifies nothing about the locator, which is the whole point of the task

### Option B — Viewer instantiates `VisualGuiLibrary` and calls its keywords

- ✓ runs literally the test's code
- ✗ drags RF keyword state (session, stale-DOM flags, capture ownership) into a Qt
  app; the library would capture on its own while the Viewer shows a different
  capture

### Option C — Extract a Robot-free `LocatorResolver`; both clients call it

- ✓ one resolver, two thin clients; behaviour and error messages unchanged for RF
- ✓ the Viewer keeps owning capture/analysis/display
- ✗ a refactor of a hot keyword path (mitigated by tests pinning messages)

## Decision

**Option C.**

- `visual_gui_library/locators/resolver.py`: `LocatorResolver.resolve` / `explain`
  / `resolve_all` hold the ADR-024 chain logic; `Get Visual Element(s)` delegate to
  it. `explain` returns a `Resolution` (winning alternative, per-alternative
  failure reasons) so the Viewer can show *why* a locator failed.
- `tools/visual_dom_viewer/export/locators.py` builds every exported locator —
  and the one the Viewer tries — as `<text/hint/role AND-group> || id=E7`: the
  semantic part survives renumbering, the id is only the last-resort fallback.
  Properties with no locator equivalent are left out and named in the resource
  comment. The resource uses `VisualGuiLibrary` and its keywords.
- `tools/visual_dom_viewer/core/actuation.py` (Qt-free): `LocatorTrial` resolves,
  maps the element center to normalized device coordinates (`CaptureFrame` for a
  window capture, proportional for a full-screen one — the RF library's
  `_norm_xy` rules, ADR-021), raises the window (actuator `focus_target`, then the
  capture side's), then taps through the `ActuatorStrategy` (ADR-019).
- Viewer UX (`ui/try_locator.py`): right-click an element on the canvas or tree,
  or *Capture > Click Selected via Actuator* (`Ctrl+T`). By default it **captures
  and analyzes again first**, resolves on that fresh DOM, clicks, then captures
  again to show the effect (ADR-023). Pipeline Settings gains an **Actuation**
  group (strategy, service target, window title, the two capture toggles);
  the session config's `actuator` and `grounding` sections apply to it.

Safety rules: never click without a target window; never click when the window
cannot be raised; refuse a screenshot whose screen position is unknown (an image
opened from disk, a window-handler crop without geometry); ask once per Viewer
session before the first real click.

## Consequences

**Positive**

- A broken locator now fails in the Viewer with the same message the suite would
  print, before the test exists.
- Exported resources run against VizDOM as written, and their locators survive
  element renumbering.
- One resolver for all clients; any future client (a session orchestrator,
  ADR-025) reuses it.

**Negative / limits**

- A trial with the default settings costs two full analyses (before and after the
  click); turning "capture again before resolving" off is faster but only proves
  uniqueness on the current DOM.
- The window-handler capture path records no screen position, so trials always
  capture through a capture strategy (the platform default when the toolbar uses
  the handler).
- Only clicks (single / double / right) are offered; typing and keys are left for
  later, as the task proposed.
- Text containing a literal `"` cannot be expressed by the locator grammar and is
  exported without the quote character.
- Container nodes that exist only in the hierarchy (not in the flat `elements`
  list) are not resolvable by any locator; trying one fails, as it would in a test.

## References

- ADR-019 (actuator), ADR-021 (targeting and focus), ADR-022 (`desc=`),
  ADR-023 (post-action recap), ADR-024 (fallback chains), ADR-026 (Viewer UI)
- Code: `src/visual_gui_library/locators/resolver.py`,
  `tools/visual_dom_viewer/export/locators.py`,
  `tools/visual_dom_viewer/core/actuation.py`, `tools/visual_dom_viewer/ui/try_locator.py`
- Tests: `tests/unit/test_locator_resolver.py`, `test_export_locators.py`,
  `test_viewer_actuation.py`, `test_try_locator_ui.py`
