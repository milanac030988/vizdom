"""
Platform Manager - Unified wrapper for platform plugins.

Provides a consistent interface for:
- Platform selection and configuration
- Target application discovery
- Screenshot capture
- DOM generation via Visual DOM pipeline
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import threading


class PlatformType(Enum):
    """Supported platform types."""
    WINDOWS = "windows"
    ANDROID = "android"
    LINUX = "linux"
    WEB = "web"


@dataclass
class TargetApplication:
    """Represents a target application/window."""
    id: str  # Window handle, package name, etc.
    title: str  # Display name
    process_name: str = ""
    pid: int = 0
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height
    icon: Optional[bytes] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __str__(self):
        return f"{self.title} ({self.process_name})" if self.process_name else self.title


@dataclass
class PlatformConfig:
    """Configuration for a platform connection."""
    platform: PlatformType
    target: Optional[TargetApplication] = None
    device_id: str = ""  # For Android
    activity_name: str = ""  # For Android
    url: str = ""  # For Web
    extra: Dict[str, Any] = field(default_factory=dict)


class PlatformHandler(ABC):
    """
    Abstract base class for platform-specific handlers.

    Each platform (Windows, Android, Linux, Web) implements this interface.
    """

    PLATFORM_TYPE: PlatformType = None
    PLATFORM_NAME: str = "Unknown"
    PLATFORM_DESCRIPTION: str = ""

    def __init__(self):
        self._connected = False
        self._config: Optional[PlatformConfig] = None
        self._last_screenshot: Optional[bytes] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def config(self) -> Optional[PlatformConfig]:
        return self._config

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this platform is available on current system."""
        pass

    @abstractmethod
    def list_targets(self) -> List[TargetApplication]:
        """List available target applications/windows."""
        pass

    @abstractmethod
    def connect(self, config: PlatformConfig) -> bool:
        """Connect to target application."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from target."""
        pass

    @abstractmethod
    def capture_screenshot(self) -> Optional[bytes]:
        """Capture screenshot from target."""
        pass

    def get_last_screenshot(self) -> Optional[bytes]:
        """Get the last captured screenshot."""
        return self._last_screenshot


class PlatformManager:
    """
    Singleton manager for platform handlers.

    Provides unified interface for:
    - Listing available platforms
    - Connecting to targets
    - Capturing and analyzing screenshots
    """

    _instance: Optional['PlatformManager'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'PlatformManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._handlers: Dict[PlatformType, PlatformHandler] = {}
        self._current_handler: Optional[PlatformHandler] = None
        self._listeners: List[callable] = []

        # Register built-in handlers
        self._register_builtin_handlers()

    def _register_builtin_handlers(self):
        """Register built-in platform handlers."""
        # Import and register handlers
        try:
            from .windows_handler import WindowsPlatformHandler
            handler = WindowsPlatformHandler()
            if handler.is_available():
                self._handlers[PlatformType.WINDOWS] = handler
        except ImportError as e:
            print(f"Windows handler not available: {e}")

        try:
            from .android_handler import AndroidPlatformHandler
            handler = AndroidPlatformHandler()
            if handler.is_available():
                self._handlers[PlatformType.ANDROID] = handler
        except ImportError as e:
            print(f"Android handler not available: {e}")

    @classmethod
    def get_instance(cls) -> 'PlatformManager':
        """Get singleton instance."""
        return cls()

    def add_listener(self, callback: callable) -> None:
        """Add state change listener."""
        self._listeners.append(callback)

    def _notify(self, event: str, data: Any = None) -> None:
        """Notify listeners of state change."""
        for callback in self._listeners:
            try:
                callback(event, data)
            except Exception as e:
                print(f"Error in listener: {e}")

    def get_available_platforms(self) -> List[Tuple[PlatformType, str, str]]:
        """
        Get list of available platforms.

        Returns:
            List of (PlatformType, name, description) tuples
        """
        platforms = []
        for platform_type, handler in self._handlers.items():
            platforms.append((
                platform_type,
                handler.PLATFORM_NAME,
                handler.PLATFORM_DESCRIPTION
            ))
        return platforms

    def get_handler(self, platform: PlatformType) -> Optional[PlatformHandler]:
        """Get handler for a platform."""
        return self._handlers.get(platform)

    def list_targets(self, platform: PlatformType) -> List[TargetApplication]:
        """List available targets for a platform."""
        handler = self._handlers.get(platform)
        if handler:
            return handler.list_targets()
        return []

    def connect(self, config: PlatformConfig) -> bool:
        """
        Connect to a target application.

        Args:
            config: Platform configuration with target info

        Returns:
            True if connection successful
        """
        handler = self._handlers.get(config.platform)
        if not handler:
            return False

        # Disconnect current if any
        if self._current_handler and self._current_handler.is_connected:
            self._current_handler.disconnect()

        # Connect to new target
        if handler.connect(config):
            self._current_handler = handler
            self._notify('connected', config)
            return True

        return False

    def disconnect(self) -> None:
        """Disconnect from current target."""
        if self._current_handler:
            self._current_handler.disconnect()
            self._notify('disconnected', None)
            self._current_handler = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to a target."""
        return self._current_handler is not None and self._current_handler.is_connected

    @property
    def current_handler(self) -> Optional[PlatformHandler]:
        """Get current active handler."""
        return self._current_handler

    @property
    def current_config(self) -> Optional[PlatformConfig]:
        """Get current connection config."""
        if self._current_handler:
            return self._current_handler.config
        return None

    def capture_screenshot(self) -> Optional[bytes]:
        """Capture screenshot from current target."""
        if not self._current_handler:
            return None

        screenshot = self._current_handler.capture_screenshot()
        if screenshot:
            self._notify('screenshot_captured', screenshot)
        return screenshot

    def capture_and_analyze(self) -> Tuple[Optional[bytes], Optional[Any]]:
        """
        Capture screenshot and generate DOM using Visual DOM pipeline.

        Returns:
            Tuple of (screenshot_bytes, dom_tree)
        """
        screenshot = self.capture_screenshot()
        if not screenshot:
            return None, None

        # Run Visual DOM pipeline
        try:
            from visual_dom import VisualDOMGenerator

            # Save screenshot temporarily
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                f.write(screenshot)
                temp_path = f.name

            try:
                generator = VisualDOMGenerator()
                dom = generator.process(temp_path)
                self._notify('dom_generated', dom)
                return screenshot, dom
            finally:
                os.unlink(temp_path)

        except ImportError:
            print("Visual DOM Generator not available")
            return screenshot, None
        except Exception as e:
            print(f"Error generating DOM: {e}")
            return screenshot, None
