"""
VizDOM capture gRPC server (ADR-018 Phase 2).

Runs on the host/device under test. Instantiates a CaptureStrategy ONCE (by name,
from config/CLI) and serves Grab requests, so the pipeline running elsewhere can
pull screenshots from where the app-under-test actually is.

Usage:
    pip install grpcio grpcio-tools
    # generate stubs first (see rpc/__init__.py), then:
    python -m visual_dom.adapters.inbound.grpc.capture_server --strategy windows --port 50053
    python -m visual_dom.adapters.inbound.grpc.capture_server --strategy android --port 50053 --serial <dev>

Any registered strategy works (--strategy windows|linux|android|camera|<plugin>).
Pass strategy constructor args as --kw key=value (repeatable), e.g.
    --strategy camera --kw device=0
"""

import argparse
import time
from concurrent import futures

import cv2

from visual_dom.logging_utils import get_logger
from visual_dom.adapters.outbound.capture import create_capture, list_captures

log = get_logger(__name__)


def _load_stubs():
    import grpc
    from visual_dom.generated import capture_pb2 as pb2
    from visual_dom.generated import capture_pb2_grpc as pb2_grpc
    return grpc, pb2, pb2_grpc


class CaptureServicer:
    """Wraps a local CaptureStrategy and serves it over gRPC."""

    def __init__(self, strategy, pb2):
        self._strategy = strategy
        self._pb2 = pb2

    def Grab(self, request, context):
        import grpc
        rid = request.request_id or "-"
        t0 = time.perf_counter()
        try:
            image = self._strategy.capture()
        except Exception as e:  # never crash the server on one bad grab
            log.error("Grab [%s] failed: %s", rid, e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return self._pb2.GrabResponse(request_id=rid)
        grab_ms = (time.perf_counter() - t0) * 1000.0

        ok, buf = cv2.imencode(".png", image)
        if not ok:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("could not encode captured image")
            return self._pb2.GrabResponse(request_id=rid)

        h, w = image.shape[:2]
        log.info("Grab [%s]: %dx%d via %s in %.0f ms", rid, w, h, self._strategy.name, grab_ms)
        return self._pb2.GrabResponse(
            image=buf.tobytes(), image_format="png",
            width=int(w), height=int(h),
            strategy=self._strategy.name, request_id=rid, grab_ms=grab_ms,
        )

    def HealthCheck(self, request, context):
        return self._pb2.HealthResponse(
            ready=True, strategy=self._strategy.name,
            platform=getattr(self._strategy, "platform", "any"),
        )


def serve(strategy_name, port, strategy_kwargs, max_workers=4):
    grpc, pb2, pb2_grpc = _load_stubs()
    log.info("Instantiating capture strategy '%s'...", strategy_name)
    strategy = create_capture(strategy_name, **strategy_kwargs)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_CaptureServicer_to_server(CaptureServicer(strategy, pb2), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("VizDOM capture service '%s' listening on :%d", strategy_name, port)
    try:
        server.wait_for_termination()
    finally:
        try:
            strategy.close()
        except Exception:
            pass


def _parse_kw(pairs):
    """['device=0', 'x=1'] -> {'device': '0', 'x': '1'} (values stay strings)."""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--kw expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="VizDOM capture gRPC server (ADR-018)")
    ap.add_argument("--strategy", default=None,
                    help="capture strategy name (default: OS auto-select)")
    ap.add_argument("--port", type=int, default=50053)
    ap.add_argument("--serial", default=None, help="android device serial (adb -s)")
    ap.add_argument("--kw", action="append", default=[],
                    help="strategy constructor arg key=value (repeatable)")
    ap.add_argument("--list", action="store_true", help="list strategies and exit")
    args = ap.parse_args()

    if args.list:
        for c in list_captures():
            print(f"  {c['name']:<14} platform={c['platform']:<8} "
                  f"available={c['available']}  {c['description']}")
        return

    from visual_dom.adapters.outbound.capture import auto_select
    strategy_name = args.strategy or auto_select()
    if not strategy_name:
        raise SystemExit("no capture strategy available; pass --strategy explicitly")

    kwargs = _parse_kw(args.kw)
    if args.serial:
        kwargs["serial"] = args.serial

    serve(strategy_name, args.port, kwargs)


if __name__ == "__main__":
    main()
