"""
Symbol detector for UI elements.

Detects common UI symbols (+, -, =, ×, ÷, etc.) in small regions
where OCR fails. Uses simple pattern recognition based on edge/stroke
analysis rather than template matching for scale robustness.
"""

import cv2
import numpy as np
from typing import Optional, Tuple


def _stroke_candidates(gray: np.ndarray) -> list:
    """
    ALL plausible binarizations of a button region (both Otsu polarities +
    adaptive), density-filtered. detect_symbol template-matches every candidate
    and keeps the best overall — choosing by a density heuristic alone proved
    wrong on thick-glyph themes, where an adaptive-threshold *ring* artifact
    (glyph appearing as a hole in a blob) had the "best" density and won.

    Each binarization is offered at TWO crop margins. The wide margin (20%)
    strips button borders on loose key-cell boxes; but on a box drawn tightly
    around the glyph it amputates structure — a hamburger menu loses its outer
    bars and the survivor reads as a plausible "-". The narrow-margin sibling
    keeps the full structure, and the specificity ranking prefers whichever view
    explains more components.
    """
    h, w = gray.shape
    out = []

    otsu_thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, bin_inv = cv2.threshold(gray, otsu_thresh, 255, cv2.THRESH_BINARY_INV)
    _, bin_norm = cv2.threshold(gray, otsu_thresh, 255, cv2.THRESH_BINARY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    block = max(11, (min(w, h) // 3) | 1)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=block, C=3
    )
    for margin in (0.2, 0.05):
        margin_x, margin_y = int(w * margin), int(h * margin)
        for binary in (bin_inv, bin_norm, adaptive):
            center = binary[margin_y:h - margin_y, margin_x:w - margin_x]
            if center.size == 0:
                continue
            density = np.sum(center > 0) / center.size
            if 0.005 < density < 0.6:
                out.append(center)
    return out


def _tighten_to_glyph(binary: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """
    Crop a binary stroke image to the glyph's own bounding box.

    A key/button crop is mostly background, so projection analysis on it is
    scale-dependent and unreliable (the root cause of both missed operators and
    the hollow-square -> "+" false positive). Analysing the tight glyph bbox
    normalises scale.

    Returns:
        (tight binary crop, glyph_area / full_area) or None if no glyph found.
    """
    ys, xs = np.where(binary > 0)
    if len(xs) < 4:
        return None
    x1, x2 = xs.min(), xs.max() + 1
    y1, y2 = ys.min(), ys.max() + 1
    if (x2 - x1) < 3 or (y2 - y1) < 2:
        return None
    tight = binary[y1:y2, x1:x2]
    area_ratio = float(len(xs)) / binary.size
    return tight, area_ratio


# --------------------------------------------------------------------------- #
# Template matching
#
# Hand-tuned projection rules are fragile at real glyph sizes (8-20 px): a "-"
# binarises to a chunky 17x9 blob, "=" bars fill most of their tight bbox, and
# thresholds tuned for one shape break another. Instead we render each candidate
# symbol with real fonts, normalise both glyph and template to a canonical
# binary patch, and score with the Dice coefficient. Scale-invariant, easy to
# extend (add a char to _SYMBOLS), and anti-aliasing tolerant.
# --------------------------------------------------------------------------- #

# (render string, reported symbol). Multi-char renders cover composite glyphs:
# e.g. the Windows Calculator plus/minus key draws "+/-", not the font's "±".
_SYMBOLS = [
    ("+", "+"), ("-", "-"), ("=", "="), ("×", "×"), ("÷", "÷"),
    ("±", "±"), ("+/-", "±"), (".", "."), ("%", "%"),
]
# Canonical semantic names for read glyphs. Used to label operator keys where a
# caption model produced a look-alike guess ("Add" on ÷, "Close" on ×,
# "Minimize" on −): the pixel read is authoritative outside the title bar.
SYMBOL_LABELS = {
    "+": "Plus", "-": "Minus", "×": "Multiply", "÷": "Divide",
    "=": "Equals", "±": "Plus/Minus", ".": "Decimal", "%": "Percent",
}

_CANON = 32                   # canonical patch size
_TEMPLATE_CACHE: Optional[list] = None


def _canonicalize(binary: np.ndarray) -> np.ndarray:
    """Resize a tight binary glyph onto a CANONxCANON patch, preserving aspect."""
    h, w = binary.shape
    scale = (_CANON - 2) / max(h, w)
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    resized = cv2.resize(binary, (nw, nh), interpolation=cv2.INTER_AREA)
    patch = np.zeros((_CANON, _CANON), dtype=np.uint8)
    y0, x0 = (_CANON - nh) // 2, (_CANON - nw) // 2
    patch[y0:y0 + nh, x0:x0 + nw] = (resized > 127).astype(np.uint8) * 255
    return patch


def _build_templates() -> list:
    """Render each symbol in a few fonts -> list of (symbol, canonical patch)."""
    from PIL import Image, ImageDraw, ImageFont

    font_paths = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",   # bold — thick-glyph themes (e.g. Win11 calc)
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",    # bold
        "C:/Windows/Fonts/seguisym.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    templates = []
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, 64)
        except OSError:
            continue
        for render, sym in _SYMBOLS:
            img = Image.new("L", (192, 128), 0)
            draw = ImageDraw.Draw(img)
            draw.text((96, 64), render, fill=255, font=font, anchor="mm")
            arr = np.array(img)
            tight = _tighten_to_glyph((arr > 127).astype(np.uint8) * 255)
            if tight is None:
                continue
            templates.append((sym, _canonicalize(tight[0])))

        # Composite plus/minus as drawn on calculator keys: a small "+" top-left,
        # a "/" through the middle, a small "-" bottom-right (diagonal layout —
        # no font string renders this arrangement).
        try:
            small = ImageFont.truetype(path, 40)
            img = Image.new("L", (128, 128), 0)
            draw = ImageDraw.Draw(img)
            draw.text((30, 26), "+", fill=255, font=small, anchor="mm")
            draw.text((64, 64), "/", fill=255, font=font, anchor="mm")
            draw.text((98, 102), "-", fill=255, font=small, anchor="mm")
            tight = _tighten_to_glyph((np.array(img) > 127).astype(np.uint8) * 255)
            if tight is not None:
                templates.append(("±", _canonicalize(tight[0])))
        except OSError:
            pass
    return templates


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    """Dice coefficient of two binary patches (1.0 = identical)."""
    fa, fb = a > 0, b > 0
    inter = np.logical_and(fa, fb).sum()
    denom = fa.sum() + fb.sum()
    return 2.0 * inter / denom if denom else 0.0


# Specificity rank: when different binarizations of one region disagree, prefer
# the reading that explains MORE structure. A degraded binarization can only
# lose components (the dots of ÷, the second bar of =) — so "÷ from candidate A"
# beats "- from candidate B", never the other way round. Without this, any
# candidate that degenerates into a wide blob wins as a high-scoring "-".
# "menu" is a veto sentinel, not a symbol: a hamburger icon (three stacked
# bars) must silence the bar family, because a binarization that merges or drops
# one bar reads convincingly as "-" or "=". Its rank sits above both so the
# candidate that SAW all three bars wins, and detect_symbol maps it to None.
_SPECIFICITY = {"÷": 6, "%": 6, "±": 5, "menu": 4.5, "=": 4, "+": 3, "×": 3,
                ".": 2, "-": 1}


def detect_symbol(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],
    min_score: Optional[float] = None,
) -> Optional[str]:
    """
    Detect a common UI symbol in the given region.

    Recognises the arithmetic/UI glyphs in ``_SYMBOLS`` (+ - = × ÷ ± . %).
    Classification is **structure-first**: the glyph's connected components must
    form the symbol's actual shape (÷ = bar with a dot above and below, = = two
    stacked bars, + = centred cross, ...), with font-template Dice scores as
    supporting evidence where structure alone is loose (+ × ±). A region whose
    glyph fits no structure is rejected — which is what keeps word keys ("mod",
    "exp"), icons (a backspace ⌫), and digits from being misread as operators:
    canonicalised, those all look bar-like enough to fool a template score, but
    none of them survives a component-level test.

    Args:
        image: BGR image (full screenshot)
        bbox: Region to analyze (x1, y1, x2, y2)
        min_score: Optional extra strictness: when set, the winning symbol's
            template Dice score must also reach this value. Structure decides;
            this only vetoes.

    Returns:
        Detected symbol string (e.g., "+", "-", "=") or None
    """
    global _TEMPLATE_CACHE

    x1, y1, x2, y2 = bbox
    region = image[y1:y2, x1:x2]
    if region.size == 0:
        return None

    h, w = region.shape[:2]
    if w < 8 or h < 8:
        return None

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region

    # Small anti-aliased glyphs binarise badly at native size (a title-bar dash
    # can survive as ~10 stray pixels); upscale first so strokes are solid.
    if min(h, w) < 48:
        f = int(np.ceil(64.0 / min(h, w)))
        gray = cv2.resize(gray, (w * f, h * f), interpolation=cv2.INTER_CUBIC)

    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _build_templates()
    if not _TEMPLATE_CACHE:
        return None

    # Evaluate EVERY binarization candidate (both polarities + adaptive); pick
    # the winner by (specificity, score) — see _SPECIFICITY.
    best: Optional[Tuple[int, float, str]] = None
    for strokes in _stroke_candidates(gray):
        result = _classify_candidate(strokes, min_score, region_h=gray.shape[0])
        if result is None:
            continue
        sym, score = result
        key = (_SPECIFICITY.get(sym, 0), score)
        if best is None or key > (best[0], best[1]):
            best = (key[0], key[1], sym)
    if best is None or best[2] == "menu":     # hamburger veto — not a symbol
        return None
    return best[2]


def _components(glyph: np.ndarray) -> list:
    """
    Connected components of a tight binary glyph, as dicts with geometry.

    Specks below 2% of the total ink are dropped (anti-aliasing debris) so that
    component COUNTS are meaningful: ÷ must yield exactly 3, = exactly 2.
    """
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(
        (glyph > 0).astype(np.uint8), connectivity=8)
    total_ink = int(np.sum(glyph > 0))
    comps = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if area < max(2, 0.02 * total_ink):
            continue
        comps.append({
            "x": int(x), "y": int(y), "w": int(cw), "h": int(ch),
            "area": int(area), "cx": float(centroids[i][0]),
            "cy": float(centroids[i][1]),
            "fill": area / max(1, cw * ch),
            "mask": (labels == i),
        })
    comps.sort(key=lambda c: c["area"], reverse=True)
    return comps


def _is_bar(c: dict) -> bool:
    """A solid, clearly-horizontal stroke."""
    return c["w"] / max(1, c["h"]) >= 2.2 and c["fill"] >= 0.55


def _diagonal_coverage(glyph: np.ndarray) -> Tuple[float, float, float]:
    """
    (main-diagonal coverage, anti-diagonal coverage, fraction of ink inside the
    two diagonal bands). An × has BOTH diagonals covered and nearly all its ink
    on them; a ⌫ icon or a digit covers at most one, or carries most of its ink
    elsewhere.

    The band is NARROW (12% of the width, min 1.5 px): a wide band degenerates
    into "everything is ×", because with enough slack any blob touches both
    diagonals.
    """
    h, w = glyph.shape
    if h < 4 or w < 4:
        return 0.0, 0.0, 0.0
    ink = glyph > 0
    rows = np.arange(h, dtype=np.float32)
    cols = np.arange(w, dtype=np.float32)
    # Expected column of each diagonal per row, as a (h, 1) column vector.
    main_c = (rows * (w - 1) / max(1, h - 1)).reshape(-1, 1)
    anti_c = (w - 1) - main_c
    band = max(1.5, 0.12 * w)
    on_main = np.abs(cols.reshape(1, -1) - main_c) <= band     # (h, w)
    on_anti = np.abs(cols.reshape(1, -1) - anti_c) <= band
    d1 = np.sum(np.any(ink & on_main, axis=1)) / h   # rows where the main diag has ink
    d2 = np.sum(np.any(ink & on_anti, axis=1)) / h
    total = np.sum(ink)
    on = np.sum(ink & (on_main | on_anti))
    return float(d1), float(d2), float(on / total if total else 0.0)


def _classify_candidate(
    strokes: np.ndarray,
    min_score: Optional[float],
    region_h: int,
) -> Optional[Tuple[str, float]]:
    """Tighten + structurally classify ONE binarization candidate."""
    tightened = _tighten_to_glyph(strokes)
    if tightened is None:
        return None
    glyph, area_ratio = tightened
    gh, gw = glyph.shape
    aspect = gw / max(1, gh)
    fill = np.sum(glyph > 0) / glyph.size

    # Reject hollow outline shapes (maximize square, checkbox frame): strong
    # strokes only along the bbox edges and an empty centre.
    if gh >= 6 and gw >= 6:
        h_norm = np.sum(glyph > 0, axis=1) / gw
        v_norm = np.sum(glyph > 0, axis=0) / gh
        h_segments = _count_segments(h_norm > 0.55)
        v_segments = _count_segments(v_norm > 0.55)
        cy0, cy1 = gh // 2 - max(1, gh // 6), gh // 2 + max(1, gh // 6) + 1
        cx0, cx1 = gw // 2 - max(1, gw // 6), gw // 2 + max(1, gw // 6) + 1
        center_fill = np.sum(glyph[max(0, cy0):cy1, max(0, cx0):cx1] > 0) / \
            max(1, (cy1 - max(0, cy0)) * (cx1 - max(0, cx0)))
        if h_segments >= 2 and v_segments >= 2 and center_fill < 0.2:
            return None

    # Template Dice scores: supporting evidence, never the decision alone.
    scores: dict = {}
    if gh >= 4 and gw >= 4:
        patch = _canonicalize(glyph)
        for sym, tmpl in _TEMPLATE_CACHE:
            s = _dice(patch, tmpl)
            if s > scores.get(sym, 0.0):
                scores[sym] = s

    comps = _components(glyph)
    if not comps:
        return None

    result = _structural_symbol(glyph, comps, aspect, fill, area_ratio,
                                region_h, scores)
    if result is None:
        return None
    sym, score = result
    if min_score is not None and scores.get(sym, 0.0) < min_score:
        return None
    return (sym, score)


def _structural_symbol(glyph, comps, aspect, fill, area_ratio,
                       region_h, dice) -> Optional[Tuple[str, float]]:
    """
    Match the component layout against each symbol's actual shape.
    Checked most-specific first; the caller additionally ranks across
    binarization candidates with _SPECIFICITY.
    """
    gh, gw = glyph.shape
    n = len(comps)

    # -- ☰ : three or more stacked bars is a hamburger MENU, not an operator ---
    # Aspect-only (no fill test): a clipped outer bar binarizes patchily, but
    # three WIDE stacked strokes already rule out every symbol we recognise.
    if n >= 3:
        bars = [c for c in comps if c["w"] / max(1, c["h"]) >= 2.2]
        if len(bars) == n:
            bars.sort(key=lambda c: c["cy"])
            widths = [c["w"] for c in bars]
            overlaps = all(
                min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                >= 0.6 * max(a["w"], b["w"])
                for a, b in zip(bars, bars[1:]))
            if min(widths) / max(widths) >= 0.6 and overlaps:
                return ("menu", 0.9)

    # -- ÷ : wide bar + one dot above + one dot below --------------------------
    if n == 3:
        bar = max(comps, key=lambda c: c["w"])
        dots = [c for c in comps if c is not bar]
        if (_is_bar(bar) and bar["w"] >= 0.7 * gw
                and all(0.35 <= d["w"] / max(1, d["h"]) <= 2.8 for d in dots)
                and all(d["area"] <= 0.9 * bar["area"] for d in dots)
                and min(d["cy"] for d in dots) < bar["cy"] - bar["h"]
                and max(d["cy"] for d in dots) > bar["cy"] + bar["h"]
                and all(abs(d["cx"] - gw / 2.0) <= 0.3 * gw for d in dots)):
            return ("÷", max(0.9, dice.get("÷", 0.0)))

    # -- % : two compact dots on opposite corners of a diagonal stroke ---------
    if n == 3:
        slash = max(comps, key=lambda c: c["h"])
        dots = [c for c in comps if c is not slash]
        if (slash["h"] >= 0.7 * gh
                and all(0.4 <= d["w"] / max(1, d["h"]) <= 2.5 for d in dots)):
            top = min(dots, key=lambda d: d["cy"])
            bot = max(dots, key=lambda d: d["cy"])
            if (top["cy"] < gh * 0.45 and bot["cy"] > gh * 0.55
                    and top["cx"] < gw * 0.5 < bot["cx"]
                    and dice.get("%", 0.0) >= 0.5):
                return ("%", max(0.9, dice.get("%", 0.0)))

    # -- = : exactly two stacked, similar, solid horizontal bars ---------------
    if n == 2:
        a, b = sorted(comps, key=lambda c: c["cy"])
        x_overlap = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
        if (_is_bar(a) and _is_bar(b)
                and a["h"] >= 2 and b["h"] >= 2
                and min(a["w"], b["w"]) / max(a["w"], b["w"]) >= 0.65
                and x_overlap >= 0.6 * max(a["w"], b["w"])
                and (b["cy"] - a["cy"]) >= max(2.0, 0.9 * max(a["h"], b["h"]))):
            return ("=", max(0.9, dice.get("=", 0.0)))

    # -- ± : the calculator key draws "+/-": a cross top-left, a slash, a bar
    #        bottom-right. Structure: one wide solid bar sitting below AND right
    #        of everything else (÷ cannot match — its dots straddle the bar; the
    #        template composite backs it up when binarization merges components).
    if 2 <= n <= 4 and 0.55 <= aspect <= 1.9:
        bars = [c for c in comps if _is_bar(c) and c["fill"] >= 0.7]
        others = [c for c in comps if c not in bars]
        structural_pm = (
            len(bars) == 1 and others
            and all(bars[0]["cy"] > o["cy"] for o in others)
            and all(bars[0]["cx"] > o["cx"] for o in others)
            and any(o["h"] >= 0.4 * gh for o in others)   # the slash / cross part
        )
        # Structure is required — a Dice-only acceptance proved too loose (an
        # inverted-polarity '6' is a blob plus its counter-hole, and the composite
        # template scored it 0.63).
        if structural_pm:
            return ("±", max(0.85, dice.get("±", 0.0)))

    if n == 1:
        c = comps[0]

        # -- . : tiny, near-round, solid blob relative to its key. Aspect cap
        #        1.5, not 2.0: a smeared minus dash reaches 1.63 and must not
        #        outrank the true '-' reading from a cleaner binarization.
        if (gh <= max(6, region_h / 4.0) and 0.5 <= aspect <= 1.5
                and fill >= 0.6 and area_ratio < 0.1):
            return (".", max(0.85, dice.get(".", 0.0)))

        # -- - : one solid clearly-horizontal stroke. Fill 0.7 is the floor that
        #        separates real bars (measured 0.72-0.98) from a merged lowercase
        #        word ("ln" binarises to a 50x22 blob at fill 0.67). The relaxed
        #        branch covers a thin dash smeared square-ish by the cubic
        #        upscale (a title-bar minimize at 125% scaling): tiny relative
        #        height + template agreement stand in for the lost aspect ratio.
        if fill >= 0.7 and (
                (aspect >= 2.2 and gh <= 0.5 * region_h)
                or (aspect >= 1.4 and gh <= 0.30 * region_h
                    and dice.get("-", 0.0) >= 0.6)):
            return ("-", max(0.9, dice.get("-", 0.0)))

        # -- + : centred cross: full-width middle row, full-height middle col,
        #        empty corners. The corner test is what digits fail.
        if 0.55 <= aspect <= 1.8 and gh >= 6 and gw >= 6:
            band_h = max(1, int(0.12 * gh))
            band_w = max(1, int(0.12 * gw))
            mid_rows = glyph[gh // 2 - band_h: gh // 2 + band_h + 1, :]
            mid_cols = glyph[:, gw // 2 - band_w: gw // 2 + band_w + 1]
            row_span = np.sum(np.any(mid_rows > 0, axis=0)) / gw
            col_span = np.sum(np.any(mid_cols > 0, axis=1)) / gh
            ch_, cw_ = max(2, gh // 3), max(2, gw // 3)
            corners = [glyph[:ch_, :cw_], glyph[:ch_, -cw_:],
                       glyph[-ch_:, :cw_], glyph[-ch_:, -cw_:]]
            corner_fill = max(np.sum(c_ > 0) / c_.size for c_ in corners)
            if (row_span >= 0.75 and col_span >= 0.75
                    and corner_fill <= 0.30 and dice.get("+", 0.0) >= 0.5):
                return ("+", max(0.85, dice.get("+", 0.0)))

        # -- × : both diagonals covered, and the ink LIVES on the diagonals ----
        if 0.55 <= aspect <= 1.8 and gh >= 6 and gw >= 6:
            d1, d2, on_band = _diagonal_coverage(glyph)
            if min(d1, d2) >= 0.7 and on_band >= 0.75 and dice.get("×", 0.0) >= 0.5:
                return ("×", max(0.85, dice.get("×", 0.0)))

    return None


def _count_segments(active: np.ndarray) -> int:
    """Count number of contiguous active segments."""
    if len(active) == 0:
        return 0

    segments = 0
    in_segment = False
    for val in active:
        if val and not in_segment:
            segments += 1
            in_segment = True
        elif not val:
            in_segment = False
    return segments
