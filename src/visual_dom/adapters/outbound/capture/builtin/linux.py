"""Linux screen capture (mss)."""

import threading

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class LinuxCapture(CaptureStrategy):
    name = "linux"
    platform = "linux"
    description = "Full-screen grab on Linux/X11 via mss (needs a display)."

    def __init__(self, monitor: int = 1, window_title: str = None):
        self._monitor = monitor
        # window_title: default target for focus_target() (config: capture.window_title)
        self._window_title = window_title
        # One mss instance per thread: mss is not thread-safe and this strategy is
        # shared by the gRPC service's worker pool (see the Windows strategy).
        self._local = threading.local()
        self._instances = []
        self._lock = threading.Lock()

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

    def focus_target(self, title: str = None) -> bool:
        """Activate the SUT window via wmctrl/xdotool (X11 only) — ADR-021."""
        from visual_dom.adapters.outbound import x11_window
        wanted = title or self._window_title
        if not wanted:
            return False
        return x11_window.focus_window_by_title(wanted)

    def _sct(self):
        """This thread's mss instance, created on first use."""
        import mss
        got = getattr(self._local, "sct", None)
        if got is None:
            got = mss.mss()
            self._local.sct = got
            with self._lock:
                self._instances.append(got)
        return got

    def capture(self) -> np.ndarray:
        import cv2
        sct = self._sct()
        shot = sct.grab(sct.monitors[self._monitor])
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

    def close(self) -> None:
        with self._lock:
            instances, self._instances = self._instances, []
        for sct in instances:
            try:
                sct.close()
            except Exception:
                pass
        self._local = threading.local()
