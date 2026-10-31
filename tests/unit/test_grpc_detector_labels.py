"""
A remote detector must carry captions across the wire (ADR-016 / ADR-017).

The Detection message had `text` but no `label`, so every caption of a
detector behind the gRPC service (OmniParser's Florence-2, the modular
backend's `florence` captioner) was silently dropped: the Viewer showed a
remote modular+florence DOM with no icon label at all (2026-10-31). This
runs a real server and the real client on a loopback port.
"""
from concurrent import futures

import grpc
import numpy as np

from visual_dom.adapters.inbound.grpc.detector_server import DetectorServicer
from visual_dom.adapters.outbound.detectors.grpc_backend import GrpcDetectorBackend
from visual_dom.core.ports.outbound.detector_port import Detection
from visual_dom.generated import detector_pb2, detector_pb2_grpc


class _Backend:
    name = "fake"
    license = "test"

    def detect(self, image):
        return [
            Detection(bounds=(0, 0, 40, 40), visual_type="icon", confidence=0.9,
                      text=None, label="Maximize", interactable=True, source="fake"),
            Detection(bounds=(50, 0, 90, 40), visual_type="icon", confidence=0.9,
                      text="-", label="Minimize", interactable=True, source="fake"),
            Detection(bounds=(0, 50, 90, 90), visual_type="button", confidence=0.9,
                      text="Save", label=None, interactable=True, source="fake"),
        ]


def test_text_and_label_both_survive_the_round_trip():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    detector_pb2_grpc.add_DetectorServicer_to_server(
        DetectorServicer(_Backend(), detector_pb2), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        client = GrpcDetectorBackend(target=f"127.0.0.1:{port}")
        out = client.detect(np.zeros((100, 100, 3), dtype=np.uint8))
    finally:
        server.stop(0)
    assert [(d.text, d.label) for d in out] == [
        (None, "Maximize"), ("-", "Minimize"), ("Save", None)]


def test_a_detection_without_label_reads_as_none():
    d = detector_pb2.Detection(text="7")
    assert not d.HasField("label")
