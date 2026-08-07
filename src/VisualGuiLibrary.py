"""
Robot Framework entry point for the VizDOM visual-automation library.

Robot Framework imports a library by *module* name, and by convention a library
is importable under the name test authors write:

    *** Settings ***
    Library    VisualGuiLibrary

This module exists so that line works. The implementation lives in
``visual_gui_library.keywords`` (a thin client over the visual_dom capture and
actuator ports, ADR-019); this file only re-exports the class under the name
Robot Framework looks for. Because the module defines an attribute with the same
name as the module, Robot Framework uses it as the library class.

Equivalent explicit form, if you prefer it:

    Library    visual_gui_library.keywords.VisualGuiLibrary
"""

from visual_gui_library.keywords import VisualGuiLibrary

__all__ = ["VisualGuiLibrary"]
