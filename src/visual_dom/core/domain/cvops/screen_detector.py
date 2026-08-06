"""
Screen region detector for camera-captured photos.

Detects the display/app boundary in a photo taken of a screen,
finds the 4 corners, and applies perspective correction to produce
a flat, rectified screenshot for the CV pipeline.

Strategies:
1. Edge-based: Canny edges + Hough lines + intersection points
2. Contour-based: Largest quadrilateral contour in the image
3. Brightness-based: Screen is typically the brightest rectangle
"""

import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class ScreenRegion:
    """Detected screen region in a camera photo."""
    corners: np.ndarray          # 4 corner points [TL, TR, BR, BL], shape (4,2)
    confidence: float            # 0-1 detection confidence
    method: str                  # Detection method used
    rectified: np.ndarray = None # Perspective-corrected image


def detect_screen(
    image: np.ndarray,
    target_width: int = 0,
    target_height: int = 0,
) -> Optional[ScreenRegion]:
    """
    Detect and rectify screen region in a camera photo.

    Args:
        image: BGR camera photo
        target_width: Output width (0 = auto from aspect ratio)
        target_height: Output height (0 = auto from aspect ratio)

    Returns:
        ScreenRegion with rectified image, or None if no screen found
    """
    # Try multiple strategies, pick best
    results = []

    contour_result = _detect_by_contour(image)
    if contour_result:
        results.append(contour_result)

    edge_result = _detect_by_edges(image)
    if edge_result:
        results.append(edge_result)

    brightness_result = _detect_by_brightness(image)
    if brightness_result:
        results.append(brightness_result)

    if not results:
        return None

    # Pick highest confidence
    best = max(results, key=lambda r: r.confidence)

    # Rectify
    best.rectified = _rectify(image, best.corners, target_width, target_height)

    return best


def _detect_by_contour(image: np.ndarray) -> Optional[ScreenRegion]:
    """Find screen as the largest quadrilateral contour."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    # Also try Canny
    edges = cv2.Canny(blurred, 50, 150)

    # Dilate to connect edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    h, w = image.shape[:2]
    image_area = h * w

    # Sort by area, largest first
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for contour in contours[:10]:
        area = cv2.contourArea(contour)

        # Screen should be at least 10% of image and at most 95%
        if area < image_area * 0.10 or area > image_area * 0.95:
            continue

        # Approximate to polygon
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        # Must be a quadrilateral
        if len(approx) == 4:
            corners = _order_corners(approx.reshape(4, 2))
            confidence = min(area / image_area, 0.9)

            # Check it's roughly rectangular (angles close to 90 degrees)
            if _is_roughly_rectangular(corners):
                return ScreenRegion(
                    corners=corners,
                    confidence=confidence,
                    method="contour",
                )

    return None


def _detect_by_edges(image: np.ndarray) -> Optional[ScreenRegion]:
    """Find screen using Hough line detection and intersections."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    h, w = image.shape[:2]

    # Detect lines
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=80,
        minLineLength=min(w, h) // 4,
        maxLineGap=20,
    )

    if lines is None or len(lines) < 4:
        return None

    # Separate horizontal and vertical lines
    h_lines = []
    v_lines = []

    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))

        if angle < 20 or angle > 160:
            h_lines.append(line[0])
        elif 70 < angle < 110:
            v_lines.append(line[0])

    if len(h_lines) < 2 or len(v_lines) < 2:
        return None

    # Find top/bottom horizontal lines and left/right vertical lines
    h_lines_sorted = sorted(h_lines, key=lambda l: (l[1] + l[3]) / 2)
    v_lines_sorted = sorted(v_lines, key=lambda l: (l[0] + l[2]) / 2)

    top_line = h_lines_sorted[0]
    bottom_line = h_lines_sorted[-1]
    left_line = v_lines_sorted[0]
    right_line = v_lines_sorted[-1]

    # Find intersections
    tl = _line_intersection(top_line, left_line)
    tr = _line_intersection(top_line, right_line)
    br = _line_intersection(bottom_line, right_line)
    bl = _line_intersection(bottom_line, left_line)

    if any(p is None for p in [tl, tr, br, bl]):
        return None

    corners = np.array([tl, tr, br, bl], dtype=np.float32)

    # Validate: all corners within image bounds (with margin)
    margin = max(w, h) * 0.05
    if np.any(corners < -margin) or np.any(corners[:, 0] > w + margin) or np.any(corners[:, 1] > h + margin):
        return None

    # Clamp to image bounds
    corners[:, 0] = np.clip(corners[:, 0], 0, w - 1)
    corners[:, 1] = np.clip(corners[:, 1], 0, h - 1)

    # Check area
    area = cv2.contourArea(corners.astype(np.int32))
    if area < h * w * 0.10:
        return None

    return ScreenRegion(
        corners=corners,
        confidence=0.6,
        method="edges",
    )


def _detect_by_brightness(image: np.ndarray) -> Optional[ScreenRegion]:
    """Find screen as the brightest large rectangle."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Threshold to find bright regions (screens are typically bright)
    mean_brightness = np.mean(gray)
    threshold = max(mean_brightness * 1.1, 100)

    _, bright = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY)

    # Morphological close to fill gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)

    # Find contours of bright regions
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Find largest bright contour
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    if area < h * w * 0.10:
        return None

    # Approximate to quadrilateral
    peri = cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

    if len(approx) != 4:
        # Fall back to bounding box
        rect = cv2.minAreaRect(largest)
        box = cv2.boxPoints(rect)
        approx = box.astype(np.int32).reshape(4, 1, 2)

    corners = _order_corners(approx.reshape(4, 2))

    return ScreenRegion(
        corners=corners,
        confidence=0.5,
        method="brightness",
    )


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order corners as [top-left, top-right, bottom-right, bottom-left]."""
    pts = pts.astype(np.float32)

    # Sort by y coordinate
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()

    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[np.argmin(s)]   # top-left: smallest x+y
    ordered[2] = pts[np.argmax(s)]   # bottom-right: largest x+y
    ordered[1] = pts[np.argmin(d)]   # top-right: smallest x-y
    ordered[3] = pts[np.argmax(d)]   # bottom-left: largest x-y

    return ordered


def _is_roughly_rectangular(corners: np.ndarray, angle_tolerance: float = 30) -> bool:
    """Check if 4 corners form a roughly rectangular shape."""
    for i in range(4):
        p1 = corners[i]
        p2 = corners[(i + 1) % 4]
        p3 = corners[(i + 2) % 4]

        v1 = p1 - p2
        v2 = p3 - p2

        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
        angle = np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))

        if abs(angle - 90) > angle_tolerance:
            return False

    return True


def _line_intersection(
    line1: np.ndarray, line2: np.ndarray
) -> Optional[Tuple[float, float]]:
    """Find intersection point of two line segments."""
    x1, y1, x2, y2 = line1.astype(float)
    x3, y3, x4, y4 = line2.astype(float)

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-8:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom

    ix = x1 + t * (x2 - x1)
    iy = y1 + t * (y2 - y1)

    return (ix, iy)


def _rectify(
    image: np.ndarray,
    corners: np.ndarray,
    target_width: int = 0,
    target_height: int = 0,
) -> np.ndarray:
    """Apply perspective correction to extract the screen region."""
    tl, tr, br, bl = corners

    # Compute output dimensions from corner distances
    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)

    out_w = target_width or int(max(width_top, width_bottom))
    out_h = target_height or int(max(height_left, height_right))

    # Destination corners
    dst = np.array([
        [0, 0],
        [out_w - 1, 0],
        [out_w - 1, out_h - 1],
        [0, out_h - 1],
    ], dtype=np.float32)

    # Perspective transform
    M = cv2.getPerspectiveTransform(corners, dst)
    rectified = cv2.warpPerspective(image, M, (out_w, out_h))

    return rectified
