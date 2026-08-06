"""Windows screen capture (mss if available, else Pillow ImageGrab)."""

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class WindowsCapture(CaptureStrategy):
    name = "windows"
    platform = "windows"
    description = "Full-screen grab on Windows (mss, or Pillow ImageGrab fallback)."

    def __init__(self, monitor: int = 1):
        self._monitor = monitor
        self._sct = None

    @classmethod
    def is_available(cls) -> bool:
        import sys
        if not sys.platform.startswith("win"):
            return False
        try:
            import mss  # noqa: F401
            return True
        except Exception:
            try:
                from PIL import ImageGrab  # noqa: F401
                return True
            except Exception:
                return False

    def describe_target(self) -> dict:
        """
        Foreground window title + owning process, skipping OUR OWN process.

        A full-screen grab contains whatever is on screen, and at capture time the
        caller (Viewer/CLI) is usually itself the foreground window - so walk down
        the Z-order past our own windows to name the application actually under
        test. Windows-only; returns {} on any failure.
        """
        try:
            import ctypes
            import os
            from ctypes import wintypes
            user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
            GW_HWNDNEXT, my_pid = 2, os.getpid()

            def info(hwnd):
                if not hwnd or not user32.IsWindowVisible(hwnd):
                    return None
                n = user32.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return None
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.strip()
                if not title:
                    return None
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == my_pid:
                    return None
                proc = None
                h = kernel32.OpenProcess(0x1000, False, pid.value)
                if h:
                    try:
                        pbuf = ctypes.create_unicode_buffer(512)
                        size = wintypes.DWORD(512)
                        if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
                            proc = os.path.basename(pbuf.value)
                    finally:
                        kernel32.CloseHandle(h)
                return {"window_title": title, "process_name": proc}

            hwnd = user32.GetForegroundWindow()
            for _ in range(30):
                got = info(hwnd)
                if got:
                    return got
                hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT) if hwnd else None
                if not hwnd:
                    break
        except Exception:
            pass
        return {}

    def capture(self) -> np.ndarray:
        import cv2
        # Prefer mss (fast, multi-monitor); fall back to Pillow ImageGrab.
        try:
            import mss
            if self._sct is None:
                self._sct = mss.mss()
            mon = self._sct.monitors[self._monitor]
            shot = self._sct.grab(mon)
            arr = np.array(shot)  # BGRA
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        except Exception:
            from PIL import ImageGrab
            img = ImageGrab.grab()  # RGB
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
