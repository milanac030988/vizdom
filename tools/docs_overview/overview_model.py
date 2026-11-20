"""The content of the interactive system overview (docs home + System Overview page).

Edit this file, then run ``python tools/docs_overview/build_overview.py``.
Never edit the generated files (docs/overview/*.svg, docs/system-overview.md, the
marked block in docs/index.md).

Each component has an id (the section anchor is ``c-<id>``), a box in the overview
(``box`` = x, y, width, height in the overview's coordinates, ``None`` = shown only
in the component diagrams), and the text of its section.
"""

# --- bands of the overview (title, y, height, style, title x) -------------------
# The title x keeps each band title clear of the arrows that cross the band.
BANDS = [
    ("Where you work", 20, 140, "work", 38),
    ("VizDOM engine  ·  runs inside your process", 190, 360, "engine", 38),
    ("Optional services  ·  gRPC", 580, 120, "services", 172),
    ("Machine under test", 730, 100, "aut", 172),
]
WIDTH, HEIGHT = 1160, 850

# kind -> colour family (fill, stroke, text accent); see build_overview.PALETTE
COMPONENTS = [
    {
        "id": "rf", "kind": "entry", "title": "Robot Framework library",
        "sub": "Library    VisualGuiLibrary", "box": (40, 60, 330, 84),
        "summary": "Write GUI tests in Robot Framework against what VizDOM sees on the screen.",
        "body": """
`VisualGuiLibrary` gives a Robot suite keywords that work on the Visual DOM:
`Connect`, `Dump Visual DOM`, `Click Visual`, `Type Text Visual`,
`Visual Should Exist`, `Wait Until Visual Appears`, `Verify Element Value`,
`Bring App To Front` and more.

```robotframework
*** Settings ***
Library    VisualGuiLibrary

*** Test Cases ***
Save The Document
    Connect              vizdom.config.json
    Bring App To Front   Notepad
    Dump Visual DOM
    Click Visual         text=Save || desc="save button"
```

The suite parses a screen once (`Dump Visual DOM`); every click and check after
that is resolved against that DOM until the layout changes. When a keyword fails,
the library saves a screenshot of the application window.

**Install:** `pip install "vizdom[robot]"`, or use the Python that comes with the
VizDOM Studio installer.
""",
        "docs": [("Using as a Client", "USAGE.md")],
    },
    {
        "id": "studio", "kind": "entry", "title": "VizDOM Studio",
        "sub": "desktop app (Windows installer)", "box": (415, 60, 330, 84),
        "summary": "Look at an application the way VizDOM does, and build locators by hand.",
        "body": """
| Area | What you do there |
|---|---|
| **Capture & Analyze** (F5) | Pick a window; Studio hides itself, captures it and builds its Visual DOM |
| **Inspect** | Element list, zoomable canvas coloured by element type, the locators of each element |
| **Locator Lab** | Type a locator and see live what it matches: one match is green, an ambiguous one amber |
| **Try click** | Capture again, resolve the locator as a test would, click through the actuator |
| **Export** (Ctrl E) | Write a Robot Framework `.resource` with the chosen elements |
| **Services** (Ctrl 3) | Start, stop and watch the detector, capture and actuator services |
| **Settings** (Ctrl ,) | Edit the session config, checked by VizDOM itself |

The installer brings its own Python with everything VizDOM needs. Your config,
sessions and plugins are kept in `Documents\\VizDOM`.
""",
        "docs": [("README: VizDOM Studio", "https://github.com/milanac030988/vizdom/tree/HEAD/tools/vizdom_studio")],
    },
    {
        "id": "python", "kind": "entry", "title": "Python API & CLI",
        "sub": "visual_dom.connect()", "box": (790, 60, 330, 84),
        "summary": "Build a Visual DOM from your own code, a script or another test framework.",
        "body": """
```python
from visual_dom import connect

session = connect("vizdom.config.json")   # or connect() for the defaults
dom = session.analyze("screenshot.png")   # -> Visual DOM (dict)
```

The same session object captures the screen and drives the actuator, so any test
framework can use VizDOM, not only Robot Framework.
""",
        "docs": [("Using as a Client", "USAGE.md"), ("Commands", "COMMANDS.md")],
    },
    {
        "id": "config", "kind": "config", "title": "Session config",
        "sub": "vizdom.config.json  ·  one file drives every stage", "box": (40, 230, 1080, 50),
        "summary": "One JSON file chooses the detector, OCR, capture, input and grounding, for every entry point.",
        "body": """
```bash
python -m visual_dom.config --init vizdom.config.json   # annotated template
```

| Section | Chooses |
|---|---|
| `detector` | `uied` (CPU), `omniparser`, `modular`, `yolo`, or `grpc` for the detector service |
| `ocr` | `easyocr`, `tesseract`, `paddleocr`, or `none` |
| `capture` | `windows`, `linux`, `android`, `camera`, `grpc`, or a plugin; the window to target |
| `actuator` | `desktop`, `android`, `grpc`, or a plugin |
| `grounding` | the `desc=` tiers: `lexical`, `slm`, `vlm`, and the models behind them |

Moving a part to another machine is a change in this file only, e.g.
`"detector": {"backend": "grpc", "grpc_target": "gpu-host:50051"}`.
""",
        "docs": [("Configuration & Sessions", "CONFIGURATION.md")],
    },
    {
        "id": "capture", "kind": "engine", "title": "Capture",
        "sub": "windows · linux · android · camera", "box": (40, 310, 225, 90),
        "summary": "Takes the screenshot: the whole screen, or only the window of the application under test.",
        "body": """
Built-in sources: `windows`, `linux` (X11), `android` (adb) and `camera` (a
physical screen photographed and rectified). With `capture.window_title` and
`capture.window_scope` it captures only the application under test, raised to the
front first, so the DOM does not describe whatever window happens to be on top.

Set `capture.strategy` to `grpc` to take the screenshot on another machine through
the [capture service](#c-capsvc).
""",
        "docs": [("Configuration: capture", "CONFIGURATION.md"), ("Writing Plugins", "PLUGINS.md")],
    },
    {
        "id": "pipeline", "kind": "engine", "title": "Detection pipeline",
        "sub": "detect · OCR · merge · hierarchy", "box": (325, 310, 225, 90),
        "summary": "Turns the screenshot into elements: boxes, text, types and a containment tree.",
        "body": """
1. **Detect** the elements with the configured backend: UIED (CPU, no weights),
   OmniParser or the modular detector (GPU recommended), or YOLO.
2. **Read text** with EasyOCR, Tesseract or PaddleOCR, and read glyph keys
   (`+ − × ÷ =`) that have no text.
3. **Merge** duplicates and over-split boxes, and sort in reading order.
4. **Build the hierarchy** by containment, and attach labels to inputs.

With `detector.backend = grpc` the detection step runs on the
[detector service](#c-detsvc), e.g. on a GPU host.
""",
        "docs": [("CV Pipeline", "PIPELINE.md"), ("OmniParser Setup", "omniparser-setup.md")],
    },
    {
        "id": "dom", "kind": "engine", "title": "Visual DOM",
        "sub": "elements · locators · session folder", "box": (610, 310, 225, 90),
        "summary": "The result: every element with its role, text, label, flags and ready-made locators.",
        "body": """
Each element has its bounds, role, text, label, interaction flags (clickable,
editable, scrollable), its parent in the hierarchy and locator suggestions. Every
analysis is saved as a session folder:

```
output/sessions/<timestamp>/
    screenshot.png       the captured screen
    dom_result.json      the Visual DOM
    session_info.json    where the screenshot came from
```

Studio and the Viewer open the same folders.
""",
        "docs": [("Configuration & Sessions", "CONFIGURATION.md")],
    },
    {
        "id": "locator", "kind": "engine", "title": "Locator resolver",
        "sub": "text= · role= · desc= · || chains", "box": (895, 310, 225, 90),
        "summary": "Finds the one element a locator means, or fails the step.",
        "body": """
| Locator | Matches |
|---|---|
| `text=Save`, `hint=Email`, `role=button`, `id=E12` | by what the element says or is |
| `right_of="Name"`, `below="Title"`, `within="Dialog"` | by position relative to another element |
| `desc="save button"` | by a plain-language description |
| <code>text=Save &#124;&#124; desc="save button"</code> | the first alternative that resolves wins |

A locator must resolve to **exactly one** element; none or several fails the step,
so an absent element is never reported as found. `desc=` is resolved in tiers:
`lexical` (no model) first; what it cannot settle goes to a vision model (`vlm`,
the default, GPU) or a small language model (`slm`, CPU) through
[Ollama](#c-ollama).
""",
        "docs": [("Using as a Client: locators", "USAGE.md")],
    },
    {
        "id": "plugins", "kind": "engine", "title": "Plugins",
        "sub": "your own capture source or actuator", "box": (610, 440, 225, 80),
        "summary": "Add a capture source or an input device without changing VizDOM.",
        "body": """
Drop a Python file into `plugins/capture/` or `plugins/actuator/` (Studio:
`Documents\\VizDOM\\plugins\\…`), or point `VIZDOM_CAPTURE_PLUGINS` /
`VIZDOM_ACTUATOR_PLUGINS` at a folder. The plugin is then selectable by name in
the config, like a built-in one: a camera, a capture card, a robot arm.
""",
        "docs": [("Writing Plugins", "PLUGINS.md")],
    },
    {
        "id": "actuator", "kind": "engine", "title": "Actuator",
        "sub": "desktop · android", "box": (975, 440, 145, 80),
        "summary": "Delivers the click, the keystrokes and the scroll to the application.",
        "body": """
Built-in: `desktop` (mouse and keyboard on Windows and Linux) and `android`
(adb input). Before input it can raise the application under test, so the click
reaches it and not the window on top (`actuator.window_title`, or the keyword
`Bring App To Front`).

Set `actuator.strategy` to `grpc` to deliver the input on another machine through
the [actuator service](#c-actsvc).
""",
        "docs": [("Configuration: actuator", "CONFIGURATION.md")],
    },
    {
        "id": "capsvc", "kind": "service", "title": "Capture service",
        "sub": ":50053  ·  vizdom-capture", "box": (40, 615, 225, 70),
        "summary": "Takes the screenshot on the machine that shows the application.",
        "body": """
```bash
vizdom-capture --strategy windows --port 50053
```

Client side: `"capture": {"strategy": "grpc", "target": "sut-host:50053"}`.
""",
        "docs": [("Using as a Client: services", "USAGE.md")],
    },
    {
        "id": "detsvc", "kind": "service", "title": "Detector service",
        "sub": ":50051  ·  vizdom-detector", "box": (325, 615, 225, 70),
        "summary": "Runs the detector on a GPU host, one warm model for every test runner.",
        "body": """
```bash
# source checkout (see OmniParser Setup)
uv pip install -e ".[robot,omniparser]"
python scripts/setup_omniparser.py           # model weights, once
vizdom-detector --backend omniparser --port 50051
```

Client side: `"detector": {"backend": "grpc", "grpc_target": "gpu-host:50051"}`.
`--backend uied` runs on a CPU and needs no weights.
""",
        "docs": [("OmniParser Setup", "omniparser-setup.md"), ("Using as a Client: services", "USAGE.md")],
    },
    {
        "id": "ollama", "kind": "optional", "title": "Language model",
        "sub": "Ollama :11434  ·  optional", "box": (610, 615, 225, 70),
        "summary": "Resolves the descriptions the lexical tier cannot, e.g. a paraphrase.",
        "body": """
Needed for the model tiers of `desc=`. The default chain is `lexical` (no model)
then `vlm`, a 7B vision model that wants a GPU; on a machine without one, use
`slm`, a 3B text model that runs on a CPU.

```bash
ollama pull qwen2.5vl:7b      # vlm tier (default), GPU recommended
ollama pull qwen2.5:3b        # slm tier, runs on a CPU
```

Default: `"grounding": {"tiers": ["lexical", "vlm"], "host": "http://gpu-host:11434"}`;
CPU only: `"tiers": ["lexical", "slm"]`. `text=`, `role=` and the other locators
need no model at all.
""",
        "docs": [("Configuration: grounding", "CONFIGURATION.md")],
    },
    {
        "id": "actsvc", "kind": "service", "title": "Actuator service",
        "sub": ":50054  ·  vizdom-actuator", "box": (895, 615, 225, 70),
        "summary": "Delivers clicks and keystrokes on the machine that runs the application.",
        "body": """
```bash
vizdom-actuator --strategy desktop --port 50054
```

Client side: `"actuator": {"strategy": "grpc", "target": "sut-host:50054"}`.

!!! warning "Trusted networks only"
    The services have no TLS and no authentication and listen on every network
    interface. The actuator executes the clicks and keystrokes it receives.
""",
        "docs": [("Using as a Client: services", "USAGE.md")],
    },
    {
        "id": "aut", "kind": "aut", "title": "Application under test",
        "sub": "untouched: no agent, no hooks, no accessibility tree needed", "box": (40, 760, 1080, 56),
        "summary": "Any application with a screen: desktop, embedded HMI, Android, or a screen seen through a camera.",
        "body": """
VizDOM needs nothing inside the application: no test build, no injected agent,
no accessibility API. It sees the pixels and sends input like a user, so the
same suite works on custom-rendered Qt/OpenGL interfaces, industrial HMIs and
remote desktops.
""",
        "docs": [],
    },
]

# --- interactions: (from, to, label, style, in_overview) --------------------------
# style: "call" solid, "remote" dashed (optional gRPC hop), "config" dotted
INTERACTIONS = [
    ("rf", "config", "Connect", "config", False),
    ("rf", "pipeline", "Dump Visual DOM", "call", False),
    ("rf", "locator", "Click Visual, Visual Should Exist, …", "call", False),
    ("studio", "pipeline", "Capture & Analyze", "call", False),
    ("studio", "locator", "Locator Lab, Try click", "call", False),
    ("studio", "config", "Settings", "config", False),
    ("studio", "detsvc", "Services page: start, stop", "call", False),
    ("studio", "capsvc", "Services page: start, stop", "call", False),
    ("studio", "actsvc", "Services page: start, stop", "call", False),
    ("python", "pipeline", "session.analyze()", "call", False),
    ("python", "config", "connect()", "config", False),
    ("config", "capture", "capture.*", "config", False),
    ("config", "pipeline", "detector.*, ocr.*", "config", False),
    ("config", "locator", "grounding.*", "config", False),
    ("config", "actuator", "actuator.*", "config", False),
    ("capture", "pipeline", "screenshot", "call", True),
    ("pipeline", "dom", "elements", "call", True),
    ("dom", "locator", "find", "call", True),
    ("locator", "actuator", "click point", "call", True),
    ("plugins", "capture", "your source", "call", False),
    ("plugins", "actuator", "your device", "call", False),
    ("capture", "capsvc", "gRPC", "remote", True),
    ("pipeline", "detsvc", "gRPC", "remote", True),
    ("locator", "ollama", "desc= tiers", "remote", True),
    ("actuator", "actsvc", "gRPC", "remote", True),
    ("capture", "aut", "reads the screen", "call", False),
    ("actuator", "aut", "clicks, types", "call", False),
    ("capsvc", "aut", "reads the screen", "call", True),
    ("actsvc", "aut", "clicks, types", "call", True),
]

# Arrows that must bend around other boxes in the overview: (from, to) -> points
ROUTES = {
    ("locator", "ollama"): [(915, 400), (915, 565), (722, 565), (722, 615)],
}

# Arrows from the entry points into the engine band (overview only):
# (from, x where it enters the band, label)
ENTRY_ARROWS = [
    ("rf", 205, "Connect · Dump Visual DOM · Click Visual"),
    ("studio", 580, "Capture & Analyze · Locator Lab · Try click"),
    ("python", 955, "connect() · analyze()"),
]
