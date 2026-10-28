"""
Modular three-stage detector backend (ADR-027).

Composes three independently replaceable stages into one `DetectorBackend`:

    1. RegionProposer  - interactable-region candidates   (boxes + logits)
    2. TextDetector    - full-image OCR                    (reused, ADR-012)
    3. Captioner       - semantic names for icon regions   (optional)

with the fusion logic (a faithful port of OmniParser's `remove_overlap_new`,
see modular_fusion.py) in between. Selected as `detector.backend=modular`;
the existing `omniparser` / `uied` / `yolo` / `grpc` backends are untouched
and remain the baseline (the isolation constraint in ADR-027).

Two properties the monolith could not offer:

* Confidences are NATIVE. Stage 1 hands over its logits directly and OCR
  scores never round-trip through a channel that drops them - the recovery
  machinery of IMPROVEMENTS 3d is unnecessary on this path.
* Stage 3 is skippable (`captioner="none"`): icons then carry no `label`, and
  `desc=` locators fall back to tier-2 VLM grounding (ADR-022) - the price of
  not loading a caption model at all.

Skeleton status (part 2 of the Notion task): the `omniparser` region proposer
and `florence` captioner reuse the vendored weights, `uied` / `none` run with
no weights at all. Ollama-based captioning and a non-AGPL region model are
gated on the hardware decision recorded in ADR-027.
"""

from typing import Any, Dict, List, Optional

import numpy as np

from visual_dom.core.ports.outbound.captioner_port import Captioner
from visual_dom.core.ports.outbound.detector_port import Detection, DetectorBackend
from visual_dom.core.ports.outbound.region_proposer_port import (
    RegionProposal, RegionProposer,
)
from visual_dom.logging_utils import get_logger, log_timing

from .modular_fusion import DEFAULT_REGION_OVERLAP, fuse

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stage 1 implementations
# ---------------------------------------------------------------------------

class OmniParserRegionProposer(RegionProposer):
    """
    OmniParser's icon_detect YOLO as a standalone stage-1 model.

    Reuses the vendored repo + weights but loads ONLY the YOLO - no Florence-2,
    which is the monolith's heavyweight. Paths come from the arguments, then the
    OMNIPARSER_* env vars, then the standard project locations.
    """

    name = "omniparser"
    license = "AGPL-3.0 (icon_detect)"
    requires_gpu = True

    def __init__(self, box_threshold: float = 0.05,
                 icon_detect_path: Optional[str] = None,
                 omniparser_root: Optional[str] = None, **_ignored: Any):
        # Reuse the monolith backend's path resolution and its predict_yolo
        # wrapper - but only the YOLO half of its initialisation.
        from .omniparser_backend import OmniParserBackend
        from .omniparser_paths import resolve_omniparser_paths

        self._box_threshold = box_threshold
        paths = resolve_omniparser_paths(omniparser_root=omniparser_root,
                                         icon_detect_path=icon_detect_path)
        root = paths.get("omniparser_root")
        icon_detect = paths.get("icon_detect_path")
        if not icon_detect:
            raise ValueError(
                "OmniParserRegionProposer needs the icon_detect .pt path "
                "(icon_detect_path or OMNIPARSER_ICON_DETECT).")
        import sys
        if root and root not in sys.path:
            sys.path.insert(0, root)
        import util.utils as omni_utils  # type: ignore

        OmniParserBackend._install_yolo_recorder(omni_utils)
        self._predict = omni_utils.predict_yolo
        self._model = omni_utils.get_yolo_model(model_path=icon_detect)

    def propose(self, image: np.ndarray) -> List[RegionProposal]:
        from PIL import Image
        import cv2

        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        boxes, conf, _phrases = self._predict(
            model=self._model, image=pil, box_threshold=self._box_threshold,
            imgsz=None, scale_img=False, iou_threshold=0.1)
        # round(), not int(): the monolith converts ratio->px with round(), and
        # truncation's off-by-one flipped borderline type classifications
        # (h=22 button vs h=21 input_field) in the parity comparison.
        return [
            RegionProposal(bounds=tuple(int(round(v)) for v in box),
                           confidence=float(c))
            for box, c in zip(boxes.tolist(), conf.tolist())
        ]


class UIEDRegionProposer(RegionProposer):
    """UIED's non-text detections as region proposals. CPU, no weights, no AGPL."""

    name = "uied"
    license = "project"
    requires_gpu = False

    # UIED types that plausibly mark an interactable region.
    _INTERACTABLE = {"button", "input_field", "checkbox", "icon"}

    def __init__(self, min_element_area: int = 100, **_ignored: Any):
        from .uied_detection import UIEDDetector

        self._detector = UIEDDetector(min_element_area=min_element_area)

    def propose(self, image: np.ndarray) -> List[RegionProposal]:
        detected = self._detector.detect(image)
        return [
            RegionProposal(bounds=tuple(d.bounds), confidence=float(d.confidence))
            for d in detected
            if d.element_type.value in self._INTERACTABLE
        ]


# ---------------------------------------------------------------------------
# Stage 3 implementations
# ---------------------------------------------------------------------------

class NoneCaptioner(Captioner):
    """No captions: icons stay unlabelled, desc= uses ADR-022 tier-2 instead."""

    name = "none"
    license = "n/a"

    def __init__(self, **_ignored: Any):
        # Like every stage, accept (and ignore) the OmniParser paths the
        # backend forwards: a bare class broke the default captioner whenever
        # those paths were known.
        pass

    def caption(self, image, boxes):
        return [None] * len(boxes)


class FlorenceCaptioner(Captioner):
    """
    OmniParser's Florence-2 icon captioner as a standalone stage-3 model.

    Feeds crops through the vendored `get_parsed_content_icon`, batched exactly
    as the monolith does (the batching is why this stage is fast enough).
    """

    name = "florence"
    license = "MIT"
    requires_gpu = True

    def __init__(self, batch_size: int = 128,
                 icon_caption_path: Optional[str] = None,
                 omniparser_root: Optional[str] = None, **_ignored: Any):
        import sys

        from .omniparser_paths import resolve_omniparser_paths

        paths = resolve_omniparser_paths(omniparser_root=omniparser_root,
                                         icon_caption_path=icon_caption_path)
        root = paths.get("omniparser_root")
        icon_caption = paths.get("icon_caption_path")
        if not icon_caption:
            raise ValueError(
                "FlorenceCaptioner needs the icon_caption model directory "
                "(icon_caption_path or OMNIPARSER_ICON_CAPTION).")
        if root and root not in sys.path:
            sys.path.insert(0, root)
        import util.utils as omni_utils  # type: ignore

        self._utils = omni_utils
        self._batch_size = batch_size
        self._processor = omni_utils.get_caption_model_processor(
            model_name="florence2", model_name_or_path=icon_caption)

    def caption(self, image, boxes):
        if not boxes:
            return []
        import torch

        height, width = image.shape[:2]
        # get_parsed_content_icon expects ratio-xyxy boxes and captions from
        # `starting_idx` onward; we caption everything we are given.
        ratio = torch.tensor(
            [[x1 / width, y1 / height, x2 / width, y2 / height]
             for (x1, y1, x2, y2) in boxes])
        rgb = image[:, :, ::-1]     # BGR -> RGB array, as the monolith passes
        captions = self._utils.get_parsed_content_icon(
            ratio, 0, rgb, self._processor, batch_size=self._batch_size)
        out: List[Optional[str]] = [str(c).strip() or None if c is not None else None
                                    for c in captions]
        # Defensive: the model must not silently drop entries.
        out += [None] * (len(boxes) - len(out))
        return out[:len(boxes)]


# ---------------------------------------------------------------------------
# Stage factories (registry pattern, small scale)
# ---------------------------------------------------------------------------

_REGION_PROPOSERS = {
    "omniparser": OmniParserRegionProposer,
    "uied": UIEDRegionProposer,
}

_CAPTIONERS = {
    "none": NoneCaptioner,
    "florence": FlorenceCaptioner,
}


def create_region_proposer(name: str, **kwargs: Any) -> RegionProposer:
    """
    Build a stage-1 proposer by name. ``auto`` picks omniparser when its
    weights, repo and ultralytics are all usable, and otherwise degrades the
    STAGE to uied (CPU) with a warning - never the whole backend.
    """
    if name == "auto":
        return _auto_region_proposer(**kwargs)
    try:
        cls = _REGION_PROPOSERS[name]
    except KeyError:
        raise ValueError(f"Unknown region proposer {name!r}; "
                         f"known: {sorted(_REGION_PROPOSERS)}") from None
    return cls(**kwargs)


def _auto_region_proposer(**kwargs: Any) -> RegionProposer:
    from .omniparser_paths import (
        omniparser_unavailable_reason, resolve_omniparser_paths,
    )

    paths = resolve_omniparser_paths(
        omniparser_root=kwargs.get("omniparser_root"),
        icon_detect_path=kwargs.get("icon_detect_path"))
    reason = omniparser_unavailable_reason(
        paths.get("omniparser_root"),
        required={"icon_detect weights": paths.get("icon_detect_path")})
    if reason is None:
        try:
            return OmniParserRegionProposer(**{**kwargs, **paths})
        except Exception as exc:     # weights present but unloadable
            reason = f"loading it failed: {exc}"
    log.warning("modular: omniparser region proposer unavailable (%s) - "
                "using the uied region proposer (CPU)", reason)
    return UIEDRegionProposer(**kwargs)


def create_captioner(name: str, **kwargs: Any) -> Captioner:
    try:
        cls = _CAPTIONERS[name]
    except KeyError:
        raise ValueError(f"Unknown captioner {name!r}; "
                         f"known: {sorted(_CAPTIONERS)}") from None
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# The composite backend
# ---------------------------------------------------------------------------

class ModularDetectorBackend(DetectorBackend):
    """Three pluggable stages + faithful fusion, emitting the standard IR."""

    name = "modular"
    description = ("Composite detector: region proposer + OCR + optional "
                   "captioner, each replaceable (ADR-027).")
    license = "composite (per stage; see list_detectors of each stage)"
    requires_gpu = False    # depends on the chosen stages

    def __init__(
        self,
        region_proposer: Any = "auto",
        ocr_engine: str = "easyocr",
        captioner: Any = "none",
        use_gpu: bool = True,
        region_overlap: float = DEFAULT_REGION_OVERLAP,
        region_kwargs: Optional[Dict[str, Any]] = None,
        captioner_kwargs: Optional[Dict[str, Any]] = None,
        text_detector: Any = None,
        omniparser_root: Optional[str] = None,
        icon_detect_path: Optional[str] = None,
        icon_caption_path: Optional[str] = None,
        box_threshold: Optional[float] = None,
        infer_roles: bool = True,
        **_ignored: Any,
    ):
        """
        Stage arguments accept either a registry name (str) or a ready
        instance - instances make the backend testable without any model and
        let callers share an already-loaded stage.

        ``infer_roles=False`` keeps fusion's raw text/icon split instead of
        recovering button / input_field / checkbox / icon from interactivity,
        geometry and caption: the state of the DOM before that recovery, kept
        as the "roles off" ablation column (benchmarks/README.md sec. 7).

        The OmniParser path arguments and ``box_threshold`` are conveniences
        forwarded to the stages that use them (explicit ``region_kwargs`` /
        ``captioner_kwargs`` entries win), so a flat config or CLI can reach
        them without building the per-stage dicts.
        """
        region_kwargs = dict(region_kwargs or {})
        captioner_kwargs = dict(captioner_kwargs or {})
        for key, value in (("omniparser_root", omniparser_root),
                           ("icon_detect_path", icon_detect_path),
                           ("box_threshold", box_threshold)):
            if value is not None:
                region_kwargs.setdefault(key, value)
        for key, value in (("omniparser_root", omniparser_root),
                           ("icon_caption_path", icon_caption_path)):
            if value is not None:
                captioner_kwargs.setdefault(key, value)
        self._proposer = (region_proposer if isinstance(region_proposer, RegionProposer)
                          else create_region_proposer(str(region_proposer),
                                                      **region_kwargs))
        self._captioner = (captioner if isinstance(captioner, Captioner)
                           else create_captioner(str(captioner),
                                                 **captioner_kwargs))
        if text_detector is not None:
            self._text = text_detector
        else:
            from visual_dom.adapters.outbound.ocr.text_detector import TextDetector

            self._text = TextDetector(ocr_engine=ocr_engine, gpu=use_gpu)
        self._region_overlap = region_overlap
        self._infer_roles = infer_roles
        log.info("Modular detector: regions=%s ocr=%s captioner=%s roles=%s",
                 self._proposer.name, getattr(self._text, "ocr_engine", "?"),
                 self._captioner.name, "inferred" if infer_roles else "raw")

    def detect(self, image: np.ndarray) -> List[Detection]:
        height, width = image.shape[:2]

        with log_timing(log, "modular: stage 1 (regions)"):
            regions = self._proposer.propose(image)
        with log_timing(log, "modular: stage 2 (OCR)"):
            texts = self._text.detect(image)

        fused = fuse(
            [(r.bounds, r.confidence) for r in regions],
            [(t.bounds, t.text, t.confidence) for t in texts],
            region_overlap=self._region_overlap,
        )

        # Stage 3: caption only the icon boxes fusion left unlabelled.
        unlabelled = [f for f in fused if f.kind == "icon" and f.content is None]
        if unlabelled:
            with log_timing(log, f"modular: stage 3 (captions x{len(unlabelled)})"):
                captions = self._captioner.caption(
                    image, [f.bounds for f in unlabelled])
            for f, caption in zip(unlabelled, captions):
                f.content = caption

        # Emit the standard IR. Type inference and the text/label split reuse
        # the monolith backend's mapping so the parity combo compares like with
        # like (same rules, different plumbing).
        from .omniparser_backend import OmniParserBackend

        detections: List[Detection] = []
        for f in fused:
            if self._infer_roles:
                visual_type = OmniParserBackend._infer_visual_type(
                    f.kind, f.interactable, f.content,
                    f.bounds[2] - f.bounds[0], f.bounds[3] - f.bounds[1], height)
            else:
                visual_type = f.kind          # "text" | "icon", as fused
            if f.kind == "text":
                det_text, det_label = f.content, None
            else:
                # absorbed OCR is a literal read; a caption is a prediction
                literal = f.source == "box_yolo_content_ocr"
                det_text = f.content if literal else None
                det_label = None if literal else f.content
            detections.append(Detection(
                bounds=f.bounds,
                visual_type=visual_type,
                confidence=f.confidence,
                text=det_text,
                label=det_label,
                interactable=f.interactable,
                source="modular",
                extra={"fusion_source": f.source,
                       "stages": {"regions": self._proposer.name,
                                  "captioner": self._captioner.name}},
            ))
        log.info("modular: %d detections (%d regions, %d texts) from %dx%d",
                 len(detections), len(regions), len(texts), width, height)
        return detections

    def close(self) -> None:
        for stage in (self._proposer, self._captioner):
            try:
                stage.close()
            except Exception:
                pass

    @classmethod
    def is_available(cls) -> bool:
        return True     # the no-weights combo (uied + easyocr + none) always works
