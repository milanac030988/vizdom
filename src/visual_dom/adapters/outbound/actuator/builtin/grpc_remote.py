"""
Remote actuator strategy (ADR-019 Phase 2).

`GrpcActuatorStrategy` is an ActuatorStrategy that forwards input actions to a
remote `actuator_server` (running on the SUT host / device / robot-arm controller)
over gRPC. Because it is itself a registered strategy, the rest of the system
treats "actuate on another machine" exactly like local input - select it by name
`grpc`:

    from visual_dom.adapters.outbound.actuator import create_actuator
    act = create_actuator("grpc", target="192.168.1.20:50054")
    act.tap(0.5, 0.5, image_size=(1920, 1080))

Coordinates stay NORMALIZED on the wire; the *server-side* strategy maps them to
its own device space, so this client does no coordinate math. gRPC imports are
lazy so the registry stays importable where grpcio / the stubs are absent -
`is_available()` reports it.
"""

import os
from typing import Optional, Tuple

from visual_dom.core.ports.outbound.actuator_port import ActuatorStrategy
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


class GrpcActuatorStrategy(ActuatorStrategy):
    name = "grpc"
    platform = "any"
    description = "Drive input on a remote VizDOM actuator service (ADR-019)."

    def __init__(self, target: str = None, timeout: float = 30.0):
        self.target = target or os.environ.get("VIZDOM_ACTUATOR_TARGET", "localhost:50054")
        self.timeout = float(timeout)
        self._channel = None
        self._stub = None

    @classmethod
    def is_available(cls) -> bool:
        try:
            import grpc  # noqa: F401
            from visual_dom.generated import actuator_pb2, actuator_pb2_grpc  # noqa: F401
            return True
        except Exception:
            return False

    def _connect(self):
        if self._stub is not None:
            return
        import grpc
        from visual_dom.generated import actuator_pb2_grpc
        self._channel = grpc.insecure_channel(self.target)
        self._stub = actuator_pb2_grpc.ActuatorStub(self._channel)

    def _img(self, image_size: Optional[Tuple[int, int]]):
        from visual_dom.generated import actuator_pb2
        if not image_size:
            return actuator_pb2.ImageSize(width=0, height=0)
        return actuator_pb2.ImageSize(width=int(image_size[0]), height=int(image_size[1]))

    def _check(self, resp):
        if not resp.ok:
            raise RuntimeError(f"remote actuator '{self.target}' reported failure")

    def tap(self, nx, ny, image_size=None, click_type="single"):
        from visual_dom.generated import actuator_pb2
        self._connect()
        self._check(self._stub.Tap(actuator_pb2.TapRequest(
            nx=nx, ny=ny, image_size=self._img(image_size), click_type=click_type),
            timeout=self.timeout))

    def type_text(self, text: str) -> None:
        from visual_dom.generated import actuator_pb2
        self._connect()
        self._check(self._stub.TypeText(
            actuator_pb2.TypeTextRequest(text=text), timeout=self.timeout))

    def press_key(self, key: str) -> None:
        from visual_dom.generated import actuator_pb2
        self._connect()
        self._check(self._stub.PressKey(
            actuator_pb2.PressKeyRequest(key=key), timeout=self.timeout))

    def scroll(self, nx, ny, direction="down", amount=1, image_size=None):
        from visual_dom.generated import actuator_pb2
        self._connect()
        self._check(self._stub.Scroll(actuator_pb2.ScrollRequest(
            nx=nx, ny=ny, direction=direction, amount=int(amount),
            image_size=self._img(image_size)), timeout=self.timeout))

    def swipe(self, nx1, ny1, nx2, ny2, image_size=None, duration=0.3):
        from visual_dom.generated import actuator_pb2
        self._connect()
        self._check(self._stub.Swipe(actuator_pb2.SwipeRequest(
            nx1=nx1, ny1=ny1, nx2=nx2, ny2=ny2,
            image_size=self._img(image_size), duration=duration), timeout=self.timeout))

    def focus_target(self, title: Optional[str] = None) -> bool:
        """
        Ask the remote actuator service to raise the SUT window (ADR-021).

        Unlike the action RPCs this does NOT raise on failure: focus is advisory
        (the caller decides whether to abort), and a False must stay
        distinguishable from an exception. Returns the server's *verified* result.
        """
        from visual_dom.generated import actuator_pb2
        try:
            self._connect()
            resp = self._stub.Focus(
                actuator_pb2.FocusRequest(title=title or ""), timeout=self.timeout)
            if not resp.focused and resp.detail:
                log.warning("Remote actuator %s could not focus %r: %s",
                            self.target, title or "<server default>", resp.detail)
            return bool(resp.focused)
        except Exception as exc:  # noqa: BLE001 - best effort by contract
            log.warning("Focus RPC to %s failed: %s", self.target, exc)
            return False

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
