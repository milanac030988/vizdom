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

from visual_dom.adapters.outbound.ocr.text_detector import TextDetector, TextElement
from visual_dom.adapters.outbound.detectors.uied_detection import UIEDDetector, DetectedElement, ElementType
from visual_dom.core.domain.cvops.image_processing import calculate_iou, non_max_suppression, is_contained
from visual_dom.core.domain.cvops.symbol_detector import detect_symbol
from visual_dom.logging_utils import get_logger
from visual_dom.core.domain.reading_order import sort_reading_order

log = get_logger(__name__)


@dataclass
class UIElement:
    """Unified UI element from CV pipeline."""
    id: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    visual_type: str
    confidence: float
    ocr_text: Optional[str] = None
    source: str = "unknown"  # "text", "uied", "yolo", "omniparser", "merged"
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    interactable: Optional[bool] = None  # set by backends that predict it (OmniParser)
    label: Optional[str] = None  # semantic name (own text, or associated nearby label)

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
        if self.interactable is not None:
            result["interactable"] = self.interactable
        if self.label:
            result["label"] = self.label
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
        slm_backend: str = None,
        slm_model: str = None,
        slm_host: str = "http://localhost:11434",
        camera_mode: bool = False,
        detector: str = "uied",
        yolo_model_path: str = None,
        detector_kwargs: Dict[str, Any] = None,
        text_ensemble: bool = True,
        merge_oversegmented: bool = True,
        cross_type_iou: float = 0.4,
        duplicate_tolerance_px: int = 5,
        group_fill_ratio_min: float = 0.5,
        hierarchy_containment_threshold: float = 0.7,
        detect_symbols: bool = True,
        symbol_min_score: float = None,
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
            slm_backend: SLM backend for smart review ("ollama", "openai", or None to disable)
            slm_model: SLM model name (default: qwen2.5:3b for ollama)
            slm_host: Ollama server URL
            camera_mode: Auto-detect and rectify screen from camera photos
            detector: Detection backend ("uied", "yolo", "omniparser", or "hybrid")
            yolo_model_path: Path to YOLO .pt model file (required for yolo/hybrid)
            detector_kwargs: Extra kwargs forwarded to the pluggable detector
                backend (e.g. OmniParser weight paths). Ignored by "hybrid".
            text_ensemble: For detector="omniparser", feed our upscaling OCR into
                OmniParser to recover missed text (ADR-016). True = "gained"
                (ensemble), False = "original" (OmniParser's own OCR only).
        """
        self.camera_mode = camera_mode
        self._text_ensemble = text_ensemble
        self._merge_oversegmented = merge_oversegmented
        # Stage 2.5 (merge & deduplicate) tunables, previously hardcoded.
        self._cross_type_iou = cross_type_iou
        self._duplicate_tolerance_px = duplicate_tolerance_px
        self._group_fill_ratio_min = group_fill_ratio_min
        # Stage 3 (hierarchy) containment threshold for the in-pipeline pass.
        self._hierarchy_containment_threshold = hierarchy_containment_threshold
        # Stage 4c (symbol reading) tunables.
        self._detect_symbols_enabled = detect_symbols
        self._symbol_min_score = symbol_min_score
        self.detector_mode = detector
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

        # YOLO detector (kept for legacy "hybrid" mode, which merges YOLO + UIED)
        self._yolo_model = None
        if detector == "hybrid" and yolo_model_path:
            self._init_yolo(yolo_model_path, use_gpu)

        # Pluggable primary backend for single-backend modes
        # ("uied", "yolo", "omniparser"). "hybrid" keeps its bespoke path above.
        self._primary_backend = None
        if detector != "hybrid":
            self._primary_backend = self._init_backend(
                detector, use_gpu, confidence_threshold,
                min_element_area, iou_threshold,
                yolo_model_path, detector_kwargs or {},
            )

        # Optional SLM advisor for smart element review
        self._slm_advisor = None
        if slm_backend:
            from visual_dom.adapters.outbound.refiner.slm_advisor import SLMAdvisor
            self._slm_advisor = SLMAdvisor(
                backend=slm_backend,
                model=slm_model,
                host=slm_host,
            )

        self._element_counter = 0
        self._scale = 1.0

    def _init_backend(
        self,
        detector: str,
        use_gpu: bool,
        confidence_threshold: float,
        min_element_area: int,
        iou_threshold: float,
        yolo_model_path: str,
        detector_kwargs: Dict[str, Any],
    ):
        """
        Construct the pluggable primary detector backend by name.

        Backend-specific defaults are supplied here from the pipeline's own
        config; `detector_kwargs` overrides/extends them (e.g. OmniParser paths).
        Returns None on failure so the pipeline degrades gracefully rather than
        failing to construct.
        """
        from visual_dom.adapters.outbound.detectors import create_detector

        if detector == "uied":
            kwargs = dict(min_element_area=min_element_area, nms_threshold=iou_threshold)
        elif detector == "yolo":
            kwargs = dict(
                model_path=yolo_model_path,
                use_gpu=use_gpu,
                confidence_threshold=confidence_threshold,
            )
        elif detector == "omniparser":
            kwargs = dict(use_gpu=use_gpu)
            # Auto-resolve model paths from standard project locations when not
            # given via detector_kwargs or OMNIPARSER_* env vars. Without this the
            # backend fails to construct and the pipeline silently degrades to
            # OCR-text-only -- a trap that quietly invalidates "omniparser" runs.
            import os as _os
            # core/domain/ -> core -> visual_dom -> src -> project root (4 levels).
            # This module lives two packages deeper since the ADR-014 restructure;
            # with one ".." too few the candidates below never exist and every
            # in-process "omniparser" run silently degrades to OCR-text-only.
            _root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__),
                                                   "..", "..", "..", ".."))
            if "icon_detect_path" not in detector_kwargs and not _os.environ.get("OMNIPARSER_ICON_DETECT"):
                _cand = _os.path.join(_root, "models", "omniparser", "icon_detect", "model.pt")
                if _os.path.exists(_cand):
                    kwargs["icon_detect_path"] = _cand
            if "icon_caption_path" not in detector_kwargs and not _os.environ.get("OMNIPARSER_ICON_CAPTION"):
                _cand = _os.path.join(_root, "models", "omniparser", "icon_caption_florence")
                if _os.path.isdir(_cand):
                    kwargs["icon_caption_path"] = _cand
            if "omniparser_root" not in detector_kwargs and not _os.environ.get("OMNIPARSER_ROOT"):
                _cand = _os.path.join(_root, "third_party", "OmniParser")
                if _os.path.isdir(_cand):
                    kwargs["omniparser_root"] = _cand
            # Text ensemble (ADR-016): feed our upscaling OCR into OmniParser so
            # its text/icon linking uses better OCR and misses less text. Reuses
            # the pipeline's TextDetector. Disable via text_ensemble=False to get
            # OmniParser's original OCR. Overridable via detector_kwargs.
            if self._text_ensemble:
                # Reuse the pipeline's TextDetector only if it has a real OCR
                # engine; otherwise build a dedicated easyocr one so the ensemble
                # works even when Step-1 text detection is disabled (ocr_engine=None).
                _td = self.text_detector
                if getattr(_td, "ocr_engine", None) in (None, "none", ""):
                    from visual_dom.adapters.outbound.ocr.text_detector import TextDetector
                    _td = TextDetector(ocr_engine="easyocr", gpu=use_gpu, upscale=True)
                    log.info("OmniParser text ensemble: ON (dedicated easyocr)")
                else:
                    log.info("OmniParser text ensemble: ON (engine=%s)", _td.ocr_engine)
                kwargs["ocr_provider"] = lambda img, _td=_td: [
                    (te.bounds, te.text) for te in _td.detect(img)
                ]
            else:
                log.info("OmniParser text ensemble: OFF (original OCR)")
        else:
            kwargs = {}
        kwargs.update(detector_kwargs)

        try:
            backend = create_detector(detector, **kwargs)
            if detector != "uied":
                log.info(f"Detector backend: {detector} (license: {backend.license})")
            return backend
        except Exception as e:
            log.warning(f"Could not initialize '{detector}' backend: {e}")
            if detector == "uied":
                raise  # UIED is the baseline; failing to build it is fatal
            return None

    def _convert_detections(self, detections) -> List[UIElement]:
        """Convert neutral Detection objects from a backend into UIElements."""
        result = []
        for d in detections:
            result.append(UIElement(
                id=self._next_id(),
                bounds=tuple(d.bounds),
                visual_type=d.visual_type,
                confidence=d.confidence,
                ocr_text=d.text,
                label=getattr(d, "label", None),
                source=d.source,
                parent_id=d.parent_id,
                children_ids=list(d.children_ids),
                interactable=d.interactable,
            ))
        return result

    def _init_yolo(self, model_path: str, use_gpu: bool = True):
        """Initialize YOLO model."""
        try:
            from ultralytics import YOLO
            self._yolo_model = YOLO(model_path)
            device = "cuda:0" if use_gpu else "cpu"
            # Warm up with a dummy inference
            log.info(f"YOLO model loaded: {model_path}")
        except ImportError:
            raise ImportError(
                "ultralytics not installed. Run: pip install ultralytics"
            )
        except Exception as e:
            log.warning(f"YOLO init failed: {e}")
            self._yolo_model = None

    def _detect_yolo(self, image: np.ndarray) -> List[UIElement]:
        """Detect UI elements using YOLO model."""
        if self._yolo_model is None:
            return []

        try:
            from models.configs.cv_model_registry import UI_ELEMENT_CLASSES
        except ImportError:
            UI_ELEMENT_CLASSES = [
                "button", "text", "icon", "input_field", "checkbox",
                "radio_button", "toggle", "slider", "dropdown", "image",
                "container", "toolbar", "navbar", "card", "list_item",
            ]

        results = self._yolo_model(
            image, conf=self.confidence_threshold, verbose=False
        )

        elements = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())

                if cls_id < len(UI_ELEMENT_CLASSES):
                    vtype = UI_ELEMENT_CLASSES[cls_id]
                else:
                    vtype = "unknown"

                elements.append(UIElement(
                    id=self._next_id(),
                    bounds=(x1, y1, x2, y2),
                    visual_type=vtype,
                    confidence=conf,
                    source="yolo",
                ))

        log.info(f"YOLO detected {len(elements)} elements")
        return elements

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
        self._image_path = None

        # Load image if path
        if isinstance(image, str):
            self._image_path = image
            image = cv2.imread(image)

        if image is None:
            raise ValueError("Could not load image")

        # Step 0: Camera mode — detect and rectify screen region
        if self.camera_mode:
            from visual_dom.core.domain.cvops.screen_detector import detect_screen
            screen = detect_screen(image)
            if screen and screen.rectified is not None:
                log.info(f"Screen detected ({screen.method}, conf={screen.confidence:.2f})")
                image = screen.rectified
            else:
                log.warning("No screen detected in camera photo, using full image")

        height, width = image.shape[:2]

        # Compute scale factor relative to 1080p reference
        # Clamp to minimum 1.0 so small images keep original thresholds
        self._scale = max(1.0, height / self.REFERENCE_HEIGHT)

        all_elements: List[UIElement] = []

        # Step 1: Text Detection
        text_elements = []
        text_error = None
        if detect_text:
            try:
                text_results = self.text_detector.detect(image)
                text_elements = self._convert_text_elements(text_results)
                all_elements.extend(text_elements)
            except Exception as e:
                # Degrading to a text-free run keeps headless batch jobs alive,
                # but the failure must reach the caller: a DOM with 0 text looks
                # identical to a text-free screen, and a dead OCR engine once
                # went unnoticed for a whole session that way (20260806_195229).
                text_error = str(e)
                log.warning(f"Text detection failed: {e}")

        # Step 2: Element Detection (UIED, YOLO, or Hybrid)
        uied_elements = []
        yolo_elements = []

        if detect_elements:
            if self.detector_mode == "hybrid":
                # Legacy hybrid path: run UIED + YOLO and merge (YOLO priority).
                try:
                    uied_results = self.uied_detector.detect(image)
                    uied_elements = self._convert_uied_elements(uied_results)
                except Exception as e:
                    log.warning(f"UIED detection failed: {e}")

                if self._yolo_model:
                    try:
                        yolo_elements = self._detect_yolo(image)
                    except Exception as e:
                        log.warning(f"YOLO detection failed: {e}")

                if yolo_elements and uied_elements:
                    uied_elements = self._merge_yolo_uied(yolo_elements, uied_elements)
                elif yolo_elements:
                    uied_elements = yolo_elements
            elif self._primary_backend is not None:
                # Single pluggable backend ("uied", "yolo", "omniparser").
                try:
                    detections = self._primary_backend.detect(image)
                    uied_elements = self._convert_detections(detections)
                except Exception as e:
                    log.warning(f"{self.detector_mode} detection failed: {e}")

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

        # Step 4b: Rule-based split using text positions
        if text_elements:
            all_elements = self._split_by_text_positions(all_elements, text_elements)

        # Step 4c: Symbol detection for elements without OCR text
        all_elements = self._detect_symbols(image, all_elements)

        # Step 5: Filter by size and confidence
        all_elements = self._filter_elements(all_elements)

        # Step 5: Apply NMS across all elements (cross-type)
        all_elements = self._apply_cross_type_nms(all_elements)

        # Step 6: Apply per-type NMS
        all_elements = self._apply_nms(all_elements)

        # Step 6b: Remove near-duplicate detections
        all_elements = self._remove_duplicates(all_elements)

        # Step 6c: Smart-merge over-segmented elements — a multi-word "full text"
        # box plus fragment boxes on the same text line (common with OmniParser:
        # a 2-line button split into halves + a full-text box). Rule-based; the
        # SLM can propose further merges in Step 8.
        if self._merge_oversegmented:
            all_elements = self._merge_oversegmented_elements(all_elements)

        # Step 7: Limit number of elements
        all_elements = self._limit_elements(all_elements)

        # Step 7b: Reading-order sort (top->bottom, left->right) so the optional
        # SLM review sees spatially-coherent input, which improves its suggestions.
        all_elements = sort_reading_order(all_elements)

        # Step 8: SLM-guided review (optional)
        if self._slm_advisor:
            all_elements = self._slm_review(all_elements, width, height)

        # Step 9: Build hierarchy (re-sorts internally by area)
        all_elements = self._build_hierarchy(all_elements)

        # Step 9b: Re-apply reading order after hierarchy so the final list — and
        # the sequential IDs assigned next — follow reading order (E1 = top-left).
        all_elements = sort_reading_order(all_elements)

        # Step 10: Reassign IDs for clean output
        all_elements = self._reassign_ids(all_elements)

        # Prepare output
        stats = {
            "text_detected": len(text_elements),
            "uied_detected": len(uied_elements),
            "yolo_detected": len(yolo_elements),
            "detector": self.detector_mode,
            "final_count": len(all_elements),
        }
        if text_error:
            stats["text_error"] = text_error
        return {
            "elements": [e.to_dict() for e in all_elements],
            "image_size": {"width": width, "height": height},
            "stats": stats,
        }

    def _merge_yolo_uied(
        self,
        yolo_elements: List[UIElement],
        uied_elements: List[UIElement],
    ) -> List[UIElement]:
        """
        Merge YOLO and UIED detections for hybrid mode.

        YOLO elements take priority. UIED elements that don't significantly
        overlap with any YOLO element are added to fill gaps.
        """
        merged = list(yolo_elements)

        for uied_elem in uied_elements:
            is_duplicate = False
            for yolo_elem in yolo_elements:
                iou = calculate_iou(uied_elem.bounds, yolo_elem.bounds)
                if iou > 0.3:
                    is_duplicate = True
                    # Transfer text from UIED to YOLO if YOLO lacks it
                    if uied_elem.ocr_text and not yolo_elem.ocr_text:
                        yolo_elem.ocr_text = uied_elem.ocr_text
                    break

            if not is_duplicate:
                uied_elem.source = "uied_gap"
                merged.append(uied_elem)

        log.info(f"Hybrid merge: {len(yolo_elements)} YOLO + "
                 f"{len(merged) - len(yolo_elements)} UIED gaps = {len(merged)} total")
        return merged

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
            log.info(f"Re-scanned {rescan_count} merged regions")

        return result

    def _split_by_text_positions(
        self,
        elements: List[UIElement],
        text_elements: List[UIElement],
    ) -> List[UIElement]:
        """
        Rule-based splitting: if a non-text element contains multiple
        non-overlapping OCR text regions, split it into separate elements
        using the text positions as guides.

        This catches merged buttons that the rescan missed (e.g., "+" and "-"
        side by side detected as one element).
        """
        result = []
        split_count = 0

        # Boxes the detector itself marked as ONE interactable. Other stages
        # (rescan, merge) produce coincident copies of these boxes that carry
        # interactable=None, so the guard below must compare against the
        # detector's boxes, not just each element's own flag.
        detector_interactables = [e.bounds for e in elements
                                  if e.interactable is True]

        for elem in elements:
            # Only split non-text, non-block elements
            if elem.visual_type in ("text", "block"):
                result.append(elem)
                continue

            # Never split a control the detector identified as ONE interactable
            # (OmniParser's interactivity flag). A tile button whose caption is
            # two words ("Check Now") contains two OCR boxes, and splitting it
            # produced two half-buttons; the detector's own segmentation is the
            # better authority here. Splitting exists for UIED's merged blobs,
            # which carry interactable=None.
            if elem.interactable is True:
                result.append(elem)
                continue

            # The same authority extends to coincident copies: a rescan or merge
            # box occupying (IoU >= 0.8) a detector-marked interactable IS that
            # control seen by another stage. Splitting such a copy cut the
            # "Send Logfiles" tile (icon glyph reading as 'LoG' above the
            # caption) into an icon half and a caption half - session
            # 20260810_160751, E13.
            if any(calculate_iou(elem.bounds, b) >= 0.8
                   for b in detector_interactables):
                result.append(elem)
                continue

            # Find text elements contained in this element
            contained = []
            for te in text_elements:
                if is_contained(te.bounds, elem.bounds, threshold=0.6):
                    contained.append(te)

            # Need 2+ non-overlapping texts to split
            if len(contained) < 2:
                result.append(elem)
                continue

            # Words of ONE caption sit close together; separate merged controls
            # sit far apart. Require a clear gap between adjacent texts (relative
            # to text height) before splitting — otherwise "User Info" on one
            # tile splits into two buttons at the word boundary.
            xs = sorted(contained, key=lambda t: t.bounds[0])
            med_h = sorted(t.bounds[3] - t.bounds[1] for t in contained)[len(contained) // 2]
            max_gap = 0
            for prev, cur in zip(xs, xs[1:]):
                max_gap = max(max_gap, cur.bounds[0] - prev.bounds[2])
            ys = sorted(contained, key=lambda t: t.bounds[1])
            for prev, cur in zip(ys, ys[1:]):
                max_gap = max(max_gap, cur.bounds[1] - prev.bounds[3])
            if max_gap < max(12, int(1.5 * med_h)):
                result.append(elem)
                continue

            # Check that texts don't overlap each other (they're separate items)
            texts_overlap = False
            for i in range(len(contained)):
                for j in range(i + 1, len(contained)):
                    if calculate_iou(contained[i].bounds, contained[j].bounds) > 0.2:
                        texts_overlap = True
                        break
                if texts_overlap:
                    break

            if texts_overlap:
                result.append(elem)
                continue

            # Determine arrangement: horizontal or vertical
            sorted_x = sorted(contained, key=lambda t: t.bounds[0])
            sorted_y = sorted(contained, key=lambda t: t.bounds[1])
            x_spread = sorted_x[-1].bounds[2] - sorted_x[0].bounds[0]
            y_spread = sorted_y[-1].bounds[3] - sorted_y[0].bounds[1]

            px1, py1, px2, py2 = elem.bounds
            split_count += 1

            if x_spread >= y_spread:
                # Horizontal — split vertically between texts
                sorted_texts = sorted_x
                for i, te in enumerate(sorted_texts):
                    if i == 0:
                        left = px1
                    else:
                        prev_right = sorted_texts[i - 1].bounds[2]
                        left = (prev_right + te.bounds[0]) // 2

                    if i == len(sorted_texts) - 1:
                        right = px2
                    else:
                        next_left = sorted_texts[i + 1].bounds[0]
                        right = (te.bounds[2] + next_left) // 2

                    result.append(UIElement(
                        id=self._next_id(),
                        bounds=(left, py1, right, py2),
                        visual_type=elem.visual_type,
                        confidence=elem.confidence,
                        ocr_text=te.ocr_text,
                        source="text_split",
                        parent_id=elem.id,
                    ))
            else:
                # Vertical — split horizontally between texts
                sorted_texts = sorted_y
                for i, te in enumerate(sorted_texts):
                    if i == 0:
                        top = py1
                    else:
                        prev_bottom = sorted_texts[i - 1].bounds[3]
                        top = (prev_bottom + te.bounds[1]) // 2

                    if i == len(sorted_texts) - 1:
                        bottom = py2
                    else:
                        next_top = sorted_texts[i + 1].bounds[1]
                        bottom = (te.bounds[3] + next_top) // 2

                    result.append(UIElement(
                        id=self._next_id(),
                        bounds=(px1, top, px2, bottom),
                        visual_type=elem.visual_type,
                        confidence=elem.confidence,
                        ocr_text=te.ocr_text,
                        source="text_split",
                        parent_id=elem.id,
                    ))

            # Keep parent as container
            elem.visual_type = "block"
            result.append(elem)

        if split_count > 0:
            log.info(f"Text-split {split_count} merged elements")

        return result

    def _detect_symbols(
        self,
        image: np.ndarray,
        elements: List[UIElement],
    ) -> List[UIElement]:
        """
        Detect common UI symbols (+, -, =, ×, ÷) in elements that
        have no OCR text. OCR often misses small single-character symbols.
        """
        if not self._detect_symbols_enabled:
            return elements
        symbol_count = 0

        for elem in elements:
            # Skip elements that already have text
            if elem.ocr_text:
                continue

            # Captioned glyph elements (e.g. OmniParser icons) DO get symbol
            # detection: the symbol is a literal pixel read, so it belongs in
            # `text`, while the caption stays in `label`. This recovers correct
            # text on operator keys whose captions are look-alike noise (a "-"
            # key captioned "Minimize", a "+" key captioned "Add"). Safe now
            # that the detector is template-matched with a confidence gate and
            # rejects hollow shapes (the old square -> "+" misfire).

            # Only check button-sized elements (not blocks or tiny elements)
            if elem.area < self._scaled_area(200) or elem.area > self._scaled_area(40000):
                continue

            symbol = detect_symbol(image, elem.bounds, min_score=self._symbol_min_score)
            if symbol:
                elem.ocr_text = symbol
                # The pixel read is authoritative: outside the title-bar strip a
                # look-alike caption ("Add" on ÷, "Close" on ×, "Minimize" on −)
                # is noise, so the label becomes the canonical operator name.
                # Inside the title bar the caption IS the semantic name
                # (Close/Minimize/Maximize) and is kept.
                in_titlebar = elem.bounds[3] <= int(0.08 * image.shape[0])
                if not in_titlebar:
                    from visual_dom.core.domain.cvops.symbol_detector import SYMBOL_LABELS
                    elem.label = SYMBOL_LABELS.get(symbol, symbol)
                symbol_count += 1

        if symbol_count > 0:
            log.info(f"Detected {symbol_count} symbols in textless elements")

        return elements

    def _merge_text_and_elements(
        self,
        text_elements: List[UIElement],
        uied_elements: List[UIElement]
    ) -> List[UIElement]:
        """
        Merge text detections with UIED detections.

        Strategy:
        - Only merge text into interactive-sized elements (buttons, inputs)
        - Large containers (blocks) keep text as separate children
        - Text that doesn't match any element stays standalone
        """
        merged = []
        used_text_ids = set()

        # Max area for text merging — elements larger than this are containers
        # and should NOT swallow text into a combined string
        max_merge_area = self._scaled_area(30000)

        # Sort UIED elements: smallest first, so small elements claim text
        # before large containers can
        sorted_uied = sorted(uied_elements, key=lambda e: e.area)

        for uied_elem in sorted_uied:
            # Large elements (containers/blocks) should not merge text
            is_container = (
                uied_elem.area > max_merge_area
                or uied_elem.visual_type == "block"
            )

            if is_container:
                # Keep the container but don't attach text
                if uied_elem.area > self._scaled_area(5000):
                    merged.append(uied_elem)
                continue

            # For interactive-sized elements, find overlapping text
            overlapping_text = []

            for text_elem in text_elements:
                if text_elem.id in used_text_ids:
                    continue

                iou = calculate_iou(uied_elem.bounds, text_elem.bounds)

                # Check if text is inside or overlaps the UIED element
                if iou > 0.3 or is_contained(text_elem.bounds, uied_elem.bounds, 0.7):
                    overlapping_text.append(text_elem)
                    used_text_ids.add(text_elem.id)

            # Merge text into the element
            if overlapping_text:
                combined_text = " ".join(
                    t.ocr_text for t in overlapping_text if t.ocr_text
                )
                uied_elem.ocr_text = combined_text
                uied_elem.source = "merged"

                # Boost confidence if text confirms element
                if uied_elem.visual_type in ["button", "input_field"]:
                    uied_elem.confidence = min(1.0, uied_elem.confidence + 0.1)

            merged.append(uied_elem)

        # Add remaining text elements that weren't merged — they stay standalone
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
        """
        Remove redundant overlapping elements across all types.

        Priority rules:
        1. Elements with text beat those without
        2. Specific types (button, input_field) beat generic (block, unknown)
        3. Higher confidence wins among equals
        4. Children from text_split are preferred over their parent containers
        """
        if not elements:
            return []

        def _element_priority(e: UIElement) -> tuple:
            """Higher = better priority."""
            has_text = 1 if e.ocr_text else 0
            type_rank = {
                "button": 5, "input_field": 5, "checkbox": 4,
                "icon": 3, "text": 3, "divider": 2,
                "block": 1, "unknown": 0,
            }
            rank = type_rank.get(e.visual_type, 0)
            return (has_text, rank, e.confidence)

        # Sort by priority (best first)
        sorted_elements = sorted(elements, key=_element_priority, reverse=True)

        keep = []
        suppressed_ids = set()

        for elem in sorted_elements:
            if elem.id in suppressed_ids:
                continue

            keep.append(elem)

            for other in sorted_elements:
                if other.id == elem.id or other.id in suppressed_ids:
                    continue

                iou = calculate_iou(elem.bounds, other.bounds)

                # High IoU overlap — keep higher priority
                if iou > self._cross_type_iou:
                    suppressed_ids.add(other.id)
                    continue

                # Check containment both ways
                other_in_elem = is_contained(other.bounds, elem.bounds, threshold=0.75)
                elem_in_other = is_contained(elem.bounds, other.bounds, threshold=0.75)

                if other_in_elem:
                    # Other is inside elem
                    if elem.visual_type == "block" and other.visual_type != "block":
                        # Block contains a specific element — keep both (parent-child)
                        continue
                    if other.area < elem.area * 0.2:
                        # Much smaller — likely a real child, keep both
                        continue
                    # Similar size, overlapping — suppress the worse one
                    suppressed_ids.add(other.id)

                elif elem_in_other:
                    # Elem is inside other — other is a larger container
                    # We already kept elem (higher priority), suppress other
                    # unless other is a legitimate container
                    if other.visual_type == "block" and elem.visual_type != "block":
                        continue  # Keep container
                    if elem.area < other.area * 0.2:
                        continue  # Very different sizes, keep both
                    suppressed_ids.add(other.id)

        return keep

    def _remove_duplicates(self, elements: List[UIElement]) -> List[UIElement]:
        """
        Remove near-duplicate elements that have similar bounds and same text.

        This catches duplicates from different detection passes (e.g., a button
        detected by both coarse and fine detection, or rescan creating a
        duplicate of the original).
        """
        if not elements:
            return []

        # Sort: prefer elements with text, then by confidence
        sorted_elems = sorted(
            elements,
            key=lambda e: (1 if e.ocr_text else 0, e.confidence),
            reverse=True,
        )

        keep = []
        removed = 0

        for elem in sorted_elems:
            is_dup = False
            for kept in keep:
                # Check if bounds are very similar (within 5px on each side)
                b1 = elem.bounds
                b2 = kept.bounds
                dx = max(abs(b1[0] - b2[0]), abs(b1[2] - b2[2]))
                dy = max(abs(b1[1] - b2[1]), abs(b1[3] - b2[3]))

                tol = self._duplicate_tolerance_px
                if dx <= tol and dy <= tol:
                    # Nearly identical position — it's a duplicate
                    # Transfer text if the kept one doesn't have it
                    if elem.ocr_text and not kept.ocr_text:
                        kept.ocr_text = elem.ocr_text
                    is_dup = True
                    break

                # Also catch elements with same text and high overlap
                if elem.ocr_text and elem.ocr_text == kept.ocr_text:
                    iou = calculate_iou(b1, b2)
                    if iou > 0.3:
                        is_dup = True
                        break

            if is_dup:
                removed += 1
            else:
                keep.append(elem)

        if removed > 0:
            log.info(f"Removed {removed} duplicate elements")

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
                if is_contained(child.bounds, elem.bounds,
                                threshold=self._hierarchy_containment_threshold):
                    child.parent_id = elem.id
                    elem.children_ids.append(child.id)

        return sorted_elements

    @staticmethod
    def _norm_text(t: Optional[str]) -> str:
        """Normalize text for fragment comparison: lowercase, collapse spaces."""
        import re
        return re.sub(r"\s+", " ", (t or "").strip().lower())

    @staticmethod
    def _vertical_overlap_ratio(a, b) -> float:
        """Vertical overlap of two boxes over the smaller box's height (0..1)."""
        top, bot = max(a[1], b[1]), min(a[3], b[3])
        inter = max(0, bot - top)
        h = min(a[3] - a[1], b[3] - b[1])
        return inter / h if h > 0 else 0.0

    def _find_merge_candidates(self, elements: List[UIElement]) -> List[List[UIElement]]:
        """
        Find over-segmentation groups.

        A group is a multi-word "full text" anchor element plus other elements on
        the same text line (vertical overlap) whose normalized text is a substring
        of (or equal to) the anchor's text. This catches OmniParser splitting one
        multi-line control into fragment boxes alongside a full-text box.
        Conservative: the anchor must be multi-word (contains a space) and >= 8
        chars, fragments >= 3 chars, vertical overlap >= 0.3 — so single glyphs
        (7, 8, 9) are never merged.
        """
        groups: List[List[UIElement]] = []
        used = set()
        anchors = sorted(elements, key=lambda e: len(self._norm_text(e.ocr_text)), reverse=True)
        for anchor in anchors:
            if anchor.id in used:
                continue
            atext = self._norm_text(anchor.ocr_text)
            if len(atext) < 8 or " " not in atext:
                continue
            # Navigation/breadcrumb bars ("A > B > C", "X | Y") are separate links,
            # not one over-segmented element — leave those to SLM judgement.
            if any(sep in atext for sep in (" > ", " › ", " » ", " | ", " / ")):
                continue
            members = []
            for other in elements:
                if other.id == anchor.id or other.id in used:
                    continue
                otext = self._norm_text(other.ocr_text)
                if len(otext) < 3:
                    continue
                is_fragment = otext in atext and len(otext) < len(atext)
                is_duplicate = otext == atext
                if (is_fragment or is_duplicate) and \
                        self._vertical_overlap_ratio(anchor.bounds, other.bounds) >= 0.3:
                    members.append(other)
            if members:
                group = [anchor] + members
                # Spatial safety guard: only accept if the parts densely fill
                # their union box. Genuine over-segmentation (a multi-line label,
                # a split text line) tiles its region; a coincidental substring
                # match with a distant element leaves the union mostly empty.
                if self._group_fill_ratio(group) >= self._group_fill_ratio_min:
                    used.update(m.id for m in group)
                    groups.append(group)
        return groups

    @staticmethod
    def _group_fill_ratio(members: List[UIElement]) -> float:
        """Sum of member box areas over their union box area (overlap-capped)."""
        x1 = min(m.bounds[0] for m in members)
        y1 = min(m.bounds[1] for m in members)
        x2 = max(m.bounds[2] for m in members)
        y2 = max(m.bounds[3] for m in members)
        union = max(1, (x2 - x1) * (y2 - y1))
        parts = sum(max(0, m.bounds[2] - m.bounds[0]) * max(0, m.bounds[3] - m.bounds[1])
                    for m in members)
        return parts / union

    def _find_line_text_candidates(self, elements: List[UIElement]) -> List[List[UIElement]]:
        """
        Group consecutive same-line text pieces into merge candidates.

        Handles the over-segmentation pattern where a sentence/label is split into
        disjoint horizontal pieces with NO full-text box (so _find_merge_candidates
        can't anchor). Restricted to non-interactable text elements — a row of
        buttons/icons is never grouped — and split into runs by horizontal gap so
        genuinely separate labels on the same row (large gap) stay apart.

        These are returned as *candidates only*: whether a run is one sentence or
        several labels is a semantic call left to the SLM, not auto-applied.
        """
        texts = [e for e in elements
                 if e.visual_type == "text"
                 and not getattr(e, "interactable", False)
                 and self._norm_text(e.ocr_text)]
        if len(texts) < 2:
            return []

        # Assign to rows by vertical overlap (sorted top->bottom, left->right).
        ordered = sorted(texts, key=lambda e: ((e.bounds[1] + e.bounds[3]) / 2, e.bounds[0]))
        rows: List[List[UIElement]] = []
        for e in ordered:
            if rows and self._vertical_overlap_ratio(rows[-1][-1].bounds, e.bounds) >= 0.5:
                rows[-1].append(e)
            else:
                rows.append([e])

        groups: List[List[UIElement]] = []
        for row in rows:
            if len(row) < 2:
                continue
            row.sort(key=lambda e: e.bounds[0])
            heights = sorted(r.bounds[3] - r.bounds[1] for r in row)
            med_h = heights[len(heights) // 2]
            gap_thresh = max(12, 2.5 * med_h)  # phrase-gap tolerant, but not huge
            run = [row[0]]
            for prev, cur in zip(row, row[1:]):
                if cur.bounds[0] - prev.bounds[2] <= gap_thresh:
                    run.append(cur)
                else:
                    if len(run) >= 2:
                        groups.append(run)
                    run = [cur]
            if len(run) >= 2:
                groups.append(run)
        return groups

    def _merge_group(self, members: List[UIElement], label: str = None) -> Optional[UIElement]:
        """Combine a group of over-segmented elements into a single element."""
        members = [m for m in members if m is not None]
        if len(members) < 2:
            return None
        x1 = min(m.bounds[0] for m in members)
        y1 = min(m.bounds[1] for m in members)
        x2 = max(m.bounds[2] for m in members)
        y2 = max(m.bounds[3] for m in members)
        texts = [m.ocr_text for m in members if m.ocr_text]
        full = label or (max(texts, key=len) if texts else None)
        # Prefer an interactable/structural type over plain text.
        preferred = ("button", "input_field", "checkbox", "icon")
        vtype = next((m.visual_type for m in members if m.visual_type in preferred),
                     members[0].visual_type)
        interact = True if any(getattr(m, "interactable", None) for m in members) else None
        conf = max(m.confidence for m in members)
        return UIElement(
            id=members[0].id,
            bounds=(x1, y1, x2, y2),
            visual_type=vtype,
            confidence=conf,
            ocr_text=full,
            source="merge",
            label=full,
            interactable=interact,
        )

    def _merge_oversegmented_elements(self, elements: List[UIElement]) -> List[UIElement]:
        """Rule-based smart-merge stage (Step 6c). Non-destructive when no groups."""
        groups = self._find_merge_candidates(elements)
        if not groups:
            return elements
        removed = set()
        merged = []
        for group in groups:
            # Don't auto-fuse a group that contains 2+ independently interactable
            # members — those are almost certainly distinct controls (e.g. two
            # adjacent ribbon buttons "Session" + "Servers" that a spanning text
            # label happens to cover), not one over-segmented element. Geometry
            # can't distinguish that from a wrapped multi-line button, so defer
            # such groups to the SLM (they remain SLM merge candidates).
            interactable_members = sum(
                1 for g in group if getattr(g, "interactable", None) is True)
            if interactable_members >= 2:
                log.info("Smart-merge: skipping %s (%d interactable members — likely "
                         "distinct controls; deferring to SLM)",
                         [g.id for g in group], interactable_members)
                continue
            m = self._merge_group(group)
            if m:
                merged.append(m)
                removed.update(g.id for g in group)
        if not merged:
            return elements
        log.info("Smart-merge: %d group(s), %d elements -> %d merged",
                 len(merged), len(removed), len(merged))
        result = [e for e in elements if e.id not in removed]
        result.extend(merged)
        return result

    def _slm_review(
        self,
        elements: List[UIElement],
        img_width: int,
        img_height: int,
    ) -> List[UIElement]:
        """
        Use the SLM to review elements and apply corrections.

        Supported actions from the SLM:
        - split:  break one element into several (uses text positions)
        - retype: change an element's visual_type
        - merge:  combine over-segmented elements into one (ids + optional label)
        - label:  set an element's semantic label

        Over-segmentation candidates (from `_find_merge_candidates`) are passed as
        hints so the SLM can confirm/deny ambiguous merges (e.g. breadcrumb bars).
        """
        log.info("SLM reviewing detected elements...")

        # Convert to dicts for SLM, with over-segmentation hints from both
        # detectors: anchor-containment groups + same-line text runs. Deduped.
        elem_dicts = [e.to_dict() for e in elements]
        candidate_groups = self._find_merge_candidates(elements) + \
            self._find_line_text_candidates(elements)
        seen_groups = set()
        merge_candidates = []
        for g in candidate_groups:
            key = frozenset(m.id for m in g)
            if len(key) >= 2 and key not in seen_groups:
                seen_groups.add(key)
                merge_candidates.append([m.id for m in g])

        suggestions = self._slm_advisor.review_elements(
            elem_dicts, (img_width, img_height),
            image_path=self._image_path,
            merge_candidates=merge_candidates,
        )

        if not suggestions:
            log.info("SLM: no changes suggested")
            return elements

        log.info(f"SLM: {len(suggestions)} suggestions")

        # Build lookup
        elements_by_id = {e.id: e for e in elements}
        # SLM merges are gated to the geometric candidate groups: the SLM may
        # only CONFIRM/reject a proposed over-segmentation group, not invent
        # arbitrary merges (a 7B VLM over-merges badly when given free rein —
        # e.g. combining two separate buttons). A suggested merge is applied only
        # if its id-set is a subset of some candidate group.
        candidate_sets = [frozenset(g) for g in merge_candidates]
        new_elements = []
        split_ids = set()
        retype_map = {}
        label_map = {}
        removed_ids = set()

        for suggestion in suggestions:
            action = suggestion.get("action")
            target_id = suggestion.get("id")
            reason = suggestion.get("reason", "")

            if action == "split" and target_id in elements_by_id:
                texts = suggestion.get("texts", [])
                if len(texts) >= 2:
                    log.info(f"Split {target_id}: {texts} ({reason})")
                    parent = elements_by_id[target_id]
                    split_result = self._apply_slm_split(parent, texts)
                    if split_result:
                        split_ids.add(target_id)
                        new_elements.extend(split_result)

            elif action == "retype" and target_id in elements_by_id:
                new_type = suggestion.get("type")
                if new_type:
                    log.info(f"Retype {target_id}: -> {new_type} ({reason})")
                    retype_map[target_id] = new_type

            elif action == "label" and target_id in elements_by_id:
                lbl = suggestion.get("label") or suggestion.get("text")
                if lbl:
                    log.info(f"Label {target_id}: {lbl!r} ({reason})")
                    label_map[target_id] = lbl

            elif action == "merge":
                ids = [i for i in (suggestion.get("ids") or [])
                       if i in elements_by_id and i not in removed_ids]
                if len(ids) >= 2 and not any(frozenset(ids) <= cs for cs in candidate_sets):
                    log.info(f"Merge {ids} rejected (not a geometric candidate)")
                    continue
                if len(ids) >= 2:
                    merged_elem = self._merge_group(
                        [elements_by_id[i] for i in ids],
                        label=suggestion.get("label") or suggestion.get("text"),
                    )
                    if merged_elem:
                        log.info(f"Merge {ids} -> {merged_elem.ocr_text!r} ({reason})")
                        removed_ids.update(ids)
                        new_elements.append(merged_elem)

        # Build result: drop merged members, apply retypes/labels, mark splits
        result = []
        for elem in elements:
            if elem.id in removed_ids:
                continue
            if elem.id in split_ids:
                elem.visual_type = "block"  # keep as container for split children
            elif elem.id in retype_map:
                elem.visual_type = retype_map[elem.id]
            if elem.id in label_map:
                elem.label = label_map[elem.id]
            result.append(elem)

        result.extend(new_elements)
        return result

    def _apply_slm_split(
        self,
        parent: UIElement,
        texts: List[str],
    ) -> Optional[List[UIElement]]:
        """
        Split a merged element based on SLM-suggested text labels.

        Uses text positions from existing OCR detections to determine
        split boundaries. Falls back to even division if text positions
        are not available.
        """
        px1, py1, px2, py2 = parent.bounds
        pw = px2 - px1
        ph = py2 - py1
        n = len(texts)

        if n < 2:
            return None

        elements = []

        # Determine layout: horizontal if wider than tall, else vertical
        if pw >= ph:
            # Horizontal split — divide width evenly
            slice_w = pw / n
            for i, text in enumerate(texts):
                left = int(px1 + i * slice_w)
                right = int(px1 + (i + 1) * slice_w)
                bounds = (left, py1, right, py2)
                elements.append(UIElement(
                    id=self._next_id(),
                    bounds=bounds,
                    visual_type=parent.visual_type if parent.visual_type != "block" else "button",
                    confidence=parent.confidence * 0.9,
                    ocr_text=text,
                    source="slm_split",
                    parent_id=parent.id,
                ))
        else:
            # Vertical split — divide height evenly
            slice_h = ph / n
            for i, text in enumerate(texts):
                top = int(py1 + i * slice_h)
                bottom = int(py1 + (i + 1) * slice_h)
                bounds = (px1, top, px2, bottom)
                elements.append(UIElement(
                    id=self._next_id(),
                    bounds=bounds,
                    visual_type=parent.visual_type if parent.visual_type != "block" else "button",
                    confidence=parent.confidence * 0.9,
                    ocr_text=text,
                    source="slm_split",
                    parent_id=parent.id,
                ))

        return elements

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
