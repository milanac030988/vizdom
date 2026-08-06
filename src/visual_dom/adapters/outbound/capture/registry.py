"""
Capture strategy registry with plugin auto-discovery (ADR-018).

Discovers `CaptureStrategy` subclasses from:
  1. the built-in package `visual_dom.adapters.outbound.capture.builtin`, and
  2. a plugins folder — `$VIZDOM_CAPTURE_PLUGINS`, else `<repo>/plugins/capture/`.
Any `.py` there defining a `CaptureStrategy` subclass with a unique `name` is
registered automatically. Selection is by name (from config/CLI):
    create_capture("windows")  ->  WindowsCapture instance

Security note: discovery IMPORTS the plugin files (executes their top-level
code). Only use plugins you trust.
"""

import importlib
import importlib.util
import inspect
import os
import pkgutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from visual_dom.logging_utils import get_logger
from visual_dom.core.ports.outbound.capture_port import CaptureStrategy

log = get_logger(__name__)

_REGISTRY: Dict[str, Type[CaptureStrategy]] = {}
_DISCOVERED = False


def register(cls: Type[CaptureStrategy]) -> None:
    """Register a CaptureStrategy subclass by its `name` (last one wins)."""
    name = getattr(cls, "name", None)
    if not name or name == "base":
        return
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        log.warning("Capture strategy name %r redefined by %s", name, cls.__module__)
    _REGISTRY[name] = cls


def _register_subclasses_in_module(module) -> None:
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, CaptureStrategy) and obj is not CaptureStrategy:
            register(obj)


def _plugins_dir() -> Path:
    env = os.environ.get("VIZDOM_CAPTURE_PLUGINS")
    if env:
        return Path(env)
    # <repo root>/plugins/capture — this file: src/visual_dom/adapters/outbound/capture/registry.py
    try:
        root = Path(__file__).resolve().parents[5]
    except IndexError:  # pragma: no cover
        root = Path.cwd()
    return root / "plugins" / "capture"


def discover(force: bool = False) -> None:
    """Populate the registry from built-ins + the plugins folder (idempotent)."""
    global _DISCOVERED
    if _DISCOVERED and not force:
        return

    # 1. built-ins
    from visual_dom.adapters.outbound.capture import builtin
    for info in pkgutil.iter_modules(builtin.__path__):
        try:
            mod = importlib.import_module(f"{builtin.__name__}.{info.name}")
            _register_subclasses_in_module(mod)
        except Exception as e:
            log.warning("Skipping built-in capture module %s: %s", info.name, e)

    # 2. external plugins folder
    pdir = _plugins_dir()
    if pdir.is_dir():
        for py in sorted(pdir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"vizdom_capture_plugin_{py.stem}", py)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _register_subclasses_in_module(mod)
                log.info("Loaded capture plugin: %s", py.name)
            except Exception as e:
                log.warning("Skipping capture plugin %s: %s", py.name, e)

    _DISCOVERED = True


def create_capture(name: str, **kwargs: Any) -> CaptureStrategy:
    """
    Instantiate a capture strategy by name.

    Raises ValueError with the list of known names if `name` is unknown.
    """
    discover()
    key = (name or "").lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown capture strategy {name!r}. Available: {', '.join(sorted(_REGISTRY)) or '(none)'}"
        )
    return _REGISTRY[key](**kwargs)


def list_captures() -> List[Dict[str, Any]]:
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
    """Pick a sensible default capture strategy for the current OS (first available)."""
    import sys
    pref = ("windows" if sys.platform.startswith("win")
            else "linux" if sys.platform.startswith("linux") else None)
    caps = {c["name"]: c for c in list_captures()}
    if pref and caps.get(pref, {}).get("available"):
        return pref
    for c in list_captures():
        if c["available"]:
            return c["name"]
    return None
