"""
Harness for test_analyze_reentrancy: runs in a SUBPROCESS.

Constructing the full VisualDOMViewerWindow inside the pytest process aborts
natively in Qt's offscreen platform (pytest's IO capture interacts badly with
the window teardown), while the identical flow is stable as a plain script -
so the test invokes this file with the project's interpreter and asserts on
its output.

Exit code 0 + the PASS markers on stdout = the re-entrancy guard works:
  phase 1: a re-entrant analyze (what a queued F5 press does when the event
           pump dispatches it mid-analysis) is refused; the trigger actions
           are disabled during the run and restored after.
  phase 2: an exploding pipeline still releases the guard.
"""

import os
import shutil
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QBuffer, QByteArray  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841
    from visual_dom_viewer.ui.main_window import VisualDOMViewerWindow
    import visual_dom.core.domain.pipeline as pl

    window = VisualDOMViewerWindow()

    img = QImage(8, 8, QImage.Format_RGB32)
    img.fill(0xFFFFFF)
    buf = QBuffer(QByteArray())
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    shot = bytes(buf.data())

    sessions = Path("output/sessions")
    before = {p.name for p in sessions.iterdir()} if sessions.is_dir() else set()

    try:
        # ---- phase 1: re-entry refused, actions disabled during the run ----
        runs = {"inner": 0, "nested": False}
        state = {}

        def fake_process(self, image, **kwargs):
            runs["inner"] += 1
            state["capture"] = window._capture_action.isEnabled()
            state["refresh"] = window._refresh_action.isEnabled()
            if not runs["nested"]:
                runs["nested"] = True
                window._do_analyze_screenshot(shot)   # queued F5 dispatch
            return {"elements": [], "image_size": {"width": 8, "height": 8},
                    "stats": {"text_detected": 0}}

        window._refresh_action.setEnabled(True)
        with mock.patch.object(pl.VisualDOMPipeline, "process", fake_process):
            window._do_analyze_screenshot(shot)

        assert runs["nested"], "harness never attempted re-entry"
        assert runs["inner"] == 1, f"pipeline ran {runs['inner']}x"
        assert state == {"capture": False, "refresh": False}, state
        assert window._analysis_running is False
        assert window._refresh_action.isEnabled() is True
        print("PASS phase1: re-entry refused, actions disabled+restored")

        # ---- phase 2: failure releases the guard ---------------------------
        def boom(self, image, **kwargs):
            raise RuntimeError("pipeline exploded")

        with mock.patch.object(pl.VisualDOMPipeline, "process", boom), \
                mock.patch.object(QMessageBox, "warning"):
            window._do_analyze_screenshot(shot)
        assert window._analysis_running is False, "guard stuck after failure"
        print("PASS phase2: guard released after pipeline failure")
        return 0
    finally:
        window.close()
        if sessions.is_dir():
            for p in sessions.iterdir():
                if p.name not in before:
                    shutil.rmtree(p, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
