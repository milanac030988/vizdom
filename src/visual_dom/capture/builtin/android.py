"""Android screen capture via ADB (`adb exec-out screencap -p`)."""

import shutil
import subprocess

import numpy as np

from ..base import CaptureStrategy


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
