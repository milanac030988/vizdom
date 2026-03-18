"""
Android Platform Handler - ADB-based device capture.

Uses ADB (Android Debug Bridge) for:
- Listing connected devices
- Capturing device screenshots
- Getting running activities
"""

from typing import Optional, List, Dict, Any
import subprocess
import shutil
import io

from .platform_manager import (
    PlatformHandler, PlatformType, PlatformConfig, TargetApplication
)


class AndroidPlatformHandler(PlatformHandler):
    """
    Android platform handler using ADB.

    Features:
    - List connected Android devices
    - Capture device screenshots
    - Get foreground activity info
    """

    PLATFORM_TYPE = PlatformType.ANDROID
    PLATFORM_NAME = "Android Device"
    PLATFORM_DESCRIPTION = "Capture Android devices via ADB"

    def __init__(self):
        super().__init__()
        self._device_id: Optional[str] = None
        self._adb_path: Optional[str] = None

    def is_available(self) -> bool:
        """Check if ADB is available."""
        self._adb_path = shutil.which('adb')
        return self._adb_path is not None

    def _run_adb(self, *args, device_id: str = None) -> Optional[str]:
        """Run ADB command and return output."""
        if not self._adb_path:
            return None

        cmd = [self._adb_path]

        if device_id:
            cmd.extend(['-s', device_id])

        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            print(f"ADB error: {e}")
            return None

    def _run_adb_bytes(self, *args, device_id: str = None) -> Optional[bytes]:
        """Run ADB command and return bytes output."""
        if not self._adb_path:
            return None

        cmd = [self._adb_path]

        if device_id:
            cmd.extend(['-s', device_id])

        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            print(f"ADB error: {e}")
            return None

    def list_targets(self) -> List[TargetApplication]:
        """List connected Android devices."""
        if not self.is_available():
            return []

        output = self._run_adb('devices', '-l')
        if not output:
            return []

        devices = []
        lines = output.split('\n')[1:]  # Skip header line

        for line in lines:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            device_id = parts[0]
            status = parts[1]

            if status != 'device':
                continue  # Skip unauthorized or offline devices

            # Parse device properties
            props = {}
            for part in parts[2:]:
                if ':' in part:
                    key, value = part.split(':', 1)
                    props[key] = value

            # Get device model
            model = props.get('model', device_id)
            product = props.get('product', '')

            # Get screen resolution
            resolution = self._get_device_resolution(device_id)

            devices.append(TargetApplication(
                id=device_id,
                title=f"{model} ({device_id})",
                process_name=product,
                bounds=(0, 0, resolution[0], resolution[1]) if resolution else (0, 0, 0, 0),
                extra={
                    'model': model,
                    'product': product,
                    'transport_id': props.get('transport_id', ''),
                }
            ))

        return devices

    def _get_device_resolution(self, device_id: str) -> Optional[tuple]:
        """Get device screen resolution."""
        output = self._run_adb('shell', 'wm', 'size', device_id=device_id)
        if output:
            # Parse "Physical size: 1080x2340"
            for line in output.split('\n'):
                if 'Physical size:' in line or 'Override size:' in line:
                    size_part = line.split(':')[1].strip()
                    try:
                        w, h = size_part.split('x')
                        return (int(w), int(h))
                    except (ValueError, IndexError):
                        pass
        return None

    def get_foreground_activity(self, device_id: str = None) -> Optional[Dict[str, str]]:
        """Get current foreground activity."""
        device = device_id or self._device_id
        if not device:
            return None

        # Try different methods based on Android version
        output = self._run_adb(
            'shell', 'dumpsys', 'activity', 'activities',
            device_id=device
        )

        if output:
            # Parse for focused activity
            for line in output.split('\n'):
                if 'mResumedActivity' in line or 'mFocusedActivity' in line:
                    # Extract package/activity
                    parts = line.split()
                    for part in parts:
                        if '/' in part and '.' in part:
                            pkg_activity = part.strip('{}')
                            if '/' in pkg_activity:
                                pkg, activity = pkg_activity.split('/', 1)
                                return {
                                    'package': pkg,
                                    'activity': activity,
                                    'full': pkg_activity
                                }

        return None

    def connect(self, config: PlatformConfig) -> bool:
        """Connect to Android device."""
        if not config.target:
            return False

        self._device_id = config.target.id
        self._config = config

        # Verify device is still connected
        devices = self.list_targets()
        for device in devices:
            if device.id == self._device_id:
                self._connected = True
                return True

        self._device_id = None
        self._config = None
        return False

    def disconnect(self) -> None:
        """Disconnect from device."""
        self._device_id = None
        self._config = None
        self._connected = False
        self._last_screenshot = None

    def capture_screenshot(self) -> Optional[bytes]:
        """Capture screenshot from Android device."""
        if not self._device_id:
            return None

        # Method 1: Direct screencap to stdout (fastest)
        screenshot = self._run_adb_bytes(
            'exec-out', 'screencap', '-p',
            device_id=self._device_id
        )

        if screenshot:
            # Fix line endings if needed (some ADB versions add \r\n)
            if b'\r\n' in screenshot[:100]:  # Check header area
                screenshot = screenshot.replace(b'\r\n', b'\n')

            self._last_screenshot = screenshot
            return screenshot

        # Method 2: Capture to file and pull (fallback)
        remote_path = '/sdcard/screenshot_temp.png'

        result = self._run_adb(
            'shell', 'screencap', '-p', remote_path,
            device_id=self._device_id
        )

        if result is not None:
            screenshot = self._run_adb_bytes(
                'exec-out', 'cat', remote_path,
                device_id=self._device_id
            )

            # Cleanup
            self._run_adb(
                'shell', 'rm', remote_path,
                device_id=self._device_id
            )

            if screenshot:
                self._last_screenshot = screenshot
                return screenshot

        return None

    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """Get detailed device information."""
        if not self._device_id:
            return None

        info = {}

        # Get Android version
        output = self._run_adb(
            'shell', 'getprop', 'ro.build.version.release',
            device_id=self._device_id
        )
        if output:
            info['android_version'] = output

        # Get SDK version
        output = self._run_adb(
            'shell', 'getprop', 'ro.build.version.sdk',
            device_id=self._device_id
        )
        if output:
            info['sdk_version'] = output

        # Get device model
        output = self._run_adb(
            'shell', 'getprop', 'ro.product.model',
            device_id=self._device_id
        )
        if output:
            info['model'] = output

        # Get manufacturer
        output = self._run_adb(
            'shell', 'getprop', 'ro.product.manufacturer',
            device_id=self._device_id
        )
        if output:
            info['manufacturer'] = output

        # Get screen resolution
        resolution = self._get_device_resolution(self._device_id)
        if resolution:
            info['resolution'] = f"{resolution[0]}x{resolution[1]}"

        # Get foreground activity
        activity = self.get_foreground_activity()
        if activity:
            info['foreground_activity'] = activity

        return info

    def tap(self, x: int, y: int) -> bool:
        """Send tap event to device."""
        if not self._device_id:
            return False

        result = self._run_adb(
            'shell', 'input', 'tap', str(x), str(y),
            device_id=self._device_id
        )
        return result is not None

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Send swipe event to device."""
        if not self._device_id:
            return False

        result = self._run_adb(
            'shell', 'input', 'swipe',
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
            device_id=self._device_id
        )
        return result is not None

    def input_text(self, text: str) -> bool:
        """Send text input to device."""
        if not self._device_id:
            return False

        # Escape special characters
        escaped = text.replace(' ', '%s').replace('&', '\\&')

        result = self._run_adb(
            'shell', 'input', 'text', escaped,
            device_id=self._device_id
        )
        return result is not None

    def press_key(self, keycode: str) -> bool:
        """Send key event to device."""
        if not self._device_id:
            return False

        result = self._run_adb(
            'shell', 'input', 'keyevent', keycode,
            device_id=self._device_id
        )
        return result is not None

    def press_back(self) -> bool:
        """Press back button."""
        return self.press_key('KEYCODE_BACK')

    def press_home(self) -> bool:
        """Press home button."""
        return self.press_key('KEYCODE_HOME')

    def press_menu(self) -> bool:
        """Press menu button."""
        return self.press_key('KEYCODE_MENU')
