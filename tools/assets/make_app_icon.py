"""
Write the VizDOM icon files from the single source of truth in
`visual_dom_viewer.ui.branding`.

The application itself does not need these files - it draws the icon at runtime.
They exist for the things that cannot call Python: Windows shortcuts and
`.exe` packaging (`vizdom.ico`), the docs site favicon, and slides/reports.

    python tools/assets/make_app_icon.py            # write all outputs
    python tools/assets/make_app_icon.py --preview  # also write a size sheet

Outputs (relative to the repository root):
    tools/visual_dom_viewer/resources/vizdom.ico      all sizes, one container
    tools/visual_dom_viewer/resources/vizdom-256.png  press/slides
    docs/img/favicon.png                              docs site (32 px)
"""

import argparse
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # runs headless in CI

from PyQt5.QtCore import QBuffer, QByteArray, Qt          # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPixmap          # noqa: E402
from PyQt5.QtWidgets import QApplication                   # noqa: E402

from visual_dom_viewer.ui.branding import ICON_SIZES, render_icon  # noqa: E402


def png_bytes(pixmap: QPixmap) -> bytes:
    buffer = QBuffer(QByteArray())
    buffer.open(QBuffer.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path, sizes=ICON_SIZES) -> None:
    """
    Pack PNG-compressed entries into an ICO container.

    Written by hand rather than via Pillow so the only dependency is PyQt5,
    which the Viewer already requires - a contributor can regenerate the icon
    without installing anything extra. PNG-in-ICO is read by Windows Vista and
    later, and by Qt's own ICO handler (verified in the round-trip check below).
    """
    blobs = [png_bytes(render_icon(size)) for size in sizes]

    header = struct.pack("<HHH", 0, 1, len(blobs))           # reserved, type=icon, count
    offset = len(header) + 16 * len(blobs)
    directory, payload = b"", b""
    for size, blob in zip(sizes, blobs):
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,   # 0 means 256 in the ICO format
            0 if size >= 256 else size,
            0,          # palette entries (0 = truecolour)
            0,          # reserved
            1,          # colour planes
            32,         # bits per pixel
            len(blob),
            offset,
        )
        payload += blob
        offset += len(blob)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + payload)


def write_preview(path: Path) -> None:
    """A size sheet: every rendered size in a row, on a neutral strip."""
    gap = 16
    width = sum(ICON_SIZES) + gap * (len(ICON_SIZES) + 1)
    height = max(ICON_SIZES) + 2 * gap
    sheet = QPixmap(width, height)
    sheet.fill(QColor("#F4F5F7"))

    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.Antialiasing, True)
    x = gap
    for size in ICON_SIZES:
        y = gap + (max(ICON_SIZES) - size)          # sit them on a shared baseline
        painter.drawPixmap(x, y, render_icon(size))
        painter.setPen(QColor("#5A6472"))
        painter.drawText(x, height - gap // 2, f"{size}")
        x += size + gap
    painter.end()

    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(path), "PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true",
                        help="also write a size sheet next to the outputs")
    args = parser.parse_args()

    app = QApplication(sys.argv)                      # QPixmap needs one
    resources = ROOT / "tools" / "visual_dom_viewer" / "resources"

    ico = resources / "vizdom.ico"
    write_ico(ico)
    print(f"wrote {ico.relative_to(ROOT)} ({ico.stat().st_size:,} bytes, "
          f"{len(ICON_SIZES)} sizes)")

    big = resources / "vizdom-256.png"
    render_icon(256).save(str(big), "PNG")
    print(f"wrote {big.relative_to(ROOT)}")

    favicon = ROOT / "docs" / "img" / "favicon.png"
    favicon.parent.mkdir(parents=True, exist_ok=True)
    render_icon(32).save(str(favicon), "PNG")
    print(f"wrote {favicon.relative_to(ROOT)}")

    if args.preview:
        sheet = resources / "vizdom-sizes.png"
        write_preview(sheet)
        print(f"wrote {sheet.relative_to(ROOT)}")

    # Round-trip: an ICO that Qt cannot read is an ICO Explorer may not like.
    from PyQt5.QtGui import QIcon
    sizes = sorted(s.width() for s in QIcon(str(ico)).availableSizes())
    print(f"readable sizes in {ico.name}: {sizes}")
    assert sizes == sorted(ICON_SIZES), f"ICO round-trip lost sizes: {sizes}"
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
