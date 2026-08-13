"""
Graceful shutdown for the VizDOM gRPC services (detector / capture / actuator).

Each server used to block in ``server.wait_for_termination()``, so Ctrl+C
escaped as a ``KeyboardInterrupt`` traceback — noisy for the user and leaving
the grace-less server to drop in-flight RPCs and hold the port until the process
died. This module gives all three services one consistent, quiet shutdown path.

``run_until_signal`` waits for SIGINT (Ctrl+C) or, where supported, SIGTERM,
then stops the gRPC server with a grace period (so in-flight RPCs finish and the
listen socket is released — the port is reusable immediately) and runs an
optional resource-cleanup callback. Only the expected termination signals are
treated as graceful; any other exception still propagates so real failures stay
visible.
"""

import signal
import threading

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)

# gRPC's own default; enough for a click/capture RPC to finish, short enough
# that an unresponsive server does not hang the shutdown.
DEFAULT_GRACE_SECONDS = 5.0


def run_until_signal(server, name, port, on_shutdown=None,
                     grace=DEFAULT_GRACE_SECONDS):
    """
    Block until an interrupt/termination signal, then stop `server` cleanly.

    Args:
        server: a started ``grpc.Server``.
        name: service name, for the log line.
        port: listening port, for the log line.
        on_shutdown: optional zero-arg callable to release resources (close a
            capture/actuator strategy, a device handle, …). Its failure is
            logged, never raised — teardown must not turn into a new traceback.
        grace: seconds to let in-flight RPCs finish before the socket closes.
    """
    stop_event = threading.Event()

    def _request_stop(signum, _frame):
        # Runs in the main thread between bytecodes; just flip the flag and let
        # the wait loop below do the actual (blocking) teardown.
        try:
            label = signal.Signals(signum).name
        except (ValueError, AttributeError):
            label = str(signum)
        log.info("%s: received %s, shutting down…", name, label)
        stop_event.set()

    # SIGINT  = Ctrl+C everywhere.
    # SIGTERM = the polite kill from service managers / `docker stop` (POSIX).
    # SIGBREAK = Ctrl+Break in a Windows console, and what a parent delivers via
    #            CTRL_BREAK_EVENT; without it Windows would hard-kill the process
    #            (STATUS_CONTROL_C_EXIT) instead of shutting down gracefully.
    candidate_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        candidate_signals.append(signal.SIGBREAK)

    installed = []
    for sig in candidate_signals:
        try:
            signal.signal(sig, _request_stop)
            installed.append(sig)
        except (ValueError, OSError, AttributeError):
            # A signal may be undeliverable on this OS, or signals can only be
            # installed from the main thread; either way, fall back to the
            # KeyboardInterrupt path below.
            pass

    try:
        # Poll rather than wait() forever: on Windows a bare, un-timed wait on a
        # threading primitive does not let the interpreter run the Ctrl+C signal
        # handler promptly. A short timeout keeps Ctrl+C responsive on every OS.
        while not stop_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        # Windows may still surface Ctrl+C as an exception despite the handler.
        log.info("%s: received keyboard interrupt, shutting down…", name)

    log.info("Stopping %s on :%s (grace %.1fs)…", name, port, grace)
    stopped = server.stop(grace)
    # Bound the wait so a wedged RPC cannot hang shutdown forever.
    stopped.wait(grace + 1.0)

    if on_shutdown is not None:
        try:
            on_shutdown()
        except Exception as exc:                       # cleanup must stay quiet
            log.warning("%s: error during resource cleanup: %s", name, exc)

    log.info("%s stopped cleanly.", name)
