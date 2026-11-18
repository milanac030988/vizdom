# VizDOM Studio

A desktop GUI for VizDOM (Electron + React + TypeScript): capture an
application, inspect the Visual DOM, prove a locator, export a Robot
Framework resource. It sits beside the PyQt Viewer (`tools/visual_dom_viewer`)
and reads and writes the same session folders, so either tool opens the
other's results.

```
Electron renderer (React)  ──HTTP + WebSocket, 127.0.0.1, per-launch token──▶  Python bridge (tools/vizdom_bridge)
        ▲                                                                              │
Electron main: starts the bridge, native dialogs,                         visual_dom.connect().analyze(),
hides the window while a capture is taken                                 capture / actuator registries,
                                                                          LocatorResolver, the Viewer's
                                                                          locator + Robot exporters
```

All pipeline logic stays in Python: a locator Studio resolves is resolved by
the same `LocatorResolver` a suite uses, and the exported string is the one the
PyQt Viewer would write.

## Run

Needs Node 20+ and a Python with VizDOM's dependencies plus `fastapi` and
`uvicorn` (`D:\Python\python39` on the development machine).

```powershell
cd tools\vizdom_studio
npm install
$env:VIZDOM_PYTHON = "D:\Python\python39\python.exe"   # or set it in Settings > Studio
npm run dev        # hot-reloading development build
npm run build; npm start
```

If the bridge cannot start, Studio says why and asks for the interpreter. The
choice is remembered in the app's `prefs.json`.

## Installer

The all-in-one Windows installer is built by the Release workflow
(`.github/workflows/release.yml`) on every `v*` tag. To build it by hand
(needs Node 20+, [uv](https://docs.astral.sh/uv/) and internet access):

```powershell
# from the repository root
python scripts/gen_protos.py
uv build --wheel
./tools/vizdom_studio/scripts/bundle_python.ps1 -Wheel (Get-Item dist/*.whl).FullName
cd tools/vizdom_studio
npm install
npm run dist            # -> release/VizDOM-Studio-Setup-<version>.exe
```

`bundle_python.ps1` fills `bundle/` (git-ignored), which electron-builder copies
into the app's `resources/`:

| Folder | Contents |
|---|---|
| `python/` | relocatable CPython 3.12 with VizDOM, the Robot Framework library (`[robot,studio]` extras) and CPU PyTorch |
| `vizdom/` | `tools/vizdom_bridge`, `tools/visual_dom_viewer`, `plugins/`, the example config |
| `easyocr/` | EasyOCR's English models (no download on first use) |
| `tesseract/` | a copy of `C:\Program Files\Tesseract-OCR`, when installed on the build machine |

The installed Studio uses that Python unless `VIZDOM_PYTHON` or Settings names
another, runs the bridge with `VIZDOM_REPO` = the `vizdom/` folder, and keeps the
user's config, sessions and plugins in `Documents\VizDOM` (`VIZDOM_HOME`).

## What it does

| Area | |
|---|---|
| **Capture & Analyze** (F5) | Pick a window (or full screen) in the toolbar. Studio hides itself, grabs the frame through the capture registry (window-scoped with geometry, ADR-021) and analyses it with the session config. |
| **Re-analyze** (F6) | Same screenshot, current settings. Each run is a new session. |
| **Open** | Analyze an image file (Ctrl O), open a `dom_result.json` with the screenshot beside it (Ctrl D), or browse sessions. |
| **Inspect** | Element list (search, reading order or hierarchy), zoomable canvas coloured by element type (legend doubles as a filter), inspector with the exported locator and the DOM's other locators. |
| **Locator Lab** | Type a locator; it is resolved live against the screen. Exactly one match is green, an ambiguous one outlines every match in amber, and `desc=` asks before it calls the grounding models. |
| **Try click** | Captures again, resolves the locator on the fresh screen as a test would, raises the window and clicks through the configured actuator (ADR-028), then captures the result. Asks once per launch. |
| **Export** (Ctrl E) | Marked elements, captioned elements or everything, with a live preview of the `.resource`. |
| **Sessions** (Ctrl 2) | Gallery of `output/sessions`, shared with the Viewer. |
| **Services** (Ctrl 3) | Configure (each server's own options), start, stop and watch the detector, capture and actuator gRPC services, with the exact command line shown. Options are remembered (`output/.studio/services.json`), can be filled from the session config, and a running service can be made the one the analysis uses. Services started here stop when Studio closes; ones started elsewhere are shown, not stopped. |
| **Settings** (Ctrl ,) | The session config: detector, OCR, capture source, `desc=` tiers and models, refiner, actuator, validated by `VizDomConfig` itself. **Open…** any config file, **Save** or **Save as…**; the file in use is remembered for the next launch (default `vizdom.config.json` at the repository root, or `$env:VIZDOM_CONFIG`). |
| **Command palette** (Ctrl K) | Every command, every element on screen, recent sessions. |

One analysis or trial runs at a time; progress is streamed from the bridge.

## Layout

```
tools/vizdom_bridge/        Python: FastAPI app (server.py), session folders, services
tools/vizdom_studio/
  src/main/                 Electron main: window, bridge supervisor, dialogs
  src/preload/              the window.studio API exposed to the renderer
  src/renderer/src/         React app: views/, components/, store.ts (zustand), api.ts
tests/unit/test_vizdom_bridge.py
```
