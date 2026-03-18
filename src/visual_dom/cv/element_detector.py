"""
Non-text UI element detection module.

This module provides a high-level interface for UI element detection.
It wraps the UIED-style coarse-to-fine detection strategy.

For the full pipeline (text + non-text), use VisualDOMPipeline instead.
"""

import cv2
import numpy as np
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional, Union

from .uied_detection import UIEDDetector, DetectedElement, ElementType
from .image_processing import calculate_iou, non_max_suppression


class VisualType(Enum):
    """Coarse visual type classification."""
    BUTTON = "button"
    ICON = "icon"
    INPUT_FIELD = "input_field"
    CHECKBOX = "checkbox"
    CONTAINER = "container"
    IMAGE = "image"
    TEXT = "text"
    DIVIDER = "divider"
    UNKNOWN = "unknown"


@dataclass
class UIElement:
    """Detected UI element with bounding box and visual type."""
    id: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    visual_type: VisualType
    confidence: float
    ocr_text: Optional[str] = None

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "bounds": list(self.bounds),
            "visual_type": self.visual_type.value,
            "confidence": self.confidence,
        }
        if self.ocr_text:
            result["ocr_text"] = self.ocr_text
        return result


class ElementDetector:
    """
    Detect non-text UI elements in GUI screenshots.

    Uses UIED-style coarse-to-fine detection:
    1. Detect large blocks/containers (coarse)
    2. Detect elements within blocks (fine)
    3. Detect special elements (inputs, buttons, checkboxes)
    4. Merge and deduplicate results
    """

    def __init__(
        self,
        use_deep_learning: bool = False,
        model_path: Optional[str] = None,
        min_element_area: int = 100,
        confidence_threshold: float = 0.3,
    ):
        """
        Initialize element detector.

        Args:
            use_deep_learning: Use YOLO model instead of traditional CV
            model_path: Path to YOLO model (if use_deep_learning=True)
            min_element_area: Minimum element area in pixels
            confidence_threshold: Minimum confidence to keep detections
        """
        self.use_deep_learning = use_deep_learning
        self.model_path = model_path
        self.min_element_area = min_element_area
        self.confidence_threshold = confidence_threshold

        self._uied_detector = None
        self._yolo_model = None

    def _init_detector(self):
        """Initialize the appropriate detector."""
        if self.use_deep_learning:
            self._init_yolo()
        else:
            self._init_uied()

    def _init_uied(self):
        """Initialize UIED-style detector."""
        if self._uied_detector is None:
            self._uied_detector = UIEDDetector(
                min_element_area=self.min_element_area,
            )

    def _init_yolo(self):
        """Initialize YOLO detector."""
        if self._yolo_model is None:
            if not self.model_path:
                raise ValueError("model_path required for deep learning mode")

            try:
                from ultralytics import YOLO
                self._yolo_model = YOLO(self.model_path)
            except ImportError:
                raise ImportError("ultralytics not installed. Run: pip install ultralytics")

    def detect(self, image: Union[np.ndarray, str]) -> List[UIElement]:
        """
        Detect UI elements in an image.

        Args:
            image: numpy array (BGR) or path to image file

        Returns:
            List of UIElement with bounding boxes and visual types
        """
        # Load image if path
        if isinstance(image, str):
            image = cv2.imread(image)

        if image is None:
            raise ValueError("Could not load image")

        self._init_detector()

        if self.use_deep_learning:
            return self._detect_yolo(image)
        else:
            return self._detect_uied(image)

    def _detect_uied(self, image: np.ndarray) -> List[UIElement]:
        """Detect using UIED-style traditional CV."""
        detected = self._uied_detector.detect(image)

        # Convert to UIElement format
        elements = []
        for det in detected:
            # Map ElementType to VisualType
            vtype = self._map_element_type(det.element_type)

            if det.confidence >= self.confidence_threshold:
                elements.append(UIElement(
                    id=det.id,
                    bounds=det.bounds,
                    visual_type=vtype,
                    confidence=det.confidence,
                    ocr_text=det.text,
                ))

        return elements

    def _detect_yolo(self, image: np.ndarray) -> List[UIElement]:
        """Detect using YOLO model."""
        from models.configs.cv_model_registry import UI_ELEMENT_CLASSES

        results = self._yolo_model(image, conf=self.confidence_threshold, verbose=False)

        elements = []
        for i, result in enumerate(results):
            boxes = result.boxes

            for j, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())

                # Map class to VisualType
                if cls_id < len(UI_ELEMENT_CLASSES):
                    class_name = UI_ELEMENT_CLASSES[cls_id]
                    vtype = self._map_class_name(class_name)
                else:
                    vtype = VisualType.UNKNOWN

                elements.append(UIElement(
                    id=f"E{len(elements) + 1}",
                    bounds=(int(x1), int(y1), int(x2), int(y2)),
                    visual_type=vtype,
                    confidence=conf,
                ))

        return elements

    def _map_element_type(self, elem_type: ElementType) -> VisualType:
        """Map ElementType to VisualType."""
        mapping = {
            ElementType.BLOCK: VisualType.CONTAINER,
            ElementType.BUTTON: VisualType.BUTTON,
            ElementType.TEXT: VisualType.TEXT,
            ElementType.ICON: VisualType.ICON,
            ElementType.INPUT_FIELD: VisualType.INPUT_FIELD,
            ElementType.CHECKBOX: VisualType.CHECKBOX,
            ElementType.IMAGE: VisualType.IMAGE,
            ElementType.DIVIDER: VisualType.DIVIDER,
            ElementType.UNKNOWN: VisualType.UNKNOWN,
        }
        return mapping.get(elem_type, VisualType.UNKNOWN)

    def _map_class_name(self, class_name: str) -> VisualType:
        """Map YOLO class name to VisualType."""
        mapping = {
            "button": VisualType.BUTTON,
            "text": VisualType.TEXT,
            "icon": VisualType.ICON,
            "input_field": VisualType.INPUT_FIELD,
            "checkbox": VisualType.CHECKBOX,
            "radio_button": VisualType.CHECKBOX,
            "toggle": VisualType.CHECKBOX,
            "slider": VisualType.INPUT_FIELD,
            "dropdown": VisualType.INPUT_FIELD,
            "image": VisualType.IMAGE,
            "container": VisualType.CONTAINER,
            "toolbar": VisualType.CONTAINER,
            "navbar": VisualType.CONTAINER,
            "card": VisualType.CONTAINER,
            "list_item": VisualType.CONTAINER,
        }
        return mapping.get(class_name.lower(), VisualType.UNKNOWN)

    def merge_with_text(
        self,
        elements: List[UIElement],
        text_elements: List
    ) -> List[UIElement]:
        """
        Merge element detections with text detections using NMS/IoU.

        Args:
            elements: Detected UI elements
            text_elements: Detected text elements (TextElement objects)

        Returns:
            Merged and deduplicated list of elements
        """
        merged = list(elements)

        # For each text element, check if it overlaps with existing elements
        for text_elem in text_elements:
            overlaps = False

            for elem in elements:
                iou = calculate_iou(elem.bounds, text_elem.bounds)
                if iou > 0.3:
                    # Text overlaps with element, attach text
                    if not elem.ocr_text:
                        elem.ocr_text = text_elem.text
                    overlaps = True
                    break

            # If no overlap, add as new text element
            if not overlaps:
                merged.append(UIElement(
                    id=f"T{len(merged) + 1}",
                    bounds=text_elem.bounds,
                    visual_type=VisualType.TEXT,
                    confidence=text_elem.confidence,
                    ocr_text=text_elem.text,
                ))

        return merged
