"""
The VizDOM application icon, drawn in code.

The mark is the product in one glyph: a **locator reticle** (four corner
brackets — find the element) around a **DOM tree** (three connected nodes — the
structure that comes out). Screenshot in, structure out.

Drawn with QPainter rather than shipped as a bitmap, for the same reason the
toolbar uses `QStyle.standardIcon`: no binary assets to keep in sync, and every
size is rendered at its own scale instead of being resampled from one master.
That matters below 48 px, where the tree collapses into a single node — three
1-pixel dots joined by 1-pixel lines are mud, and an icon that is mud at 16 px is
the icon a user actually sees in the taskbar.

`tools/assets/make_app_icon.py` uses the same code to write `vizdom.ico` for
Windows shortcuts and the docs favicon.
"""

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap,
)

# The sizes Windows, Qt and the docs site actually ask for.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Palette. Navy reads as "tooling" and keeps the accent legible; the teal is the
# one saturated colour, so it is what the eye lands on at any size.
TILE_TOP = QColor("#22334F")
TILE_BOTTOM = QColor("#0E1626")
RETICLE = QColor("#F2F6FC")
ACCENT = QColor("#4FD1C5")
EDGE = QColor(255, 255, 255, 30)


# At and below this size the mark is drawn on whole pixels with antialiasing
# off. Anti-aliased 1.2-pixel strokes turn the corner brackets into a grey haze
# that reads as a plain square frame - the opposite of a reticle.
CRISP_MAX = 32

# Below this size the tree's connector legs are shorter than a node is wide, so
# the three dots merge into a blob; one node is the honest simplification.
TREE_MIN = 48


def render_icon(size: int) -> QPixmap:
    """The icon at one specific pixel size, drawn for that size."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        _draw_tile(painter, size)
        _draw_reticle(painter, size)
        if size >= TREE_MIN:
            _draw_tree(painter, size)
        else:
            _draw_single_node(painter, size)
    finally:
        painter.end()
    return pixmap


def app_icon() -> QIcon:
    """A multi-resolution icon for `QApplication.setWindowIcon`."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(render_icon(size))
    return icon


def set_windows_app_id(app_id: str = "VizDOM.Viewer") -> None:
    """
    Give the process its own taskbar identity on Windows.

    Without an explicit AppUserModelID, Windows attributes the window to the
    host interpreter: the taskbar button shows the Python icon and groups the
    Viewer with every other Python process, no matter what `setWindowIcon` says.
    No-op off Windows, and non-fatal if the call is unavailable.
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# pieces
# ---------------------------------------------------------------------------

def _draw_tile(painter: QPainter, size: int) -> None:
    """Rounded app tile with a vertical gradient and a hairline top edge."""
    painter.setRenderHint(QPainter.Antialiasing, True)
    # A fractional inset would land the tile edge between pixels and fringe the
    # whole silhouette; small icons use the full square.
    inset = 0.0 if size <= CRISP_MAX else size * 0.02
    rect = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = round(size * 0.20) if size <= CRISP_MAX else size * 0.22

    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, TILE_TOP)
    gradient.setColorAt(1.0, TILE_BOTTOM)

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, QBrush(gradient))

    # The lit edge only reads at sizes where it is more than one pixel wide.
    if size >= 32:
        painter.setPen(QPen(EDGE, max(1.0, size * 0.012)))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)


def _draw_reticle(painter: QPainter, size: int) -> None:
    """
    Four corner brackets: the bounding box of a located element.

    The gap between two arms is what makes this a reticle rather than a frame,
    so the arms are kept to a third of the side and the geometry is snapped to
    whole pixels at small sizes - at 16 px, half a pixel of drift closes the gap.
    """
    crisp = size <= CRISP_MAX
    painter.setRenderHint(QPainter.Antialiasing, not crisp)

    if crisp:
        # Optically corrected, not scaled down: the small mark is deliberately
        # larger and chunkier relative to the tile, because a stroke cannot be
        # thinner than one pixel and a gap cannot be narrower than two.
        # The smallest size needs the largest mark; by 32 px the tile's rounded
        # corner needs clearance or the brackets fuse with the tile edge.
        ratio = 0.37 if size <= 16 else (0.33 if size <= 24 else 0.31)
        side = 2 * round(size * ratio)              # even, so it centres exactly
        origin = (size - side) / 2
        arm = max(2, round(side * 0.26))
        width = max(2, round(size * 0.10))
        # A stroke of odd width centred on an integer coordinate straddles the
        # pixel boundary and comes out grey on both sides; shift to the pixel
        # centre so it lands on whole pixels.
        if width % 2:
            origin += 0.5
    else:
        side = size * 0.58
        origin = (size - side) / 2.0
        arm = side * 0.32
        width = size * 0.075

    pen = QPen(RETICLE, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)

    left, top = origin, origin
    right, bottom = origin + side, origin + side
    for x, y, dx, dy in ((left, top, 1, 1), (right, top, -1, 1),
                         (left, bottom, 1, -1), (right, bottom, -1, -1)):
        corner = QPainterPath()
        corner.moveTo(x, y + dy * arm)
        corner.lineTo(x, y)
        corner.lineTo(x + dx * arm, y)
        painter.drawPath(corner)


def _draw_tree(painter: QPainter, size: int) -> None:
    """Root over two children: the DOM the reticle encloses."""
    painter.setRenderHint(QPainter.Antialiasing, True)

    # The drop has to exceed twice the node radius or the connector legs end up
    # underneath the nodes they connect, and the tree reads as a bar with blobs.
    radius = size * 0.05
    centre = size / 2.0
    root = QPointF(centre, centre - size * 0.14)
    spread = size * 0.115
    drop = size * 0.20
    children = (QPointF(centre - spread, root.y() + drop),
                QPointF(centre + spread, root.y() + drop))

    edge = QColor(ACCENT)
    edge.setAlpha(190)
    pen = QPen(edge, max(1.0, size * 0.026))
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    elbow = QPointF(centre, root.y() + drop * 0.50)
    painter.drawLine(root, elbow)
    painter.drawLine(QPointF(children[0].x(), elbow.y()),
                     QPointF(children[1].x(), elbow.y()))
    for child in children:
        painter.drawLine(QPointF(child.x(), elbow.y()), child)

    painter.setPen(Qt.NoPen)
    painter.setBrush(ACCENT)
    for node in (root,) + children:
        painter.drawEllipse(node, radius, radius)


def _draw_single_node(painter: QPainter, size: int) -> None:
    """Below TREE_MIN the tree becomes one node - the only shape that survives."""
    painter.setRenderHint(QPainter.Antialiasing, True)   # a round dot needs it
    painter.setPen(Qt.NoPen)
    painter.setBrush(ACCENT)
    radius = size * 0.125
    painter.drawEllipse(QPointF(size / 2.0, size / 2.0), radius, radius)
