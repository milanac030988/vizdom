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


def detect_symbol(image: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[str]:
    """
    Detect a common UI symbol in the given region.

    Args:
        image: BGR image (full screenshot)
        bbox: Region to analyze (x1, y1, x2, y2)

    Returns:
        Detected symbol string (e.g., "+", "-", "=") or None
    """
    x1, y1, x2, y2 = bbox
    region = image[y1:y2, x1:x2]

    if region.size == 0:
        return None

    h, w = region.shape[:2]
    if w < 8 or h < 8:
        return None

    # Convert to grayscale
    if len(region.shape) == 3:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    else:
        gray = region

    # Strategy: try multiple binarization methods and pick the best
    center = _extract_symbol_strokes(gray)

    if center is None:
        return None

    ch, cw = center.shape

    # Compute stroke density
    fg_pixels = np.sum(center > 0)
    total_pixels = ch * cw
    density = fg_pixels / total_pixels if total_pixels > 0 else 0

    # Too little or too much foreground — not a clean symbol
    if density < 0.01 or density > 0.55:
        return None

    # Analyze horizontal and vertical projections
    h_proj = np.sum(center > 0, axis=1)  # sum each row
    v_proj = np.sum(center > 0, axis=0)  # sum each column

    # Normalize projections
    h_norm = h_proj / cw if cw > 0 else h_proj
    v_norm = v_proj / ch if ch > 0 else v_proj

    # Use two thresholds:
    # "strong" = thick stroke (>50% of row/col filled)
    # "weak"   = thin stroke or spread (>10% filled)
    h_strong = h_norm > 0.5
    v_strong = v_norm > 0.5
    h_weak = h_norm > 0.08
    v_weak = v_norm > 0.08

    h_strong_count = int(np.sum(h_strong))
    v_strong_count = int(np.sum(v_strong))
    h_weak_count = int(np.sum(h_weak))
    v_weak_count = int(np.sum(v_weak))

    # Count contiguous strong stroke segments
    h_strong_segments = _count_segments(h_strong)
    v_strong_segments = _count_segments(v_strong)

    # Check if there's a clear peak in horizontal projection (a horizontal line)
    has_h_peak = h_strong_count >= 1
    # Check if there's a clear peak in vertical projection (a vertical line)
    has_v_peak = v_strong_count >= 1

    # Pattern matching

    # PLUS "+" — has both a horizontal and vertical strong stroke
    if has_h_peak and has_v_peak:
        # Verify they cross near center
        h_peak_rows = np.where(h_strong)[0]
        v_peak_cols = np.where(v_strong)[0]
        h_center = np.mean(h_peak_rows) / ch
        v_center = np.mean(v_peak_cols) / cw
        if 0.2 < h_center < 0.8 and 0.2 < v_center < 0.8:
            return "+"

    # EQUALS "=" — two separate horizontal strokes, no vertical stroke
    if h_strong_segments == 2 and not has_v_peak:
        return "="

    # MINUS "-" — one horizontal stroke, no vertical stroke
    if h_strong_segments == 1 and not has_v_peak:
        # Verify it's centered vertically
        h_peak_rows = np.where(h_strong)[0]
        if len(h_peak_rows) > 0:
            center_ratio = np.mean(h_peak_rows) / ch
            if 0.25 < center_ratio < 0.75:
                return "-"

    # MULTIPLY "×" — no clear h/v peaks, but diagonal strokes
    if not has_h_peak and not has_v_peak and density > 0.05:
        diag_score = _check_diagonal(center)
        if diag_score > 0.4:
            return "×"

    # Also check × with broad h/v coverage but no strong peaks
    if h_weak_count > ch * 0.5 and v_weak_count > cw * 0.5 and not has_h_peak:
        diag_score = _check_diagonal(center)
        if diag_score > 0.3:
            return "×"

    # DIVIDE "÷" — horizontal line with dots above and below
    if has_h_peak and h_strong_segments == 1:
        # Check for dots above and below the line
        h_peak_rows = np.where(h_strong)[0]
        line_center = int(np.mean(h_peak_rows))
        above = center[:max(1, line_center - 2), :]
        below = center[min(ch - 1, line_center + 3):, :]
        above_density = np.sum(above > 0) / max(above.size, 1)
        below_density = np.sum(below > 0) / max(below.size, 1)
        if above_density > 0.02 and below_density > 0.02:
            # Has stuff both above and below the line
            # Check the stuff is dot-like (small clusters)
            if above_density < 0.2 and below_density < 0.2:
                return "÷"

    # DOT "." — very small cluster near bottom
    if density < 0.1 and h_weak_count < ch * 0.3 and v_weak_count < cw * 0.3:
        bottom_half = center[ch // 2:, :]
        top_half = center[:ch // 2, :]
        if np.sum(bottom_half > 0) > np.sum(top_half > 0) * 2:
            return "."

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
