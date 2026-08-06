"""
DOM Viewer Model - Central state management (Singleton pattern).

Manages the DOM tree, screenshot, selection state, and coordinates
between different views (canvas, tree, inspector).
"""

from typing import Optional, List, Callable, Any, Dict
from pathlib import Path
import threading

from .tree import DOMTree, DOMElement, BoundingBox
from .state import (
    StateManager, ViewerState, ViewerMode,
    SelectionState, ViewState, ViewerStateSnapshot
)
from .element_definition import ElementDefinition, ElementDefinitionManager


class DOMViewerModel:
    """
    Singleton model managing viewer state.

    Coordinates between:
    - Screenshot canvas view
    - Element tree view
    - Property inspector view

    Provides:
    - DOM tree management
    - Selection/highlighting state
    - View transformation (zoom/pan)
    - Event notification to views
    """

    _instance: Optional['DOMViewerModel'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'DOMViewerModel':
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize model (only once due to singleton)."""
        if self._initialized:
            return

        self._initialized = True

        # Core data
        self._dom_tree: Optional[DOMTree] = None
        self._screenshot_path: Optional[Path] = None
        self._screenshot_data: Optional[bytes] = None

        # State management
        self._state_manager = StateManager()

        # Event listeners
        self._listeners: Dict[str, List[Callable]] = {
            'dom_loaded': [],
            'screenshot_loaded': [],
            'selection_changed': [],
            'hover_changed': [],
            'state_changed': [],
            'view_changed': [],
            'definition_changed': [],
            'error': [],
        }

        # Element definitions manager
        self._definition_manager = ElementDefinitionManager()

    @classmethod
    def get_instance(cls) -> 'DOMViewerModel':
        """Get singleton instance."""
        return cls()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def dom_tree(self) -> Optional[DOMTree]:
        """Get current DOM tree."""
        return self._dom_tree

    @property
    def screenshot_path(self) -> Optional[Path]:
        """Get screenshot file path."""
        return self._screenshot_path

    @property
    def state(self) -> ViewerStateSnapshot:
        """Get current state snapshot."""
        return self._state_manager.current

    @property
    def is_explore_mode(self) -> bool:
        """Check if in explore mode (hover highlighting)."""
        return self._state_manager.current.mode == ViewerMode.EXPLORE

    @property
    def selected_element(self) -> Optional[DOMElement]:
        """Get currently selected element."""
        if self._dom_tree and self.state.selection.selected_id:
            return self._dom_tree.get_element_by_id(self.state.selection.selected_id)
        return None

    @property
    def hovered_element(self) -> Optional[DOMElement]:
        """Get currently hovered element."""
        if self._dom_tree and self.state.selection.hovered_id:
            return self._dom_tree.get_element_by_id(self.state.selection.hovered_id)
        return None

    # =========================================================================
    # Event System
    # =========================================================================

    def add_listener(self, event: str, callback: Callable) -> None:
        """Add event listener."""
        if event in self._listeners:
            self._listeners[event].append(callback)

    def remove_listener(self, event: str, callback: Callable) -> None:
        """Remove event listener."""
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def _notify(self, event: str, *args, **kwargs) -> None:
        """Notify all listeners of an event."""
        for callback in self._listeners.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"Error in listener {callback}: {e}")

    # =========================================================================
    # DOM Tree Operations
    # =========================================================================

    def load_dom_from_file(self, filepath: str) -> bool:
        """Load DOM tree from JSON file."""
        try:
            self._update_state(state=ViewerState.LOADING)

            self._dom_tree = DOMTree.from_json_file(filepath)
            self._update_state(
                state=ViewerState.READY,
                dom_file=filepath
            )
            self._notify('dom_loaded', self._dom_tree)
            return True

        except Exception as e:
            self._update_state(
                state=ViewerState.ERROR,
                error_message=str(e)
            )
            self._notify('error', e)
            return False

    def load_dom_from_dict(self, data: Dict[str, Any]) -> bool:
        """Load DOM tree from dictionary."""
        try:
            self._update_state(state=ViewerState.LOADING)

            self._dom_tree = DOMTree.from_dict(data)
            self._update_state(state=ViewerState.READY)
            self._notify('dom_loaded', self._dom_tree)
            return True

        except Exception as e:
            self._update_state(
                state=ViewerState.ERROR,
                error_message=str(e)
            )
            self._notify('error', e)
            return False

    def set_dom_tree(self, tree: DOMTree) -> None:
        """Set DOM tree directly."""
        self._dom_tree = tree
        self._update_state(state=ViewerState.READY)
        self._notify('dom_loaded', tree)

    # =========================================================================
    # Screenshot Operations
    # =========================================================================

    def load_screenshot(self, filepath: str) -> bool:
        """Load screenshot from file."""
        try:
            path = Path(filepath)
            if not path.exists():
                raise FileNotFoundError(f"Screenshot not found: {filepath}")

            with open(path, 'rb') as f:
                self._screenshot_data = f.read()

            self._screenshot_path = path
            self._update_state(screenshot_file=str(path))
            self._notify('screenshot_loaded', path)
            return True

        except Exception as e:
            self._notify('error', e)
            return False

    def set_screenshot_data(self, data: bytes, filename: str = "screenshot.png") -> None:
        """Set screenshot data directly."""
        self._screenshot_data = data
        self._screenshot_path = Path(filename)
        self._notify('screenshot_loaded', self._screenshot_path)

    def get_screenshot_data(self) -> Optional[bytes]:
        """Get screenshot image data."""
        return self._screenshot_data

    # =========================================================================
    # Selection Operations
    # =========================================================================

    def select_element(self, element_id: Optional[str]) -> None:
        """Select an element by ID."""
        selection = SelectionState(
            selected_id=element_id,
            hovered_id=self.state.selection.hovered_id,
            multi_selected_ids=self.state.selection.multi_selected_ids.copy()
        )
        self._update_state(
            selection=selection,
            mode=ViewerMode.SELECT if element_id else ViewerMode.EXPLORE
        )
        self._notify('selection_changed', self.selected_element)

    def select_elements(self, element_ids) -> None:
        """
        Replace the whole selection with `element_ids` (order-preserving input).

        Used by the tree view's ExtendedSelection: the LAST id becomes the
        primary selection (drives the property panel) and ALL ids populate
        `multi_selected_ids`, so the canvas highlights every selected element
        rather than only one.
        """
        ids = [i for i in (element_ids or []) if i]
        primary = ids[-1] if ids else None
        selection = SelectionState(
            selected_id=primary,
            hovered_id=self.state.selection.hovered_id,
            multi_selected_ids=set(ids),
        )
        self._update_state(
            selection=selection,
            mode=ViewerMode.SELECT if primary else ViewerMode.EXPLORE,
        )
        self._notify('selection_changed', self.selected_element)

    def select_element_at_point(self, x: int, y: int) -> Optional[DOMElement]:
        """Select element at given screen coordinates."""
        if not self._dom_tree:
            return None

        # Convert screen to content coordinates if needed
        view = self.state.view
        content_x, content_y = view.screen_to_content(x, y)

        element = self._dom_tree.find_element_at_point(content_x, content_y)
        if element:
            self.select_element(element.id)
        return element

    def hover_element(self, element_id: Optional[str]) -> None:
        """Set hovered element (for explore mode)."""
        if self.state.selection.hovered_id == element_id:
            return  # No change

        selection = SelectionState(
            selected_id=self.state.selection.selected_id,
            hovered_id=element_id,
            multi_selected_ids=self.state.selection.multi_selected_ids.copy()
        )
        self._update_state(selection=selection)
        self._notify('hover_changed', self.hovered_element)

    def hover_element_at_point(self, x: int, y: int) -> Optional[DOMElement]:
        """Update hover for element at given coordinates."""
        if not self._dom_tree or self.state.mode != ViewerMode.EXPLORE:
            return None

        view = self.state.view
        content_x, content_y = view.screen_to_content(x, y)

        element = self._dom_tree.find_element_at_point(content_x, content_y)
        self.hover_element(element.id if element else None)
        return element

    def toggle_multi_select(self, element_id: str) -> None:
        """Toggle multi-selection for an element."""
        new_ids = self.state.selection.multi_selected_ids.copy()
        if element_id in new_ids:
            new_ids.discard(element_id)
        else:
            new_ids.add(element_id)

        selection = SelectionState(
            selected_id=self.state.selection.selected_id,
            hovered_id=self.state.selection.hovered_id,
            multi_selected_ids=new_ids
        )
        self._update_state(
            selection=selection,
            mode=ViewerMode.MULTI_SELECT if new_ids else ViewerMode.SELECT
        )
        self._notify('selection_changed', self.selected_element)

    def clear_selection(self) -> None:
        """Clear all selection."""
        selection = SelectionState(
            hovered_id=self.state.selection.hovered_id
        )
        self._update_state(
            selection=selection,
            mode=ViewerMode.EXPLORE
        )
        self._notify('selection_changed', None)

    def get_selected_elements(self) -> List[DOMElement]:
        """Get all selected elements."""
        if not self._dom_tree:
            return []

        elements = []
        for elem_id in self.state.selection.get_all_selected():
            elem = self._dom_tree.get_element_by_id(elem_id)
            if elem:
                elements.append(elem)
        return elements

    # =========================================================================
    # Mode Operations
    # =========================================================================

    def set_explore_mode(self, enabled: bool = True) -> None:
        """Enable/disable explore mode."""
        if enabled:
            self._update_state(mode=ViewerMode.EXPLORE)
        else:
            self._update_state(mode=ViewerMode.SELECT)

    def toggle_explore_mode(self) -> bool:
        """Toggle explore mode."""
        new_mode = ViewerMode.SELECT if self.is_explore_mode else ViewerMode.EXPLORE
        self._update_state(mode=new_mode)
        return new_mode == ViewerMode.EXPLORE

    # =========================================================================
    # View Operations
    # =========================================================================

    def zoom_in(self) -> None:
        """Zoom in the view."""
        view = ViewState(
            scale=self.state.view.scale * 1.2,
            offset_x=self.state.view.offset_x,
            offset_y=self.state.view.offset_y
        )
        self._update_state(view=view)
        self._notify('view_changed', view)

    def zoom_out(self) -> None:
        """Zoom out the view."""
        view = ViewState(
            scale=self.state.view.scale / 1.2,
            offset_x=self.state.view.offset_x,
            offset_y=self.state.view.offset_y
        )
        self._update_state(view=view)
        self._notify('view_changed', view)

    def reset_view(self) -> None:
        """Reset view to default."""
        view = ViewState()
        self._update_state(view=view)
        self._notify('view_changed', view)

    def fit_to_viewport(self, viewport_width: int, viewport_height: int) -> None:
        """Fit content to viewport size."""
        if not self._dom_tree:
            return

        view = ViewState()
        view.fit_to_size(
            self._dom_tree.screen_width,
            self._dom_tree.screen_height,
            viewport_width,
            viewport_height
        )
        self._update_state(view=view)
        self._notify('view_changed', view)

    # =========================================================================
    # State Management
    # =========================================================================

    def _update_state(self, **kwargs) -> ViewerStateSnapshot:
        """Update state and notify listeners."""
        new_state = self._state_manager.update(**kwargs)
        self._notify('state_changed', new_state)
        return new_state

    def undo(self) -> bool:
        """Undo last state change."""
        result = self._state_manager.undo()
        if result:
            self._notify('state_changed', result)
            return True
        return False

    def redo(self) -> bool:
        """Redo last undone state change."""
        result = self._state_manager.redo()
        if result:
            self._notify('state_changed', result)
            return True
        return False

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._state_manager.can_undo()

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._state_manager.can_redo()

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_elements_in_rect(self, x1: int, y1: int, x2: int, y2: int) -> List[DOMElement]:
        """Get all elements within a rectangle."""
        if not self._dom_tree:
            return []

        rect = BoundingBox.from_xyxy(x1, y1, x2, y2)
        results = []

        for element in self._dom_tree.get_all_elements():
            if element.bbox and rect.intersects(element.bbox):
                results.append(element)

        return results

    def search_elements(self, query: str) -> List[DOMElement]:
        """Search elements by text or type."""
        if not self._dom_tree:
            return []

        results = []
        query_lower = query.lower()

        for element in self._dom_tree.get_all_elements():
            if (query_lower in element.text.lower() or
                query_lower in element.type.value.lower() or
                query_lower in element.id.lower()):
                results.append(element)

        return results

    # =========================================================================
    # Element Definition Operations
    # =========================================================================

    @property
    def definition_manager(self) -> ElementDefinitionManager:
        """Get the element definition manager."""
        return self._definition_manager

    def define_element(
        self,
        element: DOMElement,
        name: str,
        selected_properties: List[str]
    ) -> ElementDefinition:
        """
        Create or update definition for an element.

        Args:
            element: The DOM element to define
            name: User-defined name (e.g., "Button_Number_4")
            selected_properties: List of property names to use as locators

        Returns:
            The created/updated ElementDefinition
        """
        # Build property values from element
        property_values = self._extract_element_properties(element)

        definition = ElementDefinition(
            element_id=element.id,
            name=name,
            selected_properties=set(selected_properties),
            property_values=property_values
        )

        self._definition_manager.add_definition(definition)
        self._notify('definition_changed', definition)
        return definition

    def _extract_element_properties(self, element: DOMElement) -> Dict[str, Any]:
        """Extract all available properties from an element."""
        props = {
            'text': element.text,
            'type': element.type.value,
            'id': element.id,
            'confidence': element.confidence,
        }

        if element.bbox:
            props['bbox'] = [
                element.bbox.x,
                element.bbox.y,
                element.bbox.width,
                element.bbox.height
            ]
            props['center'] = list(element.bbox.center)
            props['x'] = element.bbox.x
            props['y'] = element.bbox.y
            props['width'] = element.bbox.width
            props['height'] = element.bbox.height

        # Add custom properties
        props.update(element.properties)

        return props

    def remove_definition(self, element_id: str) -> bool:
        """Remove element definition."""
        definition = self._definition_manager.remove_definition(element_id)
        if definition:
            self._notify('definition_changed', None)
            return True
        return False

    def get_definition(self, element_id: str) -> Optional[ElementDefinition]:
        """Get definition for an element."""
        return self._definition_manager.get_definition(element_id)

    def get_all_definitions(self) -> List[ElementDefinition]:
        """Get all element definitions."""
        return self._definition_manager.get_all_definitions()

    def save_definitions(self, filepath: str) -> bool:
        """Save element definitions to file."""
        return self._definition_manager.save_to_file(filepath)

    def load_definitions(self, filepath: str) -> bool:
        """Load element definitions from file."""
        result = self._definition_manager.load_from_file(filepath)
        if result:
            self._notify('definition_changed', None)
        return result
