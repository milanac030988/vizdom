"""
Session folders in the Viewer's format, and the view of a DOM the GUI draws.

A session is ``output/sessions/<id>/`` holding ``screenshot.png``,
``dom_result.json`` (``{image_size, source, session_id, cv_stats, dom}``) and
``session_info.json``. The PyQt Viewer writes and reads the same files.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# REPO holds the code (src/, tools/, plugins/); HOME holds what the user makes
# (the session config and output/). In a checkout both are the repository. The
# installed Studio sets VIZDOM_REPO to its read-only resources folder and
# VIZDOM_HOME to a folder the user can write (Documents\VizDOM).
REPO = Path(os.environ.get("VIZDOM_REPO") or Path(__file__).resolve().parents[2])
HOME = Path(os.environ.get("VIZDOM_HOME") or REPO)
SESSIONS = HOME / "output" / "sessions"


def new_session_dir() -> Path:
    """A fresh ``output/sessions/<timestamp>`` (suffixed when two land in one second)."""
    SESSIONS.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    path, n = SESSIONS / base, 2
    while path.exists():
        path, n = SESSIONS / f"{base}_{n}", n + 1
    path.mkdir(parents=True)
    return path


def session_dir(session_id: str) -> Path:
    """The folder of ``session_id``; refuses ids that would leave the sessions root."""
    if not session_id or any(c in session_id for c in "/\\:") or session_id.startswith("."):
        raise KeyError(session_id)
    path = SESSIONS / session_id
    if not path.is_dir():
        raise KeyError(session_id)
    return path


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_session(path: Path, png: bytes, dom: Dict[str, Any], info: Dict[str, Any]) -> None:
    (path / "screenshot.png").write_bytes(png)
    size = dom.get("image_size") or [0, 0]
    width, height = (size[0], size[1]) if isinstance(size, (list, tuple)) else (
        size.get("width", 0), size.get("height", 0))
    result = {
        "image_size": {"width": width, "height": height},
        "source": "vizdom-studio",
        "session_id": path.name,
        "cv_stats": info.get("cv_stats", {}),
        "dom": dom,
    }
    (path / "dom_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    info = dict(info)
    info.update({
        "session_id": path.name,
        "timestamp": datetime.now().isoformat(),
        "image_size": {"width": width, "height": height},
        "element_count": len(dom.get("elements") or []),
    })
    (path / "session_info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def import_dom_file(dom_path: Path) -> str:
    """
    Open a ``dom_result.json`` from disk. Inside the sessions root it IS a
    session; elsewhere it is copied into a new one, with the screenshot that
    sits beside it (the Viewer's rule, ADR-026).
    """
    dom_path = Path(dom_path).resolve()
    try:
        rel = dom_path.parent.relative_to(SESSIONS.resolve())
        if len(rel.parts) == 1:
            return rel.parts[0]
    except ValueError:
        pass
    data = _read_json(dom_path)
    if not data or "dom" not in data:
        raise ValueError(f"{dom_path.name} is not a VizDOM result (no 'dom' section)")
    target = new_session_dir()
    shutil.copyfile(dom_path, target / "dom_result.json")
    for name in ("screenshot.png", "screenshot.jpg"):
        if (dom_path.parent / name).exists():
            shutil.copyfile(dom_path.parent / name, target / "screenshot.png")
            break
    info = _read_json(dom_path.parent / "session_info.json") or {}
    info.update({"session_id": target.name, "imported_from": str(dom_path)})
    (target / "session_info.json").write_text(json.dumps(info, indent=2, default=str),
                                              encoding="utf-8")
    return target.name


def list_sessions(limit: int = 200) -> List[Dict[str, Any]]:
    """Newest first; folders without a DOM (a capture that never analysed) are skipped."""
    if not SESSIONS.is_dir():
        return []
    out = []
    for path in sorted(SESSIONS.iterdir(), key=lambda p: p.name, reverse=True):
        if not (path / "dom_result.json").exists():
            continue
        info = _read_json(path / "session_info.json") or {}
        size = info.get("image_size") or {}
        out.append({
            "id": path.name,
            "timestamp": info.get("timestamp"),
            "element_count": info.get("element_count"),
            "window_title": info.get("window_title"),
            "capture_source": info.get("capture_source"),
            "detector": (info.get("cv_stats") or {}).get("detector") or info.get("detector"),
            "ocr_engine": info.get("ocr_engine"),
            "width": size.get("width"),
            "height": size.get("height"),
            "has_screenshot": (path / "screenshot.png").exists(),
        })
        if len(out) >= limit:
            break
    return out


def load_result(session_id: str) -> Dict[str, Any]:
    path = session_dir(session_id)
    data = _read_json(path / "dom_result.json")
    if not data or "dom" not in data:
        raise KeyError(session_id)
    return data


def load_info(session_id: str) -> Dict[str, Any]:
    return _read_json(session_dir(session_id) / "session_info.json") or {}


def _outline(node: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": node.get("id"),
            "children": [_outline(c) for c in node.get("children") or []]}


def session_view(session_id: str) -> Dict[str, Any]:
    """
    What the GUI draws: flat elements (each with the locator the exporter
    would write), the hierarchy as nested ids, and the capture provenance.
    """
    data = load_result(session_id)
    dom = data["dom"]
    elements = [dict(e) for e in dom.get("elements") or []]

    locators: Dict[str, str] = {}
    try:
        from visual_dom_viewer.core.tree import DOMTree
        from visual_dom_viewer.export.locators import element_locator
        tree = DOMTree.from_dict(data)
        for e in elements:
            node = tree.get_element_by_id(e["id"])
            if node is not None:
                locators[e["id"]] = element_locator(node)
    except Exception:  # noqa: BLE001 - the GUI still works with the fallback below
        pass
    for e in elements:
        e["locator"] = locators.get(e["id"]) or f"id={e['id']}"

    size = data.get("image_size") or {}
    if isinstance(size, (list, tuple)):
        size = {"width": size[0], "height": size[1]}
    if not size.get("width"):
        ds = dom.get("image_size") or [0, 0]
        size = {"width": ds[0], "height": ds[1]}
    hierarchy = dom.get("hierarchy")
    return {
        "id": session_id,
        "info": load_info(session_id),
        "image": size,
        "has_screenshot": (session_dir(session_id) / "screenshot.png").exists(),
        "elements": elements,
        "hierarchy": _outline(hierarchy) if hierarchy else None,
    }
