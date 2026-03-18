"""
Train YOLOv8 for UI element detection.

Usage:
    python scripts/training/cv/train_yolo.py --data data/cv_dataset.yaml --model yolov8s

Prerequisites:
    pip install ultralytics

Data format: YOLO format
    data/
    ├── images/
    │   ├── train/
    │   └── val/
    └── labels/
        ├── train/
        └── val/

Label format (per image): class_id x_center y_center width height (normalized 0-1)
"""

import argparse
from pathlib import Path
import yaml

try:
    from ultralytics import YOLO
except ImportError:
    print("Please install ultralytics: pip install ultralytics")
    exit(1)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from models.configs.cv_model_registry import (
    get_cv_model_config,
    UI_ELEMENT_CLASSES,
    CV_MODEL_REGISTRY
)


def parse_args():
    parser = argparse.ArgumentParser(description="Train YOLO for UI detection")
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8s",
        choices=["yolov8n", "yolov8s", "yolov8m"],
        help="YOLO model size"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/ui_detection.yaml",
        help="Path to dataset YAML"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Training epochs"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Image size"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/cv_detection",
        help="Output directory"
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Resume from checkpoint"
    )
    return parser.parse_args()


def create_dataset_yaml(output_path: str, data_root: str):
    """Create YOLO dataset configuration YAML."""
    config = {
        "path": data_root,
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(UI_ELEMENT_CLASSES),
        "names": UI_ELEMENT_CLASSES
    }

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Created dataset config: {output_path}")
    return output_path


def main():
    args = parse_args()

    config = get_cv_model_config(args.model)
    print(f"Training {config.name} for UI element detection")
    print(f"Classes: {len(UI_ELEMENT_CLASSES)}")

    # Check if dataset exists
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"\nDataset config not found: {args.data}")
        print("Creating example dataset structure...")
        create_example_dataset_structure()
        return

    # Load pretrained YOLO
    if args.resume:
        model = YOLO(args.resume)
        print(f"Resuming from {args.resume}")
    else:
        model = YOLO(config.model_id)
        print(f"Starting from pretrained {config.model_id}")

    # Train
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        project=args.output,
        name=f"{args.model}_ui_detection",
        exist_ok=True,
        pretrained=True,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        warmup_epochs=3,
        augment=True,
        hsv_h=0.015,
        hsv_s=0.4,
        hsv_v=0.4,
        translate=0.1,
        scale=0.2,
        flipud=0.0,  # Don't flip UI vertically
        fliplr=0.0,  # Don't flip UI horizontally (text would be reversed)
        mosaic=0.5,
        mixup=0.1,
    )

    print(f"\nTraining complete!")
    print(f"Best model saved to: {results.save_dir}/weights/best.pt")

    # Validate
    metrics = model.val()
    print(f"\nValidation mAP50: {metrics.box.map50:.3f}")
    print(f"Validation mAP50-95: {metrics.box.map:.3f}")


def create_example_dataset_structure():
    """Create example dataset directory structure."""
    base = Path("data/ui_detection_dataset")

    dirs = [
        base / "images" / "train",
        base / "images" / "val",
        base / "images" / "test",
        base / "labels" / "train",
        base / "labels" / "val",
        base / "labels" / "test",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Create example label file
    example_label = base / "labels" / "train" / "example.txt"
    with open(example_label, "w") as f:
        f.write("# YOLO format: class_id x_center y_center width height\n")
        f.write("# All values normalized to 0-1\n")
        f.write("# Example: button at center of 1080x1920 screen\n")
        f.write("0 0.5 0.5 0.2 0.05\n")

    # Create dataset YAML
    create_dataset_yaml(
        "data/ui_detection.yaml",
        str(base.absolute())
    )

    print(f"\nCreated example dataset structure at: {base}")
    print("\nNext steps:")
    print("1. Add screenshot images to images/train/ and images/val/")
    print("2. Create corresponding label files in labels/train/ and labels/val/")
    print("3. Use a labeling tool like Label Studio or CVAT")
    print("4. Run training: python scripts/training/cv/train_yolo.py")

    # Print class mapping
    print("\nClass mapping:")
    for i, cls in enumerate(UI_ELEMENT_CLASSES):
        print(f"  {i}: {cls}")


if __name__ == "__main__":
    main()
