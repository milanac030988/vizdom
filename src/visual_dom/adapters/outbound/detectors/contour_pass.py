"""
Contour pass for the modular detector: a second, model-free look for icons
the region model did not propose.

Why it exists (2026-11-23): on an automotive home screen the icon model
scored a dimmed fan icon at 0.004, far under its 0.05 cut-off, while the
same shape in white scored 0.17. Lowering the cut-off to reach it lets in
noise everywhere. The icon was nevertheless plain to see: an isolated shape
of icon size on a quiet background. This pass finds exactly that and nothing
more.

What counts as a candidate:

  1. it stands out from its local background (median over a wide window) by
     at least ``min_delta`` grey levels;
  2. after its strokes are joined, it is one connected shape of icon size
     and roughly square proportions;
  3. it is isolated: a thin ring around its box is one even background,
     so the corner of a panel or a piece of a picture does not qualify;
  4. nothing already detected covers it (a region, a text box).

It is deliberately conservative. It never replaces or removes a box of the
earlier stages, and a shape that fails any test is left alone. Off by
default (``detector.contour_pass``), so every published benchmark figure is
unchanged.
"""

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

Box = Tuple[int, int, int, int]

# The pass has no model score to hand over. A fixed, low value marks its
# boxes as second-rate beside any model detection of the same thing.
CONTOUR_CONFIDENCE = 0.2


@dataclass(frozen=True)
class ContourPassParams:
    """Sizes are fractions of the image height, so one setting fits 720p and 4K."""

    min_delta: int = 20            # grey levels above/below the local background
    background_window: float = 0.12
    join: float = 0.008            # closing kernel that joins an icon's strokes
    min_side: float = 0.022        # 16 px at 720p
    max_side: float = 0.14         # 100 px at 720p
    min_aspect: float = 0.5        # width / height
    max_aspect: float = 2.0
    min_fill: float = 0.10         # share of the box that stands out
    max_fill: float = 0.90
    ring: float = 0.006            # width of the isolation ring
    max_ring_fill: float = 0.04
    max_ring_spread: int = 16      # grey-level spread allowed inside the ring ...
    ring_spread_ratio: float = 0.3  # ... or this share of the shape's own contrast, if larger
    covered: float = 0.2           # overlap with an existing box that rules a candidate out
    max_candidates: int = 25       # more than this is a picture or a texture, not icons


def _odd(value: float, minimum: int = 3) -> int:
    n = max(minimum, int(round(value)))
    return n if n % 2 else n + 1


def _intersection(a: Box, b: Box) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


def standout_mask(image: np.ndarray, params: ContourPassParams) -> np.ndarray:
    """Pixels that differ from their local background, as a 0/255 mask."""
    import cv2

    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    window = _odd(gray.shape[0] * params.background_window, minimum=15)
    background = cv2.medianBlur(gray, window)
    diff = cv2.absdiff(gray, background)
    return (diff >= params.min_delta).astype(np.uint8) * 255


def propose_contour_regions(
    image: np.ndarray,
    existing: Sequence[Box],
    params: ContourPassParams = ContourPassParams(),
) -> List[Box]:
    """
    Icon-like shapes in ``image`` (BGR) that no box of ``existing`` covers.

    Returns boxes in reading order (top to bottom, then left to right); an
    empty list when there are none or when there are suspiciously many.
    """
    import cv2

    height, width = image.shape[:2]
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = standout_mask(gray, params)
    hi = height * params.max_side
    # Take out what is too large to be an icon (a bar, a panel edge, a picture)
    # before the strokes are joined: an icon a few pixels above a bright bar
    # would otherwise be welded to it and lost.
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    large = [i for i in range(1, count)
             if stats[i, cv2.CC_STAT_WIDTH] > hi or stats[i, cv2.CC_STAT_HEIGHT] > hi]
    if large:
        mask = mask.copy()
        mask[np.isin(labels, large)] = 0
    join = _odd(height * params.join)
    joined = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (join, join)))
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(joined, 8)

    lo = height * params.min_side
    ring = max(2, int(round(height * params.ring)))
    out: List[Box] = []
    for i in range(1, count):
        x, y, w, h, _area = (int(v) for v in stats[i])
        if not (lo <= w <= hi and lo <= h <= hi):
            continue
        if not params.min_aspect <= w / h <= params.max_aspect:
            continue
        if x <= 0 or y <= 0 or x + w >= width or y + h >= height:
            continue                                  # cut by the image border
        box = (x, y, x + w, y + h)
        fill = cv2.countNonZero(mask[y:y + h, x:x + w]) / float(w * h)
        if not params.min_fill <= fill <= params.max_fill:
            continue
        # Isolation: the ring around the box holds (almost) no stand-out pixel.
        # A fragment of a picture, a table or a line of text fails here.
        x1, y1 = max(0, x - ring), max(0, y - ring)
        x2, y2 = min(width, x + w + ring), min(height, y + h + ring)
        outer = cv2.countNonZero(mask[y1:y2, x1:x2])
        inner = cv2.countNonZero(mask[y:y + h, x:x + w])
        ring_area = (x2 - x1) * (y2 - y1) - w * h
        if ring_area <= 0 or (outer - inner) / float(ring_area) > params.max_ring_fill:
            continue
        # ... and the ring is ONE background. The mask alone cannot tell: at
        # the corner of a filled panel the local median is the screen behind
        # it, so the corner itself stands out as an icon-sized blob.
        around = np.ones((y2 - y1, x2 - x1), dtype=bool)
        around[y - y1:y - y1 + h, x - x1:x - x1 + w] = False
        # 15th to 85th percentile: a bar that grazes one side of the ring is
        # tolerated, a panel that fills half of it is not.
        ring_pixels = gray[y1:y2, x1:x2][around]
        low, high = np.percentile(ring_pixels, (15, 85))
        # On a photographed screen the background is never flat (a glow, a
        # gradient), so the allowance grows with the shape's own contrast: a
        # bright icon on a soft gradient passes, a panel corner (whose
        # "contrast" IS the step in its ring) still does not.
        inside = gray[y:y + h, x:x + w][mask[y:y + h, x:x + w] > 0]
        contrast = float(np.median(np.abs(inside.astype(np.int16) - np.median(ring_pixels))))
        if high - low > max(params.max_ring_spread, params.ring_spread_ratio * contrast):
            continue
        area = w * h
        if any(_intersection(box, other) > params.covered * area for other in existing):
            continue
        out.append(box)

    if len(out) > params.max_candidates:
        return []
    out.sort(key=lambda b: (b[1], b[0]))
    return out
