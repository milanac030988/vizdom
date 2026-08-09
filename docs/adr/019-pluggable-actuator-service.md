# ADR-019: Pluggable Input Actuation (Strategy + Auto-Discovery + Service)

## Status

Accepted (fully implemented - Phases 1-3)

## Date

2026-07-27

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-27 | 0.1 | Initial proposal: `ActuatorPort` as the write-side twin of `CapturePort` (ADR-018) - strategy + auto-discovery registry + built-ins + optional gRPC service. |
| 2026-07-27 | 0.2 | Phase 1 implemented: `ActuatorStrategy` (normalized-coord contract) + auto-discovery registry + built-ins (desktop/android, relocated from RF adapters) + robot-arm example plugin. Verified discovery + coordinate mapping. gRPC service = Phase 2. |
| 2026-07-27 | 0.3 | Phase 2 implemented: gRPC `Actuator` service (`actuator_server`) + `GrpcActuatorStrategy` client (registered as `grpc`) + `protos/actuator.proto`. Verified end-to-end (normalized coords mapped server-side). |
| 2026-07-27 | 1.0 | Phase 3 implemented: RF library rewired as a thin client over `visual_dom` capture + actuator strategies (in-process or gRPC per config); old `adapters/{base,desktop,android}.py` deleted. Verified end-to-end (normalized round-trip to element centers). Component + class diagrams updated. |

## Context

Driving an application under test (SUT) has two halves:

- **Read** the screen - already a pluggable, service-able driven port
  (`CapturePort`, ADR-018): windows / linux / android / camera + a gRPC service.
- **Drive input** - click, type, scroll, swipe, key presses. Today this lives in
  the Robot Framework library's platform adapters
  (`visual_gui_library/adapters/{base,desktop,android}.py`), a *separate*
  mechanism from capture. Worse, `BaseAdapter` bundles **both** `capture_screen()`
  and the action methods, so capture is implemented twice (once here, once in
  `visual_dom.capture`).

This has three problems:

1. **Duplication / drift.** Capture logic exists in two places.
2. **No extensibility for input.** A user cannot plug in a new way to actuate the
   SUT without editing the RF library. The motivating case: a **robot arm** (or
   capture card + serial/CAN controller) that physically taps a screen which is
   observed through `CaptureStrategy=camera`. There is no seam for that.
3. **Asymmetry.** Capture is a first-class `visual_dom` port that can run as a
   remote service; input is not, even though it has the same "runs where the SUT
   is" property.

`visual_dom` should own **both** driven ports. The RF library should become a thin
orchestrator: capture -> detect -> build DOM -> resolve locator -> **actuate**.

## Decision

Introduce **`ActuatorPort`** - the write-side twin of `CapturePort` - built with
the exact machinery already proven for detectors (ADR-015) and capture (ADR-018).

### 1. Strategy base (`ActuatorStrategy`)

Abstract, **primitive** input operations (no DOM knowledge):

```
tap(x, y, image_size, click_type="single")
type_text(text)
press_key(key)              # "enter", "ctrl+a", "alt+f4"
swipe(x1, y1, x2, y2, image_size, duration=0.3)   # also drag / scroll
```

Plus `name`, `platform`, `description`, `is_available()`, `close()` - identical to
`CaptureStrategy`.

Element resolution (`locator -> bounds -> center`) and higher-level flows
(focus-then-type, wait-then-click) stay in the RF keywords. The actuator only
receives coordinates and primitives.

### 2. Coordinate contract - normalized [0, 1]

This is the one concern capture does not have: the DOM gives coordinates in
**image pixels**, but where a tap lands depends on the actuator's own space.

The wire/API contract uses a **normalized coordinate** `(nx, ny) in [0, 1]` plus
the source `image_size`. Each strategy maps normalization to its own device space:

- **desktop** (windows/linux): image px == screen px -> `nx * screen_w` (identity-ish).
- **android**: scale normalized -> device input resolution.
- **robot-arm** (user plugin): apply a **calibration homography** image -> physical
  servo coordinates (a one-time calibrate step the plugin owns).

Device-specific mapping stays inside the device adapter (hexagonally correct); the
orchestrator and the protocol stay dumb.

### 3. Auto-discovery registry (`visual_dom/actuator/registry.py`)

Discovers `ActuatorStrategy` subclasses from the built-in package **and** a
plugins folder - `$VIZDOM_ACTUATOR_PLUGINS`, else `<repo>/plugins/actuator/`.
API mirrors capture: `create_actuator(name, **kw)`, `list_actuators()`,
`register()`, `auto_select()`. Selection is by name from config/CLI.

### 4. Built-in adapters (`visual_dom/actuator/builtin/`)

Relocated from the RF adapters (mostly a move, not new logic):

- `desktop` - pyautogui / platform input (from `adapters/desktop.py`).
- `android` - adb `input tap/text/swipe/keyevent` (from `adapters/android.py`).
- Example plugin `plugins/actuator/example_robot_arm.py` - a worked stub showing
  the calibrate + homography + servo-command pattern.

### 5. Actuation as a service (gRPC) - transport, not requirement

Mirrors the capture/detector services:

- `protos/actuator.proto` - `Tap`, `TypeText`, `PressKey`, `Swipe`, `HealthCheck`.
- `visual_dom/rpc/actuator_server.py` - wraps one `ActuatorStrategy`, runs **on the
  SUT host / the arm's controller**. `vizdom-actuator` / `start_actuator.bat`.
- `GrpcActuatorStrategy` - registered as `grpc`, just another strategy.

**gRPC is one transport.** A local desktop click uses the in-process strategy (no
server, no latency); `grpc` is selected only when the actuator lives on another
machine/device. Same local-vs-remote selection as capture.

### 6. RF library becomes a thin client

`visual_gui_library` stops owning platform I/O. `ActionKeywords` /
`CaptureKeywords` resolve locators against the DOM and call the `visual_dom`
capture + actuator strategies (in-process or gRPC, per config). The old
`adapters/{base,desktop,android}.py` are deleted once parity is confirmed.

## Alternatives Considered

- **Leave input in the RF adapters.** Rejected: keeps capture duplicated, gives no
  plug-in seam for a robot arm / custom controller, and leaves input unable to run
  as a remote service next to the SUT.
- **Element-level actuator API** (`click(locator)` on the actuator). Rejected: it
  drags DOM/locator knowledge into the device layer. Keeping the actuator to
  coordinate primitives makes a robot-arm plugin trivial to write.
- **Absolute pixel coordinates on the wire.** Rejected in favour of normalized
  coords: absolute px forces the orchestrator to know each device's resolution;
  normalization pushes that where it belongs (the device adapter).
- **gRPC always.** Rejected: needless latency/complexity for local desktop runs.

## Consequences

### Positive

- Removes the capture duplication; `visual_dom` owns both driven ports symmetrically.
- Users add a new way to actuate the SUT by dropping one file in
  `plugins/actuator/` - no core edits. Robot arm / capture card / serial / CAN all fit.
- Completes the distributed picture: **capture on the device, detect on a GPU box,
  actuate on the SUT/arm controller, orchestrate on the client** - each a
  strategy/backend selected by name, each optionally a gRPC service.
- RF library gets thinner and testable against a mock actuator.

### Negative / risks

- **Calibration is real work** for the robot-arm case (image -> physical mapping);
  the port design isolates it to that plugin, but it must be solved there.
- Auto-discovery **imports** plugin files (executes code) - trusted plugins only
  (same caveat as ADR-018).
- **Physical actuation is irreversible and can be unsafe** (a real arm moving).
  Plugins own their own safety limits / e-stop; out of scope for the port.
- gRPC channel is insecure by default (LAN/trusted use; TLS is a follow-up, as
  with ADR-017/018).
- One-time migration churn moving adapters out of the RF library.

### Follow-ups

- Phase 1: `ActuatorStrategy` + registry + relocate desktop/android built-ins +
  robot-arm example plugin.
- Phase 2: `protos/actuator.proto` + `actuator_server` + `GrpcActuatorStrategy`.
- Phase 3: rewire the RF library as a thin client; delete `adapters/*`.
- Factor a shared plugin-registry base (detector + capture + actuator repeat the
  same discovery code three times).
- TLS/auth on the actuator + capture gRPC channels.

## Files

**Phase 1 (implemented)**
- `src/visual_dom/actuator/base.py` - `ActuatorStrategy` (normalized-coord contract)
- `src/visual_dom/actuator/builtin/{desktop,android}.py` - relocated from RF adapters
- `src/visual_dom/actuator/registry.py` - `create_actuator` / `list_actuators` / `auto_select`
- `src/visual_dom/actuator/__init__.py`
- `plugins/actuator/example_robot_arm.py` - worked example (calibrate + homography)

**Phase 2 (implemented)**
- `protos/actuator.proto` - `Actuator` service (`Tap`, `TypeText`, `PressKey`, `Scroll`, `Swipe`, `HealthCheck`)
- `src/visual_dom/rpc/actuator_server.py` - server (runs on SUT / arm controller); `vizdom-actuator` / `start_actuator.bat`
- `src/visual_dom/actuator/builtin/grpc_remote.py` - `GrpcActuatorStrategy` (name `grpc`)

**Phase 3 (implemented)**
- `src/visual_gui_library/keywords/__init__.py` - `VisualGuiLibrary` holds capture +
  actuator strategies (config: `capture`/`actuator`/`*_target`), pixel<->normalized helpers
- `src/visual_gui_library/keywords/{capture,actions}.py` - call the strategies (normalized coords)
- removed `src/visual_gui_library/adapters/{base,desktop,android}.py`

## Related

- ADR-015 Pluggable Detector Backends (the strategy+registry pattern)
- ADR-017 Distributed Hexagonal + gRPC (the service pattern, `DetectorPort`)
- ADR-018 Pluggable Screenshot Capture (`CapturePort` - the read-side twin)
