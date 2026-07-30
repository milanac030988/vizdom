# Demo — Robot Framework GUI test on Windows (end to end)

A complete, runnable flow: **start the detector service → configure a session →
run a Robot Framework test** that drives the Windows Calculator purely from its
Visual DOM (no accessibility tree used).

```
detector service (:50051, warm OmniParser)
        ▲ gRPC
        │
  calculator_demo.robot ──uses──► VisualGuiLibrary
        │                          ├─ capture  = windows   (in-process)
        │                          └─ actuator = desktop   (in-process)
        └─ Connect vizdom.config.json → Dump Visual DOM → Click/Type/Assert
```

Files here: [`vizdom.config.json`](vizdom.config.json) (session config) and
[`calculator_demo.robot`](calculator_demo.robot) (the test).

## Prerequisites (once)

```bat
:: from the repo root, in your Python 3.9 env
pip install -e ".[ocr]"          & :: engine + easyocr
pip install grpcio grpcio-tools robotframework
:: OmniParser weights under models\omniparser\  (scripts\setup_omniparser.py),
:: or edit the config to use a lighter backend (see "No-service variant" below).
```

## Step 1 — Start the detector service  (Terminal 1)

The detector loads the heavy model **once** and serves the test over gRPC:

```bat
cd <repo-root>
start_detector.bat --backend omniparser
:: equivalent to:
:: python -m visual_dom.rpc.detector_server --backend omniparser --port 50051
```

Wait until it logs that it is **ready / HealthCheck** — leave this terminal running.

## Step 2 — (optional) Review the config

[`vizdom.config.json`](vizdom.config.json) already points the detector at the
service and uses EasyOCR + Windows capture:

```json
{
  "detector": { "backend": "grpc", "grpc_target": "localhost:50051" },
  "ocr":      { "engine": "easyocr" },
  "capture":  { "strategy": "windows" }
}
```

Regenerate a full annotated template any time with
`python -m visual_dom.config --init my.config.json`, or validate one with
`python -m visual_dom.config --check vizdom.config.json`.

## Step 3 — Run the test  (Terminal 2)

```bat
cd <repo-root>
set PYTHONPATH=%CD%\src
robot examples\windows_calculator_demo\calculator_demo.robot
```

What it does: launches `calc.exe`, `Connect`s the session, `Dump Visual DOM`,
then clicks `7`, `+`, `5`, `=` by their on-screen labels and asserts `12` appears.
Results land in `report.html` / `log.html` / `output.xml` in the current folder.

## No-service variant (nothing to start)

If you don't want to run a service, make the detector in-process — change the config's
detector block to:

```json
"detector": { "backend": "omniparser" }
```
(or `"uied"` for a CPU-only, weight-free run) and **skip Step 1**. The test file is
unchanged.

## Troubleshooting

- **`failed to connect to localhost:50051`** — the detector service (Step 1) isn't
  running or is still loading the model; wait for its ready log, or check the port.
- **Element not found (`text=7`, `text="+"`, …)** — locators match what VizDOM
  *reads from pixels*, which varies with Windows version, theme, and DPI. Open the
  generated DOM (`Dump Visual DOM` returns it; or run the Viewer, `start_viewer.bat`)
  to see the exact `text`/`label` values and adjust the locators. Operator glyphs
  (`+`, `=`) come from symbol detection; digits and the display come from OCR.
- **Calculator not focused / off-screen** — capture is full-screen here, so keep the
  Calculator visible and in the foreground (per-window targeting is planned, ADR-021).
- **Wrong OCR / slow first run** — the first EasyOCR run downloads models (~100 MB).
