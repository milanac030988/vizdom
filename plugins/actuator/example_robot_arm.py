"""
Example custom actuator plugin: a robot arm that physically taps a screen (ADR-019).

This is the motivating case for the ActuatorPort: the "screen" is a physical
display observed through `CaptureStrategy=camera`, and input is performed by a
robot arm touching it. Copy this file, rename the class + `name`, replace the
`_move_and_tap` / `_send` bodies with your arm's SDK/serial/CAN commands, and drop
it in this folder (plugins/actuator/). The registry auto-loads it; select it by
its `name` in config/CLI.

The key idea: the DOM gives coordinates in *image pixels*, but the arm works in
*physical* coordinates. Override `_to_device()` to apply a calibration
**homography** (image px -> arm XY). Calibrate once by tapping known reference
points; here we accept a 3x3 matrix (e.g. from cv2.getPerspectiveTransform).

SAFETY: a real arm moves in the physical world. A production plugin MUST enforce
work-area limits, speed caps, and an e-stop. This stub only prints.
"""

import os

from visual_dom.actuator import ActuatorStrategy


class RobotArmActuator(ActuatorStrategy):
    name = "robot-arm"
    platform = "any"
    description = "Robot arm physically tapping a screen (demo stub; pairs with camera capture)."

    def __init__(self, homography=None, port: str = None):
        # homography: 3x3 image-pixel -> physical mapping (list of 9 floats or 3x3).
        # In practice, produce it once from a calibration routine and pass/load it.
        self._H = self._parse_homography(homography)
        self._port = port or os.environ.get("VIZDOM_ROBOT_ARM_PORT")

    @classmethod
    def is_available(cls) -> bool:
        # A real plugin would check the arm SDK import / that the port is present.
        # The stub is always "available" so the example is discoverable.
        return True

    # --- coordinate mapping: normalized -> physical via homography ------------

    def _to_device(self, nx, ny, image_size=None):
        if image_size is None:
            raise RuntimeError("robot-arm actuator needs image_size to map coordinates")
        # normalized -> source image pixels
        px, py = nx * image_size[0], ny * image_size[1]
        if self._H is None:
            # No calibration: pass image pixels straight through (demo only).
            return int(round(px)), int(round(py))
        # apply 3x3 homography: [X Y W]^T = H . [px py 1]^T ; physical = (X/W, Y/W)
        H = self._H
        X = H[0][0] * px + H[0][1] * py + H[0][2]
        Y = H[1][0] * px + H[1][1] * py + H[1][2]
        W = H[2][0] * px + H[2][1] * py + H[2][2]
        if W == 0:
            W = 1e-9
        return int(round(X / W)), int(round(Y / W))

    @staticmethod
    def _parse_homography(h):
        if h is None:
            return None
        if len(h) == 9:  # flat list of 9
            return [list(h[0:3]), list(h[3:6]), list(h[6:9])]
        return [list(row) for row in h]  # already 3x3

    # --- primitive actions: drive the arm ------------------------------------

    def _move_and_tap(self, X, Y):
        # Replace with your arm SDK: move above (X, Y), lower, contact, lift.
        print(f"[robot-arm] tap at physical ({X}, {Y})")

    def _send(self, command: str):
        # Replace with your arm/keyboard bridge (a real screen has no keyboard,
        # so typing usually drives an on-screen keyboard via taps, or a HID device).
        print(f"[robot-arm] command: {command}")

    def tap(self, nx, ny, image_size=None, click_type="single"):
        X, Y = self._to_device(nx, ny, image_size)
        self._move_and_tap(X, Y)
        if click_type == "double":
            self._move_and_tap(X, Y)

    def type_text(self, text: str) -> None:
        self._send(f"type:{text}")

    def press_key(self, key: str) -> None:
        self._send(f"key:{key}")

    def scroll(self, nx, ny, direction="down", amount=1, image_size=None):
        X, Y = self._to_device(nx, ny, image_size)
        self._send(f"scroll:{direction}x{amount}@({X},{Y})")

    def swipe(self, nx1, ny1, nx2, ny2, image_size=None, duration=0.3):
        X1, Y1 = self._to_device(nx1, ny1, image_size)
        X2, Y2 = self._to_device(nx2, ny2, image_size)
        self._send(f"swipe:({X1},{Y1})->({X2},{Y2}) in {duration}s")
