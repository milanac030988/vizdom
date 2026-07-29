"""
Robot Framework keywords for visual GUI automation.
"""

from .capture import CaptureKeywords
from .assertions import AssertionKeywords
from .actions import ActionKeywords


class VisualGuiLibrary(CaptureKeywords, AssertionKeywords, ActionKeywords):
    """
    Robot Framework library for visual GUI automation.

    This library is a thin orchestrator over the ``visual_dom`` engine (ADR-019):
    it captures a screenshot, generates a Visual DOM, resolves locators to
    elements, and drives input - all via pluggable ``visual_dom`` strategies that
    run **in-process** or **remotely over gRPC**, selected by name.

    Two driven ports back every keyword:
      - capture  (visual_dom.capture, ADR-018): windows/linux/android/camera/grpc/<plugin>
      - actuator (visual_dom.actuator, ADR-019): desktop/android/grpc/<plugin, e.g. robot-arm>

    Locator Strategies:
        - id=E12            : Find by exact DOM element id (case-insensitive)
        - text="Login"      : Find by visible text
        - hint="Email"      : Find by hint/placeholder text
        - role=button       : Find by accessibility role
        - within="Form"     : Find within container
        - right_of="Label"  : Find element to the right of another
        - below="Title"     : Find element below another

    Example:
        | Library | VisualGuiLibrary | actuator=desktop |
        |         |                  |
        | Dump Visual DOM |          |
        | Click Visual | text=Login  |
        | Type Text Visual | hint=Email | user@example.com |
        | Visual Should Exist | text=Welcome |

    Remote example (capture on the device, actuate via a robot arm, both over gRPC):
        | Library | VisualGuiLibrary | capture=grpc | capture_target=sut:50053 |
        | ...     |                  | actuator=grpc | actuator_target=arm:50054 |
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_VERSION = "0.2.0"

    def __init__(
        self,
        platform: str = "desktop",
        ocr_engine: str = "tesseract",
        click_delay: float = 0.1,
        capture: str = None,
        actuator: str = None,
        capture_target: str = None,
        actuator_target: str = None,
        **kwargs
    ):
        """
        Initialize Visual GUI Library.

        Args:
            platform: Convenience preset for strategy selection: "desktop" (default)
                or "android". Overridden by explicit ``capture``/``actuator``.
            ocr_engine: Default OCR engine for DOM generation.
            click_delay: Delay after clicks in seconds.
            capture: visual_dom capture strategy name (default: derived from
                platform; desktop -> OS auto-select, android -> "android").
            actuator: visual_dom actuator strategy name (default: derived from
                platform; desktop -> "desktop", android -> "android").
            capture_target: host:port for a remote capture service (capture=grpc).
            actuator_target: host:port for a remote actuator service (actuator=grpc).
        """
        CaptureKeywords.__init__(self)
        AssertionKeywords.__init__(self)
        ActionKeywords.__init__(self, click_delay=click_delay)

        self.platform = platform
        self.ocr_engine = ocr_engine

        # Resolve strategy names from the platform preset unless given explicitly.
        # None capture name -> auto_select() at first use.
        self._capture_name = capture or ("android" if platform == "android" else None)
        self._actuator_name = actuator or ("android" if platform == "android" else "desktop")
        self._capture_kwargs = {"target": capture_target} if capture_target else {}
        self._actuator_kwargs = {"target": actuator_target} if actuator_target else {}
        self._capture = None
        self._actuator = None

    # --- strategy accessors (lazy) -------------------------------------------

    def _get_capture(self):
        """The visual_dom capture strategy (in-process or gRPC), created on first use."""
        if self._capture is None:
            from visual_dom.capture import create_capture, auto_select
            name = self._capture_name or auto_select()
            if not name:
                raise RuntimeError("No capture strategy available; pass capture=<name>.")
            self._capture = create_capture(name, **self._capture_kwargs)
        return self._capture

    def _get_actuator(self):
        """The visual_dom actuator strategy (in-process or gRPC), created on first use."""
        if self._actuator is None:
            from visual_dom.actuator import create_actuator, auto_select
            name = self._actuator_name or auto_select()
            if not name:
                raise RuntimeError("No actuator strategy available; pass actuator=<name>.")
            self._actuator = create_actuator(name, **self._actuator_kwargs)
        return self._actuator

    # --- coordinate helpers (pixel <-> normalized) ---------------------------

    def _image_size(self):
        """(width, height) of the current screenshot / DOM, for normalizing coords."""
        shot = getattr(self, "_current_screenshot", None)
        if shot is not None:
            h, w = shot.shape[:2]
            return (int(w), int(h))
        dom = getattr(self, "_current_dom", None) or {}
        sz = dom.get("image_size")
        if isinstance(sz, (list, tuple)) and len(sz) == 2:
            return (int(sz[0]), int(sz[1]))
        if isinstance(sz, dict) and "width" in sz and "height" in sz:
            return (int(sz["width"]), int(sz["height"]))
        return None

    def _element_center_px(self, element: dict) -> tuple:
        """Pixel center of an element (from 'center', else bounds midpoint)."""
        center = element.get("center")
        if center:
            return (int(center[0]), int(center[1]))
        b = element.get("bounds", [0, 0, 0, 0])
        return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)

    def _norm_xy(self, x, y):
        """Image-space pixel (x, y) -> normalized (nx, ny) using the current image size."""
        size = self._image_size()
        if not size:
            # Fall back to the actuator's own device size (e.g. desktop screen).
            try:
                size = self._get_actuator().device_size()
            except Exception:
                raise RuntimeError(
                    "No image size known - capture a screen or 'Dump Visual DOM' first."
                )
        w, h = size
        return (x / w, y / h)

    def _norm_point(self, element: dict):
        """Element center -> normalized (nx, ny)."""
        cx, cy = self._element_center_px(element)
        return self._norm_xy(cx, cy)


__all__ = ["VisualGuiLibrary"]
