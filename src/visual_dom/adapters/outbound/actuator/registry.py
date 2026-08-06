"""
Actuator strategy registry with plugin auto-discovery (ADR-019).

Discovers `ActuatorStrategy` subclasses from:
  1. the built-in package `visual_dom.adapters.outbound.actuator.builtin`, and
  2. a plugins folder - `$VIZDOM_ACTUATOR_PLUGINS`, else `<repo>/plugins/actuator/`.
Any `.py` there defining an `ActuatorStrategy` subclass with a unique `name` is
registered automatically. Selection is by name (from config/CLI):
    create_actuator("desktop")  ->  DesktopActuator instance

Security note: discovery IMPORTS the plugin files (executes their top-level
code). Only use plugins you trust. (Actuators also drive real input - a plugin
can move a physical arm; trust matters doubly here.)
"""

import importlib
import importlib.util
import inspect
import os
import pkgutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from visual_dom.logging_utils import get_logger
from visual_dom.core.ports.outbound.actuator_port import ActuatorStrategy

log = get_logger(__name__)

_REGISTRY: Dict[str, Type[ActuatorStrategy]] = {}
_DISCOVERED = False


def register(cls: Type[ActuatorStrategy]) -> None:
    """Register an ActuatorStrategy subclass by its `name` (last one wins)."""
    name = getattr(cls, "name", None)
    if not name or name == "base":
        return
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        log.warning("Actuator strategy name %r redefined by %s", name, cls.__module__)
    _REGISTRY[name] = cls


def _register_subclasses_in_module(module) -> None:
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, ActuatorStrategy) and obj is not ActuatorStrategy:
            register(obj)


def _plugins_dir() -> Path:
    env = os.environ.get("VIZDOM_ACTUATOR_PLUGINS")
    if env:
        return Path(env)
    # <repo root>/plugins/actuator - this file: src/visual_dom/actuator/registry.py
    try:
        root = Path(__file__).resolve().parents[5]
    except IndexError:  # pragma: no cover
        root = Path.cwd()
    return root / "plugins" / "actuator"


def discover(force: bool = False) -> None:
    """Populate the registry from built-ins + the plugins folder (idempotent)."""
    global _DISCOVERED
    if _DISCOVERED and not force:
        return

    # 1. built-ins
    from visual_dom.adapters.outbound.actuator import builtin
    for info in pkgutil.iter_modules(builtin.__path__):
        try:
            mod = importlib.import_module(f"{builtin.__name__}.{info.name}")
            _register_subclasses_in_module(mod)
        except Exception as e:
            log.warning("Skipping built-in actuator module %s: %s", info.name, e)

    # 2. external plugins folder
    pdir = _plugins_dir()
    if pdir.is_dir():
        for py in sorted(pdir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"vizdom_actuator_plugin_{py.stem}", py)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _register_subclasses_in_module(mod)
                log.info("Loaded actuator plugin: %s", py.name)
            except Exception as e:
                log.warning("Skipping actuator plugin %s: %s", py.name, e)

    _DISCOVERED = True


def create_actuator(name: str, **kwargs: Any) -> ActuatorStrategy:
    """
    Instantiate an actuator strategy by name.

    Raises ValueError with the list of known names if `name` is unknown.
    """
    discover()
    key = (name or "").lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown actuator strategy {name!r}. Available: {', '.join(sorted(_REGISTRY)) or '(none)'}"
        )
    return _REGISTRY[key](**kwargs)


def list_actuators() -> List[Dict[str, Any]]:
    """Metadata for all discovered strategies: name, platform, description, available."""
    discover()
    out: List[Dict[str, Any]] = []
    for name, cls in sorted(_REGISTRY.items()):
        try:
            available = cls.is_available()
        except Exception:
            available = False
        out.append({
            "name": name,
            "platform": getattr(cls, "platform", "any"),
            "description": getattr(cls, "description", ""),
            "available": available,
            "module": cls.__module__,
        })
    return out


def auto_select() -> Optional[str]:
    """Pick a sensible default actuator for the current OS (first available)."""
    import sys
    # desktop actuation works on win/mac/linux via pyautogui
    if not sys.platform.startswith("android") and _is_available("desktop"):
        return "desktop"
    for c in list_actuators():
        if c["available"]:
            return c["name"]
    return None


def _is_available(name: str) -> bool:
    for c in list_actuators():
        if c["name"] == name:
            return bool(c["available"])
    return False
