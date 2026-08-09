# ADR-018: Pluggable Screenshot Capture (Strategy + Auto-Discovery + Service)

## Status

Accepted (Phase 1 + 2 implemented)

## Date

2026-07-26

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-26 | 0.1 | Phase 1: `CaptureStrategy` + auto-discovery registry + built-ins (windows/linux/android/camera) + plugin folder. gRPC service = Phase 2. |
| 2026-07-26 | 0.2 | Phase 2 implemented: gRPC `Capture` service (`capture_server`) + `GrpcCaptureStrategy` client (registered as `grpc`) + `protos/capture.proto`. Verified end-to-end (pixel-identical round-trip). |

## Context

The pipeline needs an input image. How a screenshot is obtained varies by target:
Windows/Linux desktop grab, Android via ADB, or non-standard sources (a camera
pointed at a physical display, a capture card, a frame-grabber SDK, a remote
feed). Users must be able to **plug in their own capture method** without editing
the codebase, and — like the detector — capture should be runnable **as a
service**, because it runs *where the app-under-test is* (which may be a different
machine or device than the pipeline).

This is the same strategy + registry pattern as the detector backends (ADR-015)
and the same gRPC-service pattern as the remote detector (ADR-017), applied to
input. In hexagonal terms it is a new driven port, **`CapturePort`**.

## Decision

### 1. Strategy base (`CaptureStrategy`)
Abstract `capture() -> np.ndarray` (BGR image, same as `cv2.imread`), plus
`name`, `platform`, `is_available()`, optional `close()`. Users subclass it.

### 2. Built-in adapters (`visual_dom/capture/builtin/`)
- `windows` — mss, or Pillow `ImageGrab` fallback.
- `linux` — mss (X11/Wayland, needs a display).
- `android` — `adb exec-out screencap -p` (optional `-s <serial>`).
- `camera` — `cv2.VideoCapture` (device index or stream URL) — the example of a
  non-screenshot source; pairs with the pipeline's `camera_mode` rectification.

### 3. Auto-discovery registry (`visual_dom/capture/registry.py`)
Discovers `CaptureStrategy` subclasses from (a) the built-in package and (b) a
**plugins folder** — `$VIZDOM_CAPTURE_PLUGINS`, else `<repo>/plugins/capture/`.
Any `.py` there defining a subclass with a unique `name` is registered on next
run. API: `create_capture(name, **kw)`, `list_captures()`, `register()`,
`auto_select()` (OS-appropriate default). Selection is by name from config/CLI.

Example plugin: `plugins/capture/example_static_image.py` (`static-image`) —
copy, rename, implement `capture()`, drop back in the folder.

### 4. Capture as a service (Phase 2 — implemented)
A gRPC `Capture` service mirroring the detector service (ADR-017):
- `protos/capture.proto` — `Grab() -> image bytes (+ w/h/strategy/timing)` and
  `HealthCheck()`; correlation `request_id`.
- `src/visual_dom/rpc/capture_server.py` — instantiates a `CaptureStrategy` once
  (by name, from CLI/config) and serves it. Runs **on the SUT host/device**.
  `--strategy <name>`, `--serial` (android), `--kw key=value` (ctor args),
  `--list`. Console script `vizdom-capture`; launcher `start_capture.bat`.
- `src/visual_dom/capture/builtin/grpc_remote.py` — `GrpcCaptureStrategy`,
  **registered as `grpc`** like any other strategy, so "capture from another
  machine" is selected exactly like a local grab: `create_capture("grpc",
  target="host:50053")` (or `$VIZDOM_CAPTURE_TARGET`). gRPC imports are lazy so
  the registry stays importable without grpcio; `is_available()` reports it.

Enables the distributed split: capture on the device, detection on a GPU box
(ADR-017), orchestration on the client — each a strategy/backend selected by name.

Stubs (`capture_pb2*.py`) are generated, not committed (see `rpc/__init__.py`).

## Alternatives Considered

- **Hard-code per-OS capture in the pipeline** — rejected: no user extensibility;
  can't add a camera/remote source without editing core.
- **setuptools entry-points for plugins** — more robust than folder-scan, but
  folder-scan matches the "drop a file in and it loads" request and needs no
  reinstall. Entry-points can be added later as a second discovery source.

## Consequences

### Positive
- Users add capture methods by dropping one file in `plugins/capture/` — no core
  edits, auto-loaded, selected by config.
- Consistent with detector backends (strategy + registry) and the gRPC service
  pattern — low conceptual overhead.
- Cleanly extends the hexagonal architecture (`CapturePort`).

### Negative / risks
- Auto-discovery **imports** plugin files (executes code) — trusted plugins only.
- Capture is platform/session-specific: needs a display (desktop), a connected
  device (android), or hardware (camera); `is_available()` reflects this.

### Follow-ups
- setuptools entry-point discovery as an optional second source.
- TLS/auth on the capture channel (currently insecure, LAN/trusted use).

## Files
**Phase 1 (local core)**
- `src/visual_dom/capture/base.py` — `CaptureStrategy`
- `src/visual_dom/capture/builtin/{windows,linux,android,camera}.py`
- `src/visual_dom/capture/registry.py` — discovery + `create_capture`/`list_captures`/`auto_select`
- `src/visual_dom/capture/__init__.py`
- `plugins/capture/example_static_image.py` — worked example

**Phase 2 (service)**
- `protos/capture.proto` — `Capture` service (`Grab`, `HealthCheck`)
- `src/visual_dom/rpc/capture_server.py` — server (runs on SUT); `vizdom-capture` / `start_capture.bat`
- `src/visual_dom/capture/builtin/grpc_remote.py` — `GrpcCaptureStrategy` (name `grpc`)

**Client wiring**
- `scripts/process_gui_image.py` — `--capture <name>` (or `auto`), `--capture-target`,
  `--capture-serial`, `--capture-kw key=value`, `--list-captures`. Grabs a frame
  (saved to `output/captures/`) then runs the pipeline; `image` arg now optional.
- `tools/visual_dom_viewer/ui/main_window.py` — "Src:" toolbar combo (window
  handler | discovered strategies) + arg field. Strategy sources grab directly
  (no Connect needed); "window (handler)" keeps the existing platform-handler path.

## Usage
```
# local full-screen grab -> DOM
python scripts/process_gui_image.py --capture windows --ocr tesseract

# capture on the device under test, detect on a GPU box, orchestrate here
start_capture.bat --strategy windows            # on the SUT host
python scripts/process_gui_image.py --capture grpc --capture-target sut-host:50053 \
    --detector grpc --detector-target gpu-host:50051

python scripts/process_gui_image.py --list-captures   # what's available here
```
