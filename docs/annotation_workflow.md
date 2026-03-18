# Data Annotation Workflow Guide

This guide explains how to create training data for the Visual DOM project.

## Overview

You need to annotate two types of data:

1. **CV Detection Data**: Bounding boxes around UI elements (for YOLOv8 training)
2. **LLM Hierarchy Data**: Tree structure relationships (for Qwen/LLM finetuning)

## Quick Start

### Option 1: Simple Web Annotator (Recommended for small datasets)

```bash
# Install Flask
pip install flask

# Run the annotator
python tools/annotator/app.py --images data/raw/screenshots --output data/annotations

# Open http://localhost:5000
```

### Option 2: Label Studio (Recommended for team collaboration)

```bash
# Install Label Studio
pip install label-studio

# Set up project
python scripts/annotation/setup_label_studio.py --project "UI Detection v1" --images data/raw/screenshots

# Start Label Studio
label-studio start
```

## Step-by-Step Workflow

### Step 1: Capture Screenshots

```bash
# Desktop screenshots (batch mode)
python scripts/annotation/capture_screenshots.py --platform desktop --batch --prefix app_name

# Android screenshots
python scripts/annotation/capture_screenshots.py --platform android --batch --prefix mobile_app
```

**Tips:**
- Capture diverse screens (login, home, settings, forms, lists)
- Include different states (loading, error, empty, populated)
- Aim for 500+ screenshots for good model performance

### Step 2: Annotate UI Elements

#### Using Simple Annotator:
1. Run `python tools/annotator/app.py --images data/raw/screenshots --output data/annotations`
2. Open http://localhost:5000
3. Draw bounding boxes around UI elements
4. Select the correct class for each box
5. Press 'S' to save, 'D' for next image

#### Using Label Studio:
1. Create project with the labeling config from `setup_label_studio.py`
2. Import images
3. Draw bounding boxes and select labels
4. Export as JSON when done

### Step 3: Convert to Training Format

```bash
# From Simple Annotator (already saves YOLO format)
# Just organize into train/val splits

# From Label Studio
python scripts/annotation/convert_labelstudio_to_training.py \
    --input labelstudio_export.json \
    --output-yolo data/ui_detection_dataset \
    --output-llm data/processed/train/hierarchy_data.jsonl
```

### Step 4: Validate Annotations

```bash
python scripts/annotation/validate_annotations.py --input data/ui_detection_dataset
```

This checks for:
- Missing labels
- Overlapping boxes
- Class distribution imbalance
- Invalid coordinates

### Step 5: Split Dataset

```bash
python scripts/data_prep/convert_to_yolo.py \
    --split \
    --images data/annotations \
    --labels data/annotations \
    --output data/ui_detection_dataset \
    --train-ratio 0.8 \
    --val-ratio 0.1
```

## Annotation Guidelines

### UI Element Classes

| Class | Description | Examples |
|-------|-------------|----------|
| button | Clickable buttons | Submit, Cancel, Login |
| text | Static text | Labels, titles, paragraphs |
| icon | Small symbolic images | Menu icon, search icon |
| input_field | Text input boxes | Search bar, text field |
| checkbox | Square checkable boxes | Remember me, Terms |
| radio_button | Round selection buttons | Gender selection |
| toggle | On/off switches | Enable notifications |
| slider | Draggable range controls | Volume, brightness |
| dropdown | Expandable menus | Country selector |
| image | Photos/illustrations | Profile photo, banner |
| container | Grouped UI areas | Cards, panels |
| toolbar | Action bars | Top bar with buttons |
| navbar | Navigation bars | Bottom navigation |
| card | Content cards | Product card, post |
| list_item | Items in a list | Chat message, menu item |

### Best Practices

1. **Draw Tight Boxes**: Minimize whitespace around elements
2. **Be Consistent**: Same element type = same class across images
3. **Include Everything**: Even small icons and separators
4. **Don't Overlap**: One box per distinct element
5. **Handle Ambiguity**: When unsure, use the more general class

### Common Mistakes to Avoid

- ❌ Boxing the entire screen as "container"
- ❌ Missing small icons
- ❌ Inconsistent labeling (button vs icon for same element)
- ❌ Overlapping boxes for the same element
- ❌ Very loose bounding boxes

## Dataset Size Recommendations

| Quality Level | Images | Boxes/Image | Total Boxes |
|--------------|--------|-------------|-------------|
| Minimum | 100 | 10 | 1,000 |
| Good | 500 | 15 | 7,500 |
| Production | 2,000+ | 20 | 40,000+ |

## File Structure After Annotation

```
data/
├── raw/
│   └── screenshots/           # Original screenshots
├── annotations/               # Raw annotation files
├── ui_detection_dataset/      # Final YOLO dataset
│   ├── images/
│   │   ├── train/
│   │   ├── val/
│   │   └── test/
│   ├── labels/
│   │   ├── train/
│   │   ├── val/
│   │   └── test/
│   └── ui_detection.yaml      # Dataset config
└── processed/
    └── train/
        └── hierarchy_data.jsonl   # LLM training data
```

## Training After Annotation

### Train CV Model (YOLOv8)

```bash
python scripts/training/cv/train_yolo.py \
    --model yolov8s \
    --data data/ui_detection.yaml \
    --epochs 100
```

### Train LLM (Hierarchy Refinement)

```bash
python scripts/training/finetune_lora.py \
    --model qwen2.5-3b \
    --data data/processed/train
```

## Tips for Faster Annotation

1. **Use Keyboard Shortcuts**: 1-9 for classes, A/D for navigation
2. **Annotate in Batches**: Focus on one screen type at a time
3. **Start with Common Elements**: Annotate buttons and text first
4. **Use Pre-annotation**: Run traditional CV first, then correct

## Getting Help

- Check `scripts/annotation/validate_annotations.py` for common issues
- Review `data/annotation_projects/*/guidelines.md` for class definitions
- Run validation before training to catch problems early
