"""Android input actuation via ADB `input` (tap / text / keyevent / swipe).

Relocated from visual_gui_library/adapters/android.py (ADR-019). Normalized
coordinates denormalize against the device's input resolution (`wm size`), which
may differ from the captured screenshot buffer.
"""

import shutil
import subprocess
from typing import Optional, Tuple

from ..base import ActuatorStrategy


class AndroidActuator(ActuatorStrategy):
    name = "android"
    platform = "android"
    description = "Touch/key input on a connected Android device/emulator via adb."

    _KEYCODES = {
        "enter": "66", "back": "4", "home": "3", "tab": "61",
        "delete": "67", "backspace": "67", "space": "62", "escape": "111",
    }

    def __init__(self, serial: Optional[str] = None, adb: str = "adb"):
        self._serial = serial
        self._adb = adb
        self._size = None  # cached (w, h) from `wm size`

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("adb") is not None

    def _shell(self, *args) -> subprocess.CompletedProcess:
        cmd = [self._adb]
        if self._serial:
            cmd += ["-s", self._serial]
        cmd += ["shell", *args]
        return subprocess.run(cmd, capture_output=True, text=True)

    def device_size(self, image_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        if self._size is not None:
            return self._size
        # `wm size` -> "Physical size: 1080x2340"
        try:
            out = self._shell("wm", "size").stdout
            for token in out.replace("Override size", "Physical size").split():
                if "x" in token and token.replace("x", "").isdigit():
                    w, h = token.split("x")
                    self._size = (int(w), int(h))
                    return self._size
        except Exception:
            pass
        if image_size is not None:  # fall back to the source image resolution
            self._size = (int(image_size[0]), int(image_size[1]))
            return self._size
        raise RuntimeError("could not determine Android device size (adb `wm size`)")

    def tap(self, nx, ny, image_size=None, click_type="single"):
        x, y = self._to_device(nx, ny, image_size)
        if click_type == "double":
            self._shell("input", "tap", str(x), str(y))
            self._shell("input", "tap", str(x), str(y))
        elif click_type == "long":
            self._shell("input", "swipe", str(x), str(y), str(x), str(y), "1000")
        else:
            self._shell("input", "tap", str(x), str(y))

    def type_text(self, text: str) -> None:
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        self._shell("input", "text", escaped)

    def press_key(self, key: str) -> None:
        keycode = self._KEYCODES.get(key.lower(), key)
        self._shell("input", "keyevent", keycode)

    def scroll(self, nx, ny, direction="down", amount=1, image_size=None):
        x, y = self._to_device(nx, ny, image_size)
        dist = 300 * amount
        if direction == "down":
            self._shell("input", "swipe", str(x), str(y), str(x), str(y - dist), "300")
        elif direction == "up":
            self._shell("input", "swipe", str(x), str(y), str(x), str(y + dist), "300")
        elif direction == "left":
            self._shell("input", "swipe", str(x), str(y), str(x + dist), str(y), "300")
        elif direction == "right":
            self._shell("input", "swipe", str(x), str(y), str(x - dist), str(y), "300")

    def swipe(self, nx1, ny1, nx2, ny2, image_size=None, duration=0.3):
        x1, y1 = self._to_device(nx1, ny1, image_size)
        x2, y2 = self._to_device(nx2, ny2, image_size)
        self._shell("input", "swipe", str(x1), str(y1), str(x2), str(y2),
                    str(int(duration * 1000)))
