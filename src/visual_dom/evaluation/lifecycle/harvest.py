"""
Harvest real-application states for the lifecycle benchmark.

The synthetic set has one weakness a reviewer will name first: the screens are
generated. This module photographs REAL application windows and takes their
ground truth from the Windows UI Automation tree - the accessibility layer
VizDOM exists to do without. The executors still see only the screenshot; the
tree is the answer key, available here because these are ordinary desktop
applications, and absent on the canvases, HMIs and cameras VizDOM targets.

One state = one window at one moment:

    data/realworld/images/<app>__<state>.png
    data/realworld/labels/<app>__<state>.json   (same schema as the synthetic GT)

The label file adds ``all_names`` (every UIA name in the window, kept or not)
so the step generator never picks a "same-app" negative the screen does show,
and per element ``role_word`` / ``uia_type`` / ``review``.

Accessibility trees are noisy, so conversion is conservative and the rest is
left to a human pass over the review sheet:

- only visible, on-screen, named elements inside the captured area are kept;
- an element repeating its ancestor's name (a Button's own Text child, a
  SplitButton's inner Button) is folded into the ancestor, or every button
  label would count twice and fail the uniqueness rule;
- an actionable element that looks icon-only (small, roughly square, a name
  longer than two characters) becomes ``icon``: its UIA name is a tooltip, not
  text on the screen, and a ``text=`` step on it would grade the benchmark;
- Edit / ComboBox become ``block``: their UIA name is usually a label drawn
  BESIDE the field, so a text step would aim at the wrong box.

Workflow (see benchmarks/lifecycle-realworld-v1/README.md):

    python -m visual_dom.evaluation.lifecycle.harvest capture --title "Notepad++" --app notepadpp --state main
    python -m visual_dom.evaluation.lifecycle.harvest review
    python -m visual_dom.evaluation.lifecycle.generate --labels data/realworld/labels \
        --images data/realworld/images --negatives same-app \
        --benchmark lifecycle-realworld-v1 --out benchmarks/lifecycle-realworld-v1/steps.json
    python -m visual_dom.evaluation.lifecycle.harvest review     # again: check the negatives
"""

import html
import json
import re
import time
from pathlib import Path

DEFAULT_ROOT = Path("data/realworld")
DEFAULT_STEPS = Path("benchmarks/lifecycle-realworld-v1/steps.json")

# UIA control type -> (visual_type, role word used in instructions)
_ACTIONABLE = {
    "Button": ("button", "button"),
    "SplitButton": ("button", "button"),
    "Hyperlink": ("button", "link"),
    "MenuItem": ("button", "menu item"),
    "TabItem": ("button", "tab"),
    "ListItem": ("button", "list item"),
    "TreeItem": ("button", "tree item"),
    "CheckBox": ("checkbox", "checkbox"),
    "RadioButton": ("checkbox", "radio button"),
}
_TEXT = ("Text",)
_ICON = ("Image",)

_STATE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _inside(inner, outer, slack=2):
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
            and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack)


def looks_icon_only(name: str, bounds) -> bool:
    """A small, roughly square control whose name is a word, not a glyph: its
    name is a tooltip ("Bold", "Save") the screen does not print."""
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    return len(name) > 2 and h <= 48 and w < 1.6 * h


def uia_to_gt(nodes, client_rect, image_size):
    """
    Convert a flat UIA dump into the benchmark's element GT.

    ``nodes``: dicts with name, control_type, rect (l, t, r, b in screen
    pixels), visible, parent (index into nodes or None), in tree order.
    ``client_rect``: (x, y, w, h) of the captured area in the same space.
    ``image_size``: (width, height) of the screenshot; rects are scaled by
    width / client width, so a DPI mismatch between the two still lines up.
    """
    cx, cy, cw, ch = client_rect
    iw, ih = image_size
    sx, sy = iw / float(cw), ih / float(ch)

    def to_image(r):
        return [int(round((r[0] - cx) * sx)), int(round((r[1] - cy) * sy)),
                int(round((r[2] - cx) * sx)), int(round((r[3] - cy) * sy))]

    all_names = sorted({(n.get("name") or "").strip() for n in nodes} - {""})

    kept = {}          # node index -> element
    elements = []
    for i, n in enumerate(nodes):
        name = (n.get("name") or "").strip()
        ctype = n.get("control_type") or ""
        if not n.get("visible", True):
            continue
        raw = to_image(n["rect"])
        b = [max(0, raw[0]), max(0, raw[1]), min(iw, raw[2]), min(ih, raw[3])]
        if b[2] - b[0] < 4 or b[3] - b[1] < 4:
            continue
        if _area(b) < 0.5 * _area(raw):        # mostly outside the capture
            continue

        # nearest kept ancestor
        p, parent = n.get("parent"), None
        while p is not None:
            if p in kept:
                parent = kept[p]
                break
            p = nodes[p].get("parent")

        # a repeat of an ancestor's name inside it is that ancestor's label
        q, folded = parent, False
        while q is not None and name:
            if q.get("_name", "").lower() == name.lower() and _inside(b, q["bounds"]):
                folded = True
                break
            q = q.get("_parent")
        if folded:
            kept[i] = parent
            continue

        el = {"id": f"E{len(elements) + 1}", "bounds": b, "confidence": 1.0,
              "uia_type": ctype}
        if ctype in _ACTIONABLE and name:
            vt, word = _ACTIONABLE[ctype]
            if looks_icon_only(name, b):
                el.update(visual_type="icon", ocr_text=name, review="icon-only?")
            else:
                el.update(visual_type=vt, ocr_text=name, role_word=word)
        elif ctype in _TEXT and name:
            el.update(visual_type="text", ocr_text=name)
        elif ctype in _ICON:
            el.update(visual_type="icon")
        else:
            # containers, fields and everything else: structure, no caption
            el.update(visual_type="block")
            if not name and ctype not in ("Edit", "ComboBox"):
                kept[i] = parent       # an unnamed wrapper adds nothing
                continue
        if parent is not None:
            el["parent_id"] = parent["id"]
            parent.setdefault("children_ids", []).append(el["id"])
        el["_name"], el["_parent"] = name, parent
        kept[i] = el
        elements.append(el)

    for el in elements:
        el.pop("_name")
        el.pop("_parent")
    return {
        "image_size": {"width": iw, "height": ih},
        "elements": elements,
        "all_names": all_names,
        "source": "uia",
    }


def _norm(s):
    return " ".join(re.sub(r"[^\w]+", " ", s.casefold()).split())


def name_is_printed(name: str, read: str) -> bool:
    """Does the OCR reading of a box show its UIA name? Containment either way
    ("Save" in "Save As..."), or a close spelling for OCR slips."""
    import difflib
    a = _norm(name)
    if not a:
        return False
    # a reader may return several readings joined by " | "; judge each
    for b in (_norm(r) for r in read.split(" | ")):
        if b and (a in b or (b in a and len(b) >= 0.6 * len(a))
                  or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8):
            return True
    return False


def tesseract_reader():
    """A box reader on Tesseract: crop, upscale, light-on-dark inverted, one
    block of text. None when Tesseract is not installed."""
    import cv2

    from visual_dom.adapters.outbound.ocr.text_detector import find_tesseract
    exe = find_tesseract()
    if not exe:
        return None
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = exe

    def read(image, b):
        crop = image[b[1]:b[3], b[0]:b[2]]
        if crop.size == 0:
            return ""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        if gray.mean() < 128:
            gray = 255 - gray
        # trim the control's own border, which Tesseract reads as text
        # or which makes it read nothing at all
        inset = 6 if min(gray.shape) > 40 else 0
        if inset:
            gray = gray[inset:-inset, inset:-inset]
        # block, single-line and sparse reads: each mode misses captions the
        # others find (block mode returns nothing for a framed "OK")
        reads = [pytesseract.image_to_string(gray, config=f"--psm {m}").strip()
                 for m in (6, 7, 11)]
        return " | ".join(r for r in reads if r)
    return read


def confirm_printed(gt, image, read):
    """
    Keep a UIA name as a caption only where the screen prints it.

    UIA names are often spoken names ("Memory recall") for printed glyphs
    ("MR"); a text= step on them would fail every executor that reads the
    screen. A box whose reading does not show its name is demoted to ``icon``
    with ``printed`` (the reading) and ``review: "name not printed"``; the
    reviewer can restore it with the printed text as its caption. OCR only
    proposes here - it decides nothing the review sheet does not show.

    A guessed icon-only control is read too: a short word in a narrow box
    (PuTTY's "Bell" tree item) passes the size test, and its printed name
    restores it.
    """
    for e in gt["elements"]:
        guessed = e.get("review") == "icon-only?"
        if e["visual_type"] not in ("button", "checkbox") and not guessed:
            continue
        got = read(image, e["bounds"])
        e["printed"] = got
        if name_is_printed(e["ocr_text"], got):
            if guessed:
                e["visual_type"], e["role_word"] = _ACTIONABLE[e["uia_type"]]
                del e["review"]
        elif not guessed:
            e["visual_type"] = "icon"
            e["review"] = "name not printed"
    return gt


def unpainted(gt, image, min_std=4.0):
    """
    Ids of the named elements whose box is one flat colour on the screenshot.

    A page that is still loading (Windows Settings shows a spinner) already
    has its full UIA tree, so every element is labelled while the screen
    shows none of them; the before/after comparison cannot see it because
    the blank page does not change. A few flat boxes are normal (a collapsed
    label, a scroll-bar arrow); most of them mean the page is not drawn.
    """
    ids = []
    for e in gt["elements"]:
        if not e.get("ocr_text") or e["visual_type"] == "block":
            continue
        x0, y0, x1, y1 = e["bounds"]
        crop = image[y0:y1, x0:x1]
        if crop.size and float(crop.std()) < min_std:
            ids.append(e["id"])
    return ids


def check_painted(gt, image, max_share=0.3, min_count=3):
    """Refuse a capture whose labels mostly point at blank screen."""
    named = sum(1 for e in gt["elements"]
                if e.get("ocr_text") and e["visual_type"] != "block")
    blank = unpainted(gt, image)
    if named and len(blank) >= min_count and len(blank) >= max_share * named:
        raise RuntimeError(
            f"{len(blank)} of {named} labelled elements are blank on the screenshot "
            f"({', '.join(blank[:6])}...) - the page is probably still loading; "
            "wait until it is drawn and capture again (--delay)")


def recheck_printed(root=DEFAULT_ROOT, read=None):
    """Re-read every demoted element of every saved state with the current
    reader and restore the ones whose name is now found. Returns the ids of
    the restored elements; labels are rewritten in place."""
    import cv2
    read = read or tesseract_reader()
    restored = []
    for label in sorted((Path(root) / "labels").glob("*.json")):
        gt = json.loads(label.read_text(encoding="utf-8"))
        demoted = [e for e in gt["elements"]
                   if e.get("review") in ("name not printed", "icon-only?")]
        if not demoted:
            continue
        image = cv2.imread(str(Path(root) / "images" / f"{label.stem}.png"))
        for e in demoted:
            e["visual_type"], e["review"] = "icon", "icon-only?"
        confirm_printed({"elements": demoted}, image, read)
        changed = [e for e in demoted if e["visual_type"] != "icon"]
        for e in demoted:
            if e["visual_type"] == "icon" and e["review"] == "icon-only?" \
                    and not looks_icon_only(e["ocr_text"], e["bounds"]):
                e["review"] = "name not printed"
        restored += [f"{label.stem}/{e['id']}" for e in changed]
        label.write_text(json.dumps(gt, indent=1, ensure_ascii=False), encoding="utf-8")
    return restored


# --------------------------------------------------------------------------- #
# Windows: capture + UIA dump
# --------------------------------------------------------------------------- #

def dump_uia(hwnd, max_nodes=5000):
    """The window's UIA tree as a flat node list (see uia_to_gt)."""
    from pywinauto.uia_element_info import UIAElementInfo

    nodes = []
    stack = [(UIAElementInfo(hwnd), None)]
    while stack and len(nodes) < max_nodes:
        info, parent = stack.pop()
        try:
            r = info.rectangle
            node = {"name": info.name, "control_type": info.control_type,
                    "rect": (r.left, r.top, r.right, r.bottom),
                    "visible": bool(info.visible), "parent": parent}
        except Exception:
            continue
        nodes.append(node)
        idx = len(nodes) - 1
        try:
            children = info.children()
        except Exception:
            children = []
        # reversed so the pop order is tree order
        stack.extend((c, idx) for c in reversed(children))
    return nodes


def _window_rect(hwnd):
    """(x, y, w, h) of the whole visible window - title bar and Win32 menu bar
    included, which the client area leaves out - without the invisible resize
    border (DWM extended frame bounds)."""
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
            return None

    # clip to the monitor's work area: a window reaching the screen edge
    # would otherwise carry the taskbar - the user's pinned apps - into a
    # dataset meant for publication
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
    mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    mon = ctypes.windll.user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)
    if mon and ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        w = mi.rcWork
        r.left, r.top = max(r.left, w.left), max(r.top, w.top)
        r.right, r.bottom = min(r.right, w.right), min(r.bottom, w.bottom)
    if r.right <= r.left or r.bottom <= r.top:
        return None
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _grab(cap, rect):
    """(pixels, screen origin) of a rectangle on the monitor it sits on,
    clipped to that monitor; (None, None) when it is on none."""
    mon = cap._monitor_for_rect(rect)
    if mon is None:
        return None, None
    frame = cap._grab_monitor(mon)
    x, y, wd, h = rect
    x0, y0 = max(0, x - mon["left"]), max(0, y - mon["top"])
    x1, y1 = x - mon["left"] + wd, y - mon["top"] + h
    crop = frame[y0:y1, x0:x1]
    if not crop.size:
        return None, None
    return crop.copy(), (mon["left"] + x0, mon["top"] + y0)


def capture_state(title, app, state, root=DEFAULT_ROOT, delay=0.0, check_printed=True):
    """Photograph a window, dump its UIA tree, write image + label. Returns
    the label path and the number of steppable elements."""
    import cv2
    import numpy as np

    from visual_dom.adapters.outbound import win32_window as w
    from visual_dom.adapters.outbound.capture.builtin.windows import WindowsCapture

    for part in (app, state):
        if not _STATE_ID.match(part):
            raise ValueError(f"{part!r}: use lowercase letters, digits and '-' "
                             "(state ids are <app>__<state>)")
    read = None
    if check_printed:
        read = tesseract_reader()
        if read is None:
            raise RuntimeError("Tesseract is needed to check that UIA names are printed "
                               "on the screen; install it or pass --no-printed-check "
                               "(then review every element by hand)")
    if delay:
        time.sleep(delay)

    # the WHOLE window, not the client area the test captures use: a Win32
    # menu bar is non-client, and "File" / "Edit" are prime targets
    w.ensure_process_dpi_aware()
    hwnd = w.find_window(title)
    if hwnd is None or not w.bring_to_front(hwnd):
        raise RuntimeError(f"could not raise window {title!r} (not found, minimised, "
                           "or another window kept the focus)")
    rect = _window_rect(hwnd)
    cap = WindowsCapture(window_title=title)
    try:
        before, origin = _grab(cap, rect) if rect else (None, None)
        if before is None:
            raise RuntimeError(f"window {title!r} is not on any monitor")
        nodes = dump_uia(hwnd)
        after, _ = _grab(cap, rect)
    finally:
        cap.close()

    # the tree walk takes time; a screen that changed meanwhile has no answer key
    if after is None or after.shape != before.shape or \
            float(np.mean(cv2.absdiff(after, before))) > 1.0:
        raise RuntimeError("the window changed while its tree was read (animation, "
                           "caret, tooltip?) - move the mouse away and capture again")

    h, wd = before.shape[:2]
    gt = uia_to_gt(nodes, (origin[0], origin[1], wd, h), (wd, h))
    check_painted(gt, before)
    if read:
        confirm_printed(gt, before, read)
    else:
        for e in gt["elements"]:
            if e["visual_type"] in ("button", "checkbox"):
                e["review"] = "unchecked"
    gt["window_title"] = title

    root = Path(root)
    sid = f"{app}__{state}"
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(root / "images" / f"{sid}.png"), before)
    label = root / "labels" / f"{sid}.json"
    label.write_text(json.dumps(gt, indent=1, ensure_ascii=False), encoding="utf-8")
    n = sum(1 for e in gt["elements"] if e["visual_type"] in ("button", "checkbox"))
    return label, n


# --------------------------------------------------------------------------- #
# review sheet
# --------------------------------------------------------------------------- #

_COLORS = {"button": "#2e9e6b", "checkbox": "#2e9e6b", "icon": "#e0912f",
           "text": "#5b8def"}


def review_sheet(root=DEFAULT_ROOT, steps_path=DEFAULT_STEPS):
    """One HTML page over every state: boxes on the screenshot (green = will
    be stepped on, orange = guessed icon-only, blue = plain text) and the
    negatives the manifest drew, if it exists yet. The reviewer fixes a label
    by editing its JSON (visual_type) and regenerates the steps."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    out = root / "review.html"
    negs = {}
    if Path(steps_path).exists():
        manifest = json.loads(Path(steps_path).read_text(encoding="utf-8"))
        for s in manifest["steps"]:
            if s.get("expect") == "FAILED":
                negs.setdefault(s["state"], []).append(
                    f'{s["description"]} ({s.get("negative_kind", "nonsense")})')
    parts = []
    for label in sorted((root / "labels").glob("*.json")):
        sid = label.stem
        gt = json.loads(label.read_text(encoding="utf-8"))
        iw, ih = gt["image_size"]["width"], gt["image_size"]["height"]
        boxes, rows = [], []
        for e in gt["elements"]:
            color = _COLORS.get(e["visual_type"])
            if not color or not e.get("ocr_text"):
                continue
            x0, y0, x1, y1 = e["bounds"]
            boxes.append(
                f'<div class="b" title="{html.escape(e["id"] + " " + e["ocr_text"])}" style="'
                f'left:{100 * x0 / iw:.2f}%;top:{100 * y0 / ih:.2f}%;'
                f'width:{100 * (x1 - x0) / iw:.2f}%;height:{100 * (y1 - y0) / ih:.2f}%;'
                f'border-color:{color}"><span style="background:{color}">{e["id"]}</span></div>')
            if e["visual_type"] != "text":
                rows.append(f'<tr><td>{e["id"]}</td><td>{e["visual_type"]}</td>'
                            f'<td>{html.escape(e.get("uia_type", ""))}</td>'
                            f'<td>{html.escape(e["ocr_text"])}</td>'
                            f'<td>{html.escape(e.get("printed", ""))}</td>'
                            f'<td>{html.escape(e.get("review", ""))}</td></tr>')
        neg = "".join(f"<li>{html.escape(n)}</li>" for n in negs.get(sid, [])) or \
            "<li><i>no manifest yet</i></li>"
        parts.append(
            f'<section><h2>{sid}</h2><div class="shot"><img src="images/{sid}.png">'
            f'{"".join(boxes)}</div><div class="side"><h3>Negatives - confirm each is NOT '
            f'on the screen</h3><ul>{neg}</ul><h3>Actionable / icon</h3><table>'
            f'<tr><th>id</th><th>type</th><th>UIA</th><th>name</th><th>OCR read</th>'
            f'<th>flag</th></tr>'
            f'{"".join(rows)}</table></div></section>')
    out.write_text(
        "<!doctype html><meta charset=utf-8><title>Real-world states - review</title><style>"
        "body{font:13px system-ui;margin:16px;background:#fff;color:#222}"
        "section{display:flex;gap:16px;margin-bottom:32px;align-items:flex-start}"
        ".shot{position:relative;flex:0 0 60%}.shot img{width:100%;display:block}"
        ".b{position:absolute;border:2px solid}.b span{position:absolute;top:-14px;left:-2px;"
        "font-size:10px;color:#fff;padding:0 2px}.side{flex:1}"
        "table{border-collapse:collapse}td,th{border-bottom:1px solid #ddd;padding:2px 6px;"
        "text-align:left}</style><h1>Real-world states - review</h1><p>Green: becomes a "
        "click + verify step. Orange: no step - guessed icon-only, or its UIA name is not "
        "printed in the box (\"Memory recall\" on a key printed \"MR\"). If the screen "
        "prints a usable caption, set visual_type to \"button\" and ocr_text to the PRINTED "
        "text. A green box whose name is not printed inside it: set visual_type to "
        "\"icon\". Then regenerate the steps.</p>"
        + "".join(parts), encoding="utf-8")
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Harvest real-application states (UIA ground truth)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture", help="photograph one window state and dump its UIA tree")
    c.add_argument("--title", required=True, help="window title (substring match)")
    c.add_argument("--app", required=True, help="application id, e.g. notepadpp")
    c.add_argument("--state", required=True, help="state id, e.g. main, find-dialog")
    c.add_argument("--delay", type=float, default=0.0,
                   help="seconds to wait first (to open a menu by hand)")
    c.add_argument("--no-printed-check", action="store_true",
                   help="skip the OCR check that each name is printed (review all by hand)")
    c.add_argument("--root", default=str(DEFAULT_ROOT))
    r = sub.add_parser("review", help="write <root>/review.html")
    r.add_argument("--root", default=str(DEFAULT_ROOT))
    r.add_argument("--steps", default=str(DEFAULT_STEPS))
    k = sub.add_parser("recheck", help="re-read demoted elements of saved states "
                                       "with the current reader")
    k.add_argument("--root", default=str(DEFAULT_ROOT))
    sub.add_parser("windows", help="list visible window titles")
    args = parser.parse_args()

    if args.cmd == "capture":
        label, n = capture_state(args.title, args.app, args.state, args.root, args.delay,
                                 check_printed=not args.no_printed_check)
        print(f"{label}: {n} actionable elements")
    elif args.cmd == "review":
        print(review_sheet(args.root, args.steps))
    elif args.cmd == "recheck":
        restored = recheck_printed(args.root)
        print(f"{len(restored)} restored: {', '.join(restored)}")
    else:
        from visual_dom.adapters.outbound import win32_window as w
        for hwnd, title in w.list_windows():
            print(f"{hwnd:>10}  {title}")


if __name__ == "__main__":
    main()
