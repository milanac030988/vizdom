"""
Remote capture strategy (ADR-018 Phase 2).

`GrpcCaptureStrategy` is a CaptureStrategy that pulls screenshots from a remote
`capture_server` (running on the host/device under test) over gRPC. Because it is
itself a registered strategy, the rest of the system treats "capture from another
machine" exactly like a local grab — select it by name `grpc`:

    from visual_dom.capture import create_capture
    cap = create_capture("grpc", target="192.168.1.20:50053")
    image = cap.capture()

gRPC imports are lazy so this module loads (and the registry stays importable)
even where grpcio / the generated stubs are absent — `is_available()` reports it.
"""

import os

import numpy as np

from ..base import CaptureStrategy


class GrpcCaptureStrategy(CaptureStrategy):
    name = "grpc"
    platform = "any"
    description = "Pull screenshots from a remote VizDOM capture service (ADR-018)."

    def __init__(self, target: str = None, timeout: float = 30.0):
        # target: host:port of the remote capture_server; env fallback for config-only setups
        self.target = target or os.environ.get("VIZDOM_CAPTURE_TARGET", "localhost:50053")
        self.timeout = float(timeout)
        self._channel = None
        self._stub = None

    @classmethod
    def is_available(cls) -> bool:
        try:
            import grpc  # noqa: F401
            from ...rpc import capture_pb2, capture_pb2_grpc  # noqa: F401
            return True
        except Exception:
            return False

    def _connect(self):
        if self._stub is not None:
            return
        import grpc
        from ...rpc import capture_pb2_grpc
        self._channel = grpc.insecure_channel(self.target)
        self._stub = capture_pb2_grpc.CaptureStub(self._channel)

    def capture(self) -> np.ndarray:
        import cv2
        from ...rpc import capture_pb2
        self._connect()
        resp = self._stub.Grab(capture_pb2.GrabRequest(request_id=""), timeout=self.timeout)
        if not resp.image:
            raise RuntimeError(f"remote capture service {self.target} returned no image")
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
