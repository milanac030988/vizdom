"""
Visual assertion keywords.

Existence checks (`Visual Should Exist` / `Visual Should Not Exist`) run against
the CURRENT Visual DOM, so dump or load one first ('Dump Visual DOM' /
'Load Visual DOM'). The `Wait Until Visual ...` keywords refresh the DOM
themselves on every poll, so they can watch the screen change over time.
"""

import time
from typing import Optional

from robot.api.deco import keyword


class AssertionKeywords:
    """Keywords for visual assertions and waiting."""

    def __init__(self):
        pass

    # --- helpers -------------------------------------------------------------

    def _assert_finder(self):
        """Return the current element finder or fail with a clear message."""
        finder = getattr(self, "_finder", None)
        if finder is None:
            raise RuntimeError(
                "No DOM loaded. Call 'Dump Visual DOM' (or 'Load Visual DOM') first."
            )
        return finder

    def _match(self, locator: str) -> list:
        """
        Elements in the current DOM matching ``locator`` (may be empty).

        Honours ``||`` fallback chains (ADR-024): alternatives are tried in
        order and the first that matches anything is returned. For an existence
        check, several matches are fine (unlike a click), so ambiguity is not a
        miss here.
        """
        from ..locators import LocatorParser
        finder = self._assert_finder()
        for group in LocatorParser.parse_alternatives(locator):
            found = finder.find(group)
            if found:
                return found
        return []

    @staticmethod
    def _to_secs(value) -> float:
        """Parse a Robot time string ('10s', '0.5s', '1 min') into seconds."""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            from robot.utils import timestr_to_secs
            return float(timestr_to_secs(value))
        except Exception:
            return float(str(value).strip().rstrip("s").strip() or 0)

    # --- existence assertions (current DOM) ----------------------------------

    @keyword("Visual Should Exist")
    def visual_should_exist(
        self,
        locator: str,
        message: Optional[str] = None
    ) -> None:
        """
        Assert that a visual element exists in the current DOM.

        Checks the DOM produced by the last 'Dump Visual DOM' / 'Load Visual DOM'.
        To wait for something that appears over time, use
        'Wait Until Visual Appears' instead.

        Args:
            locator: Element locator string
            message: Custom failure message

        Example:
            | Visual Should Exist | text=Welcome |
            | Visual Should Exist | role=Button | message=Login button missing |
        """
        if not self._match(locator):
            raise AssertionError(
                message or f"Expected a visual element matching '{locator}', but none was found."
            )

    @keyword("Visual Should Not Exist")
    def visual_should_not_exist(
        self,
        locator: str,
        message: Optional[str] = None
    ) -> None:
        """
        Assert that a visual element does not exist in the current DOM.

        Args:
            locator: Element locator string
            message: Custom failure message

        Example:
            | Visual Should Not Exist | text=Error |
        """
        matches = self._match(locator)
        if matches:
            raise AssertionError(
                message or f"Expected no visual element matching '{locator}', but found {len(matches)}."
            )

    # --- waits (refresh the DOM on each poll) --------------------------------

    @keyword("Wait Until Visual Appears")
    def wait_until_visual_appears(
        self,
        locator: str,
        timeout: str = "10s",
        poll_interval: str = "0.5s"
    ) -> None:
        """
        Wait until a visual element appears.

        Re-captures the screen and rebuilds the Visual DOM on each poll, so it
        reflects the live screen (not a stale DOM). Fails if the element has not
        appeared within ``timeout``.

        Args:
            locator: Element locator string
            timeout: Maximum wait time (e.g. 30s)
            poll_interval: Time between checks (e.g. 0.5s)

        Example:
            | Wait Until Visual Appears | text=Dashboard | timeout=30s |
        """
        deadline = time.time() + self._to_secs(timeout)
        interval = self._to_secs(poll_interval)
        last_err = None

        while True:
            try:
                self.dump_visual_dom()
                if self._match(locator):
                    return
            except Exception as e:  # capture/DOM error - keep trying until timeout
                last_err = e

            if time.time() >= deadline:
                msg = f"Visual element '{locator}' did not appear within {timeout}."
                if last_err is not None:
                    msg += f" (last error: {last_err})"
                raise AssertionError(msg)

            time.sleep(interval)

    @keyword("Wait Until Visual Disappears")
    def wait_until_visual_disappears(
        self,
        locator: str,
        timeout: str = "10s",
        poll_interval: str = "0.5s"
    ) -> None:
        """
        Wait until a visual element disappears.

        Re-captures the screen and rebuilds the Visual DOM on each poll. Fails if
        the element is still present after ``timeout``.

        Args:
            locator: Element locator string
            timeout: Maximum wait time (e.g. 60s)
            poll_interval: Time between checks (e.g. 0.5s)

        Example:
            | Wait Until Visual Disappears | text=Loading... | timeout=60s |
        """
        deadline = time.time() + self._to_secs(timeout)
        interval = self._to_secs(poll_interval)

        while True:
            try:
                self.dump_visual_dom()
                if not self._match(locator):
                    return
            except Exception:
                # Can't build a DOM (e.g. capture failed): don't claim it vanished;
                # keep polling until the timeout decides.
                pass

            if time.time() >= deadline:
                raise AssertionError(
                    f"Visual element '{locator}' was still present after {timeout}."
                )

            time.sleep(interval)
