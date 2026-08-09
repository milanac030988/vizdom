# Demo — Robot Framework GUI test on Windows (fully distributed)

A complete, runnable flow: **start the three gRPC services → configure a session →
run a Robot Framework test** that drives the Windows Calculator purely from its
Visual DOM (no accessibility tree used), with every button located by
**text + description fallback**.

```
detector :50051   (heavy model — e.g. a GPU host)
capture  :50053   (the machine showing the Calculator)
actuator :50054   (the machine receiving the clicks)
        ▲ gRPC          ▲ gRPC            ▲ gRPC
        └────────────────┴─────────────────┘
                         │
              vizdom.config.json  ← selects all three by name
                         │
   calculator_demo.robot ──uses──► calculator_locators.resource
        Connect → Dump Visual DOM → Compute → Verify
```

Files here:

| File | Purpose |
|---|---|
| [`vizdom.config.json`](vizdom.config.json) | session config — **detector, capture and actuator all via gRPC** |
| [`calculator_locators.resource`](calculator_locators.resource) | button definitions as `text=… \|\| desc=…` chains + `Enter Number` / `Compute` keywords |
| [`calculator_demo.robot`](calculator_demo.robot) | the two test cases |

## What the suite does, step by step

A full sequence diagram of this exact suite — services, suite setup, both tests,
teardown, and where each capture/detector call happens — is on the docs site under
[Using as a Client](https://milanac030988.github.io/vizdom/USAGE/) (source:
`docs/diagrams/robot_suite_sequence.puml`). The short version: the app is opened,
connected and dumped **once**; every click after that is a cached-DOM lookup plus
one normalized tap; the whole suite makes **2** detector calls and the second test
case adds none.

## Why every button has two locators

Each control is a **fallback chain** (ADR-024):

```robotframework
${BTN_7}        text=7 || desc="digit seven button"
${BTN_DIVIDE}   text="÷" || desc="divide button"
```

* `text=` is a free, deterministic lookup in the Visual DOM — tried **first**, so
  the happy path costs nothing extra.
* `desc=` is the safety net for the failures this project actually measured: OCR
  misreading a small glyph, or an unstable icon caption. Operator keys have no
  readable label at all — their `text` comes from the **symbol reader** (a literal
  pixel read) and their canonical label ("Divide") is what `desc` matches.
* An alternative is abandoned when it matches **nothing** *or* is **ambiguous** —
  but before an ambiguous one is abandoned, the chain's `desc=` **arbitrates**
  among the matched elements (e.g. the `±` key's `+/-` glyph can OCR as `+`,
  making `text="+"` match two keys; `desc="plus button"` picks the real one).
  When a fallback wins, the library logs a **warning naming the stale primary** —
  treat it as a prompt to update that locator.

Window controls invert the order (`desc=` first), because a title-bar icon's
caption *is* its real name while its glyph read is just `×`.

## Why the test raises the window first

Both tests call `Focus Calculator` (→ `Bring App To Front`) right after `Connect`.
VizDOM captures the **whole screen** and clicks by **coordinate**, so a window
covering the Calculator would make it build a DOM of the wrong application and send
the clicks there too — with no way to notice from the DOM alone (ADR-021).

The title comes from `capture.window_title`; the raise happens **on the machine
running the capture/actuator service**, through their `Focus` RPC, so it works the
same in this fully distributed setup as in-process. Success is verified, so an
unfocusable or ambiguous window fails the test instead of producing a confusing
downstream error. Set `"focus_before_capture": true` in the config to raise the app
before *every* grab instead of calling the keyword.

### Even better: capture only the Calculator

Add `"window_scope": true` to the `capture` section and the service crops to the
Calculator's client area, so the DOM contains **just the application** instead of the
whole desktop:

```json
"capture": { "strategy": "grpc", "target": "localhost:50053",
             "window_title": "Calculator", "window_scope": true }
```

The crop's geometry travels back with the pixels, so clicks stay correct — including
for a Calculator on a second monitor, whose screen coordinates can be negative
(verified: a 53-element Calculator-only DOM at 402×658, clicking `7` then `8` on a
window at x = −831 produced `78`). The test file does not change.

## Prerequisites (once)

```bat
:: in your Python 3.9 env, from the repo root
pip install -e ".[ocr]"
pip install grpcio grpcio-tools robotframework
:: detector host also needs the OmniParser weights (scripts\setup_omniparser.py);
:: paths auto-resolve. Or use --backend uied for a CPU-only, weight-free run.
:: Pass --ocr easyocr so the text ensemble runs on the service (it cannot cross gRPC).
```

## Step 1 — Start the three services

Each runs until `Ctrl-C`; give each its own terminal. On the machine that owns the
relevant resource (all three can be the same machine for a first run).

```bat
:: Terminal 1 — detector (the heavy model, loaded once, served warm)
start_detector.bat --backend omniparser --ocr easyocr
:: CPU-only alternative:  start_detector.bat --backend uied

:: Terminal 2 — capture (must run where the Calculator is visible)
start_capture.bat --strategy windows --window-title "Calculator"

:: Terminal 3 — actuator (must run where the clicks should land)
start_actuator.bat --strategy desktop --window-title "Calculator"
```

Equivalent any-OS commands:

```bash
python -m visual_dom.adapters.inbound.grpc.detector_server --backend omniparser --ocr easyocr --port 50051
python -m visual_dom.adapters.inbound.grpc.capture_server  --strategy windows   --port 50053 --window-title "Calculator"
python -m visual_dom.adapters.inbound.grpc.actuator_server  --strategy desktop   --port 50054 --window-title "Calculator"
```

Wait for each to report ready before continuing.

## Step 2 — Point the config at them

[`vizdom.config.json`](vizdom.config.json) already selects all three by name:

```json
{
  "detector": { "backend": "grpc",  "grpc_target": "localhost:50051" },
  "capture":  { "strategy": "grpc", "target":      "localhost:50053",
                "window_title": "Calculator" },
  "actuator": { "strategy": "grpc", "target":      "localhost:50054" },
  "ocr":      { "engine": "easyocr" },
  "grounding":{ "tiers": ["lexical"] }
}
```

Replace `localhost` with the host running each service to spread the run across
machines — **the test file does not change**. Validate the file any time with
`python -m visual_dom.config --check vizdom.config.json`.

## Step 3 — Run the test  (a fourth terminal)

```bat
run_demo.bat
```

This example is **Windows-only** — it launches `calc.exe` and locates keys in
the Windows Calculator. On Linux/macOS the services and the library work the
same way (`./start_detector.sh`, `./start_capture.sh`, `./start_actuator.sh`),
but point the runner at a suite for an application that exists there:
`./run_demo.sh my_suite.robot`.

The launcher (repo root) pins the project's Python, sets `PYTHONPATH`, and writes
results to `output\demo_run`. **Do not launch the `.robot` file directly** — that
runs whatever Python owns the `.robot` file association, typically one without
`easyocr`, and fails fast with *"OCR engine 'easyocr' is not installed"*.
Equivalent manual command:

```bat
cd <repo-root>
set PYTHONPATH=%CD%\src
"%VIZDOM_PY%" -m robot --outputdir output\demo_run examples\windows_calculator_demo\calculator_demo.robot
```

Two cases run: `7 + 5 = 12`, and `8 ÷ 2` verified by re-reading the display from
the live screen (`Verify Element Value`, ADR-023). Results land in `report.html` /
`log.html` / `output.xml`.

## No-service variant (nothing to start)

Run everything in-process — useful for a first smoke test. Replace the three port
sections with:

```json
{
  "detector": { "backend": "omniparser" },
  "capture":  { "strategy": "windows" },
  "actuator": { "strategy": "desktop" }
}
```

…or delete `capture`/`actuator` entirely to accept the platform defaults. Skip
Step 1; the test file is unchanged.

## Troubleshooting

- **`OCR engine 'easyocr' is not installed`** — the run used the wrong Python
  (usually from launching the `.robot` file directly). Use `run_demo.bat`.
- **A test failed — what was on screen?** Every failing library keyword attaches a
  screenshot to `log.html` (taken through the capture service, so it shows the
  machine under test). Open the log and expand the failing keyword.
- **`failed to connect to localhost:5005x`** — that service isn't running yet (or
  is still loading its model). Start it / wait for its ready log.
- **Clicks land on the wrong machine** — `actuator.target` points at the wrong
  host. Capture and actuator should normally be the *same* machine (you must act
  on the screen you are looking at).
- **A locator warning on every run** — the `text=` primary is stale for that
  button (theme/DPI/OCR drift). Read the warning, then update the primary; the
  `desc=` fallback is keeping the test green in the meantime.
- **`Could not bring 'Calculator' to the foreground`** — the window isn't open, its
  title is ambiguous (another window contains "Calculator"), or Windows refused the
  raise. Close the competing window, or click the Calculator once by hand and re-run.
- **Element not found for a digit** — locators match what VizDOM *reads*. Open the
  DOM (or the Viewer, `start_viewer.bat`) to see the actual `text`/`label`, and
  adjust. Operator glyphs come from symbol detection, digits from OCR.
- **`grounding.tiers` includes `slm`/`vlm`** — those need a running Ollama; the
  demo pins the model-free `lexical` tier so it works offline.
