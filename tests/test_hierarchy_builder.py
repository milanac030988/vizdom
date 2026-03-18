"""
Test the Coarse Hierarchy Builder.

Usage:
    python tests/test_hierarchy_builder.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from visual_dom.hierarchy import CoarseHierarchyBuilder, build_hierarchy


def test_with_sample_data():
    """Test hierarchy builder with sample pipeline output."""
    print("=" * 60)
    print("TEST: Coarse Hierarchy Builder (Ground Truth Data)")
    print("=" * 60)

    # Load ground truth which has text
    samples_dir = project_root / "tests" / "samples"
    result_path = samples_dir / "login_screen_gt.json"

    if not result_path.exists():
        print(f"\nSample data not found: {result_path}")
        print("Run generate_test_ui.py first to generate test data.")
        return None

    with open(result_path) as f:
        gt_data = json.load(f)

    elements = gt_data["elements"]
    print(f"\nInput: {len(elements)} elements from ground truth (with text)")

    # Show elements with text
    print("\nElements with text:")
    for elem in elements:
        text = elem.get("text", "")
        if text:
            etype = elem.get("type") or elem.get("visual_type", "unknown")
            print(f"  {etype}: \"{text}\"")

    # Build hierarchy
    builder = CoarseHierarchyBuilder(
        containment_threshold=0.85,
        alignment_tolerance=15,
        label_max_distance=50
    )

    hierarchy = builder.build(elements)

    # Print results
    print(f"\n{'='*60}")
    print("HIERARCHY RESULTS")
    print("=" * 60)

    print(f"\nRoot node: {hierarchy['root']['id'] if hierarchy['root'] else 'None'}")
    print(f"Total nodes: {len(hierarchy['nodes'])}")
    print(f"Label associations: {len(hierarchy['label_associations'])}")
    print(f"Detected groups: {len(hierarchy['groups'])}")

    # Print tree structure
    print(f"\n{'='*60}")
    print("TREE STRUCTURE")
    print("=" * 60)

    if hierarchy['root']:
        print_tree(hierarchy['root'], indent=0)

    # Print label associations
    if hierarchy['label_associations']:
        print(f"\n{'='*60}")
        print("LABEL ASSOCIATIONS")
        print("=" * 60)
        for elem_id, label_id in hierarchy['label_associations'].items():
            elem = next((n for n in hierarchy['nodes'] if n['id'] == elem_id), None)
            label = next((n for n in hierarchy['nodes'] if n['id'] == label_id), None)
            if elem and label:
                print(f"  {elem_id} ({elem['visual_type']}) <- {label_id}: \"{label.get('text', '')}\"")

    # Print groups
    if hierarchy['groups']:
        print(f"\n{'='*60}")
        print("ALIGNMENT GROUPS")
        print("=" * 60)
        for group in hierarchy['groups']:
            print(f"  {group['type']}: {group['members']}")

    # Save hierarchy result
    output_path = samples_dir / "login_hierarchy_result.json"
    with open(output_path, "w") as f:
        json.dump(hierarchy, f, indent=2)
    print(f"\nHierarchy saved to: {output_path}")

    return hierarchy


def print_tree(node, indent=0):
    """Print tree structure recursively."""
    prefix = "  " * indent
    role = node.get('role', '')
    text = node.get('text', '')[:30] if node.get('text') else ''
    hint = node.get('hint', '')[:20] if node.get('hint') else ''
    conf = node.get('confidence', 0)

    info = f"{node['id']}: {node['visual_type']}"
    if role:
        info += f" [{role}]"
    if text:
        info += f" text=\"{text}\""
    if hint:
        info += f" hint=\"{hint}\""
    if conf > 0:
        info += f" ({conf:.2f})"

    print(f"{prefix}{info}")

    for child in node.get('children', []):
        print_tree(child, indent + 1)


def test_with_synthetic_data():
    """Test with manually created synthetic data."""
    print("\n" + "=" * 60)
    print("TEST: Synthetic Data")
    print("=" * 60)

    # Create synthetic elements representing a form
    elements = [
        # Container (card)
        {"id": "C1", "bounds": [50, 50, 350, 400], "visual_type": "block", "confidence": 0.8},

        # Email label and input
        {"id": "T1", "bounds": [70, 80, 120, 100], "visual_type": "text", "ocr_text": "Email", "confidence": 0.9},
        {"id": "I1", "bounds": [70, 110, 330, 150], "visual_type": "input_field", "confidence": 0.8},

        # Password label and input
        {"id": "T2", "bounds": [70, 170, 140, 190], "visual_type": "text", "ocr_text": "Password", "confidence": 0.9},
        {"id": "I2", "bounds": [70, 200, 330, 240], "visual_type": "input_field", "confidence": 0.8},

        # Checkbox with label
        {"id": "CB1", "bounds": [70, 270, 90, 290], "visual_type": "checkbox", "confidence": 0.7},
        {"id": "T3", "bounds": [100, 272, 200, 288], "visual_type": "text", "ocr_text": "Remember me", "confidence": 0.9},

        # Submit button
        {"id": "B1", "bounds": [70, 320, 330, 370], "visual_type": "button", "ocr_text": "Sign In", "confidence": 0.8},
    ]

    hierarchy = build_hierarchy(elements)

    print(f"\nInput: {len(elements)} elements")
    print(f"Label associations: {len(hierarchy['label_associations'])}")

    print("\nExpected associations:")
    print("  I1 (input_field) <- T1 (Email)")
    print("  I2 (input_field) <- T2 (Password)")
    print("  CB1 (checkbox) <- T3 (Remember me)")

    print("\nActual associations:")
    for elem_id, label_id in hierarchy['label_associations'].items():
        elem = next((n for n in hierarchy['nodes'] if n['id'] == elem_id), None)
        label = next((n for n in hierarchy['nodes'] if n['id'] == label_id), None)
        if elem and label:
            print(f"  {elem_id} ({elem['visual_type']}) <- {label_id}: \"{label.get('text', '')}\"")

    print("\nTree structure:")
    if hierarchy['root']:
        print_tree(hierarchy['root'], indent=0)

    # Verify containment
    nodes_with_parent = [n for n in hierarchy['nodes'] if n.get('parent_id')]
    print(f"\nNodes with parents: {len(nodes_with_parent)}/{len(hierarchy['nodes'])}")

    return hierarchy


def test_alignment_grouping():
    """Test alignment detection with a grid of elements."""
    print("\n" + "=" * 60)
    print("TEST: Alignment Grouping")
    print("=" * 60)

    # Create a grid of buttons (3x2)
    elements = [
        # Row 1
        {"id": "B1", "bounds": [50, 50, 120, 80], "visual_type": "button", "ocr_text": "Btn 1", "confidence": 0.8},
        {"id": "B2", "bounds": [140, 50, 210, 80], "visual_type": "button", "ocr_text": "Btn 2", "confidence": 0.8},
        {"id": "B3", "bounds": [230, 50, 300, 80], "visual_type": "button", "ocr_text": "Btn 3", "confidence": 0.8},

        # Row 2
        {"id": "B4", "bounds": [50, 100, 120, 130], "visual_type": "button", "ocr_text": "Btn 4", "confidence": 0.8},
        {"id": "B5", "bounds": [140, 100, 210, 130], "visual_type": "button", "ocr_text": "Btn 5", "confidence": 0.8},
        {"id": "B6", "bounds": [230, 100, 300, 130], "visual_type": "button", "ocr_text": "Btn 6", "confidence": 0.8},
    ]

    hierarchy = build_hierarchy(elements)

    print(f"\nInput: {len(elements)} buttons in 3x2 grid")
    print(f"Detected groups: {len(hierarchy['groups'])}")

    print("\nExpected groups:")
    print("  Row 1: B1, B2, B3")
    print("  Row 2: B4, B5, B6")
    print("  Column 1: B1, B4")
    print("  Column 2: B2, B5")
    print("  Column 3: B3, B6")

    print("\nActual groups:")
    for group in hierarchy['groups']:
        print(f"  {group['type']}: {group['members']}")

    return hierarchy


def main():
    """Run all tests."""
    # Test with synthetic data first (no dependencies)
    test_with_synthetic_data()
    test_alignment_grouping()

    # Test with real pipeline output
    test_with_sample_data()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
