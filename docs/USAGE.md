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
| Detector | 50051 | `python -m visual_dom.rpc.detector_server --backend omniparser --port 50051` |
| Capture | 50053 | `python -m visual_dom.rpc.capture_server --strategy windows --port 50053` |
| Actuator | 50054 | `python -m visual_dom.rpc.actuator_server --strategy desktop --port 50054` |

On Windows the `start_detector.bat` / `start_capture.bat` / `start_actuator.bat`
launchers wrap these (and set `PYTHONPATH`). The detector server also accepts
`--icon-detect` / `--icon-caption` / `--omniparser-root` / `--yolo-model`
(OmniParser auto-detects `models/omniparser/` + `third_party/OmniParser`).

Prerequisite (once): `pip install grpcio grpcio-tools`.

### Start the detector service (GPU host)

```bash
python -m visual_dom.rpc.detector_server \
    --backend omniparser --port 50051 \
    --icon-detect  models/omniparser/icon_detect/model.pt \
    --icon-caption models/omniparser/icon_caption_florence
```

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
from visual_dom.cv.pipeline import VisualDOMPipeline
pipe = VisualDOMPipeline(detector="grpc", detector_kwargs={"target": "gpu-host:50051"})
result = pipe.process("screenshot.png")   # {"elements": [...], "image_size": {...}}
```

Capture and actuation have matching clients when you need them:

```python
from visual_dom.capture import create_capture
from visual_dom.actuator import create_actuator

shot = create_capture("grpc", target="sut-device:50053").capture()   # BGR frame
create_actuator("grpc", target="sut-device:50054").tap(0.5, 0.5)      # normalized xy
```

Coordinates on the actuator port are **normalized** `[0,1]` (resolution-independent);
the service maps them to device pixels.

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

Locate elements by **role/text/spatial** rather than pixel coordinates — e.g.
`text=Login`, `hint=Email`, `role=button`, `right_of="Label"`, `below="Title"`,
`within="Form"` — so tests survive layout and theme changes.

> **Tip.** For icon-only controls whose caption can be unreliable (a bare `□`
> maximize glyph, small toolbar icons), prefer `role=button` + a spatial relation
> over `text=`, since the visual caption is a best-effort hint, not a stable id.
