"""
Screen capture and DOM generation keywords.
"""

import json
from typing import Optional, Any, Tuple
from robot.api.deco import keyword
import numpy as np

# Sentinel so `Get Element Property` can tell "no default given" (-> raise on a
# missing property) apart from "default is None / empty" (-> return it).
_UNSET = object()


class CaptureKeywords:
    """Keywords for screen capture and Visual DOM generation."""

    def __init__(self):
        self._current_dom = None
        self._current_screenshot = None
        self._finder = None
        # Session config supplied by the `Connect` keyword (ADR-020). When set,
        # `Dump Visual DOM` builds the DOM through this pre-configured session
        # instead of the ad-hoc default pipeline.
        self._session = None
        self._session_config = None

    def _get_capture(self):
        """Get the visual_dom capture strategy - provided by VisualGuiLibrary."""
        raise NotImplementedError("VisualGuiLibrary provides _get_capture")

    @keyword("Connect")
    def connect(self, config: Optional[str] = None) -> dict:
        """
        Start a configured VizDOM session for this suite (ADR-020).

        This is the recommended first step. Give it the path to a JSON config
        file (see ``python -m visual_dom.config --init``) and every subsequent
        ``Dump Visual DOM`` uses that config for all stages: detector/OCR choice
        and parameters, Stage 2.5 merge/dedup, Stage 3 hierarchy, filters, the
        optional refiner, and capture. Call with no argument for all-defaults.

        The config's ``capture`` section (strategy/target/camera_mode) is also
        applied to this library's capture port, so a single file configures both
        DOM generation and screen acquisition.

        Args:
            config: Path to a VizDOM JSON config file, or ``None`` for defaults.

        Returns:
            The resolved config as a dictionary (handy for logging/asserts).

        Example:
            | Connect | vizdom.config.json |
            | Dump Visual DOM |
            | Click Visual | text=Login |

            | # defaults, no file:
            | Connect |
        """
        from visual_dom.config import VizDomConfig
        from visual_dom.session import Session

        cfg = VizDomConfig.load(config)
        self._session_config = cfg
        self._session = Session(cfg)

        # Apply the capture section to this library's capture port so one config
        # drives both DOM generation and screen acquisition. Only override when
        # the config actually specifies a strategy; otherwise keep the library's
        # platform-derived default. Reset any cached capture so it rebuilds.
        cap = cfg.capture
        if cap.strategy and hasattr(self, "_capture_name"):
            self._capture_name = cap.strategy
            self._capture_kwargs = {"target": cap.target} if cap.target else {}
            self._capture = None

        return cfg.to_dict()

    @keyword("Capture Screen")
    def capture_screen(self, region: Optional[str] = None) -> np.ndarray:
        """
        Capture the current screen via the configured capture strategy
        (visual_dom.capture: windows/linux/android/camera/grpc/<plugin>).

        Args:
            region: Optional region to crop, "x,y,width,height"

        Returns:
            Screenshot as numpy array (BGR)

        Example:
            | ${img}= | Capture Screen |
            | ${img}= | Capture Screen | region=0,0,800,600 |
        """
        screenshot = self._get_capture().capture()

        if region:
            parts = [int(x.strip()) for x in region.split(",")]
            if len(parts) == 4:
                x, y, w, h = parts
                screenshot = screenshot[y:y + h, x:x + w]

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

        If a session was started with ``Connect``, that config drives all stages
        and the ``ocr_engine`` / ``use_llm`` / ``llm_model`` arguments here are
        ignored (they only apply to the ad-hoc default path used when no
        ``Connect`` was called).

        Example:
            | # preferred: configure once, then just dump
            | Connect | vizdom.config.json |
            | ${dom}= | Dump Visual DOM |
            |
            | # ad-hoc (no Connect): per-call arguments
            | ${dom}= | Dump Visual DOM | ocr_engine=tesseract |
            | ${dom}= | Dump Visual DOM | use_llm=True | llm_model=ollama |
        """
        # Capture if needed
        if image is None:
            image = self.capture_screen()

        # Preferred path: a session was configured via `Connect`.
        if self._session is not None:
            dom = self._session.analyze(image, save_path=save_path)
            self._current_dom = dom
            self._update_finder()
            return dom

        # Ad-hoc fallback: build a default pipeline from the call arguments.
        from visual_dom.cv.pipeline import VisualDOMPipeline
        from visual_dom.hierarchy import CoarseHierarchyBuilder, LLMHierarchyRefiner
        from visual_dom.compiler import DOMCompiler

        height, width = image.shape[:2]

        pipeline = VisualDOMPipeline(ocr_engine=ocr_engine)
        cv_result = pipeline.process(image, detect_text=True, detect_elements=True)

        builder = CoarseHierarchyBuilder()
        hierarchy = builder.build(cv_result["elements"])

        elements = cv_result["elements"]

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

        compiler = DOMCompiler(generate_locators=True)
        dom = compiler.compile(
            elements=elements,
            hierarchy=hierarchy["root"],
            image_size=(width, height),
        )

        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(dom, f, indent=2, ensure_ascii=False)

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

    @keyword("Get Element Property")
    def get_element_property(
        self,
        locator: str,
        name: str,
        default: Any = _UNSET,
    ) -> Any:
        """
        Get a single property of a visual element from the current DOM.

        Reads one field of the element matched by ``locator``. Common properties:
        ``text``, ``label``, ``hint``, ``role``, ``visual_type``, ``bounds``,
        ``center``, ``clickable``, ``editable``, ``scrollable``, ``confidence``,
        ``id``. Property names are case-insensitive. A generated locator can be
        read with a dotted name, e.g. ``locators.text``.

        Some properties (``text``, ``hint``, ``label``, ``locators``) exist only
        when the element actually has them. If the requested property is absent
        and no ``default`` is given, the keyword fails and lists the available
        properties; pass ``default`` to get a fallback value instead.

        Args:
            locator: Element locator string (e.g. ``text=Login``).
            name: Property name to read (case-insensitive).
            default: Value to return when the property is absent. If omitted, an
                absent property raises an error.

        Returns:
            The property value.

        Example:
            | ${label}=     | Get Element Property | text=Login     | label |
            | ${role}=      | Get Element Property | id=E12         | role  |
            | ${clickable}= | Get Element Property | text=Submit    | clickable |
            | ${hint}=      | Get Element Property | role=textField | hint | default=${EMPTY} |
        """
        element = self.get_visual_element(locator)
        return self._read_property(element, name, default, locator)

    def _read_property(self, element: dict, name: str, default: Any, locator: str) -> Any:
        """Resolve a (possibly dotted, case-insensitive) property name on an element."""
        key = (name or "").strip()

        if "." in key:
            # dotted access into a sub-dict, e.g. "locators.text"
            head, tail = key.split(".", 1)
            sub = element.get(head)
            if isinstance(sub, dict):
                lower = {k.lower(): k for k in sub}
                if tail.lower() in lower:
                    return sub[lower[tail.lower()]]
        else:
            lower = {k.lower(): k for k in element}
            if key.lower() in lower:
                return element[lower[key.lower()]]
            # convenience: fall through into the 'locators' sub-dict
            locs = element.get("locators") or {}
            locs_lower = {k.lower(): k for k in locs}
            if key.lower() in locs_lower:
                return locs[locs_lower[key.lower()]]

        if default is not _UNSET:
            return default

        available = sorted(element.keys())
        locs = element.get("locators") or {}
        if locs:
            available += [f"locators.{k}" for k in sorted(locs)]
        raise ValueError(
            f"Property '{name}' not found on element (locator: {locator}). "
            f"Available: {', '.join(available)}"
        )

    @keyword("Get Element Text")
    def get_element_text(self, locator: str, default: Any = _UNSET) -> str:
        """
        Get the OCR/visible text of an element (convenience for
        ``Get Element Property  <locator>  text``).

        Example:
            | ${txt}= | Get Element Text | id=E12 |
            | ${txt}= | Get Element Text | role=staticText | default=${EMPTY} |
        """
        element = self.get_visual_element(locator)
        return self._read_property(element, "text", default, locator)

    @keyword("Get Element Label")
    def get_element_label(self, locator: str, default: Any = _UNSET) -> str:
        """
        Get the associated label of an element (convenience for
        ``Get Element Property  <locator>  label``).

        Example:
            | ${label}= | Get Element Label | role=textField |
        """
        element = self.get_visual_element(locator)
        return self._read_property(element, "label", default, locator)

    # Existence assertions live in AssertionKeywords as the canonical
    # 'Visual Should Exist' / 'Visual Should Not Exist' (they add a custom
    # `message` and refresh-aware 'Wait Until Visual ...' companions).
