"""
UIED-inspired coarse-to-fine UI element detection.

Based on the paper:
"Object Detection for Graphical User Interface: Old Fashioned or Deep Learning or a Combination?"

Strategy:
1. COARSE: Detect large blocks/containers first
2. FINE: Detect elements within each block
3. MERGE: Combine with text detection results
4. CLASSIFY: Assign element types
"""

import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum

from visual_dom.core.domain.cvops.image_processing import (
    preprocess_image,
    ProcessedImage,
    ColorFeatures,
    extract_color_features,
    find_contours,
    contour_to_bbox,
    merge_close_bboxes,
    calculate_iou,
    non_max_suppression,
    is_contained,
    detect_lines,
)


class ElementType(Enum):
    """UI element types for classification."""
    BLOCK = "block"           # Container/layout block
    BUTTON = "button"
    TEXT = "text"
    ICON = "icon"
    INPUT_FIELD = "input_field"
    CHECKBOX = "checkbox"
    IMAGE = "image"
    DIVIDER = "divider"
    UNKNOWN = "unknown"


@dataclass
class DetectedElement:
    """A detected UI element."""
    id: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    element_type: ElementType
    confidence: float
    text: Optional[str] = None
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    features: Dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> Tuple[int, int]:
        return (
            (self.bounds[0] + self.bounds[2]) // 2,
            (self.bounds[1] + self.bounds[3]) // 2
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "bounds": list(self.bounds),
            "visual_type": self.element_type.value,
            "confidence": self.confidence,
            "ocr_text": self.text,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
        }


class UIEDDetector:
    """
    UIED-style coarse-to-fine UI element detector.

    Pipeline:
    1. Preprocess image
    2. Detect blocks (coarse)
    3. Detect elements within blocks (fine)
    4. Detect special elements (inputs, buttons)
    5. Merge all detections
    6. Build containment hierarchy
    """

    # Reference height for threshold scaling (1080p)
    REFERENCE_HEIGHT = 1080

    def __init__(
        self,
        min_element_area: int = 100,
        min_block_area: int = 1000,
        block_padding: int = 3,
        merge_distance: int = 5,
        nms_threshold: float = 0.5,
    ):
        """
        Initialize UIED detector.

        Args:
            min_element_area: Minimum area for elements (at 1080p reference)
            min_block_area: Minimum area for blocks (at 1080p reference)
            block_padding: Padding when extracting block regions
            merge_distance: Distance threshold for merging close boxes
            nms_threshold: IoU threshold for NMS
        """
        self.min_element_area = min_element_area
        self.min_block_area = min_block_area
        self.block_padding = block_padding
        self.merge_distance = merge_distance
        self.nms_threshold = nms_threshold

        self._element_counter = 0
        self._scale = 1.0

    def _next_id(self, prefix: str = "E") -> str:
        """Generate next element ID."""
        self._element_counter += 1
        return f"{prefix}{self._element_counter}"

    def _scaled(self, value: float) -> float:
        """Scale a pixel value relative to current image resolution."""
        return value * self._scale

    def _scaled_area(self, value: float) -> float:
        """Scale an area value (pixels squared) relative to current image resolution."""
        return value * self._scale * self._scale

    def detect(self, image: np.ndarray) -> List[DetectedElement]:
        """
        Detect UI elements using coarse-to-fine strategy.

        Args:
            image: BGR image (numpy array)

        Returns:
            List of detected elements with hierarchy
        """
        self._element_counter = 0

        # Compute scale factor relative to 1080p reference
        # Clamp to minimum 1.0 so small images keep original thresholds
        self._scale = max(1.0, image.shape[0] / self.REFERENCE_HEIGHT)

        # Step 1: Preprocess
        processed = preprocess_image(image)

        # Step 2: Detect blocks (COARSE)
        blocks = self._detect_blocks(processed)

        # Step 3: Detect elements within blocks (FINE)
        elements = self._detect_elements_in_blocks(processed, blocks)

        # Step 4: Detect special elements
        special = self._detect_special_elements(processed)

        # Step 5: Merge all detections
        all_elements = blocks + elements + special
        merged = self._merge_detections(all_elements)

        # Step 6: Build hierarchy
        result = self._build_hierarchy(merged)

        return result

    def _detect_blocks(self, processed: ProcessedImage) -> List[DetectedElement]:
        """
        COARSE detection: Find large UI blocks/containers.

        Uses flood-fill on background to find block boundaries.
        """
        blocks = []

        # Method 1: Connected component analysis on inverted binary
        binary_inv = 255 - processed.binary

        # Morphological closing to connect nearby components
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(binary_inv, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours = find_contours(
            closed,
            min_area=int(self._scaled_area(self.min_block_area)),
            max_area_ratio=0.95
        )

        for contour in contours:
            bbox = contour_to_bbox(contour)

            # Filter by aspect ratio (blocks shouldn't be too thin)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 100

            if aspect_ratio < 20:  # Not a line/divider
                blocks.append(DetectedElement(
                    id=self._next_id("B"),
                    bounds=bbox,
                    element_type=ElementType.BLOCK,
                    confidence=0.8,
                    features={"source": "block_detection"}
                ))

        # Method 2: Horizontal/vertical line detection for dividers
        h_lines, v_lines = detect_lines(processed.edges, min_length=100)

        # Group lines to find block boundaries
        # (This helps identify card-like containers)

        return blocks

    def _detect_elements_in_blocks(
        self,
        processed: ProcessedImage,
        blocks: List[DetectedElement]
    ) -> List[DetectedElement]:
        """
        FINE detection: Find elements within each block.

        For each block, analyze its interior for smaller elements.
        """
        elements = []

        # If no blocks found, treat entire image as one block
        if not blocks:
            blocks = [DetectedElement(
                id="B0",
                bounds=(0, 0, processed.width, processed.height),
                element_type=ElementType.BLOCK,
                confidence=1.0
            )]

        for block in blocks:
            x1, y1, x2, y2 = block.bounds

            # Add padding
            x1 = max(0, x1 - self.block_padding)
            y1 = max(0, y1 - self.block_padding)
            x2 = min(processed.width, x2 + self.block_padding)
            y2 = min(processed.height, y2 + self.block_padding)

            # Extract region
            region_binary = processed.binary[y1:y2, x1:x2]
            region_gray = processed.gray[y1:y2, x1:x2]

            if region_binary.size == 0:
                continue

            # Find contours in region
            contours = find_contours(
                region_binary,
                min_area=int(self._scaled_area(self.min_element_area)),
                max_area_ratio=0.8
            )

            for contour in contours:
                bbox = contour_to_bbox(contour)

                # Adjust to global coordinates
                global_bbox = (
                    bbox[0] + x1,
                    bbox[1] + y1,
                    bbox[2] + x1,
                    bbox[3] + y1
                )

                # Classify element based on features
                elem_type, confidence = self._classify_element(
                    processed, global_bbox
                )

                elements.append(DetectedElement(
                    id=self._next_id("E"),
                    bounds=global_bbox,
                    element_type=elem_type,
                    confidence=confidence,
                    parent_id=block.id,
                    features={"source": "fine_detection"}
                ))

        return elements

    def _detect_special_elements(
        self,
        processed: ProcessedImage
    ) -> List[DetectedElement]:
        """
        Detect special UI elements with specific visual patterns.

        - Input fields: rectangular with border
        - Buttons: rectangular with background color
        - Checkboxes: small squares
        - Icons: small, roughly square shapes
        """
        special = []

        # Detect rectangles (potential inputs/buttons)
        rectangles = self._detect_rectangles(processed)

        for rect_bbox, rect_type in rectangles:
            if rect_type == "input":
                elem_type = ElementType.INPUT_FIELD
            elif rect_type == "button":
                elem_type = ElementType.BUTTON
            elif rect_type == "checkbox":
                elem_type = ElementType.CHECKBOX
            else:
                continue

            special.append(DetectedElement(
                id=self._next_id("S"),
                bounds=rect_bbox,
                element_type=elem_type,
                confidence=0.7,
                features={"source": "special_detection", "rect_type": rect_type}
            ))

        return special

    def _detect_rectangles(
        self,
        processed: ProcessedImage
    ) -> List[Tuple[Tuple[int, int, int, int], str]]:
        """
        Detect rectangular UI elements.

        Returns list of (bbox, type) where type is 'input', 'button', or 'checkbox'.
        """
        rectangles = []

        # Find contours on edge image
        contours, _ = cv2.findContours(
            processed.edges,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:
            # Approximate contour to polygon
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # Check if it's a rectangle (4 vertices)
            if len(approx) == 4:
                bbox = contour_to_bbox(contour)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                area = w * h

                if area < self._scaled_area(self.min_element_area):
                    continue

                aspect_ratio = w / h if h > 0 else 0

                # Classify rectangle type (thresholds scaled to resolution)
                cb_min = self._scaled(15)
                cb_max = self._scaled(30)
                input_max_h = self._scaled(60)
                btn_max_area = self._scaled_area(50000)

                if cb_min <= w <= cb_max and cb_min <= h <= cb_max:
                    # Small square: checkbox
                    rect_type = "checkbox"
                elif aspect_ratio > 2.5 and h < input_max_h:
                    # Wide and short: input field
                    rect_type = "input"
                elif 0.5 < aspect_ratio < 4 and area < btn_max_area:
                    # Medium rectangle: button
                    rect_type = "button"
                else:
                    continue

                rectangles.append((bbox, rect_type))

        return rectangles

    def _classify_element(
        self,
        processed: ProcessedImage,
        bbox: Tuple[int, int, int, int]
    ) -> Tuple[ElementType, float]:
        """
        Classify element type based on visual features.

        Uses fast grayscale/edge features first, then color features
        only when needed to resolve ambiguous cases.

        Args:
            processed: Processed image
            bbox: Element bounding box

        Returns:
            Tuple of (element_type, confidence)
        """
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        area = w * h
        aspect_ratio = w / h if h > 0 else 1

        # Extract region
        region = processed.gray[y1:y2, x1:x2]
        if region.size == 0:
            return ElementType.UNKNOWN, 0.5

        # Fast grayscale features (always computed)
        std_intensity = np.std(region)
        edge_density = np.sum(processed.edges[y1:y2, x1:x2] > 0) / max(area, 1)

        # Classification rules (all pixel thresholds scaled to resolution)

        # Thin horizontal element: divider
        if aspect_ratio > 10 and h < self._scaled(10):
            return ElementType.DIVIDER, 0.7

        # Small square with high edge density: icon or checkbox
        icon_min = self._scaled(10)
        icon_max = self._scaled(50)
        if icon_min <= w <= icon_max and icon_min <= h <= icon_max and 0.7 < aspect_ratio < 1.4:
            if edge_density > 0.3:
                return ElementType.ICON, 0.7
            else:
                return ElementType.CHECKBOX, 0.6

        # Wide rectangle with border: input field
        if aspect_ratio > 3 and h < self._scaled(80) and edge_density > 0.1:
            return ElementType.INPUT_FIELD, 0.7

        # Medium rectangle with distinct background: button
        if self._scaled_area(1000) < area < self._scaled_area(30000) and 0.3 < aspect_ratio < 5:
            if std_intensity < 30:  # Uniform color (button background)
                return ElementType.BUTTON, 0.6
            # Ambiguous — use color to refine
            color = extract_color_features(processed.original, bbox)
            if color.is_uniform and color.bg_contrast > 20:
                return ElementType.BUTTON, 0.7

        # Large area: block/container
        if area > self._scaled_area(50000):
            return ElementType.BLOCK, 0.8

        # Default: unknown
        return ElementType.UNKNOWN, 0.5

    def _merge_detections(
        self,
        elements: List[DetectedElement]
    ) -> List[DetectedElement]:
        """
        Merge overlapping detections using NMS.
        """
        if not elements:
            return []

        # Group by element type
        type_groups: Dict[ElementType, List[DetectedElement]] = {}
        for elem in elements:
            if elem.element_type not in type_groups:
                type_groups[elem.element_type] = []
            type_groups[elem.element_type].append(elem)

        merged = []

        for elem_type, group in type_groups.items():
            boxes = [e.bounds for e in group]
            scores = [e.confidence for e in group]

            # Apply NMS
            keep_indices = non_max_suppression(
                boxes, scores, self.nms_threshold
            )

            for idx in keep_indices:
                merged.append(group[idx])

        # Merge close boxes of same type
        final = []
        processed_ids = set()

        for elem in merged:
            if elem.id in processed_ids:
                continue

            # Find close elements of same type
            close_elements = [elem]
            for other in merged:
                if other.id != elem.id and other.id not in processed_ids:
                    if other.element_type == elem.element_type:
                        # Check distance
                        dist = self._box_distance(elem.bounds, other.bounds)
                        if dist < self.merge_distance:
                            close_elements.append(other)
                            processed_ids.add(other.id)

            # Merge if multiple close elements
            if len(close_elements) > 1:
                merged_bbox = self._merge_boxes([e.bounds for e in close_elements])
                avg_conf = sum(e.confidence for e in close_elements) / len(close_elements)

                final.append(DetectedElement(
                    id=elem.id,
                    bounds=merged_bbox,
                    element_type=elem.element_type,
                    confidence=avg_conf,
                    features={"merged_count": len(close_elements)}
                ))
            else:
                final.append(elem)

            processed_ids.add(elem.id)

        return final

    def _box_distance(
        self,
        box1: Tuple[int, int, int, int],
        box2: Tuple[int, int, int, int]
    ) -> float:
        """Calculate minimum distance between two boxes."""
        # Check if overlapping
        if calculate_iou(box1, box2) > 0:
            return 0

        # Calculate edge-to-edge distance
        h_dist = max(0, max(box1[0], box2[0]) - min(box1[2], box2[2]))
        v_dist = max(0, max(box1[1], box2[1]) - min(box1[3], box2[3]))

        return max(h_dist, v_dist)

    def _merge_boxes(
        self,
        boxes: List[Tuple[int, int, int, int]]
    ) -> Tuple[int, int, int, int]:
        """Merge multiple boxes into one encompassing box."""
        x1 = min(b[0] for b in boxes)
        y1 = min(b[1] for b in boxes)
        x2 = max(b[2] for b in boxes)
        y2 = max(b[3] for b in boxes)
        return (x1, y1, x2, y2)

    def _build_hierarchy(
        self,
        elements: List[DetectedElement]
    ) -> List[DetectedElement]:
        """
        Build parent-child hierarchy based on containment.

        Larger elements that contain smaller ones become parents.
        """
        # Sort by area (largest first)
        sorted_elements = sorted(elements, key=lambda e: e.area, reverse=True)

        # Build containment relationships
        for i, elem in enumerate(sorted_elements):
            for j in range(i + 1, len(sorted_elements)):
                child = sorted_elements[j]

                if child.parent_id is None:
                    if is_contained(child.bounds, elem.bounds, threshold=0.8):
                        child.parent_id = elem.id
                        elem.children_ids.append(child.id)

        return sorted_elements


def detect_ui_elements(
    image: np.ndarray,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function to detect UI elements.

    Args:
        image: BGR image (numpy array) or path to image
        **kwargs: Arguments passed to UIEDDetector

    Returns:
        List of element dictionaries
    """
    if isinstance(image, str):
        image = cv2.imread(image)

    detector = UIEDDetector(**kwargs)
    elements = detector.detect(image)

    return [e.to_dict() for e in elements]
