"""
Visual action keywords (click, type, scroll, swipe).

All actions are performed through the configured ``visual_dom`` actuator strategy
(desktop / android / grpc / <plugin, e.g. robot-arm>, ADR-019). Element centers
are converted to **normalized** coordinates and the actuator maps them to its own
device space, so the same keywords work locally, over gRPC, or against a robot arm.
"""

import time
from typing import Optional

from robot.api.deco import keyword


class ActionKeywords:
    """Keywords for visual GUI interactions."""

    def __init__(self, click_delay: float = 0.1, **kwargs):
        self.click_delay = click_delay

    # _get_actuator / _norm_point / _norm_xy / _image_size are provided by
    # VisualGuiLibrary; _find_element resolves a locator to an element dict.

    def _find_element(self, locator: str) -> dict:
        """Find element using locator (delegates to CaptureKeywords.get_visual_element)."""
        return self.get_visual_element(locator)

    @keyword("Click Visual")
    def click_visual(self, locator: str, click_type: str = "single") -> None:
        """
        Click on a visual element.

        Args:
            locator: Element locator string
            click_type: single | double | right | long

        Example:
            | Click Visual | text=Login |
            | Click Visual | id=E7 | click_type=double |
        """
        element = self._find_element(locator)
        nx, ny = self._norm_point(element)
        self._get_actuator().tap(nx, ny, self._image_size(), click_type=click_type)
        time.sleep(self.click_delay)

    @keyword("Click At Coordinates")
    def click_at_coordinates(self, x: int, y: int, click_type: str = "single") -> None:
        """
        Click at specific image-space pixel coordinates.

        Args:
            x: X coordinate (image/screen pixels)
            y: Y coordinate (image/screen pixels)
            click_type: single | double | right | long

        Example:
            | Click At Coordinates | 100 | 200 |
            | Click At Coordinates | 100 | 200 | click_type=right |
        """
        nx, ny = self._norm_xy(int(x), int(y))
        self._get_actuator().tap(nx, ny, self._image_size(), click_type=click_type)
        time.sleep(self.click_delay)

    @keyword("Type Text Visual")
    def type_text_visual(self, locator: str, text: str, clear_first: bool = False) -> None:
        """
        Type text into a visual element (clicks it first to focus).

        Example:
            | Type Text Visual | hint=Email | user@example.com |
            | Type Text Visual | hint=Password | secret | clear_first=True |
        """
        self.click_visual(locator)
        actuator = self._get_actuator()
        if clear_first:
            actuator.clear_text()
            time.sleep(0.05)
        actuator.type_text(text)

    @keyword("Type Text")
    def type_text(self, text: str) -> None:
        """
        Type text at the current focus.

        Example:
            | Type Text | Hello World |
        """
        self._get_actuator().type_text(text)

    @keyword("Press Key")
    def press_key(self, key: str) -> None:
        """
        Press a keyboard key or combination.

        Example:
            | Press Key | enter |
            | Press Key | ctrl+a |
            | Press Key | alt+f4 |
        """
        self._get_actuator().press_key(key)

    @keyword("Clear Text Visual")
    def clear_text_visual(self, locator: str) -> None:
        """
        Clear text from a visual input element (clicks it first to focus).

        Example:
            | Clear Text Visual | hint=Search |
        """
        self.click_visual(locator)
        self._get_actuator().clear_text()

    @keyword("Scroll Visual")
    def scroll_visual(
        self,
        locator: Optional[str] = None,
        direction: str = "down",
        amount: int = 1
    ) -> None:
        """
        Scroll within a visual element, or at the screen center if no locator.

        Example:
            | Scroll Visual | direction=down |
            | Scroll Visual | locator=text=ListView | direction=up | amount=2 |
        """
        if locator:
            nx, ny = self._norm_point(self._find_element(locator))
        else:
            nx, ny = 0.5, 0.5  # screen center
        self._get_actuator().scroll(nx, ny, direction=direction,
                                    amount=int(amount), image_size=self._image_size())

    @keyword("Wait And Click Visual")
    def wait_and_click_visual(
        self,
        locator: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        click_type: str = "single"
    ) -> None:
        """
        Wait for an element to appear (refreshing the DOM) then click it.

        Example:
            | Wait And Click Visual | text=Submit | timeout=5 |
        """
        start_time = time.time()
        while True:
            try:
                self.dump_visual_dom()
                element = self._find_element(locator)
                if element:
                    nx, ny = self._norm_point(element)
                    self._get_actuator().tap(nx, ny, self._image_size(), click_type=click_type)
                    time.sleep(self.click_delay)
                    return
            except (ValueError, RuntimeError):
                pass

            if time.time() - start_time > float(timeout):
                raise TimeoutError(f"Element not found within {timeout}s: {locator}")
            time.sleep(float(interval))

    @keyword("Drag And Drop Visual")
    def drag_and_drop_visual(
        self,
        source_locator: str,
        target_locator: str,
        duration: float = 0.5
    ) -> None:
        """
        Drag from a source element to a target element.

        Example:
            | Drag And Drop Visual | text=Item1 | text=Folder |
        """
        nx1, ny1 = self._norm_point(self._find_element(source_locator))
        nx2, ny2 = self._norm_point(self._find_element(target_locator))
        self._get_actuator().swipe(nx1, ny1, nx2, ny2,
                                   image_size=self._image_size(), duration=float(duration))
