# ADR-014: Project Restructure — Output Directory and Repository Setup

## Status

Accepted

## Date

2026-03-30

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-03-30 | 1.0 | Initial version |

## Context

The project root was cluttered with 27+ output files (PNG visualizations, JSON results) from various test runs. These artifacts made the codebase difficult to navigate and were not tracked in git.

Additionally, the project needed to be set up as a GitHub repository for version control.

## Decision

### 1. Output Directory Consolidation

Moved all generated output files from project root to `output/`:
- 15 PNG files (result visualizations, VLM outputs, test captures)
- 12 JSON files (DOM results, hierarchy outputs)
- 2 misc files (debug logs)

Updated scripts to default output to `output/` directory:
- `scripts/process_gui_image.py` — default JSON and visualization paths
- `scripts/visualize_dom.py` — default output image path
- `examples/evaluate_dom.py` — updated reference paths

### 2. Repository Setup

- Repository name: **vizdom** (private GitHub repo)
- Description: "Visual DOM Generator & Robot Framework Library — Converts GUI screenshots into UIAutomator-like DOM JSON using Computer Vision + LLM, with Robot Framework keywords for visual GUI test automation without accessibility APIs"
- Added `start_viewer.bat` for easy viewer launch

### 3. Requirements Files

Created layered requirements files alongside `pyproject.toml`:
- `requirements.txt` — Core + EasyOCR + Tesseract
- `requirements-llm.txt` — + PyTorch + Transformers
- `requirements-training.txt` — + PEFT, datasets, YOLOv8
- `requirements-dev.txt` — + pytest, black, ruff, mypy
- `requirements-tools.txt` — + PyQt5, pyautogui, Flask, PaddleOCR

Fixed `pyproject.toml`:
- Added missing `requests` to core dependencies
- Added `pytesseract` to OCR extras
- Added `viewer` optional group for PyQt5

### 4. README Updates

- Updated project structure to reflect current state
- Updated development status table (milestones 1-9 done, milestone 10 pending)
- Fixed output paths in quick start examples

## Consequences

### Positive
- Clean project root — only source directories and config files
- All generated output in one place, gitignored
- Layered requirements for different installation needs
- Version-controlled on GitHub

### Negative
- Existing scripts referencing root-level output files need path updates (done)

## Files Changed

- `output/` — All generated files moved here
- `scripts/process_gui_image.py` — Default output paths updated
- `scripts/visualize_dom.py` — Default output path updated
- `examples/evaluate_dom.py` — Reference path updated
- `requirements.txt`, `requirements-llm.txt`, `requirements-training.txt`, `requirements-dev.txt`, `requirements-tools.txt` — New
- `pyproject.toml` — Added missing deps, viewer group
- `readme.md` — Updated structure, status, paths
- `start_viewer.bat` — New: viewer launch script
- `.gitignore` — Added `.claude/`
