# ADR-003: Platform Handler Plugin Architecture

## Status

Accepted

## Date

2025-01-26

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2025-01-26 | 1.0 | Initial version |

## Context

The Visual DOM Viewer needs to capture screenshots from target applications across different platforms:

- **Windows**: Desktop applications via WinAPI
- **Android**: Mobile apps via ADB
- **Linux**: Applications via X11/Wayland
- **Web**: Browsers via DevTools/Selenium

Requirements:
1. Support multiple platforms with a unified interface
2. Allow adding new platforms without modifying core code
3. Handle platform-specific operations (window enumeration, screenshot capture)
4. Manage connection state and target selection

## Decision

Implement a **Plugin Architecture** with:

1. **Abstract Base Handler**: Defines interface all platform handlers must implement
2. **Platform Manager**: Singleton that manages handler registration and lifecycle
3. **Concrete Handlers**: Platform-specific implementations

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PlatformManager                          │
│                     (Singleton)                             │
├─────────────────────────────────────────────────────────────┤
│  • get_available_platforms()                                │
│  • connect(config)                                          │
│  • disconnect()                                             │
│  • capture_screenshot()                                     │
│  • current_handler: PlatformHandler                         │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ WindowsHandler  │ │ AndroidHandler  │ │  LinuxHandler   │
├─────────────────┤ ├─────────────────┤ ├─────────────────┤
│ • WinAPI        │ │ • ADB           │ │ • X11/Wayland   │
│ • EnumWindows   │ │ • screencap     │ │ • xdotool       │
│ • PrintWindow   │ │ • uiautomator   │ │ • scrot         │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Base Handler Interface

```python
class PlatformHandler(ABC):
    """Abstract base class for platform handlers."""

    @property
    @abstractmethod
    def platform_type(self) -> PlatformType:
        """Return platform type identifier."""
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if platform is available on current system."""
        pass

    @abstractmethod
    def list_targets(self) -> List[TargetApplication]:
        """List available target applications."""
        pass

    @abstractmethod
    def connect(self, config: PlatformConfig) -> bool:
        """Connect to target application."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from current target."""
        pass

    @abstractmethod
    def capture_screenshot(self) -> Optional[bytes]:
        """Capture screenshot from connected target."""
        pass
```

### Windows Handler Implementation

```python
class WindowsPlatformHandler(PlatformHandler):
    """Windows platform handler using WinAPI."""

    def list_targets(self) -> List[TargetApplication]:
        # Use EnumWindows to list visible windows
        windows = []
        def enum_callback(hwnd, results):
            if user32.IsWindowVisible(hwnd):
                title = get_window_title(hwnd)
                if title:
                    results.append(TargetApplication(
                        id=str(hwnd),
                        title=title,
                        process_name=get_process_name(hwnd),
                        bounds=get_window_rect(hwnd)
                    ))
        user32.EnumWindows(EnumWindowsProc(enum_callback), windows)
        return windows

    def capture_screenshot(self) -> Optional[bytes]:
        # Use Desktop DC capture for DWM compatibility
        hwnd = self._connected_hwnd
        rect = get_window_rect(hwnd)

        # Bring window to front
        self.bring_to_front()

        # Capture from desktop DC
        desktop_dc = user32.GetDC(0)
        # ... capture logic
        return png_bytes
```

### Android Handler Implementation

```python
class AndroidPlatformHandler(PlatformHandler):
    """Android platform handler using ADB."""

    def list_targets(self) -> List[TargetApplication]:
        # List connected devices
        result = subprocess.run(['adb', 'devices'], capture_output=True)
        devices = parse_devices(result.stdout)
        return [TargetApplication(id=d.serial, title=d.model) for d in devices]

    def capture_screenshot(self) -> Optional[bytes]:
        # Use adb screencap
        result = subprocess.run(
            ['adb', '-s', self._device_serial, 'exec-out', 'screencap', '-p'],
            capture_output=True
        )
        return result.stdout if result.returncode == 0 else None
```

### Platform Manager Usage

```python
# Get singleton instance
manager = PlatformManager.get_instance()

# List available platforms
platforms = manager.get_available_platforms()
# [('WINDOWS', 'Windows', 'Windows desktop applications'), ...]

# Connect to target
config = PlatformConfig(
    platform=PlatformType.WINDOWS,
    target=selected_window
)
manager.connect(config)

# Capture screenshot
screenshot = manager.capture_screenshot()

# Disconnect
manager.disconnect()
```

## Consequences

### Positive

- **Extensible**: Easy to add new platforms without changing core code
- **Consistent API**: Same interface for all platforms
- **Encapsulated complexity**: Platform-specific code isolated in handlers
- **Testable**: Can mock handlers for testing
- **Auto-detection**: Handlers report availability based on system

### Negative

- **Platform-specific dependencies**: Each handler may need different libraries
- **Complexity**: More code than a single-platform solution
- **Testing burden**: Need to test on each supported platform

### Neutral

- Handler registration happens at import time
- Only one connection active at a time (by design)
- Screenshot capture methods vary by platform capabilities

## Alternatives Considered

### 1. Single Monolithic Handler (Rejected)

One handler class with platform detection and branching logic.

Rejected because:
- Becomes unmaintainable as platforms increase
- Hard to add new platforms
- Violates Single Responsibility Principle

### 2. Subprocess-Only Approach (Rejected)

Use only command-line tools (scrot, screencap, etc.) via subprocess.

Rejected because:
- Less control over capture process
- Harder to enumerate windows/targets
- Missing features like bringing window to front

### 3. Third-Party Library (pyautogui) (Deferred)

Use pyautogui for cross-platform screenshot capture.

Deferred because:
- Less control over specific windows
- Cannot enumerate individual windows well
- Can add as fallback later

## References

- WinAPI documentation: https://docs.microsoft.com/en-us/windows/win32/api/
- ADB documentation: https://developer.android.com/studio/command-line/adb
- Source: `tools/visual_dom_viewer/plugins/platform_manager.py`
- Source: `tools/visual_dom_viewer/plugins/windows_handler.py`
- Source: `tools/visual_dom_viewer/plugins/android_handler.py`
