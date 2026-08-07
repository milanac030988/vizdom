"""
Remote capture strategy (ADR-018 Phase 2).

`GrpcCaptureStrategy` is a CaptureStrategy that pulls screenshots from a remote
`capture_server` (running on the host/device under test) over gRPC. Because it is
itself a registered strategy, the rest of the system treats "capture from another
machine" exactly like a local grab — select it by name `grpc`:

    from visual_dom.adapters.outbound.capture import create_capture
    cap = create_capture("grpc", target="192.168.1.20:50053")
    image = cap.capture()

gRPC imports are lazy so this module loads (and the registry stays importable)
even where grpcio / the generated stubs are absent — `is_available()` reports it.
"""

import os

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


class GrpcCaptureStrategy(CaptureStrategy):
    name = "grpc"
    platform = "any"
    description = "Pull screenshots from a remote VizDOM capture service (ADR-018)."

    def __init__(self, target: str = None, timeout: float = 30.0,
                 window_title: str = None):
        # target: host:port of the remote capture_server; env fallback for config-only setups
        self.target = target or os.environ.get("VIZDOM_CAPTURE_TARGET", "localhost:50053")
        self.timeout = float(timeout)
        # default window for capture_window() / focus_target() (ADR-021); the title
        # is resolved on the SERVER, so it names a window on the remote machine
        self.target_window = window_title
        self._channel = None
        self._stub = None
        # geometry reported by the most recent Grab (ADR-021); see frame_geometry()
        self._last_geometry = None

    @classmethod
    def is_available(cls) -> bool:
        try:
            import grpc  # noqa: F401
            from visual_dom.generated import capture_pb2, capture_pb2_grpc  # noqa: F401
            return True
        except Exception:
            return False

    def _connect(self):
        if self._stub is not None:
            return
        import grpc
        from visual_dom.generated import capture_pb2_grpc
        self._channel = grpc.insecure_channel(self.target)
        self._stub = capture_pb2_grpc.CaptureStub(self._channel)

    def describe_target(self) -> dict:
        """
        The frame comes from a remote host, so only the endpoint is knowable here.
        (Identifying the app on that host would need a provenance field in the
        capture RPC — noted as future work.)
        """
        return {"target_hint": f"remote capture service {self.target}",
                "capture_target": self.target}

    def capture_window(self, title: str = None):
        """
        Ask the remote service to capture ONLY the target window (ADR-021).

        The crop happens server-side because only that machine knows where the
        window is (and a separate "give me the rectangle" call would race a moving
        window and cost a second round trip). The response carries the geometry, so
        coordinates measured on the crop remain mappable to the remote device's
        coordinate space.

        Returns None when the remote strategy cannot do it (the server answers
        FAILED_PRECONDITION), so the caller can fall back to a full-screen grab.
        """
        import cv2
        from visual_dom.core.ports.outbound.capture_port import CaptureFrame
        from visual_dom.generated import capture_pb2

        wanted = title or self.target_window
        if not wanted:
            return None
        try:
            self._connect()
            resp = self._stub.Grab(
                capture_pb2.GrabRequest(request_id="", window_title=wanted),
                timeout=self.timeout)
        except Exception as exc:  # includes FAILED_PRECONDITION from the server
            log.warning("Remote window capture of %r from %s failed: %s",
                        wanted, self.target, exc)
            return None
        if not resp.image:
            return None
        buf = np.frombuffer(resp.image, dtype=np.uint8)
        image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if image is None:
            log.warning("Could not decode the window image from %s", self.target)
            return None
        if not resp.device_width or not resp.device_height:
            # An older server ignored window_title and sent a full screen: say so
            # rather than pretending the frame is window-scoped.
            log.warning("Capture service %s returned no window geometry - treating "
                        "the frame as a full screen", self.target)
            return None
        return CaptureFrame(
            image=image,
            origin=(resp.origin_x, resp.origin_y),
            device_size=(resp.device_width, resp.device_height),
            device_origin=(resp.device_origin_x, resp.device_origin_y),
            window_title=resp.window_title or wanted,
        )

    def focus_target(self, title: str = None) -> bool:
        """
        Ask the remote capture service to raise the SUT window (ADR-021).

        Focus must happen on the machine that owns the screen, so it travels as
        its own `Focus` RPC; the server runs its local strategy's `focus_target`
        and returns whether it *verified* success. Connection/RPC failures return
        False (never raise) — same contract as the local strategies.
        """
        from visual_dom.generated import capture_pb2
        try:
            self._connect()
            resp = self._stub.Focus(
                capture_pb2.FocusRequest(title=title or self.target_window or "",
                                         request_id=""),
                timeout=self.timeout,
            )
            if not resp.focused and resp.detail:
                log.warning("Remote capture service %s could not focus %r: %s",
                            self.target, title or "<server default>", resp.detail)
            return bool(resp.focused)
        except Exception as exc:  # noqa: BLE001 - best effort by contract
            log.warning("Focus RPC to %s failed: %s", self.target, exc)
            return False

    def frame_geometry(self):
        """
        Geometry reported by the most recent `capture()`, or None.

        The remote service sends it with every frame, so this is a cache rather than
        a second round trip - and it must be read after the grab it belongs to.
        """
        return self._last_geometry

    def capture(self) -> np.ndarray:
        import cv2
        from visual_dom.generated import capture_pb2
        self._connect()
        resp = self._stub.Grab(capture_pb2.GrabRequest(request_id=""), timeout=self.timeout)
        if not resp.image:
            raise RuntimeError(f"remote capture service {self.target} returned no image")
        self._last_geometry = (
            ((resp.origin_x, resp.origin_y),
             (resp.device_origin_x, resp.device_origin_y),
             (resp.device_width, resp.device_height))
            if resp.device_width and resp.device_height else None)
        buf = np.frombuffer(resp.image, dtype=np.uint8)
        image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("could not decode image from remote capture service")
        return image

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
