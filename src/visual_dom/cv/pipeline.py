"""
Visual DOM CV Pipeline

Combines UIED-style coarse-to-fine detection with OCR to produce
a complete list of UI elements with bounding boxes.

Pipeline:
1. Text Detection (OCR) - EasyOCR/PaddleOCR
2. Non-text Detection (UIED) - Coarse blocks → Fine elements
3. Merge & Deduplicate - NMS, containment filtering
4. Output: List of elements ready for hierarchy building
"""

import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple
from enum import Enum

from .text_detector import TextDetector, TextElement
from .uied_detection import UIEDDetector, DetectedElement, ElementType
from .image_processing import calculate_iou, non_max_suppression, is_contained


@dataclass
class UIElement:
    """Unified UI element from CV pipeline."""
    id: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    visual_type: str
    confidence: float
    ocr_text: Optional[str] = None
    source: str = "unknown"  # "text", "uied", "merged"
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

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
        result = {
            "id": self.id,
            "bounds": list(self.bounds),
            "visual_type": self.visual_type,
            "confidence": round(self.confidence, 3),
        }
        if self.ocr_text:
            result["ocr_text"] = self.ocr_text
        if self.parent_id:
            result["parent_id"] = self.parent_id
        if self.children_ids:
            result["children_ids"] = self.children_ids
        return result


class VisualDOMPipeline:
    """
    Complete CV pipeline for Visual DOM generation.

    Combines:
    - Text detection (OCR)
    - UIED-style non-text element detection
    - Merging and deduplication
    - Containment-based hierarchy
    """

    # Reference height for threshold scaling (1080p)
    REFERENCE_HEIGHT = 1080

    def __init__(
        self,
        ocr_engine: str = "easyocr",
        ocr_languages: List[str] = None,
        use_gpu: bool = True,
        confidence_threshold: float = 0.3,
        iou_threshold: float = 0.5,
        min_element_area: int = 100,
        min_element_size: int = 10,
        max_elements: int = 200,
    ):
        """
        Initialize CV pipeline.

        Args:
            ocr_engine: OCR backend ("easyocr", "paddleocr", "tesseract")
            ocr_languages: Languages for OCR
            use_gpu: Use GPU acceleration
            confidence_threshold: Minimum confidence to keep detections (default: 0.3)
            iou_threshold: IoU threshold for NMS (default: 0.5)
            min_element_area: Minimum element area in pixels at 1080p (default: 100)
            min_element_size: Minimum width/height in pixels at 1080p (default: 10)
            max_elements: Maximum number of elements to return (default: 200)
        """
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.min_element_area = min_element_area
        self.min_element_size = min_element_size
        self.max_elements = max_elements

        # Initialize detectors
        self.text_detector = TextDetector(
            ocr_engine=ocr_engine,
            languages=ocr_languages or ["en"],
            confidence_threshold=confidence_threshold,
            gpu=use_gpu
        )

        self.uied_detector = UIEDDetector(
            min_element_area=min_element_area,
            nms_threshold=iou_threshold,
        )

        self._element_counter = 0
        self._scale = 1.0

    def _next_id(self) -> str:
        """Generate next element ID."""
        self._element_counter += 1
        return f"E{self._element_counter}"

    def _scaled(self, value: float) -> float:
        """Scale a pixel value relative to current image resolution."""
        return value * self._scale

    def _scaled_area(self, value: float) -> float:
        """Scale an area value (pixels squared) relative to current image resolution."""
        return value * self._scale * self._scale

    def process(
        self,
        image: Union[np.ndarray, str],
        detect_text: bool = True,
        detect_elements: bool = True,
    ) -> Dict[str, Any]:
        """
        Process image through complete CV pipeline.

        Args:
            image: BGR image (numpy array) or path to image file
            detect_text: Run text detection
            detect_elements: Run UIED element detection

        Returns:
            Dictionary with:
            - "elements": List of detected elements
            - "image_size": (width, height)
            - "stats": Detection statistics
        """
        self._element_counter = 0

        # Load image if path
        if isinstance(image, str):
            image = cv2.imread(image)

        if image is None:
            raise ValueError("Could not load image")

        height, width = image.shape[:2]

        # Compute scale factor relative to 1080p reference
        # Clamp to minimum 1.0 so small images keep original thresholds
        self._scale = max(1.0, height / self.REFERENCE_HEIGHT)

        all_elements: List[UIElement] = []

        # Step 1: Text Detection
        text_elements = []
        if detect_text:
            try:
                text_results = self.text_detector.detect(image)
                text_elements = self._convert_text_elements(text_results)
                all_elements.extend(text_elements)
            except Exception as e:
                print(f"Warning: Text detection failed: {e}")

        # Step 2: UIED Element Detection
        uied_elements = []
        if detect_elements:
            try:
                uied_results = self.uied_detector.detect(image)
                uied_elements = self._convert_uied_elements(uied_results)
            except Exception as e:
                print(f"Warning: UIED detection failed: {e}")

        # Step 3: Re-scan merged regions (elements with multiple texts)
        if text_elements and uied_elements:
            uied_elements = self._rescan_merged_regions(
                image, text_elements, uied_elements
            )

        # Step 4: Merge text and non-text detections
        merged_elements = self._merge_text_and_elements(
            text_elements, uied_elements
        )
        all_elements = merged_elements

        # Step 5: Filter by size and confidence
        all_elements = self._filter_elements(all_elements)

        # Step 5: Apply NMS across all elements (cross-type)
        all_elements = self._apply_cross_type_nms(all_elements)

        # Step 6: Apply per-type NMS
        all_elements = self._apply_nms(all_elements)

        # Step 7: Limit number of elements
        all_elements = self._limit_elements(all_elements)

        # Step 8: Build hierarchy
        all_elements = self._build_hierarchy(all_elements)

        # Step 9: Reassign IDs for clean output
        all_elements = self._reassign_ids(all_elements)

        # Prepare output
        return {
            "elements": [e.to_dict() for e in all_elements],
            "image_size": {"width": width, "height": height},
            "stats": {
                "text_detected": len(text_elements),
                "uied_detected": len(uied_elements),
                "final_count": len(all_elements),
            }
        }

    def _convert_text_elements(
        self,
        text_elements: List[TextElement]
    ) -> List[UIElement]:
        """Convert TextElement to unified UIElement."""
        result = []
        for te in text_elements:
            result.append(UIElement(
                id=self._next_id(),
                bounds=te.bounds,
                visual_type="text",
                confidence=te.confidence,
                ocr_text=te.text,
                source="text"
            ))
        return result

    def _convert_uied_elements(
        self,
        uied_elements: List[DetectedElement]
    ) -> List[UIElement]:
        """Convert DetectedElement to unified UIElement."""
        result = []
        for de in uied_elements:
            result.append(UIElement(
                id=self._next_id(),
                bounds=de.bounds,
                visual_type=de.element_type.value,
                confidence=de.confidence,
                ocr_text=de.text,
                source="uied",
                parent_id=de.parent_id,
                children_ids=de.children_ids.copy(),
            ))
        return result

    def _rescan_merged_regions(
        self,
        image: np.ndarray,
        text_elements: List[UIElement],
        uied_elements: List[UIElement]
    ) -> List[UIElement]:
        """
        Re-scan regions that contain multiple text elements.

        If a UIED element contains multiple OCR texts, it likely merged
        multiple buttons. Re-scan that region with finer detection.
        """
        result = []
        rescan_count = 0

        for uied_elem in uied_elements:
            # Find text elements inside this UIED element
            contained_texts = []
            for text_elem in text_elements:
                if is_contained(text_elem.bounds, uied_elem.bounds, threshold=0.7):
                    contained_texts.append(text_elem)

            # If multiple texts inside, re-scan the region
            if len(contained_texts) >= 2:
                x1, y1, x2, y2 = uied_elem.bounds

                # Extract region from image
                region = image[y1:y2, x1:x2]
                if region.size == 0:
                    result.append(uied_elem)
                    continue

                # Create a fine-grained detector for this region
                fine_detector = UIEDDetector(
                    min_element_area=50,  # Smaller minimum area
                    min_block_area=200,
                    nms_threshold=0.3,    # Stricter NMS
                    merge_distance=2,     # Less merging
                )

                try:
                    # Detect elements in the region
                    sub_elements = fine_detector.detect(region)

                    # If we found more elements than before, use them
                    if len(sub_elements) >= len(contained_texts):
                        rescan_count += 1
                        for sub_elem in sub_elements:
                            # Adjust bounds to global coordinates
                            sx1, sy1, sx2, sy2 = sub_elem.bounds
                            global_bounds = (sx1 + x1, sy1 + y1, sx2 + x1, sy2 + y1)

                            # Find matching text for this sub-element
                            matching_text = None
                            for text_elem in contained_texts:
                                if is_contained(text_elem.bounds, global_bounds, threshold=0.5) or \
                                   calculate_iou(text_elem.bounds, global_bounds) > 0.3:
                                    matching_text = text_elem.ocr_text
                                    break

                            result.append(UIElement(
                                id=self._next_id(),
                                bounds=global_bounds,
                                visual_type=sub_elem.element_type.value,
                                confidence=sub_elem.confidence,
                                ocr_text=matching_text,
                                source="rescan",
                                parent_id=uied_elem.id,
                            ))

                        # Also keep the parent element as container
                        uied_elem.visual_type = "block"
                        result.append(uied_elem)
                        continue

                except Exception as e:
                    pass  # Fall through to keep original element

            # Keep original element
            result.append(uied_elem)

        if rescan_count > 0:
            print(f"  Re-scanned {rescan_count} merged regions")

        return result

    def _merge_text_and_elements(
        self,
        text_elements: List[UIElement],
        uied_elements: List[UIElement]
    ) -> List[UIElement]:
        """
        Merge text detections with UIED detections.

        Strategy:
        - If text overlaps with button/input, attach text to that element
        - If text doesn't overlap, keep as separate text element
        - Keep non-text elements that don't duplicate text boxes
        """
        merged = []
        used_text_ids = set()

        # For each UIED element, check for overlapping text
        for uied_elem in uied_elements:
            overlapping_text = []

            for text_elem in text_elements:
                if text_elem.id in used_text_ids:
                    continue

                iou = calculate_iou(uied_elem.bounds, text_elem.bounds)

                # Check if text is inside the UIED element
                if iou > 0.3 or is_contained(text_elem.bounds, uied_elem.bounds, 0.7):
                    overlapping_text.append(text_elem)
                    used_text_ids.add(text_elem.id)

            # Merge text into UIED element
            if overlapping_text:
                combined_text = " ".join(
                    t.ocr_text for t in overlapping_text if t.ocr_text
                )
                uied_elem.ocr_text = combined_text
                uied_elem.source = "merged"

                # Boost confidence if text confirms element
                if uied_elem.visual_type in ["button", "input_field"]:
                    uied_elem.confidence = min(1.0, uied_elem.confidence + 0.1)

            # Skip pure block elements with no content
            if uied_elem.visual_type == "block" and not overlapping_text:
                # Keep blocks only if they have reasonable size
                if uied_elem.area > self._scaled_area(5000):
                    merged.append(uied_elem)
            else:
                merged.append(uied_elem)

        # Add remaining text elements that weren't merged
        for text_elem in text_elements:
            if text_elem.id not in used_text_ids:
                merged.append(text_elem)

        return merged

    def _filter_elements(self, elements: List[UIElement]) -> List[UIElement]:
        """Filter elements by size and confidence (resolution-aware)."""
        filtered = []
        scaled_min_area = self._scaled_area(self.min_element_area)
        scaled_min_size = self._scaled(self.min_element_size)

        for elem in elements:
            # Skip elements below confidence threshold
            if elem.confidence < self.confidence_threshold:
                continue

            # Skip elements below minimum area
            if elem.area < scaled_min_area:
                # Exception: keep text elements even if small
                if elem.visual_type != "text":
                    continue

            # Skip elements below minimum size
            if elem.width < scaled_min_size or elem.height < scaled_min_size:
                continue

            # Skip very thin elements (likely noise/lines)
            aspect_ratio = max(elem.width, elem.height) / max(min(elem.width, elem.height), 1)
            if aspect_ratio > 20 and elem.visual_type not in ["divider", "text"]:
                continue

            filtered.append(elem)

        return filtered

    def _apply_cross_type_nms(self, elements: List[UIElement]) -> List[UIElement]:
        """Apply NMS across all element types to remove highly overlapping boxes."""
        if not elements:
            return []

        # Sort by confidence (highest first)
        sorted_elements = sorted(elements, key=lambda e: e.confidence, reverse=True)

        keep = []
        suppressed_ids = set()

        for elem in sorted_elements:
            if elem.id in suppressed_ids:
                continue

            keep.append(elem)

            # Check overlap with remaining elements
            for other in sorted_elements:
                if other.id == elem.id or other.id in suppressed_ids:
                    continue

                iou = calculate_iou(elem.bounds, other.bounds)

                # Suppress if high overlap (stricter threshold for cross-type)
                if iou > 0.5:
                    # Keep the one with higher confidence (already sorted)
                    suppressed_ids.add(other.id)

                # Also suppress if one is almost completely inside another
                elif is_contained(other.bounds, elem.bounds, threshold=0.85):
                    # Keep smaller element, suppress larger container if it has no other info
                    if elem.visual_type in ["block", "unknown"] and other.visual_type not in ["block", "unknown"]:
                        pass  # Keep both
                    elif other.area < elem.area * 0.3:
                        pass  # Keep both - significantly different sizes
                    else:
                        suppressed_ids.add(other.id)

        return keep

    def _limit_elements(self, elements: List[UIElement]) -> List[UIElement]:
        """Limit the number of elements returned."""
        if len(elements) <= self.max_elements:
            return elements

        # Sort by confidence and take top N
        sorted_elements = sorted(elements, key=lambda e: e.confidence, reverse=True)

        # But always keep text elements with OCR
        text_with_content = [e for e in sorted_elements if e.visual_type == "text" and e.ocr_text]
        others = [e for e in sorted_elements if e not in text_with_content]

        # Take text elements first, then fill with others
        result = text_with_content[:self.max_elements]
        remaining_slots = self.max_elements - len(result)

        if remaining_slots > 0:
            result.extend(others[:remaining_slots])

        return result

    def _apply_nms(self, elements: List[UIElement]) -> List[UIElement]:
        """Apply Non-Maximum Suppression to remove duplicates within each type."""
        if not elements:
            return []

        # Group by visual type for type-aware NMS
        type_groups: Dict[str, List[UIElement]] = {}
        for elem in elements:
            vtype = elem.visual_type
            if vtype not in type_groups:
                type_groups[vtype] = []
            type_groups[vtype].append(elem)

        result = []

        for vtype, group in type_groups.items():
            boxes = [e.bounds for e in group]
            scores = [e.confidence for e in group]

            keep_indices = non_max_suppression(boxes, scores, self.iou_threshold)

            for idx in keep_indices:
                result.append(group[idx])

        return result

    def _build_hierarchy(self, elements: List[UIElement]) -> List[UIElement]:
        """Build parent-child relationships based on containment."""
        # Sort by area (largest first)
        sorted_elements = sorted(elements, key=lambda e: e.area, reverse=True)

        # Clear existing hierarchy
        for elem in sorted_elements:
            elem.parent_id = None
            elem.children_ids = []

        # Build containment relationships
        for i, elem in enumerate(sorted_elements):
            for j in range(i + 1, len(sorted_elements)):
                child = sorted_elements[j]

                # Skip if child already has a parent
                if child.parent_id is not None:
                    continue

                # Check containment
                if is_contained(child.bounds, elem.bounds, threshold=0.7):
                    child.parent_id = elem.id
                    elem.children_ids.append(child.id)

        return sorted_elements

    def _reassign_ids(self, elements: List[UIElement]) -> List[UIElement]:
        """Reassign clean sequential IDs."""
        id_mapping = {}

        for i, elem in enumerate(elements):
            old_id = elem.id
            new_id = f"E{i + 1}"
            id_mapping[old_id] = new_id
            elem.id = new_id

        # Update parent/children references
        for elem in elements:
            if elem.parent_id and elem.parent_id in id_mapping:
                elem.parent_id = id_mapping[elem.parent_id]
            elem.children_ids = [
                id_mapping.get(cid, cid) for cid in elem.children_ids
            ]

        return elements


def extract_elements(
    image: Union[np.ndarray, str],
    ocr_engine: str = "easyocr",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function to extract UI elements from image.

    Args:
        image: Image (numpy array) or path
        ocr_engine: OCR engine to use
        **kwargs: Additional arguments for pipeline

    Returns:
        List of element dictionaries
    """
    pipeline = VisualDOMPipeline(ocr_engine=ocr_engine, **kwargs)
    result = pipeline.process(image)
    return result["elements"]


# CLI interface
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Extract UI elements from screenshot")
    parser.add_argument("image", help="Path to image file")
    parser.add_argument("--ocr", default="easyocr", help="OCR engine")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--visualize", "-v", help="Output visualization image")
    parser.add_argument("--no-gpu", action="store_true", help="Disable GPU")
    args = parser.parse_args()

    # Process image
    pipeline = VisualDOMPipeline(
        ocr_engine=args.ocr,
        use_gpu=not args.no_gpu
    )

    result = pipeline.process(args.image)

    # Print summary
    print(f"\nDetected {result['stats']['final_count']} elements:")
    print(f"  - Text: {result['stats']['text_detected']}")
    print(f"  - UIED: {result['stats']['uied_detected']}")

    # Show elements
    for elem in result["elements"][:10]:
        text = elem.get("ocr_text", "")[:30] if elem.get("ocr_text") else ""
        print(f"  {elem['id']}: {elem['visual_type']} {text}")

    if len(result["elements"]) > 10:
        print(f"  ... and {len(result['elements']) - 10} more")

    # Save output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved to {args.output}")

    # Visualize
    if args.visualize:
        img = cv2.imread(args.image)

        colors = {
            "text": (0, 255, 0),      # Green
            "button": (255, 0, 0),    # Blue
            "input_field": (0, 255, 255),  # Yellow
            "icon": (255, 0, 255),    # Magenta
            "block": (128, 128, 128), # Gray
            "unknown": (200, 200, 200),
        }

        for elem in result["elements"]:
            x1, y1, x2, y2 = elem["bounds"]
            color = colors.get(elem["visual_type"], (200, 200, 200))

            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

            label = elem["visual_type"]
            if elem.get("ocr_text"):
                label += f": {elem['ocr_text'][:15]}"

            cv2.putText(img, label, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        cv2.imwrite(args.visualize, img)
        print(f"Visualization saved to {args.visualize}")
