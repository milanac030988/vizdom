"""
Convert Label Studio exports to training data formats.

Supports:
- Label Studio JSON -> YOLO format (for CV detection)
- Label Studio JSON -> JSONL format (for LLM hierarchy)

Usage:
    python scripts/annotation/convert_labelstudio_to_training.py \
        --input export.json \
        --output-yolo data/ui_detection_dataset \
        --output-llm data/processed/train
"""

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple
from urllib.parse import unquote
import os

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.cv_model_registry import UI_ELEMENT_CLASSES

class_to_id = {cls: i for i, cls in enumerate(UI_ELEMENT_CLASSES)}


def load_labelstudio_export(export_file: str) -> List[Dict]:
    """Load Label Studio JSON export."""
    with open(export_file) as f:
        data = json.load(f)
    return data


def get_image_path_from_url(url: str) -> str:
    """Extract image path from Label Studio URL."""
    # Handle local file URLs
    if "local-files" in url:
        # /data/local-files/?d=/path/to/image.png
        path = url.split("?d=")[-1]
        return unquote(path)
    elif url.startswith("/data/upload/"):
        # Uploaded file
        return url.replace("/data/upload/", "")
    else:
        return url


def convert_to_yolo(
    annotations: List[Dict],
    output_dir: str,
    copy_images: bool = True
) -> Tuple[int, int]:
    """
    Convert Label Studio annotations to YOLO format.

    Returns:
        Tuple of (num_images, num_boxes)
    """
    output_path = Path(output_dir)
    images_dir = output_path / "images" / "train"
    labels_dir = output_path / "labels" / "train"

    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    num_images = 0
    num_boxes = 0

    for task in annotations:
        # Get image info
        image_url = task.get("data", {}).get("image", "")
        image_path = get_image_path_from_url(image_url)

        if not image_path:
            continue

        # Get image dimensions from annotations or file
        img_width = task.get("data", {}).get("width")
        img_height = task.get("data", {}).get("height")

        # Process annotations
        results = task.get("annotations", [])
        if not results:
            continue

        # Use the most recent annotation
        latest_annotation = results[-1]
        regions = latest_annotation.get("result", [])

        lines = []
        for region in regions:
            if region.get("type") != "rectanglelabels":
                continue

            value = region.get("value", {})

            # Get label
            labels = value.get("rectanglelabels", [])
            if not labels:
                continue

            label = labels[0].lower()
            if label not in class_to_id:
                continue

            class_id = class_to_id[label]

            # Get bounding box (Label Studio uses percentages)
            x_pct = value.get("x", 0) / 100
            y_pct = value.get("y", 0) / 100
            w_pct = value.get("width", 0) / 100
            h_pct = value.get("height", 0) / 100

            # Convert to YOLO format (center x, center y, width, height)
            x_center = x_pct + w_pct / 2
            y_center = y_pct + h_pct / 2

            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_pct:.6f} {h_pct:.6f}")
            num_boxes += 1

        if lines:
            # Save label file
            img_name = Path(image_path).stem
            label_file = labels_dir / f"{img_name}.txt"

            with open(label_file, "w") as f:
                f.write("\n".join(lines))

            # Copy image if requested
            if copy_images and Path(image_path).exists():
                dest_img = images_dir / Path(image_path).name
                shutil.copy(image_path, dest_img)

            num_images += 1

    return num_images, num_boxes


def convert_to_llm_training(
    annotations: List[Dict],
    output_file: str
) -> int:
    """
    Convert Label Studio annotations to LLM training JSONL.

    Returns:
        Number of examples created
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    examples = []

    for task in annotations:
        results = task.get("annotations", [])
        if not results:
            continue

        latest_annotation = results[-1]
        regions = latest_annotation.get("result", [])

        # Extract elements
        elements = []
        relations = []

        for region in regions:
            region_type = region.get("type")

            if region_type == "rectanglelabels":
                value = region.get("value", {})
                labels = value.get("rectanglelabels", [])

                if labels:
                    elem = {
                        "id": region.get("id", f"E{len(elements)+1}"),
                        "visual_type": labels[0].lower(),
                        "x": value.get("x", 0),
                        "y": value.get("y", 0),
                        "width": value.get("width", 0),
                        "height": value.get("height", 0),
                    }

                    # Get additional properties
                    for prop_region in regions:
                        if (prop_region.get("type") == "choices" and
                            prop_region.get("parentID") == region.get("id")):
                            choices = prop_region.get("value", {}).get("choices", [])
                            if "clickable" in choices:
                                elem["clickable"] = True
                            if "editable" in choices:
                                elem["editable"] = True

                        if (prop_region.get("type") == "textarea" and
                            prop_region.get("parentID") == region.get("id")):
                            text_value = prop_region.get("value", {}).get("text", [""])[0]
                            if text_value:
                                prop_name = prop_region.get("from_name", "text")
                                elem[prop_name] = text_value

                    elements.append(elem)

            elif region_type == "relation":
                relations.append({
                    "from": region.get("from_id"),
                    "to": region.get("to_id"),
                    "type": region.get("labels", ["contains"])[0]
                })

        if elements:
            # Build tree draft (flat structure)
            tree_draft = {
                "id": "root",
                "role": "FrameLayout",
                "children": [{"id": e["id"], "role": "Unknown"} for e in elements]
            }

            # Build target tree from relations
            tree_target = build_tree_from_relations(elements, relations)

            # Compute edits
            edits = compute_edits_from_diff(tree_draft, tree_target, elements)

            # Format elements for prompt
            elements_text = format_elements_for_prompt(elements)

            examples.append({
                "elements": elements_text,
                "tree_draft": tree_draft,
                "edits": edits
            })

    # Write JSONL
    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    return len(examples)


def format_elements_for_prompt(elements: List[Dict]) -> str:
    """Format elements for LLM prompt without coordinates."""
    # Sort by position
    sorted_elements = sorted(elements, key=lambda e: (e.get("y", 0), e.get("x", 0)))

    lines = []
    for elem in sorted_elements:
        parts = [f"{elem['id']}: {elem['visual_type']}"]

        if elem.get("text_content"):
            parts.append(f"'{elem['text_content']}'")

        if elem.get("clickable"):
            parts.append("[clickable]")

        if elem.get("editable"):
            parts.append("[editable]")

        lines.append(" ".join(parts))

    return "\n".join(lines)


def build_tree_from_relations(
    elements: List[Dict],
    relations: List[Dict]
) -> Dict:
    """Build tree structure from elements and relations."""
    # Build parent-child mapping
    children_map: Dict[str, List[str]] = {}
    parent_map: Dict[str, str] = {}

    for rel in relations:
        if rel["type"] == "contains":
            parent_id = rel["from"]
            child_id = rel["to"]

            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(child_id)
            parent_map[child_id] = parent_id

    # Find root elements (no parent)
    root_children = [e["id"] for e in elements if e["id"] not in parent_map]

    def build_subtree(elem_id: str) -> Dict:
        elem = next((e for e in elements if e["id"] == elem_id), None)
        if not elem:
            return {"id": elem_id, "role": "Unknown"}

        node = {
            "id": elem_id,
            "role": elem.get("role", elem.get("visual_type", "Unknown").title()),
        }

        if elem_id in children_map:
            node["children"] = [build_subtree(cid) for cid in children_map[elem_id]]

        if elem.get("clickable"):
            node["clickable"] = True
        if elem.get("editable"):
            node["editable"] = True

        return node

    return {
        "id": "root",
        "role": "FrameLayout",
        "children": [build_subtree(cid) for cid in root_children]
    }


def compute_edits_from_diff(
    draft: Dict,
    target: Dict,
    elements: List[Dict]
) -> List[Dict]:
    """Compute edits needed to transform draft into target."""
    edits = []

    def get_parent_map(tree: Dict, parent_id: str = None) -> Dict[str, str]:
        result = {}
        for child in tree.get("children", []):
            result[child["id"]] = tree["id"]
            result.update(get_parent_map(child, child["id"]))
        return result

    draft_parents = get_parent_map(draft)
    target_parents = get_parent_map(target)

    # Find parent changes
    for elem_id, target_parent in target_parents.items():
        draft_parent = draft_parents.get(elem_id)
        if draft_parent != target_parent:
            edits.append({
                "op": "set_parent",
                "element": elem_id,
                "parent": target_parent
            })

    # Find role assignments
    def get_roles(tree: Dict) -> Dict[str, str]:
        result = {tree["id"]: tree.get("role", "Unknown")}
        for child in tree.get("children", []):
            result.update(get_roles(child))
        return result

    target_roles = get_roles(target)
    for elem in elements:
        elem_id = elem["id"]
        target_role = target_roles.get(elem_id, "Unknown")
        if target_role != "Unknown":
            edits.append({
                "op": "set_role",
                "element": elem_id,
                "role": target_role
            })

    return edits


def main():
    parser = argparse.ArgumentParser(description="Convert Label Studio to training format")
    parser.add_argument("--input", type=str, required=True, help="Label Studio JSON export")
    parser.add_argument("--output-yolo", type=str, help="Output dir for YOLO format")
    parser.add_argument("--output-llm", type=str, help="Output file for LLM JSONL")
    parser.add_argument("--no-copy-images", action="store_true", help="Don't copy images")
    args = parser.parse_args()

    print(f"Loading annotations from {args.input}")
    annotations = load_labelstudio_export(args.input)
    print(f"Found {len(annotations)} annotated tasks")

    if args.output_yolo:
        print(f"\nConverting to YOLO format...")
        num_images, num_boxes = convert_to_yolo(
            annotations,
            args.output_yolo,
            copy_images=not args.no_copy_images
        )
        print(f"Created {num_images} label files with {num_boxes} bounding boxes")
        print(f"Output: {args.output_yolo}")

    if args.output_llm:
        print(f"\nConverting to LLM training format...")
        num_examples = convert_to_llm_training(annotations, args.output_llm)
        print(f"Created {num_examples} training examples")
        print(f"Output: {args.output_llm}")


if __name__ == "__main__":
    main()
