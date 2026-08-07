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
      - capture  (visual_dom.adapters.outbound.capture, ADR-018): windows/linux/android/camera/grpc/<plugin>
      - actuator (visual_dom.adapters.outbound.actuator, ADR-019): desktop/android/grpc/<plugin, e.g. robot-arm>

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
        app_title: str = None,
        focus_before_capture: bool = False,
        window_scope: bool = False,
        screenshot_on_failure: bool = True,
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
            app_title: Window title of the application under test (Android: package
                or package/.Activity), used by ``Bring App To Front`` (ADR-021).
            focus_before_capture: Raise ``app_title`` before every screen grab.
            window_scope: Capture only ``app_title``'s window instead of the whole
                screen, so the DOM contains just that application (ADR-021).
            screenshot_on_failure: Attach a screenshot to the Robot log whenever a
                keyword of this library fails (default on). Toggle at runtime with
                ``Set Screenshot On Failure``.
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

        # Application targeting / focus (ADR-021). `Connect` overrides these from
        # the config's capture.window_title / capture.focus_before_capture.
        self._app_title = app_title
        self._actuator_app_title = app_title
        self._focus_before_capture = bool(focus_before_capture)
        self._window_scope = bool(window_scope)
        # Geometry of the last grab when it was window-scoped (a CaptureFrame), so
        # coordinates measured on the crop map back to the device space.
        self._capture_frame = None

        # Failure evidence: capture the screen THROUGH THE CAPTURE PORT when one
        # of our keywords fails, and embed it in the Robot log. Going through the
        # port matters on a distributed run - the screenshot shows the machine
        # under test (via the capture service), not the runner's desktop.
        self._screenshot_on_failure = bool(screenshot_on_failure)
        self._shot_index = 0
        self._last_shot_exc = None      # dedup: one shot per propagating exception
        self._capturing_failure = False  # re-entrancy guard
        self._wrap_keywords_for_failure_capture()
        self._attach_robot_log_bridge()

    def _attach_robot_log_bridge(self):
        """
        Forward visual_dom log records into the Robot Framework log.

        The package logger deliberately does not propagate to the root logger
        (so plain-Python use never double-prints), which also means Robot's
        automatic logging capture never sees it - detector/pipeline log lines
        ended up only on the console and in logs/vizdom.log, invisible in
        log.html. This bridge emits each record via robot.api.logger, which
        files it under the keyword that was executing - exactly where someone
        debugging a failed dump looks. Level policy follows the package logger
        (VIZDOM_LOG_LEVEL). Idempotent; a no-op outside Robot.
        """
        import logging
        try:
            from robot.api import logger as rf_logger
        except ImportError:
            return
        from visual_dom.logging_utils import configure_logging
        pkg = configure_logging()
        if any(getattr(h, "_vizdom_rf_bridge", False) for h in pkg.handlers):
            return

        class _RobotBridge(logging.Handler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    if record.levelno >= logging.ERROR:
                        rf_logger.error(msg)
                    elif record.levelno >= logging.WARNING:
                        rf_logger.warn(msg)
                    else:
                        rf_logger.info(msg)
                except Exception:   # logging must never break a keyword
                    pass

        handler = _RobotBridge()
        handler.setFormatter(logging.Formatter("%(name)s | %(message)s"))
        handler._vizdom_rf_bridge = True
        pkg.addHandler(handler)

    # --- failure screenshots -------------------------------------------------

    def _wrap_keywords_for_failure_capture(self):
        """
        Wrap every keyword so a failure captures the screen before re-raising.

        A wrapper (rather than a Robot listener) is deliberate: inside the failing
        keyword's execution the log message lands UNDER that keyword in log.html,
        exactly where someone debugging looks - a listener's message would not.
        Instance attributes shadow the class methods, so nested keyword calls
        (Click Visual -> Get Visual Element) go through the wrappers too; the
        exception-identity dedup below keeps that to ONE screenshot per failure.
        """
        import functools
        import sys

        for name in dir(type(self)):
            if name.startswith("_"):
                continue
            attr = getattr(self, name)
            if not callable(attr) or not hasattr(attr, "robot_name"):
                continue
            if name == "take_screenshot":   # taking the evidence must not recurse
                continue

            @functools.wraps(attr)
            def wrapper(*args, __orig=attr, **kwargs):
                try:
                    return __orig(*args, **kwargs)
                except Exception:
                    exc = sys.exc_info()[1]
                    if self._last_shot_exc is not exc:   # once per exception
                        self._last_shot_exc = exc
                        self._capture_failure_screenshot(__orig.__name__)
                    raise

            setattr(self, name, wrapper)

    def _capture_failure_screenshot(self, keyword_name: str):
        """Best-effort evidence capture; must never mask the original error."""
        if not self._screenshot_on_failure or self._capturing_failure:
            return
        self._capturing_failure = True
        try:
            self.take_screenshot(name=f"fail-{keyword_name}")
        except Exception as exc:  # noqa: BLE001 - the original failure wins
            print(f"WARN: could not capture a failure screenshot: {exc}")
        finally:
            self._capturing_failure = False

    # --- strategy accessors (lazy) -------------------------------------------

    def _get_capture(self):
        """The visual_dom capture strategy (in-process or gRPC), created on first use."""
        if self._capture is None:
            from visual_dom.adapters.outbound.capture import create_capture, auto_select
            name = self._capture_name or auto_select()
            if not name:
                raise RuntimeError("No capture strategy available; pass capture=<name>.")
            self._capture = create_capture(name, **self._capture_kwargs)
        return self._capture

    def _get_actuator(self):
        """The visual_dom actuator strategy (in-process or gRPC), created on first use."""
        if self._actuator is None:
            from visual_dom.adapters.outbound.actuator import create_actuator, auto_select
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
        """
        Image-space pixel (x, y) -> normalized (nx, ny) for the actuator.

        With a window-scoped capture (ADR-021) the image is a crop, so its pixels
        must first be shifted by the crop's screen origin and then normalized
        against the *device's* coordinate space - otherwise a click computed on a
        402x658 crop would be applied to a 1920x1080 screen and land far away.
        """
        frame = getattr(self, "_capture_frame", None)
        if frame is not None:
            return frame.to_normalized(x, y)
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
