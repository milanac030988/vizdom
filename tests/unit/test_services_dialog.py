"""
Services dialog: health polling must not block the UI thread.

Each `HealthCheck` is a gRPC call with a 1 s deadline that blocks for most of
that second when the service is down; three of them ran synchronously on the UI
thread (including from the constructor), so opening the window froze for up to
~3 s. Polling now runs on a `_HealthWorker` QThread and reports back per row.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from pathlib import Path                                        # noqa: E402

from PyQt5.QtCore import QThread                                # noqa: E402
from PyQt5.QtWidgets import QApplication                        # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app):
    from visual_dom_viewer.ui.services_dialog import ServicesDialog
    dlg = ServicesDialog(repo_root=Path.cwd())
    yield dlg
    dlg.shutdown()


def test_constructor_does_not_poll_synchronously(dialog):
    """The first poll is deferred to the event loop, so __init__ never blocks
    on a HealthCheck. No worker has been spawned yet at construction time."""
    assert dialog._worker is None


def test_poll_runs_on_a_worker_thread(app, dialog):
    dialog._poll_health()
    assert isinstance(dialog._worker, QThread)
    # It is a real thread, distinct from the GUI thread.
    assert dialog._worker is not None
    dialog._worker.wait(3000)


def test_overlapping_poll_is_skipped(app, dialog):
    """A slow sweep must not stack up behind the 4 s timer."""
    dialog._poll_health()
    first = dialog._worker
    dialog._poll_health()          # while the first may still be running
    if first.isRunning():
        assert dialog._worker is first, "a second worker was spawned over a live one"
    first.wait(3000)


def test_port_check_is_fast_for_a_closed_port():
    """The socket pre-check short-circuits before the expensive gRPC path."""
    import time

    from visual_dom_viewer.ui.services_dialog import _HealthWorker

    start = time.perf_counter()
    open_ = _HealthWorker._port_open("59999")   # nothing listening
    elapsed = time.perf_counter() - start
    assert open_ is False
    assert elapsed < 0.5, f"closed-port check took {elapsed:.2f}s"


def test_apply_health_updates_row_state(dialog):
    dialog._apply_health("detector", True, "omniparser")
    row = dialog._rows["detector"]
    assert row.state == "running"
    assert "omniparser" in row.status.text()
    assert row.external is True      # not started by the dialog

    dialog._apply_health("detector", False, "not reachable")
    assert dialog._rows["detector"].state == "stopped"


def test_apply_health_ignores_unknown_key(dialog):
    dialog._apply_health("nonesuch", True, "x")   # must not raise
