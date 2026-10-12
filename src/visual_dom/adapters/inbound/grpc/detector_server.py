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

Any registered backend works (--backend uied|yolo|omniparser|modular). The
heavy ones (omniparser, or modular with its omniparser/florence stages) are the
intended use. OmniParser paths default to the OMNIPARSER_* env vars, then the
standard project locations, so the flags above are usually unnecessary.
"""

import argparse
import time
from concurrent import futures

import cv2
import numpy as np

from visual_dom.logging_utils import get_logger
from visual_dom.adapters.outbound.detectors import create_detector, resolve_omniparser_paths

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
    from ._shutdown import run_until_signal

    grpc, pb2, pb2_grpc = _load_stubs()
    log.info("Loading detector backend '%s' (warm model)...", backend_name)
    backend = create_detector(backend_name, **detector_kwargs)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_DetectorServicer_to_server(DetectorServicer(backend, pb2), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("VizDOM detector service '%s' listening on :%d", backend_name, port)

    def _cleanup():
        close = getattr(backend, "close", None)
        if callable(close):
            close()

    run_until_signal(server, f"detector '{backend_name}'", port, on_shutdown=_cleanup)


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
    ap.add_argument("--backend", default="omniparser",
                    choices=["uied", "yolo", "omniparser", "modular"])
    ap.add_argument("--captioner", default="none", choices=["none", "florence"],
                    help="modular only: stage-3 captioner. 'florence' loads the "
                         "OmniParser caption model (~1 GB VRAM); 'none' leaves "
                         "icons unlabelled and desc= falls back to ADR-022 tier-2.")
    ap.add_argument("--regions", default="auto",
                    choices=["auto", "omniparser", "uied"],
                    help="modular only: stage-1 region proposer. 'auto' picks "
                         "omniparser when its weights are found, else uied (CPU); "
                         "an explicit 'omniparser' fails fast if they are absent.")
    ap.add_argument("--port", type=int, default=50051)
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--icon-detect", default=None, help="OmniParser icon_detect .pt")
    ap.add_argument("--icon-caption", default=None, help="OmniParser icon_caption dir")
    ap.add_argument("--omniparser-root", default=None)
    ap.add_argument("--yolo-model", default=None)
    ap.add_argument("--ocr", default=None, metavar="ENGINE",
                    help="OCR engine run ON THIS SERVICE (easyocr|paddleocr|"
                         "tesseract|none). omniparser: feeds the text ensemble; "
                         "without it a remote OmniParser uses only its own OCR, "
                         "since the client's OCR callable cannot cross gRPC. "
                         "modular: the stage-2 engine (default easyocr; 'none' "
                         "skips OCR).")
    ap.add_argument("--box-threshold", type=float, default=None,
                    help="OmniParser YOLO confidence cutoff (default 0.05); lower "
                         "to ~0.03 to recover faint glyphs. Applies to omniparser "
                         "and to modular's omniparser region proposer.")
    args = ap.parse_args()

    # Only backends that accept use_gpu get it (UIED is CPU-only, no such arg).
    kwargs = {}
    use_gpu = not args.no_gpu
    if args.backend in ("yolo", "omniparser"):
        kwargs["use_gpu"] = use_gpu
    if args.backend != "modular":
        for flag, value, default in (("--regions", args.regions, "auto"),
                                     ("--captioner", args.captioner, "none")):
            if value != default:
                log.warning("%s applies to --backend modular only; ignored", flag)
    # Explicit flags, then OMNIPARSER_* env vars, then the standard locations.
    paths = resolve_omniparser_paths(omniparser_root=args.omniparser_root,
                                     icon_detect_path=args.icon_detect,
                                     icon_caption_path=args.icon_caption)
    if args.backend == "omniparser":
        kwargs.update(paths)
        if args.box_threshold is not None:
            kwargs["box_threshold"] = args.box_threshold
        if args.ocr and args.ocr != "none":
            kwargs["ocr_provider"] = _build_ocr_provider(args.ocr, use_gpu)
            kwargs["ocr_ensemble"] = True
    elif args.backend == "yolo" and args.yolo_model:
        kwargs["model_path"] = args.yolo_model
    elif args.backend == "modular":
        # ADR-027 composite. The stages take the paths explicitly; region
        # proposer 'auto' degrades the STAGE to uied (CPU) when OmniParser
        # cannot run here, never the whole service.
        kwargs.update(paths)
        kwargs["use_gpu"] = use_gpu
        kwargs["region_proposer"] = args.regions
        if args.regions == "omniparser" and "icon_detect_path" not in paths:
            raise SystemExit("--regions omniparser needs the icon_detect "
                             "weights (--icon-detect or OMNIPARSER_ICON_DETECT)")
        if args.box_threshold is not None:
            kwargs["box_threshold"] = args.box_threshold
        # --ocr names the stage-2 engine here (the backend runs OCR itself),
        # unlike the omniparser backend where it builds the ensemble provider.
        if args.ocr:
            kwargs["ocr_engine"] = args.ocr
        kwargs["captioner"] = args.captioner
        if args.captioner == "florence" and "icon_caption_path" not in paths:
            raise SystemExit("--captioner florence needs the OmniParser caption "
                             "weights (--icon-caption or OMNIPARSER_ICON_CAPTION)")
        log.info("modular stages: regions=%s, ocr=%s, captioner=%s",
                 args.regions, args.ocr or "easyocr", args.captioner)

    serve(args.backend, args.port, kwargs)


if __name__ == "__main__":
    main()
