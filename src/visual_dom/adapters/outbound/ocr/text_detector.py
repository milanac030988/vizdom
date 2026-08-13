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

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


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

    # Images below this height get upscaled for better OCR on small text
    UPSCALE_THRESHOLD = 1500

    def __init__(
        self,
        ocr_engine: str = "easyocr",
        languages: List[str] = None,
        confidence_threshold: float = 0.2,
        gpu: bool = True,
        upscale: bool = True,
    ):
        """
        Initialize text detector.

        Args:
            ocr_engine: OCR backend ("easyocr", "paddleocr", "tesseract")
            languages: List of language codes (default: ["en"])
            confidence_threshold: Minimum confidence to accept detection
            gpu: Use GPU acceleration if available
            upscale: Auto-upscale small images for better OCR accuracy
        """
        self.ocr_engine = ocr_engine
        self.languages = languages or ["en"]
        self.confidence_threshold = confidence_threshold
        self.gpu = gpu
        self.upscale = upscale
        self._engine = None
        self._text_counter = 0

    def _next_id(self) -> str:
        """Generate next text element ID."""
        self._text_counter += 1
        return f"T{self._text_counter}"

    def _enhance_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance image contrast for better OCR on low-contrast text.

        Applies CLAHE (Contrast Limited Adaptive Histogram Equalization)
        to improve readability of gray text on white/light backgrounds.
        """
        # Convert to LAB color space for luminance-only enhancement
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Apply CLAHE to luminance channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)

        # Merge back
        enhanced_lab = cv2.merge([l_enhanced, a_channel, b_channel])
        enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

        return enhanced

    def _retry_low_confidence_with_tesseract(
        self,
        image: np.ndarray,
        results: List[TextElement],
        scale_factor: float,
    ) -> List[TextElement]:
        """
        Re-OCR low-confidence EasyOCR detections using Tesseract.

        EasyOCR is good at finding text regions but sometimes can't read
        certain fonts. Tesseract often handles system/custom fonts better.

        Args:
            image: The upscaled BGR image (same as what EasyOCR processed)
            results: EasyOCR results with bounds already scaled back to original
            scale_factor: The upscale factor applied to the image
        """
        try:
            import os
            tesseract_paths = [
                r"C:\Program Files\Tesseract-OCR",
                r"C:\Program Files (x86)\Tesseract-OCR",
                r"D:\Program Files\Tesseract-OCR",
            ]
            tesseract_exe = None
            for base in tesseract_paths:
                exe = os.path.join(base, "tesseract.exe")
                if os.path.exists(exe):
                    tessdata = os.path.join(base, "tessdata")
                    if os.path.exists(tessdata):
                        os.environ["TESSDATA_PREFIX"] = tessdata
                    tesseract_exe = exe
                    break

            if not tesseract_exe:
                return results

            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe
        except ImportError:
            return results

        retry_count = 0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        img_h, img_w = gray.shape[:2]

        # Retry threshold — re-OCR anything below this confidence
        retry_threshold = 0.5

        for elem in results:
            if elem.confidence >= retry_threshold:
                continue

            # Convert bounds back to upscaled image coordinates
            if scale_factor > 1.0:
                x1 = int(elem.bounds[0] * scale_factor)
                y1 = int(elem.bounds[1] * scale_factor)
                x2 = int(elem.bounds[2] * scale_factor)
                y2 = int(elem.bounds[3] * scale_factor)
            else:
                x1, y1, x2, y2 = elem.bounds

            # Add proportional padding
            rw = x2 - x1
            rh = y2 - y1
            pad_x = max(4, int(rw * 0.1))
            pad_y = max(4, int(rh * 0.2))
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(img_w, x2 + pad_x)
            y2 = min(img_h, y2 + pad_y)

            region = gray[y1:y2, x1:x2]
            if region.size == 0 or region.shape[0] < 5 or region.shape[1] < 5:
                continue

            # Run tesseract on this region
            try:
                tess_text = pytesseract.image_to_string(
                    region, config='--psm 7'  # Single line mode
                ).strip()

                # Clean up tesseract output (remove trailing |, \n, etc.)
                tess_text = tess_text.replace('|', '').replace('\n', ' ').strip()

                if tess_text and len(tess_text) >= 1:
                    elem.text = tess_text
                    # Boost confidence so it survives the filter
                    elem.confidence = max(elem.confidence, 0.3)
                    retry_count += 1
            except Exception:
                continue

        if retry_count > 0:
            log.info(f"Tesseract re-OCR improved {retry_count} low-confidence detections")

        return results

    def _init_engine(self):
        """Lazy initialization of OCR engine."""
        if self._engine is not None:
            return

        # Text detection disabled: "none"/None/"" is a valid config choice
        # (e.g. detector=omniparser with its own OCR, or a text-free benchmark).
        if self.ocr_engine in (None, "none", ""):
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

        # No OCR engine configured -> no text elements (clean no-op).
        if self.ocr_engine in (None, "none", ""):
            return []

        # Load image if path provided
        if isinstance(image, str):
            image = cv2.imread(image)

        if image is None:
            raise ValueError("Could not load image")

        # Enhance contrast for low-contrast text (gray on white, etc.)
        image = self._enhance_for_ocr(image)

        # Upscale small images for better OCR accuracy on small text
        scale_factor = 1.0
        h, w = image.shape[:2]
        if self.upscale and h < self.UPSCALE_THRESHOLD:
            scale_factor = self.UPSCALE_THRESHOLD / h
            # Cap at 3x to avoid excessive memory usage
            scale_factor = min(scale_factor, 3.0)
            new_w = int(w * scale_factor)
            new_h = int(h * scale_factor)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            log.info(f"OCR upscale: {w}x{h} -> {new_w}x{new_h} ({scale_factor:.1f}x)")

        # Detect based on engine
        if self.ocr_engine == "easyocr":
            results = self._detect_easyocr(image)
        elif self.ocr_engine == "paddleocr":
            results = self._detect_paddleocr(image)
        elif self.ocr_engine == "tesseract":
            results = self._detect_tesseract(image)
        else:
            results = []

        # Scale bounding boxes back to original coordinates
        if scale_factor > 1.0:
            for r in results:
                x1, y1, x2, y2 = r.bounds
                r.bounds = (
                    int(x1 / scale_factor),
                    int(y1 / scale_factor),
                    int(x2 / scale_factor),
                    int(y2 / scale_factor),
                )

        # For EasyOCR: re-OCR low confidence regions with Tesseract
        if self.ocr_engine == "easyocr":
            results = self._retry_low_confidence_with_tesseract(image, results, scale_factor)

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

    # Horizontal gap that may still be one phrase, as a fraction of the text
    # height. Inter-word spaces run about a quarter to a third of the cap height;
    # 0.45 leaves headroom for wide tracking without reaching the gap that
    # separates two independent labels.
    GAP_HEIGHT_RATIO = 0.45
    # Floor for tiny text, where the ratio would fall below one pixel.
    MIN_GAP_PX = 3
    # Two boxes are on the same line when they overlap this much vertically,
    # measured against the shorter box.
    LINE_OVERLAP_MIN = 0.5

    @staticmethod
    def _vertical_overlap_ratio(a: Tuple[int, int, int, int],
                                b: Tuple[int, int, int, int]) -> float:
        """Vertical intersection of two boxes over the shorter box's height."""
        overlap = min(a[3], b[3]) - max(a[1], b[1])
        if overlap <= 0:
            return 0.0
        shorter = min(a[3] - a[1], b[3] - b[1])
        return overlap / shorter if shorter > 0 else 0.0

    def _merge_text_boxes(
        self,
        elements: List[TextElement],
        gap_height_ratio: float = None,
        min_gap_px: int = None,
        line_overlap_min: float = None,
    ) -> List[TextElement]:
        """
        Merge OCR fragments that belong to the same word or phrase.

        The gap that separates two fragments of one phrase scales with the text:
        a space is roughly a quarter to a third of the cap height. This used to
        be a fixed 20 px, which at 14 px text also swallowed the 13 px gaps
        between three *distinct* links — "Printer Management >", "Docupedia >",
        "My IT Profile >" came back as one 295 px element (session
        20260807_094630, E71), which no test can click and no locator can
        address. Scaling the threshold with the line height keeps character-level
        splits merging while leaving separate labels alone.

        Same-line membership is decided by real vertical overlap rather than by
        similar top edges: a taller neighbour (a heading, a boxed label) can sit
        within 10 px of a line's top without being on it.

        Args:
            elements: detected text elements
            gap_height_ratio: max gap as a fraction of text height
            min_gap_px: absolute floor for the gap, for very small text
            line_overlap_min: min vertical overlap to count as the same line

        Returns:
            Merged text elements
        """
        if not elements:
            return []

        gap_ratio = (self.GAP_HEIGHT_RATIO if gap_height_ratio is None
                     else gap_height_ratio)
        gap_floor = self.MIN_GAP_PX if min_gap_px is None else min_gap_px
        overlap_min = (self.LINE_OVERLAP_MIN if line_overlap_min is None
                       else line_overlap_min)

        # Two passes: rows first, then left-to-right within each row. A single
        # y-then-x sort visits boxes with jittered tops ("Remove" at y=466,
        # "Add" at y=468) in the wrong x order, the gap goes negative, and a
        # genuine split is missed.
        #
        # Membership is judged against the ROW'S BAND (mean y1..y2 of members),
        # not the last member appended: chaining member-to-member lets a tall
        # box drag the row downward until it swallows the next line - on the
        # IWT screen, 'Application Control' (h=17) bridged to '(BlackList)' one
        # line below, which then sat between 'Low' and 'Protection' in x-order
        # and broke their merge.
        ordered = sorted(elements,
                         key=lambda e: ((e.bounds[1] + e.bounds[3]) / 2, e.bounds[0]))
        rows: List[List[TextElement]] = []
        bands: List[Tuple[float, float]] = []      # running mean (y1, y2) per row
        for elem in ordered:
            y1, y2 = elem.bounds[1], elem.bounds[3]
            if rows:
                by1, by2 = bands[-1]
                band = (0, int(by1), 0, int(by2))
                if self._vertical_overlap_ratio(band, elem.bounds) >= overlap_min:
                    row = rows[-1]
                    row.append(elem)
                    n = len(row)
                    bands[-1] = (by1 + (y1 - by1) / n, by2 + (y2 - by2) / n)
                    continue
            rows.append([elem])
            bands.append((float(y1), float(y2)))

        merged = []
        for row in rows:
            row.sort(key=lambda e: e.bounds[0])
            group = [row[0]]
            for elem in row[1:]:
                last = group[-1]
                # Scale by the shorter box: merging small text into a tall
                # heading should be judged by the small text's own spacing.
                limit = max(gap_floor, gap_ratio * min(last.height, elem.height))
                x_gap = elem.bounds[0] - last.bounds[2]
                if 0 <= x_gap <= limit:
                    group.append(elem)
                else:
                    # A gap too wide - or negative, meaning overlapping boxes,
                    # which are dedup's concern, not line assembly's.
                    merged.append(self._merge_text_group(group))
                    group = [elem]
            merged.append(self._merge_text_group(group))

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
