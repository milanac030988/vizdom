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
        # Post-action staleness (ADR-023): actions set this; a cache read
        # (refresh=none) while stale logs a warning. Dump/Load clear it.
        self._dom_stale = False
        self._refresh_ocr = None  # lazy TextDetector for element-region re-OCR

    def _get_capture(self):
        """Get the visual_dom capture strategy - provided by VisualGuiLibrary."""
        raise NotImplementedError("VisualGuiLibrary provides _get_capture")

    # --- post-action recap (ADR-023) -----------------------------------------

    def _mark_dom_stale(self):
        """Called by action keywords: the screen may no longer match the DOM."""
        self._dom_stale = True

    def _warn_if_stale(self, keyword_name: str):
        if self._dom_stale:
            print(f"WARN: {keyword_name} is reading a DOM captured BEFORE the last "
                  f"action - the value may be stale. Pass refresh=element (or "
                  f"refresh=screen), use 'Verify Element Value', or re-run "
                  f"'Dump Visual DOM'.")

    # --- application focus (ADR-021) -----------------------------------------

    def _grab_frame(self):
        """
        One screen grab, honouring the configured window scope (ADR-021).

        Returns the BGR image and records the capture geometry on the library
        (`self._capture_frame`), which `_norm_xy` uses to map coordinates measured
        on a crop back to the device's own space. Every grab in the session must go
        through here: mixing a window-scoped capture with a full-screen one would
        invalidate cached element bounds (notably the recap re-grab, ADR-023).
        """
        cap = self._get_capture()
        if getattr(self, "_window_scope", False) and getattr(self, "_app_title", None):
            frame = None
            try:
                frame = cap.capture_window(self._app_title)
            except Exception as exc:      # a strategy should not raise; be safe
                print(f"WARN: window capture failed ({exc}); using the full screen")
            if frame is not None:
                self._capture_frame = frame
                return frame.image
            print(f"WARN: capture strategy '{cap.name}' could not capture "
                  f"{self._app_title!r} alone (unsupported, not found, or it could "
                  f"not be raised) - falling back to a full-screen grab. Element "
                  f"coordinates stay correct; the DOM will include other windows.")
        self._focus_before_grab()
        image = cap.capture()
        # A full-screen grab also has a place in the device space: the monitor it
        # came from may not start at (0, 0) on a multi-monitor desktop. Strategies
        # that report None (e.g. Android, where the capture buffer and the input
        # resolution can differ) keep the proportional image-space mapping.
        self._capture_frame = None
        try:
            geometry = cap.frame_geometry()
        except Exception:
            geometry = None
        if geometry:
            from visual_dom.core.ports.outbound.capture_port import CaptureFrame
            origin, device_origin, device_size = geometry
            self._capture_frame = CaptureFrame(
                image=image, origin=tuple(origin),
                device_size=tuple(device_size), device_origin=tuple(device_origin))
        return image

    def _focus_before_grab(self):
        """
        Opt-in hygiene before a screen grab: raise the SUT so we photograph IT and
        not whatever window is on top (``capture.focus_before_capture``).

        A failure only warns: the grab may still be perfectly usable, and one
        transient foreground lock should not abort a suite. Use the explicit
        `Bring App To Front` keyword where the raise must be fatal.
        """
        if not getattr(self, "_focus_before_capture", False):
            return
        if not getattr(self, "_app_title", None):
            print("WARN: focus_before_capture is enabled but no window title is "
                  "set - nothing to raise. Set capture.window_title in the config.")
            return
        self.bring_app_to_front(required=False)

    def _get_refresh_ocr(self):
        """TextDetector for element-region re-OCR, created once and reused."""
        if self._session is not None:
            # Reuse the session pipeline's already-loaded OCR engine.
            td = getattr(self._session._pipeline, "text_detector", None)
            if td is not None and getattr(td, "ocr_engine", None) not in (None, "none", ""):
                return td
        if self._refresh_ocr is None:
            from visual_dom.adapters.outbound.ocr.text_detector import TextDetector
            engine = getattr(self, "ocr_engine", None) or "tesseract"
            self._refresh_ocr = TextDetector(ocr_engine=engine, upscale=True)
        return self._refresh_ocr

    def _refresh_element(self, element: dict, pad: int = 8) -> dict:
        """
        Element-region recap: re-capture the screen, re-OCR ONLY this element's
        bounds (+pad), and update the element's text in the cached DOM.

        Cheap (no detector / hierarchy rebuild) and typically MORE accurate than
        the full-screen pass, because the small crop gets the OCR upscaling
        treatment. Updates one element only - if the whole layout may have
        changed, use refresh=screen / 'Dump Visual DOM' instead.
        """
        shot = self._grab_frame()
        self._current_screenshot = shot
        h, w = shot.shape[:2]
        x1, y1, x2, y2 = element.get("bounds", [0, 0, 0, 0])
        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
        x2, y2 = min(w, x2 + pad), min(h, y2 + pad)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Element bounds {element.get('bounds')} lie outside "
                             f"the captured screen ({w}x{h}).")
        crop = shot[y1:y2, x1:x2]

        # OCR the crop, escalating the upscale on an empty read: EasyOCR's text
        # detection stage regularly drops an ISOLATED small character (a lone "4"
        # on a key reads as nothing at native size but perfectly at 2x), and a
        # single character is precisely what a value recap often looks at. Only
        # the text matters here, not its coordinates, so re-rendering larger is
        # free of side effects.
        import cv2
        texts = []
        for factor in (1, 2, 4):
            probe = crop if factor == 1 else cv2.resize(
                crop, (crop.shape[1] * factor, crop.shape[0] * factor),
                interpolation=cv2.INTER_CUBIC)
            texts = self._get_refresh_ocr().detect(probe)
            if texts:
                break
        # Reading order (top->bottom, left->right), then join the pieces.
        texts.sort(key=lambda t: (t.bounds[1], t.bounds[0]))
        new_text = " ".join(t.text for t in texts if t.text).strip()

        if new_text:
            element["text"] = new_text
        else:
            element.pop("text", None)
        # The finder's text index is now out of date for this element.
        if self._current_dom:
            from ..locators import ElementFinder
            self._finder = ElementFinder(self._current_dom)
        return element

    def _resolve_with_refresh(self, locator: str, refresh: str, keyword_name: str) -> dict:
        """Common locator resolution honouring refresh=none|element|screen."""
        mode = (refresh or "none").strip().lower()
        if mode not in ("none", "element", "screen"):
            raise ValueError(f"refresh must be none|element|screen, got {refresh!r}")
        if mode == "screen":
            self.dump_visual_dom()
            return self.get_visual_element(locator)
        element = self.get_visual_element(locator)
        if mode == "element":
            return self._refresh_element(element)
        self._warn_if_stale(keyword_name)
        return element

    @keyword("Connect")
    def connect(self, config: Optional[str] = None) -> dict:
        """
        Start a configured VizDOM session for this suite (ADR-020).

        This is the recommended first step. Give it the path to a JSON config
        file (see ``python -m visual_dom.config --init``) and every subsequent
        ``Dump Visual DOM`` uses that config for all stages: detector/OCR choice
        and parameters, Stage 2.5 merge/dedup, Stage 3 hierarchy, filters, the
        optional refiner, and capture. Call with no argument for all-defaults.

        The config's ``capture`` and ``actuator`` sections (strategy/target) are
        also applied to this library's ports, so a single file configures all
        three: DOM generation (detector), screen acquisition, and input --- each
        of which may be local or a remote gRPC service.

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
        from visual_dom.context import Session

        cfg = VizDomConfig.load(config)
        self._session_config = cfg
        self._session = Session(cfg)
        self._desc_resolver = None  # grounding config may have changed

        # Apply the capture section to this library's capture port so one config
        # drives both DOM generation and screen acquisition. Only override when
        # the config actually specifies a strategy; otherwise keep the library's
        # platform-derived default. Reset any cached capture so it rebuilds.
        cap = cfg.capture
        if cap.strategy and hasattr(self, "_capture_name"):
            self._capture_name = cap.strategy
            self._capture_kwargs = {"target": cap.target} if cap.target else {}
            self._capture = None

        # Same for the actuator port (ADR-019), so ONE config file drives all
        # three ports - detector (via the session), capture and actuator.
        act = getattr(cfg, "actuator", None)
        if act and act.strategy and hasattr(self, "_actuator_name"):
            self._actuator_name = act.strategy
            self._actuator_kwargs = {"target": act.target} if act.target else {}
            self._actuator = None

        # Application targeting (ADR-021). The title is passed to focus_target()
        # per call rather than into the constructor, so it works identically for a
        # local grabber and for a remote strategy (whose constructor takes no
        # title - the Focus RPC carries it instead).
        if hasattr(self, "_app_title"):
            if cap.window_title:
                self._app_title = cap.window_title
            act_title = getattr(act, "window_title", None) if act else None
            # Both ports normally drive the same app, so the actuator inherits.
            self._actuator_app_title = act_title or self._app_title
            self._focus_before_capture = bool(
                getattr(cap, "focus_before_capture", False)) or self._focus_before_capture
            self._window_scope = bool(
                getattr(cap, "window_scope", False)) or self._window_scope
            if self._window_scope and not self._app_title:
                raise ValueError(
                    "capture.window_scope is enabled but capture.window_title is "
                    "not set - there is no window to scope the capture to.")

        return cfg.to_dict()

    @keyword("Bring App To Front")
    def bring_app_to_front(self, title: Optional[str] = None,
                           required: bool = True) -> bool:
        """
        Raise the application under test so it is the foreground window (ADR-021).

        Why this matters: a screen grab photographs whatever is on top, clicks land
        on whatever window is at that coordinate, and typed text goes to whatever
        holds keyboard focus. If another window covers the SUT, the DOM is built
        from the wrong pixels and the actions go to the wrong application.

        Both ports can focus, so the capture strategy is tried first and the
        actuator second --- that way a setup where only one of them can influence
        the screen (e.g. a camera capture paired with a desktop actuator) still
        works. Success is *verified* by the strategy, never assumed.

        Args:
            title: Window title to raise (Android: package or package/.Activity).
                Defaults to ``capture.window_title`` from the config / the
                library's ``app_title`` argument.
            required: When true (default) an unfocusable target fails the keyword.
                Pass ``${False}`` to downgrade it to a warning and return False.

        Returns:
            True if a strategy confirmed the target is now foreground.

        Example:
            | Bring App To Front | Calculator |
            | Bring App To Front |            | # uses capture.window_title |
            | Dump Visual DOM    |            |

        Note:
            Focusing mutates the SUT (it can dismiss tooltips or transient popups),
            which is why it is an explicit step rather than implicit in every grab.
            Windows may refuse the raise outright (foreground lock) --- that is
            reported as a failure rather than hidden.
        """
        wanted = title or getattr(self, "_app_title", None)
        if not wanted:
            raise ValueError(
                "Bring App To Front needs a window title: pass one, or set "
                "capture.window_title in the config (or app_title= at import).")

        # Per-port titles: the two ports may name the same app differently (an
        # Android capture identifies it by activity, for instance).
        act_title = title or getattr(self, "_actuator_app_title", None) or wanted
        tried = []
        for port_name, getter, port_title in (
                ("capture", self._get_capture, wanted),
                ("actuator", getattr(self, "_get_actuator", None), act_title)):
            if getter is None:
                continue
            try:
                strategy = getter()
            except Exception as exc:      # port not available in this setup
                tried.append(f"{port_name} unavailable ({exc})")
                continue
            if strategy.focus_target(port_title):
                print(f"INFO: brought {wanted!r} to front via the {port_name} port "
                      f"({strategy.name})")
                return True
            tried.append(f"{port_name}={strategy.name} declined")

        message = (f"Could not bring {wanted!r} to the foreground "
                   f"[{'; '.join(tried) or 'no port available'}]. The window may not "
                   f"exist, its title may be ambiguous, or the OS refused the raise.")
        if required:
            raise AssertionError(message)
        print(f"WARN: {message}")
        return False

    @keyword("Take Screenshot")
    def take_screenshot(self, name: str = "vizdom-screenshot") -> str:
        """
        Capture the screen through the configured capture port and embed the
        image in the Robot Framework log.

        Because the grab goes through the capture strategy, it shows the machine
        under test even in a distributed run (``capture=grpc`` fetches the frame
        from the remote capture service), honours ``window_scope`` (the image is
        the application under test, not the whole desktop), and raises the app
        first when focusing is configured.

        With ``screenshot_on_failure`` (default on), every failing keyword of
        this library calls this automatically — the image lands in log.html
        directly under the failing keyword.

        Args:
            name: Base name for the image file (saved in the Robot output dir).

        Returns:
            Path of the written PNG.

        Example:
            | Take Screenshot |
            | Take Screenshot | after-login |
            | # in a teardown, only when the test failed:
            | Run Keyword If Test Failed | Take Screenshot |
        """
        import os
        import re
        import cv2

        shot = self._grab_frame()

        outdir = os.getcwd()
        try:
            from robot.libraries.BuiltIn import BuiltIn
            outdir = BuiltIn().get_variable_value("${OUTPUTDIR}") or outdir
        except Exception:
            pass  # not running under Robot - save to cwd, skip log embedding

        self._shot_index = getattr(self, "_shot_index", 0) + 1
        safe = re.sub(r"[^\w.-]+", "_", name).strip("_") or "vizdom-screenshot"
        filename = f"{safe}-{self._shot_index}.png"
        path = os.path.join(outdir, filename)
        if not cv2.imwrite(path, shot):
            raise RuntimeError(f"could not write screenshot to {path}")

        try:
            from robot.api import logger
            # Relative src keeps log.html portable when the output dir moves.
            logger.info(f'<a href="{filename}"><img src="{filename}" '
                        f'width="800px"></a>', html=True)
        except Exception:
            print(f"Screenshot saved: {path}")
        return path

    @keyword("Set Screenshot On Failure")
    def set_screenshot_on_failure(self, enabled: bool = True) -> bool:
        """
        Turn automatic failure screenshots on or off for this session.

        Returns the previous setting, so a suite can restore it:
        | ${old}= | Set Screenshot On Failure | ${False} |
        | ...     |
        | Set Screenshot On Failure | ${old} |
        """
        previous = getattr(self, "_screenshot_on_failure", True)
        self._screenshot_on_failure = bool(enabled)
        return previous

    @keyword("Capture Screen")
    def capture_screen(self, region: Optional[str] = None) -> np.ndarray:
        """
        Capture the current screen via the configured capture strategy
        (visual_dom.adapters.outbound.capture: windows/linux/android/camera/grpc/<plugin>).

        Args:
            region: Optional region to crop, "x,y,width,height"

        Returns:
            Screenshot as numpy array (BGR)

        Example:
            | ${img}= | Capture Screen |
            | ${img}= | Capture Screen | region=0,0,800,600 |
        """
        screenshot = self._grab_frame()

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
            self._dom_stale = False
            self._update_finder()
            return dom

        # Ad-hoc fallback: build a default pipeline from the call arguments.
        from visual_dom.core.domain.pipeline import VisualDOMPipeline
        from visual_dom.core.domain.hierarchy import CoarseHierarchyBuilder, LLMHierarchyRefiner
        from visual_dom.core.domain.compiler import DOMCompiler

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
        self._dom_stale = False
        self._update_finder()

        return dom

    def _update_finder(self):
        """Update element finder with current DOM."""
        if self._current_dom:
            from ..locators import ElementFinder
            self._finder = ElementFinder(self._current_dom)
            self._desc_resolver = None  # per-screen cache; rebuild lazily

    def _get_desc_resolver(self):
        """DescriptionResolver for the current DOM (ADR-022), built lazily."""
        if getattr(self, "_desc_resolver", None) is None:
            from ..locators.desc_resolver import DescriptionResolver
            g = getattr(self._session_config, "grounding", None) if self._session_config else None
            self._desc_resolver = DescriptionResolver(
                self._current_dom,
                screenshot=self._current_screenshot,
                tiers=(list(g.tiers) if g else None),
                backend=(g.backend if g else "ollama"),
                model=(g.model if g else "qwen2.5:3b"),
                vision_model=(g.vision_model if g else "qwen2.5-vl:3b"),
                host=(g.host if g else "http://localhost:11434"),
            )
        return self._desc_resolver

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
        self._dom_stale = False
        self._update_finder()

        return dom

    def _resolve_alternative(self, locators) -> tuple:
        """
        Resolve ONE alternative (an AND-group of locators) to a single element.

        Returns (element_or_None, reason). `reason` explains a miss so a failed
        chain can report why each alternative did not resolve.
        """
        from ..locators.locator import LocatorStrategy
        try:
            element = self._finder.find_one(locators)
        except ValueError as exc:              # find_one raises on ambiguity
            return None, str(exc)
        if element is not None:
            return element, "ok"

        # desc= escalation (ADR-022): the finder only runs the deterministic
        # lexical tier. If that missed and this alternative is a lone
        # description, escalate through the configured chain (SLM over DOM,
        # optionally VLM Set-of-Mark over the screenshot).
        if len(locators) == 1 and locators[0].strategy == LocatorStrategy.DESC:
            resolver = self._get_desc_resolver()
            element, info = resolver.resolve(locators[0].value)
            if element is not None:
                print(f"desc= resolved by tier '{info['tier']}' "
                      f"({info['reason']}) -> {element.get('id')}")
                return element, "ok"
            cands = ", ".join(str(c) for c in info.get("candidates", [])) or "none"
            return None, f"no grounding tier confident (nearest: {cands})"

        return None, "not found"

    def _disambiguate_with_desc(self, group, rendered: str, desc_values) -> Optional[dict]:
        """
        Ambiguity arbitration (ADR-024): a property locator matched SEVERAL
        elements — let a desc= from the same chain judge which one was meant,
        by grounding the description over just those candidates.

        This runs *before* falling through to the next alternative, because the
        ambiguous matches carry real information: the wanted element is almost
        certainly among them, and a 2-3 element pool is exactly where grounding
        is at its most reliable (even the model-free lexical tier usually
        separates "Plus" from "±"; configured SLM/VLM tiers judge a short,
        focused list). Not confident -> return None and the chain continues
        unchanged, so this can rescue a resolution but never corrupt one.
        """
        try:
            candidates = self._finder.find(group)
        except Exception:
            return None
        if len(candidates) < 2:
            return None
        resolver = self._get_desc_resolver()
        for desc in desc_values:
            element, info = resolver.resolve(desc, within=candidates)
            if element is not None:
                ids = ", ".join(str(c.get("id")) for c in candidates)
                print(f"INFO: '{rendered}' matched {len(candidates)} elements "
                      f"({ids}); desc={desc!r} disambiguated to "
                      f"{element.get('id')} (tier '{info['tier']}', {info['reason']})")
                return element
        return None

    @keyword("Get Visual Element")
    def get_visual_element(self, locator: str) -> dict:
        """
        Get element metadata from current DOM.

        Supports **fallback chains** (ADR-024): alternatives separated by
        ``||`` are tried in order and the first that resolves to exactly one
        element wins. Within an alternative, several locators still mean AND.
        An alternative that finds nothing *or* is ambiguous falls through to the
        next one, so put the cheap deterministic locator first and the
        resilient one last:

            ``text=Save || desc="save button in the toolbar"``

        When a later alternative wins, a warning names the one that failed —
        that is a signal the primary locator has gone stale.

        Args:
            locator: Element locator string, optionally a ``||`` chain

        Returns:
            Element metadata dictionary

        Example:
            | ${elem}= | Get Visual Element | text=Login |
            | ${elem}= | Get Visual Element | text=Login \\|\\| desc="login button" |
        """
        if not self._finder:
            raise RuntimeError("No DOM loaded. Call 'Dump Visual DOM' first.")

        from ..locators import LocatorParser
        from ..locators.locator import LocatorStrategy
        alternatives = LocatorParser.parse_alternatives(locator)
        if not alternatives:
            raise ValueError(f"Could not parse locator: {locator!r}")

        # Descriptions available for AMBIGUITY ARBITRATION: when a property
        # locator matches several elements, a desc= elsewhere in the chain can
        # judge WHICH of those candidates was meant — grounding over 2-3
        # candidates is far more reliable than over the whole DOM, so this
        # rescues chains like `text=+ || desc="plus button"` where the ± key's
        # composite glyph also OCRs as "+".
        desc_values = [g[0].value for g in alternatives
                       if len(g) == 1 and g[0].strategy == LocatorStrategy.DESC]

        attempts = []
        for index, group in enumerate(alternatives):
            element, reason = self._resolve_alternative(group)
            rendered = LocatorParser.render(group)
            if element is None and desc_values and "Multiple elements match" in reason:
                element = self._disambiguate_with_desc(group, rendered, desc_values)
            if element is not None:
                if index > 0:
                    failed = "; ".join(f"{r} ({why})" for r, why in attempts)
                    print(f"WARN: locator fallback — used alternative #{index + 1} "
                          f"'{rendered}' -> {element.get('id')}; earlier alternative(s) "
                          f"failed: {failed}. The primary locator may be stale.")
                return element
            attempts.append((rendered, reason))

        detail = "; ".join(f"#{i + 1} '{r}' -> {why}"
                           for i, (r, why) in enumerate(attempts))
        # "not found" would be wrong when the cause was ambiguity, so state the
        # actual contract that failed: exactly one element.
        if len(attempts) == 1 and attempts[0][1] == "not found":
            raise ValueError(f"Element not found: {locator}")
        raise ValueError(
            f"Locator did not resolve to exactly one element: {locator} "
            f"[tried {detail}]"
        )

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

        # Honours ``||`` fallback chains (ADR-024): the first alternative that
        # matches anything wins; many matches are expected here by design.
        from ..locators import LocatorParser
        for group in LocatorParser.parse_alternatives(locator):
            found = self._finder.find(group)
            if found:
                return found
        return []

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
        refresh: str = "none",
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
            refresh: ``none`` (default) reads the cached DOM; ``element``
                re-captures and re-OCRs ONLY this element's bounds (updates its
                ``text``); ``screen`` re-runs the full Dump Visual DOM first
                (ADR-023). Use ``element``/``screen`` after an action changed
                the screen.

        Returns:
            The property value.

        Example:
            | ${label}=     | Get Element Property | text=Login     | label |
            | ${role}=      | Get Element Property | id=E12         | role  |
            | ${clickable}= | Get Element Property | text=Submit    | clickable |
            | ${hint}=      | Get Element Property | role=textField | hint | default=${EMPTY} |
            | ${value}=     | Get Element Property | hint=Email     | text | refresh=element |
        """
        element = self._resolve_with_refresh(locator, refresh, "Get Element Property")
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
    def get_element_text(self, locator: str, default: Any = _UNSET,
                         refresh: str = "none") -> str:
        """
        Get the OCR/visible text of an element (convenience for
        ``Get Element Property  <locator>  text``). See ``refresh`` on
        `Get Element Property` (ADR-023).

        Example:
            | ${txt}= | Get Element Text | id=E12 |
            | ${txt}= | Get Element Text | role=staticText | default=${EMPTY} |
            | ${txt}= | Get Element Text | hint=Email | refresh=element |
        """
        element = self._resolve_with_refresh(locator, refresh, "Get Element Text")
        return self._read_property(element, "text", default, locator)

    @keyword("Get Element Label")
    def get_element_label(self, locator: str, default: Any = _UNSET,
                          refresh: str = "none") -> str:
        """
        Get the associated label of an element (convenience for
        ``Get Element Property  <locator>  label``). See ``refresh`` on
        `Get Element Property` (ADR-023).

        Example:
            | ${label}= | Get Element Label | role=textField |
        """
        element = self._resolve_with_refresh(locator, refresh, "Get Element Label")
        return self._read_property(element, "label", default, locator)

    @keyword("Get Element Value")
    def get_element_value(self, locator: str, refresh: str = "element") -> str:
        """
        Get an element's CURRENT visible text, re-read from the live screen.

        Unlike `Get Element Text`, this defaults to ``refresh=element``
        (ADR-023): the screen is re-captured and ONLY this element's bounds are
        re-OCR'd, so the value reflects the state AFTER the last action - the
        right keyword for reading back what was just typed. Returns an empty
        string when the region contains no readable text.

        Note: region refresh updates this one element only. If the action may
        have moved the layout or changed other elements, use
        ``refresh=screen`` (full re-analysis) instead.

        Example:
            | Type Text Visual | hint=Email | user@example.com |
            | ${value}= | Get Element Value | hint=Email |
            | Should Be Equal | ${value} | user@example.com |
        """
        element = self._resolve_with_refresh(locator, refresh, "Get Element Value")
        return element.get("text", "") or ""

    @keyword("Verify Element Value")
    def verify_element_value(
        self,
        locator: str,
        expected: str,
        refresh: str = "element",
        exact: bool = False,
        ignore_case: bool = False,
        message: Optional[str] = None,
    ) -> None:
        """
        Assert that an element's CURRENT visible text equals ``expected``,
        re-reading it from the live screen first (``refresh=element`` default,
        ADR-023) - the act -> read back -> assert pattern in one keyword.

        Comparison is whitespace-normalized by default (leading/trailing
        stripped, internal runs collapsed), because OCR spacing is not
        pixel-stable; pass ``exact=True`` for strict equality and
        ``ignore_case=True`` to compare case-insensitively.

        Args:
            locator: Element locator string.
            expected: Expected visible text.
            refresh: ``element`` (default) | ``screen`` | ``none``.
            exact: Strict string equality instead of normalized comparison.
            ignore_case: Case-insensitive comparison.
            message: Custom failure message.

        Example:
            | Type Text Visual     | hint=Email | user@example.com |
            | Verify Element Value | hint=Email | user@example.com |
        """
        element = self._resolve_with_refresh(locator, refresh, "Verify Element Value")
        actual = element.get("text", "") or ""

        def _norm(s: str) -> str:
            if not exact:
                s = " ".join(s.split())
            if ignore_case:
                s = s.lower()
            return s

        if _norm(actual) != _norm(str(expected)):
            raise AssertionError(
                message or
                f"Element value mismatch for {locator}: "
                f"expected {expected!r}, got {actual!r} "
                f"(refresh={refresh}, exact={exact}, ignore_case={ignore_case})"
            )

    # Existence assertions live in AssertionKeywords as the canonical
    # 'Visual Should Exist' / 'Visual Should Not Exist' (they add a custom
    # `message` and refresh-aware 'Wait Until Visual ...' companions).
