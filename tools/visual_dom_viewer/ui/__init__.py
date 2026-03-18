"""
UI components for Visual DOM Viewer.

Provides the graphical interface for the viewer application.
Uses PyQt5 for cross-platform desktop UI.
"""

from .main_window import VisualDOMViewerWindow

try:
    from .connect_dialog import ConnectDialog
except ImportError:
    ConnectDialog = None

__all__ = [
    "VisualDOMViewerWindow",
    "ConnectDialog",
]
