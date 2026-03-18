"""
Plugin Registry - Central registry for all platform plugins.

Provides automatic discovery and registration of plugins.
"""

from typing import Dict, Type, Optional, List, Any
from pathlib import Path
import importlib
import sys

from .base import PlatformPlugin, PluginManager


class PluginRegistry:
    """
    Global registry for platform plugins.

    Singleton pattern to ensure consistent plugin management.
    """

    _instance: Optional['PluginRegistry'] = None
    _manager: Optional[PluginManager] = None

    def __new__(cls) -> 'PluginRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._manager = PluginManager()
            cls._instance._initialize_builtin_plugins()
        return cls._instance

    def _initialize_builtin_plugins(self) -> None:
        """Register built-in plugins."""
        # Import and register built-in plugins
        builtin_plugins = [
            'visual_dom_plugin',
            # Future plugins:
            # 'windows_plugin',
            # 'android_plugin',
            # 'linux_plugin',
            # 'web_plugin',
        ]

        for plugin_module in builtin_plugins:
            try:
                # Try to import from same package
                module = importlib.import_module(
                    f".{plugin_module}",
                    package="tools.visual_dom_viewer.plugins"
                )

                # Find and register plugin classes
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, PlatformPlugin) and
                        attr is not PlatformPlugin):
                        self._manager.register_plugin(attr)

            except ImportError as e:
                # Plugin not available, skip
                pass

    @classmethod
    def get_manager(cls) -> PluginManager:
        """Get the plugin manager instance."""
        registry = cls()
        return cls._manager

    @classmethod
    def register(cls, plugin_class: Type[PlatformPlugin]) -> None:
        """Register a plugin class."""
        registry = cls()
        cls._manager.register_plugin(plugin_class)

    @classmethod
    def get_plugin(cls, name: str, config: Dict[str, Any] = None) -> Optional[PlatformPlugin]:
        """Get a plugin instance by name."""
        registry = cls()
        return cls._manager.get_plugin(name, config)

    @classmethod
    def list_plugins(cls) -> List[Dict[str, Any]]:
        """List all available plugins."""
        registry = cls()
        return cls._manager.get_available_plugins()

    @classmethod
    def discover_external_plugins(cls, path: str) -> List[str]:
        """Discover plugins from external path."""
        registry = cls()
        cls._manager.add_plugin_path(path)
        return cls._manager.discover_plugins()


# Decorator for easy plugin registration
def register_plugin(cls: Type[PlatformPlugin]) -> Type[PlatformPlugin]:
    """Decorator to register a plugin class."""
    PluginRegistry.register(cls)
    return cls
