"""
Window geometry in physical pixels whatever the process's DPI awareness.

Regression for the Studio bridge (2026-11-17): a process that is only system-DPI
aware, with a system DPI from an earlier docking (100%) on a 125% screen, read the
target's client rectangle scaled by 96/120 and cropped the wrong part of the screen.
"""
import ctypes
import sys

import pytest

from visual_dom.adapters.outbound import win32_window as w

pytestmark = pytest.mark.skipif(not sys.platform.startswith("win"), reason="Win32 only")


def _thread_awareness():
    user32 = ctypes.windll.user32
    user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return user32.GetAwarenessFromDpiAwarenessContext(user32.GetThreadDpiAwarenessContext())


def _set_thread(context):
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(context))


def test_physical_pixels_is_per_monitor_inside_and_restores_after():
    old = _set_thread(-1)                       # DPI unaware, the worst case
    try:
        assert _thread_awareness() == 0
        with w.physical_pixels():
            assert _thread_awareness() == 2     # per-monitor
        assert _thread_awareness() == 0         # the caller's context is back
    finally:
        _set_thread(old)


def test_physical_pixels_restores_after_an_exception():
    old = _set_thread(-1)
    try:
        with pytest.raises(RuntimeError):
            with w.physical_pixels():
                raise RuntimeError("boom")
        assert _thread_awareness() == 0
    finally:
        _set_thread(old)


def test_client_rect_does_not_depend_on_the_callers_awareness():
    hwnd = ctypes.windll.user32.GetDesktopWindow()
    old = _set_thread(-1)
    try:
        unaware_caller = w.client_rect_on_screen(hwnd)
    finally:
        _set_thread(old)
    with w.physical_pixels():
        aware_caller = w.client_rect_on_screen(hwnd)
    assert unaware_caller == aware_caller
