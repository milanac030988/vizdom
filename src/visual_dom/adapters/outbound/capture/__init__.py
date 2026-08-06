"""
Pluggable screenshot capture (ADR-018).

Strategy pattern + auto-discovery: subclass `CaptureStrategy`, drop it in the
capture plugins folder, and select it by name via `create_capture`.

    from visual_dom.adapters.outbound.capture import create_capture, list_captures, auto_select
    cap = create_capture(auto_select())     # or "windows" / "android" / "camera" / <your plugin>
    image = cap.capture()                    # BGR numpy image for the pipeline
"""

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy
from visual_dom.adapters.outbound.capture.registry import create_capture, list_captures, register, discover, auto_select

__all__ = [
    "CaptureStrategy",
    "create_capture",
    "list_captures",
    "register",
    "discover",
    "auto_select",
]
