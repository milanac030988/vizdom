"""
Base classes for platform plugins.

Defines the interface that all platform plugins must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Type
from pathlib import Path
import importlib
import importlib.util
import sys
import os

from ..core.tree import DOMTree, DOMElement


class PlatformPlugin(ABC):
    """
    Abstract base class for platform plugins.

    Each platform (Windows, Android, Linux, Web, VisualDOM) implements
    this interface to provide:
    - Screenshot capture
    - DOM tree extraction
    - Element interaction
    """

    # Plugin metadata
    PLUGIN_NAME: str = "base"
    PLUGIN_VERSION: str = "0.0.0"
    PLUGIN_DESCRIPTION: str = "Base platform plugin"
    SUPPORTED_PLATFORMS: List[str] = []

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize plugin with optional configuration.

        Args:
            config: Platform-specific configuration dictionary
        """
        self.config = config or {}
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if plugin is connected to target."""
        return self._connected

    @abstractmethod
    def connect(self, target: str = None) -> bool:
        """
        Connect to target application/device.

        Args:
            target: Target identifier (window title, device ID, URL, etc.)

        Returns:
            True if connected successfully
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from target."""
        pass

    @abstractmethod
    def capture_screenshot(self) -> Optional[bytes]:
        """
        Capture screenshot of current screen/window.

        Returns:
            Screenshot image data as bytes (PNG format)
        """
        pass

    @abstractmethod
    def get_dom_tree(self) -> Optional[DOMTree]:
        """
        Extract DOM tree from current screen/window.

        Returns:
            DOMTree object representing the UI hierarchy
        """
        pass

    @abstractmethod
    def get_element_at_point(self, x: int, y: int) -> Optional[DOMElement]:
        """
        Get element at specific screen coordinates.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            DOMElement at the point, or None
        """
        pass

    def refresh(self) -> bool:
        """
        Refresh the DOM tree and screenshot.

        Returns:
            True if refresh successful
        """
        return self.get_dom_tree() is not None

    def click_element(self, element: DOMElement) -> bool:
        """
        Click on an element.

        Args:
            element: Element to click

        Returns:
            True if click successful
        """
        # Default implementation - can be overridden
        if element.bbox:
            return self.click_at(element.bbox.center[0], element.bbox.center[1])
        return False

    def click_at(self, x: int, y: int) -> bool:
        """
        Click at specific coordinates.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if click successful
        """
        # Default: not implemented
        return False

    def input_text(self, element: DOMElement, text: str) -> bool:
        """
        Input text to an element.

        Args:
            element: Target element
            text: Text to input

        Returns:
            True if input successful
        """
        # Default: not implemented
        return False

    def get_element_properties(self, element: DOMElement) -> Dict[str, Any]:
        """
        Get detailed properties of an element.

        Args:
            element: Target element

        Returns:
            Dictionary of element properties
        """
        # Default implementation
        return {
            'id': element.id,
            'type': element.type.value,
            'text': element.text,
            'bbox': element.bbox.to_list() if element.bbox else None,
            'confidence': element.confidence,
            **element.properties
        }

    def validate_connection(self) -> bool:
        """
        Validate that connection is still active.

        Returns:
            True if connection is valid
        """
        return self._connected

    def get_available_targets(self) -> List[Dict[str, str]]:
        """
        Get list of available targets (windows, devices, etc.)

        Returns:
            List of target info dictionaries with 'id' and 'name' keys
        """
        return []

    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        """Get plugin information."""
        return {
            'name': cls.PLUGIN_NAME,
            'version': cls.PLUGIN_VERSION,
            'description': cls.PLUGIN_DESCRIPTION,
            'platforms': cls.SUPPORTED_PLATFORMS,
        }


class PluginManager:
    """
    Manages loading and instantiation of platform plugins.

    Supports:
    - Built-in plugins (in plugins/ directory)
    - External plugins (from configurable paths)
    - Dynamic plugin discovery
    """

    def __init__(self):
        self._plugins: Dict[str, Type[PlatformPlugin]] = {}
        self._instances: Dict[str, PlatformPlugin] = {}
        self._plugin_paths: List[Path] = []

    def add_plugin_path(self, path: str) -> None:
        """Add path to search for plugins."""
        p = Path(path)
        if p.exists() and p.is_dir():
            self._plugin_paths.append(p)

    def register_plugin(self, plugin_class: Type[PlatformPlugin]) -> None:
        """Register a plugin class."""
        name = plugin_class.PLUGIN_NAME
        self._plugins[name] = plugin_class

    def unregister_plugin(self, name: str) -> None:
        """Unregister a plugin."""
        if name in self._plugins:
            del self._plugins[name]
        if name in self._instances:
            self._instances[name].disconnect()
            del self._instances[name]

    def discover_plugins(self) -> List[str]:
        """
        Discover plugins from registered paths.

        Returns:
            List of discovered plugin names
        """
        discovered = []

        for plugin_path in self._plugin_paths:
            for file in plugin_path.glob("*.py"):
                if file.name.startswith("_"):
                    continue

                try:
                    plugin_name = file.stem
                    spec = importlib.util.spec_from_file_location(
                        f"visual_dom_viewer.plugins.{plugin_name}",
                        file
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[spec.name] = module
                        spec.loader.exec_module(module)

                        # Look for PlatformPlugin subclasses
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and
                                issubclass(attr, PlatformPlugin) and
                                attr is not PlatformPlugin):
                                self.register_plugin(attr)
                                discovered.append(attr.PLUGIN_NAME)

                except Exception as e:
                    print(f"Error loading plugin from {file}: {e}")

        return discovered

    def get_plugin(self, name: str, config: Dict[str, Any] = None) -> Optional[PlatformPlugin]:
        """
        Get or create plugin instance.

        Args:
            name: Plugin name
            config: Optional configuration

        Returns:
            Plugin instance or None
        """
        if name not in self._plugins:
            return None

        # Create new instance if not exists or config changed
        if name not in self._instances:
            self._instances[name] = self._plugins[name](config)
        elif config:
            # Recreate with new config
            self._instances[name].disconnect()
            self._instances[name] = self._plugins[name](config)

        return self._instances[name]

    def get_available_plugins(self) -> List[Dict[str, Any]]:
        """Get info about all available plugins."""
        return [cls.get_info() for cls in self._plugins.values()]

    def get_plugins_for_platform(self, platform: str) -> List[str]:
        """Get plugins that support a specific platform."""
        result = []
        for name, cls in self._plugins.items():
            if platform.lower() in [p.lower() for p in cls.SUPPORTED_PLATFORMS]:
                result.append(name)
        return result
