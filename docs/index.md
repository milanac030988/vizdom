# VizDOM — Visual DOM Generator

Turn a GUI **screenshot** into a UIAutomator-like **DOM JSON tree** — element
bounds, roles, text labels, locators and hierarchy — using Computer Vision plus a
small LLM/VLM, so GUI test automation works even when no accessibility tree
exists.

---

## Why this project exists

GUI test automation lives or dies on one thing: being able to **find an element**
on screen and address it reliably. The usual way is the platform's accessibility
tree (UIAutomator, UIA, the DOM). But a large class of applications expose **no
usable tree at all**:

- Custom-rendered UIs — Qt/QML, OpenGL, game engines, canvas apps.
- Embedded / industrial HMIs and kiosk software.
- Screens seen **through a camera** (a physical device, a capture card) where
  there is no software API to query at all.

For these, testers fall back to brittle pixel-coordinate scripts that break on the
first layout change. **VizDOM's premise:** if a human tester can look at the
screen and know "that's the Login button", a pipeline should be able to
reconstruct an equivalent structured tree from the pixels alone — and hand it to a
test framework as if it came from an accessibility API.

This is a master's **applied project**: the contribution is solid engineering that
composes existing CV/LLM building blocks into a working, extensible, deployable
system — not a new model or a research claim.

---

## What we have built

A complete **screenshot → DOM → test-automation** path, plus the architecture to
run it in the real world.

**The pipeline** (`visual_dom.cv.pipeline`)

- **Pluggable element detectors** behind one interface (ADR-015): traditional CV
  (**UIED**), **YOLO**, and Microsoft **OmniParser** (YOLO + Florence-2 + OCR).
  Pick per run; add more without touching the core.
- **OCR text layer** (EasyOCR / PaddleOCR / Tesseract) with upscaling, and an
  **ensemble** that feeds our OCR into OmniParser to recover missed text.
- **Clean-up passes**: merge / split / NMS / dedup, plus a **smart-merge** for
  over-segmented boxes (guarded by fill-ratio, delimiter and interactable checks).
- **Reading-order** sorting (row-band, top→bottom / left→right).
- An optional **SLM/VLM advisor** (via Ollama) that reviews suspicious elements —
  split, re-type, merge and **label** — with merges gated to safe candidates.

**From detections to a usable DOM**

- **Coarse hierarchy builder** — containment, alignment grouping, label
  association (ADR-016).
- **DOM compiler** — roles, flags (clickable/editable/scrollable), multiple
  **locators**, and human-readable labels, emitted as UIAutomator-like JSON.
- **Robot Framework Visual Automation Library** — GUI-testing keywords driven by
  that DOM (the second deliverable).

**Tooling & architecture**

- **Visual DOM Viewer** (PyQt5) to capture, inspect and export; a Streamlit
  dashboard; and an **evaluation framework** (IoU / precision / recall / F1).
- **Hexagonal (ports & adapters)** structure with **distributed gRPC services**
  (ADR-017): run the heavy detector as a warm-model service on a GPU box.
- **Pluggable capture service** (ADR-018): a `CaptureStrategy` for
  Windows / Linux / Android / camera, **auto-discovered** user plugins, and a gRPC
  `Capture` service so screenshots come from **where the app-under-test runs** —
  wired into both the CLI (`--capture`) and the Viewer (`Src:`).
- **`uv`**-managed environment and this **ProperDocs** site with diagrams rendered
  offline (behind a corporate proxy, no PlantUML server, no Graphviz).

---

## What we are still improving

Honest status — these are the open edges, roughly in priority order:

- **Real-world robustness.** Detection and symbol recognition (ADR-011) are strong
  on clean/synthetic UIs but weaker on gradient-heavy, themed real-world apps.
  Reducing OmniParser's over-segmentation is ongoing.
- **Evaluation at scale.** The metrics framework exists; it needs a larger, more
  representative labelled dataset (synthetic-data generation is in progress) to
  quantify accuracy and regressions.
- **Capture service hardening** (ADR-018 follow-ups): setuptools **entry-point**
  plugin discovery as a second source, and **TLS/auth** on the currently-insecure
  gRPC channel.
- **Model choices.** Ongoing comparison of grounding/agent models (OmniParser,
  Aria-UI, ELAM-7B, Jedi) to decide what best replaces or augments the SLM
  refinement step — see the [model discussion notes](model-discussion.md).

---

## Get started

Installed with [**uv**](https://docs.astral.sh/uv/), which fetches its own
Python — no pre-existing local interpreter needed:

```bat
pip install uv
uv python install 3.12
uv venv --python 3.12
uv pip install -e ".[ocr,grpc]"
```

The `start_*.bat` launchers pick up the resulting `.venv` automatically. Full
instructions — dependency groups, GPU notes, interpreter resolution order — in
**[Setup with uv](uv-setup.md)**.

## Documentation map

- **[Architecture](architecture.md)** — system, pipeline, component, class,
  sequence and hexagonal (ports & adapters) diagrams (rendered inline from the
  `.puml` sources of record).
- **[CV Pipeline](PIPELINE.md)** and **[OmniParser Setup](omniparser-setup.md)** —
  how detection works and how to set up the OmniParser backend.
- **[Evaluation](EVALUATION.md)** and **[VLM Study](RESEARCH.md)** — the metrics
  framework and the VLM experiments.
- **[Model Discussion Notes](model-discussion.md)** — comparisons (OmniParser,
  Aria-UI, ELAM-7B, Jedi) that shaped the design.
- **[Architecture Decisions](adr/README.md)** — the full ADR log (001–025).

## Two deliverables

1. **Visual DOM Generator** — the screenshot→DOM pipeline (CV + small LLM/VLM).
2. **Robot Framework Visual Automation Library** — GUI-testing keywords driven by
   the DOM.

## Building these docs

This site is built with [ProperDocs](https://properdocs.org) (a MkDocs fork).
Diagrams render locally — **no PlantUML server, no Graphviz**:

```bash
# needs: Java on PATH, and tools/plantuml.jar present
properdocs serve -f properdocs.yml     # live preview at http://localhost:8000
properdocs build -f properdocs.yml     # static site/ (gitignored)
```

PlantUML runs via the vendored `tools/plantuml.jar` using the built-in **Smetana**
layout engine (`!pragma layout smetana`), so no external `dot.exe` is required
(the `architecture.puml` ports & adapters diagram is the one exception — it uses `dot`).
