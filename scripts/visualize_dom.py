#!/usr/bin/env python3
"""
Visualize DOM elements on an image.
Draws bounding boxes around detected elements.
"""

import json
import argparse
import cv2
import numpy as np
from pathlib import Path

# Color palette for different element types
TYPE_COLORS = {
    "button": (0, 255, 0),      # Green
    "input_field": (255, 0, 0),  # Blue
    "text": (0, 165, 255),       # Orange
    "checkbox": (255, 0, 255),   # Magenta
    "icon": (255, 255, 0),       # Cyan
    "image": (128, 0, 128),      # Purple
    "container": (128, 128, 128), # Gray
    "unknown": (200, 200, 200),  # Light gray
}


def draw_elements(image, elements, show_ids=True, show_text=True):
    """Draw bounding boxes for all elements."""
    output = image.copy()

    for elem in elements:
        bounds = elem.get("bounds", [0, 0, 0, 0])
        if len(bounds) != 4:
            continue

        x1, y1, x2, y2 = [int(b) for b in bounds]
        vtype = elem.get("visual_type", "unknown")
        elem_id = elem.get("id", "?")
        text = elem.get("text") or elem.get("ocr_text", "")

        # Get color for element type
        color = TYPE_COLORS.get(vtype, TYPE_COLORS["unknown"])

        # Draw rectangle
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)

        # Draw label
        label_parts = []
        if show_ids:
            label_parts.append(elem_id)
        if show_text and text:
            label_parts.append(f'"{text[:15]}"')

        if label_parts:
            label = " ".join(label_parts)
            # Background for text
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(output, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
            cv2.putText(output, label, (x1 + 2, y1 - 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    return output


def extract_elements_from_hierarchy(node, elements_list):
    """Recursively extract elements from hierarchy tree."""
    if node.get("id") and node.get("id") != "ROOT":
        elements_list.append(node)

    for child in node.get("children", []):
        extract_elements_from_hierarchy(child, elements_list)


def main():
    parser = argparse.ArgumentParser(description="Visualize DOM elements on image")
    parser.add_argument("dom_json", help="Path to DOM JSON file")
    default_output = os.path.join(os.path.dirname(__file__), '..', 'output', 'dom_visualized.png')
    parser.add_argument("-o", "--output", help="Output image path",
                       default=default_output)
    parser.add_argument("--no-ids", action="store_true", help="Hide element IDs")
    parser.add_argument("--no-text", action="store_true", help="Hide element text")
    parser.add_argument("--image", help="Override image path from JSON")

    args = parser.parse_args()

    # Load DOM JSON
    with open(args.dom_json, "r", encoding="utf-8") as f:
        dom_data = json.load(f)

    # Get image path
    image_path = args.image or dom_data.get("image_path")
    if not image_path:
        print("Error: No image path found in JSON or provided via --image")
        return 1

    # Handle relative paths
    json_dir = Path(args.dom_json).parent
    if not Path(image_path).is_absolute():
        image_path = json_dir / image_path

    # Load image
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"Error: Could not load image: {image_path}")
        return 1

    print(f"Image loaded: {image.shape[1]}x{image.shape[0]}")

    # Extract elements from hierarchy or raw_elements
    elements = []
    if "dom" in dom_data and "hierarchy" in dom_data["dom"]:
        extract_elements_from_hierarchy(dom_data["dom"]["hierarchy"], elements)
    elif "raw_elements" in dom_data:
        elements = dom_data["raw_elements"]
    else:
        print("Error: No elements found in JSON")
        return 1

    print(f"Elements found: {len(elements)}")

    # Draw visualization
    output = draw_elements(
        image,
        elements,
        show_ids=not args.no_ids,
        show_text=not args.no_text
    )

    # Save output
    cv2.imwrite(args.output, output)
    print(f"Visualization saved to: {args.output}")

    # Print legend
    print("\nColor Legend:")
    for vtype, color in TYPE_COLORS.items():
        bgr = color
        print(f"  {vtype}: RGB({bgr[2]}, {bgr[1]}, {bgr[0]})")

    return 0


if __name__ == "__main__":
    exit(main())
