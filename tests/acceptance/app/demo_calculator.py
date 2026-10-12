"""
A tiny calculator for the acceptance suite — the application under test in CI.

Deliberately plain: large, high-contrast keys and a big display, so the CPU-only
pipeline (UIED + EasyOCR) reads it reliably on a headless runner. The suite
must never depend on what this app's widgets *are* (VizDOM sees pixels only);
it only needs a GUI that reacts to clicks and keys in a predictable way.

Run:  python tests/acceptance/app/demo_calculator.py
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

TITLE = "VizDOM Demo Calculator"

# label shown on the key -> what it does (operators show their glyph)
KEYS = [
    ["7", "8", "9", "Clear"],
    ["4", "5", "6", "Plus"],
    ["1", "2", "3", "Minus"],
    ["0", "Equals"],
]


class DemoCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setStyleSheet(
            "QWidget { background: white; }"
            "QPushButton { background: #e8e8e8; color: black; border: 2px solid #444;"
            "  min-width: 120px; min-height: 64px; }"
            "QLabel#display { background: white; color: black; border: 2px solid #444;"
            "  padding: 8px; }")
        self._expr = ""

        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(24, 24, 24, 24)

        self.display = QLabel("0")
        self.display.setObjectName("display")
        self.display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.display.setFont(QFont("DejaVu Sans", 36, QFont.Bold))
        self.display.setMinimumHeight(90)
        root.addWidget(self.display)

        grid = QGridLayout()
        grid.setSpacing(16)
        key_font = QFont("DejaVu Sans", 22, QFont.Bold)
        for r, row in enumerate(KEYS):
            for c, label in enumerate(row):
                button = QPushButton(label)
                button.setFont(key_font)
                button.setFocusPolicy(Qt.NoFocus)
                button.clicked.connect(lambda _=False, k=label: self.press(k))
                span = 3 if label == "Equals" else 1
                grid.addWidget(button, r, c, 1, span)
        root.addLayout(grid)

    def press(self, key: str):
        if key == "Clear":
            self._expr = ""
        elif key == "Equals":
            try:
                # only digits and + - are ever appended, so this is safe
                self._expr = str(eval(self._expr or "0"))  # noqa: S307
            except Exception:
                self._expr = "Error"
        elif key == "Plus":
            self._expr += "+"
        elif key == "Minus":
            self._expr += "-"
        else:
            if self._expr in ("Error",):
                self._expr = ""
            self._expr += key
        self.display.setText(self._expr or "0")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.press("Clear")
        else:
            super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = DemoCalculator()
    window.move(40, 40)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
