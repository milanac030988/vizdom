"""Android screen capture via ADB (`adb exec-out screencap -p`)."""

import shutil
import subprocess
import time

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class AndroidCapture(CaptureStrategy):
    name = "android"
    platform = "android"
    description = "Screenshot from a connected Android device/emulator via adb."

    def __init__(self, serial: str = None, adb: str = "adb", activity: str = None):
        # serial: target a specific device when several are attached (-s <serial>)
        self._serial = serial
        self._adb = adb
        # activity: default target for focus_target(), "package/.Activity" or a
        # bare package name (config: capture.window_title)
        self._activity = activity

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("adb") is not None

    def describe_target(self) -> dict:
        """The resumed activity — Android's precise equivalent of a window title."""
        try:
            cmd = [self._adb]
            if self._serial:
                cmd += ["-s", self._serial]
            cmd += ["shell", "dumpsys", "activity", "activities"]
            out = subprocess.run(cmd, capture_output=True, timeout=10)
            if out.returncode != 0:
                return {}
            text = out.stdout.decode(errors="replace")
            for line in text.splitlines():
                if "mResumedActivity" in line or "mFocusedActivity" in line:
                    for part in line.split():
                        token = part.strip("{}")
                        if "/" in token and "." in token:
                            package, _, activity = token.partition("/")
                            return {
                                "window_title": token,   # package/.Activity
                                "process_name": package,
                                "activity": token,
                                "device_serial": self._serial,
                            }
            return {"device_serial": self._serial} if self._serial else {}
        except Exception:
            return {}

    def focus_target(self, title: str = None) -> bool:
        """
        Bring an app to the foreground with `am start` (ADR-021).

        ``title`` is a component (``com.example/.MainActivity``) or a bare package
        name, in which case the launcher intent is used. Success is verified
        against the resumed activity rather than adb's exit code — `am start`
        happily reports success for an activity that then finishes.
        """
        wanted = (title or self._activity or "").strip()
        if not wanted:
            return False
        try:
            base = [self._adb] + (["-s", self._serial] if self._serial else [])
            if "/" in wanted:
                cmd = base + ["shell", "am", "start", "-n", wanted]
            else:
                cmd = base + ["shell", "monkey", "-p", wanted,
                              "-c", "android.intent.category.LAUNCHER", "1"]
            subprocess.run(cmd, capture_output=True, timeout=15)
            time.sleep(0.6)                      # app launch is asynchronous
            resumed = (self.describe_target().get("activity") or "")
            package = wanted.split("/", 1)[0]
            return package.lower() in resumed.lower()
        except Exception:
            return False

    def capture(self) -> np.ndarray:
        import cv2
        cmd = [self._adb]
        if self._serial:
            cmd += ["-s", self._serial]
        cmd += ["exec-out", "screencap", "-p"]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError(f"adb screencap failed: {result.stderr.decode(errors='replace')[:200]}")
        buf = np.frombuffer(result.stdout, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)  # PNG bytes -> BGR
        if img is None:
            raise RuntimeError("adb screencap returned undecodable data")
        return img
