"""
State management for Visual DOM Viewer.

Implements state machine and snapshot pattern for viewer state.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Set, Any
from enum import Enum, auto


class ViewerMode(Enum):
    """Viewer interaction modes."""
    IDLE = auto()           # No interaction
    EXPLORE = auto()        # Hover highlighting (dashed rectangle)
    SELECT = auto()         # Element selected (solid rectangle)
    MULTI_SELECT = auto()   # Multiple elements selected
    PAN = auto()            # Panning the view
    ZOOM = auto()           # Zooming the view


class ViewerState(Enum):
    """Viewer workflow states."""
    INITIAL = auto()        # Initial state, no DOM loaded
    LOADING = auto()        # Loading DOM/screenshot
    READY = auto()          # DOM loaded, ready for interaction
    ANALYZING = auto()      # Running analysis/detection
    EXPORTING = auto()      # Exporting to file
    ERROR = auto()          # Error state


@dataclass
class SelectionState:
    """Track element selection state."""
    selected_id: Optional[str] = None
    hovered_id: Optional[str] = None
    multi_selected_ids: Set[str] = field(default_factory=set)

    def select(self, element_id: str) -> None:
        """Select a single element."""
        self.selected_id = element_id
        self.multi_selected_ids.clear()

    def toggle_multi_select(self, element_id: str) -> None:
        """Toggle multi-selection for an element."""
        if element_id in self.multi_selected_ids:
            self.multi_selected_ids.discard(element_id)
        else:
            self.multi_selected_ids.add(element_id)

    def clear_selection(self) -> None:
        """Clear all selection."""
        self.selected_id = None
        self.multi_selected_ids.clear()

    def hover(self, element_id: Optional[str]) -> None:
        """Set hovered element."""
        self.hovered_id = element_id

    def get_all_selected(self) -> Set[str]:
        """Get all selected element IDs."""
        result = set(self.multi_selected_ids)
        if self.selected_id:
            result.add(self.selected_id)
        return result


@dataclass
class ViewState:
    """Track view transformation state."""
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def zoom_in(self, factor: float = 1.2) -> None:
        """Zoom in by factor."""
        self.scale *= factor

    def zoom_out(self, factor: float = 1.2) -> None:
        """Zoom out by factor."""
        self.scale /= factor

    def reset(self) -> None:
        """Reset to default view."""
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

    def fit_to_size(self, content_width: int, content_height: int,
                    viewport_width: int, viewport_height: int) -> None:
        """Fit content to viewport."""
        scale_x = viewport_width / content_width if content_width > 0 else 1.0
        scale_y = viewport_height / content_height if content_height > 0 else 1.0
        self.scale = min(scale_x, scale_y, 1.0)
        self.offset_x = 0
        self.offset_y = 0

    def screen_to_content(self, screen_x: float, screen_y: float) -> tuple:
        """Convert screen coordinates to content coordinates."""
        content_x = (screen_x - self.offset_x) / self.scale
        content_y = (screen_y - self.offset_y) / self.scale
        return (int(content_x), int(content_y))

    def content_to_screen(self, content_x: float, content_y: float) -> tuple:
        """Convert content coordinates to screen coordinates."""
        screen_x = content_x * self.scale + self.offset_x
        screen_y = content_y * self.scale + self.offset_y
        return (screen_x, screen_y)


@dataclass
class ViewerStateSnapshot:
    """
    Immutable snapshot of viewer state.
    Used for state tracking and undo/redo.
    """
    state: ViewerState
    mode: ViewerMode
    selection: SelectionState
    view: ViewState
    dom_file: Optional[str] = None
    screenshot_file: Optional[str] = None
    platform: str = "unknown"
    error_message: Optional[str] = None

    def copy(self) -> 'ViewerStateSnapshot':
        """Create a copy of the snapshot."""
        return ViewerStateSnapshot(
            state=self.state,
            mode=self.mode,
            selection=SelectionState(
                selected_id=self.selection.selected_id,
                hovered_id=self.selection.hovered_id,
                multi_selected_ids=set(self.selection.multi_selected_ids),
            ),
            view=ViewState(
                scale=self.view.scale,
                offset_x=self.view.offset_x,
                offset_y=self.view.offset_y,
            ),
            dom_file=self.dom_file,
            screenshot_file=self.screenshot_file,
            platform=self.platform,
            error_message=self.error_message,
        )


class StateManager:
    """
    Manages viewer state with history support.
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._history: List[ViewerStateSnapshot] = []
        self._history_index: int = -1
        self._current = ViewerStateSnapshot(
            state=ViewerState.INITIAL,
            mode=ViewerMode.IDLE,
            selection=SelectionState(),
            view=ViewState(),
        )

    @property
    def current(self) -> ViewerStateSnapshot:
        """Get current state snapshot."""
        return self._current

    def update(self, **kwargs) -> ViewerStateSnapshot:
        """
        Update state and add to history.
        Returns new state snapshot.
        """
        # Create new snapshot with updates
        new_state = self._current.copy()

        for key, value in kwargs.items():
            if hasattr(new_state, key):
                setattr(new_state, key, value)

        # Add to history
        self._add_to_history(new_state)
        self._current = new_state

        return new_state

    def _add_to_history(self, snapshot: ViewerStateSnapshot) -> None:
        """Add snapshot to history."""
        # Remove any forward history if we're not at the end
        if self._history_index < len(self._history) - 1:
            self._history = self._history[:self._history_index + 1]

        self._history.append(snapshot)
        self._history_index = len(self._history) - 1

        # Trim history if too long
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
            self._history_index = len(self._history) - 1

    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return self._history_index > 0

    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return self._history_index < len(self._history) - 1

    def undo(self) -> Optional[ViewerStateSnapshot]:
        """Undo to previous state."""
        if self.can_undo():
            self._history_index -= 1
            self._current = self._history[self._history_index]
            return self._current
        return None

    def redo(self) -> Optional[ViewerStateSnapshot]:
        """Redo to next state."""
        if self.can_redo():
            self._history_index += 1
            self._current = self._history[self._history_index]
            return self._current
        return None

    def reset(self) -> ViewerStateSnapshot:
        """Reset to initial state."""
        self._history.clear()
        self._history_index = -1
        self._current = ViewerStateSnapshot(
            state=ViewerState.INITIAL,
            mode=ViewerMode.IDLE,
            selection=SelectionState(),
            view=ViewState(),
        )
        return self._current
