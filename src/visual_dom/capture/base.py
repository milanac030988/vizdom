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

import numpy as np


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

    def close(self) -> None:
        """Release any resources (camera handles, adb sessions). Optional."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} name={self.name!r} platform={self.platform!r}>"
