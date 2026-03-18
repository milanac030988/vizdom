# Visual DOM Command Reference

Complete list of commands for running the Visual DOM pipeline, viewer, evaluation, and tests.

## Table of Contents

- [Visual DOM Pipeline](#visual-dom-pipeline)
- [Visual DOM Viewer](#visual-dom-viewer)
- [Evaluation](#evaluation)
- [Tests](#tests)
- [Robot Framework Library](#robot-framework-library)

---

## Visual DOM Pipeline

Process screenshots to generate DOM JSON.

### Basic Usage

```bash
# Process a single image
python -m visual_dom.cv.pipeline <image_path> [options]

# Examples
python -m visual_dom.cv.pipeline screenshot.png
python -m visual_dom.cv.pipeline screenshot.png -o output.json
python -m visual_dom.cv.pipeline screenshot.png --no-gpu --ocr-engine tesseract
```

### Parameters

| Parameter | Short | Default | Description |
|-----------|-------|---------|-------------|
| `image_path` | - | Required | Path to input image (PNG, JPG, BMP) |
| `--output` | `-o` | `<image>_dom.json` | Output JSON file path |
| `--ocr-engine` | - | `easyocr` | OCR engine: `easyocr`, `paddleocr`, `tesseract` |
| `--no-gpu` | - | False | Disable GPU acceleration (use CPU) |
| `--confidence` | `-c` | `0.3` | Minimum confidence threshold (0.0-1.0) |
| `--languages` | `-l` | `en` | OCR languages (comma-separated, e.g., `en,ch_sim`) |
| `--max-elements` | - | `200` | Maximum elements to detect |
| `--visualize` | `-v` | False | Save visualization image with bounding boxes |
| `--no-hierarchy` | - | False | Skip hierarchy building (flat output) |
| `--no-locators` | - | False | Skip locator generation |

### Examples

```bash
# Basic processing
python -m visual_dom.cv.pipeline tests/samples/calculator.png

# With custom output and visualization
python -m visual_dom.cv.pipeline screenshot.png -o result.json -v

# CPU-only processing with Tesseract
python -m visual_dom.cv.pipeline screenshot.png --no-gpu --ocr-engine tesseract

# Multi-language OCR (English + Chinese)
python -m visual_dom.cv.pipeline screenshot.png -l en,ch_sim

# High confidence threshold
python -m visual_dom.cv.pipeline screenshot.png -c 0.7

# Quick processing (no hierarchy/locators)
python -m visual_dom.cv.pipeline screenshot.png --no-hierarchy --no-locators
```

---

## Visual DOM Viewer

Interactive GUI for viewing and editing DOM structures.

### Basic Usage

```bash
# Start viewer
python -m tools.visual_dom_viewer

# Or using the package directly
cd D:/Project/MasterProject
python -c "import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'src'); from tools.visual_dom_viewer.__main__ import main; main()"
```

### Viewer Features

| Feature | Shortcut | Description |
|---------|----------|-------------|
| Connect | `Ctrl+N` | Connect to target application |
| Capture & Analyze | `F5` | Capture screenshot and run pipeline |
| Re-Analyze | `F6` | Re-analyze current screenshot |
| Open Image | `Ctrl+O` | Load screenshot from file |
| Open DOM | - | Load DOM JSON from file |
| Explore Mode | - | Toggle element selection mode |
| Zoom In | `Ctrl++` | Zoom in on canvas |
| Zoom Out | `Ctrl+-` | Zoom out on canvas |
| Export | `Ctrl+E` | Export to Robot Framework |

### Workflow

1. **Connect** → Select platform (Windows/Android) → Select target app
2. **Capture & Analyze** → Captures screenshot and generates DOM
3. **Explore Mode** → Click elements to select them
4. **Define Elements** → Name elements and select properties
5. **Export** → Generate Robot Framework resource file

---

## Evaluation

Evaluate Visual DOM output quality against ground truth.

### Command Line

```bash
# Single file evaluation
python -m visual_dom.evaluation.cli <predicted.json> <ground_truth.json> [options]

# Batch evaluation
python -m visual_dom.evaluation.cli --batch <predictions_dir> <ground_truths_dir> [options]
```

### Parameters

| Parameter | Short | Default | Description |
|-----------|-------|---------|-------------|
| `predicted` | - | Required | Predicted DOM JSON file or directory |
| `ground_truth` | - | Required | Ground truth DOM JSON file or directory |
| `--batch` | `-b` | False | Batch mode (treat args as directories) |
| `--format` | `-f` | `text` | Output format: `text`, `json`, `markdown`, `html` |
| `--output` | `-o` | stdout | Output file path |
| `--iou-threshold` | - | `0.5` | IoU threshold for matching (0.0-1.0) |
| `--no-hierarchy` | - | False | Skip hierarchy evaluation |
| `--no-locators` | - | False | Skip locator evaluation |

### Examples

```bash
# Basic evaluation
python -m visual_dom.evaluation.cli predicted.json ground_truth.json

# Save as Markdown report
python -m visual_dom.evaluation.cli pred.json gt.json -f markdown -o report.md

# Save as HTML report
python -m visual_dom.evaluation.cli pred.json gt.json -f html -o report.html

# Strict evaluation (higher IoU threshold)
python -m visual_dom.evaluation.cli pred.json gt.json --iou-threshold 0.75

# Batch evaluation
python -m visual_dom.evaluation.cli --batch outputs/ ground_truths/ -f json -o batch_results.json

# Quick evaluation (skip hierarchy/locators)
python -m visual_dom.evaluation.cli pred.json gt.json --no-hierarchy --no-locators
```

### Python API

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationReport

# Create evaluator
evaluator = VisualDOMEvaluator()

# Evaluate
result = evaluator.evaluate_from_files("predicted.json", "ground_truth.json")

# Print summary
print(result.summary())

# Access specific metrics
print(f"F1 Score: {result.element_metrics.f1_score:.2%}")
print(f"OCR Accuracy: {result.ocr_metrics.char_accuracy:.2%}")

# Generate report
report = EvaluationReport(result)
report.save_markdown("report.md")
```

---

## Tests

Run unit tests and integration tests.

### Unit Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_pipeline.py -v

# Run specific test function
python -m pytest tests/test_pipeline.py::test_text_detection -v

# Run with coverage
python -m pytest tests/ --cov=src/visual_dom --cov-report=html

# Run only fast tests (skip slow integration tests)
python -m pytest tests/ -v -m "not slow"
```

### Test Parameters

| Parameter | Description |
|-----------|-------------|
| `-v` | Verbose output |
| `-vv` | More verbose output |
| `-s` | Show print statements |
| `--cov=<path>` | Enable coverage for path |
| `--cov-report=html` | Generate HTML coverage report |
| `-m "<marker>"` | Run tests with specific marker |
| `-k "<pattern>"` | Run tests matching pattern |
| `-x` | Stop on first failure |
| `--tb=short` | Shorter traceback |

### Test Categories

```bash
# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only
python -m pytest tests/integration/ -v

# CV pipeline tests
python -m pytest tests/ -k "pipeline" -v

# OCR tests
python -m pytest tests/ -k "ocr or text" -v

# Hierarchy tests
python -m pytest tests/ -k "hierarchy" -v
```

---

## Robot Framework Library

Use Visual DOM with Robot Framework for UI automation.

### Installation

```bash
# The library is in src/visual_dom/robot/
# Add to PYTHONPATH or install
pip install -e .
```

### Robot Framework Usage

```robot
*** Settings ***
Library    visual_dom.robot.VisualDOMLibrary

*** Test Cases ***
Example Test
    # Load DOM from file
    Load Visual DOM    calculator_dom.json

    # Or capture and analyze
    Capture And Analyze    screenshot.png

    # Find elements
    ${element}=    Find Element By Text    Submit
    ${buttons}=    Find Elements By Type    button

    # Get element properties
    ${bounds}=    Get Element Bounds    ${element}
    ${center}=    Get Element Center    ${element}

    # Click using locator
    Click Element    text=Submit
    Click Element    id=E42
    Click Element    type_index=button[0]
```

### Library Keywords

| Keyword | Arguments | Description |
|---------|-----------|-------------|
| `Load Visual DOM` | `json_path` | Load DOM from JSON file |
| `Capture And Analyze` | `image_path` | Analyze image and load DOM |
| `Find Element By Text` | `text`, `exact=False` | Find element by text content |
| `Find Element By Id` | `element_id` | Find element by ID |
| `Find Elements By Type` | `visual_type` | Find all elements of type |
| `Get Element Bounds` | `element` | Get element bounding box |
| `Get Element Center` | `element` | Get element center point |
| `Get Element Text` | `element` | Get element text content |
| `Click Element` | `locator` | Click element (simulated) |
| `Element Should Exist` | `locator` | Assert element exists |
| `Element Should Have Text` | `locator`, `expected` | Assert element text |

---

## Research / Model Testing

Test various Vision-Language Models (VLMs) for GUI element detection capabilities.

### Test Qwen2-VL Models

```bash
# Basic usage
python research/test_qwen_vl.py <image_path> [options]

# Examples
python research/test_qwen_vl.py screenshot.png
python research/test_qwen_vl.py screenshot.png -m 7b --mode json -o output.png
```

#### Parameters

| Parameter | Short | Default | Description |
|-----------|-------|---------|-------------|
| `image` | - | Required | Path to GUI screenshot |
| `--model` | `-m` | `2b` | Model size: `2b` (faster) or `7b` (more accurate) |
| `--mode` | - | `simple` | Detection mode: `simple`, `json`, `grounding` |
| `--output` | `-o` | None | Output visualization path |
| `--gpu` | - | True | Use GPU acceleration |
| `--no-gpu` | - | False | Force CPU inference |
| `--flash-attn` | - | False | Use Flash Attention (faster, requires flash-attn package) |

#### Detection Modes

| Mode | Description | Output |
|------|-------------|--------|
| `simple` | Basic description of UI elements | Text description |
| `json` | Structured JSON output with bboxes | JSON array |
| `grounding` | Uses special grounding tokens for precise bboxes | Parsed elements |

#### Examples

```bash
# Simple description (fastest)
python research/test_qwen_vl.py tests/samples/calculator.png --mode simple

# JSON output with visualization
python research/test_qwen_vl.py tests/samples/calculator.png --mode json -o detected.png

# Grounding mode (most precise bboxes)
python research/test_qwen_vl.py tests/samples/calculator.png --mode grounding -o grounded.png

# Use larger 7B model for better accuracy
python research/test_qwen_vl.py screenshot.png -m 7b --mode json

# CPU-only (for machines without GPU)
python research/test_qwen_vl.py screenshot.png --no-gpu
```

### Test Multiple VLM Models

Compare different Vision-Language Models for GUI detection.

```bash
# Basic usage
python research/test_vlm_models.py <image_path> [options]

# List available models
python research/test_vlm_models.py --list-models

# Examples
python research/test_vlm_models.py screenshot.png -m florence-2-base -o output.png
```

#### Parameters

| Parameter | Short | Default | Description |
|-----------|-------|---------|-------------|
| `image` | - | Required | Path to GUI screenshot |
| `--model` | `-m` | `florence-2-base` | Model to test (see list below) |
| `--output` | `-o` | None | Output visualization path |
| `--gpu` | - | True | Use GPU acceleration |
| `--no-gpu` | - | False | Force CPU inference |
| `--list-models` | - | False | List available models and exit |

#### Available Models

| Model Key | HuggingFace Name | VRAM | Description |
|-----------|------------------|------|-------------|
| `qwen2-vl-2b` | Qwen/Qwen2-VL-2B-Instruct | ~5GB | Fast, good quality |
| `qwen2-vl-7b` | Qwen/Qwen2-VL-7B-Instruct | ~15GB | More accurate |
| `florence-2-base` | microsoft/Florence-2-base | ~2GB | Excellent for grounding |
| `florence-2-large` | microsoft/Florence-2-large | ~4GB | Better accuracy |
| `phi-3.5-vision` | microsoft/Phi-3.5-vision-instruct | ~8GB | Small but capable |
| `minicpm-v-2.6` | openbmb/MiniCPM-V-2_6 | ~8GB | Efficient multimodal |
| `internvl2-2b` | OpenGVLab/InternVL2-2B | ~5GB | Strong visual understanding |
| `internvl2-8b` | OpenGVLab/InternVL2-8B | ~16GB | Best accuracy |

#### Examples

```bash
# Test with Florence-2 (recommended for beginners - small & fast)
python research/test_vlm_models.py screenshot.png -m florence-2-base -o florence_output.png

# Test with Florence-2 Large (better accuracy)
python research/test_vlm_models.py screenshot.png -m florence-2-large -o florence_large.png

# Test with Qwen2-VL 2B
python research/test_vlm_models.py screenshot.png -m qwen2-vl-2b -o qwen_output.png

# Test with Phi-3.5-Vision
python research/test_vlm_models.py screenshot.png -m phi-3.5-vision -o phi_output.png

# Test with InternVL2 (high accuracy)
python research/test_vlm_models.py screenshot.png -m internvl2-8b -o internvl_output.png

# CPU-only testing
python research/test_vlm_models.py screenshot.png -m florence-2-base --no-gpu
```

#### Model Comparison Tips

```bash
# Compare multiple models on same image
for model in florence-2-base qwen2-vl-2b phi-3.5-vision; do
    echo "Testing $model..."
    python research/test_vlm_models.py screenshot.png -m $model -o "output_${model}.png"
done
```

### Required Dependencies for Research

```bash
# Base dependencies
pip install transformers torch torchvision pillow

# For Qwen2-VL
pip install qwen-vl-utils

# For Flash Attention (optional, faster inference)
pip install flash-attn --no-build-isolation

# For visualization
pip install opencv-python
```

---

## Quick Reference

### Most Common Commands

```bash
# 1. Process image to DOM
python -m visual_dom.cv.pipeline screenshot.png -o dom.json -v

# 2. Start viewer
python -m tools.visual_dom_viewer

# 3. Evaluate quality
python -m visual_dom.evaluation.cli predicted.json ground_truth.json

# 4. Run tests
python -m pytest tests/ -v

# 5. Generate coverage report
python -m pytest tests/ --cov=src/visual_dom --cov-report=html

# 6. Research: Test Qwen2-VL
python research/test_qwen_vl.py screenshot.png --mode json -o output.png

# 7. Research: Test multiple VLMs
python research/test_vlm_models.py screenshot.png -m florence-2-base -o output.png
```

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install with GPU support (CUDA 11.8)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Install OCR engines
pip install easyocr paddleocr pytesseract

# Install viewer dependencies
pip install PyQt5
```

### Check GPU Availability

```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: visual_dom` | Add `src/` to PYTHONPATH or run from project root |
| `CUDA out of memory` | Use `--no-gpu` flag or reduce image size |
| `EasyOCR downloading models` | Wait for first-time model download (~100-200MB) |
| `PyQt5 not found` | Install with `pip install PyQt5` |
| `Tesseract not found` | Install Tesseract OCR and add to PATH |
| `Permission denied` | Run as administrator (Windows) or check file permissions |

### Debug Mode

```bash
# Enable verbose logging
export VISUAL_DOM_DEBUG=1
python -m visual_dom.cv.pipeline screenshot.png

# Python logging
import logging
logging.basicConfig(level=logging.DEBUG)
```
