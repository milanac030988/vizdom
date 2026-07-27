#!/usr/bin/env python
"""
Convert synthetic dataset to YOLO format and optionally train YOLOv8.

Usage:
    # Convert only
    python scripts/training/cv/prepare_and_train.py --dataset data/synthetic

    # Convert + train
    python scripts/training/cv/prepare_and_train.py --dataset data/synthetic --train

    # Train with specific model size
    python scripts/training/cv/prepare_and_train.py --dataset data/synthetic --train --model yolov8s --epochs 50
"""

import sys
import os
import json
import shutil
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# UI element classes (must match pipeline)
UI_ELEMENT_CLASSES = [
    "button", "text", "icon", "input_field", "checkbox",
    "radio_button", "toggle", "slider", "dropdown", "image",
    "container", "toolbar", "navbar", "card", "list_item",
]

# Map synthetic template types to YOLO class names
TYPE_MAPPING = {
    "button": "button",
    "text": "text",
    "icon": "icon",
    "input_field": "input_field",
    "checkbox": "checkbox",
    "toggle": "toggle",
    "dropdown": "dropdown",
    "block": "container",
    "container": "container",
    "divider": None,  # Skip dividers (too thin for YOLO)
    "unknown": None,
}


def convert_visual_dom_to_yolo(
    json_path: str,
    output_label_path: str,
    img_width: int,
    img_height: int,
) -> int:
    """Convert a VizDOM ground truth JSON to YOLO label format.

    Returns number of valid elements converted.
    """
    with open(json_path, 'r') as f:
        data = json.load(f)

    elements = data.get("elements", [])
    img_size = data.get("image_size", {})
    w = img_size.get("width", img_width)
    h = img_size.get("height", img_height)

    lines = []
    for elem in elements:
        vtype = elem.get("visual_type", "unknown")
        mapped = TYPE_MAPPING.get(vtype)
        if mapped is None:
            continue

        if mapped not in UI_ELEMENT_CLASSES:
            continue

        class_id = UI_ELEMENT_CLASSES.index(mapped)
        bounds = elem.get("bounds", [0, 0, 0, 0])
        x1, y1, x2, y2 = bounds

        # Convert to YOLO format: x_center y_center width height (normalized)
        bw = x2 - x1
        bh = y2 - y1
        if bw <= 0 or bh <= 0:
            continue

        x_center = (x1 + x2) / 2.0 / w
        y_center = (y1 + y2) / 2.0 / h
        norm_w = bw / w
        norm_h = bh / h

        # Clamp to [0, 1]
        x_center = max(0, min(1, x_center))
        y_center = max(0, min(1, y_center))
        norm_w = max(0, min(1, norm_w))
        norm_h = max(0, min(1, norm_h))

        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")

    with open(output_label_path, 'w') as f:
        f.write("\n".join(lines))

    return len(lines)


def convert_dataset(dataset_dir: str, output_dir: str) -> dict:
    """Convert a full synthetic dataset to YOLO format."""
    ds_path = Path(dataset_dir)
    out_path = Path(output_dir)

    # Load manifest
    manifest_path = ds_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {dataset_dir}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    config = manifest.get("config", {})
    img_w = config.get("width", 800)
    img_h = config.get("height", 600)

    stats = {"train": 0, "val": 0, "total_elements": 0, "skipped": 0}

    for split_name, yolo_split in [("train", "train"), ("test", "val")]:
        entries = manifest.get(split_name, [])

        img_out = out_path / "images" / yolo_split
        lbl_out = out_path / "labels" / yolo_split
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            img_src = ds_path / entry["image"]
            json_src = ds_path / entry["label"]

            if not img_src.exists() or not json_src.exists():
                stats["skipped"] += 1
                continue

            name = entry.get("name", img_src.stem)

            # Copy image
            img_dst = img_out / f"{name}.png"
            shutil.copy2(img_src, img_dst)

            # Convert label
            lbl_dst = lbl_out / f"{name}.txt"
            n_elems = convert_visual_dom_to_yolo(str(json_src), str(lbl_dst), img_w, img_h)
            stats["total_elements"] += n_elems
            stats[yolo_split] += 1

    # Create data.yaml
    yaml_path = out_path / "data.yaml"
    yaml_content = f"""# VizDOM YOLO Dataset
# Auto-generated from {dataset_dir}

path: {out_path.resolve()}
train: images/train
val: images/val

nc: {len(UI_ELEMENT_CLASSES)}
names: {UI_ELEMENT_CLASSES}
"""
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)

    stats["yaml_path"] = str(yaml_path)
    return stats


def train_yolo(
    data_yaml: str,
    model: str = "yolov8s.pt",
    epochs: int = 100,
    batch: int = 16,
    imgsz: int = 640,
    project: str = None,
    name: str = "vizdom_ui",
):
    """Train YOLOv8 on the prepared dataset."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("Error: ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    if project is None:
        project = str(PROJECT_ROOT / "models" / "cv_detection")

    print(f"\nStarting YOLO training:")
    print(f"  Model: {model}")
    print(f"  Data: {data_yaml}")
    print(f"  Epochs: {epochs}")
    print(f"  Batch: {batch}")
    print(f"  Image size: {imgsz}")
    print(f"  Output: {project}/{name}")

    yolo = YOLO(model)

    results = yolo.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        project=project,
        name=name,
        exist_ok=True,
        # Augmentation settings (no flips for UI)
        flipud=0.0,
        fliplr=0.0,
        mosaic=0.5,
        mixup=0.1,
        # Optimizer
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        warmup_epochs=3,
        # Other
        verbose=True,
        save=True,
        plots=True,
    )

    # Copy best model to a known location
    best_path = Path(project) / name / "weights" / "best.pt"
    if best_path.exists():
        dest = PROJECT_ROOT / "models" / "pretrained" / "yolo_ui_best.pt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best_path, dest)
        print(f"\nBest model saved to: {dest}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Convert dataset to YOLO format and train")
    parser.add_argument("--dataset", "-d", required=True,
                        help="Path to synthetic dataset (with manifest.json)")
    parser.add_argument("--output", "-o", default=None,
                        help="YOLO output directory (default: <dataset>/yolo)")
    parser.add_argument("--train", action="store_true",
                        help="Train YOLOv8 after conversion")
    parser.add_argument("--model", default="yolov8s.pt",
                        help="YOLO base model (default: yolov8s.pt)")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--name", default="vizdom_ui",
                        help="Training run name")

    args = parser.parse_args()

    output_dir = args.output or str(Path(args.dataset) / "yolo")

    # Convert
    print(f"Converting dataset: {args.dataset}")
    print(f"Output: {output_dir}")
    stats = convert_dataset(args.dataset, output_dir)

    print(f"\nConversion complete:")
    print(f"  Train images: {stats['train']}")
    print(f"  Val images: {stats['val']}")
    print(f"  Total elements: {stats['total_elements']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  YAML: {stats['yaml_path']}")

    # Train
    if args.train:
        train_yolo(
            data_yaml=stats["yaml_path"],
            model=args.model,
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            name=args.name,
        )


if __name__ == "__main__":
    main()
