"""
Visual action keywords (click, type, scroll).
"""

import time
from typing import Optional
from robot.api.deco import keyword


class ActionKeywords:
    """Keywords for visual GUI interactions."""

    def __init__(self, platform: str = "desktop", click_delay: float = 0.1, **kwargs):
        self.platform = platform
        self.click_delay = click_delay
        self._adapter = None

    def _get_adapter(self):
        """Get platform adapter for executing actions."""
        if self._adapter is not None:
            return self._adapter

        if self.platform == "android":
            from ..adapters.android import AndroidAdapter
            self._adapter = AndroidAdapter()
        else:
            from ..adapters.desktop import DesktopAdapter
            self._adapter = DesktopAdapter()

        return self._adapter

    def _find_element(self, locator: str) -> dict:
        """Find element using locator. Must be overridden by main class."""
        # This will be provided by CaptureKeywords.get_visual_element
        return self.get_visual_element(locator)

    def _get_click_point(self, element: dict) -> tuple:
        """Get click coordinates from element."""
        center = element.get("center")
        if center:
            return tuple(center)
        # Fallback to bounds center
        bounds = element.get("bounds", [0, 0, 0, 0])
        return (
            (bounds[0] + bounds[2]) // 2,
            (bounds[1] + bounds[3]) // 2
        )

    @keyword("Click Visual")
    def click_visual(
        self,
        locator: str,
        click_type: str = "single"
    ) -> None:
        """
        Click on a visual element.

        Args:
            locator: Element locator string
            click_type: Click type (single, double, right)

        Example:
            | Click Visual | text=Login |
            | Click Visual | hint=Email | click_type=double |
        """
        element = self._find_element(locator)
        x, y = self._get_click_point(element)

        adapter = self._get_adapter()
        adapter.click(x, y, click_type=click_type)

        time.sleep(self.click_delay)

    @keyword("Click At Coordinates")
    def click_at_coordinates(
        self,
        x: int,
        y: int,
        click_type: str = "single"
    ) -> None:
        """
        Click at specific screen coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            click_type: Click type (single, double, right)

        Example:
            | Click At Coordinates | 100 | 200 |
            | Click At Coordinates | 100 | 200 | click_type=right |
        """
        adapter = self._get_adapter()
        adapter.click(int(x), int(y), click_type=click_type)
        time.sleep(self.click_delay)

    @keyword("Type Text Visual")
    def type_text_visual(
        self,
        locator: str,
        text: str,
        clear_first: bool = False
    ) -> None:
        """
        Type text into a visual element.

        Args:
            locator: Element locator string
            text: Text to type
            clear_first: Clear existing text before typing

        Example:
            | Type Text Visual | hint=Email | user@example.com |
            | Type Text Visual | hint=Password | secret | clear_first=True |
        """
        # Click element first to focus
        self.click_visual(locator)

        adapter = self._get_adapter()

        if clear_first:
            adapter.clear_text()
            time.sleep(0.05)

        adapter.type_text(text)

    @keyword("Type Text")
    def type_text(self, text: str) -> None:
        """
        Type text at current cursor position.

        Args:
            text: Text to type

        Example:
            | Type Text | Hello World |
        """
        adapter = self._get_adapter()
        adapter.type_text(text)

    @keyword("Press Key")
    def press_key(self, key: str) -> None:
        """
        Press a keyboard key or key combination.

        Args:
            key: Key name (enter, tab, escape) or combination (ctrl+a, alt+f4)

        Example:
            | Press Key | enter |
            | Press Key | ctrl+a |
            | Press Key | alt+f4 |
        """
        adapter = self._get_adapter()
        adapter.press_key(key)

    @keyword("Clear Text Visual")
    def clear_text_visual(self, locator: str) -> None:
        """
        Clear text from a visual input element.

        Args:
            locator: Element locator string

        Example:
            | Clear Text Visual | hint=Search |
        """
        # Click to focus
        self.click_visual(locator)

        adapter = self._get_adapter()
        adapter.clear_text()

    @keyword("Scroll Visual")
    def scroll_visual(
        self,
        locator: Optional[str] = None,
        direction: str = "down",
        amount: int = 1
    ) -> None:
        """
        Scroll within a visual element or the screen.

        Args:
            locator: Element locator (scrolls at screen center if None)
            direction: Scroll direction (up, down, left, right)
            amount: Scroll amount (1 = one "page")

        Example:
            | Scroll Visual | direction=down |
            | Scroll Visual | locator=text=ListView | direction=up | amount=2 |
        """
        adapter = self._get_adapter()

        if locator:
            element = self._find_element(locator)
            x, y = self._get_click_point(element)
        else:
            # Scroll at screen center
            screenshot = adapter.capture_screen()
            h, w = screenshot.shape[:2]
            x, y = w // 2, h // 2

        adapter.scroll(x, y, direction=direction, amount=int(amount))

    @keyword("Wait And Click Visual")
    def wait_and_click_visual(
        self,
        locator: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        click_type: str = "single"
    ) -> None:
        """
        Wait for element to appear then click it.

        Args:
            locator: Element locator string
            timeout: Maximum wait time in seconds
            interval: Check interval in seconds
            click_type: Click type (single, double, right)

        Example:
            | Wait And Click Visual | text=Submit | timeout=5 |
        """
        start_time = time.time()

        while True:
            try:
                # Refresh DOM
                self.dump_visual_dom()
                element = self._find_element(locator)
                if element:
                    x, y = self._get_click_point(element)
                    adapter = self._get_adapter()
                    adapter.click(x, y, click_type=click_type)
                    time.sleep(self.click_delay)
                    return
            except (ValueError, RuntimeError):
                pass

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Element not found within {timeout}s: {locator}")

            time.sleep(interval)

    @keyword("Drag And Drop Visual")
    def drag_and_drop_visual(
        self,
        source_locator: str,
        target_locator: str,
        duration: float = 0.5
    ) -> None:
        """
        Drag from source element to target element.

        Args:
            source_locator: Source element locator
            target_locator: Target element locator
            duration: Drag duration in seconds

        Example:
            | Drag And Drop Visual | text=Item1 | text=Folder |
        """
        source = self._find_element(source_locator)
        target = self._find_element(target_locator)

        src_x, src_y = self._get_click_point(source)
        tgt_x, tgt_y = self._get_click_point(target)

        adapter = self._get_adapter()

        # Use pyautogui drag if available
        if hasattr(adapter, '_pyautogui'):
            adapter._init_pyautogui()
            adapter._pyautogui.moveTo(src_x, src_y)
            adapter._pyautogui.drag(
                tgt_x - src_x,
                tgt_y - src_y,
                duration=duration
            )
        else:
            # Fallback: click and hold, move, release
            adapter.click(src_x, src_y)
            time.sleep(0.1)
            adapter.click(tgt_x, tgt_y)
