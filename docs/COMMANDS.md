# Command Reference

The commands you run day to day. Every command accepts `--help` for the full
list of options. Commands marked *source checkout* need a clone of the
repository (see [Setup](uv-setup.md)); the others come with
`pip install "vizdom[robot]"` or with the VizDOM Studio installer.

## Run a Robot Framework suite

```bash
robot --outputdir results my_suite.robot
```

The library is `VisualGuiLibrary`; its keywords are in
[Using as a Client](USAGE.md#3-robot-framework). Settings come from
`vizdom.config.json` in the working directory (see
[Configuration & Sessions](CONFIGURATION.md)).

## Start the services

Each service is a console script installed with the `grpc` extra. Stop it with
Ctrl+C.

```bash
vizdom-detector --backend omniparser --port 50051   # GPU host
vizdom-detector --backend uied --port 50051         # any host, CPU only, no weights
vizdom-capture  --strategy windows --port 50053     # machine that shows the app
vizdom-actuator --strategy desktop --port 50054     # machine that receives the input
```

| Service | Main options |
|---|---|
| `vizdom-detector` | <code>--backend uied&#124;yolo&#124;omniparser&#124;modular</code> (default `omniparser`), <code>--captioner none&#124;florence&#124;ocr</code> (modular), `--ocr ENGINE`, `--no-gpu`, `--port` |
| `vizdom-capture` | <code>--strategy windows&#124;linux&#124;android&#124;camera&#124;&lt;plugin&gt;</code>, `--window-title`, `--serial` (Android), `--list`, `--port` |
| `vizdom-actuator` | <code>--strategy desktop&#124;android&#124;&lt;plugin&gt;</code>, `--window-title`, `--serial` (Android), `--list`, `--port` |

`--list` prints the strategies that are installed, including plugins. The
services have no TLS and no authentication: run them on an isolated test
network only.

## Analyze one screenshot

```bash
# source checkout: file or live capture in, DOM JSON out
python scripts/process_gui_image.py screenshot.png --ocr easyocr -O dom.json -v dom.png
python scripts/process_gui_image.py --capture windows --ocr easyocr -t
python scripts/process_gui_image.py screenshot.png --detector grpc --detector-target gpu-host:50051
```

| Option | Meaning |
|---|---|
| `--capture NAME` | grab the screen with a capture strategy instead of reading a file (`--list-captures` lists them) |
| `--ocr`, `-o` | `easyocr`, `paddleocr` or `tesseract` (default: no OCR) |
| `--detector` | `uied` (default), `yolo`, `omniparser`, `hybrid`, `grpc` |
| `--output`, `-O` | DOM JSON path |
| `--visualize`, `-v` | image with the detected boxes |
| `--print-tree`, `-t` | print the element tree |

With only the package installed, the same pipeline runs as
`python -m visual_dom.core.domain.pipeline screenshot.png --ocr easyocr -o dom.json`,
or from Python through `visual_dom.connect()` ([Using as a Client](USAGE.md)).

## VizDOM Studio

Installed with the Studio installer, it is a normal Windows application.
To run it from a source checkout:

```bash
cd tools/vizdom_studio
npm install
npm run dev        # development window
npm run dist       # build the Windows installer into release/
```

Studio starts its Python bridge with the interpreter in `VIZDOM_PYTHON`
(the installer's bundled Python when installed).

## Visual DOM Viewer (PyQt)

```bash
python -m tools.visual_dom_viewer    # source checkout
```

| Action | Shortcut |
|---|---|
| Connect… | `Ctrl+N` |
| Capture & Analyze | `F5` |
| Re-Analyze | `F6` |
| Click selected element via the actuator | `Ctrl+T` |
| Open image… | `Ctrl+O` |
| Analyze image… | `Ctrl+Shift+O` |
| Open DOM… | `Ctrl+D` |
| Export to Robot… | `Ctrl+E` |
| Zoom in / out | `Ctrl++` / `Ctrl+-` |
| Fit to window / actual size | `Ctrl+0` / `Ctrl+1` |
| Settings | `Ctrl+,` |

## Evaluate a DOM against ground truth

```bash
python -m visual_dom.evaluation.cli predicted.json ground_truth.json
python -m visual_dom.evaluation.cli pred.json gt.json -f markdown -o report.md
python -m visual_dom.evaluation.cli --batch outputs/ ground_truths/ -f json -o results.json
```

Options: `--format text|json|markdown|html`, `--output`, `--iou-threshold`
(default 0.5), `--no-hierarchy`, `--no-locators`. The benchmarks behind the
published results are described in [Evaluation](EVALUATION.md).

## Tests (source checkout)

```bash
python -m pytest tests/unit          # fast, no model, no screen
python -m pytest tests/architecture  # dependency rules of the hexagonal core
python -m pytest tests/integration   # needs OCR engines and sample images
python -m pytest tests/unit -k locator
```

## Source checkout chores

```bash
python scripts/gen_protos.py         # generate the gRPC stubs (once after cloning, and after editing protos/)
python scripts/setup_omniparser.py   # fetch the OmniParser weights for the GPU detector
python scripts/setup_tesseract.py    # find Tesseract on Windows and check it works
python tools/docs_overview/build_overview.py && properdocs serve -f properdocs.yml   # docs preview
```

## Troubleshooting

| Problem | Fix |
|---|---|
| More detail in the log | set `VIZDOM_LOG_LEVEL=DEBUG` |
| `ModuleNotFoundError` for a `..._pb2` module | source checkout: run `python scripts/gen_protos.py` |
| `No module named 'grpc'` | install the `grpc` extra: `pip install "vizdom[grpc]"` |
| First analysis is slow | EasyOCR downloads its models once (about 100 MB) |
| `Tesseract not found` | install Tesseract and put it on the PATH (the Studio installer bundles it) |
| `CUDA out of memory` on the detector | `--no-gpu`, or `--backend uied` |
