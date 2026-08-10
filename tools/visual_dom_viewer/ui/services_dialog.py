"""
Service manager for the Viewer: detector / capture / actuator (ADR-017/018/019).

Starting the three gRPC services meant three terminals and remembering which
flags each one needs (`--ocr easyocr` for a remote OmniParser, `--window-title`
for focus). This dialog does it in-process: per service a status light, the flags
that actually matter, start/stop, and the service's own log output.

Two honest properties:

* **Health is polled, not assumed.** Each row's light comes from the service's
  `HealthCheck` RPC, so it reflects reachability rather than "we started a
  process". A service someone else started in a terminal shows as running and is
  marked *external* — the dialog will not offer to stop what it does not own.
* **Stop only kills our own child.** Terminating a process this dialog did not
  start would be a surprising side effect, so the button is disabled for
  external services.

The services are launched with the *Viewer's own interpreter* (`sys.executable`),
which by construction has the project's dependencies.
"""

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QProcess, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

_DOT = {
    "running": ("●", "#2e7d32", "reachable"),
    "starting": ("●", "#f9a825", "starting…"),
    "stopped": ("●", "#9e9e9e", "not reachable"),
    "error": ("●", "#c62828", "failed"),
}


class ServiceRow:
    """One service: its widgets, its child process, and its health state."""

    def __init__(self, key, title, module, port, hint):
        self.key = key
        self.title = title
        self.module = module
        self.default_port = port
        self.hint = hint
        self.process = None          # QProcess we own, or None
        self.external = False        # reachable but not started by us
        self.state = "stopped"


class ServicesDialog(QDialog):
    """Start, stop and monitor the three VizDOM services."""

    POLL_MS = 4000

    def __init__(self, parent=None, repo_root: Path = None):
        super().__init__(parent)
        self.setWindowTitle("Services")
        self.resize(820, 620)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self._root = Path(repo_root) if repo_root else Path.cwd()

        self._rows = {
            "detector": ServiceRow(
                "detector", "Detector", "visual_dom.adapters.inbound.grpc.detector_server",
                50051, "the heavy model — run it where the GPU is"),
            "capture": ServiceRow(
                "capture", "Capture", "visual_dom.adapters.inbound.grpc.capture_server",
                50053, "must run where the application under test is visible"),
            "actuator": ServiceRow(
                "actuator", "Actuator", "visual_dom.adapters.inbound.grpc.actuator_server",
                50054, "must run where the clicks should land"),
        }

        root = QVBoxLayout(self)
        note = QLabel(
            "Services are optional: the Viewer analyses in-process by default. "
            "Start them to share one warm model, or to capture/act on another machine "
            "(then point the Viewer's capture source at <code>grpc</code>)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        root.addWidget(note)

        for row in self._rows.values():
            root.addWidget(self._build_row(row))

        log_box = QGroupBox("Service output")
        log_layout = QVBoxLayout(log_box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setMaximumBlockCount(2000)     # a service can be chatty
        log_layout.addWidget(self._log)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._log.clear)
        log_layout.addWidget(clear, alignment=Qt.AlignRight)
        root.addWidget(log_box, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        stop_all = QPushButton("Stop all (ours)")
        stop_all.clicked.connect(self._stop_all)
        buttons.addWidget(stop_all)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_health)
        self._timer.start(self.POLL_MS)
        self._poll_health()

    # -- per-service UI --------------------------------------------------

    def _build_row(self, row: ServiceRow) -> QWidget:
        box = QGroupBox(f"{row.title} — {row.hint}")
        grid = QGridLayout(box)

        row.light = QLabel(_DOT["stopped"][0])
        row.light.setStyleSheet(f"color: {_DOT['stopped'][1]}; font-size: 18px;")
        grid.addWidget(row.light, 0, 0)

        row.status = QLabel("not reachable")
        row.status.setMinimumWidth(190)
        grid.addWidget(row.status, 0, 1)

        grid.addWidget(QLabel("Port:"), 0, 2)
        row.port_edit = QLineEdit(str(row.default_port))
        row.port_edit.setMaximumWidth(70)
        grid.addWidget(row.port_edit, 0, 3)

        # per-service options: only the flags that change behaviour meaningfully
        col = 4
        if row.key == "detector":
            grid.addWidget(QLabel("Backend:"), 0, col); col += 1
            row.backend = QComboBox()
            row.backend.addItems(["uied", "omniparser", "yolo"])
            grid.addWidget(row.backend, 0, col); col += 1
            grid.addWidget(QLabel("OCR:"), 0, col); col += 1
            row.ocr = QComboBox()
            row.ocr.addItems(["(none)", "easyocr", "paddleocr", "tesseract"])
            row.ocr.setCurrentText("easyocr")
            row.ocr.setToolTip(
                "Runs the OCR text ensemble ON THE SERVICE (ADR-016). The client's "
                "OCR callable cannot cross gRPC, so without this a remote OmniParser "
                "silently falls back to its own weaker OCR."
            )
            grid.addWidget(row.ocr, 0, col); col += 1
        else:
            grid.addWidget(QLabel("Strategy:"), 0, col); col += 1
            row.strategy = QComboBox()
            row.strategy.setEditable(True)
            if row.key == "capture":
                row.strategy.addItems(["", "windows", "linux", "android", "camera"])
            else:
                row.strategy.addItems(["", "desktop", "android"])
            row.strategy.setToolTip("Blank = let the service auto-select for its OS")
            grid.addWidget(row.strategy, 0, col); col += 1
            grid.addWidget(QLabel("Window title:"), 0, col); col += 1
            row.window_title = QLineEdit()
            row.window_title.setPlaceholderText("app to raise on Focus (ADR-021)")
            grid.addWidget(row.window_title, 0, col); col += 1

        row.start_btn = QPushButton("Start")
        row.start_btn.clicked.connect(lambda _, r=row: self._start(r))
        grid.addWidget(row.start_btn, 0, col); col += 1

        row.stop_btn = QPushButton("Stop")
        row.stop_btn.setEnabled(False)
        row.stop_btn.clicked.connect(lambda _, r=row: self._stop(r))
        grid.addWidget(row.stop_btn, 0, col)

        return box

    # -- start / stop ----------------------------------------------------

    def _args_for(self, row: ServiceRow):
        args = ["-m", row.module, "--port", row.port_edit.text().strip() or str(row.default_port)]
        if row.key == "detector":
            args += ["--backend", row.backend.currentText()]
            if row.ocr.currentText() != "(none)":
                args += ["--ocr", row.ocr.currentText()]
        else:
            strategy = row.strategy.currentText().strip()
            if strategy:
                args += ["--strategy", strategy]
            title = row.window_title.text().strip()
            if title:
                args += ["--window-title", title]
        return args

    def _start(self, row: ServiceRow):
        if row.process is not None:
            self._append(f"[{row.key}] already started by this dialog")
            return
        if row.external:
            self._append(f"[{row.key}] something is already listening on that port "
                         f"(started elsewhere) — stop it there, or pick another port")
            return

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(self._args_for(row))
        process.setWorkingDirectory(str(self._root))
        # the child needs src/ on PYTHONPATH exactly like the launchers set it
        from PyQt5.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        src = str(self._root / "src")
        existing = env.value("PYTHONPATH", "")
        env.insert("PYTHONPATH", src if not existing else src + ";" + existing)
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda r=row: self._drain(r))
        process.finished.connect(lambda code, _s, r=row: self._on_finished(r, code))
        process.errorOccurred.connect(
            lambda err, r=row: self._append(f"[{r.key}] process error: {err}"))

        row.process = process
        row.state = "starting"
        self._paint(row)
        self._append(f"[{row.key}] {sys.executable} {' '.join(self._args_for(row))}")
        process.start()

    def _stop(self, row: ServiceRow):
        if row.process is None:
            return
        self._append(f"[{row.key}] stopping…")
        row.process.terminate()
        if not row.process.waitForFinished(3000):
            self._append(f"[{row.key}] did not exit on terminate; killing")
            row.process.kill()
            row.process.waitForFinished(2000)

    def _stop_all(self):
        for row in self._rows.values():
            if row.process is not None:
                self._stop(row)

    def _on_finished(self, row: ServiceRow, code: int):
        self._append(f"[{row.key}] exited with code {code}")
        row.process = None
        row.state = "error" if code not in (0, 62097, 15) else "stopped"
        self._paint(row)
        self._poll_health()

    def _drain(self, row: ServiceRow):
        if row.process is None:
            return
        data = bytes(row.process.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.splitlines():
            self._append(f"[{row.key}] {line}")

    # -- health ----------------------------------------------------------

    def _poll_health(self):
        for row in self._rows.values():
            port = row.port_edit.text().strip() or str(row.default_port)
            ready, detail = self._health(row.key, port)
            if ready:
                row.external = row.process is None
                row.state = "running"
                row.status.setText(
                    f"{detail} · port {port}" + ("  (external)" if row.external else ""))
            else:
                row.external = False
                if row.process is not None:
                    row.state = "starting"
                    row.status.setText(f"starting… · port {port}")
                elif row.state != "error":
                    row.state = "stopped"
                    row.status.setText(f"not reachable · port {port}")
            self._paint(row)

    def _health(self, key: str, port: str):
        """(ready, detail) via the service's own HealthCheck RPC."""
        try:
            import grpc
            if key == "detector":
                from visual_dom.generated import detector_pb2 as pb, detector_pb2_grpc as pbg
                stub_cls, request = pbg.DetectorStub, pb.HealthRequest()
            elif key == "capture":
                from visual_dom.generated import capture_pb2 as pb, capture_pb2_grpc as pbg
                stub_cls, request = pbg.CaptureStub, pb.HealthRequest()
            else:
                from visual_dom.generated import actuator_pb2 as pb, actuator_pb2_grpc as pbg
                stub_cls, request = pbg.ActuatorStub, pb.HealthRequest()
            channel = grpc.insecure_channel(f"localhost:{port}")
            try:
                response = stub_cls(channel).HealthCheck(request, timeout=1.0)
            finally:
                channel.close()
            if not getattr(response, "ready", False):
                return False, "not ready"
            label = (getattr(response, "backend", "")
                     or getattr(response, "strategy", "")
                     or getattr(response, "actuator", "") or "ready")
            return True, label
        except ImportError:
            return False, "grpc not installed"
        except Exception:
            return False, "not reachable"

    def _paint(self, row: ServiceRow):
        glyph, colour, _ = _DOT[row.state]
        row.light.setText(glyph)
        row.light.setStyleSheet(f"color: {colour}; font-size: 18px;")
        ours = row.process is not None
        row.start_btn.setEnabled(not ours and row.state != "running")
        row.stop_btn.setEnabled(ours)
        row.stop_btn.setToolTip(
            "" if ours else "Only services started here can be stopped from here.")

    def _append(self, line: str):
        self._log.appendPlainText(line)

    # -- lifecycle -------------------------------------------------------

    def closeEvent(self, event):
        """Hide, but keep our children running (the user may still be using them)."""
        event.ignore()
        self.hide()

    def shutdown(self):
        """Called by the main window on exit: never leave orphaned services."""
        self._timer.stop()
        self._stop_all()
