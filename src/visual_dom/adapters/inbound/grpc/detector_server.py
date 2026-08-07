"""
VizDOM detector gRPC server (ADR-017).

Runs on the GPU host. Loads a DetectorBackend ONCE (warm model) and serves
Detect requests, so many lightweight clients share one model instance.

Usage:
    pip install grpcio grpcio-tools
    # generate stubs first (see rpc/__init__.py), then:
    python -m visual_dom.adapters.inbound.grpc.detector_server --backend omniparser --port 50051 \\
        --icon-detect models/omniparser/icon_detect/model.pt \\
        --icon-caption models/omniparser/icon_caption_florence

Any registered backend works (--backend uied|yolo|omniparser). The heavy one
(omniparser) is the intended use.
"""

import argparse
import time
from concurrent import futures

import cv2
import numpy as np

from visual_dom.logging_utils import get_logger
from visual_dom.adapters.outbound.detectors import create_detector

log = get_logger(__name__)


def _load_stubs():
    import grpc
    from visual_dom.generated import detector_pb2 as pb2
    from visual_dom.generated import detector_pb2_grpc as pb2_grpc
    return grpc, pb2, pb2_grpc


class DetectorServicer:
    """Wraps a local DetectorBackend and serves it over gRPC."""

    def __init__(self, backend, pb2):
        self._backend = backend
        self._pb2 = pb2

    def Detect(self, request, context):
        rid = request.request_id or "-"
        buf = np.frombuffer(request.image, dtype=np.uint8)
        image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if image is None:
            context.set_code(__import__("grpc").StatusCode.INVALID_ARGUMENT)
            context.set_details("could not decode image")
            return self._pb2.DetectResponse(request_id=rid)

        t0 = time.perf_counter()
        try:
            dets = self._backend.detect(image)
        except Exception as e:  # never crash the server on one bad request
            log.error("Detect [%s] failed: %s", rid, e)
            context.set_code(__import__("grpc").StatusCode.INTERNAL)
            context.set_details(str(e))
            return self._pb2.DetectResponse(request_id=rid)
        infer_ms = (time.perf_counter() - t0) * 1000.0

        resp = self._pb2.DetectResponse(
            request_id=rid, backend=self._backend.name, infer_ms=infer_ms,
        )
        for d in dets:
            x1, y1, x2, y2 = d.bounds
            pd = resp.detections.add()
            pd.bounds.x1, pd.bounds.y1, pd.bounds.x2, pd.bounds.y2 = int(x1), int(y1), int(x2), int(y2)
            pd.visual_type = d.visual_type
            pd.confidence = float(d.confidence)
            pd.source = d.source or self._backend.name
            if d.text is not None:
                pd.text = d.text
            if d.interactable is not None:
                pd.interactable = bool(d.interactable)
        log.info("Detect [%s]: %d detections in %.0f ms", rid, len(dets), infer_ms)
        return resp

    def HealthCheck(self, request, context):
        return self._pb2.HealthResponse(
            ready=True, backend=self._backend.name,
            model_info=getattr(self._backend, "license", ""),
        )


def serve(backend_name, port, detector_kwargs, max_workers=4):
    grpc, pb2, pb2_grpc = _load_stubs()
    log.info("Loading detector backend '%s' (warm model)...", backend_name)
    backend = create_detector(backend_name, **detector_kwargs)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_DetectorServicer_to_server(DetectorServicer(backend, pb2), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("VizDOM detector service '%s' listening on :%d", backend_name, port)
    server.wait_for_termination()


def _resolve_omniparser_paths(args) -> dict:
    """
    Fill in OmniParser weight/repo paths the caller didn't give, from the
    standard project locations — the same auto-resolution the in-process
    pipeline does, so the service does not need three long flags to start.
    Explicit flags and OMNIPARSER_* env vars still win.
    """
    import os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                        "..", "..", "..", "..", ".."))
    out = {}
    if not args.icon_detect and not os.environ.get("OMNIPARSER_ICON_DETECT"):
        cand = os.path.join(root, "models", "omniparser", "icon_detect", "model.pt")
        if os.path.exists(cand):
            out["icon_detect_path"] = cand
    if not args.icon_caption and not os.environ.get("OMNIPARSER_ICON_CAPTION"):
        cand = os.path.join(root, "models", "omniparser", "icon_caption_florence")
        if os.path.isdir(cand):
            out["icon_caption_path"] = cand
    if not args.omniparser_root and not os.environ.get("OMNIPARSER_ROOT"):
        cand = os.path.join(root, "third_party", "OmniParser")
        if os.path.isdir(cand):
            out["omniparser_root"] = cand
    return out


def _build_ocr_provider(engine: str, use_gpu: bool):
    """
    Build the OCR-ensemble provider for a server-side OmniParser (ADR-016).

    The ensemble normally injects the *client* pipeline's upscaling OCR into
    OmniParser, but that is a Python callable and cannot cross gRPC — so a
    remote detector would silently fall back to OmniParser's own (weaker) OCR.
    Constructing the TextDetector here restores the prefer-external ensemble on
    the service side, which is what recovers small/low-contrast text rows.
    """
    from visual_dom.adapters.outbound.ocr.text_detector import TextDetector
    detector = TextDetector(ocr_engine=engine, gpu=use_gpu, upscale=True)
    log.info("OCR ensemble enabled on the service (engine=%s)", engine)
    return lambda image: [(t.bounds, t.text) for t in detector.detect(image)]


def main():
    ap = argparse.ArgumentParser(description="VizDOM detector gRPC server (ADR-017)")
    ap.add_argument("--backend", default="omniparser", choices=["uied", "yolo", "omniparser"])
    ap.add_argument("--port", type=int, default=50051)
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--icon-detect", default=None, help="OmniParser icon_detect .pt")
    ap.add_argument("--icon-caption", default=None, help="OmniParser icon_caption dir")
    ap.add_argument("--omniparser-root", default=None)
    ap.add_argument("--yolo-model", default=None)
    ap.add_argument("--ocr", default=None, metavar="ENGINE",
                    help="OCR engine for the OmniParser text ensemble, run ON THIS "
                         "SERVICE (easyocr|paddleocr|tesseract). Without it a remote "
                         "OmniParser uses only its own OCR, since the client's OCR "
                         "callable cannot cross gRPC.")
    ap.add_argument("--box-threshold", type=float, default=None,
                    help="OmniParser YOLO confidence cutoff (default 0.05); lower "
                         "to ~0.03 to recover faint glyphs.")
    args = ap.parse_args()

    # Only backends that accept use_gpu get it (UIED is CPU-only, no such arg).
    kwargs = {}
    use_gpu = not args.no_gpu
    if args.backend in ("yolo", "omniparser"):
        kwargs["use_gpu"] = use_gpu
    if args.backend == "omniparser":
        if args.icon_detect:
            kwargs["icon_detect_path"] = args.icon_detect
        if args.icon_caption:
            kwargs["icon_caption_path"] = args.icon_caption
        if args.omniparser_root:
            kwargs["omniparser_root"] = args.omniparser_root
        kwargs.update(_resolve_omniparser_paths(args))
        if args.box_threshold is not None:
            kwargs["box_threshold"] = args.box_threshold
        if args.ocr:
            kwargs["ocr_provider"] = _build_ocr_provider(args.ocr, use_gpu)
            kwargs["ocr_ensemble"] = True
    elif args.backend == "yolo" and args.yolo_model:
        kwargs["model_path"] = args.yolo_model

    serve(args.backend, args.port, kwargs)


if __name__ == "__main__":
    main()
