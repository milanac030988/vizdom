"""
Windows Platform Handler - WinAPI-based window capture.

Uses ctypes to interact with Windows API for:
- Listing visible windows
- Capturing window screenshots
- Getting window information
"""

from typing import Optional, List, Tuple
import sys
import io

from .platform_manager import (
    PlatformHandler, PlatformType, PlatformConfig, TargetApplication
)

# Check if running on Windows
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    # Windows API constants
    GWL_STYLE = -16
    WS_VISIBLE = 0x10000000
    WS_MINIMIZE = 0x20000000
    SRCCOPY = 0x00CC0020
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    # Load Windows DLLs
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32

    # Function prototypes
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetForegroundWindow.argtypes = []
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

    # Additional functions for bringing window to front
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p]
    user32.SetActiveWindow.argtypes = [wintypes.HWND]
    user32.SetActiveWindow.restype = wintypes.HWND
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    # Bitmap info header
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', wintypes.DWORD),
            ('biWidth', wintypes.LONG),
            ('biHeight', wintypes.LONG),
            ('biPlanes', wintypes.WORD),
            ('biBitCount', wintypes.WORD),
            ('biCompression', wintypes.DWORD),
            ('biSizeImage', wintypes.DWORD),
            ('biXPelsPerMeter', wintypes.LONG),
            ('biYPelsPerMeter', wintypes.LONG),
            ('biClrUsed', wintypes.DWORD),
            ('biClrImportant', wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ('bmiHeader', BITMAPINFOHEADER),
            ('bmiColors', wintypes.DWORD * 3),
        ]


class WindowsPlatformHandler(PlatformHandler):
    """
    Windows platform handler using WinAPI.

    Features:
    - List all visible windows
    - Capture specific window screenshots
    - Get window process information
    """

    PLATFORM_TYPE = PlatformType.WINDOWS
    PLATFORM_NAME = "Windows Desktop"
    PLATFORM_DESCRIPTION = "Capture Windows desktop applications"

    def __init__(self):
        super().__init__()
        self._target_hwnd: Optional[int] = None

    def is_available(self) -> bool:
        """Check if Windows API is available."""
        return IS_WINDOWS

    def list_targets(self) -> List[TargetApplication]:
        """List all visible windows."""
        if not IS_WINDOWS:
            return []

        windows = []

        def enum_callback(hwnd, _):
            # Check if window is visible
            if not user32.IsWindowVisible(hwnd):
                return True

            # Get window style
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            if not (style & WS_VISIBLE):
                return True

            # Skip minimized windows (optional, can be included)
            # if style & WS_MINIMIZE:
            #     return True

            # Get window title
            length = user32.GetWindowTextLengthW(hwnd) + 1
            title_buffer = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, title_buffer, length)
            title = title_buffer.value

            # Skip windows without title
            if not title or title.strip() == "":
                return True

            # Skip certain system windows
            skip_titles = [
                "Program Manager",
                "Windows Input Experience",
                "Microsoft Text Input Application",
                "Settings",
            ]
            if title in skip_titles:
                return True

            # Get window rect
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

            # Skip zero-size windows
            if bounds[2] <= 0 or bounds[3] <= 0:
                return True

            # Get process ID
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            # Get process name
            process_name = self._get_process_name(pid.value)

            windows.append(TargetApplication(
                id=str(hwnd),
                title=title,
                process_name=process_name,
                pid=pid.value,
                bounds=bounds
            ))

            return True

        # Enumerate windows
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        # Sort by title
        windows.sort(key=lambda w: w.title.lower())

        return windows

    def _get_process_name(self, pid: int) -> str:
        """Get process name from PID."""
        if not IS_WINDOWS:
            return ""

        try:
            # Open process
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010

            handle = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                False,
                pid
            )

            if not handle:
                return ""

            try:
                # Get process name
                psapi = ctypes.windll.psapi
                name_buffer = ctypes.create_unicode_buffer(260)

                if psapi.GetModuleBaseNameW(handle, None, name_buffer, 260):
                    return name_buffer.value

                return ""
            finally:
                kernel32.CloseHandle(handle)

        except Exception:
            return ""

    def connect(self, config: PlatformConfig) -> bool:
        """Connect to target window."""
        if not config.target:
            return False

        try:
            self._target_hwnd = int(config.target.id)
            self._config = config
            self._connected = True
            return True
        except (ValueError, TypeError):
            return False

    def disconnect(self) -> None:
        """Disconnect from target."""
        self._target_hwnd = None
        self._config = None
        self._connected = False
        self._last_screenshot = None

    def _get_client_rect_on_screen(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """
        Get the client area rectangle in screen coordinates.

        Uses ClientToScreen to get the exact client area, excluding
        window frame, title bar, and shadow borders.

        Returns:
            (x, y, width, height) or None
        """
        try:
            # Get client area size
            client_rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(client_rect))
            client_w = client_rect.right - client_rect.left
            client_h = client_rect.bottom - client_rect.top

            if client_w <= 0 or client_h <= 0:
                return None

            # Convert client (0,0) to screen coordinates
            point = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(point))

            return (point.x, point.y, client_w, client_h)
        except Exception:
            return None

    def capture_screenshot(self) -> Optional[bytes]:
        """Capture screenshot of target window (client area only, no frame/shadow)."""
        if not IS_WINDOWS or not self._target_hwnd:
            return None

        try:
            hwnd = self._target_hwnd

            # First, bring window to foreground for better capture
            self.bring_to_front()
            import time
            time.sleep(0.1)  # Brief delay to let window render

            # Try client area capture first (excludes frame and shadow)
            client = self._get_client_rect_on_screen(hwnd)
            if client:
                x, y, width, height = client
                screenshot = self._capture_from_desktop(x, y, width, height)
                if screenshot:
                    return screenshot

            # Fallback: full window rect (includes frame)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            width = rect.right - rect.left
            height = rect.bottom - rect.top

            if width <= 0 or height <= 0:
                return None

            screenshot = self._capture_from_desktop(rect.left, rect.top, width, height)
            if screenshot:
                return screenshot

            # Method 2: Fallback to window DC
            return self._capture_from_window_dc(hwnd, width, height)

        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _capture_from_desktop(self, x: int, y: int, width: int, height: int) -> Optional[bytes]:
        """Capture region from desktop DC (works better with DWM)."""
        try:
            # Get desktop DC
            desktop_dc = user32.GetDC(None)  # None = entire screen
            if not desktop_dc:
                return None

            try:
                # Create compatible DC and bitmap
                mfc_dc = gdi32.CreateCompatibleDC(desktop_dc)
                bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, width, height)
                old_bitmap = gdi32.SelectObject(mfc_dc, bitmap)

                # Copy from desktop at window position
                gdi32.BitBlt(mfc_dc, 0, 0, width, height, desktop_dc, x, y, SRCCOPY)

                # Get bitmap data
                bmp_info = BITMAPINFO()
                bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmp_info.bmiHeader.biWidth = width
                bmp_info.bmiHeader.biHeight = -height  # Top-down
                bmp_info.bmiHeader.biPlanes = 1
                bmp_info.bmiHeader.biBitCount = 32
                bmp_info.bmiHeader.biCompression = BI_RGB

                buffer_size = width * height * 4
                buffer = ctypes.create_string_buffer(buffer_size)

                gdi32.GetDIBits(
                    mfc_dc, bitmap, 0, height,
                    buffer, ctypes.byref(bmp_info), DIB_RGB_COLORS
                )

                # Convert to PNG
                return self._buffer_to_png(buffer.raw, width, height)

            finally:
                gdi32.SelectObject(mfc_dc, old_bitmap)
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(mfc_dc)
                user32.ReleaseDC(None, desktop_dc)

        except Exception as e:
            print(f"Desktop capture failed: {e}")
            return None

    def _capture_from_window_dc(self, hwnd: int, width: int, height: int) -> Optional[bytes]:
        """Capture from window DC using PrintWindow."""
        try:
            hwnd_dc = user32.GetWindowDC(hwnd)
            if not hwnd_dc:
                return None

            try:
                mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
                bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
                old_bitmap = gdi32.SelectObject(mfc_dc, bitmap)

                # Try PrintWindow with different flags
                PW_CLIENTONLY = 0x00000001
                PW_RENDERFULLCONTENT = 0x00000002

                result = user32.PrintWindow(hwnd, mfc_dc, PW_RENDERFULLCONTENT)
                if not result:
                    result = user32.PrintWindow(hwnd, mfc_dc, 0)
                if not result:
                    # Final fallback: BitBlt
                    gdi32.BitBlt(mfc_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)

                # Get bitmap data
                bmp_info = BITMAPINFO()
                bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmp_info.bmiHeader.biWidth = width
                bmp_info.bmiHeader.biHeight = -height
                bmp_info.bmiHeader.biPlanes = 1
                bmp_info.bmiHeader.biBitCount = 32
                bmp_info.bmiHeader.biCompression = BI_RGB

                buffer_size = width * height * 4
                buffer = ctypes.create_string_buffer(buffer_size)

                gdi32.GetDIBits(
                    mfc_dc, bitmap, 0, height,
                    buffer, ctypes.byref(bmp_info), DIB_RGB_COLORS
                )

                return self._buffer_to_png(buffer.raw, width, height)

            finally:
                gdi32.SelectObject(mfc_dc, old_bitmap)
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(mfc_dc)
                user32.ReleaseDC(hwnd, hwnd_dc)

        except Exception as e:
            print(f"Window DC capture failed: {e}")
            return None

    def _buffer_to_png(self, buffer: bytes, width: int, height: int) -> Optional[bytes]:
        """Convert raw BGRA buffer to PNG bytes."""
        try:
            from PIL import Image

            img = Image.frombytes('RGBA', (width, height), buffer, 'raw', 'BGRA')
            img = img.convert('RGB')

            output = io.BytesIO()
            img.save(output, format='PNG')
            self._last_screenshot = output.getvalue()
            return self._last_screenshot

        except ImportError:
            print("PIL not available for image conversion")
            return None

    def bring_to_front(self) -> bool:
        """
        Bring the target window to the foreground.

        Delegates to the shared adapter helper (ADR-021), which is where this
        routine now lives so the capture strategies, the actuator strategies and
        this handler all use ONE implementation. Unlike the previous local copy,
        the result is verified: False means the window really is not foreground
        (Windows can refuse the raise), not merely that no exception was thrown.
        """
        if not IS_WINDOWS or not self._target_hwnd:
            return False
        from visual_dom.adapters.outbound.win32_window import bring_to_front
        return bring_to_front(self._target_hwnd)

    def refresh_target_info(self) -> Optional[TargetApplication]:
        """Refresh target window information."""
        if not IS_WINDOWS or not self._target_hwnd:
            return None

        hwnd = self._target_hwnd

        # Get updated title
        length = user32.GetWindowTextLengthW(hwnd) + 1
        title_buffer = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, title_buffer, length)

        # Get updated rect
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        # Get process info
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        return TargetApplication(
            id=str(hwnd),
            title=title_buffer.value,
            process_name=self._get_process_name(pid.value),
            pid=pid.value,
            bounds=(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        )
