"""
Canvas sizing / fit behaviour for screenshots larger than the panel.

A capture of a large application used to be clipped at the panel edge with no
scrollbars and no indication anything was missing: the canvas was a plain widget
that painted the screenshot at 1:1 into whatever space the splitter gave it.
It now sizes itself to the scaled content inside a QScrollArea, which is what
produces the scrollbars.

These tests exercise the geometry only (no OCR, no models) under the offscreen
Qt platform.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt                                     # noqa: E402
from PyQt5.QtGui import QImage, QPixmap                         # noqa: E402
from PyQt5.QtWidgets import QApplication, QScrollArea           # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(app):
    from visual_dom_viewer.core.model import DOMViewerModel
    from visual_dom_viewer.ui.main_window import ScreenshotCanvas

    DOMViewerModel.get_instance().reset_view()
    return ScreenshotCanvas()


def give_image(canvas, width, height):
    """Put a real pixmap of the given size on the canvas."""
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(0x202020)
    canvas._pixmap = QPixmap.fromImage(image)
    canvas._announce_new_image()


# --------------------------------------------------------------------------
# canvas sizes itself to the content, which is what makes scrolling possible
# --------------------------------------------------------------------------

def test_canvas_takes_the_image_size(canvas):
    give_image(canvas, 2560, 1440)
    assert (canvas.width(), canvas.height()) == (2560, 1440)


def test_canvas_size_follows_the_scale(canvas):
    give_image(canvas, 1000, 500)
    canvas._on_view_changed(type("V", (), {"scale": 0.5, "offset_x": 0, "offset_y": 0})())
    assert (canvas.width(), canvas.height()) == (500, 250)


def test_scrollbars_appear_for_an_oversized_image(app, canvas):
    scroll = QScrollArea()
    scroll.setWidget(canvas)
    scroll.setWidgetResizable(False)
    scroll.resize(800, 600)
    scroll.show()

    give_image(canvas, 2560, 1440)
    app.processEvents()

    assert canvas.width() > scroll.viewport().width()
    assert canvas.height() > scroll.viewport().height()
    assert scroll.horizontalScrollBar().maximum() > 0, "no horizontal scroll range"
    assert scroll.verticalScrollBar().maximum() > 0, "no vertical scroll range"


# --------------------------------------------------------------------------
# fit
# --------------------------------------------------------------------------

def test_fit_scale_shrinks_a_large_image(canvas):
    give_image(canvas, 2000, 1000)
    # limiting dimension is width: 800/2000 = 0.4 vs 600/1000 = 0.6
    assert canvas.fit_scale(800, 600) == pytest.approx(0.4)


def test_fit_scale_never_upscales(canvas):
    """A small dialog stays 1:1 - upscaling would only add blur."""
    give_image(canvas, 300, 200)
    assert canvas.fit_scale(1600, 1200) == 1.0


def test_fit_scale_without_image_is_neutral(canvas):
    assert canvas.fit_scale(800, 600) == 1.0


# --------------------------------------------------------------------------
# zoom bounds and wheel behaviour
# --------------------------------------------------------------------------

def test_zoom_is_clamped(app):
    from visual_dom_viewer.core.model import DOMViewerModel

    model = DOMViewerModel.get_instance()
    model.set_scale(500.0)
    assert model.state.view.scale == model.MAX_SCALE
    model.set_scale(0.0001)
    assert model.state.view.scale == model.MIN_SCALE
    model.reset_view()


def test_plain_wheel_is_left_to_the_scroll_area(canvas):
    """
    A plain wheel must NOT zoom - it has to reach the QScrollArea so the view
    scrolls. Ctrl+wheel zooms.
    """
    from PyQt5.QtCore import QPoint
    from PyQt5.QtGui import QWheelEvent
    from visual_dom_viewer.core.model import DOMViewerModel

    model = DOMViewerModel.get_instance()
    model.reset_view()
    give_image(canvas, 1000, 500)
    before = model.state.view.scale

    def wheel(modifier):
        return QWheelEvent(QPoint(10, 10), QPoint(10, 10), QPoint(0, 0),
                           QPoint(0, 120), 120, Qt.Vertical,
                           Qt.NoButton, modifier)

    plain = wheel(Qt.NoModifier)
    canvas.wheelEvent(plain)
    assert model.state.view.scale == before, "plain wheel zoomed"
    assert not plain.isAccepted(), "plain wheel was swallowed, so it cannot scroll"

    ctrl = wheel(Qt.ControlModifier)
    canvas.wheelEvent(ctrl)
    assert model.state.view.scale > before, "Ctrl+wheel did not zoom"
    model.reset_view()


# --------------------------------------------------------------------------
# a null path must not blank an existing screenshot
# --------------------------------------------------------------------------

def test_unreadable_path_keeps_the_current_image(canvas):
    give_image(canvas, 640, 480)
    assert canvas.load_image("screenshot.png") is False   # nominal, not on disk
    assert canvas.has_image()
    assert (canvas.width(), canvas.height()) == (640, 480)


# --------------------------------------------------------------------------
# hover / click hit-testing must line up with the cursor at any zoom
# --------------------------------------------------------------------------

def test_hover_maps_cursor_to_content_once(app, canvas, monkeypatch):
    """
    The canvas passes RAW widget coordinates to the model, which applies
    screen_to_content exactly once. The old code pre-divided by scale and the
    model divided again - correct at scale 1, wrong everywhere else. Assert the
    model receives the widget coords unchanged (not pre-divided).
    """
    from PyQt5.QtCore import QPoint
    from PyQt5.QtGui import QMouseEvent
    from visual_dom_viewer.core.model import DOMViewerModel

    model = DOMViewerModel.get_instance()
    model.reset_view()
    model.set_explore_mode(True)          # is_explore_mode is a read-only property
    give_image(canvas, 1000, 500)

    seen = []
    monkeypatch.setattr(model, "hover_element_at_point",
                        lambda x, y: seen.append((x, y)) or None)

    for scale in (1.0, 2.0, 0.5):
        model.set_scale(scale)
        seen.clear()
        ev = QMouseEvent(QMouseEvent.MouseMove, QPoint(400, 300),
                         Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        canvas.mouseMoveEvent(ev)
        # RAW widget coords, regardless of zoom - the model does the transform.
        assert seen == [(400, 300)], f"scale {scale}: model saw {seen}"
    model.reset_view()


def test_highlight_and_hittest_agree_at_zoom(app, canvas):
    """
    End-to-end: the box drawn for an element and the region that hover-selects
    it must be the same on screen. Draw position is bbox*scale; hit-test maps
    the cursor back through the same scale - so a cursor inside the drawn box
    must resolve to that element.
    """
    from visual_dom_viewer.core.model import DOMViewerModel

    model = DOMViewerModel.get_instance()
    model.reset_view()
    give_image(canvas, 1000, 500)

    # An element box at content (100,50)-(300,150).
    class Box:
        x, y, width, height = 100, 50, 200, 100

    class Elem:
        id = "E1"
        bbox = Box()

    for scale in (1.0, 2.0, 0.5):
        model.set_scale(scale)
        # Draw position of the box's top-left corner on the widget.
        draw_x = int(Box.x * scale + model.state.view.offset_x)
        draw_y = int(Box.y * scale + model.state.view.offset_y)
        # Map that same widget point back to content the way the model does.
        cx, cy = model.state.view.screen_to_content(draw_x + 5, draw_y + 5)
        assert Box.x <= cx <= Box.x + Box.width, f"scale {scale}: x {cx} outside box"
        assert Box.y <= cy <= Box.y + Box.height, f"scale {scale}: y {cy} outside box"
    model.reset_view()
