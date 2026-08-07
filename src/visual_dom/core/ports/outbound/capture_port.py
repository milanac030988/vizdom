"""
Screenshot capture strategy (ADR-018).

`CaptureStrategy` is the strategy base users override to plug in their own way of
obtaining a screenshot (a platform grab, an ADB pull, a camera/frame-grabber API,
a remote feed, ...). It is the driven "CapturePort" of the hexagonal architecture:
it produces the BGR image that feeds the CV pipeline.

To add a custom capture method: subclass `CaptureStrategy`, set a unique `name`,
implement `capture()`, drop the file in the capture plugins folder (default
`plugins/capture/`, or `$VIZDOM_CAPTURE_PLUGINS`), and the registry auto-loads it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class CaptureFrame:
    """
    A window-scoped capture: the cropped image **plus the geometry needed to act
    on it** (ADR-021).

    A bare cropped image is dangerous. Actuators work in the device's own
    coordinate space, so if a DOM is built from a crop and its normalized
    coordinates are mapped back against the whole screen, every click lands at the
    wrong place. The geometry therefore travels *with* the pixels:

        screen_px    = origin + crop_px
        normalized   = (screen_px - device_origin) / device_size

    ``device_origin`` exists because a second monitor can start at a **negative**
    screen coordinate (a display left of the primary one). Normalizing against the
    primary screen alone would push those elements outside [0,1] and the actuator
    would clamp them to the screen edge. Carrying the origin of the coordinate
    space keeps a window on any monitor addressable, and collapses to today's
    behaviour on a single-monitor setup, where ``device_origin`` is ``(0, 0)``.
    """

    #: the captured pixels (BGR, H x W x 3) — the window's client area
    image: np.ndarray
    #: (x, y) of the image's top-left corner in absolute screen coordinates
    origin: Tuple[int, int]
    #: (width, height) of the coordinate space used for normalization
    device_size: Tuple[int, int]
    #: (x, y) where that coordinate space begins, in screen coordinates (may be
    #: negative for a monitor placed left of / above the primary one)
    device_origin: Tuple[int, int] = (0, 0)
    #: the window actually captured (as resolved), for provenance
    window_title: Optional[str] = None

    def to_normalized(self, px: float, py: float) -> Tuple[float, float]:
        """Pixel (px, py) *within this image* -> normalized [0,1] device coords."""
        ox, oy = self.origin
        dx, dy = self.device_origin
        dw, dh = self.device_size
        return ((ox + px - dx) / float(dw), (oy + py - dy) / float(dh))


class CaptureStrategy(ABC):
    """A way to obtain a screenshot as a BGR numpy image."""

    #: unique registry name, e.g. "windows", "android", "my-camera"
    name: str = "base"

    #: "windows" | "linux" | "android" | "any" (informational / filtering)
    platform: str = "any"

    #: human-readable description shown by `list_captures()`
    description: str = ""

    @abstractmethod
    def capture(self) -> np.ndarray:
        """
        Grab one screenshot and return it as a BGR image (H, W, 3) uint8 —
        the same format `cv2.imread` produces, ready for the pipeline.
        """
        raise NotImplementedError

    @classmethod
    def is_available(cls) -> bool:
        """
        Whether this strategy can run here (deps importable / tool present /
        device connected). Must never raise — return False instead. Cheap check.
        """
        return True

    def describe_target(self) -> dict:
        """
        Identify WHAT was captured, for session provenance. Optional override.

        Each strategy knows best how to name its own target, so this is a port
        concern rather than a caller concern: the OS grabbers can query the
        window manager, ADB can ask for the resumed activity, a camera cannot
        know anything (it photographs an external display), and a remote feed
        only knows its endpoint.

        Returns a JSON-serialisable dict; recommended keys:
          ``window_title``  authoritative name, when the platform can supply one
          ``process_name``  owning executable / package, when known
          ``activity``      Android component (package/.Activity)
          ``target_hint``   free-form note when nothing authoritative exists
          ``guess_source``  set ONLY for inferred values (e.g. "ocr", "vlm"),
                            so a guess is never mistaken for a fact

        Must never raise — return ``{}`` when the target cannot be identified.
        """
        return {}

    def frame_geometry(self):
        """
        Where the frames `capture()` returns sit in the device's coordinate space.
        Optional; returns ``(origin, device_origin, device_size)`` or None.

        This is what lets a caller convert pixels into the coordinate space the
        *actuator* uses. It matters on a multi-monitor desktop: a grab of the primary
        monitor starts at (0, 0) of a virtual desktop that may begin at (-1920, 0),
        so normalizing against the image alone would send clicks to the wrong
        display.

        Returning None (the default) means "my pixels have no relation to a larger
        space" and the caller normalizes against the image itself. That is the right
        answer for Android, where the screencap buffer may not even share the input
        resolution and the mapping must stay proportional.
        """
        return None

    def capture_window(self, title: str = None) -> "Optional[CaptureFrame]":
        """
        Capture ONLY the application under test, not the whole screen. Optional.

        Returns a `CaptureFrame` (pixels + crop origin + full device size), or
        ``None`` when this strategy cannot scope a capture to one window — the
        caller then falls back to `focus_target()` + `capture()`.

        Implementations must **raise the window first**: a region grab reads the
        desktop, so an occluded window would yield the pixels of whatever covers
        it. Returning a crop that silently contains another application is worse
        than returning None, so a strategy that cannot confirm focus should refuse.

        Why a whole method instead of a `region=` argument to `capture()`: the
        image and the geometry must come from the *same instant*. Asking for the
        rectangle and the pixels separately races against a window that is moving
        or resizing, and over gRPC it would also mean two round trips.

        Android returns None deliberately: there the app already owns the screen,
        so a plain `capture()` is window-scoped by construction.
        """
        return None

    def focus_target(self, title: str = None) -> bool:
        """
        Bring the application under test to the foreground. Optional override.

        This is a *correctness* capability, not a convenience: a full-screen grab
        photographs whatever window is on top, so if the SUT is behind another
        window the pipeline analyses the wrong pixels.

        ``title`` names the window/activity to raise; when omitted the strategy
        uses whatever target it was configured with (and may return False if it
        has none). Strategies that cannot influence what is on screen (a camera
        pointed at an external display) simply return False.

        Returns True only when the strategy is *confident* the target is now
        foreground, so callers can fail loudly: raising a window can be blocked
        outright (Windows' foreground lock), and reporting a hopeful True would
        turn that into a silently wrong screenshot. Must never raise.

        Note that focusing mutates the state of the SUT (it can dismiss
        popups/tooltips or change what has keyboard focus), which is why it is an
        explicit call rather than something `capture()` always does.
        """
        return False

    def close(self) -> None:
        """Release any resources (camera handles, adb sessions). Optional."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} name={self.name!r} platform={self.platform!r}>"
