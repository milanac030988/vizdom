"""Trying a locator from the Viewer through the actuator (ADR-028)."""

import pytest

from visual_dom_viewer.core.actuation import (
    ActuationError,
    ActuationSettings,
    LocatorTrial,
    to_normalized,
)

DOM = {
    "image_size": [400, 200],
    "elements": [
        {"id": "E1", "text": "Save", "role": "button", "bounds": [100, 50, 140, 70],
         "center": [120, 60]},
        {"id": "E2", "text": "Open", "role": "button", "bounds": [200, 50, 240, 70],
         "center": [220, 60]},
        {"id": "E3", "text": "Open", "role": "button", "bounds": [300, 50, 340, 70],
         "center": [320, 60]},
    ],
}
SCREEN = {"capture_scope": "screen"}
WINDOW = {"capture_scope": "window", "capture_origin": [1000, 500],
          "device_origin": [0, 0], "device_size": [2000, 1000]}


class FakeActuator:
    name = "fake"

    def __init__(self, can_focus=True):
        self.can_focus = can_focus
        self.events = []

    def focus_target(self, title=None):
        self.events.append(("focus", title))
        return self.can_focus

    def tap(self, nx, ny, image_size=None, click_type="single"):
        self.events.append(("tap", round(nx, 4), round(ny, 4), click_type))


def test_click_lands_on_the_resolved_element():
    act = FakeActuator()
    out = LocatorTrial(act).run("text=Save || id=E9", DOM, SCREEN, (400, 200), "App")
    assert out.clicked and out.element_id == "E1"
    assert act.events == [("focus", "App"), ("tap", 0.3, 0.3, "single")]


def test_focus_happens_before_the_click():
    act = FakeActuator()
    LocatorTrial(act).run("text=Save", DOM, SCREEN, (400, 200), "App")
    assert [e[0] for e in act.events] == ["focus", "tap"]


def test_window_capture_maps_through_its_geometry():
    act = FakeActuator()
    out = LocatorTrial(act).run("text=Save", DOM, WINDOW, (400, 200), "App")
    # (1000 + 120) / 2000, (500 + 60) / 1000
    assert out.normalized == pytest.approx((0.56, 0.56))


def test_broken_locator_fails_without_clicking():
    act = FakeActuator()
    out = LocatorTrial(act).run("text=Open", DOM, SCREEN, (400, 200), "App")
    assert not out.clicked
    assert "exactly one element" in out.resolution.error_message()
    assert act.events == []


def test_fallback_use_is_reported():
    out = LocatorTrial(FakeActuator()).run("text=Gone || text=Save", DOM, SCREEN,
                                           (400, 200), "App")
    assert out.clicked and out.notes and "fallback #2" in out.notes[0]


def test_no_window_means_no_click():
    act = FakeActuator()
    with pytest.raises(ActuationError, match="No target window"):
        LocatorTrial(act).run("text=Save", DOM, SCREEN, (400, 200), None)
    assert act.events == []


def test_unraisable_window_means_no_click():
    act = FakeActuator(can_focus=False)
    with pytest.raises(ActuationError, match="Could not bring"):
        LocatorTrial(act).run("text=Save", DOM, SCREEN, (400, 200), "App")
    assert ("tap",) not in [e[:1] for e in act.events]


def test_capture_side_can_focus_when_the_actuator_cannot():
    act = FakeActuator(can_focus=False)
    out = LocatorTrial(act, capture_focus=lambda title: True).run(
        "text=Save", DOM, SCREEN, (400, 200), "App")
    assert out.clicked and out.focused_via == "capture"


def test_capture_without_geometry_is_refused():
    with pytest.raises(ActuationError, match="no known position"):
        to_normalized(10, 10, {"capture_source": "file:x.png"}, (400, 200))


def test_no_dom_is_refused():
    with pytest.raises(ActuationError, match="No analyzed DOM"):
        LocatorTrial(FakeActuator()).run("text=Save", None, SCREEN, (400, 200), "App")


def test_settings_from_config():
    s = ActuationSettings.from_config(
        {"actuator": {"strategy": "grpc", "target": "host:50054", "window_title": None}})
    assert (s.strategy, s.target, s.window_title) == ("grpc", "host:50054", None)
