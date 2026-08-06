"""
DOM Compiler - produces final UIAutomator-like JSON.

Responsibilities:
- Apply LLM tree edits
- Validate structure integrity
- Inject bounds from CV evidence
- Export automation-friendly JSON
- Generate locators for Robot Framework
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


# Map visual_type to accessibility roles
ROLE_MAPPING = {
    "button": "button",
    "text": "staticText",
    "input_field": "textField",
    "checkbox": "checkBox",
    "icon": "image",
    "image": "image",
    "container": "group",
    "block": "group",
    "divider": "separator",
    "unknown": "generic",
}


@dataclass
class DOMNode:
    """Final DOM node with all attributes."""
    id: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    role: str
    visual_type: str = "unknown"
    text: Optional[str] = None
    hint: Optional[str] = None
    label: Optional[str] = None  # semantic name (own text or associated label)
    clickable: bool = False
    editable: bool = False
    scrollable: bool = False
    confidence: float = 1.0
    locators: Dict[str, str] = field(default_factory=dict)
    children: List["DOMNode"] = field(default_factory=list)

    @property
    def center(self) -> Tuple[int, int]:
        """Get center coordinates."""
        return (
            (self.bounds[0] + self.bounds[2]) // 2,
            (self.bounds[1] + self.bounds[3]) // 2
        )

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "id": self.id,
            "bounds": list(self.bounds),
            "center": list(self.center),
            "role": self.role,
            "visual_type": self.visual_type,
            "clickable": self.clickable,
            "editable": self.editable,
            "scrollable": self.scrollable,
            "confidence": self.confidence,
        }
        if self.text:
            result["text"] = self.text
        if self.hint:
            result["hint"] = self.hint
        if self.label:
            result["label"] = self.label
        if self.locators:
            result["locators"] = self.locators
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


class DOMCompiler:
    """
    Compile detected elements and tree edits into final DOM JSON.

    Output format is similar to UIAutomator but with visual detection metadata.
    """

    def __init__(self, generate_locators: bool = True):
        """
        Initialize compiler.

        Args:
            generate_locators: Whether to generate locator strategies
        """
        self.generate_locators = generate_locators
        self.elements_map: Dict[str, Any] = {}
        self.nodes_map: Dict[str, DOMNode] = {}
        self.dom_result: Optional[Dict] = None

    def compile(
        self,
        elements: List[Dict],
        hierarchy: Dict = None,
        image_size: Tuple[int, int] = None,
    ) -> Dict[str, Any]:
        """
        Compile final DOM from elements.

        Args:
            elements: Detected elements with bounds from CV/LLM
            hierarchy: Hierarchy tree from coarse builder (optional)
            image_size: (width, height) of source image

        Returns:
            Final DOM JSON with metadata and flat element list
        """
        # Build element lookup
        self.elements_map = {e["id"]: e for e in elements}

        # Convert elements to DOMNodes
        dom_nodes = []
        for elem in elements:
            node = self._create_dom_node(elem)
            dom_nodes.append(node)
            self.nodes_map[node.id] = node

        # Build hierarchy if provided
        if hierarchy:
            root_node = self._build_hierarchy_tree(hierarchy)
        else:
            # Flat structure with synthetic root
            root_node = DOMNode(
                id="root",
                bounds=(0, 0, image_size[0] if image_size else 1920, image_size[1] if image_size else 1080),
                role="window",
                visual_type="root",
                children=dom_nodes
            )

        # Generate locators
        if self.generate_locators:
            self._generate_locators(dom_nodes)

        # Build result
        self.dom_result = {
            "version": "1.0",
            "image_size": list(image_size) if image_size else None,
            "element_count": len(elements),
            "hierarchy": root_node.to_dict(),
            "elements": [n.to_dict() for n in dom_nodes],
        }

        return self.dom_result

    def _create_dom_node(self, elem: Dict) -> DOMNode:
        """Create DOMNode from element dict."""
        visual_type = elem.get("visual_type", "unknown")
        role = elem.get("role", ROLE_MAPPING.get(visual_type, "generic"))

        # Determine interaction flags from type
        clickable = visual_type in ("button", "checkbox", "icon")
        editable = visual_type == "input_field"

        bounds = tuple(elem.get("bounds", [0, 0, 0, 0]))

        return DOMNode(
            id=elem.get("id", ""),
            bounds=bounds,
            role=role,
            visual_type=visual_type,
            text=elem.get("ocr_text") or elem.get("text"),
            hint=elem.get("hint"),
            label=elem.get("label"),
            clickable=clickable,
            editable=editable,
            confidence=elem.get("confidence", 1.0),
        )

    def _build_hierarchy_tree(self, hierarchy: Dict) -> DOMNode:
        """Build DOM tree from hierarchy dict."""
        if hierarchy is None:
            return None

        # Find or create node
        node_id = hierarchy.get("id", "root")
        if node_id in self.nodes_map:
            node = self.nodes_map[node_id]
        else:
            # Create from hierarchy data
            node = DOMNode(
                id=node_id,
                bounds=tuple(hierarchy.get("bounds", [0, 0, 0, 0])),
                role=hierarchy.get("role", "group"),
                visual_type=hierarchy.get("visual_type", "unknown"),
                text=hierarchy.get("text"),
            )
            self.nodes_map[node_id] = node

        # Recursively build children
        children = hierarchy.get("children", [])
        for child_data in children:
            child_node = self._build_hierarchy_tree(child_data)
            if child_node:
                node.children.append(child_node)

        return node

    def _generate_locators(self, nodes: List[DOMNode]) -> None:
        """Generate locator strategies for each node."""
        text_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}

        # Count duplicates for index-based locators
        for node in nodes:
            if node.text:
                text_counts[node.text] = text_counts.get(node.text, 0) + 1
            type_counts[node.visual_type] = type_counts.get(node.visual_type, 0) + 1

        # Track indices for duplicate handling
        text_indices: Dict[str, int] = {}
        type_indices: Dict[str, int] = {}

        for node in nodes:
            locators = {}

            # ID locator (always unique)
            locators["id"] = node.id

            # Text locator (if has text)
            if node.text:
                if text_counts[node.text] == 1:
                    locators["text"] = node.text
                else:
                    idx = text_indices.get(node.text, 0)
                    locators["text"] = f"{node.text}[{idx}]"
                    text_indices[node.text] = idx + 1

            # Type + index locator
            type_key = node.visual_type
            idx = type_indices.get(type_key, 0)
            locators["type_index"] = f"{type_key}[{idx}]"
            type_indices[type_key] = idx + 1

            # Bounds locator (always works)
            locators["bounds"] = f"bounds({node.bounds[0]},{node.bounds[1]},{node.bounds[2]},{node.bounds[3]})"

            # Center coordinate locator
            cx, cy = node.center
            locators["center"] = f"point({cx},{cy})"

            node.locators = locators

    def get_element_by_text(self, text: str) -> Optional[DOMNode]:
        """Find element by text content."""
        for node in self.nodes_map.values():
            if node.text == text:
                return node
        return None

    def get_elements_by_type(self, visual_type: str) -> List[DOMNode]:
        """Find all elements of given type."""
        return [n for n in self.nodes_map.values() if n.visual_type == visual_type]

    def get_clickable_elements(self) -> List[DOMNode]:
        """Get all clickable elements."""
        return [n for n in self.nodes_map.values() if n.clickable]

    def to_json(self, indent: int = 2) -> str:
        """Export DOM as JSON string."""
        if self.dom_result is None:
            raise ValueError("No DOM compiled yet. Call compile() first.")
        return json.dumps(self.dom_result, indent=indent, ensure_ascii=False)

    def save(self, path: str, indent: int = 2) -> None:
        """Save DOM to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent))


def compile_dom(
    elements: List[Dict],
    hierarchy: Dict = None,
    image_size: Tuple[int, int] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to compile DOM.

    Args:
        elements: Detected elements from CV/LLM pipeline
        hierarchy: Hierarchy tree (optional)
        image_size: Source image dimensions
        **kwargs: Additional args for DOMCompiler

    Returns:
        Compiled DOM dictionary
    """
    compiler = DOMCompiler(**kwargs)
    return compiler.compile(elements, hierarchy, image_size)
