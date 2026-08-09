# Setup with uv

This project uses [**uv**](https://docs.astral.sh/uv/) (a fast Python
package/env manager) to install dependencies reproducibly from `pyproject.toml`.

> **Scope (honest).** uv manages the **Python** side. Three things live outside
> it and are separate steps uv *invokes* or that you install once:
> **Ollama** (native app — the SLM refiner), **OmniParser** (a git repo + HF
> weights, fetched by `scripts/setup_omniparser.py`), and **CUDA PyTorch**
> (already installed in the app's Python 3.9 — see Path A below).

## Which interpreter do the launchers use?

Every `start_*.bat` / `run_demo.bat` resolves Python through **one** helper,
`python_env.bat`, instead of hardcoding a path — so the repository runs on a
machine that is not the author's. Resolution order, first hit wins:

| # | Candidate | When it applies |
|---|---|---|
| 1 | `%VIZDOM_PYTHON%` | explicit override — always wins |
| 2 | `.venv\Scripts\python.exe` | an in-project env (`uv venv`, `python -m venv`) |
| 3 | `D:\Python\python39\python.exe` | this workstation's CUDA-enabled 3.9 |
| 4 | `py -3.9` | the Windows launcher, if 3.9 is registered |
| 5 | `python` on PATH | last resort |

Nothing found → the launcher stops with the two commands that fix it. To use a
specific interpreter for one session:

```bat
set VIZDOM_PYTHON=C:\path	o\python.exe
start_detector.bat --backend uied
```

In the commands below, `%VIZDOM_PY%` means "the interpreter the resolver picked";
substitute your own path if you are running them by hand.

## Prerequisites
- The reference environment is **Python 3.9** with a working `torch 2.4.1+cu124`
  (on the author's workstation: `D:\Python\python39\python.exe`, which is why
  it is candidate #3 above).
- Install uv into it (avoids the GitHub-blocked standalone installer):
  ```bat
  "%VIZDOM_PY%" -m pip install uv
  ```

## Path A — uv over the existing Python 3.9 (recommended here)

Keeps the working CUDA torch (no ~2.5 GB redownload). uv installs/locks the
*other* dependencies **into that interpreter** via its pip interface.

```bat
REM install a dependency group into the existing python39 (examples):
"%VIZDOM_PY%" -m uv pip install --python "%VIZDOM_PY%" -e ".[grpc]"
"%VIZDOM_PY%" -m uv pip install --python "%VIZDOM_PY%" -e ".[docs]"
"%VIZDOM_PY%" -m uv pip install --python "%VIZDOM_PY%" -e ".[viewer,dashboard]"
```

> ⚠️ **Do NOT** run `uv sync` / a fresh `uv venv` in Path A — that creates an
> isolated env and would reinstall torch (Path B). Use `uv pip install --python`
> against the existing interpreter, as above.

> ⚠️ **protobuf pin.** `grpcio-tools >= 1.63` pulls **protobuf 6**, which breaks
> the streamlit dashboard (needs `protobuf < 6`). The `grpc` group pins
> `grpcio* < 1.63` and `[tool.uv] constraint-dependencies = ["protobuf<6"]`
> keeps it project-wide. Keep it that way.

## Path B — fresh uv-managed environment (portable, heavier)

For a clean machine / full reproducibility (re-downloads CUDA torch from the
configured PyTorch index):

```bash
uv venv --python 3.12
uv pip install -e ".[omniparser,grpc,viewer,docs,dashboard]"
```
`[tool.uv]` already points `torch`/`torchvision` at `pytorch-cu124`.
(`uv python install` fetches Python from GitHub, which the corporate proxy may
block — use a system Python with `uv venv --python <path>` if so.)

## One-time external setup (either path)
```bat
REM OmniParser detector backend (repo + weights); see docs/omniparser-setup.md
"%VIZDOM_PY%" scripts\setup_omniparser.py --install-deps

REM gRPC stubs for the remote detector (ADR-017)
"%VIZDOM_PY%" -m grpc_tools.protoc -I protos ^
  --python_out=src\visual_dom\rpc --grpc_python_out=src\visual_dom\rpc protos\detector.proto
REM then make the generated grpc import relative:
REM   edit detector_pb2_grpc.py: `import detector_pb2` -> `from . import detector_pb2`
```
Ollama (refiner): install separately and `ollama pull minicpm-v`.

## Running
```bat
start_viewer.bat                 REM PyQt5 inspector
start_dashboard.bat              REM Streamlit dashboard
start_detector.bat --backend omniparser   REM remote detector service (ADR-017)
```

## Lockfile (`requirements.lock`)

A resolved lock (112 pinned packages) over the runtime + tooling extras
(`ocr,omniparser,grpc,viewer,dashboard,docs,desktop`), generated with:

```bat
"%VIZDOM_PY%" -m uv pip compile pyproject.toml --python-version 3.9 ^
  --extra ocr --extra omniparser --extra grpc --extra viewer --extra dashboard ^
  --extra docs --extra desktop -o requirements.lock
```

⚠️ **It is a *fresh-install* lock, not a snapshot of the current env.** It resolves
the newest compatible versions (e.g. `torch==2.6.0+cu124`, `opencv-python==5.x`),
which differ from what's installed on this machine (`torch 2.4.1`, `opencv 4.9`).

- **Fresh machine (Path B):** `uv pip install -r requirements.lock` into a new venv
  → reproduces the pinned set (downloads CUDA torch from the pytorch index).
- **Do NOT `uv pip sync requirements.lock` into the working Python 3.9** — it would
  upgrade torch (2.4→2.6, ~2.5 GB) and opencv (4→5). To snapshot the *current*
  working env instead, use `uv pip freeze --python <py39> > current-env.lock`.

## Dependency groups (`pyproject.toml`)
`ocr` · `omniparser` · `grpc` · `docs` · `dashboard` · `viewer` · `desktop` ·
`llm` · `training` · `cv-training` · `annotation` · `dev` · `all`.
Deliberately **not** installed: `ocr-paddle` (paddle → protobuf-6 conflict; the
OmniParser setup patches around needing paddle).
