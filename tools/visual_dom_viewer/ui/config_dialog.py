"""
Session-config editor for the Viewer (ADR-020).

Edits the same `vizdom.config.json` the CLI, the Python API and Robot Framework
read, so a setting proven here transfers verbatim to a test suite.

Two views over one document:
  * **Form** — generated from the `VizDomConfig` dataclasses, with tooltips taken
    from the in-code `_FIELD_HELP` strings. Generating it means the editor cannot
    drift from the schema when a field is added, and there is no second copy of
    the field list to maintain.
  * **JSON** — the raw file, for anything the form does not cover (nested lists,
    comment keys) and for people who prefer text.

Validation is delegated to `VizDomConfig.load()` — the real loader, including its
unknown-key rejection — rather than a re-implementation that could disagree with
what the pipeline accepts.
"""

import json
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

# Fields whose value is one of a known set - rendered as a combo box. Anything
# not listed falls back to a free-text line edit, so a new field still works.
_CHOICES = {
    "detector.backend": ["uied", "yolo", "omniparser", "hybrid", "grpc"],
    "ocr.engine": ["easyocr", "paddleocr", "tesseract", "none"],
    "refiner.backend": ["ollama", "openai"],
    "grounding.backend": ["ollama", "openai"],
    "capture.strategy": ["", "windows", "linux", "android", "camera", "grpc"],
    "actuator.strategy": ["", "desktop", "android", "grpc"],
}


class ConfigDialog(QDialog):
    """Open, edit, validate and apply a VizDOM session config."""

    def __init__(self, parent=None, path: str = None):
        super().__init__(parent)
        self.setWindowTitle("Session Configuration")
        self.resize(760, 640)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        self._path = Path(path) if path else None
        self._editors = {}          # "section.field" -> widget
        self._applied_cb = None     # set by the caller via on_apply()

        root = QVBoxLayout(self)

        # ---- file row ---------------------------------------------------
        file_row = QHBoxLayout()
        self._path_label = QLabel("(unsaved — defaults)")
        self._path_label.setStyleSheet("color: #555;")
        file_row.addWidget(self._path_label, 1)
        for text, slot in (("Open…", self._open), ("Save", self._save),
                           ("Save As…", self._save_as)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            file_row.addWidget(b)
        root.addLayout(file_row)

        # ---- tabs -------------------------------------------------------
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_form_tab(), "Form")
        self._json_edit = QPlainTextEdit()
        self._json_edit.setFont(QFont("Consolas", 10))
        self._tabs.addTab(self._json_edit, "JSON")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, 1)

        # ---- status + actions ------------------------------------------
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        actions = QHBoxLayout()
        validate = QPushButton("Validate")
        validate.clicked.connect(self._validate_clicked)
        actions.addWidget(validate)
        actions.addStretch(1)
        self._apply_btn = QPushButton("Apply to Viewer")
        self._apply_btn.setToolTip(
            "Use this configuration for the next analysis (detector, OCR, "
            "capture strategy and target are taken from it)."
        )
        self._apply_btn.clicked.connect(self._apply_clicked)
        actions.addWidget(self._apply_btn)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        actions.addWidget(close)
        root.addLayout(actions)

        if self._path and self._path.exists():
            self._load_path(self._path)
        else:
            self._set_config_dict(self._defaults())

    # -- public ----------------------------------------------------------

    def on_apply(self, callback):
        """Register `callback(config_dict)`, invoked by 'Apply to Viewer'."""
        self._applied_cb = callback

    def config_dict(self) -> dict:
        """The current document as a dict (from whichever tab is showing)."""
        if self._tabs.currentIndex() == 1:
            return json.loads(self._json_edit.toPlainText())
        return self._form_to_dict()

    # -- construction ----------------------------------------------------

    def _defaults(self) -> dict:
        from visual_dom.config import VizDomConfig
        return VizDomConfig.default().to_dict()

    def _build_form_tab(self) -> QWidget:
        """One group box per config section, generated from the dataclasses."""
        from visual_dom.config import VizDomConfig, _FIELD_HELP

        inner = QWidget()
        layout = QVBoxLayout(inner)

        for section in fields(VizDomConfig):
            sub = section.default_factory()
            if not is_dataclass(sub):
                continue
            box = QGroupBox(f"{section.name} — {_FIELD_HELP.get(section.name, '')}")
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignRight)
            for f in fields(sub):
                key = f"{section.name}.{f.name}"
                default = (f.default if f.default is not MISSING
                           else f.default_factory())        # type: ignore[misc]
                widget = self._editor_for(key, default)
                widget.setToolTip(_FIELD_HELP.get(key, ""))
                self._editors[key] = widget
                label = QLabel(f.name)
                label.setToolTip(_FIELD_HELP.get(key, ""))
                form.addRow(label, widget)
            layout.addWidget(box)

        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _editor_for(self, key: str, default):
        if key in _CHOICES:
            combo = QComboBox()
            combo.addItems(_CHOICES[key])
            combo.setEditable(True)      # a plugin name may not be in the list
            return combo
        if isinstance(default, bool):
            return QCheckBox()
        edit = QLineEdit()
        if isinstance(default, list):
            edit.setPlaceholderText("comma-separated")
        elif default is None:
            edit.setPlaceholderText("null (use the default)")
        return edit

    # -- form <-> dict ---------------------------------------------------

    def _set_config_dict(self, data: dict):
        for key, widget in self._editors.items():
            section, field = key.split(".", 1)
            value = (data.get(section) or {}).get(field)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText("" if value is None else str(value))
            else:
                if value is None:
                    widget.setText("")
                elif isinstance(value, list):
                    widget.setText(", ".join(str(v) for v in value))
                else:
                    widget.setText(str(value))
        self._json_edit.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))

    def _form_to_dict(self) -> dict:
        """Read the form back, preserving types and treating blank as 'default'."""
        from visual_dom.config import VizDomConfig
        defaults = VizDomConfig.default().to_dict()
        out = {}
        for key, widget in self._editors.items():
            section, field = key.split(".", 1)
            ref = (defaults.get(section) or {}).get(field)
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            else:
                text = (widget.currentText() if isinstance(widget, QComboBox)
                        else widget.text()).strip()
                if text == "" or text.lower() == "null":
                    value = None            # explicit "use the default"
                elif isinstance(ref, list):
                    value = [t.strip() for t in text.split(",") if t.strip()]
                elif isinstance(ref, bool):
                    value = text.lower() in ("1", "true", "yes", "on")
                elif isinstance(ref, int) and not isinstance(ref, bool):
                    try:
                        value = int(text)
                    except ValueError:
                        value = text
                elif isinstance(ref, float):
                    try:
                        value = float(text)
                    except ValueError:
                        value = text
                else:
                    value = text
            out.setdefault(section, {})[field] = value
        return out

    def _on_tab_changed(self, index: int):
        """Keep the two views in step; a JSON syntax error blocks the switch."""
        try:
            if index == 1:                                  # form -> json
                self._json_edit.setPlainText(
                    json.dumps(self._form_to_dict(), indent=2, ensure_ascii=False))
            else:                                           # json -> form
                self._set_config_dict(json.loads(self._json_edit.toPlainText()))
        except json.JSONDecodeError as exc:
            self._fail(f"JSON is not parseable: {exc}")
            self._tabs.blockSignals(True)
            self._tabs.setCurrentIndex(1)
            self._tabs.blockSignals(False)

    # -- actions ---------------------------------------------------------

    def _validate(self):
        """(ok, message) using the real loader, so the GUI cannot be laxer."""
        from visual_dom.config import VizDomConfig
        try:
            data = self.config_dict()
        except json.JSONDecodeError as exc:
            return False, f"JSON is not parseable: {exc}"
        try:
            cfg = VizDomConfig.load(data)
        except Exception as exc:                       # ValueError, TypeError…
            return False, str(exc)
        return True, (f"Valid — detector={cfg.detector.backend}, "
                      f"ocr={cfg.ocr.engine}, capture={cfg.capture.strategy or 'auto'}")

    def _validate_clicked(self):
        ok, message = self._validate()
        (self._ok if ok else self._fail)(message)

    def _apply_clicked(self):
        ok, message = self._validate()
        if not ok:
            self._fail(f"Not applied — {message}")
            return
        if self._applied_cb is None:
            self._fail("Nothing to apply to (no handler registered).")
            return
        try:
            self._applied_cb(self.config_dict())
        except Exception as exc:                       # a bad handler must not kill the dialog
            self._fail(f"Apply failed: {exc}")
            return
        self._ok(f"Applied to the Viewer. {message}")

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open session config", str(self._path or Path.cwd()),
            "JSON files (*.json);;All files (*)")
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._fail(f"Could not read {path.name}: {exc}")
            return
        self._path = path
        self._path_label.setText(str(path))
        self._set_config_dict(data)
        ok, message = self._validate()
        (self._ok if ok else self._fail)(message)

    def _save(self):
        if self._path is None:
            self._save_as()
            return
        ok, message = self._validate()
        if not ok:
            self._fail(f"Not saved — {message}")
            return
        try:
            self._path.write_text(
                json.dumps(self.config_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as exc:
            self._fail(f"Could not write {self._path}: {exc}")
            return
        self._ok(f"Saved to {self._path}")

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save session config",
            str(self._path or Path.cwd() / "vizdom.config.json"),
            "JSON files (*.json)")
        if path:
            self._path = Path(path)
            self._path_label.setText(path)
            self._save()

    # -- status ----------------------------------------------------------

    def _ok(self, message: str):
        self._status.setStyleSheet("color: #1b5e20;")
        self._status.setText(message)

    def _fail(self, message: str):
        self._status.setStyleSheet("color: #b71c1c;")
        self._status.setText(message)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
