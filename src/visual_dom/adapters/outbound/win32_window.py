"""
Shared Win32 window helpers for the capture and actuator adapters (ADR-021).

Both driven ports need the same two things on Windows: *find* a top-level window
by title, and *bring it to the foreground*. Keeping the ctypes details here means
the capture and actuator strategies share one proven implementation instead of
duplicating it.

Why focusing matters (it is a correctness concern, not a convenience):
  * a full-screen grab photographs whatever is on top — if the application under
    test is behind another window, the wrong pixels are analysed;
  * coordinate-based actuation clicks whatever window sits at that point, and
    typing goes to whatever holds *keyboard focus* — so without focus management
    a test can click and type into a completely different application.

Windows deliberately restricts ``SetForegroundWindow`` from background processes
(the "foreground lock"), so the raise routine escalates through three techniques
and then *verifies* the result rather than assuming success.

Every function is best-effort and must never raise: they return None/False.
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional, Tuple

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


def is_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


def _user32_kernel32():
    import ctypes
    return ctypes.windll.user32, ctypes.windll.kernel32


def list_windows() -> List[Tuple[int, str]]:
    """Visible top-level windows as (hwnd, title); [] off-Windows or on failure."""
    if not is_windows():
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32, _ = _user32_kernel32()
        out: List[Tuple[int, str]] = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n > 0:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    title = buf.value.strip()
                    if title:
                        out.append((int(hwnd), title))
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
        return out
    except Exception:
        return []


def find_window(title: str) -> Optional[int]:
    """
    hwnd of a visible window whose title matches ``title``.

    Exact (case-insensitive) match wins; otherwise a unique case-insensitive
    substring match. An ambiguous substring returns None and logs the candidates
    — guessing which window to drive would be worse than failing.
    """
    if not title:
        return None
    windows = list_windows()
    needle = title.strip().lower()
    exact = [h for h, t in windows if t.lower() == needle]
    if exact:
        if len(exact) > 1:
            # Real case: an app can own several windows with the same title (a
            # hidden helper alongside the visible one). EnumWindows walks the
            # Z-order, so the first is the most recently active - the best guess.
            log.info("%d windows are titled %r; taking the topmost (Z-order)",
                     len(exact), title)
        return exact[0]
    partial = [(h, t) for h, t in windows if needle in t.lower()]
    if len(partial) == 1:
        return partial[0][0]
    if len(partial) > 1:
        log.warning("Window title %r is ambiguous (%d matches: %s) - refusing to guess",
                    title, len(partial), ", ".join(t for _, t in partial[:5]))
    return None


def foreground_hwnd() -> Optional[int]:
    if not is_windows():
        return None
    try:
        user32, _ = _user32_kernel32()
        return int(user32.GetForegroundWindow())
    except Exception:
        return None


def _raise_window(hwnd: int, settle: float, use_attach: bool = False) -> None:
    """
    The actual raise sequence. May block: several of these calls are synchronous
    with the owning window's message pump, which is why `bring_to_front` runs this
    under a watchdog.

    ``use_attach`` enables the AttachThreadInput escalation, which is powerful but
    can deadlock (see below) - so it is the second attempt, not the first.
    """
    user32, kernel32 = _user32_kernel32()

    SW_RESTORE, SW_SHOWNORMAL = 9, 1
    HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
    SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0040
    VK_MENU, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x12, 0x0001, 0x0002

    user32.ShowWindow(hwnd, SW_RESTORE)

    current = user32.GetForegroundWindow()
    current_thread = user32.GetWindowThreadProcessId(current, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    our_thread = kernel32.GetCurrentThreadId()

    # Attaching to the CURRENT FOREGROUND thread is the classic way to inherit
    # foreground rights - and a deadlock waiting to happen: sharing an input queue
    # with a thread that is not pumping messages blocks us until it does. That is
    # not hypothetical here; the caller of a capture service is often a GUI whose
    # UI thread is blocked inside its own synchronous capture. Only attach when
    # Windows says that window is responsive, and rely on the synthetic Alt tap
    # (which grants the same rights) otherwise.
    attach_current = False
    if use_attach and current_thread != our_thread and current:
        try:
            attach_current = not bool(user32.IsHungAppWindow(current))
        except Exception:
            attach_current = False

    attached_current = attached_target = False
    try:
        if attach_current:
            attached_current = bool(
                user32.AttachThreadInput(our_thread, current_thread, True))
        if use_attach and target_thread not in (our_thread, current_thread):
            attached_target = bool(
                user32.AttachThreadInput(our_thread, target_thread, True))

        # Synthetic Alt tap: Windows grants foreground rights after input.
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

        user32.ShowWindow(hwnd, SW_SHOWNORMAL)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        try:
            # Designed for exactly this (alt-tab style switching) and does not
            # depend on input-queue attachment.
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        # Temporary topmost, then drop the flag so we don't leave the SUT
        # permanently above every other window.
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached_current:
            user32.AttachThreadInput(our_thread, current_thread, False)
        if attached_target:
            user32.AttachThreadInput(our_thread, target_thread, False)

    if settle:
        time.sleep(settle)              # focus changes are asynchronous


def bring_to_front(hwnd: int, settle: float = 0.25, verify: bool = True,
                   budget: float = 5.0) -> bool:
    """
    Raise and focus ``hwnd``, defeating the foreground lock where possible.

    Escalates: restore-if-minimized -> AttachThreadInput (only if the current
    foreground window is responsive) -> synthetic Alt keypress (Windows grants
    foreground rights after input) -> `SwitchToThisWindow` -> temporary
    HWND_TOPMOST. Then waits ``settle`` seconds and confirms the window really is
    foreground.

    Runs under a ``budget`` (seconds) watchdog, because the Win32 calls involved
    are synchronous with the owning window's message pump and can stall for as long
    as some other application is busy. Exceeding the budget returns False rather
    than holding the caller - which matters most for the capture/actuator services,
    where a stuck raise would otherwise consume a worker thread and blow the
    client's RPC deadline.

    Returns True only when verification passes (or when verify=False).
    """
    if not is_windows() or not hwnd:
        return False

    # Phase 1 without AttachThreadInput (cannot deadlock), phase 2 with it only if
    # the first attempt did not take. Ordering it this way means the normal case
    # never touches the API that can block on another application's message pump.
    for use_attach in (False, True):
        result = {}

        def run():
            try:
                _raise_window(int(hwnd), settle, use_attach=use_attach)
                result["ok"] = True
            except Exception as exc:  # noqa: BLE001 - best effort by contract
                result["error"] = exc

        worker = threading.Thread(target=run, name="vizdom-bring-to-front", daemon=True)
        worker.start()
        worker.join(timeout=max(0.5, float(budget)))

        if worker.is_alive():
            log.warning("Raising hwnd %s exceeded its %.1fs budget - another "
                        "application is not processing messages. Reporting failure "
                        "instead of waiting; the window may still come forward.",
                        hwnd, budget)
            return False
        if "error" in result:
            log.warning("bring_to_front failed: %s", result["error"])
            return False
        if not verify:
            return True
        if foreground_hwnd() == int(hwnd):
            return True
        if not use_attach:
            log.info("hwnd %s did not come forward; retrying with input-queue "
                     "attachment", hwnd)

    log.warning("Could not bring hwnd %s to the foreground (Windows "
                "foreground lock); the screen may show another window", hwnd)
    return False


_dpi_aware_done = False


def ensure_process_dpi_aware() -> bool:
    """
    Make this process per-monitor DPI-aware, so window rectangles are reported in
    the same **physical pixels** a screenshot contains.

    Without this, a DPI-unaware process on a 125%-scaled display is told the screen
    is 1536x864 while the framebuffer is 1920x1080 — and a window rectangle read in
    that coordinate space crops the wrong region. Screenshot libraries (mss) set
    this themselves on first grab, which makes the geometry depend on call order;
    doing it explicitly and early removes that hazard.

    Idempotent and best-effort: fails harmlessly when awareness is already set (a Qt
    application typically sets it at startup), returning False.
    """
    global _dpi_aware_done
    if _dpi_aware_done or not is_windows():
        return _dpi_aware_done
    try:
        import ctypes
        user32, _ = _user32_kernel32()
        ok = False
        try:                       # Windows 10 1703+: per-monitor v2
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
            ok = bool(user32.SetProcessDpiAwarenessContext(
                DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
        except Exception:
            ok = False
        if not ok:
            try:                   # Windows 8.1+: per-monitor v1
                shcore = ctypes.windll.shcore
                ok = shcore.SetProcessDpiAwareness(2) == 0
            except Exception:
                ok = False
        if not ok:
            try:                   # Vista+: system-DPI aware
                ok = bool(user32.SetProcessDPIAware())
            except Exception:
                ok = False
        _dpi_aware_done = True     # do not retry: already set is a normal failure
        if ok:
            log.info("Process set to per-monitor DPI awareness for accurate "
                     "window geometry")
        return ok
    except Exception:
        _dpi_aware_done = True
        return False


def client_rect_on_screen(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """
    (x, y, w, h) of a window's **client area** in screen coordinates.

    The client area excludes the title bar, frame and drop shadow, so a crop of it
    contains only the application's own content. Returns None on failure or for a
    zero-sized window (minimised).
    """
    if not is_windows() or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32, _ = _user32_kernel32()

        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None

        point = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
            return None
        return int(point.x), int(point.y), int(w), int(h)
    except Exception:
        return None


def _display_rects_physical():
    """
    Physical rectangles of every attached display, from the display *driver*
    (`EnumDisplaySettings`) rather than from window-manager metrics.

    This is the one source that does not depend on the process's DPI awareness —
    which matters because a third-party import can claim awareness before we do
    (pyautogui calls `SetProcessDPIAware()` at import time) and awareness cannot be
    changed afterwards. `GetSystemMetrics` then reports a *scaled* desktop, and with
    per-monitor scaling that distortion is not even uniform, so it cannot be undone
    by a single factor. Reading the driver's mode sidesteps the whole problem.
    """
    import ctypes
    from ctypes import wintypes

    class DEVMODE(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
            ("dmPositionX", wintypes.LONG), ("dmPositionY", wintypes.LONG),
            ("dmDisplayOrientation", wintypes.DWORD),
            ("dmDisplayFixedOutput", wintypes.DWORD),
            ("dmColor", wintypes.SHORT), ("dmDuplex", wintypes.SHORT),
            ("dmYResolution", wintypes.SHORT), ("dmTTOption", wintypes.SHORT),
            ("dmCollate", wintypes.SHORT), ("dmFormName", wintypes.WCHAR * 32),
            ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
        ]

    class DISPLAY_DEVICE(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128),
        ]

    DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
    ENUM_CURRENT_SETTINGS = -1
    user32, _ = _user32_kernel32()
    rects, i = [], 0
    while True:
        dd = DISPLAY_DEVICE()
        dd.cb = ctypes.sizeof(dd)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        if dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(dm)
            if user32.EnumDisplaySettingsW(dd.DeviceName, ENUM_CURRENT_SETTINGS,
                                           ctypes.byref(dm)):
                rects.append((int(dm.dmPositionX), int(dm.dmPositionY),
                              int(dm.dmPelsWidth), int(dm.dmPelsHeight)))
        i += 1
    return rects


def virtual_screen_rect() -> Optional[Tuple[int, int, int, int]]:
    """
    (left, top, width, height) of the **virtual screen** — the bounding box of all
    monitors — in physical pixels.

    This is the single coordinate space that both driven ports normalize against
    (ADR-021). It has to be the *whole desktop* rather than one monitor: capture and
    actuation exchange normalized [0,1] coordinates, so if the capture side
    normalized against the monitor it grabbed while the actuator denormalized
    against the desktop, every click on a secondary display would be misplaced.
    ``left``/``top`` are negative for monitors above or left of the primary one.
    """
    if not is_windows():
        return None
    ensure_process_dpi_aware()          # for everything else that reads geometry
    try:
        rects = _display_rects_physical()
        if rects:
            left = min(r[0] for r in rects)
            top = min(r[1] for r in rects)
            right = max(r[0] + r[2] for r in rects)
            bottom = max(r[1] + r[3] for r in rects)
            return (left, top, right - left, bottom - top)
    except Exception:
        pass
    try:                                # fallback: window-manager metrics
        import ctypes
        gsm = ctypes.windll.user32.GetSystemMetrics
        left, top = int(gsm(76)), int(gsm(77))
        width, height = int(gsm(78)), int(gsm(79))
        return (left, top, width, height) if width > 0 and height > 0 else None
    except Exception:
        return None


def warn_if_dpi_context_mismatched() -> bool:
    """
    True when the process's reported desktop disagrees with the physical one.

    That happens when another component claimed DPI awareness first (typically
    ``import pyautogui``, which calls ``SetProcessDPIAware()``). Coordinates handed
    to such a component are then interpreted in a scaled space, so clicks on a
    scaled multi-monitor desktop can be misplaced. It cannot be fixed after the
    fact, so say so clearly instead of silently clicking the wrong pixel.
    """
    if not is_windows():
        return False
    try:
        import ctypes
        physical = virtual_screen_rect()
        gsm = ctypes.windll.user32.GetSystemMetrics
        reported = (int(gsm(76)), int(gsm(77)), int(gsm(78)), int(gsm(79)))
        if not physical or physical == reported:
            return False
        log.warning(
            "DPI context mismatch: the desktop is physically %dx%d at (%d, %d) but "
            "this process sees %dx%d at (%d, %d). Another library claimed DPI "
            "awareness first (pyautogui does this on import) and it cannot be "
            "changed afterwards. On a scaled multi-monitor desktop, clicks may be "
            "misplaced - import VisualGuiLibrary (or visual_dom) BEFORE pyautogui.",
            physical[2], physical[3], physical[0], physical[1],
            reported[2], reported[3], reported[0], reported[1])
        return True
    except Exception:
        return False


def logical_screen_size() -> Optional[Tuple[int, int]]:
    """
    Primary screen size **as this process sees it** (`GetSystemMetrics`).

    On a scaled display a DPI-unaware process is told e.g. 1280x720 while the
    framebuffer (and any screenshot) is 1920x1080. Comparing this against the
    captured frame yields the scale factor needed to map window rectangles onto
    screenshot pixels — see `scale_rect_to_frame`.
    """
    if not is_windows():
        return None
    try:
        user32, _ = _user32_kernel32()
        SM_CXSCREEN, SM_CYSCREEN = 0, 1
        w = int(user32.GetSystemMetrics(SM_CXSCREEN))
        h = int(user32.GetSystemMetrics(SM_CYSCREEN))
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def scale_rect_to_frame(rect: Tuple[int, int, int, int],
                        frame_w: int, frame_h: int) -> Tuple[int, int, int, int]:
    """
    Convert a window rectangle from this process's coordinate space into the
    captured frame's pixel space, correcting for display scaling.

    The factor is derived from the frame itself rather than from a DPI query, so it
    is right whether or not the process happens to be DPI-aware.
    """
    logical = logical_screen_size()
    if not logical:
        return rect
    sx = frame_w / float(logical[0])
    sy = frame_h / float(logical[1])
    if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
        return rect
    x, y, w, h = rect
    log.info("Display scaling detected (%.2fx, %.2fy): mapping window rect to "
             "screenshot pixels", sx, sy)
    return (int(round(x * sx)), int(round(y * sy)),
            int(round(w * sx)), int(round(h * sy)))


def focus_window_by_title(title: str, settle: float = 0.25) -> bool:
    """find_window + bring_to_front, for callers that only know a title."""
    hwnd = find_window(title)
    if hwnd is None:
        log.warning("No unique visible window matching %r", title)
        return False
    return bring_to_front(hwnd, settle=settle)
