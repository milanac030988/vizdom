"""Desktop input actuation via pyautogui (Windows / macOS / Linux).

Relocated from visual_gui_library/adapters/desktop.py (ADR-019). The screenshot
that produced the DOM is a grab of this same screen, so normalized coordinates
denormalize against the live screen size (image space == screen space).
"""

from typing import Optional, Tuple

from visual_dom.core.ports.outbound.actuator_port import ActuatorStrategy
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


class DesktopActuator(ActuatorStrategy):
    name = "desktop"
    platform = "any"
    description = "Mouse/keyboard input on Windows/macOS/Linux via pyautogui."

    def __init__(self, failsafe: bool = True, window_title: Optional[str] = None):
        # failsafe: slam the mouse to a screen corner to abort (pyautogui feature)
        self.failsafe = failsafe
        # window_title: default target for focus_target() (config: actuator.window_title)
        self._window_title = window_title
        self._pyautogui = None
        self._virtual = None      # cached virtual-screen rect (multi-monitor)

    @classmethod
    def is_available(cls) -> bool:
        try:
            import pyautogui  # noqa: F401
            return True
        except Exception:
            return False

    def _pg(self):
        if self._pyautogui is None:
            import sys
            if sys.platform.startswith("win"):
                # MUST happen before pyautogui is imported: it calls
                # SetProcessDPIAware() itself, and DPI awareness cannot be changed
                # once set. Losing that race makes Windows report a *scaled*
                # desktop - non-uniformly, when monitors have different scaling -
                # and every coordinate we hand to pyautogui is then misread.
                from visual_dom.adapters.outbound.win32_window import (
                    ensure_process_dpi_aware, warn_if_dpi_context_mismatched)
                ensure_process_dpi_aware()
                warn_if_dpi_context_mismatched()
            import pyautogui
            pyautogui.FAILSAFE = self.failsafe
            self._pyautogui = pyautogui
        return self._pyautogui

    def _virtual_screen(self) -> Optional[Tuple[int, int, int, int]]:
        """
        (left, top, width, height) of the **virtual screen** — the union of all
        monitors — on Windows, else None.

        pyautogui reports only the primary monitor, so with it alone a window on a
        second display (which can start at a negative x) is unaddressable. Cached
        after the first query; a monitor being re-arranged mid-run is not supported.
        """
        import sys
        if not sys.platform.startswith("win"):
            return None
        if self._virtual is not None:
            return self._virtual
        # Same helper the capture side uses, so both ports share one space.
        from visual_dom.adapters.outbound.win32_window import virtual_screen_rect
        rect = virtual_screen_rect()
        if not rect:
            return None
        self._virtual = rect
        if rect[:2] != (0, 0):
            log.info("Multi-monitor desktop: virtual screen is %dx%d at (%d, %d) "
                     "- coordinates are mapped over all displays",
                     rect[2], rect[3], rect[0], rect[1])
        return self._virtual

    def device_size(self, image_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        virtual = self._virtual_screen()
        if virtual:
            return virtual[2], virtual[3]
        w, h = self._pg().size()
        return int(w), int(h)

    def device_origin(self) -> Tuple[int, int]:
        virtual = self._virtual_screen()
        return (virtual[0], virtual[1]) if virtual else (0, 0)

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

    def focus_target(self, title: Optional[str] = None) -> bool:
        """
        Raise the SUT window so clicks and typing reach it (ADR-021).

        pyautogui drives the *global* pointer and keyboard: a tap lands on
        whatever window is at that coordinate and `type_text` goes to whatever
        holds keyboard focus. Focus handling is therefore a correctness step, not
        cosmetic. Dispatches to the platform helper shared with the capture side.
        """
        import sys
        wanted = title or self._window_title
        if not wanted:
            return False
        if sys.platform.startswith("win"):
            from visual_dom.adapters.outbound import win32_window
            return win32_window.focus_window_by_title(wanted)
        if sys.platform.startswith("linux"):
            from visual_dom.adapters.outbound import x11_window
            return x11_window.focus_window_by_title(wanted)
        return False   # macOS would need AppleScript/Quartz — not implemented

    def swipe(self, nx1, ny1, nx2, ny2, image_size=None, duration=0.3):
        pg = self._pg()
        x1, y1 = self._to_device(nx1, ny1, image_size)
        x2, y2 = self._to_device(nx2, ny2, image_size)
        pg.moveTo(x1, y1)
        pg.dragTo(x2, y2, duration=duration)
