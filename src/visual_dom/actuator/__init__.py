"""
Pluggable input actuation (ADR-019).

Strategy pattern + auto-discovery: subclass `ActuatorStrategy`, drop it in the
actuator plugins folder, and select it by name via `create_actuator`. The
write-side twin of `visual_dom.capture` (ADR-018).

    from visual_dom.actuator import create_actuator, auto_select
    act = create_actuator(auto_select())     # or "desktop" / "android" / <your plugin>
    act.tap(0.5, 0.5, image_size=(1920, 1080))   # normalized coords -> device space
    act.type_text("hello")

Actions take normalized coordinates (nx, ny) in [0, 1]; each strategy maps them to
its own device space (see ActuatorStrategy).
"""

from .base import ActuatorStrategy
from .registry import (
    create_actuator,
    list_actuators,
    register,
    discover,
    auto_select,
)

__all__ = [
    "ActuatorStrategy",
    "create_actuator",
    "list_actuators",
    "register",
    "discover",
    "auto_select",
]
