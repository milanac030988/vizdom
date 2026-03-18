"""
DOM Tree data structures for Visual DOM Viewer.

Provides the core tree structure for representing UI elements
with support for hierarchy, bounding boxes, and properties.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
import json


class ElementType(Enum):
    """Standard UI element types."""
    UNKNOWN = "unknown"
    BUTTON = "button"
    INPUT_FIELD = "input_field"
    TEXT = "text"
    LABEL = "label"
    ICON = "icon"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    LIST = "list"
    LIST_ITEM = "list_item"
    CONTAINER = "container"
    IMAGE = "image"
    LINK = "link"
    MENU = "menu"
    MENU_ITEM = "menu_item"
    TAB = "tab"
    WINDOW = "window"
    DIALOG = "dialog"
    TOOLBAR = "toolbar"
    SCROLLBAR = "scrollbar"


@dataclass
class BoundingBox:
    """Bounding box for UI element."""
    x: int
    y: int
    width: int
    height: int

    @property
    def x1(self) -> int:
        return self.x

    @property
    def y1(self) -> int:
        return self.y

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple:
        """Return center point of bounding box."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains_point(self, px: int, py: int) -> bool:
        """Check if point is inside bounding box."""
        return (self.x <= px <= self.x2) and (self.y <= py <= self.y2)

    def contains_box(self, other: 'BoundingBox') -> bool:
        """Check if this box contains another box."""
        return (self.x <= other.x and self.y <= other.y and
                self.x2 >= other.x2 and self.y2 >= other.y2)

    def intersects(self, other: 'BoundingBox') -> bool:
        """Check if this box intersects with another box."""
        return not (self.x2 < other.x or other.x2 < self.x or
                    self.y2 < other.y or other.y2 < self.y)

    def area(self) -> int:
        """Return area of bounding box."""
        return self.width * self.height

    def to_list(self) -> List[int]:
        """Convert to [x, y, width, height] list."""
        return [self.x, self.y, self.width, self.height]

    def to_xyxy(self) -> List[int]:
        """Convert to [x1, y1, x2, y2] list."""
        return [self.x, self.y, self.x2, self.y2]

    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> 'BoundingBox':
        """Create from [x1, y1, x2, y2] coordinates."""
        return cls(x=x1, y=y1, width=x2-x1, height=y2-y1)

    @classmethod
    def from_list(cls, bbox: List[int]) -> 'BoundingBox':
        """Create from [x, y, width, height] or [x1, y1, x2, y2] list."""
        if len(bbox) != 4:
            raise ValueError("Bounding box must have 4 elements")
        # Detect format: if width/height seem like coordinates (larger than typical)
        if bbox[2] > bbox[0] and bbox[3] > bbox[1]:
            # Likely [x1, y1, x2, y2] format
            return cls.from_xyxy(*bbox)
        return cls(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])


@dataclass
class DOMElement:
    """
    Represents a single UI element in the DOM tree.

    Attributes:
        id: Unique identifier for the element
        type: Element type (button, input, text, etc.)
        bbox: Bounding box coordinates
        text: Text content of the element
        properties: Additional properties/attributes
        parent: Parent element reference
        children: List of child elements
        confidence: Detection confidence score
        selected: Whether element is selected for export
    """
    id: str
    type: ElementType = ElementType.UNKNOWN
    bbox: Optional[BoundingBox] = None
    text: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    parent: Optional['DOMElement'] = None
    children: List['DOMElement'] = field(default_factory=list)
    confidence: float = 1.0
    selected: bool = False

    # Properties to track for export
    _export_properties: Dict[str, bool] = field(default_factory=lambda: {
        'id': True,
        'type': True,
        'bbox': True,
        'text': True,
    })

    def add_child(self, child: 'DOMElement') -> None:
        """Add a child element."""
        child.parent = self
        self.children.append(child)

    def remove_child(self, child: 'DOMElement') -> None:
        """Remove a child element."""
        if child in self.children:
            child.parent = None
            self.children.remove(child)

    def find_by_id(self, element_id: str) -> Optional['DOMElement']:
        """Find element by ID in subtree."""
        if self.id == element_id:
            return self
        for child in self.children:
            result = child.find_by_id(element_id)
            if result:
                return result
        return None

    def find_by_point(self, px: int, py: int) -> Optional['DOMElement']:
        """
        Find the leaf-most element containing the given point.
        Returns the smallest element that contains the point.
        """
        if self.bbox is None or not self.bbox.contains_point(px, py):
            return None

        # Check children first (they are more specific)
        smallest = None
        smallest_area = float('inf')

        for child in self.children:
            result = child.find_by_point(px, py)
            if result and result.bbox:
                area = result.bbox.area()
                if area < smallest_area:
                    smallest = result
                    smallest_area = area

        # If no child contains the point, return self
        if smallest is None:
            return self

        return smallest

    def find_all_at_point(self, px: int, py: int) -> List['DOMElement']:
        """Find all elements containing the given point."""
        results = []
        if self.bbox and self.bbox.contains_point(px, py):
            results.append(self)
        for child in self.children:
            results.extend(child.find_all_at_point(px, py))
        return results

    def get_ancestors(self) -> List['DOMElement']:
        """Get all ancestors from root to parent."""
        ancestors = []
        current = self.parent
        while current:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors

    def get_path(self) -> str:
        """Get XPath-like path to this element."""
        if self.parent is None:
            return f"/{self.type.value}[@id='{self.id}']"
        return f"{self.parent.get_path()}/{self.type.value}[@id='{self.id}']"

    def get_depth(self) -> int:
        """Get depth in tree (root = 0)."""
        depth = 0
        current = self.parent
        while current:
            depth += 1
            current = current.parent
        return depth

    def traverse(self, callback: Callable[['DOMElement', int], None], depth: int = 0) -> None:
        """Traverse tree in pre-order, calling callback for each element."""
        callback(self, depth)
        for child in self.children:
            child.traverse(callback, depth + 1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert element to dictionary."""
        return {
            'id': self.id,
            'type': self.type.value,
            'bbox': self.bbox.to_list() if self.bbox else None,
            'text': self.text,
            'properties': self.properties,
            'confidence': self.confidence,
            'children': [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent: Optional['DOMElement'] = None) -> 'DOMElement':
        """Create element from dictionary."""
        element = cls(
            id=data.get('id', ''),
            type=ElementType(data.get('type', 'unknown')),
            bbox=BoundingBox.from_list(data['bbox']) if data.get('bbox') else None,
            text=data.get('text', ''),
            properties=data.get('properties', {}),
            confidence=data.get('confidence', 1.0),
            parent=parent,
        )
        for child_data in data.get('children', []):
            child = cls.from_dict(child_data, parent=element)
            element.children.append(child)
        return element

    def to_robot_locator(self) -> str:
        """Generate Robot Framework locator string."""
        locators = []

        # Prefer text-based locator
        if self.text:
            locators.append(f"text={self.text}")

        # Add type-based locator
        locators.append(f"type={self.type.value}")

        # Add ID if available
        if self.id:
            locators.append(f"id={self.id}")

        return " | ".join(locators)

    def __repr__(self) -> str:
        return f"DOMElement(id='{self.id}', type={self.type.value}, text='{self.text[:20]}...')"


class DOMTree:
    """
    Complete DOM tree structure representing a screen/window.

    Attributes:
        root: Root element of the tree
        screen_width: Width of the screen/screenshot
        screen_height: Height of the screen/screenshot
        title: Title of the screen/window
        source: Source platform (windows, android, linux, web)
        metadata: Additional metadata
    """

    def __init__(
        self,
        screen_width: int = 0,
        screen_height: int = 0,
        title: str = "",
        source: str = "unknown"
    ):
        self.root: Optional[DOMElement] = None
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.title = title
        self.source = source
        self.metadata: Dict[str, Any] = {}
        self._element_index: Dict[str, DOMElement] = {}

    def set_root(self, element: DOMElement) -> None:
        """Set the root element and build index."""
        self.root = element
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the element index for fast lookup."""
        self._element_index.clear()
        if self.root:
            self.root.traverse(lambda e, d: self._element_index.update({e.id: e}))

    def get_element_by_id(self, element_id: str) -> Optional[DOMElement]:
        """Get element by ID using index."""
        return self._element_index.get(element_id)

    def find_element_at_point(self, px: int, py: int) -> Optional[DOMElement]:
        """Find the leaf-most element at given point."""
        if self.root:
            return self.root.find_by_point(px, py)
        return None

    def find_all_elements_at_point(self, px: int, py: int) -> List[DOMElement]:
        """Find all elements containing the given point."""
        if self.root:
            return self.root.find_all_at_point(px, py)
        return []

    def find_elements_by_type(self, element_type: ElementType) -> List[DOMElement]:
        """Find all elements of a specific type."""
        results = []
        if self.root:
            self.root.traverse(
                lambda e, d: results.append(e) if e.type == element_type else None
            )
        return results

    def find_elements_by_text(self, text: str, partial: bool = True) -> List[DOMElement]:
        """Find elements containing the given text."""
        results = []
        if self.root:
            def check_text(e, d):
                if partial and text.lower() in e.text.lower():
                    results.append(e)
                elif not partial and text.lower() == e.text.lower():
                    results.append(e)
            self.root.traverse(check_text)
        return results

    def get_all_elements(self) -> List[DOMElement]:
        """Get flat list of all elements."""
        return list(self._element_index.values())

    def get_element_count(self) -> int:
        """Get total number of elements."""
        return len(self._element_index)

    def to_dict(self) -> Dict[str, Any]:
        """Convert tree to dictionary."""
        return {
            'screen': {
                'width': self.screen_width,
                'height': self.screen_height,
                'title': self.title,
                'source': self.source,
            },
            'metadata': self.metadata,
            'elements': self.root.to_dict() if self.root else None,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert tree to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DOMTree':
        """Create tree from dictionary. Supports multiple formats."""

        # Format 1: Visual DOM Generator format (from CV pipeline)
        if 'dom' in data and 'hierarchy' in data.get('dom', {}):
            return cls._from_visual_dom_format(data)

        # Format 2: Standard format
        screen = data.get('screen', {})
        tree = cls(
            screen_width=screen.get('width', 0),
            screen_height=screen.get('height', 0),
            title=screen.get('title', ''),
            source=screen.get('source', 'unknown'),
        )
        tree.metadata = data.get('metadata', {})
        if data.get('elements'):
            tree.set_root(DOMElement.from_dict(data['elements']))
        return tree

    @classmethod
    def _from_visual_dom_format(cls, data: Dict[str, Any]) -> 'DOMTree':
        """Parse Visual DOM Generator format (from CV pipeline)."""
        # Get image size
        image_size = data.get('image_size', {})
        if isinstance(image_size, dict):
            width = image_size.get('width', 0)
            height = image_size.get('height', 0)
        elif isinstance(image_size, list) and len(image_size) >= 2:
            width, height = image_size[0], image_size[1]
        else:
            dom_data = data.get('dom', {})
            dom_size = dom_data.get('image_size', [0, 0])
            width, height = dom_size[0], dom_size[1]

        tree = cls(
            screen_width=width,
            screen_height=height,
            title=data.get('image_path', ''),
            source='visual_dom'
        )

        # Store metadata
        tree.metadata = {
            'image_path': data.get('image_path', ''),
            'cv_stats': data.get('cv_stats', {}),
        }

        # Parse hierarchy
        dom_data = data.get('dom', {})
        hierarchy = dom_data.get('hierarchy')
        if hierarchy:
            root = cls._parse_visual_dom_element(hierarchy)
            tree.set_root(root)

        return tree

    @classmethod
    def _parse_visual_dom_element(cls, elem_data: Dict[str, Any], parent: 'DOMElement' = None) -> 'DOMElement':
        """Parse element from Visual DOM format."""
        # Map role/visual_type to ElementType
        role = elem_data.get('role', 'unknown')
        visual_type = elem_data.get('visual_type', '')

        type_mapping = {
            'button': ElementType.BUTTON,
            'input': ElementType.INPUT_FIELD,
            'text': ElementType.TEXT,
            'label': ElementType.LABEL,
            'icon': ElementType.ICON,
            'checkbox': ElementType.CHECKBOX,
            'container': ElementType.CONTAINER,
            'group': ElementType.CONTAINER,
            'root': ElementType.WINDOW,
            'window': ElementType.WINDOW,
            'dropdown': ElementType.DROPDOWN,
            'list': ElementType.LIST,
            'list_item': ElementType.LIST_ITEM,
            'menu': ElementType.MENU,
            'menu_item': ElementType.MENU_ITEM,
        }

        elem_type = type_mapping.get(visual_type, type_mapping.get(role, ElementType.UNKNOWN))

        # Parse bounds [x1, y1, x2, y2] to BoundingBox
        bounds = elem_data.get('bounds', [0, 0, 0, 0])
        if len(bounds) == 4:
            bbox = BoundingBox.from_xyxy(bounds[0], bounds[1], bounds[2], bounds[3])
        else:
            bbox = None

        # Create element
        properties = {
            'role': role,
            'visual_type': visual_type,
            'clickable': elem_data.get('clickable', False),
            'editable': elem_data.get('editable', False),
            'scrollable': elem_data.get('scrollable', False),
            'center': elem_data.get('center', []),
        }
        # Include locators if present
        if elem_data.get('locators'):
            properties['locators'] = elem_data['locators']

        element = DOMElement(
            id=elem_data.get('id', ''),
            type=elem_type,
            bbox=bbox,
            text=elem_data.get('text', ''),
            confidence=elem_data.get('confidence', 1.0),
            parent=parent,
            properties=properties
        )

        # Parse children recursively
        for child_data in elem_data.get('children', []):
            child = cls._parse_visual_dom_element(child_data, element)
            element.children.append(child)

        return element

    @classmethod
    def from_json(cls, json_str: str) -> 'DOMTree':
        """Create tree from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_json_file(cls, filepath: str) -> 'DOMTree':
        """Load tree from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))

    def save_to_json(self, filepath: str) -> None:
        """Save tree to JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"DOMTree(title='{self.title}', elements={self.get_element_count()})"
