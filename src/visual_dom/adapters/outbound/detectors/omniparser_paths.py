"""
Where OmniParser lives on disk, and whether it can run here.

One resolution shared by the omniparser backend, the ADR-027 modular stages,
the in-process pipeline, the Viewer and the detector service: explicit
argument, then the OMNIPARSER_* env var, then the standard project location.
Nothing here writes to os.environ or imports OmniParser itself, so it is cheap
to call before deciding which backend or stage to build.
"""

import os
from typing import Dict, Optional

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


# detectors/ -> outbound -> adapters -> visual_dom -> src -> project root.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             "..", "..", "..", "..", ".."))

# Where the setup script puts the weights and the cloned repo, relative to the
# project root: (key, env var, relative path, is a directory).
_STANDARD_LOCATIONS = (
    ("icon_detect_path", "OMNIPARSER_ICON_DETECT",
     os.path.join("models", "omniparser", "icon_detect", "model.pt"), False),
    ("icon_caption_path", "OMNIPARSER_ICON_CAPTION",
     os.path.join("models", "omniparser", "icon_caption_florence"), True),
    ("omniparser_root", "OMNIPARSER_ROOT",
     os.path.join("third_party", "OmniParser"), True),
)


def resolve_omniparser_paths(
    omniparser_root: Optional[str] = None,
    icon_detect_path: Optional[str] = None,
    icon_caption_path: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Dict[str, str]:
    """
    Resolve OmniParser's repo and weight paths: explicit argument, then the
    OMNIPARSER_* env var, then the standard project location.

    Returns only the keys that resolved (icon_detect_path, icon_caption_path,
    omniparser_root), so the result can be passed straight to OmniParserBackend
    or the ADR-027 stages. Never writes to os.environ.
    """
    explicit = {"omniparser_root": omniparser_root,
                "icon_detect_path": icon_detect_path,
                "icon_caption_path": icon_caption_path}
    root = project_root or _PROJECT_ROOT
    out: Dict[str, str] = {}
    for key, env_var, rel, is_dir in _STANDARD_LOCATIONS:
        value = explicit[key] or os.environ.get(env_var)
        if not value:
            cand = os.path.join(root, rel)
            if os.path.isdir(cand) if is_dir else os.path.isfile(cand):
                value = cand
        if value:
            out[key] = value
    return out


def box_threshold_from_env(default: Optional[float] = None) -> Optional[float]:
    """OMNIPARSER_BOX_THRESHOLD as a float, or ``default`` when unset/invalid."""
    raw = os.environ.get("OMNIPARSER_BOX_THRESHOLD")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("Ignoring invalid OMNIPARSER_BOX_THRESHOLD=%r", raw)
        return default


def omniparser_unavailable_reason(
    omniparser_root: Optional[str],
    required: Optional[Dict[str, Optional[str]]] = None,
) -> Optional[str]:
    """
    Why OmniParser's ``util.utils`` cannot be used here, or None when it can.

    Checks every ``required`` path exists ({label: path}), that ultralytics is
    installed and that the repo is importable from ``omniparser_root``
    (without leaving it on sys.path).
    """
    import sys

    for label, value in (required or {}).items():
        if not value:
            return f"{label} not found"
        if not os.path.exists(value):
            return f"{label} not found at {value}"
    if _module_missing("ultralytics"):
        return "ultralytics is not installed"
    added = bool(omniparser_root) and omniparser_root not in sys.path
    if added:
        sys.path.insert(0, omniparser_root)
    try:
        if _module_missing("util.utils"):
            return ("the OmniParser repo (util.utils) is not importable - "
                    "set OMNIPARSER_ROOT")
    finally:
        if added:
            sys.path.remove(omniparser_root)
    return None


def _module_missing(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ValueError):
        return True
