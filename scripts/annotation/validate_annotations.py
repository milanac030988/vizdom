"""
Validate annotation quality and consistency.

Checks:
- Missing labels
- Overlapping bounding boxes
- Class distribution
- Annotation coverage
- Common errors

Usage:
    python scripts/annotation/validate_annotations.py --input data/ui_detection_dataset
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import Counter
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.cv_model_registry import UI_ELEMENT_CLASSES


def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """Calculate Intersection over Union between two boxes."""
    # Convert from YOLO format (center_x, center_y, w, h) to corners
    def to_corners(box):
        cx, cy, w, h = box
        return [cx - w/2, cy - h/2, cx + w/2, cy + h/2]

    b1 = to_corners(box1)
    b2 = to_corners(box2)

    # Calculate intersection
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)

    # Calculate union
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def load_yolo_labels(labels_dir: Path) -> Dict[str, List[Dict]]:
    """Load all YOLO label files."""
    labels = {}

    for label_file in labels_dir.glob("*.txt"):
        boxes = []
        with open(label_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) >= 5:
                    boxes.append({
                        "class_id": int(parts[0]),
                        "x": float(parts[1]),
                        "y": float(parts[2]),
                        "w": float(parts[3]),
                        "h": float(parts[4])
                    })

        labels[label_file.stem] = boxes

    return labels


def check_overlapping_boxes(
    boxes: List[Dict],
    iou_threshold: float = 0.5
) -> List[Tuple[int, int, float]]:
    """Find overlapping bounding boxes."""
    overlaps = []

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            box1 = [boxes[i]["x"], boxes[i]["y"], boxes[i]["w"], boxes[i]["h"]]
            box2 = [boxes[j]["x"], boxes[j]["y"], boxes[j]["w"], boxes[j]["h"]]

            iou = calculate_iou(box1, box2)
            if iou > iou_threshold:
                overlaps.append((i, j, iou))

    return overlaps


def check_box_validity(boxes: List[Dict]) -> List[str]:
    """Check for invalid bounding boxes."""
    issues = []

    for i, box in enumerate(boxes):
        # Check class ID
        if box["class_id"] < 0 or box["class_id"] >= len(UI_ELEMENT_CLASSES):
            issues.append(f"Box {i}: Invalid class ID {box['class_id']}")

        # Check coordinates in range [0, 1]
        for coord in ["x", "y", "w", "h"]:
            if box[coord] < 0 or box[coord] > 1:
                issues.append(f"Box {i}: {coord}={box[coord]:.3f} out of range [0,1]")

        # Check for very small boxes
        if box["w"] < 0.01 or box["h"] < 0.01:
            issues.append(f"Box {i}: Very small box ({box['w']:.3f} x {box['h']:.3f})")

        # Check for very large boxes (likely annotation error)
        if box["w"] > 0.9 and box["h"] > 0.9:
            issues.append(f"Box {i}: Very large box ({box['w']:.3f} x {box['h']:.3f})")

    return issues


def analyze_class_distribution(all_boxes: List[Dict]) -> Dict[str, int]:
    """Analyze class distribution across all annotations."""
    class_counts = Counter()

    for box in all_boxes:
        class_id = box["class_id"]
        if 0 <= class_id < len(UI_ELEMENT_CLASSES):
            class_name = UI_ELEMENT_CLASSES[class_id]
            class_counts[class_name] += 1

    return dict(class_counts)


def check_image_label_pairs(
    images_dir: Path,
    labels_dir: Path
) -> Tuple[List[str], List[str]]:
    """Check for images without labels and labels without images."""
    image_stems = set()
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        for img in images_dir.glob(ext):
            image_stems.add(img.stem)

    label_stems = {f.stem for f in labels_dir.glob("*.txt")}

    images_without_labels = list(image_stems - label_stems)
    labels_without_images = list(label_stems - image_stems)

    return images_without_labels, labels_without_images


def generate_report(
    dataset_dir: str,
    output_file: str = None
) -> Dict[str, Any]:
    """Generate comprehensive validation report."""
    dataset_path = Path(dataset_dir)

    report = {
        "dataset_path": str(dataset_path),
        "summary": {},
        "class_distribution": {},
        "issues": [],
        "recommendations": []
    }

    # Find splits
    splits = []
    for split in ["train", "val", "test"]:
        images_dir = dataset_path / "images" / split
        labels_dir = dataset_path / "labels" / split
        if images_dir.exists() and labels_dir.exists():
            splits.append(split)

    if not splits:
        # Try flat structure
        images_dir = dataset_path / "images"
        labels_dir = dataset_path / "labels"
        if images_dir.exists() and labels_dir.exists():
            splits = ["all"]

    all_boxes = []
    total_images = 0
    total_boxes = 0

    for split in splits:
        if split == "all":
            images_dir = dataset_path / "images"
            labels_dir = dataset_path / "labels"
        else:
            images_dir = dataset_path / "images" / split
            labels_dir = dataset_path / "labels" / split

        # Load labels
        labels = load_yolo_labels(labels_dir)

        # Check image-label pairs
        missing_labels, orphan_labels = check_image_label_pairs(images_dir, labels_dir)

        if missing_labels:
            report["issues"].append({
                "type": "missing_labels",
                "split": split,
                "count": len(missing_labels),
                "files": missing_labels[:10]  # First 10
            })

        if orphan_labels:
            report["issues"].append({
                "type": "orphan_labels",
                "split": split,
                "count": len(orphan_labels),
                "files": orphan_labels[:10]
            })

        # Check each label file
        for filename, boxes in labels.items():
            all_boxes.extend(boxes)
            total_images += 1
            total_boxes += len(boxes)

            # Check validity
            validity_issues = check_box_validity(boxes)
            if validity_issues:
                report["issues"].append({
                    "type": "invalid_boxes",
                    "file": filename,
                    "split": split,
                    "details": validity_issues
                })

            # Check overlaps
            overlaps = check_overlapping_boxes(boxes)
            if overlaps:
                report["issues"].append({
                    "type": "overlapping_boxes",
                    "file": filename,
                    "split": split,
                    "overlaps": [
                        {"box_i": i, "box_j": j, "iou": f"{iou:.2f}"}
                        for i, j, iou in overlaps
                    ]
                })

    # Summary
    report["summary"] = {
        "total_images": total_images,
        "total_boxes": total_boxes,
        "avg_boxes_per_image": round(total_boxes / total_images, 2) if total_images > 0 else 0,
        "splits": splits
    }

    # Class distribution
    report["class_distribution"] = analyze_class_distribution(all_boxes)

    # Generate recommendations
    class_dist = report["class_distribution"]
    if class_dist:
        min_class = min(class_dist.values())
        max_class = max(class_dist.values())

        if max_class > min_class * 10:
            report["recommendations"].append(
                "High class imbalance detected. Consider data augmentation for minority classes."
            )

        missing_classes = set(UI_ELEMENT_CLASSES) - set(class_dist.keys())
        if missing_classes:
            report["recommendations"].append(
                f"Missing classes: {', '.join(missing_classes)}. Add more examples."
            )

    if total_images < 100:
        report["recommendations"].append(
            f"Only {total_images} images. Aim for 500+ images for good model performance."
        )

    # Print report
    print("\n" + "=" * 60)
    print("ANNOTATION VALIDATION REPORT")
    print("=" * 60)

    print(f"\nDataset: {dataset_path}")
    print(f"Total images: {report['summary']['total_images']}")
    print(f"Total boxes: {report['summary']['total_boxes']}")
    print(f"Avg boxes/image: {report['summary']['avg_boxes_per_image']}")

    print("\n--- Class Distribution ---")
    for cls, count in sorted(report["class_distribution"].items(), key=lambda x: -x[1]):
        bar = "#" * min(count // 10, 30)
        print(f"  {cls:15s} {count:5d} {bar}")

    if report["issues"]:
        print(f"\n--- Issues Found ({len(report['issues'])}) ---")
        for issue in report["issues"][:10]:
            print(f"  [{issue['type']}] {issue.get('file', issue.get('split', ''))}")

    if report["recommendations"]:
        print("\n--- Recommendations ---")
        for rec in report["recommendations"]:
            print(f"  - {rec}")

    print("=" * 60)

    # Save report
    if output_file:
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report saved to: {output_file}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Validate annotations")
    parser.add_argument("--input", type=str, required=True, help="Dataset directory")
    parser.add_argument("--output", type=str, help="Output report JSON file")
    args = parser.parse_args()

    generate_report(args.input, args.output)


if __name__ == "__main__":
    main()
