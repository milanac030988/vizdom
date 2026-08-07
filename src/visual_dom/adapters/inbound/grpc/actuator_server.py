"""
VizDOM actuator gRPC server (ADR-019 Phase 2).

Runs on the host/device under test (or a robot arm's controller). Instantiates an
ActuatorStrategy ONCE (by name, from config/CLI) and serves input actions, so the
pipeline/orchestration running elsewhere can drive input where the app-under-test
actually is. Coordinates arrive NORMALIZED [0,1] + source image size; the strategy
maps them to its own device space.

Usage:
    pip install grpcio grpcio-tools
    # generate stubs first (see rpc/__init__.py), then:
    python -m visual_dom.adapters.inbound.grpc.actuator_server --strategy desktop --port 50054
    python -m visual_dom.adapters.inbound.grpc.actuator_server --strategy android --port 50054 --serial <dev>
    python -m visual_dom.adapters.inbound.grpc.actuator_server --strategy robot-arm --kw port=COM3

Pass strategy constructor args as --kw key=value (repeatable).
"""

import argparse
import time
from concurrent import futures

from visual_dom.logging_utils import get_logger
from visual_dom.adapters.outbound.actuator import create_actuator, list_actuators

log = get_logger(__name__)


def _load_stubs():
    import grpc
    from visual_dom.generated import actuator_pb2 as pb2
    from visual_dom.generated import actuator_pb2_grpc as pb2_grpc
    return grpc, pb2, pb2_grpc


def _img_size(msg):
    """Proto ImageSize -> (w, h) tuple, or None when unset (both zero)."""
    if msg is None:
        return None
    w, h = int(msg.width), int(msg.height)
    return (w, h) if (w > 0 and h > 0) else None


class ActuatorServicer:
    """Wraps a local ActuatorStrategy and serves it over gRPC."""

    def __init__(self, strategy, pb2):
        self._strategy = strategy
        self._pb2 = pb2

    def _run(self, rid, context, fn):
        """Execute one action, timing it and never crashing the server."""
        import grpc
        t0 = time.perf_counter()
        try:
            fn()
        except Exception as e:
            log.error("action [%s] failed: %s", rid or "-", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return self._pb2.ActionResponse(ok=False, actuator=self._strategy.name, request_id=rid)
        ms = (time.perf_counter() - t0) * 1000.0
        return self._pb2.ActionResponse(
            ok=True, actuator=self._strategy.name, request_id=rid, action_ms=ms)

    def Tap(self, request, context):
        return self._run(request.request_id, context, lambda: self._strategy.tap(
            request.nx, request.ny, _img_size(request.image_size),
            click_type=request.click_type or "single"))

    def TypeText(self, request, context):
        return self._run(request.request_id, context,
                         lambda: self._strategy.type_text(request.text))

    def PressKey(self, request, context):
        return self._run(request.request_id, context,
                         lambda: self._strategy.press_key(request.key))

    def Scroll(self, request, context):
        return self._run(request.request_id, context, lambda: self._strategy.scroll(
            request.nx, request.ny, direction=request.direction or "down",
            amount=int(request.amount) or 1, image_size=_img_size(request.image_size)))

    def Swipe(self, request, context):
        return self._run(request.request_id, context, lambda: self._strategy.swipe(
            request.nx1, request.ny1, request.nx2, request.ny2,
            image_size=_img_size(request.image_size),
            duration=request.duration or 0.3))

    def Focus(self, request, context):
        """
        Raise the SUT window on THIS machine so subsequent Tap/TypeText land on it
        (ADR-021). Deliberately not routed through `_run`: a refusal is a normal
        response carrying a reason, not a gRPC error.
        """
        rid = request.request_id or "-"
        title = request.title or None
        try:
            ok = bool(self._strategy.focus_target(title))
        except Exception as e:      # a strategy must not raise, but never trust it
            log.error("Focus [%s] failed: %s", rid, e)
            return self._pb2.FocusResponse(focused=False, detail=str(e),
                                           actuator=self._strategy.name, request_id=rid)
        if ok:
            detail = f"focused {title!r}" if title else "focused the configured target"
        else:
            detail = (f"could not focus {title!r}" if title else
                      "no target given and the strategy has no configured default")
        log.info("Focus [%s]: %s (%s)", rid, ok, detail)
        return self._pb2.FocusResponse(focused=ok, detail=detail,
                                       actuator=self._strategy.name, request_id=rid)

    def HealthCheck(self, request, context):
        return self._pb2.HealthResponse(
            ready=True, actuator=self._strategy.name,
            platform=getattr(self._strategy, "platform", "any"))


def serve(strategy_name, port, strategy_kwargs, max_workers=4):
    grpc, pb2, pb2_grpc = _load_stubs()
    log.info("Instantiating actuator strategy '%s'...", strategy_name)
    strategy = create_actuator(strategy_name, **strategy_kwargs)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_ActuatorServicer_to_server(ActuatorServicer(strategy, pb2), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("VizDOM actuator service '%s' listening on :%d", strategy_name, port)
    try:
        server.wait_for_termination()
    finally:
        try:
            strategy.close()
        except Exception:
            pass


def _parse_kw(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--kw expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="VizDOM actuator gRPC server (ADR-019)")
    ap.add_argument("--strategy", default=None,
                    help="actuator strategy name (default: OS auto-select)")
    ap.add_argument("--port", type=int, default=50054)
    ap.add_argument("--serial", default=None, help="android device serial (adb -s)")
    ap.add_argument("--window-title", default=None,
                    help="default window title (Android: package or package/.Activity) "
                         "raised by the Focus RPC when the client sends no title")
    ap.add_argument("--kw", action="append", default=[],
                    help="strategy constructor arg key=value (repeatable)")
    ap.add_argument("--list", action="store_true", help="list strategies and exit")
    args = ap.parse_args()

    if args.list:
        for c in list_actuators():
            print(f"  {c['name']:<12} platform={c['platform']:<8} "
                  f"available={c['available']}  {c['description']}")
        return

    from visual_dom.adapters.outbound.actuator import auto_select
    strategy_name = args.strategy or auto_select()
    if not strategy_name:
        raise SystemExit("no actuator strategy available; pass --strategy explicitly")

    kwargs = _parse_kw(args.kw)
    if args.serial:
        kwargs["serial"] = args.serial
    if args.window_title:
        # Android names its target by component, the desktop actuator by title
        kwargs["activity" if strategy_name == "android" else "window_title"] = args.window_title

    serve(strategy_name, args.port, kwargs)


if __name__ == "__main__":
    main()
