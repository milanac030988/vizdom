"""Desktop input actuation via pyautogui (Windows / macOS / Linux).

Relocated from visual_gui_library/adapters/desktop.py (ADR-019). The screenshot
that produced the DOM is a grab of this same screen, so normalized coordinates
denormalize against the live screen size (image space == screen space).
"""

from typing import Optional, Tuple

from visual_dom.core.ports.outbound.actuator_port import ActuatorStrategy


class DesktopActuator(ActuatorStrategy):
    name = "desktop"
    platform = "any"
    description = "Mouse/keyboard input on Windows/macOS/Linux via pyautogui."

    def __init__(self, failsafe: bool = True):
        # failsafe: slam the mouse to a screen corner to abort (pyautogui feature)
        self.failsafe = failsafe
        self._pyautogui = None

    @classmethod
    def is_available(cls) -> bool:
        try:
            import pyautogui  # noqa: F401
            return True
        except Exception:
            return False

    def _pg(self):
        if self._pyautogui is None:
            import pyautogui
            pyautogui.FAILSAFE = self.failsafe
            self._pyautogui = pyautogui
        return self._pyautogui

    def device_size(self, image_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        w, h = self._pg().size()
        return int(w), int(h)

    def tap(self, nx, ny, image_size=None, click_type="single"):
        pg = self._pg()
        x, y = self._to_device(nx, ny, image_size)
        if click_type == "double":
            pg.doubleClick(x, y)
        elif click_type == "right":
            pg.rightClick(x, y)
        elif click_type == "long":
            pg.mouseDown(x, y)
            pg.sleep(1.0)
            pg.mouseUp(x, y)
        else:
            pg.click(x, y)

    def type_text(self, text: str) -> None:
        self._pg().typewrite(text, interval=0.02)

    def press_key(self, key: str) -> None:
        pg = self._pg()
        if "+" in key:
            pg.hotkey(*key.split("+"))
        else:
            pg.press(key)

    def scroll(self, nx, ny, direction="down", amount=1, image_size=None):
        pg = self._pg()
        x, y = self._to_device(nx, ny, image_size)
        pg.moveTo(x, y)
        clicks = amount * 3  # ~3 wheel clicks per "page"
        if direction == "up":
            pg.scroll(clicks)
        elif direction == "down":
            pg.scroll(-clicks)
        elif direction == "left":
            pg.hscroll(-clicks)
        elif direction == "right":
            pg.hscroll(clicks)

    def swipe(self, nx1, ny1, nx2, ny2, image_size=None, duration=0.3):
        pg = self._pg()
        x1, y1 = self._to_device(nx1, ny1, image_size)
        x2, y2 = self._to_device(nx2, ny2, image_size)
        pg.moveTo(x1, y1)
        pg.dragTo(x2, y2, duration=duration)
