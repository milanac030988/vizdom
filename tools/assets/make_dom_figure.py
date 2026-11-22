"""
Draw the "screen -> Visual DOM -> test" figure from a real analysis session:
the application as captured, an excerpt of the dom_result.json VizDOM wrote for
it, and the Robot Framework steps that address those elements.

Everything shown comes from the session (bounds, ids, text, labels, element
count); the script only chooses which elements to show. Each Robot locator is
resolved against the DOM by the library's own ElementFinder and must match
exactly the element it is drawn next to, or the script stops.

    python tools/assets/make_dom_figure.py

Inputs:   tools/assets/figure_inputs/calculator/{screenshot.png, dom_result.json}
          (a copy of a VizDOM Studio session of the Windows Calculator)
Outputs:  docs/img/calculator_to_dom.svg   docs site (text stays text)
          docs/img/calculator_to_dom.png   README (GitHub and PyPI show PNG)
"""

import base64
import json
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # never opens a window
if sys.platform == "win32":      # headless Qt only finds the fonts it is pointed at
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from visual_gui_library.locators.locator import ElementFinder, LocatorParser  # noqa: E402

INPUTS = ROOT / "tools" / "assets" / "figure_inputs" / "calculator"
OUT_SVG = ROOT / "docs" / "img" / "calculator_to_dom.svg"
OUT_PNG = ROOT / "docs" / "img" / "calculator_to_dom.png"

# the elements the figure follows, each with its colour
SHOWN = {"E34": "#F6B73C", "E36": "#4FD1C5", "E54": "#B794F4"}
# the test: (locator, the element it must resolve to)
STEPS = [
    ("text=7", "E36"),
    ('desc="divide button"', "E34"),
    ("text=7", "E36"),
    ('text="="', "E54"),
]

W, H = 1320, 588
BG, PANEL, BORDER = "#15171c", "#1e2128", "#2c313a"
INK, MUTED, FAINT = "#e8eaee", "#9aa1ad", "#5d6470"
KEY, STR, NUM = "#9ecbff", "#f2c97d", "#b5e3a1"
SANS = "Segoe UI, Helvetica Neue, Arial, sans-serif"
MONO = "Consolas, Menlo, DejaVu Sans Mono, monospace"


def load():
    result = json.loads((INPUTS / "dom_result.json").read_text(encoding="utf-8"))
    dom = result["dom"]
    # the file's top level has the size as an object; the dom's own copy is a list
    dom["image_size"] = dict(result["image_size"])
    png = (INPUTS / "screenshot.png").read_bytes()
    return dom, png


def check_steps(dom):
    finder = ElementFinder(dom)
    for locator, expected in STEPS:
        found = [e["id"] for e in finder.find(LocatorParser.parse(locator))]
        if found != [expected]:
            sys.exit(f"{locator} resolves to {found}, the figure says {expected}")


def t(x, y, s, *, size=14, fill=INK, family=SANS, weight="normal", anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
            f'xml:space="preserve">{s}</text>')


def spans(parts):
    """(text, colour) pieces -> tspans on one line"""
    return "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' for s, c in parts)


def heading(x, y, n, title, sub):
    return (f'<circle cx="{x + 11}" cy="{y - 5}" r="11" fill="{INK}"/>'
            + t(x + 11, y, str(n), size=13, fill=BG, weight="bold", anchor="middle")
            + t(x + 30, y, escape(title), size=16, weight="bold")
            + t(x + 30, y + 20, escape(sub), size=12.5, fill=MUTED))


def arrow(x1, x2, y, label):
    return (f'<line x1="{x1}" y1="{y}" x2="{x2 - 9}" y2="{y}" stroke="{MUTED}" stroke-width="2"/>'
            f'<polygon points="{x2},{y} {x2 - 11},{y - 6} {x2 - 11},{y + 6}" fill="{MUTED}"/>'
            + t((x1 + x2) / 2, y - 10, label, size=12, fill=MUTED, anchor="middle"))


def badge(x, y, text, colour, small=False):
    size, h = (10, 13) if small else (12, 17)
    w = 6 + 0.62 * size * len(text)
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="3" fill="{colour}"/>'
            + t(f"{x + w / 2:.1f}", f"{y + h - 3.5:.1f}", text, size=size, fill=BG, family=MONO,
                weight="bold", anchor="middle"))


def screen_panel(dom, png, x0, y0, scale):
    iw, ih = dom["image_size"]["width"], dom["image_size"]["height"]
    w, h = iw * scale, ih * scale
    out = [heading(x0, y0, 1, "The application", "pixels only: a capture of its window"),
           f'<rect x="{x0 - 1}" y="{y0 + 37}" width="{w + 2:.0f}" height="{h + 2:.0f}" '
           f'fill="none" stroke="{BORDER}"/>',
           f'<image x="{x0}" y="{y0 + 38}" width="{w:.0f}" height="{h:.0f}" '
           f'xlink:href="data:image/png;base64,{base64.b64encode(png).decode()}"/>']
    oy = y0 + 38
    for e in dom["elements"]:          # every element VizDOM found, faint
        if e["id"] in SHOWN:
            continue
        x1, y1, x2, y2 = e["bounds"]
        out.append(f'<rect x="{x0 + x1 * scale:.1f}" y="{oy + y1 * scale:.1f}" '
                   f'width="{(x2 - x1) * scale:.1f}" height="{(y2 - y1) * scale:.1f}" '
                   f'fill="none" stroke="#ffffff" stroke-opacity="0.28" stroke-width="1"/>')
    for e in dom["elements"]:          # the ones the figure follows
        if e["id"] not in SHOWN:
            continue
        c = SHOWN[e["id"]]
        x1, y1, x2, y2 = e["bounds"]
        out.append(f'<rect x="{x0 + x1 * scale:.1f}" y="{oy + y1 * scale:.1f}" '
                   f'width="{(x2 - x1) * scale:.1f}" height="{(y2 - y1) * scale:.1f}" '
                   f'fill="none" stroke="{c}" stroke-width="3" rx="2"/>')
        # small, in the box's top-left corner: clear of the centred glyph and of
        # the neighbouring keys
        out.append(badge(x0 + x1 * scale + 2.5, oy + y1 * scale + 2.5, e["id"], c, small=True))
    return "".join(out), oy + h


def j(v):
    return json.dumps(v, ensure_ascii=False)


def dom_panel(dom, x0, y0, width, bottom):
    out = [heading(x0, y0, 2, "The Visual DOM", "dom_result.json, the part for these keys")]
    top = y0 + 38
    out.append(f'<rect x="{x0}" y="{top}" width="{width}" height="{bottom - top}" rx="6" '
               f'fill="{PANEL}" stroke="{BORDER}"/>')
    lh, x, y = 20.5, x0 + 22, top + 30
    P = lambda s: (s, INK)          # noqa: E731  punctuation
    K = lambda s: (j(s), KEY)       # noqa: E731
    S = lambda s: (j(s), STR)       # noqa: E731
    N = lambda s: (j(s), NUM)       # noqa: E731
    size = dom["image_size"]
    lines = [
        [P("{")],
        [P("  "), K("image_size"), P(": {"), K("width"), P(": "), N(size["width"]),
         P(", "), K("height"), P(": "), N(size["height"]), P("},")],
        [P("  "), K("element_count"), P(": "), N(dom["element_count"]), P(",")],
        [P("  "), K("elements"), P(": [")],
    ]
    blocks = []
    for e in dom["elements"]:
        if e["id"] not in SHOWN:
            continue
        start = len(lines)
        lines += [
            [P("    {"), K("id"), P(": "), S(e["id"]), P(", "), K("role"), P(": "), S(e["role"]), P(",")],
            [P("     "), K("text"), P(": "), S(e["text"]), P(", "), K("label"), P(": "), S(e["label"]), P(",")],
            [P("     "), K("bounds"), P(": "), N(e["bounds"]), P(",")],
            [P("     "), K("clickable"), P(": "), N(e["clickable"]), P("},")],
        ]
        blocks.append((start, len(lines), SHOWN[e["id"]]))
    rest = dom["element_count"] - len(SHOWN)
    lines += [[("    … " + str(rest) + " more elements", MUTED)], [P("  ],")],
              [P("  "), K("hierarchy"), P(": { … }")], [P("}")]]
    for a, b, c in blocks:
        out.append(f'<rect x="{x0 + 8}" y="{y + a * lh - 15}" width="4" '
                   f'height="{(b - a) * lh - 5}" rx="2" fill="{c}"/>')
    for i, parts in enumerate(lines):
        out.append(t(x, y + i * lh, spans(parts), size=14, family=MONO))
    return "".join(out)


def test_panel(dom, x0, y0, width, bottom):
    by_id = {e["id"]: e for e in dom["elements"]}
    out = [heading(x0, y0, 3, "The test", "Robot Framework, VisualGuiLibrary")]
    top = y0 + 38
    out.append(f'<rect x="{x0}" y="{top}" width="{width}" height="{bottom - top}" rx="6" '
               f'fill="{PANEL}" stroke="{BORDER}"/>')
    lh, x, y = 21, x0 + 22, top + 30
    out.append(t(x, y, spans([("*** Test Cases ***", KEY)]), size=13.5, family=MONO))
    out.append(t(x, y + lh, spans([("Divide", INK)]), size=13.5, family=MONO, weight="bold"))
    for i, (locator, eid) in enumerate(STEPS):
        yy = y + (i + 2) * lh
        out.append(f'<rect x="{x0 + 8}" y="{yy - 14}" width="4" height="17" rx="2" '
                   f'fill="{SHOWN[eid]}"/>')
        out.append(t(x, yy, spans([("    Click Visual    ", INK), (locator, STR)]),
                     size=13.5, family=MONO))
    # how each locator resolved
    y = y + (len(STEPS) + 3.4) * lh
    out.append(t(x, y, "Each locator matches exactly one element:", size=13, fill=MUTED))
    seen = []
    for locator, eid in STEPS:
        if (locator, eid) in seen:
            continue
        seen.append((locator, eid))
        y += 44
        e = by_id[eid]
        how = ("its text" if locator.startswith("text=")
               else f'its label "{e["label"]}"')
        out.append(badge(x, y - 13, eid, SHOWN[eid]))
        out.append(t(x + 46, y, spans([(locator, STR)]), size=13, family=MONO))
        out.append(t(x + 46, y + 18, escape(f"found by {how}"), size=12, fill=MUTED))
    y += 56
    for line in ("Operator keys have no readable label:",
                 "VizDOM reads the glyph ÷ and names it",
                 "Divide, so a test can describe it."):
        out.append(t(x, y, escape(line), size=12.5, fill=MUTED))
        y += 18
    return "".join(out)


def build():
    dom, png = load()
    check_steps(dom)
    margin, top = 28, 34
    scale = 0.8
    screen, bottom = screen_panel(dom, png, margin, top, scale)
    sx2 = margin + dom["image_size"]["width"] * scale
    dx, dw = sx2 + 72, 410
    tx, tw = dx + dw + 72, W - margin - (dx + dw + 72)
    mid = top + 38 + (bottom - top - 38) / 2
    body = (screen
            + arrow(sx2 + 12, dx - 12, mid, "analyze")
            + dom_panel(dom, dx, top, dw, bottom)
            + arrow(dx + dw + 12, tx - 12, mid, "resolve")
            + test_panel(dom, tx, top, tw, bottom))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'version="1.1" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<title>The Windows Calculator, the Visual DOM VizDOM builds from its pixels, '
            f'and the Robot Framework steps that click its keys</title>'
            f'<rect width="{W}" height="{H}" rx="10" fill="{BG}"/>{body}</svg>\n')


def render_png(svg: str, path: Path, zoom: float = 2.0):
    from PyQt5.QtCore import QByteArray, QRectF
    from PyQt5.QtGui import QColor, QImage, QPainter
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841  fonts need it
    # Qt takes a font-family list as one family name: name the Windows fonts
    svg = svg.replace(f'font-family="{SANS}"', 'font-family="Segoe UI"').replace(
        f'font-family="{MONO}"', 'font-family="Consolas"')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        sys.exit("Qt could not parse the SVG")
    image = QImage(int(W * zoom), int(H * zoom), QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, W * zoom, H * zoom))
    painter.end()
    if not image.save(str(path), "PNG"):
        sys.exit(f"could not write {path}")


def main():
    svg = build()
    with open(OUT_SVG, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    render_png(svg, OUT_PNG)
    for p in (OUT_SVG, OUT_PNG):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
