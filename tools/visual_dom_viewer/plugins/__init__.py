"""
Plugin system for Visual DOM Viewer.

Provides pluggable strategies for different platforms:
- Windows (UIAutomation)
- Android (UIAutomator/ADB)
- Linux (AT-SPI)
- Web (Browser DevTools)
- VisualDOM (Screenshot-based CV detection)
"""

from .base import PlatformPlugin, PluginManager
from .registry import PluginRegistry
from .platform_manager import (
    PlatformManager, PlatformHandler, PlatformType,
    PlatformConfig, TargetApplication
)

__all__ = [
    "PlatformPlugin",
    "PluginManager",
    "PluginRegistry",
    "PlatformManager",
    "PlatformHandler",
    "PlatformType",
    "PlatformConfig",
    "TargetApplication",
]
