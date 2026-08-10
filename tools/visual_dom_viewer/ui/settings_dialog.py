"""
Pipeline settings dialog for the Viewer.

The main toolbar used to carry every pipeline knob — capture source, detector,
OCR engine, text ensemble, smart-merge, SLM, camera mode — 26 widgets in one
row. This dialog is where they live now, grouped by pipeline stage.

It **reparents the existing widgets** rather than creating new ones: the main
window reads them from ~57 call sites (`self._detector_combo.currentText()` and
friends), so moving the objects keeps every one of those working and leaves no
second source of truth for a setting.

Modeless on purpose: the dialog stays open next to the main window while you
re-analyse, so the effect of a change is visible immediately.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QWidget, QSizePolicy,
)


class PipelineSettingsDialog(QDialog):
    """Groups the pipeline controls that used to crowd the toolbar."""

    def __init__(self, parent, widgets: dict):
        """
        Args:
            parent: the main window.
            widgets: the LIVE control widgets, by key. See main_window
                ``_pipeline_widgets()``. Widgets are reparented into this
                dialog; the main window keeps its references.
        """
        super().__init__(parent)
        self.setWindowTitle("Pipeline Settings")
        self.setMinimumWidth(430)
        # A tool window: stays above the main window without blocking it.
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        intro = QLabel(
            "These settings apply to the <b>next</b> analysis — press "
            "<code>F5</code> (Capture &amp; Analyze) or <code>F6</code> "
            "(Re-Analyze) to see their effect."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555;")
        root.addWidget(intro)

        # ---- Capture source (ADR-018) ----------------------------------
        capture = QGroupBox("Capture source")
        cf = QFormLayout(capture)
        cf.setLabelAlignment(Qt.AlignRight)
        cf.addRow("Source:", widgets["capture_source"])
        cf.addRow("Argument:", widgets["capture_arg"])
        cf.addRow("", widgets["camera_mode"])
        root.addWidget(capture)

        # ---- Detection (ADR-015 / ADR-017) -----------------------------
        detect = QGroupBox("Element detection")
        df = QFormLayout(detect)
        df.setLabelAlignment(Qt.AlignRight)
        df.addRow("Detector:", widgets["detector"])
        df.addRow("Service target:", widgets["grpc_target"])
        df.addRow("", widgets["merge"])
        root.addWidget(detect)

        # ---- Text (ADR-012 / ADR-016) ----------------------------------
        text = QGroupBox("Text")
        tf = QFormLayout(text)
        tf.setLabelAlignment(Qt.AlignRight)
        tf.addRow("OCR engine:", widgets["ocr"])
        tf.addRow("", widgets["text_ensemble"])
        root.addWidget(text)

        # ---- Refinement (ADR-009) --------------------------------------
        refine = QGroupBox("Small-model refinement (optional)")
        rf = QFormLayout(refine)
        rf.setLabelAlignment(Qt.AlignRight)
        rf.addRow("", widgets["slm"])
        rf.addRow("Model:", widgets["slm_model"])
        root.addWidget(refine)

        # widgets came from a toolbar, where narrow was a virtue; in a form they
        # should fill the row
        for key in ("capture_source", "capture_arg", "detector", "grpc_target",
                    "ocr", "slm_model"):
            w = widgets.get(key)
            if w is not None:
                w.setMaximumWidth(16777215)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def closeEvent(self, event):
        """Hide instead of destroy — the hosted widgets must outlive the dialog."""
        event.ignore()
        self.hide()
