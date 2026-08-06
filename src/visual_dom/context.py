"""
VizDOM session API (ADR-020).

``connect()`` is the single entry point a client uses to start a session: give it
a config (a JSON file path, a dict, a :class:`~visual_dom.config.VizDomConfig`, or
nothing for defaults) and it returns a :class:`Session` whose ``analyze(image)``
turns a screenshot into a compiled Visual DOM using that config for every stage.

    from visual_dom import connect

    session = connect("vizdom.config.json")   # or connect() for defaults
    dom = session.analyze("screenshot.png")

The heavy objects (detector backend, OCR engine, optional refiner) are built once
when the session is created and reused across ``analyze`` calls, so a test suite
pays the model-load cost once. The Robot Framework ``Connect`` keyword is a thin
wrapper over this same object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

from visual_dom.config import VizDomConfig
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)

ConfigSource = Union[str, Path, Dict[str, Any], VizDomConfig, None]


class Session:
    """
    A configured VizDOM analysis session.

    Holds the resolved :class:`VizDomConfig` and the constructed pipeline /
    hierarchy builder / compiler. Reused across images.
    """

    def __init__(self, config: VizDomConfig):
        self.config = config
        self._pipeline = self._build_pipeline(config)
        self._compiler = self._build_compiler(config)

    # ---- construction of stage components -------------------------------- #

    @staticmethod
    def _build_pipeline(cfg: VizDomConfig):
        from visual_dom.core.domain.pipeline import VisualDOMPipeline

        det = cfg.detector
        detector_kwargs: Dict[str, Any] = {}
        if det.backend == "omniparser":
            if det.omniparser_icon_detect_path:
                detector_kwargs["icon_detect_path"] = det.omniparser_icon_detect_path
            if det.omniparser_icon_caption_path:
                detector_kwargs["icon_caption_path"] = det.omniparser_icon_caption_path
            detector_kwargs["box_threshold"] = det.omniparser_box_threshold
        elif det.backend == "grpc":
            # Detector runs as a remote gRPC service (ADR-017); point at it.
            detector_kwargs["target"] = det.grpc_target

        return VisualDOMPipeline(
            # Stage 1 - OCR
            ocr_engine=cfg.ocr.engine,
            ocr_languages=list(cfg.ocr.languages),
            confidence_threshold=cfg.detector.confidence_threshold,
            use_gpu=cfg.detector.use_gpu,
            # Stage 2 - detector
            detector=det.backend,
            yolo_model_path=det.yolo_model_path,
            detector_kwargs=detector_kwargs,
            text_ensemble=det.omniparser_text_ensemble,
            # Stage 2.5 - merge & deduplicate
            iou_threshold=cfg.merge.nms_iou_threshold,
            cross_type_iou=cfg.merge.cross_type_iou,
            duplicate_tolerance_px=cfg.merge.duplicate_tolerance_px,
            merge_oversegmented=cfg.merge.merge_oversegmented,
            group_fill_ratio_min=cfg.merge.group_fill_ratio_min,
            # Stage 3 - hierarchy (in-pipeline pass)
            hierarchy_containment_threshold=cfg.hierarchy.containment_threshold,
            # Stage 4c - symbol reading
            detect_symbols=cfg.symbols.enabled,
            symbol_min_score=cfg.symbols.min_score,
            # filters
            min_element_area=cfg.filter.min_element_area,
            min_element_size=cfg.filter.min_element_size,
            max_elements=cfg.filter.max_elements,
            # capture
            camera_mode=cfg.capture.camera_mode,
            # Stage 8 - optional refiner (SLM advisor)
            slm_backend=(cfg.refiner.backend if cfg.refiner.enabled else None),
            slm_model=cfg.refiner.model,
            slm_host=cfg.refiner.host,
        )

    @staticmethod
    def _build_compiler(cfg: VizDomConfig):
        from visual_dom.core.domain.compiler import DOMCompiler
        return DOMCompiler(generate_locators=cfg.output.generate_locators)

    def _build_hierarchy_builder(self):
        from visual_dom.core.domain.hierarchy import CoarseHierarchyBuilder
        h = self.config.hierarchy
        return CoarseHierarchyBuilder(
            containment_threshold=h.containment_threshold,
            min_containment_margin=h.min_containment_margin,
        )

    # ---- public API ------------------------------------------------------ #

    def analyze(
        self,
        image: Union[np.ndarray, str, Path],
        save_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        Run the full pipeline on ``image`` and return a compiled Visual DOM dict.

        Args:
            image: a BGR numpy array or a path to an image file.
            save_path: optional path to also write the DOM JSON to.
        """
        import cv2
        import json

        if isinstance(image, (str, Path)):
            img = cv2.imread(str(image))
            if img is None:
                raise ValueError(f"Could not load image: {image}")
        else:
            img = image
        height, width = img.shape[:2]

        cv_result = self._pipeline.process(img, detect_text=True, detect_elements=True)
        elements = cv_result["elements"]

        builder = self._build_hierarchy_builder()
        hierarchy = builder.build(elements)

        # Optional LLM hierarchy refinement (Stage 3b) when configured.
        if self.config.hierarchy.use_llm:
            try:
                from visual_dom.core.domain.hierarchy import LLMHierarchyRefiner
                refiner = LLMHierarchyRefiner(model_name=self.config.hierarchy.llm_model)
                refined = refiner.refine(
                    elements=elements,
                    hierarchy=hierarchy["root"],
                    image_size=(width, height),
                )
                elements = refined["refined_elements"]
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM hierarchy refinement failed: %s", exc)

        dom = self._compiler.compile(
            elements=elements,
            hierarchy=hierarchy["root"],
            image_size=(width, height),
        )

        if save_path:
            with open(save_path, "w", encoding="utf-8") as fh:
                json.dump(dom, fh, indent=2, ensure_ascii=False)

        return dom


def connect(config: ConfigSource = None) -> Session:
    """
    Start a VizDOM session from a config.

    Args:
        config: a path to a JSON config file, a config dict, a
            :class:`VizDomConfig`, or ``None`` for all defaults.

    Returns:
        A :class:`Session` ready for ``analyze(image)``.

    Example::

        from visual_dom import connect
        session = connect("vizdom.config.json")
        dom = session.analyze("screen.png")
    """
    cfg = VizDomConfig.load(config)
    log.info("VizDOM session connected (detector=%s, ocr=%s, refiner=%s)",
             cfg.detector.backend, cfg.ocr.engine,
             cfg.refiner.backend if cfg.refiner.enabled else "off")
    return Session(cfg)
