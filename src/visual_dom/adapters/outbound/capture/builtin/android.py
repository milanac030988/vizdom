"""Android screen capture via ADB (`adb exec-out screencap -p`)."""

import shutil
import subprocess

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class AndroidCapture(CaptureStrategy):
    name = "android"
    platform = "android"
    description = "Screenshot from a connected Android device/emulator via adb."

    def __init__(self, serial: str = None, adb: str = "adb"):
        # serial: target a specific device when several are attached (-s <serial>)
        self._serial = serial
        self._adb = adb

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
