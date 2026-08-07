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
        wanted = getattr(request, "window_title", "") or ""
        t0 = time.perf_counter()
        frame = None
        try:
            if wanted:
                # Window-scoped grab: only THIS machine knows where the window is,
                # which is why the crop happens server-side (ADR-021).
                frame = self._strategy.capture_window(wanted)
                if frame is None:
                    msg = (f"strategy '{self._strategy.name}' could not capture the "
                           f"window {wanted!r} (unsupported, not found, ambiguous, "
                           f"or could not be raised)")
                    log.warning("Grab [%s] refused: %s", rid, msg)
                    context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                    context.set_details(msg)
                    return self._pb2.GrabResponse(request_id=rid)
                image = frame.image
            else:
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
        resp = self._pb2.GrabResponse(
            image=buf.tobytes(), image_format="png",
            width=int(w), height=int(h),
            strategy=self._strategy.name, request_id=rid, grab_ms=grab_ms,
        )
        geometry = None
        if frame is None:
            # Even a full-screen grab needs its place in the device space: the
            # monitor it came from may not start at (0, 0) (ADR-021).
            try:
                geometry = self._strategy.frame_geometry()
            except Exception:
                geometry = None
            if geometry:
                (ox, oy), (dox, doy), (dw, dh) = geometry
                resp.origin_x, resp.origin_y = int(ox), int(oy)
                resp.device_origin_x, resp.device_origin_y = int(dox), int(doy)
                resp.device_width, resp.device_height = int(dw), int(dh)

        if frame is not None:
            # Geometry travels with the pixels; without it the client cannot map
            # crop coordinates back to the device space (ADR-021).
            resp.origin_x, resp.origin_y = int(frame.origin[0]), int(frame.origin[1])
            resp.device_origin_x = int(frame.device_origin[0])
            resp.device_origin_y = int(frame.device_origin[1])
            resp.device_width = int(frame.device_size[0])
            resp.device_height = int(frame.device_size[1])
            resp.window_title = frame.window_title or wanted
            log.info("Grab [%s]: window %r %dx%d at origin (%d,%d) of %dx%d via %s "
                     "in %.0f ms", rid, resp.window_title, w, h,
                     resp.origin_x, resp.origin_y, resp.device_width,
                     resp.device_height, self._strategy.name, grab_ms)
        else:
            log.info("Grab [%s]: %dx%d via %s in %.0f ms", rid, w, h,
                     self._strategy.name, grab_ms)
        return resp

    def Focus(self, request, context):
        """
        Raise the SUT window on THIS machine before the client grabs (ADR-021).

        Focus can only be done where the screen is, which is why it is an RPC and
        not client-side logic. A refusal is a normal response (`focused=False`
        plus a reason), not a gRPC error: the client decides whether an unfocusable
        window should fail the test.
        """
        rid = request.request_id or "-"
        title = request.title or None
        try:
            ok = bool(self._strategy.focus_target(title))
        except Exception as e:      # a strategy must not raise, but never trust it
            log.error("Focus [%s] failed: %s", rid, e)
            return self._pb2.FocusResponse(focused=False, detail=str(e),
                                           strategy=self._strategy.name, request_id=rid)
        if ok:
            detail = f"focused {title!r}" if title else "focused the configured target"
        else:
            detail = (f"could not focus {title!r}" if title else
                      "no target given and the strategy has no configured default")
        log.info("Focus [%s]: %s (%s)", rid, ok, detail)
        return self._pb2.FocusResponse(focused=ok, detail=detail,
                                       strategy=self._strategy.name, request_id=rid)

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
    ap.add_argument("--window-title", default=None,
                    help="default window title (Android: package or package/.Activity) "
                         "raised by the Focus RPC when the client sends no title")
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
    if args.window_title:
        # Android names its target by component, the desktop grabbers by title
        kwargs["activity" if strategy_name == "android" else "window_title"] = args.window_title

    serve(strategy_name, args.port, kwargs)


if __name__ == "__main__":
    main()
