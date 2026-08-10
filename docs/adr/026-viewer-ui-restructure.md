# ADR-026: Viewer UI — Verb Toolbar, Menu Bar, and Three Tool Windows

## Status

Accepted (implemented)

## Date

2026-08-10

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-08-10 | 1.0 | Initial version |

## Context

The Viewer's toolbar accumulated one widget per feature as the pipeline grew.
Counted before this change, it held **26 widgets in a single row**: 10 verbs
(Connect, Disconnect, Capture & Analyze, Re-Analyze, Open Image, Analyze Image,
Open DOM, Explore Mode, Zoom ±, Export) interleaved with 10 pipeline controls
(capture source + argument, camera mode, detector, service target, smart-merge,
OCR engine, text ensemble, SLM toggle, SLM model) and 6 abbreviated labels
(`Src:`, `Det:`, `OCR:`, `Text+`, `Merge`, `SLM`).

Three concrete problems followed from that:

1. **The verbs were not findable.** `Capture & Analyze` — the action a user runs
   dozens of times per session — sat between `Disconnect` and `Re-Analyze` at the
   same visual weight as a checkbox labelled `Text+`.
2. **Settings had no room to explain themselves.** A toolbar row forces
   three-character labels, so the meaning lived only in tooltips. `Text+` does not
   tell anyone that it feeds our upscaling OCR into OmniParser (ADR-016).
3. **Two capabilities had no home in the GUI at all.** The session config
   (ADR-020) could only be edited in a text editor, and the three gRPC services
   (ADR-017/018/019) could only be started from a terminal — even though the
   Viewer is the tool a user has open while working with them.

The functional driver is that the Viewer is the *authoring* surface: what a user
proves here (this detector, this OCR engine, this capture strategy) has to
transfer verbatim into a Robot Framework suite. Editing the shared config and
supervising the services are therefore part of the Viewer's job, not adjacent to
it.

## Considered options

### Option A — Wrap the toolbar onto multiple rows

- ✓ Smallest change; nothing moves.
- ✗ Does not fix findability: 26 widgets over two rows is still 26 widgets, and
  the verbs stay mixed in with the knobs.
- ✗ Still no room for honest labels, so tooltips remain the only documentation.
- ✗ Costs vertical space on every screen, permanently, for settings that change
  a few times per session.

### Option B — A docked settings panel inside the main window

- ✓ Settings always visible; no window management.
- ✗ Takes canvas width from the part of the window that matters most — the
  screenshot and the element tree already share a three-way splitter.
- ✗ Permanent cost for occasional use, same objection as Option A.

### Option C — Verbs on the toolbar, knobs in tool windows, everything also in a menu bar

- ✓ The toolbar becomes what a toolbar is for: the five or six things done
  repeatedly.
- ✓ A dialog has room for full-sentence labels and grouping by pipeline stage,
  so the UI itself explains the pipeline instead of deferring to tooltips.
- ✓ A menu bar gives every command a discoverable, searchable home with its
  keyboard shortcut shown next to it — including the commands that are too rare
  to earn a toolbar slot of their own (Explore Mode, Disconnect).
- ✓ Leaves obvious places for the two missing capabilities (config, services)
  rather than inventing a new surface for each.
- ✗ Settings are one click away instead of zero, so the toolbar must advertise
  the active pipeline some other way (see Decision).
- ✗ Three more files to maintain, and window state (open/closed, position) to
  think about.

### Option D — Rebuild the Viewer's settings from `VizDomConfig` only, dropping the widgets

- ✓ One editor for everything; no duplicated field list.
- ✗ Would rewrite ~57 call sites that read the controls directly, in a tool that
  is currently the demo surface — a large behavioural risk for a UI change.
- ✗ Conflates two different lifetimes: the Viewer's *working* settings (change
  freely, re-analyse, see the effect) and a *persisted* session config meant to
  be handed to a test suite.

## Decision

Adopt **Option C**.

- **Toolbar = verbs only**: Connect, Capture & Analyze (F5), Re-Analyze (F6),
  **Open ▾**, Export to Robot, Pipeline Settings — with standard Qt icons
  (`QStyle.standardIcon`, so no assets to ship) and `ToolButtonTextBesideIcon`.
- **Re-checking an earlier result stays a toolbar-level workflow.** Opening a
  saved image or a saved DOM is not a rare command — it is how a result is
  re-examined without capturing again — so all three openers share one
  `QToolButton` in `MenuButtonPopup` mode: clicking it opens an image, the arrow
  offers Analyze Image (`Ctrl+Shift+O`) and Open DOM JSON (`Ctrl+D`). One toolbar
  slot, three one-click destinations. Additionally, **Open DOM JSON now loads the
  screenshot that sits beside the DOM** (a session directory holds
  `dom_result.json` next to `screenshot.png`) and defaults its dialog to
  `output/sessions/`: previously it loaded the tree alone, so last session's
  boxes were drawn over whatever image happened to be on the canvas.
- **Menu bar** (File / Capture / View / Tools / Help) carries *every* command,
  including the ones without a toolbar slot. Shortcuts and status tips are
  declared on the `QAction`, so the menu, the toolbar and the status bar stay in
  agreement by construction.
- **Pipeline Settings** (`Ctrl+,`) hosts the 10 pipeline controls, grouped by
  pipeline stage: Capture source → Element detection → Text → Small-model
  refinement. It **reparents the existing widget objects** rather than creating
  new ones: the main window reads them from ~57 sites, so moving the objects
  keeps every read working and leaves exactly one source of truth per setting.
  This is the deliberate rejection of Option D's rewrite.
- **Session Configuration** edits the same `vizdom.config.json` the CLI, the
  Python API and Robot Framework read (ADR-020). Its form is **generated from the
  `VizDomConfig` dataclasses**, with tooltips taken from the in-code `_FIELD_HELP`
  strings, so the editor cannot drift from the schema when a field is added.
  Validation delegates to the real `VizDomConfig.load()` — including its
  unknown-key rejection — rather than a re-implementation that could accept what
  the pipeline refuses. A JSON tab covers what the form does not, and
  *Apply to Viewer* pushes the fields the Viewer drives onto the controls.
- **Services** starts, stops and monitors the detector (50051), capture (50053)
  and actuator (50054) servers as `QProcess` children with
  `PYTHONPATH=<repo>/src`, streams their output into a log pane, and polls the
  `HealthCheck` RPC every 4 s. A service that answers on its port but was not
  started here is shown as `(external)` with **Stop disabled** — the dialog does
  not offer to stop what it does not own. The main window's `closeEvent` calls
  `shutdown()`, so exiting the Viewer never leaves orphaned services.

The accepted cost of Option C — settings one click away — is paid down by a
**right-aligned pipeline summary** on the toolbar
(`grpc | omniparser | paddleocr | SLM`), which is also the button that opens the
settings. The toolbar no longer *shows* the controls, so it has to show their
effect; otherwise a mis-set detector stays invisible until the results look
wrong.

All three windows are modeless `Qt.Tool` windows and are created lazily on first
use, so a session that never opens them pays nothing. They `hide()` on close
rather than being destroyed — mandatory for Pipeline Settings, whose hosted
widgets must outlive the dialog.

## Consequences

**Positive**

- The toolbar carries 6 slots instead of 26 widgets; the primary action is the
  second item and has an icon.
- Re-checking a saved result is one dialog instead of two, and the boxes are
  always drawn over their own screenshot.
- Settings are labelled in full sentences and grouped by the pipeline stage they
  affect, which makes the dialog a readable description of the pipeline.
- The session config and the gRPC services are reachable from the tool the user
  already has open; the config editor is schema-generated, so adding a config
  field needs no GUI change.
- No call sites changed: the pipeline controls kept their member names and are
  the same objects, so `Capture & Analyze` behaves exactly as before.
- Services started from the Viewer are stopped when it exits.

**Negative / limits**

- Changing a setting now takes an extra click (mitigated by `Ctrl+,` and the
  summary button, not eliminated).
- Window position and open/closed state are not persisted between runs; a user
  who wants Pipeline Settings docked beside the main window rearranges it each
  session. Deferred until someone asks — persisting geometry means a settings
  store the Viewer does not otherwise need.
- `Apply to Viewer` maps only the config fields the Viewer itself drives
  (detector, OCR, capture strategy/target, refinement, camera mode). The
  remaining fields still take effect when the same file is used by the CLI or a
  suite, but the Viewer will not visibly reflect them.
- Health is inferred from the `HealthCheck` RPC, so a service that is up but
  wedged in a long inference call may report not-ready for the duration.

## References

- Implementation: `tools/visual_dom_viewer/ui/main_window.py`
  (`_setup_toolbar`, `_create_pipeline_controls`, `_update_pipeline_summary`,
  `closeEvent`), `ui/settings_dialog.py`, `ui/config_dialog.py`,
  `ui/services_dialog.py`
- ADR-006 — Viewer workflow this UI serves
- ADR-020 — the session config the Configuration window edits
- ADR-017 / ADR-018 / ADR-019 — the three services the Services window runs
- ADR-016 — what the "Text ensemble" control actually does
