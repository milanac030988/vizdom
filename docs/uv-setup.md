# Setup with uv

This project is installed with [**uv**](https://docs.astral.sh/uv/). One command
sequence works on **any** machine — uv fetches its own Python, creates the
environment in the project, and installs the pinned dependency groups from
`pyproject.toml`. Nothing depends on a pre-existing local Python.

> **Scope (honest).** uv manages the **Python** side. Three things live outside
> it: **Ollama** (a native app — the optional SLM/VLM refiner), **OmniParser**
> (a git repo + Hugging Face weights, fetched by
> `scripts/setup_omniparser.py`), and **Tesseract** (a native binary, only for
> the `tesseract` OCR engine).

---

## 1. Install uv (once per machine)

Use the **standalone installer** — it installs uv itself, independent of any
Python on the machine (which is the point: uv then provides the Python).

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Linux / macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new shell afterwards so `PATH` picks up `%USERPROFILE%\.local\bin`
(Windows) / `~/.local/bin` (Linux, macOS), then check:

```bat
uv --version
```

!!! note "If the installer host is unreachable"
    On a restricted network, either install uv from PyPI into any existing
    Python (`pip install uv`) or drop the release binary somewhere on `PATH`.
    Both give the same tool; only the bootstrap differs — everything from §2
    onwards is identical.

## 2. Create the project environment

```bat
cd <repo-root>
uv python install 3.12
uv venv --python 3.12
```

`uv python install` downloads a managed CPython (~21 MB) — no system Python
required. `uv venv` creates **`.venv`** in the repo root, which every launcher
picks up automatically (see §5).

!!! warning "Do not write `uv venv --python 3.9` without a full path"
    The code supports 3.9 (`requires-python = ">=3.9"`), but on a machine that
    has a **32-bit** Python 3.9 registered, `--python 3.9` may select it — and
    32-bit cannot load CUDA PyTorch, which fails much later with a confusing
    error. Either use 3.12 as above, or pin the exact interpreter:
    `uv venv --python "C:\path\to\64bit\python.exe"`.

## 3. Install the dependency groups you need

```bat
:: minimum: pipeline + Robot Framework library (CPU, classical detector)
uv pip install -e ".[ocr]"

:: add the gRPC services (detector / capture / actuator)
uv pip install -e ".[ocr,grpc]"

:: add the learned detector (OmniParser: torch + CUDA, ~2.5 GB download)
uv pip install -e ".[ocr,grpc,omniparser]"

:: interactive tools and docs
uv pip install -e ".[viewer,dashboard,docs]"

:: everything the project can do
uv pip install -e ".[all]"
```

Available groups: `ocr`, `ocr-paddle`, `llm`, `omniparser`, `grpc`, `viewer`,
`dashboard`, `docs`, `annotation`, `desktop`, `training`, `cv-training`, `dev`,
`all`.

**GPU note.** `[tool.uv.sources]` already resolves `torch`/`torchvision` from the
`pytorch-cu124` index, so a fresh install gets CUDA wheels. Without a GPU, skip
the `omniparser` group and use `detector.backend: "uied"` — the whole pipeline,
the Robot Framework library, and the demo run on CPU.

**Pinned constraint.** `[tool.uv] constraint-dependencies = ["protobuf<6"]` is
deliberate: `grpcio-tools >= 1.63` pulls protobuf 6, which breaks the Streamlit
dashboard. Keep it.

## 4. Verify

```bat
start_capture.bat --list
```

Should list the capture strategies with `available=True` for your platform. Then:

```bat
uv run python -m pytest tests/unit tests/architecture -q
```

## 5. Which interpreter do the launchers use?

Every launcher resolves Python through **one** helper — `python_env.bat` on
Windows, `python_env.sh` on Linux/macOS — rather than hardcoding a path. That is
what makes the repository runnable on a machine that is not the author's.

| Platform | Launchers |
|---|---|
| Windows | `start_detector.bat`, `start_capture.bat`, `start_actuator.bat`, `start_viewer.bat`, `start_dashboard.bat`, `run_demo.bat` |
| Linux / macOS | the same names with `.sh` (`./start_detector.sh …`) |

First hit wins:

| # | Candidate | When it applies |
|---|---|---|
| 1 | `%VIZDOM_PYTHON%` | explicit override — always wins |
| 2 | `.venv\Scripts\python.exe` (Windows) / `.venv/bin/python` (POSIX) | **the uv environment from §2 — the normal case** |
| 3 | `D:\Python\python39\python.exe` | the author's workstation (Windows only; legacy, predates uv) |
| 4 | `py -3.9` (Windows) / `python3.12…3.9` (POSIX) | a versioned interpreter |
| 5 | `python` on PATH | last resort |

The POSIX resolver additionally **checks that the interpreter it found actually
has the dependencies** and prints the install command if not: candidate 4/5 can
easily be a bare `python3` that would otherwise fail much later with
`ModuleNotFoundError: No module named 'cv2'`.

Nothing usable → the launcher stops and prints the commands that fix it.

!!! warning "`.venv` takes precedence over a system Python"
    Because candidate 2 outranks 3–5, an **incomplete** `.venv` shadows a
    working system interpreter: create it *and install the groups you need*
    (§3), or the launchers will fail on a missing package rather than fall
    through. To ignore `.venv` for one session, set
    `VIZDOM_PYTHON=C:\path\to\python.exe`.

Direct commands work the same way — either activate the environment
(`.venv\Scripts\activate`) or prefix with `uv run`:

```bat
uv run python -m visual_dom.adapters.inbound.grpc.detector_server --backend uied
uv run robot --outputdir output\demo_run examples\windows_calculator_demo\calculator_demo.robot
```

The console scripts declared in `pyproject.toml` are also available inside the
environment: `vizdom-detector`, `vizdom-capture`, `vizdom-actuator`.

## 5b. Linux specifics

The pipeline, the Robot Framework library and the services are
platform-independent; two adapters need system packages:

| Concern | Requirement |
|---|---|
| `linux` capture strategy | an X11 display (`$DISPLAY`) and `mss` |
| `focus_target` (ADR-021) | `wmctrl` **or** `xdotool` — `sudo apt install wmctrl xdotool` |
| `desktop` actuator (pyautogui) | `sudo apt install python3-xlib scrot` |
| Wayland | exposes no window control to unprivileged clients — focus returns `False`; run an X11 session for GUI driving |

The bundled Calculator demo launches `calc.exe`, so it is Windows-only; on Linux
point the runner at your own suite: `./run_demo.sh my_suite.robot`.

## 6. One-time external setup

```bat
:: OmniParser detector backend (repo + weights); see omniparser-setup.md
uv run python scripts\setup_omniparser.py --install-deps

:: gRPC stubs, if you change protos/*.proto (ADR-017)
uv run python -m grpc_tools.protoc -I protos ^
    --python_out=src/visual_dom/generated --grpc_python_out=src/visual_dom/generated ^
    protos/detector.proto protos/capture.proto protos/actuator.proto
```

Generated `*_pb2*.py` files are gitignored — regenerate them after cloning if you
use the services (`[grpc]` group required).

## 7. Alternative — install into an existing interpreter

If you already have a working environment (e.g. a system Python with CUDA torch
that you do not want to rebuild), uv can install into it instead of creating
`.venv`:

```bat
uv pip install --python "C:\path\to\python.exe" -e ".[ocr,grpc]"
```

Then point the launchers at it: `set VIZDOM_PYTHON=C:\path\to\python.exe`.
This is how the author's workstation is set up (candidate 3 above) — it works,
but §2 is the reproducible path and the one to use on a new machine.

Do **not** mix the two: running `uv venv` in a repo whose launchers you expect to
use the system interpreter creates exactly the shadowing problem described in §5.
