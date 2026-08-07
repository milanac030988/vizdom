"""
Shared X11 window helpers for the capture and actuator adapters (ADR-021).

The Linux counterpart of `win32_window`: raise a window by title using whichever
of the standard CLI tools is installed (`wmctrl` first — it is EWMH-correct and
matches by title natively — then `xdotool`).

Wayland has no unprivileged equivalent, so under Wayland these return False. Like
their Win32 twins, the functions are best-effort and never raise.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Optional

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


def active_window_title() -> Optional[str]:
    """Title of the currently focused X11 window, or None."""
    if not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                             capture_output=True, timeout=5)
        title = out.stdout.decode(errors="replace").strip()
        return title if out.returncode == 0 and title else None
    except Exception:
        return None


def focus_window_by_title(title: str, settle: float = 0.25) -> bool:
    """
    Activate the window whose title contains ``title``.

    Tries ``wmctrl -a`` then ``xdotool search --name … windowactivate``, then
    verifies the active window really changed (an unmanaged compositor or a
    Wayland session can accept the command and do nothing).
    """
    if not title:
        return False
    needle = title.strip()
    tried = False
    try:
        if shutil.which("wmctrl"):
            tried = True
            subprocess.run(["wmctrl", "-a", needle], capture_output=True, timeout=5)
        if shutil.which("xdotool"):
            tried = True
            subprocess.run(["xdotool", "search", "--name", needle,
                            "windowactivate", "--sync", "%1"],
                           capture_output=True, timeout=10)
        if not tried:
            log.warning("Cannot raise %r: neither wmctrl nor xdotool is installed "
                        "(apt install wmctrl xdotool)", needle)
            return False
        if settle:
            time.sleep(settle)
        active = active_window_title()
        if active is None:
            # No way to verify (no xdotool); report failure rather than guess.
            log.warning("Raised %r but cannot verify focus without xdotool", needle)
            return False
        ok = needle.lower() in active.lower()
        if not ok:
            log.warning("Could not focus %r - active window is %r", needle, active)
        return ok
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        log.warning("focus_window_by_title(%r) failed: %s", needle, exc)
        return False
