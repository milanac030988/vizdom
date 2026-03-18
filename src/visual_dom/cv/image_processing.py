"""
Image processing utilities for UI element detection.

Based on UIED paper's approach:
- Preprocessing (grayscale, binary, gradient)
- Edge detection and contour finding
- Morphological operations for noise reduction
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional
from dataclasses import dataclass


@dataclass
class ProcessedImage:
    """Container for processed image variants."""
    original: np.ndarray      # Original BGR image
    gray: np.ndarray          # Grayscale
    binary: np.ndarray        # Binary (thresholded)
    edges: np.ndarray         # Canny edges
    gradient: np.ndarray      # Gradient magnitude
    height: int
    width: int


def preprocess_image(image: np.ndarray) -> ProcessedImage:
    """
    Preprocess image for UI element detection.

    Args:
        image: BGR image (numpy array)

    Returns:
        ProcessedImage with multiple representations
    """
    if len(image.shape) == 2:
        # Already grayscale
        gray = image
        original = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        original = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    height, width = gray.shape[:2]

    # Adaptive binary thresholding (handles varying backgrounds)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=11,
        C=2
    )

    # Canny edge detection
    edges = cv2.Canny(gray, 30, 100)

    # Gradient magnitude (Sobel)
    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    gradient = np.sqrt(grad_x**2 + grad_y**2).astype(np.uint8)

    return ProcessedImage(
        original=original,
        gray=gray,
        binary=binary,
        edges=edges,
        gradient=gradient,
        height=height,
        width=width
    )


def find_contours(
    binary_image: np.ndarray,
    min_area: int = 100,
    max_area_ratio: float = 0.9
) -> List[np.ndarray]:
    """
    Find contours in binary image with area filtering.

    Args:
        binary_image: Binary (thresholded) image
        min_area: Minimum contour area in pixels
        max_area_ratio: Maximum contour area as ratio of image area

    Returns:
        List of contours (each is numpy array of points)
    """
    contours, _ = cv2.findContours(
        binary_image,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_SIMPLE
    )

    image_area = binary_image.shape[0] * binary_image.shape[1]
    max_area = image_area * max_area_ratio

    filtered = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if min_area <= area <= max_area:
            filtered.append(contour)

    return filtered


def contour_to_bbox(contour: np.ndarray) -> Tuple[int, int, int, int]:
    """Convert contour to bounding box (x1, y1, x2, y2)."""
    x, y, w, h = cv2.boundingRect(contour)
    return (x, y, x + w, y + h)


def merge_close_bboxes(
    bboxes: List[Tuple[int, int, int, int]],
    distance_threshold: int = 5
) -> List[Tuple[int, int, int, int]]:
    """
    Merge bounding boxes that are close to each other.

    Args:
        bboxes: List of (x1, y1, x2, y2) bounding boxes
        distance_threshold: Max distance between boxes to merge

    Returns:
        Merged bounding boxes
    """
    if not bboxes:
        return []

    # Convert to list for modification
    boxes = list(bboxes)
    merged = True

    while merged:
        merged = False
        i = 0
        while i < len(boxes):
            j = i + 1
            while j < len(boxes):
                if _should_merge(boxes[i], boxes[j], distance_threshold):
                    # Merge boxes
                    boxes[i] = _merge_two_boxes(boxes[i], boxes[j])
                    boxes.pop(j)
                    merged = True
                else:
                    j += 1
            i += 1

    return boxes


def _should_merge(
    box1: Tuple[int, int, int, int],
    box2: Tuple[int, int, int, int],
    threshold: int
) -> bool:
    """Check if two boxes should be merged based on distance."""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    # Check horizontal distance
    h_dist = max(0, max(x1_1, x1_2) - min(x2_1, x2_2))
    # Check vertical distance
    v_dist = max(0, max(y1_1, y1_2) - min(y2_1, y2_2))

    return h_dist <= threshold and v_dist <= threshold


def _merge_two_boxes(
    box1: Tuple[int, int, int, int],
    box2: Tuple[int, int, int, int]
) -> Tuple[int, int, int, int]:
    """Merge two bounding boxes into one encompassing box."""
    return (
        min(box1[0], box2[0]),
        min(box1[1], box2[1]),
        max(box1[2], box2[2]),
        max(box1[3], box2[3])
    )


def calculate_iou(
    box1: Tuple[int, int, int, int],
    box2: Tuple[int, int, int, int]
) -> float:
    """
    Calculate Intersection over Union between two boxes.

    Args:
        box1, box2: Bounding boxes as (x1, y1, x2, y2)

    Returns:
        IoU value between 0 and 1
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)

    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def non_max_suppression(
    boxes: List[Tuple[int, int, int, int]],
    scores: List[float],
    iou_threshold: float = 0.5
) -> List[int]:
    """
    Non-Maximum Suppression to remove overlapping boxes.

    Args:
        boxes: List of (x1, y1, x2, y2) bounding boxes
        scores: Confidence scores for each box
        iou_threshold: IoU threshold for suppression

    Returns:
        Indices of boxes to keep
    """
    if not boxes:
        return []

    # Sort by score (descending)
    indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    keep = []
    while indices:
        current = indices[0]
        keep.append(current)

        if len(indices) == 1:
            break

        # Remove current from indices
        indices = indices[1:]

        # Filter out boxes with high IoU overlap
        remaining = []
        for i in indices:
            iou = calculate_iou(boxes[current], boxes[i])
            if iou < iou_threshold:
                remaining.append(i)

        indices = remaining

    return keep


def is_contained(
    inner: Tuple[int, int, int, int],
    outer: Tuple[int, int, int, int],
    threshold: float = 0.8
) -> bool:
    """
    Check if inner box is contained within outer box.

    Args:
        inner: Inner bounding box (x1, y1, x2, y2)
        outer: Outer bounding box (x1, y1, x2, y2)
        threshold: Minimum overlap ratio to consider contained

    Returns:
        True if inner is contained within outer
    """
    # Calculate intersection
    x1 = max(inner[0], outer[0])
    y1 = max(inner[1], outer[1])
    x2 = min(inner[2], outer[2])
    y2 = min(inner[3], outer[3])

    if x2 <= x1 or y2 <= y1:
        return False

    intersection = (x2 - x1) * (y2 - y1)
    inner_area = (inner[2] - inner[0]) * (inner[3] - inner[1])

    if inner_area == 0:
        return False

    return (intersection / inner_area) >= threshold


def detect_lines(
    edges: np.ndarray,
    min_length: int = 50
) -> Tuple[List[Tuple], List[Tuple]]:
    """
    Detect horizontal and vertical lines using Hough transform.

    Args:
        edges: Edge image (from Canny)
        min_length: Minimum line length

    Returns:
        Tuple of (horizontal_lines, vertical_lines)
    """
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi/180,
        threshold=50,
        minLineLength=min_length,
        maxLineGap=10
    )

    horizontal = []
    vertical = []

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]

            # Calculate angle
            if x2 - x1 == 0:
                angle = 90
            else:
                angle = abs(np.arctan((y2 - y1) / (x2 - x1)) * 180 / np.pi)

            if angle < 10:  # Horizontal
                horizontal.append((x1, y1, x2, y2))
            elif angle > 80:  # Vertical
                vertical.append((x1, y1, x2, y2))

    return horizontal, vertical
