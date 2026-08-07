# Using VizDOM as a Client

VizDOM turns a screenshot into a queryable Visual DOM (bounds, roles, text, labels,
locators, hierarchy). There are three ways to consume it, all reading the same
[configuration](CONFIGURATION.md):

1. **In-process Python** — `connect().analyze(image)`; simplest, single machine.
2. **Distributed via gRPC** — run the heavy detector (and optionally capture /
   actuator) as services and call them from a thin client, possibly on another host.
3. **Robot Framework** — the `VisualGuiLibrary` keyword library for test suites.

!!! note "Do I need to start any services first?"
    **Not for a local, single-machine run.** In-process Python (`connect()`) and the
    Robot Framework library run the detector, capture, and actuator *inside your
    process* — nothing to launch. Start the gRPC services (§2) **only** to split work
    across machines or share one warm model. Rule of thumb:

    - share / offload the **detector** (the heavy model) → run the *detector* service;
    - capture the screen on a **different device** → run the *capture* service;
    - click / type on a **different device or a robot arm** → run the *actuator* service.

    Then point your client at each one **through the config file**
    (`detector.backend: "grpc"` + `grpc_target`) or the Robot Framework
    `capture=grpc` / `actuator=grpc` arguments (shown below). All configuration
    lives in one JSON file — see **[Configuration & Sessions](CONFIGURATION.md)** for
    how to generate, edit, and load it.

## 1. In-process Python

```python
from visual_dom import connect

session = connect("vizdom.config.json")   # or connect() for defaults
dom = session.analyze("screenshot.png")   # -> Visual DOM dict
dom = session.analyze(bgr_numpy_array, save_path="out.json")
```

Models load once per session and are reused across `analyze` calls. See
[Configuration](CONFIGURATION.md) for every tunable.

## 2. Distributed via gRPC

The detector (OmniParser/YOLO/UIED), screen **capture**, and input **actuator** can
each run as a gRPC service, so one warm GPU model serves many clients, capture runs
on the device under test, and actuation happens wherever the SUT is (ADR-017/018/019).

### Services and ports

| Service | Default port | Start command |
|---|---|---|
| Detector | 50051 | `python -m visual_dom.adapters.inbound.grpc.detector_server --backend omniparser --port 50051` |
| Capture | 50053 | `python -m visual_dom.adapters.inbound.grpc.capture_server --strategy windows --port 50053` |
| Actuator | 50054 | `python -m visual_dom.adapters.inbound.grpc.actuator_server --strategy desktop --port 50054` |

On Windows the `start_detector.bat` / `start_capture.bat` / `start_actuator.bat`
launchers wrap these (and set `PYTHONPATH`). The detector server also accepts
`--icon-detect` / `--icon-caption` / `--omniparser-root` / `--yolo-model`
(OmniParser auto-detects `models/omniparser/` + `third_party/OmniParser`).

Prerequisite (once): `pip install grpcio grpcio-tools`.

### Starting the services

Start only the ones you need (see the note at the top). Each is a single command
that runs until you stop it with `Ctrl-C`; give each its own terminal. On Windows the
`start_*.bat` wrappers do the same and set `PYTHONPATH` for you.

**Detector** — loads the model once and serves many clients (run it on the GPU host):

```bash
python -m visual_dom.adapters.inbound.grpc.detector_server \
    --backend omniparser --ocr easyocr --port 50051
# Windows:  start_detector.bat --backend omniparser --ocr easyocr
# backends: omniparser | yolo (--yolo-model <path>) | uied (CPU, no weights)
# weights auto-resolve from models/omniparser/ + third_party/OmniParser
#   (override with --icon-detect / --icon-caption / --omniparser-root)
# --box-threshold 0.03  recovers faint glyphs (default 0.05)
```

!!! warning "Pass `--ocr` when serving OmniParser remotely"
    The OCR text ensemble (ADR-016) normally injects the *client* pipeline's
    upscaling OCR into OmniParser — but that is a Python callable and **cannot
    cross gRPC**. Without `--ocr`, a remote OmniParser silently falls back to its
    own weaker OCR, and small low-contrast text rows are lost. `--ocr easyocr`
    builds the ensemble OCR **on the service**, restoring in-process text quality
    (verified: identical element count and all previously-missing status rows).

**Capture** — grabs the screen on the device under test:

```bash
python -m visual_dom.adapters.inbound.grpc.capture_server --strategy windows --port 50053
# strategies: windows | linux | android (--serial <device>) | camera
# --window-title "Calculator"  default app raised by the Focus RPC (ADR-021)
# Windows:  start_capture.bat --strategy windows
```

**Actuator** — clicks / types on the device, or drives a robot arm:

```bash
python -m visual_dom.adapters.inbound.grpc.actuator_server --strategy desktop --port 50054
# strategies: desktop | android (--serial <device>) | <your plugin>
# --window-title "Calculator"  default app raised by the Focus RPC (ADR-021)
# Windows:  start_actuator.bat --strategy desktop
```

Both services also expose a **`Focus`** RPC, because a window can only be raised on
the machine that owns the screen — so `Bring App To Front` works identically for an
in-process run and a fully remote one.

Each server logs a `HealthCheck` line when it is ready. Leave them running, then
start a client (below) pointed at their `host:port`.

### Python client — DOM via the remote detector

Point the session at the service by selecting the `grpc` backend and its target; the
rest of the pipeline (OCR, merge, hierarchy, compile) still runs locally:

```python
from visual_dom import connect

session = connect({
    "detector": {"backend": "grpc", "grpc_target": "gpu-host:50051"},
    "ocr": {"engine": "easyocr"}
})
dom = session.analyze("screenshot.png")
```

Or without a config object, straight through the pipeline:

```python
from visual_dom.core.domain.pipeline import VisualDOMPipeline
pipe = VisualDOMPipeline(detector="grpc", detector_kwargs={"target": "gpu-host:50051"})
result = pipe.process("screenshot.png")   # {"elements": [...], "image_size": {...}}
```

Capture and actuation have matching clients when you need them:

```python
from visual_dom.adapters.outbound.capture import create_capture
from visual_dom.adapters.outbound.actuator import create_actuator

cap = create_capture("grpc", target="sut-device:50053")
cap.focus_target("Calculator")     # raise the SUT first (ADR-021) -> True/False
shot = cap.capture()                                                 # BGR frame
frame = cap.capture_window("Calculator")   # or just that window (crop + geometry)
shot = frame.image                          # None if it cannot be scoped
create_actuator("grpc", target="sut-device:50054").tap(0.5, 0.5)      # normalized xy
```

Coordinates on the actuator port are **normalized** `[0,1]` (resolution-independent);
the service maps them to device pixels.

Both ports accept **user plugins** (a frame grabber, a serial touch-injector, a
robot arm): drop one file in `plugins/capture/` or `plugins/actuator/` and select
it by name like any built-in — see **[Writing Plugins](PLUGINS.md)**.

## 3. Robot Framework

`Connect` is the recommended first keyword — it applies one config file to the whole
session (DOM generation **and** capture):

```robotframework
*** Settings ***
Library    VisualGuiLibrary

*** Test Cases ***
Login Works
    Connect              vizdom.config.json
    Dump Visual DOM
    Click Visual         text=Login
    Type Text Visual     hint=Email        user@example.com
    Visual Should Exist  text=Welcome
```

### Fully remote (capture on the device, actuate via gRPC)

Configure the ports directly at import, or via the config's `capture` section plus
an `actuator=grpc` argument:

```robotframework
*** Settings ***
Library    VisualGuiLibrary    capture=grpc    capture_target=sut:50053
...                            actuator=grpc   actuator_target=sut:50054
```

### Keeping the app under test in front

VizDOM grabs the **whole screen** and clicks by **coordinate**, so if another window
covers the SUT the DOM is built from the wrong pixels and the clicks land in the
wrong application. Raise it first (ADR-021):

```robotframework
Bring App To Front    Calculator
Dump Visual DOM
```

Better still, capture **only that window**, so the DOM contains just the application
— no desktop, no other windows:

```json
"capture": { "window_title": "Calculator", "window_scope": true }
```

```robotframework
Connect             vizdom.config.json
Dump Visual DOM       # the DOM is now the app's own client area
Click Visual        text=7
```

Or keep the full screen and merely raise the app before each grab:

```json
"capture": { "window_title": "Calculator", "focus_before_capture": true }
```

- The title can also come from `Library  VisualGuiLibrary  app_title=Calculator`;
  with it set, `Bring App To Front` needs no argument.
- Success is **verified** (the window really is foreground), never assumed — the OS
  can refuse the raise, and an ambiguous title fails instead of guessing.
- The explicit keyword **fails the test** when it cannot focus (`required=${False}`
  downgrades it to a warning); `focus_before_capture` only warns, since the grab may
  still be usable.
- It works remotely too: capture and actuator services expose a `Focus` RPC, and
  `window_scope` crops **on the service**, so both happen on the machine that owns
  the screen. Clicks stay correct because the crop's origin and the device's
  coordinate space travel back with the pixels — including for a window on a second
  monitor, whose screen coordinates can be negative.
- If the strategy cannot scope to a window (a camera, an older service), you get a
  full-screen grab **and a warning** rather than a wrong crop.
- Focusing is an *action* — it can dismiss tooltips or transient popups. That is why
  it is opt-in rather than implicit in every capture.

Locate elements by **role/text/spatial** rather than pixel coordinates — e.g.
`text=Login`, `hint=Email`, `role=button`, `right_of="Label"`, `below="Title"`,
`within="Form"` — so tests survive layout and theme changes.

### Fallback chains — combine locators with `||`

Put the cheap deterministic locator first and the resilient one last; the first
alternative that resolves to **exactly one** element wins (ADR-024):

```robotframework
Click Visual    text=Save || desc="save button in the toolbar"
Click Visual    role=button text=OK || desc="confirm button"      # AND inside, OR between
```

- **space = AND** within an alternative (unchanged), **`||` = ordered OR** between them.
- An alternative falls through when it finds **nothing** *or* is **ambiguous** —
  an ambiguous `text=Delete` is as unusable as a missing one.
- **Ambiguity arbitration**: before an ambiguous alternative falls through, a
  `desc=` in the chain judges *which* of the matched elements was meant (the
  description is grounded over just those candidates). E.g. when the `±` key's
  glyph also OCRs as `+`, `text="+" || desc="plus button"` still picks the real
  plus. Logged as `matched N elements; desc=... disambiguated to ...`.
- When a later alternative wins, a **warning** names the one that failed: that's a
  signal the primary locator has gone stale (useful, not noise — don't ignore it).
- If the whole chain fails, the error lists every attempt and why:
  `#1 'text=Save' -> not found; #2 'desc=…' -> no grounding tier confident`.
- Existence checks (`Visual Should Exist`, `Get Visual Elements`) accept many
  matches, so there the first alternative matching *anything* wins.
- Splitting is quote-aware, so `text="a || b"` is not split.

Cost stays on the happy path: `desc=` (which may call a model) is only reached
when the deterministic locator has already failed.

### Failure screenshots

Every failing keyword of the library automatically captures the screen and embeds
the image in `log.html`, directly under the failing keyword. The grab goes through
the **capture port**, so in a distributed run the evidence shows the machine under
test (fetched from the capture service), honours `window_scope`, and falls back to
a full-screen grab when the window cannot be raised — which is often exactly the
evidence you need (it shows *what was covering the app*).

```robotframework
Set Screenshot On Failure    ${False}      # opt out for a session
Take Screenshot              after-login   # explicit evidence, any time
Run Keyword If Test Failed   Take Screenshot   # classic teardown idiom
```

Automatic capture is on by default (`Library  VisualGuiLibrary
screenshot_on_failure=${False}` to disable at import). One screenshot per failure:
nested keyword calls that fail on the same exception do not duplicate it. Note the
automatic hook covers *this library's* keywords — a plain BuiltIn assertion
(`Should Be Equal`) does not trigger it; use the teardown idiom above to cover
those too.

### Verifying values after an action (recap)

The DOM is a snapshot — after `Type Text Visual`, a plain `Get Element Text` would
return the *pre-typing* value. The act → read back → assert pattern is one keyword
(ADR-023):

```robotframework
Type Text Visual        hint=Email    user@example.com
Verify Element Value    hint=Email    user@example.com
```

`Verify Element Value` (and `Get Element Value`) default to **`refresh=element`**:
the screen is re-captured and *only that element's bounds* are re-OCR'd — fast, and
usually more accurate than the full-screen pass because the small crop gets the OCR
upscaling treatment. Comparison is whitespace-normalized (`exact=True` /
`ignore_case=True` available).

The classic getters (`Get Element Property/Text/Label`) keep their cached-read
behaviour but accept the same option: `refresh=none` (default) | `element` |
`screen` (full re-dump). Every action keyword marks the DOM stale, and a cached
read after an action logs a warning naming the fix. Rule of thumb: **`element`**
to read one value back; **`screen`** when the action may have changed the layout
or other elements (dialogs, buttons enabling).

### Locating by description (`desc=`)

You can also identify an element by *describing* it (ADR-022):

```robotframework
Click Visual    desc=settings button
Click Visual    desc="close button top right"
```

Resolution escalates through configurable tiers, stopping at the first confident
match — and every hit logs which tier answered:

1. **lexical** (always on, no model) — deterministic token/role/position matching
   against the DOM's `label`/`text`/`hint`;
2. **slm** — a small text LM (Ollama, default `qwen2.5:3b`) picks the element from
   a compact DOM table; handles paraphrase ("magnifier" → *Search*);
3. **vlm** (opt-in) — Set-of-Mark grounding: candidate boxes are numbered on the
   screenshot and a vision model picks the number, so the answer is always a real
   DOM element.

Positional words ("top right") are enforced **geometrically**, never left to the
model. Ambiguity fails loudly with the candidate list instead of guessing. Tune it
in the config's `grounding` section — e.g. pin CI to the deterministic tier:

```json
"grounding": { "tiers": ["lexical"] }
```

`desc=` trades a little determinism for resilience: prefer `text=`/`role=` when
they work; reach for `desc=` when perception noise or restyling breaks them.

> **Tip.** For icon-only controls whose caption can be unreliable (a bare `□`
> maximize glyph, small toolbar icons), prefer `role=button` + a spatial relation
> over `text=`, since the visual caption is a best-effort hint, not a stable id.

### Runnable end-to-end demo (Windows)

A complete example — **start the detector service → configure a session → run a
Robot Framework test** that drives the Windows Calculator from its Visual DOM — is in
[`examples/windows_calculator_demo/`](https://github.com/milanac030988/vizdom/tree/main/examples/windows_calculator_demo)
(`README.md` + `vizdom.config.json` + `calculator_demo.robot`). In short:

```bat
:: Terminal 1 — start the detector service (warm model on :50051)
start_detector.bat --backend omniparser

:: Terminal 2 — run the test (pins the project's Python + PYTHONPATH)
run_demo.bat
```

The test launches `calc.exe`, `Connect`s the config, `Dump Visual DOM`, then clicks
`7`, `+`, `5`, `=` and asserts `12`. A no-service variant (detector in-process) is
documented in the example's README.
