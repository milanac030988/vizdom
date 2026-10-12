"""
Harness for test_try_locator_ui: runs in a SUBPROCESS (see
_analyze_reentrancy_harness.py for why the main window is not built inside
pytest). Prints PASS markers; exit code 0 = all phases passed.

  phase 1: Click via Actuator on the DOM on screen raises the window, then taps
           the element's center through the configured actuator.
  phase 2: with "capture again before resolving", the locator is resolved on
           the FRESH analysis - after a re-analysis renumbered the elements, the
           click still lands on the same button (found by text, not by id).
  phase 3: a locator that no longer resolves fails visibly and sends no click.
"""

import os
import sys
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


class FakeActuator:
    name = "fake"

    def __init__(self):
        self.events = []

    def focus_target(self, title=None):
        self.events.append(("focus", title))
        return True

    def tap(self, nx, ny, image_size=None, click_type="single"):
        self.events.append(("tap", round(nx, 3), round(ny, 3), click_type))

    def close(self):
        pass


def dom_data(elements):
    hierarchy = {"id": "root", "role": "window", "visual_type": "root",
                 "bounds": [0, 0, 400, 200], "children": elements}
    return {"image_size": {"width": 400, "height": 200},
            "dom": {"image_size": [400, 200], "hierarchy": hierarchy,
                    "elements": elements}}


def button(eid, text, x):
    return {"id": eid, "text": text, "role": "button", "visual_type": "button",
            "bounds": [x, 50, x + 40, 70], "center": [x + 20, 60]}


FIRST = [button("E1", "Save", 100), button("E2", "Open", 200)]
# The same screen re-analyzed: one new element shifts the ids by one.
SHIFTED = [button("E1", "New", 20), button("E2", "Save", 100), button("E3", "Open", 200)]


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841
    from visual_dom_viewer.ui.main_window import VisualDOMViewerWindow
    from visual_dom_viewer.core import actuation

    window = VisualDOMViewerWindow()
    window._actuation_confirmed = True                 # skip the modal confirm
    window._actuator_window_edit.setText("Calculator")
    window._capture_context = {"capture_scope": "screen"}
    window._capture_focus_callable = lambda: None
    window._selected_capture_strategy = lambda: ("fake-capture", {})
    actuator = FakeActuator()
    warnings = []

    with mock.patch.object(actuation.ActuationSettings, "create_actuator",
                           return_value=actuator), \
         mock.patch.object(QMessageBox, "warning",
                           side_effect=lambda *a, **k: warnings.append(a[2])), \
         mock.patch("time.sleep"):

        # ---- phase 1: DOM on screen --------------------------------------
        window._model.load_dom_from_dict(dom_data(FIRST))
        window._recapture_before_try_checkbox.setChecked(False)
        window._recapture_after_try_checkbox.setChecked(False)
        window._try_click_via_actuator("E1")
        assert actuator.events == [("focus", "Calculator"), ("tap", 0.3, 0.3, "single")], \
            (actuator.events, warnings)
        assert window._model.selected_element.id == "E1"
        print("PASS phase1")

        # ---- phase 2: re-capture first, ids shifted ----------------------
        actuator.events.clear()
        window._recapture_before_try_checkbox.setChecked(True)

        def fresh_capture(name, kwargs, title=None):
            assert title == "Calculator", title
            window._capture_context = {"capture_scope": "screen"}
            window._model.load_dom_from_dict(dom_data(SHIFTED))
            return True

        window._capture_strategy_and_analyze = fresh_capture
        window._try_click_via_actuator("E1")           # "Save" was E1 when picked
        assert actuator.events[-1] == ("tap", 0.3, 0.3, "single"), (actuator.events, warnings)
        assert window._model.selected_element.id == "E2", window._model.selected_element
        print("PASS phase2")

        # ---- phase 3: the locator no longer resolves -----------------------
        actuator.events.clear()

        def gone(name, kwargs, title=None):
            window._model.load_dom_from_dict(dom_data([button("E1", "Close", 100)]))
            return True

        window._capture_strategy_and_analyze = gone
        window._recapture_before_try_checkbox.setChecked(True)
        window._model.load_dom_from_dict(dom_data(FIRST))
        window._try_click_via_actuator("E2")          # text=Open role=button || id=E2
        assert not [e for e in actuator.events if e[0] == "tap"], actuator.events
        assert any("would fail in the test suite" in w for w in warnings), warnings
        print("PASS phase3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
