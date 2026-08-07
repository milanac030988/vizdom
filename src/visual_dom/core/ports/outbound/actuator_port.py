"""
Input actuation strategy (ADR-019).

`ActuatorStrategy` is the strategy base users override to plug in their own way of
driving input on the system-under-test (a desktop mouse/keyboard, an ADB device,
a robot arm physically tapping a screen, a serial/CAN controller, ...). It is the
driven "ActuatorPort" of the hexagonal architecture - the write-side twin of
`CaptureStrategy` (ADR-018).

Coordinate contract
-------------------
Actions take **normalized** coordinates ``(nx, ny)`` in ``[0, 1]`` (fraction of
the source image width/height) plus the optional source ``image_size`` they came
from. Each strategy maps normalized coordinates to *its own* device space:

    desktop   : nx * screen_w, ny * screen_h          (screen == the captured image)
    android   : nx * device_w, ny * device_h          (input resolution)
    robot-arm : homography(image px) -> physical servo coordinates  (override _to_device)

Linear devices only need to override ``device_size()``; non-linear devices
(a robot arm) override ``_to_device()`` with their calibrated mapping. Keeping the
contract normalized means the orchestrator (and the gRPC wire) never has to know
any device's resolution.

The actuator is deliberately **primitive** (tap / type / key / scroll / swipe by
coordinate) and knows nothing about the DOM. Resolving a locator to a coordinate,
and higher-level flows like focus-then-type, stay in the caller (the Robot
Framework keywords).

To add a custom actuator: subclass `ActuatorStrategy`, set a unique `name`,
implement the primitives, drop the file in the actuator plugins folder (default
`plugins/actuator/`, or `$VIZDOM_ACTUATOR_PLUGINS`), and the registry auto-loads it.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


def _clamp01(v: float) -> float:
    """Clamp a normalized coordinate into [0, 1]."""
    return 0.0 if v < 0 else 1.0 if v > 1 else v


class ActuatorStrategy(ABC):
    """A way to drive input on the system-under-test, in normalized coordinates."""

    #: unique registry name, e.g. "desktop", "android", "my-robot-arm"
    name: str = "base"

    #: "windows" | "linux" | "android" | "any" (informational / filtering)
    platform: str = "any"

    #: human-readable description shown by `list_actuators()`
    description: str = ""

    # --- coordinate mapping (override per device) ----------------------------

    def device_size(self, image_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        """
        (width, height) of this actuator's input space, used to denormalize
        coordinates. Linear devices override this; the default falls back to the
        source ``image_size`` when the device space equals the captured image.
        """
        if image_size is not None:
            return int(image_size[0]), int(image_size[1])
        raise NotImplementedError(
            f"{type(self).__name__} must implement device_size() or receive image_size"
        )

    def device_origin(self) -> Tuple[int, int]:
        """
        Where this device's coordinate space begins, in the device's own units.

        Almost always ``(0, 0)``. It exists for the desktop case: a second monitor
        placed left of or above the primary one starts at a **negative** screen
        coordinate, so a coordinate space anchored at (0, 0) cannot address it and
        normalized coordinates would clamp to the primary monitor's edge. Override
        together with `device_size` to describe such a space.
        """
        return (0, 0)

    def _to_device(self, nx: float, ny: float,
                   image_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        """
        Map normalized [0,1] coordinates to this device's pixel space. Override
        for non-linear mappings (e.g. a robot-arm calibration homography).
        """
        w, h = self.device_size(image_size)
        ox, oy = self.device_origin()
        return (int(round(ox + _clamp01(nx) * w)),
                int(round(oy + _clamp01(ny) * h)))

    # --- primitive actions (implement these) ---------------------------------

    @abstractmethod
    def tap(self, nx: float, ny: float,
            image_size: Optional[Tuple[int, int]] = None,
            click_type: str = "single") -> None:
        """Tap/click at normalized (nx, ny). click_type: single | double | right | long."""
        raise NotImplementedError

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type text at the current focus."""
        raise NotImplementedError

    @abstractmethod
    def press_key(self, key: str) -> None:
        """Press a key or combo, e.g. 'enter', 'tab', 'ctrl+a', 'alt+f4'."""
        raise NotImplementedError

    @abstractmethod
    def scroll(self, nx: float, ny: float,
               direction: str = "down", amount: int = 1,
               image_size: Optional[Tuple[int, int]] = None) -> None:
        """Scroll at normalized (nx, ny). direction: up | down | left | right."""
        raise NotImplementedError

    @abstractmethod
    def swipe(self, nx1: float, ny1: float, nx2: float, ny2: float,
              image_size: Optional[Tuple[int, int]] = None,
              duration: float = 0.3) -> None:
        """Swipe/drag from normalized (nx1, ny1) to (nx2, ny2)."""
        raise NotImplementedError

    # --- convenience (built on the primitives) -------------------------------

    def select_all(self) -> None:
        """Select all text in the focused element."""
        self.press_key("ctrl+a")

    def clear_text(self) -> None:
        """Clear text in the focused element."""
        self.select_all()
        self.press_key("delete")

    def focus_target(self, title: Optional[str] = None) -> bool:
        """
        Bring the application under test to the foreground. Optional override.

        The write-side twin of `CaptureStrategy.focus_target` (ADR-021), and for
        the same correctness reason: `tap` clicks whatever window happens to be at
        that coordinate, and `type_text` goes to whatever holds *keyboard focus*.
        Without focus management a test can click and type into the wrong
        application entirely.

        ``title`` names the window/activity to raise; when omitted the strategy
        uses its configured target. Returns True only on confident success (see
        the capture port for why a hopeful True is harmful). Must never raise.
        """
        return False

    @classmethod
    def is_available(cls) -> bool:
        """
        Whether this actuator can run here (deps importable / tool present /
        device connected). Must never raise - return False instead. Cheap check.
        """
        return True

    def close(self) -> None:
        """Release any resources (device handles, adb sessions). Optional."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} name={self.name!r} platform={self.platform!r}>"
