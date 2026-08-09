# Writing Capture & Actuator Plugins

VizDOM's driven ports are extensible without touching core code: drop a Python
file in the plugins folder, and the registry discovers it at startup (ADR-018 /
ADR-019). This page walks through writing a **capture** plugin (a new way to
obtain screenshots) and an **actuator** plugin (a new way to deliver input) —
the two ports users most often extend, e.g. for a frame grabber, a serial
touch-injector, or a robot arm. (Detector backends are pluggable too — see
ADR-015 — via the same pattern.)

Two runnable examples ship with the repo and are the recommended starting
point — copy, rename, replace the body:

| Example | Demonstrates |
|---|---|
| [`plugins/capture/example_static_image.py`](https://github.com/milanac030988/vizdom/blob/main/plugins/capture/example_static_image.py) | minimal capture plugin (replays a PNG; env-configured; `is_available` gate) |
| [`plugins/actuator/example_robot_arm.py`](https://github.com/milanac030988/vizdom/blob/main/plugins/actuator/example_robot_arm.py) | actuator with a **calibration homography** (image px → physical arm XY) |

## How discovery works

At first use, each registry imports:

1. the built-in strategies (`visual_dom.adapters.outbound.<port>.builtin`), and
2. every `.py` file in the plugins folder —
   `$VIZDOM_CAPTURE_PLUGINS` / `$VIZDOM_ACTUATOR_PLUGINS` if set, else
   `<repo>/plugins/capture/` and `<repo>/plugins/actuator/`.

Any subclass of the port's base with a unique `name` is registered; you select
it **by that name** everywhere a built-in name works. Nothing else to wire up.

!!! warning "Plugins are imported"
    Discovery executes the plugin file's top-level code. Only place files you
    trust in the plugins folder.

List what was discovered at any time:

```bash
python -m visual_dom.adapters.inbound.grpc.capture_server --list
python -m visual_dom.adapters.inbound.grpc.actuator_server --list
```

## A capture plugin, step by step

A capture strategy is *a way to obtain one screenshot*. The whole required
contract is one method:

```python
# plugins/capture/my_grabber.py
import numpy as np
from visual_dom.core.ports.outbound.capture_port import CaptureStrategy

class MyGrabber(CaptureStrategy):
    name = "my-grabber"          # unique registry name — how users select it
    platform = "any"             # "windows" | "linux" | "android" | "any" (informational)
    description = "Frames from the FooCorp capture card."

    def __init__(self, device: int = 0):
        self._device = device    # constructor args: see "Passing parameters"

    @classmethod
    def is_available(cls) -> bool:
        # Cheap check: SDK importable / device present. Must never raise.
        try:
            import foocorp_sdk  # noqa: F401
            return True
        except Exception:
            return False

    def capture(self) -> np.ndarray:
        # Return ONE frame as BGR uint8 (H, W, 3) — the format cv2.imread
        # produces, ready for the pipeline. Raise on a genuine failure.
        ...
```

That is a complete, selectable plugin. The **optional hooks** buy extra
integration; implement only what your source can honestly answer:

| Hook | Default | Implement when… |
|---|---|---|
| `describe_target() -> dict` | `{}` | you can name *what* was captured (window title / activity / device) — feeds session provenance (ADR-018). Mark inferred values with `guess_source`. |
| `focus_target(title) -> bool` | `False` | you can raise the application under test (ADR-021). Return `True` **only on verified success** — an optimistic `True` turns an OS refusal into a silently wrong screenshot. |
| `capture_window(title) -> CaptureFrame` | `None` | you can capture *just* the app's window. Return the crop **with its geometry** (`origin`, `device_origin`, `device_size`) so clicks computed on it map back to the device — never a bare crop. |
| `frame_geometry()` | `None` | your plain frames sit inside a larger coordinate space (e.g. one monitor of a multi-monitor desktop). `None` means "normalize against the image itself" — correct for most cameras and single-screen devices. |
| `close()` | no-op | you hold resources (device handles, sessions). |

## An actuator plugin, step by step

An actuator is *a way to deliver input*, deliberately primitive: tap / type /
key / scroll / swipe. It knows nothing about the DOM — locator resolution stays
in the client.

**The coordinate contract is the one thing you must get right.** Actions arrive
as **normalized `(nx, ny)` in `[0, 1]`** plus the source `image_size`. Your job
is mapping that to *your* device's space:

- **Linear device** (its input space is a rectangle): just override
  `device_size()` — the base class does the multiplication. If the space does
  not start at (0, 0) (multi-monitor desktops), also override `device_origin()`.
- **Non-linear device** (robot arm, projector): override `_to_device()` with
  your calibration — the shipped robot-arm example applies a 3×3 homography
  obtained by tapping known reference points once.

```python
# plugins/actuator/my_touch.py
from typing import Optional, Tuple
from visual_dom.core.ports.outbound.actuator_port import ActuatorStrategy

class MyTouchInjector(ActuatorStrategy):
    name = "my-touch"
    platform = "any"
    description = "Touch events over the FooCorp serial protocol."

    def __init__(self, port: str = "COM3"):
        self._port = port

    def device_size(self, image_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        return (1920, 1080)                      # the panel's input resolution

    def tap(self, nx, ny, image_size=None, click_type="single"):
        x, y = self._to_device(nx, ny, image_size)
        self._send(f"TAP {x} {y}")

    def type_text(self, text: str) -> None: ...
    def press_key(self, key: str) -> None: ...   # "enter", "tab", "ctrl+a", ...
    def scroll(self, nx, ny, direction="down", amount=1, image_size=None): ...
    def swipe(self, nx1, ny1, nx2, ny2, image_size=None, duration=0.3): ...
```

All five primitives are abstract — implement them all (raise
`NotImplementedError` with a clear message for ones your hardware genuinely
cannot do). Optional: `focus_target(title)` (ADR-021, same verified-success
rule as capture) and `close()`.

Keeping the wire contract normalized is what lets the same test drive a local
desktop, an Android phone, or your plugin without change — the [calculator
demo](https://github.com/milanac030988/vizdom/tree/main/examples/windows_calculator_demo)
switches transports by config only.

## Logging from a plugin

Use the project logger rather than `print`, and your lines join everything else —
timestamped and module-tagged in `logs/vizdom.log`, on the console, and (under
Robot Framework) inside the test log beneath the keyword that triggered them:

```python
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)      # re-homed under the visual_dom namespace
log.info("FooCorp SDK opened device %s", self._device)
log.warning("frame dropped; retrying")
```

`print` is reserved for the user-facing stdout of CLI entry points. Set
`VIZDOM_LOG_LEVEL=DEBUG` when diagnosing your plugin.

## Selecting your plugin

By its `name`, exactly like a built-in:

```json
{ "capture": { "strategy": "my-grabber" }, "actuator": { "strategy": "my-touch" } }
```

```robotframework
Library    VisualGuiLibrary    capture=my-grabber    actuator=my-touch
```

```bat
start_capture.bat  --strategy my-grabber
start_actuator.bat --strategy my-touch --kw port=COM7
```

Running your plugin **as a service** (the `start_*.bat` form) is how it joins a
distributed setup: the service runs on the machine that owns the hardware, and
clients select `strategy: "grpc"` + its `host:port` — your plugin needs no gRPC
code of its own.

## Passing parameters

Constructor keyword arguments reach a plugin three ways:

1. **Python**: `create_capture("my-grabber", device=1)`;
2. **service CLI**: `--kw device=1` (repeatable; values arrive as strings —
   convert in `__init__`);
3. **environment variables**, the examples' pattern (`VIZDOM_STATIC_IMAGE`,
   `VIZDOM_ROBOT_ARM_PORT`) — the practical choice when selecting the plugin
   through the JSON config, whose `capture`/`actuator` sections carry only the
   strategy name and target.

## Checklist before relying on it

- [ ] `--list` shows your plugin with `available=True` on the target machine.
- [ ] `capture()` returns BGR uint8 `(H, W, 3)` — a quick smoke:
      `cv2.imwrite("probe.png", create_capture("my-grabber").capture())`.
- [ ] Actuator round-trip: tap the four corners at `(0,0) (1,0) (0,1) (1,1)`
      normalized and confirm where they land — this catches inverted axes and
      calibration errors before a test suite does.
- [ ] `is_available()` returns `False` (never raises) on a machine without your
      hardware — otherwise you break strategy auto-selection for everyone.
- [ ] Optional hooks return their honest defaults rather than guessing.
