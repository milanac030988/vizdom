"""
"Click via actuator" — try a locator from the Viewer before the test is written (ADR-028).

Flow, matching what a Robot test does with ``Dump Visual DOM`` + ``Click Visual``:

1. take the element's locator — its definition if it has one, else the default —
   exactly as the exporter will write it (`export/locators.py`);
2. capture and analyze the screen **again** (on by default): resolving against the
   DOM the locator was made from only proves it is unique there, while a fresh
   analysis is what the suite will see;
3. resolve with the shared `LocatorResolver` — a broken locator fails here;
4. raise the application (ADR-021), click through the configured actuator
   (ADR-019), and capture again so the effect is visible (ADR-023).

The pure logic lives in `core/actuation.py`; this mixin is the Qt glue the main
window inherits.
"""

import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QLineEdit, QMenu, QMessageBox,
)

from ..core.actuation import ActuationError, ActuationSettings, LocatorTrial
from ..export.locators import definition_locator, element_locator

#: label of the "no explicit strategy" entry in the actuator combo
_DEFAULT_ACTUATOR = "platform default"


class TryLocatorMixin:
    """Viewer-side client for trying locators through the actuator."""

    # ---------------- controls (hosted by Pipeline Settings) -------------

    def _create_actuation_controls(self):
        """Actuation widgets; they live in Pipeline Settings > Actuation."""
        self._actuator_combo = QComboBox()
        self._actuator_combo.addItem(_DEFAULT_ACTUATOR, None)
        try:
            from visual_dom.adapters.outbound.actuator import list_actuators
            for a in list_actuators():
                label = a["name"] if a["available"] else f"{a['name']} (n/a)"
                self._actuator_combo.addItem(label, a["name"])
        except Exception as e:
            print(f"[Viewer] actuator strategy discovery failed: {e}")
        self._actuator_combo.setToolTip(
            "How 'Click via actuator' delivers input (ADR-019):\n"
            "platform default = desktop mouse/keyboard where available\n"
            "desktop = this machine   android = adb device\n"
            "grpc = a running actuator service (set the target below)\n"
            "<plugin> = your strategy from plugins/actuator/")

        self._actuator_target_edit = QLineEdit("")
        self._actuator_target_edit.setPlaceholderText("host:port (grpc only)")
        self._actuator_target_edit.setToolTip(
            "Actuator service host:port, for strategy = grpc. "
            "Start one from Tools > Services.")

        self._actuator_window_edit = QLineEdit("")
        self._actuator_window_edit.setPlaceholderText("empty = the connected window")
        self._actuator_window_edit.setToolTip(
            "Window raised before every click (ADR-021). Empty = the window you\n"
            "connected to, or the one the last capture was scoped to. A click is\n"
            "never sent without one.")

        self._recapture_before_try_checkbox = QCheckBox(
            "Capture again before resolving (what the test will see)")
        self._recapture_before_try_checkbox.setChecked(True)
        self._recapture_before_try_checkbox.setToolTip(
            "ON  = re-capture and re-analyze, then resolve the locator on that fresh\n"
            "      DOM, as a test does. This is the meaningful check.\n"
            "OFF = resolve on the DOM on screen; a locator always finds its own\n"
            "      element there, so this only proves the locator is unique.")

        self._recapture_after_try_checkbox = QCheckBox("Capture again after the click")
        self._recapture_after_try_checkbox.setChecked(True)
        self._recapture_after_try_checkbox.setToolTip(
            "Re-capture and re-analyze after the click so its effect is visible.")

    def _actuation_widgets(self) -> dict:
        return {
            "actuator": self._actuator_combo,
            "actuator_target": self._actuator_target_edit,
            "actuator_window": self._actuator_window_edit,
            "recapture_before_try": self._recapture_before_try_checkbox,
            "recapture_after_try": self._recapture_after_try_checkbox,
        }

    def _actuation_settings(self) -> ActuationSettings:
        return ActuationSettings(
            strategy=self._actuator_combo.currentData(),
            target=self._actuator_target_edit.text().strip() or None,
            window_title=self._actuator_window_edit.text().strip() or None,
        )

    def _apply_actuator_config(self, data: dict):
        """Session config (ADR-020) ``actuator`` / ``grounding`` -> the Viewer."""
        settings = ActuationSettings.from_config(data)
        if settings.strategy:
            index = self._actuator_combo.findData(settings.strategy)
            if index >= 0:
                self._actuator_combo.setCurrentIndex(index)
        if settings.target:
            self._actuator_target_edit.setText(settings.target)
        window = settings.window_title or (data.get("capture") or {}).get("window_title")
        if window:
            self._actuator_window_edit.setText(window)
        try:
            from visual_dom.config import VizDomConfig
            self._grounding_config = VizDomConfig.load(data).grounding
        except Exception as e:
            print(f"[Viewer] grounding config not applied: {e}")

    # ---------------- context menus -------------------------------------

    def _element_context_menu(self, element_id: str, global_pos):
        """Right-click on an element (canvas or tree)."""
        if not element_id:
            return
        self._model.select_element(element_id)
        self._select_tree_item(element_id)
        menu = QMenu(self)
        click = menu.addAction("Click via Actuator")
        double = menu.addAction("Double-click via Actuator")
        right = menu.addAction("Right-click via Actuator")
        menu.addSeparator()
        copy = menu.addAction("Copy Locator")
        chosen = menu.exec_(global_pos)
        if chosen is copy:
            QApplication.clipboard().setText(self._locator_for(element_id))
            self._statusbar.showMessage(f"Copied: {self._locator_for(element_id)}", 5000)
        elif chosen in (click, double, right):
            kind = {click: "single", double: "double", right: "right"}[chosen]
            self._try_click_via_actuator(element_id, kind)

    def _on_tree_context_menu(self, pos):
        index = self._tree_view.indexAt(pos)
        if not index.isValid():
            return
        item = self._tree_model.itemFromIndex(index.siblingAtColumn(0))
        element_id = item.data(Qt.UserRole) if item else None
        self._element_context_menu(element_id, self._tree_view.viewport().mapToGlobal(pos))

    def _try_click_selected(self):
        """Capture > Click Selected via Actuator (Ctrl+T)."""
        element = self._model.selected_element
        if element is None:
            QMessageBox.information(self, "Click via Actuator",
                                    "Select an element on the canvas or in the tree first.")
            return
        self._try_click_via_actuator(element.id, "single")

    # ---------------- the trial -----------------------------------------

    def _locator_for(self, element_id: str) -> str:
        """The locator the exporter would write for this element."""
        definition = self._model.get_definition(element_id)
        if definition is not None:
            return definition_locator(definition)[0]
        element = self._model.dom_tree.get_element_by_id(element_id) if self._model.dom_tree else None
        return element_locator(element) if element is not None else f"id={element_id}"

    def _try_window_title(self):
        """Window to raise: setting > connected target > the last scoped capture."""
        return (self._actuator_window_edit.text().strip()
                or self._connected_target_title()
                or (getattr(self, "_capture_context", None) or {}).get("window_title"))

    def _confirm_first_actuation(self, locator: str, title: str, strategy: str) -> bool:
        """Real input on a real machine: ask once per session."""
        if getattr(self, "_actuation_confirmed", False):
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Click via Actuator")
        box.setText(
            f"This sends a real click to <b>{title}</b> through the "
            f"<b>{strategy}</b> actuator.")
        box.setInformativeText(
            f"Locator: {locator}\n\nThe window is raised first; the click is not sent "
            f"if it cannot be. You won't be asked again until the Viewer restarts.")
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec_() != QMessageBox.Ok:
            return False
        self._actuation_confirmed = True
        return True

    def _recapture_for_try(self, title: str) -> bool:
        """Fresh capture + analysis through a capture strategy (geometry recorded)."""
        name, kwargs = self._selected_capture_strategy()
        if name is None:
            # The window handler path records no screen position for its crop, so
            # trials always capture through a strategy (the platform default).
            from visual_dom.adapters.outbound.capture import auto_select
            name, kwargs = auto_select(), {}
            if not name:
                QMessageBox.warning(self, "Click via Actuator",
                                    "No capture strategy is available to re-capture with.")
                return False
        before = self._model.dom_tree
        ok = self._capture_strategy_and_analyze(name, kwargs, title=title)
        return ok and self._model.dom_tree is not before

    def _try_click_via_actuator(self, element_id: str, click_type: str = "single"):
        if getattr(self, "_analysis_running", False) or getattr(self, "_trial_running", False):
            self._statusbar.showMessage("Busy — wait for the current analysis to finish", 4000)
            return
        if not self._model.dom_tree:
            return

        locator = self._locator_for(element_id)
        title = self._try_window_title()
        if not title:
            QMessageBox.warning(
                self, "Click via Actuator",
                "No target window. Connect to the application, or set "
                "Pipeline Settings > Actuation > Window title, so it can be raised "
                "before the click.")
            return

        settings = self._actuation_settings()
        try:
            actuator = settings.create_actuator()
        except Exception as e:
            QMessageBox.warning(self, "Click via Actuator", f"Actuator unavailable: {e}")
            return
        if not self._confirm_first_actuation(locator, title, actuator.name):
            actuator.close()
            return

        self._trial_running = True
        try:
            if self._recapture_before_try_checkbox.isChecked():
                self._show_progress("Capturing again before resolving...", 20)
                if not self._recapture_for_try(title):
                    self._hide_progress()
                    self._statusbar.showMessage("Trial stopped: the re-capture failed", 6000)
                    return

            tree = self._model.dom_tree
            capture_focus = self._capture_focus_callable()
            trial = LocatorTrial(actuator, capture_focus=capture_focus,
                                 settle=lambda: time.sleep(0.3))
            self._show_progress(f"Trying {locator} ...", 80)
            try:
                outcome = trial.run(
                    locator, tree.compiled_dom, getattr(self, "_capture_context", None) or {},
                    (tree.screen_width, tree.screen_height) if tree.screen_width else None,
                    title, click_type=click_type,
                    screenshot=self._screenshot_for_grounding(),
                    grounding=getattr(self, "_grounding_config", None))
            except ActuationError as e:
                self._hide_progress()
                QMessageBox.warning(self, "Click via Actuator", str(e))
                return
            finally:
                if capture_focus is not None:
                    capture_focus.close()

            self._hide_progress()
            self.activateWindow()
            if not outcome.clicked:
                self._model.clear_selection()
                QMessageBox.warning(
                    self, "Locator Failed",
                    f"{outcome.resolution.error_message()}\n\n"
                    f"The same locator would fail in the test suite.")
                return

            self._model.select_element(outcome.element_id)
            self._select_tree_item(outcome.element_id)
            note = f" ({outcome.notes[0]})" if outcome.notes else ""
            self._statusbar.showMessage(
                f"Clicked {outcome.element_id} via {actuator.name} — {locator}{note}", 10000)
            print(f"[Viewer] trial: {locator} -> {outcome.element_id} at {outcome.point} "
                  f"(normalized {outcome.normalized}, focus via {outcome.focused_via})")

            if self._recapture_after_try_checkbox.isChecked():
                time.sleep(0.8)     # let the application react before looking
                self._recapture_for_try(title)
                self._statusbar.showMessage(
                    f"Clicked {outcome.element_id} via {actuator.name}; screen re-captured", 10000)
        except Exception as e:
            # A slot must not let an exception escape: PyQt5 aborts the whole
            # Viewer on one (e.g. a gRPC actuator whose service is down, or
            # pyautogui's fail-safe corner).
            import traceback
            traceback.print_exc()
            self._hide_progress()
            QMessageBox.warning(self, "Click via Actuator",
                                f"The trial failed: {type(e).__name__}: {e}")
        finally:
            self._trial_running = False
            self._hide_progress()
            try:
                actuator.close()
            except Exception:
                pass

    def _screenshot_for_grounding(self):
        """
        The analyzed screenshot as a BGR array, so `desc=` can use the VLM tier
        exactly as the suite does (it passes its current screenshot), or None.
        """
        data = self._model.get_screenshot_data()
        if not data:
            return None
        try:
            import cv2
            import numpy as np
            return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            return None

    def _capture_focus_callable(self):
        """
        ``title -> bool`` raising the window through the capture side, for
        actuators that cannot focus (ADR-021: either port may be the capable
        one). Exposes ``close()`` to release the strategy afterwards.

        The strategy is created on first use only: most actuators focus the
        window themselves, and a remote capture source would otherwise open a
        second channel (or adb session) on every trial for nothing.
        """
        name, kwargs = self._selected_capture_strategy()
        if name is None:
            from visual_dom.adapters.outbound.capture import auto_select
            name, kwargs = auto_select(), {}
        if not name:
            return None

        class _Focus:
            def __init__(self):
                self._cap = None

            def __call__(self, title):
                if self._cap is None:
                    try:
                        from visual_dom.adapters.outbound.capture import create_capture
                        self._cap = create_capture(name, **kwargs)
                    except Exception:
                        return False
                return self._cap.focus_target(title)

            def close(self):
                if self._cap is None:
                    return
                try:
                    self._cap.close()
                except Exception:
                    pass

        return _Focus()
