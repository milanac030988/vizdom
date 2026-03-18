"""
Convert various annotation formats to YOLO format for UI detection training.

Supported input formats:
- COCO JSON
- Pascal VOC XML
- Label Studio JSON
- Custom JSON (our Visual DOM format)

Output: YOLO format (txt files with: class_id x_center y_center width height)
"""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple
import shutil

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.cv_model_registry import UI_ELEMENT_CLASSES


class_to_id = {cls: i for i, cls in enumerate(UI_ELEMENT_CLASSES)}


def convert_coco_to_yolo(coco_json: str, output_dir: str, images_dir: str):
    """Convert COCO format annotations to YOLO format."""
    with open(coco_json) as f:
        coco = json.load(f)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build category mapping
    coco_cat_to_our_class = {}
    for cat in coco.get("categories", []):
        cat_name = cat["name"].lower().replace(" ", "_")
        if cat_name in class_to_id:
            coco_cat_to_our_class[cat["id"]] = class_to_id[cat_name]

    # Build image id to filename mapping
    image_info = {img["id"]: img for img in coco.get("images", [])}

    # Group annotations by image
    annotations_by_image: Dict[int, List] = {}
    for ann in coco.get("annotations", []):
        img_id = ann["image_id"]
        if img_id not in annotations_by_image:
            annotations_by_image[img_id] = []
        annotations_by_image[img_id].append(ann)

    # Convert each image
    converted = 0
    for img_id, anns in annotations_by_image.items():
        img_info = image_info.get(img_id)
        if not img_info:
            continue

        img_w = img_info["width"]
        img_h = img_info["height"]
        img_filename = Path(img_info["file_name"]).stem

        lines = []
        for ann in anns:
            cat_id = ann["category_id"]
            if cat_id not in coco_cat_to_our_class:
                continue

            class_id = coco_cat_to_our_class[cat_id]

            # COCO bbox: [x, y, width, height] (absolute)
            x, y, w, h = ann["bbox"]

            # Convert to YOLO: x_center, y_center, width, height (normalized)
            x_center = (x + w / 2) / img_w
            y_center = (y + h / 2) / img_h
            w_norm = w / img_w
            h_norm = h / img_h

            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")

        if lines:
            label_file = output_path / f"{img_filename}.txt"
            with open(label_file, "w") as f:
                f.write("\n".join(lines))
            converted += 1

    print(f"Converted {converted} images from COCO format")


def convert_voc_to_yolo(voc_dir: str, output_dir: str):
    """Convert Pascal VOC XML annotations to YOLO format."""
    voc_path = Path(voc_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    converted = 0
    for xml_file in voc_path.glob("*.xml"):
        tree = ET.parse(xml_file)
        root = tree.getroot()

        # Get image size
        size = root.find("size")
        img_w = int(size.find("width").text)
        img_h = int(size.find("height").text)

        lines = []
        for obj in root.findall("object"):
            class_name = obj.find("name").text.lower().replace(" ", "_")
            if class_name not in class_to_id:
                continue

            class_id = class_to_id[class_name]

            bbox = obj.find("bndbox")
            xmin = float(bbox.find("xmin").text)
            ymin = float(bbox.find("ymin").text)
            xmax = float(bbox.find("xmax").text)
            ymax = float(bbox.find("ymax").text)

            # Convert to YOLO format
            x_center = (xmin + xmax) / 2 / img_w
            y_center = (ymin + ymax) / 2 / img_h
            w_norm = (xmax - xmin) / img_w
            h_norm = (ymax - ymin) / img_h

            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")

        if lines:
            label_file = output_path / f"{xml_file.stem}.txt"
            with open(label_file, "w") as f:
                f.write("\n".join(lines))
            converted += 1

    print(f"Converted {converted} images from VOC format")


def convert_visual_dom_to_yolo(dom_json: str, output_dir: str, img_size: Tuple[int, int]):
    """Convert our Visual DOM elements to YOLO format."""
    with open(dom_json) as f:
        data = json.load(f)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    img_w, img_h = img_size
    elements = data.get("elements", [])

    lines = []
    for elem in elements:
        visual_type = elem.get("visual_type", "unknown").lower()
        if visual_type not in class_to_id:
            # Map to closest class
            type_mapping = {
                "edittext": "input_field",
                "textview": "text",
                "imageview": "image",
                "imagebutton": "button",
            }
            visual_type = type_mapping.get(visual_type, "container")

        if visual_type not in class_to_id:
            continue

        class_id = class_to_id[visual_type]
        x1, y1, x2, y2 = elem["bounds"]

        x_center = (x1 + x2) / 2 / img_w
        y_center = (y1 + y2) / 2 / img_h
        w_norm = (x2 - x1) / img_w
        h_norm = (y2 - y1) / img_h

        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")

    if lines:
        label_file = output_path / f"{Path(dom_json).stem}.txt"
        with open(label_file, "w") as f:
            f.write("\n".join(lines))

    return len(lines)


def split_dataset(
    images_dir: str,
    labels_dir: str,
    output_dir: str,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1
):
    """Split dataset into train/val/test sets."""
    import random

    images_path = Path(images_dir)
    labels_path = Path(labels_dir)
    output_path = Path(output_dir)

    # Find all images with labels
    image_files = list(images_path.glob("*.png")) + list(images_path.glob("*.jpg"))
    paired_files = []

    for img_file in image_files:
        label_file = labels_path / f"{img_file.stem}.txt"
        if label_file.exists():
            paired_files.append((img_file, label_file))

    random.shuffle(paired_files)

    n = len(paired_files)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    splits = {
        "train": paired_files[:n_train],
        "val": paired_files[n_train:n_train + n_val],
        "test": paired_files[n_train + n_val:]
    }

    for split_name, files in splits.items():
        img_out = output_path / "images" / split_name
        lbl_out = output_path / "labels" / split_name
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for img_file, label_file in files:
            shutil.copy(img_file, img_out / img_file.name)
            shutil.copy(label_file, lbl_out / label_file.name)

        print(f"{split_name}: {len(files)} images")

    print(f"\nDataset split saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert annotations to YOLO format")
    parser.add_argument("--format", choices=["coco", "voc", "visual_dom"], required=True)
    parser.add_argument("--input", type=str, required=True, help="Input file or directory")
    parser.add_argument("--output", type=str, required=True, help="Output directory")
    parser.add_argument("--images", type=str, help="Images directory (for COCO)")
    parser.add_argument("--img_size", type=str, default="1080,1920", help="Image size WxH")
    args = parser.parse_args()

    if args.format == "coco":
        convert_coco_to_yolo(args.input, args.output, args.images)
    elif args.format == "voc":
        convert_voc_to_yolo(args.input, args.output)
    elif args.format == "visual_dom":
        w, h = map(int, args.img_size.split(","))
        convert_visual_dom_to_yolo(args.input, args.output, (w, h))


if __name__ == "__main__":
    main()
