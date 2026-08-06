"""
Coarse hierarchy builder using rule-based heuristics.

Responsibilities:
- Containment-based parent inference (box-in-box)
- Alignment grouping (rows, columns, list items)
- Label association (nearest text to input/checkbox)

This module builds an initial DOM tree structure from flat CV detections
using spatial relationships. The tree can later be refined by the LLM.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
from enum import Enum

from visual_dom.core.domain.reading_order import order_tree


class GroupType(Enum):
    """Type of element grouping."""
    ROW = "row"
    COLUMN = "column"
    LIST = "list"
    FORM_FIELD = "form_field"
    CONTAINER = "container"


@dataclass
class TreeNode:
    """Node in the visual DOM tree."""
    id: str
    element_id: str  # Reference to source element
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    visual_type: str
    role: Optional[str] = None
    text: Optional[str] = None
    hint: Optional[str] = None
    confidence: float = 0.0
    children: List["TreeNode"] = field(default_factory=list)
    parent_id: Optional[str] = None
    group_type: Optional[GroupType] = None
    associated_label_id: Optional[str] = None
    label: Optional[str] = None  # resolved semantic name (own text or associated label)

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def center(self) -> Tuple[int, int]:
        return (
            (self.bounds[0] + self.bounds[2]) // 2,
            (self.bounds[1] + self.bounds[3]) // 2
        )

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "element_id": self.element_id,
            "bounds": list(self.bounds),
            "visual_type": self.visual_type,
            "confidence": self.confidence,
        }
        if self.role:
            result["role"] = self.role
        if self.text:
            result["text"] = self.text
        if self.hint:
            result["hint"] = self.hint
        if self.parent_id:
            result["parent_id"] = self.parent_id
        if self.group_type:
            result["group_type"] = self.group_type.value
        if self.associated_label_id:
            result["label_id"] = self.associated_label_id
        if self.label:
            result["label"] = self.label
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


class CoarseHierarchyBuilder:
    """
    Build initial DOM hierarchy using spatial rules.

    The builder applies three main strategies:
    1. Containment: Larger elements containing smaller ones become parents
    2. Alignment: Elements aligned horizontally/vertically are grouped
    3. Label association: Text elements near inputs become labels
    """

    def __init__(
        self,
        containment_threshold: float = 0.85,
        alignment_tolerance: int = 15,
        label_max_distance: int = 50,
        min_containment_margin: int = 5
    ):
        """
        Initialize hierarchy builder.

        Args:
            containment_threshold: Fraction of child area that must be inside parent
            alignment_tolerance: Pixel tolerance for alignment grouping
            label_max_distance: Maximum distance for label association
            min_containment_margin: Minimum margin for containment relationship
        """
        self.containment_threshold = containment_threshold
        self.alignment_tolerance = alignment_tolerance
        self.label_max_distance = label_max_distance
        self.min_containment_margin = min_containment_margin

    def build(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build coarse hierarchy from detected elements.

        Args:
            elements: List of detected UI elements with bounds, visual_type, etc.
                      Expected format: {"id", "bounds", "visual_type", "confidence", "ocr_text"?}

        Returns:
            Dictionary with:
            - "root": Root TreeNode as dict
            - "nodes": Flat list of all nodes
            - "label_associations": Dict mapping element_id to label_id
            - "groups": List of detected element groups
        """
        if not elements:
            return {
                "root": None,
                "nodes": [],
                "label_associations": {},
                "groups": []
            }

        # Step 1: Create tree nodes from elements
        nodes = self._create_nodes(elements)
        nodes_by_id = {n.id: n for n in nodes}

        # Step 2: Find containment relationships (parent-child)
        self._build_containment_hierarchy(nodes)

        # Step 3: Associate labels with input elements
        label_associations = self._associate_labels(nodes)

        # Step 3b: Fill in labels from own text where none was associated
        self._assign_own_text_labels(nodes)

        # Step 3c: Propagate resolved labels back onto the source element dicts,
        # so downstream stages (DOM compiler, viewer) surface them. `elements` is
        # the same list the caller passes on to the compiler.
        elem_by_id = {e.get("id"): e for e in elements}
        for n in nodes:
            if n.label and n.element_id in elem_by_id:
                elem_by_id[n.element_id]["label"] = n.label

        # Step 4: Detect alignment groups (rows/columns)
        groups = self._detect_groups(nodes)

        # Step 5: Create root node
        root = self._create_root_node(nodes)

        # Step 5b: Reading-order the tree so siblings read top->bottom/left->right
        # within each parent. order_tree sets nested child lists in place but
        # returns the ordered top-level list, which must be assigned back.
        if root is not None and root.children:
            root.children = order_tree(root.children, get_bounds=lambda n: n.bounds)

        # Step 6: Assign roles based on visual type and context
        self._assign_roles(nodes, label_associations)

        return {
            "root": root.to_dict() if root else None,
            "nodes": [n.to_dict() for n in nodes],
            "label_associations": label_associations,
            "groups": [self._group_to_dict(g) for g in groups]
        }

    def _create_nodes(self, elements: List[Dict[str, Any]]) -> List[TreeNode]:
        """Create TreeNode objects from element dictionaries."""
        nodes = []
        for i, elem in enumerate(elements):
            # Get text from various possible fields
            text = (
                elem.get("ocr_text") or
                elem.get("text") or
                elem.get("content") or
                None
            )

            # Handle both "visual_type" and "type" field names
            visual_type = (
                elem.get("visual_type") or
                elem.get("type") or
                "unknown"
            )

            # Generate ID if not present
            elem_id = elem.get("id") or f"E{i+1}"

            node = TreeNode(
                id=elem_id,
                element_id=elem_id,
                bounds=tuple(elem["bounds"]),
                visual_type=visual_type,
                text=text,
                confidence=elem.get("confidence", 0.0),
            )
            # Seed the semantic label from the detection stage (e.g. an
            # OmniParser icon caption like "Minimize"). Without this the
            # own-text fallback overwrites it with the literal glyph read
            # ("-", "×") and step 3c propagates that back over the caption.
            # Priority stays: associated nearby label > caption > own text.
            existing_label = elem.get("label")
            if existing_label:
                node.label = existing_label
            nodes.append(node)
        return nodes

    def _build_containment_hierarchy(self, nodes: List[TreeNode]) -> None:
        """
        Build parent-child relationships based on containment.

        A node B is a child of node A if:
        - B is geometrically contained within A
        - A is the smallest container that contains B
        """
        # Sort by area (largest first) to process containers before children
        sorted_nodes = sorted(nodes, key=lambda n: n.area, reverse=True)

        for i, child in enumerate(sorted_nodes):
            best_parent = None
            best_parent_area = float('inf')

            for j, parent in enumerate(sorted_nodes):
                if i == j:
                    continue

                # Check if parent can contain child
                if self._is_contained(child, parent):
                    # Find the smallest valid parent
                    if parent.area < best_parent_area:
                        best_parent = parent
                        best_parent_area = parent.area

            if best_parent:
                child.parent_id = best_parent.id
                best_parent.children.append(child)

    def _is_contained(self, child: TreeNode, parent: TreeNode) -> bool:
        """Check if child is contained within parent."""
        # Parent must be larger
        if parent.area <= child.area:
            return False

        # Calculate overlap
        cx1, cy1, cx2, cy2 = child.bounds
        px1, py1, px2, py2 = parent.bounds

        # Check if child bounds are within parent bounds (with margin)
        margin = self.min_containment_margin

        # Child must be inside parent with margin
        if cx1 < px1 + margin or cy1 < py1 + margin:
            return False
        if cx2 > px2 - margin or cy2 > py2 - margin:
            return False

        # Calculate containment ratio
        overlap_x1 = max(cx1, px1)
        overlap_y1 = max(cy1, py1)
        overlap_x2 = min(cx2, px2)
        overlap_y2 = min(cy2, py2)

        if overlap_x1 >= overlap_x2 or overlap_y1 >= overlap_y2:
            return False

        overlap_area = (overlap_x2 - overlap_x1) * (overlap_y2 - overlap_y1)
        containment_ratio = overlap_area / child.area

        return containment_ratio >= self.containment_threshold

    def _associate_labels(self, nodes: List[TreeNode]) -> Dict[str, str]:
        """
        Associate text labels with nearby input elements.

        Rules:
        - Text elements can be labels
        - Input fields, checkboxes, buttons can have labels
        - Labels are typically above or to the left of their targets
        """
        associations = {}

        # Find text elements (potential labels)
        text_nodes = [n for n in nodes if n.visual_type == "text" and n.text]

        # Find elements that can have labels
        labelable_types = {"input_field", "checkbox", "button", "unknown"}
        labelable_nodes = [n for n in nodes if n.visual_type in labelable_types]

        for labelable in labelable_nodes:
            best_label = None
            best_distance = float('inf')
            best_position = None

            for text_node in text_nodes:
                # Skip if already used as a label
                if text_node.id in associations.values():
                    continue

                distance, position = self._label_distance(text_node, labelable)

                if distance < self.label_max_distance and distance < best_distance:
                    best_label = text_node
                    best_distance = distance
                    best_position = position

            if best_label:
                associations[labelable.id] = best_label.id
                labelable.associated_label_id = best_label.id

                # Set hint + resolved label from a label positioned above/left
                # (the conventional label position for a control).
                if best_position in ("above", "left"):
                    labelable.hint = best_label.text
                    labelable.label = best_label.text

        return associations

    def _assign_own_text_labels(self, nodes: List[TreeNode]) -> None:
        """
        Give elements a `label` from their own text when no nearby label was
        associated. A button reading "OK" is labelled "OK"; a text node is its
        own label. Association (label to the left/above) already set `label` for
        controls without intrinsic text, so we only fill the gaps here.
        """
        for node in nodes:
            if node.label:
                continue
            if node.text and node.text.strip():
                node.label = node.text.strip()

    def _label_distance(
        self,
        label: TreeNode,
        target: TreeNode
    ) -> Tuple[float, str]:
        """
        Calculate distance and relative position of label to target.

        Returns:
            Tuple of (distance, position) where position is "above", "left", "right", "below"
        """
        lx1, ly1, lx2, ly2 = label.bounds
        tx1, ty1, tx2, ty2 = target.bounds

        label_center = label.center
        target_center = target.center

        # Check relative position
        # Label above target
        if ly2 <= ty1 and self._horizontal_overlap(label.bounds, target.bounds):
            distance = ty1 - ly2
            return (distance, "above")

        # Label left of target
        if lx2 <= tx1 and self._vertical_overlap(label.bounds, target.bounds):
            distance = tx1 - lx2
            return (distance, "left")

        # Label right of target (less common)
        if lx1 >= tx2 and self._vertical_overlap(label.bounds, target.bounds):
            distance = lx1 - tx2
            return (distance, "right")

        # Label below target (uncommon)
        if ly1 >= ty2 and self._horizontal_overlap(label.bounds, target.bounds):
            distance = ly1 - ty2
            return (distance, "below")

        # Fallback: Euclidean distance between centers
        dx = label_center[0] - target_center[0]
        dy = label_center[1] - target_center[1]
        distance = (dx * dx + dy * dy) ** 0.5
        return (distance, "other")

    def _horizontal_overlap(
        self,
        bounds1: Tuple[int, int, int, int],
        bounds2: Tuple[int, int, int, int]
    ) -> bool:
        """Check if two bounds have horizontal overlap."""
        x1_start, _, x1_end, _ = bounds1
        x2_start, _, x2_end, _ = bounds2
        return not (x1_end < x2_start or x2_end < x1_start)

    def _vertical_overlap(
        self,
        bounds1: Tuple[int, int, int, int],
        bounds2: Tuple[int, int, int, int]
    ) -> bool:
        """Check if two bounds have vertical overlap."""
        _, y1_start, _, y1_end = bounds1
        _, y2_start, _, y2_end = bounds2
        return not (y1_end < y2_start or y2_end < y1_start)

    def _detect_groups(self, nodes: List[TreeNode]) -> List[Dict[str, Any]]:
        """
        Detect element groups based on alignment.

        Looks for:
        - Horizontal rows (elements with similar y-coordinates)
        - Vertical columns (elements with similar x-coordinates)
        - List items (repeated similar elements)
        """
        groups = []

        # Only group leaf nodes (no children) at the same hierarchy level
        leaf_nodes = [n for n in nodes if not n.children]

        # Group by parent
        by_parent: Dict[Optional[str], List[TreeNode]] = {}
        for node in leaf_nodes:
            parent_id = node.parent_id
            if parent_id not in by_parent:
                by_parent[parent_id] = []
            by_parent[parent_id].append(node)

        for parent_id, siblings in by_parent.items():
            if len(siblings) < 2:
                continue

            # Detect horizontal rows
            rows = self._find_horizontal_groups(siblings)
            for row in rows:
                if len(row) >= 2:
                    groups.append({
                        "type": GroupType.ROW,
                        "parent_id": parent_id,
                        "members": [n.id for n in row]
                    })

            # Detect vertical columns
            columns = self._find_vertical_groups(siblings)
            for col in columns:
                if len(col) >= 2:
                    groups.append({
                        "type": GroupType.COLUMN,
                        "parent_id": parent_id,
                        "members": [n.id for n in col]
                    })

        return groups

    def _find_horizontal_groups(
        self,
        nodes: List[TreeNode]
    ) -> List[List[TreeNode]]:
        """Find groups of horizontally aligned elements (same row)."""
        if not nodes:
            return []

        # Sort by y-center
        sorted_nodes = sorted(nodes, key=lambda n: n.center[1])

        groups = []
        current_group = [sorted_nodes[0]]

        for node in sorted_nodes[1:]:
            last_y = current_group[-1].center[1]
            if abs(node.center[1] - last_y) <= self.alignment_tolerance:
                current_group.append(node)
            else:
                if len(current_group) >= 2:
                    # Sort by x within row
                    current_group.sort(key=lambda n: n.center[0])
                    groups.append(current_group)
                current_group = [node]

        if len(current_group) >= 2:
            current_group.sort(key=lambda n: n.center[0])
            groups.append(current_group)

        return groups

    def _find_vertical_groups(
        self,
        nodes: List[TreeNode]
    ) -> List[List[TreeNode]]:
        """Find groups of vertically aligned elements (same column)."""
        if not nodes:
            return []

        # Sort by x-center
        sorted_nodes = sorted(nodes, key=lambda n: n.center[0])

        groups = []
        current_group = [sorted_nodes[0]]

        for node in sorted_nodes[1:]:
            last_x = current_group[-1].center[0]
            if abs(node.center[0] - last_x) <= self.alignment_tolerance:
                current_group.append(node)
            else:
                if len(current_group) >= 2:
                    # Sort by y within column
                    current_group.sort(key=lambda n: n.center[1])
                    groups.append(current_group)
                current_group = [node]

        if len(current_group) >= 2:
            current_group.sort(key=lambda n: n.center[1])
            groups.append(current_group)

        return groups

    def _create_root_node(self, nodes: List[TreeNode]) -> Optional[TreeNode]:
        """Create or identify the root node of the hierarchy."""
        # Find nodes without parents (top-level nodes)
        root_nodes = [n for n in nodes if n.parent_id is None]

        if not root_nodes:
            return None

        if len(root_nodes) == 1:
            return root_nodes[0]

        # Multiple top-level nodes: create synthetic root
        # Find bounding box of all elements
        all_bounds = [n.bounds for n in nodes]
        x1 = min(b[0] for b in all_bounds)
        y1 = min(b[1] for b in all_bounds)
        x2 = max(b[2] for b in all_bounds)
        y2 = max(b[3] for b in all_bounds)

        root = TreeNode(
            id="ROOT",
            element_id="ROOT",
            bounds=(x1, y1, x2, y2),
            visual_type="container",
            role="root",
            children=root_nodes
        )

        for node in root_nodes:
            node.parent_id = "ROOT"

        return root

    def _assign_roles(
        self,
        nodes: List[TreeNode],
        label_associations: Dict[str, str]
    ) -> None:
        """Assign semantic roles based on visual type and context."""
        role_mapping = {
            "button": "Button",
            "input_field": "EditText",
            "checkbox": "CheckBox",
            "icon": "ImageView",
            "text": "TextView",
            "container": "ViewGroup",
            "block": "ViewGroup",
            "image": "ImageView",
        }

        for node in nodes:
            # Default role from visual type
            node.role = role_mapping.get(node.visual_type, "View")

            # Refine based on context
            if node.visual_type == "input_field":
                if node.associated_label_id:
                    # Get label text for hint
                    label_node = next(
                        (n for n in nodes if n.id == node.associated_label_id),
                        None
                    )
                    if label_node and label_node.text:
                        node.hint = label_node.text

            elif node.visual_type == "text":
                # Check if this is a button label
                if node.text and any(
                    kw in node.text.lower()
                    for kw in ["login", "sign", "submit", "cancel", "ok", "next", "back"]
                ):
                    node.role = "Button"

    def _group_to_dict(self, group: Dict[str, Any]) -> Dict[str, Any]:
        """Convert group to serializable dictionary."""
        return {
            "type": group["type"].value,
            "parent_id": group["parent_id"],
            "members": group["members"]
        }


def build_hierarchy(elements: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    Convenience function to build hierarchy from elements.

    Args:
        elements: List of detected elements
        **kwargs: Arguments for CoarseHierarchyBuilder

    Returns:
        Hierarchy dictionary
    """
    builder = CoarseHierarchyBuilder(**kwargs)
    return builder.build(elements)
