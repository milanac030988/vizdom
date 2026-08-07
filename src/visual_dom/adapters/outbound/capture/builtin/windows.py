"""Windows screen capture (mss if available, else Pillow ImageGrab)."""

import threading

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


class WindowsCapture(CaptureStrategy):
    name = "windows"
    platform = "windows"
    description = "Full-screen grab on Windows (mss, or Pillow ImageGrab fallback)."

    def __init__(self, monitor: int = 1, window_title: str = None):
        self._monitor = monitor
        # window_title: default target for focus_target() (config: capture.window_title)
        self._window_title = window_title
        # mss is NOT thread-safe (it keeps per-thread GDI handles in a
        # thread-local), and this strategy is shared by the gRPC service's worker
        # pool - one instance per thread, or a request on a second thread dies with
        # "'_thread._local' object has no attribute 'srcdc'".
        self._local = threading.local()
        self._instances = []            # every instance created, so close() frees them
        self._lock = threading.Lock()

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

    def frame_geometry(self):
        """
        Geometry of a plain `capture()`: the grabbed monitor's origin, and the
        **virtual desktop** as the coordinate space — the same space the desktop
        actuator uses, so a click computed on this frame lands on the right monitor.
        """
        from visual_dom.adapters.outbound import win32_window as w
        try:
            mons = self._monitors()
            idx = max(1, int(self._monitor)) - 1
            if idx >= len(mons):
                return None
            mon = mons[idx]
            virtual = w.virtual_screen_rect()
            if not virtual:
                return None
            return ((mon["left"], mon["top"]),
                    (virtual[0], virtual[1]), (virtual[2], virtual[3]))
        except Exception:
            return None

    def capture_window(self, title: str = None):
        """
        Capture only the target window's client area (ADR-021).

        Raises the window first and *requires* confirmation: a region grab reads the
        desktop, so cropping an occluded window would silently return the pixels of
        whatever covers it. Without verified focus this returns None so the caller
        falls back to a full-screen grab rather than trusting a wrong crop.

        The returned frame carries its `origin` and the full `device_size`, so
        coordinates computed on the crop can still be mapped back to the screen.
        """
        from visual_dom.core.ports.outbound.capture_port import CaptureFrame
        from visual_dom.adapters.outbound import win32_window as w

        wanted = title or self._window_title
        if not wanted:
            return None

        # Do this FIRST: window rectangles and the screenshot must be in the same
        # (physical) pixel space, or the crop is offset on a scaled display.
        w.ensure_process_dpi_aware()

        hwnd = w.find_window(wanted)
        if hwnd is None:
            return None
        if not w.bring_to_front(hwnd):
            log.warning("Not capturing %r as a window: could not confirm it is in "
                        "front, and a crop would show whatever covers it", wanted)
            return None

        rect = w.client_rect_on_screen(hwnd)
        if not rect:
            log.warning("Could not read the client rectangle of %r (minimised?)", wanted)
            return None

        # The window may live on any monitor - including one at a negative
        # coordinate, left of the primary. Grab THAT monitor, not monitor 1.
        mon = self._monitor_for_rect(rect)
        if mon is None:
            log.warning("Window %r is not on any monitor (rect=%s)", wanted, rect)
            return None
        frame = self._grab_monitor(mon)
        fh, fw = frame.shape[:2]

        # Window rects come from this process's DPI context; the screenshot is in
        # physical pixels. Scale using the monitor's own logical/physical ratio.
        sx = fw / float(mon["width"])
        sy = fh / float(mon["height"])
        x, y, cw, ch = rect
        # to monitor-relative, then to captured pixels
        rx, ry = (x - mon["left"]) * sx, (y - mon["top"]) * sy
        rw, rh = cw * sx, ch * sy

        x0, y0 = max(0, int(round(rx))), max(0, int(round(ry)))
        x1 = min(fw, int(round(rx + rw)))
        y1 = min(fh, int(round(ry + rh)))
        if x1 - x0 < 2 or y1 - y0 < 2:
            log.warning("Window %r has no visible area on its monitor", wanted)
            return None
        if (x0, y0) != (int(round(rx)), int(round(ry))) or (x1, y1) != (
                int(round(rx + rw)), int(round(ry + rh))):
            log.info("Window %r extends past the monitor edge; captured the visible part",
                     wanted)

        crop = frame[y0:y1, x0:x1].copy()
        # Report geometry in ABSOLUTE screen coordinates so the caller can map back.
        origin = (mon["left"] + int(round(x0 / sx)), mon["top"] + int(round(y0 / sy)))

        # The coordinate space is the VIRTUAL SCREEN, not the monitor we grabbed
        # from: the actuator normalizes against the whole desktop, and the two must
        # agree or a click on a secondary display lands on the wrong monitor.
        virtual = w.virtual_screen_rect() or (0, 0, fw, fh)
        log.info("Captured window %r: %dx%d at screen origin %s (grabbed monitor "
                 "%dx%d at (%d, %d); coordinate space %dx%d at (%d, %d))",
                 wanted, x1 - x0, y1 - y0, origin,
                 mon["width"], mon["height"], mon["left"], mon["top"],
                 virtual[2], virtual[3], virtual[0], virtual[1])
        return CaptureFrame(image=crop, origin=origin,
                            device_size=(virtual[2], virtual[3]),
                            device_origin=(virtual[0], virtual[1]),
                            window_title=wanted)

    # --- monitor helpers (multi-display support) ------------------------------

    def _monitors(self):
        """mss monitor descriptors, excluding index 0 (the virtual union)."""
        try:
            return list(self._sct().monitors[1:])
        except Exception:
            return []

    def _monitor_for_rect(self, rect):
        """
        The monitor a window rectangle sits on: the one it overlaps most.

        A window straddling two displays is captured on its dominant monitor and
        clipped, which is the honest outcome - stitching the virtual screen would
        make every element's coordinates depend on the whole desktop layout.
        """
        x, y, w_, h_ = rect
        best, best_area = None, 0
        for mon in self._monitors():
            ox = max(0, min(x + w_, mon["left"] + mon["width"]) - max(x, mon["left"]))
            oy = max(0, min(y + h_, mon["top"] + mon["height"]) - max(y, mon["top"]))
            area = ox * oy
            if area > best_area:
                best, best_area = mon, area
        return best

    def _grab_monitor(self, mon):
        """One monitor as a BGR frame."""
        import cv2
        shot = self._sct().grab(mon)
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

    def focus_target(self, title: str = None) -> bool:
        """
        Raise the application under test so the grab photographs IT (ADR-021).

        Falls back to the configured ``window_title`` when no title is given; with
        neither there is nothing to identify the target, so report False rather
        than raising an arbitrary window.
        """
        from visual_dom.adapters.outbound import win32_window
        wanted = title or self._window_title
        if not wanted:
            return False
        return win32_window.focus_window_by_title(wanted)

    def capture(self) -> np.ndarray:
        import cv2
        # Prefer mss (fast, multi-monitor); fall back to Pillow ImageGrab.
        try:
            sct = self._sct()
            mon = sct.monitors[self._monitor]
            shot = sct.grab(mon)
            arr = np.array(shot)  # BGRA
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        except Exception:
            from PIL import ImageGrab
            img = ImageGrab.grab()  # RGB
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def close(self) -> None:
        with self._lock:
            instances, self._instances = self._instances, []
        for sct in instances:
            try:
                sct.close()
            except Exception:
                pass
        self._local = threading.local()
