"""Linux screen capture (mss)."""

import numpy as np

from ..base import CaptureStrategy


class LinuxCapture(CaptureStrategy):
    name = "linux"
    platform = "linux"
    description = "Full-screen grab on Linux/X11 via mss (needs a display)."

    def __init__(self, monitor: int = 1):
        self._monitor = monitor
        self._sct = None

    @classmethod
    def is_available(cls) -> bool:
        import os
        import sys
        if not sys.platform.startswith("linux"):
            return False
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False
        try:
            import mss  # noqa: F401
            return True
        except Exception:
            return False

    def capture(self) -> np.ndarray:
        import cv2
        import mss
        if self._sct is None:
            self._sct = mss.mss()
        shot = self._sct.grab(self._sct.monitors[self._monitor])
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
