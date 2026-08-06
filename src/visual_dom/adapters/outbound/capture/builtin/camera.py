"""
Camera / frame-grabber capture (cv2.VideoCapture) — the example of a
non-screenshot source. Pair with the pipeline's camera_mode to rectify the
screen region from a photo of a physical display.
"""

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class CameraCapture(CaptureStrategy):
    name = "camera"
    platform = "any"
    description = "Frame from a camera / capture card via cv2.VideoCapture (device index or URL)."

    def __init__(self, device=0, warmup_frames: int = 2):
        self._device = device          # int index or a stream URL string
        self._warmup = warmup_frames    # discard first frames (auto-exposure)
        self._cap = None

    @classmethod
    def is_available(cls) -> bool:
        try:
            import cv2  # noqa: F401
            return True
        except Exception:
            return False

    def describe_target(self) -> dict:
        """
        A camera photographs an EXTERNAL display: there is no OS to ask, so no
        authoritative window title exists. Record what we do know (the capture
        device) and leave naming to the caller — see docs for the options
        (title-strip OCR from the analysed DOM, an operator-supplied session
        label, or an opt-in VLM guess, which must be stored with
        ``guess_source``).
        """
        return {
            "target_hint": f"external display via camera device {self._device!r}",
            "camera_device": self._device,
        }

    def capture(self) -> np.ndarray:
        import cv2
        if self._cap is None:
            self._cap = cv2.VideoCapture(self._device)
            if not self._cap.isOpened():
                raise RuntimeError(f"could not open camera device {self._device!r}")
        frame = None
        for _ in range(max(1, self._warmup)):
            ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("camera read failed")
        return frame  # already BGR

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
