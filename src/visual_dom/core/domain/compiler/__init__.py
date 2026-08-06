"""
DOM Compiler module.

Compiles CV detections and LLM refinements into final DOM JSON
with locator strategies for Robot Framework automation.
"""

from visual_dom.core.domain.compiler.dom_compiler import DOMCompiler, DOMNode, compile_dom, ROLE_MAPPING

__all__ = ["DOMCompiler", "DOMNode", "compile_dom", "ROLE_MAPPING"]
