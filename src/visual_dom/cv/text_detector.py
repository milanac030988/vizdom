"""
Text detection and OCR module.

Responsibilities:
- Detect text regions in screenshots
- Extract text content via OCR
- Return bounding boxes with confidence scores

Supports multiple OCR backends:
- EasyOCR (recommended): Good accuracy, GPU support
- PaddleOCR: Fast, good for Chinese/multi-language
- Tesseract: Classic, widely available
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional, Union


@dataclass
class TextElement:
    """Detected text element with bounding box."""
    id: str
    text: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bounds": list(self.bounds),
            "visual_type": "text",
            "ocr_text": self.text,
            "confidence": self.confidence,
        }


class TextDetector:
    """Detect and extract text from GUI screenshots."""

    def __init__(
        self,
        ocr_engine: str = "easyocr",
        languages: List[str] = None,
        confidence_threshold: float = 0.5,
        gpu: bool = True
    ):
        """
        Initialize text detector.

        Args:
            ocr_engine: OCR backend ("easyocr", "paddleocr", "tesseract")
            languages: List of language codes (default: ["en"])
            confidence_threshold: Minimum confidence to accept detection
            gpu: Use GPU acceleration if available
        """
        self.ocr_engine = ocr_engine
        self.languages = languages or ["en"]
        self.confidence_threshold = confidence_threshold
        self.gpu = gpu
        self._engine = None
        self._text_counter = 0

    def _next_id(self) -> str:
        """Generate next text element ID."""
        self._text_counter += 1
        return f"T{self._text_counter}"

    def _init_engine(self):
        """Lazy initialization of OCR engine."""
        if self._engine is not None:
            return

        if self.ocr_engine == "easyocr":
            try:
                import easyocr
                self._engine = easyocr.Reader(
                    self.languages,
                    gpu=self.gpu
                )
            except ImportError:
                raise ImportError("EasyOCR not installed. Run: pip install easyocr")

        elif self.ocr_engine == "paddleocr":
            try:
                from paddleocr import PaddleOCR
                # Map language codes
                lang = "en" if "en" in self.languages else self.languages[0]
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=lang,
                    use_gpu=self.gpu,
                    show_log=False
                )
            except ImportError:
                raise ImportError("PaddleOCR not installed. Run: pip install paddleocr")

        elif self.ocr_engine == "tesseract":
            try:
                import os

                # Auto-detect Tesseract path on Windows BEFORE importing pytesseract
                tesseract_paths = [
                    r"C:\Program Files\Tesseract-OCR",
                    r"C:\Program Files (x86)\Tesseract-OCR",
                    r"D:\Program Files\Tesseract-OCR",
                ]

                tesseract_dir = None
                tesseract_exe = None
                for base_path in tesseract_paths:
                    exe_path = os.path.join(base_path, "tesseract.exe")
                    if os.path.exists(exe_path):
                        tesseract_dir = base_path
                        tesseract_exe = exe_path
                        break

                # Set TESSDATA_PREFIX environment variable BEFORE importing pytesseract
                # This overrides any incorrect system-level setting
                if tesseract_dir:
                    tessdata_path = os.path.join(tesseract_dir, "tessdata")
                    if os.path.exists(tessdata_path):
                        os.environ["TESSDATA_PREFIX"] = tessdata_path

                import pytesseract

                if tesseract_exe:
                    pytesseract.pytesseract.tesseract_cmd = tesseract_exe

                # Verify tesseract is installed
                pytesseract.get_tesseract_version()
                self._engine = pytesseract
            except ImportError:
                raise ImportError("pytesseract not installed. Run: pip install pytesseract")
            except Exception as e:
                raise RuntimeError(
                    f"Tesseract not found. Install from: https://github.com/UB-Mannheim/tesseract/wiki\n"
                    f"Error: {e}"
                )

        else:
            raise ValueError(f"Unknown OCR engine: {self.ocr_engine}")

    def detect(
        self,
        image: Union[np.ndarray, str],
        merge_boxes: bool = True
    ) -> List[TextElement]:
        """
        Detect text elements in an image.

        Args:
            image: numpy array (BGR) or path to image file
            merge_boxes: Merge nearby text boxes into lines

        Returns:
            List of TextElement with detected text and bounding boxes
        """
        self._init_engine()
        self._text_counter = 0

        # Load image if path provided
        if isinstance(image, str):
            image = cv2.imread(image)

        if image is None:
            raise ValueError("Could not load image")

        # Detect based on engine
        if self.ocr_engine == "easyocr":
            results = self._detect_easyocr(image)
        elif self.ocr_engine == "paddleocr":
            results = self._detect_paddleocr(image)
        elif self.ocr_engine == "tesseract":
            results = self._detect_tesseract(image)
        else:
            results = []

        # Filter by confidence
        results = [r for r in results if r.confidence >= self.confidence_threshold]

        # Optionally merge nearby boxes
        if merge_boxes:
            results = self._merge_text_boxes(results)

        return results

    def _detect_easyocr(self, image: np.ndarray) -> List[TextElement]:
        """Detect text using EasyOCR."""
        # EasyOCR expects RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Run detection
        results = self._engine.readtext(rgb)

        text_elements = []
        for detection in results:
            bbox_points, text, confidence = detection

            # Convert from 4 corner points to (x1, y1, x2, y2)
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            bounds = (
                int(min(xs)),
                int(min(ys)),
                int(max(xs)),
                int(max(ys))
            )

            text_elements.append(TextElement(
                id=self._next_id(),
                text=text,
                bounds=bounds,
                confidence=float(confidence)
            ))

        return text_elements

    def _detect_paddleocr(self, image: np.ndarray) -> List[TextElement]:
        """Detect text using PaddleOCR."""
        results = self._engine.ocr(image, cls=True)

        text_elements = []

        # PaddleOCR returns nested structure
        if results and results[0]:
            for line in results[0]:
                bbox_points, (text, confidence) = line

                # Convert from 4 corner points to (x1, y1, x2, y2)
                xs = [p[0] for p in bbox_points]
                ys = [p[1] for p in bbox_points]
                bounds = (
                    int(min(xs)),
                    int(min(ys)),
                    int(max(xs)),
                    int(max(ys))
                )

                text_elements.append(TextElement(
                    id=self._next_id(),
                    text=text,
                    bounds=bounds,
                    confidence=float(confidence)
                ))

        return text_elements

    def _detect_tesseract(self, image: np.ndarray) -> List[TextElement]:
        """Detect text using Tesseract."""
        # Convert to RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Get detailed results
        data = self._engine.image_to_data(rgb, output_type=self._engine.Output.DICT)

        text_elements = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])

            # Skip empty or low confidence
            if not text or conf < 0:
                continue

            x = data['left'][i]
            y = data['top'][i]
            w = data['width'][i]
            h = data['height'][i]

            text_elements.append(TextElement(
                id=self._next_id(),
                text=text,
                bounds=(x, y, x + w, y + h),
                confidence=conf / 100.0
            ))

        return text_elements

    def _merge_text_boxes(
        self,
        elements: List[TextElement],
        x_threshold: int = 20,
        y_threshold: int = 10
    ) -> List[TextElement]:
        """
        Merge nearby text boxes that likely belong to the same line.

        Args:
            elements: List of text elements
            x_threshold: Max horizontal gap to merge
            y_threshold: Max vertical difference to merge

        Returns:
            Merged text elements
        """
        if not elements:
            return []

        # Sort by y, then x
        sorted_elements = sorted(elements, key=lambda e: (e.bounds[1], e.bounds[0]))

        merged = []
        current_group = [sorted_elements[0]]

        for elem in sorted_elements[1:]:
            last = current_group[-1]

            # Check if on same line (similar y) and close horizontally
            y_diff = abs(elem.bounds[1] - last.bounds[1])
            x_gap = elem.bounds[0] - last.bounds[2]

            if y_diff < y_threshold and 0 <= x_gap < x_threshold:
                # Same line, add to group
                current_group.append(elem)
            else:
                # New line, merge current group and start new
                merged.append(self._merge_text_group(current_group))
                current_group = [elem]

        # Don't forget last group
        if current_group:
            merged.append(self._merge_text_group(current_group))

        return merged

    def _merge_text_group(self, group: List[TextElement]) -> TextElement:
        """Merge a group of text elements into one."""
        if len(group) == 1:
            return group[0]

        # Combine text with spaces
        combined_text = " ".join(e.text for e in group)

        # Merge bounding boxes
        x1 = min(e.bounds[0] for e in group)
        y1 = min(e.bounds[1] for e in group)
        x2 = max(e.bounds[2] for e in group)
        y2 = max(e.bounds[3] for e in group)

        # Average confidence
        avg_conf = sum(e.confidence for e in group) / len(group)

        return TextElement(
            id=group[0].id,
            text=combined_text,
            bounds=(x1, y1, x2, y2),
            confidence=avg_conf
        )


def detect_text(
    image: Union[np.ndarray, str],
    engine: str = "easyocr",
    **kwargs
) -> List[dict]:
    """
    Convenience function to detect text in an image.

    Args:
        image: Image (numpy array) or path to image file
        engine: OCR engine to use
        **kwargs: Additional arguments for TextDetector

    Returns:
        List of text element dictionaries
    """
    detector = TextDetector(ocr_engine=engine, **kwargs)
    elements = detector.detect(image)
    return [e.to_dict() for e in elements]
