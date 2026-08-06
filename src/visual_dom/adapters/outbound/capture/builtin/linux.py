"""Linux screen capture (mss)."""

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


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

    def describe_target(self) -> dict:
        """
        Active window title via xdotool, else xprop (X11). Wayland exposes no
        equivalent to unprivileged clients, so this returns {} there.
        """
        import shutil
        import subprocess
        try:
            if shutil.which("xdotool"):
                out = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                                     capture_output=True, timeout=5)
                title = out.stdout.decode(errors="replace").strip()
                if out.returncode == 0 and title:
                    return {"window_title": title}
            if shutil.which("xprop"):
                root = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                                      capture_output=True, timeout=5)
                text = root.stdout.decode(errors="replace")
                win = text.rsplit(" ", 1)[-1].strip() if "0x" in text else ""
                if win:
                    name = subprocess.run(["xprop", "-id", win, "WM_NAME"],
                                          capture_output=True, timeout=5)
                    line = name.stdout.decode(errors="replace")
                    if '"' in line:
                        return {"window_title": line.split('"', 1)[1].rsplit('"', 1)[0]}
        except Exception:
            pass
        return {}

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
