"""
Symbol detector for UI elements.

Detects common UI symbols (+, -, =, ×, ÷, etc.) in small regions
where OCR fails. Uses simple pattern recognition based on edge/stroke
analysis rather than template matching for scale robustness.
"""

import cv2
import numpy as np
from typing import Optional, Tuple


def _extract_symbol_strokes(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Extract foreground strokes from a grayscale button region.

    Tries multiple binarization strategies and picks the one that
    produces a clean, sparse foreground (likely a symbol).

    Returns:
        Binary image of center region (cropped), or None.
    """
    h, w = gray.shape
    margin_x = int(w * 0.2)
    margin_y = int(h * 0.2)

    candidates = []

    # Method 1: Otsu (light background)
    otsu_thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, bin_inv = cv2.threshold(gray, otsu_thresh, 255, cv2.THRESH_BINARY_INV)
    _, bin_norm = cv2.threshold(gray, otsu_thresh, 255, cv2.THRESH_BINARY)

    for binary in [bin_inv, bin_norm]:
        center = binary[margin_y:h - margin_y, margin_x:w - margin_x]
        if center.size > 0:
            density = np.sum(center > 0) / center.size
            # Good candidate: sparse foreground (symbol strokes)
            if 0.01 < density < 0.55:
                candidates.append((center, density))

    # Method 2: Adaptive threshold
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    block = max(11, (min(w, h) // 3) | 1)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=block, C=3
    )
    center = adaptive[margin_y:h - margin_y, margin_x:w - margin_x]
    if center.size > 0:
        density = np.sum(center > 0) / center.size
        if 0.01 < density < 0.55:
            candidates.append((center, density))

    if not candidates:
        return None

    # Pick the candidate with density closest to 0.1 (typical for a clean symbol)
    candidates.sort(key=lambda c: abs(c[1] - 0.10))
    return candidates[0][0]


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
# Per-symbol Dice acceptance (default 0.70). "=" varies with bar spacing across
# fonts; the "+/-" composite is an approximation of the real key glyph.
_MIN_SCORE = {"=": 0.60, "±": 0.55}
_DEFAULT_MIN_SCORE = 0.70
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
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/seguisym.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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


def detect_symbol(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],
    min_score: Optional[float] = None,
) -> Optional[str]:
    """
    Detect a common UI symbol in the given region.

    Recognises the arithmetic/UI glyphs in ``_SYMBOLS`` (+ - = × ÷ ± . %) by
    template-matching the glyph's tight bounding box against font-rendered
    templates (Dice score). Hollow outline shapes (a window-maximize square, a
    checkbox frame) are rejected before matching.

    Args:
        image: BGR image (full screenshot)
        bbox: Region to analyze (x1, y1, x2, y2)
        min_score: Override for the default Dice acceptance threshold (0.70).
            Per-symbol calibrated thresholds still apply, but are raised to at
            least this value; i.e. raising it makes everything stricter,
            lowering it only loosens default-tier symbols.

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

    strokes = _extract_symbol_strokes(gray)
    if strokes is None:
        return None
    density = np.sum(strokes > 0) / strokes.size
    if density < 0.005 or density > 0.6:
        return None

    tightened = _tighten_to_glyph(strokes)
    if tightened is None:
        return None
    glyph, _ = tightened
    gh, gw = glyph.shape

    # A single thin solid bar is a minus/dash — classify directly, since a
    # 20x2 bar canonicalises poorly against thick font hyphens (e.g. the
    # title-bar minimize dash).
    fill = np.sum(glyph > 0) / glyph.size
    if gw / max(1, gh) >= 4.0 and fill >= 0.6:
        return "-"

    if gh < 6 or gw < 6:  # too small to classify reliably (post-upscale)
        return None

    # Reject hollow outline shapes (maximize square, checkbox frame): strong
    # strokes only along the bbox edges and an empty centre.
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

    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _build_templates()
    if not _TEMPLATE_CACHE:
        return None

    patch = _canonicalize(glyph)
    scores: dict = {}
    for sym, tmpl in _TEMPLATE_CACHE:
        s = _dice(patch, tmpl)
        if s > scores.get(sym, 0.0):
            scores[sym] = s

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_sym, best = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0

    # Accept only a confident, unambiguous match (per-symbol thresholds).
    default_thr = min_score if min_score is not None else _DEFAULT_MIN_SCORE
    thr = _MIN_SCORE.get(best_sym, default_thr)
    if min_score is not None:
        thr = max(thr, min_score)
    if best >= thr and (best - runner) >= 0.03:
        return best_sym
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


def _check_diagonal(binary: np.ndarray) -> float:
    """Check for diagonal stroke presence. Returns 0-1 score."""
    h, w = binary.shape
    if h < 4 or w < 4:
        return 0

    # Check main diagonal (top-left to bottom-right)
    diag1_pixels = 0
    diag2_pixels = 0
    total_checked = 0

    for i in range(min(h, w)):
        # Map to the other dimension proportionally
        r1 = int(i * h / min(h, w))
        c1 = int(i * w / min(h, w))
        r2 = int(i * h / min(h, w))
        c2 = int((min(h, w) - 1 - i) * w / min(h, w))

        if 0 <= r1 < h and 0 <= c1 < w:
            # Check a small neighborhood
            r_lo = max(0, r1 - 1)
            r_hi = min(h, r1 + 2)
            c_lo = max(0, c1 - 1)
            c_hi = min(w, c1 + 2)
            if np.any(binary[r_lo:r_hi, c_lo:c_hi] > 0):
                diag1_pixels += 1
            total_checked += 1

        if 0 <= r2 < h and 0 <= c2 < w:
            r_lo = max(0, r2 - 1)
            r_hi = min(h, r2 + 2)
            c_lo = max(0, c2 - 1)
            c_hi = min(w, c2 + 2)
            if np.any(binary[r_lo:r_hi, c_lo:c_hi] > 0):
                diag2_pixels += 1

    if total_checked == 0:
        return 0

    return max(diag1_pixels, diag2_pixels) / total_checked
