"""
Example custom capture plugin (ADR-018).

Copy this file, rename the class + `name`, implement `capture()`, and drop it in
this folder (plugins/capture/). The registry auto-loads it on next run; select it
by its `name` in config/CLI. This example just replays a PNG from disk — swap the
body for your camera API, a frame-grabber SDK, a remote feed, etc.
"""

import os

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class StaticImageCapture(CaptureStrategy):
    name = "static-image"
    platform = "any"
    description = "Replays a fixed image from $VIZDOM_STATIC_IMAGE (demo/testing)."

    def __init__(self, path: str = None):
        self._path = path or os.environ.get("VIZDOM_STATIC_IMAGE")

    @classmethod
    def is_available(cls) -> bool:
        p = os.environ.get("VIZDOM_STATIC_IMAGE")
        return bool(p) and os.path.exists(p)

    def capture(self) -> np.ndarray:
        import cv2
        if not self._path or not os.path.exists(self._path):
            raise RuntimeError("set VIZDOM_STATIC_IMAGE (or pass path=) to a readable image")
        img = cv2.imread(self._path)
        if img is None:
            raise RuntimeError(f"could not read image: {self._path}")
        return img
