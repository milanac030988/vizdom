"""
Graceful shutdown helper for the gRPC services (`run_until_signal`).

The three services used to block in `server.wait_for_termination()`, so Ctrl+C
escaped as a KeyboardInterrupt traceback and the port was held until the process
died. `run_until_signal` instead stops the server with a grace period and runs a
cleanup callback, quietly.

The tests drive the helper without sending a real OS signal: `os.kill(pid,
SIGINT)` is unreliable and on Windows terminates the process outright. Instead
they capture the handler the helper registers and invoke it the way the OS
would, and separately exercise the Windows KeyboardInterrupt path.
"""

import signal
import threading

import pytest

from visual_dom.adapters.inbound.grpc import _shutdown


class _Done:
    """grpc.Server.stop() returns an Event-like object; this one is immune to
    the tests' global Event.wait monkeypatch, so the helper's post-stop wait is
    not itself hijacked."""

    def wait(self, timeout=None):
        return True


class FakeServer:
    """Records how it was stopped."""

    def __init__(self):
        self.stop_grace = None
        self.stopped = threading.Event()

    def stop(self, grace):
        self.stop_grace = grace
        self.stopped.set()
        return _Done()      # nothing in flight; termination completes at once


def _arm(monkeypatch):
    """
    Make the helper's first wait deliver a SIGINT to the handler it registered.

    Returns the FakeServer. signal.signal is stubbed to capture handlers rather
    than install them (so the test process is untouched), and Event.wait is
    stubbed to fire that handler once, then behave normally.
    """
    captured = {}
    monkeypatch.setattr(_shutdown.signal, "signal",
                        lambda sig, handler: captured.__setitem__(sig, handler))

    real_wait = threading.Event.wait
    fired = {"done": False}

    def fake_wait(self, timeout=None):
        if not fired["done"]:
            fired["done"] = True
            captured[signal.SIGINT](signal.SIGINT, None)   # OS delivers Ctrl+C
        return real_wait(self, 0)

    monkeypatch.setattr(_shutdown.threading.Event, "wait", fake_wait)
    return captured


def test_signal_triggers_graceful_stop(monkeypatch):
    _arm(monkeypatch)
    server = FakeServer()

    _shutdown.run_until_signal(server, "test", 50051, grace=2.0)

    assert server.stopped.is_set(), "server was never stopped"
    assert server.stop_grace == 2.0, "grace period not passed to stop()"


def test_cleanup_callback_runs_on_shutdown(monkeypatch):
    _arm(monkeypatch)
    server = FakeServer()
    cleaned = threading.Event()

    _shutdown.run_until_signal(server, "test", 50051,
                               on_shutdown=cleaned.set, grace=1.0)

    assert cleaned.is_set(), "on_shutdown was not called"


def test_cleanup_failure_is_swallowed(monkeypatch):
    """A failing cleanup must not turn a graceful shutdown into a traceback."""
    _arm(monkeypatch)
    server = FakeServer()

    def boom():
        raise RuntimeError("device would not release")

    # Must return normally despite the cleanup error.
    _shutdown.run_until_signal(server, "test", 50051, on_shutdown=boom, grace=1.0)
    assert server.stopped.is_set()


def test_keyboardinterrupt_path_still_stops_and_cleans(monkeypatch):
    """
    The Windows path: Ctrl+C surfaces as an exception from the wait loop despite
    the handler. The server must still be stopped and cleanup still run.
    """
    server = FakeServer()
    cleaned = threading.Event()
    calls = {"n": 0}

    def fake_wait(self, timeout=None):
        calls["n"] += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(_shutdown.signal, "signal", lambda *a: None)
    monkeypatch.setattr(_shutdown.threading.Event, "wait", fake_wait)

    _shutdown.run_until_signal(server, "test", 50051,
                               on_shutdown=cleaned.set, grace=1.0)

    assert calls["n"] >= 1
    assert server.stopped.is_set()
    assert cleaned.is_set()


def test_missing_signal_support_falls_back(monkeypatch):
    """
    If signals cannot be installed (SIGTERM on Windows, non-main thread), the
    helper must not crash - it falls through to the wait loop.
    """
    server = FakeServer()

    def refuse(*_a):
        raise ValueError("signal only works in main thread")

    monkeypatch.setattr(_shutdown.signal, "signal", refuse)
    monkeypatch.setattr(_shutdown.threading.Event, "wait",
                        lambda self, timeout=None: (_ for _ in ()).throw(KeyboardInterrupt()))

    _shutdown.run_until_signal(server, "test", 50051, grace=1.0)
    assert server.stopped.is_set()
