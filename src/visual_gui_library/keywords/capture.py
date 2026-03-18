"""
Screen capture and DOM generation keywords.
"""

import json
from typing import Optional, Any, Tuple
from robot.api.deco import keyword
import numpy as np


class CaptureKeywords:
    """Keywords for screen capture and Visual DOM generation."""

    def __init__(self):
        self._current_dom = None
        self._current_screenshot = None
        self._finder = None

    def _get_adapter(self):
        """Get platform adapter - to be overridden by main class."""
        raise NotImplementedError("Subclass must implement _get_adapter")

    @keyword("Capture Screen")
    def capture_screen(self, region: Optional[str] = None) -> np.ndarray:
        """
        Capture the current screen.

        Args:
            region: Optional region to capture (x,y,width,height)

        Returns:
            Screenshot as numpy array (BGR)

        Example:
            | ${img}= | Capture Screen |
            | ${img}= | Capture Screen | region=0,0,800,600 |
        """
        adapter = self._get_adapter()

        region_tuple = None
        if region:
            parts = [int(x.strip()) for x in region.split(",")]
            if len(parts) == 4:
                region_tuple = tuple(parts)

        screenshot = adapter.capture_screen(region=region_tuple)
        self._current_screenshot = screenshot
        return screenshot

    @keyword("Dump Visual DOM")
    def dump_visual_dom(
        self,
        image: Optional[np.ndarray] = None,
        ocr_engine: str = "tesseract",
        use_llm: bool = False,
        llm_model: str = "ollama",
        save_path: Optional[str] = None
    ) -> dict:
        """
        Generate Visual DOM JSON from screenshot.

        Args:
            image: Screenshot to analyze (captures new if None)
            ocr_engine: OCR engine (tesseract, easyocr, paddleocr)
            use_llm: Whether to use LLM for hierarchy refinement
            llm_model: LLM model name if use_llm is True
            save_path: Optional path to save DOM JSON

        Returns:
            Compiled Visual DOM dictionary

        Example:
            | ${dom}= | Dump Visual DOM |
            | ${dom}= | Dump Visual DOM | ocr_engine=tesseract |
            | ${dom}= | Dump Visual DOM | use_llm=True | llm_model=ollama |
        """
        # Import visual_dom modules
        from visual_dom.cv.pipeline import VisualDOMPipeline
        from visual_dom.hierarchy import CoarseHierarchyBuilder, LLMHierarchyRefiner
        from visual_dom.compiler import DOMCompiler

        # Capture if needed
        if image is None:
            image = self.capture_screen()

        height, width = image.shape[:2]

        # Run CV pipeline
        pipeline = VisualDOMPipeline(ocr_engine=ocr_engine)
        cv_result = pipeline.process(image, detect_text=True, detect_elements=True)

        # Build coarse hierarchy
        builder = CoarseHierarchyBuilder()
        hierarchy = builder.build(cv_result["elements"])

        elements = cv_result["elements"]

        # Optional LLM refinement
        if use_llm:
            try:
                refiner = LLMHierarchyRefiner(model_name=llm_model)
                llm_result = refiner.refine(
                    elements=elements,
                    hierarchy=hierarchy["root"],
                    image_size=(width, height),
                )
                elements = llm_result["refined_elements"]
            except Exception as e:
                print(f"LLM refinement failed: {e}")

        # Compile DOM
        compiler = DOMCompiler(generate_locators=True)
        dom = compiler.compile(
            elements=elements,
            hierarchy=hierarchy["root"],
            image_size=(width, height),
        )

        # Save if requested
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(dom, f, indent=2, ensure_ascii=False)

        # Store for later use
        self._current_dom = dom
        self._update_finder()

        return dom

    def _update_finder(self):
        """Update element finder with current DOM."""
        if self._current_dom:
            from ..locators import ElementFinder
            self._finder = ElementFinder(self._current_dom)

    @keyword("Load Visual DOM")
    def load_visual_dom(self, path: str) -> dict:
        """
        Load a previously saved Visual DOM JSON file.

        Args:
            path: Path to DOM JSON file

        Returns:
            Visual DOM dictionary

        Example:
            | ${dom}= | Load Visual DOM | dom.json |
        """
        with open(path, "r", encoding="utf-8") as f:
            dom = json.load(f)

        self._current_dom = dom
        self._update_finder()

        return dom

    @keyword("Get Visual Element")
    def get_visual_element(self, locator: str) -> dict:
        """
        Get element metadata from current DOM.

        Args:
            locator: Element locator string

        Returns:
            Element metadata dictionary

        Example:
            | ${elem}= | Get Visual Element | text=Login |
            | Log | Element bounds: ${elem['bounds']} |
        """
        if not self._finder:
            raise RuntimeError("No DOM loaded. Call 'Dump Visual DOM' first.")

        from ..locators import LocatorParser
        locators = LocatorParser.parse(locator)
        element = self._finder.find_one(locators)

        if element is None:
            raise ValueError(f"Element not found: {locator}")

        return element

    @keyword("Get Visual Elements")
    def get_visual_elements(self, locator: str) -> list:
        """
        Get all elements matching locator.

        Args:
            locator: Element locator string

        Returns:
            List of matching element dictionaries

        Example:
            | @{buttons}= | Get Visual Elements | role=button |
        """
        if not self._finder:
            raise RuntimeError("No DOM loaded. Call 'Dump Visual DOM' first.")

        from ..locators import LocatorParser
        locators = LocatorParser.parse(locator)
        return self._finder.find(locators)

    @keyword("Get Element Center")
    def get_element_center(self, locator: str) -> Tuple[int, int]:
        """
        Get center coordinates of an element.

        Args:
            locator: Element locator string

        Returns:
            Tuple (x, y) of center coordinates

        Example:
            | ${x} | ${y}= | Get Element Center | text=Login |
        """
        element = self.get_visual_element(locator)
        center = element.get("center", [0, 0])
        return tuple(center)

    @keyword("Element Should Exist")
    def element_should_exist(self, locator: str) -> None:
        """
        Verify element exists in DOM.

        Args:
            locator: Element locator string

        Example:
            | Element Should Exist | text=Login |
        """
        if not self._finder:
            raise RuntimeError("No DOM loaded. Call 'Dump Visual DOM' first.")

        from ..locators import LocatorParser
        locators = LocatorParser.parse(locator)
        matches = self._finder.find(locators)

        if not matches:
            raise AssertionError(f"Element not found: {locator}")

    @keyword("Element Should Not Exist")
    def element_should_not_exist(self, locator: str) -> None:
        """
        Verify element does not exist in DOM.

        Args:
            locator: Element locator string

        Example:
            | Element Should Not Exist | text=Error |
        """
        if not self._finder:
            raise RuntimeError("No DOM loaded. Call 'Dump Visual DOM' first.")

        from ..locators import LocatorParser
        locators = LocatorParser.parse(locator)
        matches = self._finder.find(locators)

        if matches:
            raise AssertionError(f"Element unexpectedly found: {locator}")
