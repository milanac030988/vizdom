"""Generate the interactive system overview of the docs site.

    python tools/docs_overview/build_overview.py

Writes (never edit these by hand):
    docs/overview/system.svg              the overview, every component clickable
    docs/overview/components/<id>.svg     one diagram per component: who calls it, what it calls
    docs/system-overview.md               one section per component, anchors #c-<id>
    docs/index.md                         only the block between the overview markers

Contracts with docs/js/vz-overview.js (zoom, full window, fit, routing):
    * a figure is <div class="vz-fig"><div class="vz-scroll"><object ...></object></div></div>;
      <object> (not <img>) keeps the links inside the SVG working, and the
      aspect-ratio style lets the script compute a size before the SVG loads;
    * links inside an SVG are relative to the SVG file and carry target="_top".
"""

import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overview_model as M  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUT = DOCS / "overview"
PAGE = "system-overview"  # docs/system-overview.md, served at /system-overview/

PALETTE = {  # fill, stroke, title colour, dashed outline
    "entry": ("#ffffff", "#2a9d8f", "#16645b", False),
    "config": ("#eaf2fc", "#4a78c2", "#244a86", False),
    "engine": ("#ffffff", "#5b6f8a", "#1f2d3d", False),
    "service": ("#fff4e3", "#c98a2b", "#7a4d0c", False),
    "optional": ("#f5f0ff", "#8a6bbf", "#4b2f80", True),
    "aut": ("#2d3748", "#2d3748", "#ffffff", False),
}
BAND_STYLE = {
    "work": ("#eef7f6", "#9fd3cc", False),
    "engine": ("#f3f6fa", "#c6d3e3", False),
    "services": ("#fffaf2", "#e3bf86", True),
    "aut": ("#f4f4f5", "#d4d4d8", False),
}
LINE = {"call": ("#4a5568", ""), "remote": ("#b7791f", "7 5"), "config": ("#4a78c2", "2 4")}
FONT = "Segoe UI, system-ui, -apple-system, Helvetica, Arial, sans-serif"
MONO = "Consolas, Menlo, monospace"
BY_ID = {c["id"]: c for c in M.COMPONENTS}


# --------------------------------------------------------------------------- svg
def defs() -> str:
    marks = "".join(
        f'<marker id="ah-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
        for k, (c, _) in LINE.items())
    style = (
        f"<style>text{{font-family:{FONT}}} .mono{{font-family:{MONO}}}"
        " a.node{cursor:pointer} a.node:hover rect.box{stroke-width:3;filter:url(#lift)}"
        " a.node:focus rect.box{stroke-width:3} .lbl{paint-order:stroke;stroke:#fff;stroke-width:4px;"
        "stroke-linejoin:round}</style>")
    lift = ('<filter id="lift" x="-10%" y="-10%" width="120%" height="140%">'
            '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity=".25"/></filter>')
    return f"<defs>{marks}{lift}</defs>{style}"


def box_svg(c: dict, box, href: str, big: bool = False) -> str:
    x, y, w, h = box
    fill, stroke, title_col, dashed = PALETTE[c["kind"]]
    sub_col = "#d1d5db" if c["kind"] == "aut" else "#5a6878"
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    t_size, s_size = (17, 12.5) if big else (15, 11.5)
    one_line = h < 60
    if one_line:  # wide, flat boxes: title and subtitle on one line
        inner = (f'<text x="{x + 18}" y="{y + h / 2 + 5}" font-size="{t_size}" font-weight="700" fill="{title_col}">'
                 f'{escape(c["title"])}<tspan dx="14" font-size="{s_size}" font-weight="400" '
                 f'fill="{sub_col}">{escape(c["sub"])}</tspan></text>')
    else:
        cx = x + w / 2
        inner = (f'<text x="{cx}" y="{y + h / 2 - 4}" font-size="{t_size}" font-weight="700" fill="{title_col}" '
                 f'text-anchor="middle">{escape(c["title"])}</text>'
                 f'<text x="{cx}" y="{y + h / 2 + 15}" font-size="{s_size}" fill="{sub_col}" '
                 f'text-anchor="middle">{escape(c["sub"])}</text>')
    title = f'<title>{escape(c["title"])}: {escape(c["summary"])}</title>'
    return (f'<a href="{href}" target="_top" class="node">{title}'
            f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.6"{dash}/>{inner}</a>')


def anchors(a, b):
    """Start and end of a straight arrow between two boxes, edge to edge."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    lo, hi = max(ax, bx), min(ax + aw, bx + bw)
    if hi - lo > 10:  # stacked: vertical line through the overlap
        x = (lo + hi) / 2
        return ((x, ay + ah), (x, by)) if ay < by else ((x, ay), (x, by + bh))
    lo, hi = max(ay, by), min(ay + ah, by + bh)
    if hi - lo > 10:  # side by side: horizontal line
        y = (lo + hi) / 2
        return ((ax + aw, y), (bx, y)) if ax < bx else ((ax, y), (bx + bw, y))
    return ((ax + aw / 2, ay + ah), (bx + bw / 2, by))


def arrow(points, style: str, label: str = "", label_at=None) -> str:
    colour, dash = LINE[style]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    out = (f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="1.8"{dash_attr} '
           f'marker-end="url(#ah-{style})"/>')
    if label:
        if label_at is None:  # middle of the longest segment
            segs = list(zip(points, points[1:]))
            (x1, y1), (x2, y2) = max(segs, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
            vertical = abs(x1 - x2) < 1
            label_at = ((x1 + x2) / 2 + (8 if vertical else 0), (y1 + y2) / 2 + (4 if vertical else -7))
            anchor = "start" if vertical else "middle"
        else:
            anchor = "middle"
        lx, ly = label_at
        out += (f'<text class="lbl" x="{lx:.1f}" y="{ly:.1f}" font-size="11.5" fill="{colour}" '
                f'text-anchor="{anchor}">{escape(label)}</text>')
    return out


def overview_svg() -> str:
    W, H = M.WIDTH, M.HEIGHT
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="VizDOM system overview">', defs(),
             f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']
    for title, y, h, key, tx in M.BANDS:
        fill, stroke, dashed = BAND_STYLE[key]
        dash = ' stroke-dasharray="8 5"' if dashed else ""
        parts.append(f'<rect x="20" y="{y}" width="{W - 40}" height="{h}" rx="12" fill="{fill}" '
                     f'stroke="{stroke}" stroke-width="1.4"{dash}/>'
                     f'<text x="{tx}" y="{y + 22}" font-size="12.5" font-weight="700" fill="#4a5568" '
                     f'letter-spacing=".06em">{escape(title.upper())}</text>')
    # arrows first, boxes on top
    for src, x, label in M.ENTRY_ARROWS:
        bx, by, bw, bh = BY_ID[src]["box"]
        parts.append(arrow([(x, by + bh), (x, 188)], "call", label))  # label beside the line
    for src, dst, label, style, shown in M.INTERACTIONS:
        if not shown:
            continue
        pts = M.ROUTES.get((src, dst)) or list(anchors(BY_ID[src]["box"], BY_ID[dst]["box"]))
        parts.append(arrow(pts, style, label))
    for c in M.COMPONENTS:
        parts.append(box_svg(c, c["box"], f"../{PAGE}/#c-{c['id']}"))
    parts.append(f'<text x="{W - 30}" y="{H - 8}" font-size="11" fill="#718096" text-anchor="end">'
                 'Click a box for details  ·  solid: always  ·  dashed: optional, over the network</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def small_box(c: dict, box, href: str) -> str:
    """A neighbour in a component diagram: the title only, so it always fits."""
    x, y, w, h = box
    fill, stroke, title_col, dashed = PALETTE[c["kind"]]
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (f'<a href="{href}" target="_top" class="node"><title>{escape(c["title"])}: '
            f'{escape(c["summary"])}</title><rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" '
            f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 5}" font-size="14.5" font-weight="700" '
            f'fill="{title_col}" text-anchor="middle">{escape(c["title"])}</text></a>')


def component_svg(c: dict) -> str:
    ins = [(s, lbl, st) for s, d, lbl, st, _ in M.INTERACTIONS if d == c["id"]]
    outs = [(d, lbl, st) for s, d, lbl, st, _ in M.INTERACTIONS if s == c["id"]]
    W, bw, bh, gap = 1320, 230, 46, 26
    rows = max(len(ins), len(outs), 1)
    H = max(rows * (bh + gap) + gap + 34, 190)
    cw = max(270, int(len(c["sub"]) * 7) + 40)  # wide enough for the subtitle
    ch = max(96, rows * 30)
    cx, cy = (W - cw) / 2, (H - 34 - ch) / 2 + 10
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="{escape(c["title"])}: what it works with">', defs(),
             f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']

    def column(items, x, incoming):
        n = len(items)
        top = (H - 34 - (n * bh + (n - 1) * gap)) / 2 + 10
        for i, (other, label, style) in enumerate(items):
            y = top + i * (bh + gap)
            # right-angled arrows through a vertical spine beside the centre box; the
            # label sits on the neighbour's own horizontal segment, so none can cross
            ey = cy + ch * (i + 1) / (n + 1)
            yc = y + bh / 2
            if incoming:
                spine = cx - 44
                pts = [(x + bw, yc), (spine, yc), (spine, ey), (cx, ey)]
                lx, anchor = x + bw + 12, "start"
            else:
                spine = cx + cw + 44
                pts = [(cx + cw, ey), (spine, ey), (spine, yc), (x, yc)]
                lx, anchor = x - 14, "end"
            ly = yc - 7
            colour = LINE[style][0]
            parts.append(arrow(pts, style))
            parts.append(f'<text class="lbl" x="{lx:.1f}" y="{ly:.1f}" font-size="12" fill="{colour}" '
                         f'text-anchor="{anchor}">{escape(label)}</text>')
            parts.append(small_box(BY_ID[other], (x, y, bw, bh), f"../../{PAGE}/#c-{other}"))

    column(ins, 20, True)
    column(outs, W - 20 - bw, False)
    parts.append(box_svg(c, (cx, cy, cw, ch), f"../../{PAGE}/#c-{c['id']}", big=True))
    if not ins and c["kind"] == "entry":
        parts.append(f'<text x="{20 + bw / 2}" y="{cy + ch / 2}" font-size="12" fill="#a0aec0" '
                     'text-anchor="middle">you start here</text>')
    parts.append(f'<text x="{W - 10}" y="{H - 8}" font-size="11" fill="#718096" text-anchor="end">'
                 'left: uses it  ·  right: what it uses  ·  click a box to go there</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------- markdown
def figure(src: str, label: str, w: int, h: int) -> str:
    return (f'<div class="vz-fig"><div class="vz-scroll"><object type="image/svg+xml" data="{src}" '
            f'aria-label="{escape(label)}" style="aspect-ratio:{w}/{h}"></object></div></div>')


def svg_size(svg: str):
    vb = svg.split('viewBox="', 1)[1].split('"', 1)[0].split()
    return int(float(vb[2])), int(float(vb[3]))


def page_md(sizes: dict) -> str:
    groups = {"work": ["rf", "studio", "python"],
              "engine": ["config", "capture", "pipeline", "dom", "locator", "plugins", "actuator"],
              "services": ["capsvc", "detsvc", "ollama", "actsvc"],
              "aut": ["aut"]}
    heads = {"work": "Where you work", "engine": "The VizDOM engine",
             "services": "Optional services", "aut": "The application under test"}
    w, h = sizes["system"]
    out = [
        "<!-- Generated by tools/docs_overview/build_overview.py from overview_model.py. Do not edit. -->",
        "",
        "# System overview",
        "",
        "Every box is clickable: it opens that part's section below, with a smaller diagram "
        "of what it works with. Use **Full window** to explore the diagrams at full size; "
        "**Esc** closes it.",
        "",
        figure("../overview/system.svg", "VizDOM system overview", w, h),
        "",
        "On one machine everything in the engine runs **inside your test process**; nothing "
        "has to be started. The services in the dashed band are the same parts, moved to "
        "another machine when you want one GPU host to serve many test runners, or when the "
        "application runs somewhere else.",
        "",
    ]
    for key in ["work", "engine", "services", "aut"]:
        out += [f"## {heads[key]}", ""]
        for cid in groups[key]:
            c = BY_ID[cid]
            cw, ch = sizes[cid]
            out += [f"### {c['title']} {{ #c-{cid} }}", "",
                    f"*{c['summary']}*", "",
                    figure(f"../overview/components/{cid}.svg", f"{c['title']}: what it works with", cw, ch), "",
                    c["body"].strip(), ""]
            if c["docs"]:
                links = " · ".join(f"[{t}]({u})" for t, u in c["docs"])
                out += [f"**More:** {links}", ""]
    return "\n".join(out)


def home_block(sizes: dict) -> str:
    w, h = sizes["system"]
    return "\n".join([
        "<!-- overview:begin (generated by tools/docs_overview/build_overview.py) -->",
        figure("overview/system.svg", "VizDOM system overview", w, h),
        "<!-- overview:end -->",
    ])


def main() -> int:
    (OUT / "components").mkdir(parents=True, exist_ok=True)
    sizes = {}
    svg = overview_svg()
    (OUT / "system.svg").write_text(svg, encoding="utf-8")
    sizes["system"] = svg_size(svg)
    for c in M.COMPONENTS:
        s = component_svg(c)
        (OUT / "components" / f"{c['id']}.svg").write_text(s, encoding="utf-8")
        sizes[c["id"]] = svg_size(s)
    (DOCS / f"{PAGE}.md").write_text(page_md(sizes), encoding="utf-8")

    index = DOCS / "index.md"
    text = index.read_text(encoding="utf-8")
    begin, end = "<!-- overview:begin", "<!-- overview:end -->"
    if begin in text and end in text:
        head, rest = text.split(begin, 1)
        tail = rest.split(end, 1)[1]
        index.write_text(head + home_block(sizes) + tail, encoding="utf-8")
        print("docs/index.md: overview block updated")
    else:
        print("docs/index.md: no overview markers, left unchanged")
    print(f"wrote docs/overview/system.svg, {len(M.COMPONENTS)} component diagrams, docs/{PAGE}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
