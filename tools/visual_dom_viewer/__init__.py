"""
Visual DOM Viewer - Interactive UI Element Inspector

A tool similar to UIAutomatorViewer that helps visualize and select UI elements
from screenshots, with support for multiple platforms through pluggable strategies.

Features:
- Visual element selection on screenshot
- Tree view of element hierarchy
- Property inspection panel
- Robot Framework resource file export
- Pluggable platform strategies (Windows, Android, Linux, Web)
"""

__version__ = "0.1.0"
__author__ = "Nguyen Huynh Tri Cuong"

from .core.model import DOMViewerModel
from .core.tree import DOMTree, DOMElement

__all__ = [
    "DOMViewerModel",
    "DOMTree",
    "DOMElement",
]
