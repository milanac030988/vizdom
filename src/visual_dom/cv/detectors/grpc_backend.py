"""
gRPC remote detector backend (ADR-017).

Client-side adapter that implements the DetectorBackend port by delegating to a
remote Detector service (see protos/detector.proto and rpc/detector_server.py).
Lets the heavy detector (OmniParser/YOLO) run on a GPU box while the pipeline
runs anywhere.

Requires generated stubs (visual_dom.rpc.detector_pb2[_grpc]) — build them with:
    python -m grpc_tools.protoc -I protos \\
      --python_out=src/visual_dom/rpc --grpc_python_out=src/visual_dom/rpc \\
      protos/detector.proto
and `pip install grpcio grpcio-tools`.
"""

from typing import List, Optional

import numpy as np

from .base import Detection, DetectorBackend
from ...logging_utils import get_logger, log_timing

log = get_logger(__name__)


class GrpcDetectorBackend(DetectorBackend):
    name = "grpc"
    description = "Remote detector over gRPC (heavy model runs on another host)."
    license = "n/a (delegates to the remote backend)"
    requires_gpu = False  # the client does not; the server does

    def __init__(
        self,
        target: str = "localhost:50051",
        image_format: str = "png",
        timeout: float = 120.0,
        text_ensemble: Optional[bool] = None,
        box_threshold: Optional[float] = None,
    ):
        self._target = target
        self._image_format = image_format
        self._timeout = timeout
        self._text_ensemble = text_ensemble
        self._box_threshold = box_threshold

        grpc, pb2, pb2_grpc = self._imports()
        self._pb2 = pb2
        self._channel = grpc.insecure_channel(target)
        self._stub = pb2_grpc.DetectorStub(self._channel)
        log.info("gRPC detector client connected to %s", target)

    @staticmethod
    def _imports():
        import grpc  # raises ImportError if grpcio missing
        from ...rpc import detector_pb2 as pb2
        from ...rpc import detector_pb2_grpc as pb2_grpc
        return grpc, pb2, pb2_grpc

    @classmethod
    def is_available(cls) -> bool:
        try:
            cls._imports()
            return True
        except Exception:
            return False

    def _next_request_id(self) -> str:
        # Correlation id for tracing across client -> service (ADR-017). Kept
        # deterministic-free: server logs echo it. Uses object id + a counter.
        self._counter = getattr(self, "_counter", 0) + 1
        return f"{id(self):x}-{self._counter}"

    def detect(self, image: np.ndarray) -> List[Detection]:
        import cv2

        ext = ".png" if self._image_format == "png" else ".jpg"
        ok, buf = cv2.imencode(ext, image)
        if not ok:
            raise RuntimeError("gRPC detector: failed to encode image")

        params = self._pb2.DetectParams()
        if self._text_ensemble is not None:
            params.text_ensemble = self._text_ensemble
        if self._box_threshold is not None:
            params.box_threshold = self._box_threshold

        req_id = self._next_request_id()
        request = self._pb2.DetectRequest(
            image=buf.tobytes(),
            image_format=self._image_format,
            params=params,
            request_id=req_id,
        )

        with log_timing(log, f"gRPC detect [{req_id}] -> {self._target}"):
            response = self._stub.Detect(request, timeout=self._timeout)

        detections = [
            Detection(
                bounds=(d.bounds.x1, d.bounds.y1, d.bounds.x2, d.bounds.y2),
                visual_type=d.visual_type,
                confidence=d.confidence,
                text=d.text if d.HasField("text") else None,
                interactable=d.interactable if d.HasField("interactable") else None,
                source=d.source or "grpc",
            )
            for d in response.detections
        ]
        log.info("gRPC detect [%s]: %d detections from %s (server %.0f ms)",
                 req_id, len(detections), response.backend, response.infer_ms)
        return detections
