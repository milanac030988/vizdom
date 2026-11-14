"""Region guard for refresh=element (ADR-023 1.1): off by default, and when on,
a changed neighbourhood or an empty read re-analyses the whole screen."""

import numpy as np
import pytest

from visual_dom.config import VizDomConfig
from visual_gui_library.keywords.capture import CaptureKeywords

W, H = 400, 300
FIELD = [100, 100, 260, 130]          # the text box whose value is read back


class _Text:
    def __init__(self, text):
        self.text, self.bounds = text, [0, 0, 10, 10]


class _Ocr:
    """Reads the 'value' painted into a crop: its brightest grey level."""

    def detect(self, crop):
        level = int(crop.max())
        return [_Text(f"v{level}")] if level > 60 else []


def _screen(value=200, field=FIELD, label_at=(20, 100)):
    """A dark screen with a label left of a field; the field shows ``value``."""
    img = np.zeros((H, W, 3), dtype=np.uint8)
    lx, ly = label_at
    img[ly:ly + 30, lx:lx + 70] = 50                 # the label beside the field
    x1, y1, x2, y2 = field
    if value:
        img[y1 + 8:y2 - 8, x1 + 8:x2 - 8] = value    # the text inside the field
    return img


def _dom(field=FIELD):
    return {"image_size": [W, H], "elements": [
        {"id": "E1", "hint": "Email", "role": "edittext", "bounds": list(field)}]}


class _Lib(CaptureKeywords):
    """The capture keywords over a scripted screen, with a countable full scan."""

    def __init__(self, first):
        super().__init__()
        self.screen = first
        self.grabs = 0
        self.full_scans = 0
        self.next_dom = None
        self._refresh_ocr = _Ocr()
        self.dump_visual_dom(image=first)
        self.full_scans = 0

    def _grab_frame(self):
        self.grabs += 1
        return self.screen

    def _get_refresh_ocr(self):
        return self._refresh_ocr

    def dump_visual_dom(self, image=None, **_):
        self.full_scans += 1
        if image is None:
            image = self._grab_frame()
        self._current_dom = self.next_dom or _dom()
        self._dom_screenshot = image
        self._dom_stale = False
        self._update_finder()
        return self._current_dom


def test_the_guard_is_off_by_default_everywhere():
    assert VizDomConfig.default().recap.region_guard is False
    assert CaptureKeywords()._region_guard is False


def test_off_reads_the_cached_bounds_even_when_the_layout_moved():
    # the behaviour before the guard existed: one grab, no comparison, no scan
    lib = _Lib(_screen(200))
    lib.screen = _screen(120, field=[100, 180, 260, 210], label_at=(20, 180))
    assert lib.get_element_value("hint=Email") == ""
    assert (lib.grabs, lib.full_scans) == (1, 0)


def test_on_reads_only_the_region_when_the_surroundings_are_unchanged():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    lib.screen = _screen(120)                 # the value changed, nothing else
    lib.verify_element_value("hint=Email", "v120")
    assert (lib.grabs, lib.full_scans) == (1, 0)


def test_on_rescans_the_screen_when_the_field_moved():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    moved = [100, 180, 260, 210]
    lib.screen = _screen(120, field=moved, label_at=(20, 180))
    lib.next_dom = _dom(moved)
    assert lib.get_element_value("hint=Email") == "v120"
    assert (lib.grabs, lib.full_scans) == (1, 1), "one grab serves guard and rescan"
    # the new screenshot is the reference now: the next read is a region read
    lib.screen = _screen(90, field=moved, label_at=(20, 180))
    assert lib.get_element_value("hint=Email") == "v90"
    assert lib.full_scans == 1


def test_a_small_shift_in_a_sparse_neighbourhood_is_seen_by_the_band():
    # 20 px down: the crop still reads text (cut in half), so only the band can
    # tell; by area the moved label is about a tenth of it, by structure nearly all
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    shifted = [100, 120, 260, 150]
    lib.screen = _screen(120, field=shifted, label_at=(20, 120))
    reason = lib._region_changed(_dom()["elements"][0], lib.screen)
    assert reason and "surrounds it changed" in reason
    lib.next_dom = _dom(shifted)
    assert lib.get_element_value("hint=Email") == "v120"
    assert lib.full_scans == 1


def test_on_rescans_when_something_covers_the_neighbourhood():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    covered = _screen(200)
    covered[60:170, 60:300] = 180             # a dialog over the field
    lib.screen = covered
    lib.get_element_value("hint=Email")
    assert lib.full_scans == 1


def test_on_an_empty_read_is_checked_against_a_full_scan():
    # an emptied field and a field that slid away look the same in the crop
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    lib.screen = _screen(0)
    assert lib.get_element_value("hint=Email") == ""
    assert lib.full_scans == 1


def test_on_a_resized_capture_is_never_read_by_old_bounds():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    lib.screen = np.zeros((H + 40, W + 40, 3), dtype=np.uint8)
    assert "the capture is now" in lib._region_changed(_dom()["elements"][0], lib.screen)
    lib.get_element_value("hint=Email")
    assert lib.full_scans == 1


def test_on_a_vanished_element_fails_like_any_unresolved_locator():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    lib.screen = np.zeros((H, W, 3), dtype=np.uint8)
    lib.next_dom = {"image_size": [W, H], "elements": []}
    with pytest.raises(Exception):
        lib.verify_element_value("hint=Email", "v200")


def test_a_loaded_dom_has_no_reference_and_is_read_unchecked(tmp_path):
    import json
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    path = tmp_path / "dom.json"
    path.write_text(json.dumps(_dom()), encoding="utf-8")
    lib.load_visual_dom(str(path))
    lib.screen = _screen(120)
    assert lib.get_element_value("hint=Email") == "v120"
    assert lib.full_scans == 0 and lib._guard_warned_no_reference


def test_the_tolerance_decides_how_much_change_passes():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    nudged = _screen(200)
    nudged[80:83, 92:268] = 255               # a thin new line above the field
    element = _dom()["elements"][0]
    lib._guard_tolerance = 0.95
    assert lib._region_changed(element, nudged) is None
    lib._guard_tolerance = 0.2
    assert "surrounds it changed" in lib._region_changed(element, nudged)
    # a handful of pixels is noise at any tolerance
    speck = _screen(200)
    speck[80:83, 92:100] = 255
    lib._guard_tolerance = 0.0
    assert lib._region_changed(element, speck) is None


def test_the_keyword_returns_the_previous_setting_and_reads_robot_text():
    lib = _Lib(_screen(200))
    assert lib.set_region_guard("True") is False
    assert lib.set_region_guard("False") is True
    assert lib._region_guard is False


def test_refresh_screen_and_none_do_not_consult_the_guard():
    lib = _Lib(_screen(200))
    lib.set_region_guard(True)
    lib._region_changed = None                # would raise if it were called
    lib.screen = _screen(120)
    lib.get_element_value("hint=Email", refresh="screen")
    assert lib.full_scans == 1
    lib.get_element_text("hint=Email", default="", refresh="none")
    assert lib.full_scans == 1


def test_connect_turns_the_guard_on_from_the_recap_section(monkeypatch):
    import visual_dom.context as context
    monkeypatch.setattr(context, "Session", lambda cfg: object())
    lib = CaptureKeywords()
    lib.connect({"recap": {"region_guard": True, "guard_margin_px": 40,
                           "guard_tolerance": 0.2}})
    assert (lib._region_guard, lib._guard_margin, lib._guard_tolerance) == (True, 40, 0.2)
    # a config that leaves it out does not switch off what the import enabled
    lib.connect({})
    assert lib._region_guard is True
