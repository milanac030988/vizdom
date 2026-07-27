"""Ground truth JSON builder in VizDOM DOM format."""

from typing import List, Dict, Tuple
from .primitives import Element


def build_ground_truth(
    elements: List[Element],
    image_size: Tuple[int, int],
) -> Dict:
    """
    Build ground truth JSON matching VizDOM DOM output format.

    Args:
        elements: List of Element from template generation
        image_size: (width, height)

    Returns:
        Dict matching cv_pipeline_result.json format
    """
    w, h = image_size

    # Build flat element list
    elem_dicts = [e.to_dict() for e in elements]

    # Assign parent-child via spatial containment
    _assign_hierarchy(elements)

    # Update dicts with hierarchy
    for e, d in zip(elements, elem_dicts):
        if e.parent_id:
            d["parent_id"] = e.parent_id
        if e.children_ids:
            d["children_ids"] = e.children_ids

    # Count stats
    text_count = sum(1 for e in elements if e.text)

    return {
        "image_size": {"width": w, "height": h},
        "elements": elem_dicts,
        "stats": {
            "text_detected": text_count,
            "uied_detected": len(elements),
            "final_count": len(elements),
        },
        "source": "synthetic",
    }


def _assign_hierarchy(elements: List[Element]):
    """Assign parent_id/children_ids based on spatial containment."""
    # Sort by area descending (largest = potential parents)
    sorted_elems = sorted(elements, key=lambda e: _area(e.bounds), reverse=True)

    for i, parent in enumerate(sorted_elems):
        for j in range(i + 1, len(sorted_elems)):
            child = sorted_elems[j]
            if child.parent_id:
                continue  # Already has a parent

            if _is_contained(child.bounds, parent.bounds, threshold=0.7):
                child.parent_id = parent.id
                parent.children_ids.append(child.id)


def _area(bounds: List[int]) -> int:
    return (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])


def _is_contained(inner: List[int], outer: List[int], threshold: float = 0.7) -> bool:
    """Check if inner box is mostly contained within outer box."""
    x1 = max(inner[0], outer[0])
    y1 = max(inner[1], outer[1])
    x2 = min(inner[2], outer[2])
    y2 = min(inner[3], outer[3])

    if x2 <= x1 or y2 <= y1:
        return False

    intersection = (x2 - x1) * (y2 - y1)
    inner_area = (inner[2] - inner[0]) * (inner[3] - inner[1])

    if inner_area <= 0:
        return False

    return (intersection / inner_area) >= threshold
