"""
Create training data for UI hierarchy refinement model.

This script helps create training examples from:
1. Screenshots + manually annotated DOM JSON pairs
2. Synthetic generation from UI frameworks

Training data format (JSONL):
{
    "elements": "E1: Button 'Login' at top-right...",
    "tree_draft": {"id": "root", "children": [...]},
    "edits": [{"op": "set_parent", "element": "E1", "parent": "C1"}, ...]
}
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass


@dataclass
class TrainingExample:
    """A single training example."""
    screenshot_path: str
    elements: List[Dict[str, Any]]
    tree_draft: Dict[str, Any]
    tree_target: Dict[str, Any]
    edits: List[Dict[str, Any]]


def format_elements_for_prompt(elements: List[Dict]) -> str:
    """
    Format elements for LLM prompt WITHOUT coordinates.
    Use relative descriptions instead.
    """
    lines = []

    # Sort elements by position (top-to-bottom, left-to-right)
    sorted_elements = sorted(
        elements,
        key=lambda e: (e["bounds"][1], e["bounds"][0])  # y, x
    )

    for i, elem in enumerate(sorted_elements):
        elem_id = elem["id"]
        visual_type = elem.get("visual_type", "unknown")
        text = elem.get("ocr_text", "")

        # Describe position relative to other elements
        position_hints = _get_position_hints(elem, sorted_elements)

        # Build description
        desc_parts = [f"{elem_id}: {visual_type}"]
        if text:
            desc_parts.append(f"'{text}'")
        if position_hints:
            desc_parts.append(f"({position_hints})")

        lines.append(" ".join(desc_parts))

    return "\n".join(lines)


def _get_position_hints(elem: Dict, all_elements: List[Dict]) -> str:
    """Generate relative position hints for an element."""
    hints = []
    bounds = elem["bounds"]
    x1, y1, x2, y2 = bounds
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2

    # Find neighbors
    for other in all_elements:
        if other["id"] == elem["id"]:
            continue

        ox1, oy1, ox2, oy2 = other["bounds"]
        other_text = other.get("ocr_text", "")

        # Check if directly above/below/left/right
        if abs(center_x - (ox1 + ox2) // 2) < 50:  # Vertically aligned
            if oy2 < y1 and y1 - oy2 < 100:
                hints.append(f"below '{other_text}'" if other_text else f"below {other['id']}")
                break

        if abs(center_y - (oy1 + oy2) // 2) < 30:  # Horizontally aligned
            if ox2 < x1 and x1 - ox2 < 100:
                hints.append(f"right of '{other_text}'" if other_text else f"right of {other['id']}")
                break

    return ", ".join(hints[:2])  # Limit hints


def compute_edits(draft: Dict, target: Dict) -> List[Dict]:
    """
    Compute the tree edits needed to transform draft into target.
    """
    edits = []

    # Build node lookup for both trees
    draft_nodes = _flatten_tree(draft)
    target_nodes = _flatten_tree(target)

    # Find parent changes
    for node_id, target_node in target_nodes.items():
        if node_id in draft_nodes:
            draft_node = draft_nodes[node_id]

            # Check parent change
            if draft_node.get("parent_id") != target_node.get("parent_id"):
                edits.append({
                    "op": "set_parent",
                    "element": node_id,
                    "parent": target_node.get("parent_id")
                })

            # Check role change
            if draft_node.get("role") != target_node.get("role"):
                edits.append({
                    "op": "set_role",
                    "element": node_id,
                    "role": target_node.get("role")
                })

            # Check flag changes
            flag_keys = ["clickable", "editable", "scrollable"]
            flag_changes = {}
            for key in flag_keys:
                if draft_node.get(key) != target_node.get(key):
                    flag_changes[key] = target_node.get(key, False)

            if flag_changes:
                edits.append({
                    "op": "set_flags",
                    "element": node_id,
                    **flag_changes
                })

    # Find new containers in target
    for node_id, target_node in target_nodes.items():
        if node_id not in draft_nodes and target_node.get("children"):
            edits.append({
                "op": "create_container",
                "id": node_id,
                "type": target_node.get("role", "Container"),
                "children": [c["id"] for c in target_node.get("children", [])]
            })

    return edits


def _flatten_tree(tree: Dict, parent_id: str = None) -> Dict[str, Dict]:
    """Flatten tree into dict of node_id -> node_info."""
    result = {}

    node_id = tree.get("id")
    if node_id:
        result[node_id] = {**tree, "parent_id": parent_id}

        for child in tree.get("children", []):
            result.update(_flatten_tree(child, node_id))

    return result


def create_example_from_annotation(
    annotation_path: Path,
    elements_path: Path
) -> TrainingExample:
    """
    Create training example from annotation files.

    Expected files:
    - elements.json: CV-detected elements with bounds
    - draft.json: Coarse hierarchy builder output
    - target.json: Human-corrected target hierarchy
    """
    annotation_dir = annotation_path.parent

    with open(elements_path) as f:
        elements = json.load(f)

    draft_path = annotation_dir / "draft.json"
    target_path = annotation_dir / "target.json"

    with open(draft_path) as f:
        tree_draft = json.load(f)

    with open(target_path) as f:
        tree_target = json.load(f)

    # Compute edits
    edits = compute_edits(tree_draft, tree_target)

    # Find screenshot
    screenshot_path = None
    for ext in [".png", ".jpg", ".jpeg"]:
        candidate = annotation_dir / f"screenshot{ext}"
        if candidate.exists():
            screenshot_path = str(candidate)
            break

    return TrainingExample(
        screenshot_path=screenshot_path,
        elements=elements,
        tree_draft=tree_draft,
        tree_target=tree_target,
        edits=edits
    )


def export_to_jsonl(examples: List[TrainingExample], output_path: Path):
    """Export training examples to JSONL format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for ex in examples:
            record = {
                "elements": format_elements_for_prompt(ex.elements),
                "tree_draft": ex.tree_draft,
                "edits": ex.edits
            }
            f.write(json.dumps(record) + "\n")

    print(f"Exported {len(examples)} examples to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Create training data")
    parser.add_argument(
        "--annotations",
        type=str,
        default="data/raw/annotations",
        help="Path to annotation directory"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/processed/train/training_data.jsonl",
        help="Output JSONL file"
    )
    args = parser.parse_args()

    annotations_path = Path(args.annotations)

    if not annotations_path.exists():
        print(f"Creating example annotation structure at {annotations_path}")
        create_example_annotation_structure(annotations_path)
        print("Please add your annotations and run again.")
        return

    # Find all annotation directories
    examples = []
    for annotation_dir in annotations_path.iterdir():
        if annotation_dir.is_dir():
            elements_path = annotation_dir / "elements.json"
            if elements_path.exists():
                try:
                    example = create_example_from_annotation(
                        annotation_dir / "annotation.json",
                        elements_path
                    )
                    examples.append(example)
                except Exception as e:
                    print(f"Error processing {annotation_dir}: {e}")

    if examples:
        export_to_jsonl(examples, Path(args.output))
    else:
        print("No valid annotations found.")


def create_example_annotation_structure(base_path: Path):
    """Create example annotation directory structure."""
    example_dir = base_path / "example_001"
    example_dir.mkdir(parents=True, exist_ok=True)

    # Example elements.json
    elements = [
        {"id": "E1", "bounds": [100, 200, 300, 250], "visual_type": "button", "ocr_text": "Login", "confidence": 0.95},
        {"id": "E2", "bounds": [100, 100, 300, 140], "visual_type": "input_field", "ocr_text": "", "confidence": 0.90},
        {"id": "E3", "bounds": [50, 50, 200, 80], "visual_type": "text", "ocr_text": "Welcome", "confidence": 0.98},
    ]

    with open(example_dir / "elements.json", "w") as f:
        json.dump(elements, f, indent=2)

    # Example draft.json (from coarse builder)
    draft = {
        "id": "root",
        "role": "FrameLayout",
        "children": [
            {"id": "E1", "role": "Unknown"},
            {"id": "E2", "role": "Unknown"},
            {"id": "E3", "role": "Unknown"},
        ]
    }

    with open(example_dir / "draft.json", "w") as f:
        json.dump(draft, f, indent=2)

    # Example target.json (human corrected)
    target = {
        "id": "root",
        "role": "FrameLayout",
        "children": [
            {"id": "E3", "role": "TextView"},
            {
                "id": "C1",
                "role": "LinearLayout",
                "children": [
                    {"id": "E2", "role": "EditText", "hint": "Username", "editable": True},
                    {"id": "E1", "role": "Button", "clickable": True},
                ]
            }
        ]
    }

    with open(example_dir / "target.json", "w") as f:
        json.dump(target, f, indent=2)

    print(f"Created example annotation at {example_dir}")
    print("Add a screenshot.png and modify the JSON files for your data.")


if __name__ == "__main__":
    main()
