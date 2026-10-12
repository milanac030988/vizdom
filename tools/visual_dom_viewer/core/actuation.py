"""
Try a locator from the Viewer through the actuator (ADR-028).

The Viewer used to stop at *defining* locators; the first time one was exercised
was at Robot Framework runtime. A trial closes that loop: resolve the locator the
way the suite will, map the element to the device the way the suite will, raise
the application, and click — so a broken locator fails here, before the test is
written.

Kept free of Qt so the whole path is unit-testable; the main window owns the UX
(confirmation, fresh capture, showing the result).

Same machinery as the RF library, not a parallel copy:

- resolution: `visual_gui_library.locators.LocatorResolver` (ADR-024 chains,
  ADR-022 desc= grounding);
- coordinates: `CaptureFrame.to_normalized` for a window-scoped capture, else
  proportional to the image (``VisualGuiLibrary._norm_xy``) (ADR-021);
- focus before input: the actuator's ``focus_target``, then the capture side's,
  like ``Bring App To Front`` (ADR-021);
- actuation: an `ActuatorStrategy` from the registry (ADR-019).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

#: click types an ActuatorStrategy.tap understands
CLICK_TYPES = ("single", "double", "right", "long")


class ActuationError(RuntimeError):
    """A trial cannot run safely (no DOM, no target window, unmappable capture...)."""


@dataclass
class ActuationSettings:
    """How the Viewer reaches the actuator; mirrors the config's ``actuator`` section."""

    #: registry name (desktop | android | grpc | <plugin>); None = platform default
    strategy: Optional[str] = None
    #: host:port of the actuator service when strategy == "grpc"
    target: Optional[str] = None
    #: window to raise before input; None = the captured/connected window
    window_title: Optional[str] = None

    @classmethod
    def from_config(cls, data: Optional[Dict[str, Any]]) -> "ActuationSettings":
        section = (data or {}).get("actuator") or {}
        return cls(strategy=section.get("strategy") or None,
                   target=section.get("target") or None,
                   window_title=section.get("window_title") or None)

    def create_actuator(self):
        """Instantiate the configured strategy (the RF library's `_get_actuator` rules)."""
        from visual_dom.adapters.outbound.actuator import auto_select, create_actuator
        name = self.strategy or auto_select()
        if not name:
            raise ActuationError("No actuator strategy is available on this machine; "
                                 "choose one in Pipeline Settings > Actuation.")
        kwargs = {}
        if name == "grpc" and self.target:
            kwargs["target"] = self.target
        return create_actuator(name, **kwargs)


@dataclass
class TrialOutcome:
    """What a trial did — enough for the Viewer to explain a pass or a failure."""

    locator: str
    resolution: Any = None                 # visual_gui_library Resolution
    point: Optional[Tuple[int, int]] = None          # element center, image px
    normalized: Optional[Tuple[float, float]] = None
    focused_via: Optional[str] = None      # "actuator" | "capture"
    clicked: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def element_id(self) -> Optional[str]:
        element = getattr(self.resolution, "element", None)
        return element.get("id") if element else None


def element_center(element: Dict[str, Any]) -> Tuple[int, int]:
    """Pixel center of a compiled-DOM element ('center', else bounds midpoint)."""
    center = element.get("center")
    if center:
        return int(center[0]), int(center[1])
    b = element.get("bounds") or [0, 0, 0, 0]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def to_normalized(px: float, py: float, capture: Dict[str, Any],
                  image_size: Optional[Tuple[int, int]]) -> Tuple[float, float]:
    """
    Image pixel -> normalized device coordinates, from the capture's provenance.

    A window-scoped capture carries its geometry (ADR-021) and maps through
    `CaptureFrame.to_normalized`. A full-screen capture maps proportionally, as
    the RF library does without a frame. Anything else — a window handler crop
    without geometry, an image opened from disk — has no known place on the
    screen, and guessing would click somewhere else entirely, so it is refused.
    """
    origin = capture.get("capture_origin")
    device_size = capture.get("device_size")
    if origin is not None and device_size:
        from visual_dom.core.ports.outbound.capture_port import CaptureFrame
        frame = CaptureFrame(image=None, origin=tuple(origin),
                             device_size=tuple(device_size),
                             device_origin=tuple(capture.get("device_origin") or (0, 0)))
        return frame.to_normalized(px, py)
    if capture.get("capture_scope") == "screen" and image_size:
        w, h = image_size
        return px / float(w), py / float(h)
    raise ActuationError(
        "This screenshot has no known position on the screen (it was opened from a "
        "file or captured without geometry), so a click cannot be placed. Capture "
        "it with a capture strategy (Pipeline Settings > Capture source) first.")


class LocatorTrial:
    """Resolve -> map -> focus -> click, exactly as a Robot test would."""

    def __init__(self, actuator, capture_focus: Optional[Callable[[str], bool]] = None,
                 settle: Callable[[], None] = lambda: None):
        """
        Args:
            actuator: an `ActuatorStrategy`.
            capture_focus: optional ``title -> bool`` raising the window through
                the capture side when the actuator cannot (ADR-021: either port
                may be the one that can influence the screen).
            settle: called between focusing and clicking (the window manager
                needs a moment before the raised window receives input).
        """
        self.actuator = actuator
        self.capture_focus = capture_focus
        self.settle = settle

    def resolve(self, locator: str, compiled_dom: Dict[str, Any],
                screenshot=None, grounding=None):
        from visual_gui_library.locators import LocatorResolver
        if not compiled_dom or not compiled_dom.get("elements"):
            raise ActuationError("No analyzed DOM to resolve against — run "
                                 "Capture & Analyze first.")
        return LocatorResolver.for_dom(compiled_dom, screenshot, grounding).explain(locator)

    def focus(self, title: str) -> Optional[str]:
        """Raise ``title``; return which port confirmed it, or None."""
        try:
            if self.actuator.focus_target(title):
                return "actuator"
        except Exception:
            pass
        if self.capture_focus is not None:
            try:
                if self.capture_focus(title):
                    return "capture"
            except Exception:
                pass
        return None

    def run(self, locator: str, compiled_dom: Dict[str, Any], capture: Dict[str, Any],
            image_size: Optional[Tuple[int, int]], window_title: Optional[str],
            click_type: str = "single", screenshot=None, grounding=None) -> TrialOutcome:
        """
        Try ``locator``. A locator that does not resolve to exactly one element
        returns an outcome with ``clicked=False`` and the resolver's reasons —
        that is the trial's main finding, not an error. Raises `ActuationError`
        when the click itself cannot be made safely.
        """
        if click_type not in CLICK_TYPES:
            raise ActuationError(f"Unknown click type {click_type!r}")
        outcome = TrialOutcome(locator=locator)
        outcome.resolution = self.resolve(locator, compiled_dom, screenshot, grounding)
        if not outcome.resolution.ok:
            return outcome
        if outcome.resolution.used_fallback:
            failed = "; ".join(f"{r} ({why})" for r, why in outcome.resolution.attempts)
            outcome.notes.append(
                f"Resolved by fallback #{outcome.resolution.alternative + 1} "
                f"'{outcome.resolution.rendered}'; earlier alternatives failed: {failed}")

        # Never actuate without a window association: a tap lands on whatever is
        # at that coordinate, which without a raised target is anyone's guess.
        if not window_title:
            raise ActuationError("No target window: connect to the application (or set "
                                 "Actuation > Window title) so it can be raised first.")

        outcome.point = element_center(outcome.resolution.element)
        outcome.normalized = to_normalized(*outcome.point, capture, image_size)

        outcome.focused_via = self.focus(window_title)
        if outcome.focused_via is None:
            raise ActuationError(
                f"Could not bring {window_title!r} to the front, so the click was not "
                f"sent (it would land on whatever window is on top).")
        self.settle()
        self.actuator.tap(*outcome.normalized, image_size, click_type=click_type)
        outcome.clicked = True
        return outcome


__all__ = ["ActuationError", "ActuationSettings", "CLICK_TYPES", "LocatorTrial",
           "TrialOutcome", "element_center", "to_normalized"]
