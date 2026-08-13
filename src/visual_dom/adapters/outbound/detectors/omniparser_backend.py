"""
OmniParser detector backend (Microsoft OmniParser).

OmniParser parses a screenshot into structured elements: YOLO-based icon
detection + OCR + a captioning model (Florence-2 in v2), producing boxes with
semantic labels and an interactability flag. This backend adapts that output to
our neutral `Detection` type.

Setup
-----
OmniParser is NOT a pip package with a stable API; it is a repository + weights.
This backend expects:
  * the OmniParser repo importable on sys.path (so `util.utils` resolves), and
  * weights on disk: an icon-detection .pt and a caption model directory.

Point it at them via constructor args or environment variables:
  OMNIPARSER_ROOT        - path to the cloned OmniParser repo
  OMNIPARSER_ICON_DETECT - path to icon_detect weights (.pt)
  OMNIPARSER_ICON_CAPTION- path to icon_caption model directory

LICENSING (read before shipping)
--------------------------------
OmniParser's `icon_detect` component is AGPL-3.0 (a YOLOv8 fine-tune, inheriting
Ultralytics' licence); `icon_caption` is MIT; the repo is CC-BY-4.0. Using this
backend places the same AGPL obligation on distribution/network-serving as our
existing Ultralytics/YOLO dependency. See
docs/discussion/landscape-comparison-*.html section 9.

VERSION CAVEAT
--------------
The exact `util.utils` signatures have changed across OmniParser releases. The
parsing here targets the v2 `get_som_labeled_img` output (a list of dicts with
normalized `bbox`, `type`, `content`, `interactivity`). If your installed
version differs, adjust `_parse_content_list` — it is deliberately isolated.
"""

import os

# OmniParser's caption model (Florence-2) runs on torch. Some transformers builds
# eagerly import TensorFlow/Flax if installed; here TF 2.10's protobuf-generated
# code is incompatible with the protobuf the dashboard needs (protobuf>=3.20),
# raising "Descriptors cannot be created directly". We never use TF/Flax, so
# disable them before transformers is first imported. Must run at module import,
# ahead of any `import transformers`.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from visual_dom.core.ports.outbound.detector_port import Detection, DetectorBackend
from visual_dom.logging_utils import get_logger, log_timing

log = get_logger(__name__)


# Module-level cache of loaded models, keyed by (icon_detect, icon_caption,
# caption_model_name, device). Loading Florence-2 + YOLO costs ~9-10s, so when the
# pipeline is rebuilt for each run (as the Viewer does), reuse the already-loaded
# models instead of paying that cost again. `import util.utils` is separately
# cached by Python's sys.modules, so it only runs once per process regardless.
_MODEL_CACHE: Dict[tuple, Dict[str, Any]] = {}

# Per-thread capture slot for YOLO confidences (see _install_yolo_recorder).
# Thread-local because the detector service runs detect() on a gRPC thread pool.
import threading

_YOLO_TRACE = threading.local()


def _iou(a, b) -> float:
    """Intersection over union of two (x1, y1, x2, y2) boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class OmniParserBackend(DetectorBackend):
    name = "omniparser"
    description = "Microsoft OmniParser (YOLO icon-detect + OCR + Florence-2 caption). GPU recommended."
    license = "AGPL-3.0 (icon_detect) / MIT (icon_caption)"
    requires_gpu = True

    def __init__(
        self,
        omniparser_root: Optional[str] = None,
        icon_detect_path: Optional[str] = None,
        icon_caption_path: Optional[str] = None,
        box_threshold: float = 0.05,
        use_gpu: bool = True,
        caption_model_name: str = "florence2",
        ocr_provider: Optional[Callable[[np.ndarray], List[tuple]]] = None,
        ocr_ensemble: bool = True,
        ocr_dedup_iou: float = 0.5,
    ):
        self._root = omniparser_root or os.environ.get("OMNIPARSER_ROOT")
        self._icon_detect = icon_detect_path or os.environ.get("OMNIPARSER_ICON_DETECT")
        self._icon_caption = icon_caption_path or os.environ.get("OMNIPARSER_ICON_CAPTION")
        self._box_threshold = box_threshold
        self._device = "cuda" if use_gpu else "cpu"
        self._caption_model_name = caption_model_name
        # Optional external OCR to reduce missed text. `ocr_provider(image)` returns
        # [((x1,y1,x2,y2), text), ...] in pixel coords. When `ocr_ensemble` is True the
        # results are unioned with OmniParser's own OCR (deduped by IoU); when False they
        # replace it. See ADR-016 (text ensemble follow-up).
        self._ocr_provider = ocr_provider
        self._ocr_ensemble = ocr_ensemble
        self._ocr_dedup_iou = ocr_dedup_iou

        if not self._icon_detect or not self._icon_caption:
            raise ValueError(
                "OmniParserBackend needs icon_detect_path and icon_caption_path "
                "(or OMNIPARSER_ICON_DETECT / OMNIPARSER_ICON_CAPTION env vars)."
            )

        log.info("Initializing OmniParser backend (device=%s)", self._device)
        with log_timing(log, "OmniParser: import util.utils"):
            self._util = self._import_omniparser()

        cache_key = (self._icon_detect, self._icon_caption,
                     self._caption_model_name, self._device)
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            log.info("OmniParser: reusing cached models (skipping ~9s reload)")
            self._som_model = cached["som_model"]
            self._caption = cached["caption"]
        else:
            with log_timing(log, "OmniParser: load icon_detect (YOLO) model"):
                self._som_model = self._util["get_yolo_model"](model_path=self._icon_detect)
            with log_timing(log, "OmniParser: load icon_caption (Florence-2) model"):
                self._caption = self._util["get_caption_model_processor"](
                    model_name=self._caption_model_name,
                    model_name_or_path=self._icon_caption,
                    device=self._device,
                )
            _MODEL_CACHE[cache_key] = {"som_model": self._som_model, "caption": self._caption}
        log.info("OmniParser backend ready")

    # -- setup helpers -------------------------------------------------------

    def _import_omniparser(self) -> Dict[str, Any]:
        """Import OmniParser's utility functions, extending sys.path if needed."""
        import sys

        if self._root and self._root not in sys.path:
            sys.path.insert(0, self._root)

        import util.utils as omni_utils  # type: ignore

        self._install_yolo_recorder(omni_utils)

        return {
            "get_som_labeled_img": omni_utils.get_som_labeled_img,
            "check_ocr_box": omni_utils.check_ocr_box,
            "get_caption_model_processor": omni_utils.get_caption_model_processor,
            "get_yolo_model": omni_utils.get_yolo_model,
        }

    @staticmethod
    def _install_yolo_recorder(omni_utils) -> None:
        """
        Wrap OmniParser's `predict_yolo` to record (boxes, confidences).

        OmniParser computes real YOLO confidence scores but drops them on the
        floor: `get_som_labeled_img` receives (xyxy, logits, phrases) from
        predict_yolo and builds its box dicts without the logits, so every
        parsed item reaches us without a confidence and our fallback (1.0) made
        the DOM claim certainty it never had. The repo is vendored outside git
        (third_party/, ignored), so patching it in place would not survive a
        re-clone - instead the scores are captured here at the call boundary
        and matched back to the parsed boxes by IoU in `_parse_content_list`.

        Recording is per-thread (`_YOLO_TRACE.boxes`): detect() arms the slot,
        so concurrent service calls cannot see each other's scores. Wrapping is
        idempotent across backend instances.
        """
        if getattr(omni_utils.predict_yolo, "_vizdom_records_confidence", False):
            return
        original = omni_utils.predict_yolo

        def predict_yolo_recording(*args, **kwargs):
            boxes, conf, phrases = original(*args, **kwargs)
            if getattr(_YOLO_TRACE, "armed", False):
                try:
                    _YOLO_TRACE.boxes = [
                        (tuple(float(v) for v in box), float(c))
                        for box, c in zip(boxes.tolist(), conf.tolist())
                    ]
                except Exception as e:      # recording must never break detection
                    log.warning("YOLO confidence recording failed: %s", e)
                    _YOLO_TRACE.boxes = []
            return boxes, conf, phrases

        predict_yolo_recording._vizdom_records_confidence = True
        omni_utils.predict_yolo = predict_yolo_recording

    @classmethod
    def is_available(cls) -> bool:
        """True if OmniParser's utils are importable (respecting OMNIPARSER_ROOT)."""
        import importlib.util
        import sys

        root = os.environ.get("OMNIPARSER_ROOT")
        if root and root not in sys.path:
            sys.path.insert(0, root)
        try:
            return importlib.util.find_spec("util.utils") is not None
        except (ImportError, ValueError):
            return False

    # -- detection -----------------------------------------------------------

    def detect(self, image: np.ndarray) -> List[Detection]:
        """
        Run OmniParser on a BGR image and return Detections in pixel coords.

        OmniParser's file-based helpers expect an image path, so the array is
        written to a temporary PNG for the call.
        """
        import tempfile

        import cv2

        height, width = image.shape[:2]

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            cv2.imwrite(tmp_path, image)

            with log_timing(log, f"OmniParser: OCR (check_ocr_box) [{width}x{height}]"):
                ocr_result, _ = self._util["check_ocr_box"](
                    tmp_path,
                    display_img=False,
                    output_bb_format="xyxy",
                )
                ocr_text, ocr_bbox = ocr_result
                ocr_text = list(ocr_text)
                ocr_bbox = [list(b) for b in ocr_bbox]

            # Text ensemble: fold in an external OCR source (e.g. our upscaled
            # dual-engine detector) to recover text OmniParser's single pass misses.
            ocr_scores = None
            if self._ocr_provider is not None:
                ocr_text, ocr_bbox, ocr_scores = self._apply_ocr_provider(
                    image, ocr_text, ocr_bbox)

            _YOLO_TRACE.armed = True
            _YOLO_TRACE.boxes = []
            try:
                with log_timing(log, "OmniParser: detect + caption (get_som_labeled_img)"):
                    _, _, parsed_content_list = self._util["get_som_labeled_img"](
                        tmp_path,
                        self._som_model,
                        BOX_TRESHOLD=self._box_threshold,
                        output_coord_in_ratio=True,
                        ocr_bbox=ocr_bbox,
                        caption_model_processor=self._caption,
                        ocr_text=ocr_text,
                        use_local_semantics=True,
                    )
                yolo_scores = list(getattr(_YOLO_TRACE, "boxes", []) or [])
            finally:
                _YOLO_TRACE.armed = False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        detections = self._parse_content_list(
            parsed_content_list, width, height,
            yolo_scores=yolo_scores, ocr_scores=ocr_scores,
        )
        log.info("OmniParser: %d detections from %dx%d image", len(detections), width, height)
        return detections

    def _apply_ocr_provider(
        self,
        image: np.ndarray,
        ocr_text: List[str],
        ocr_bbox: List[List[float]],
    ) -> Tuple[List[str], List[List[float]], Optional[List[Tuple[List[float], float]]]]:
        """
        Merge the external OCR provider's results with OmniParser's own.

        In ensemble mode, external boxes are added unless they duplicate an
        existing box (IoU >= threshold), maximising text recall without
        double-labelling. In replace mode, the provider's results are used alone.
        A provider failure is non-fatal — we fall back to OmniParser's OCR.

        Also returns `[(bbox, confidence), ...]` for the provider's boxes. The
        boxes round-trip through OmniParser's `get_som_labeled_img`, whose
        ocr_bbox/ocr_text lists have no confidence channel - the genuine OCR
        scores would otherwise be lost and replaced by the 1.0 fallback.
        `_parse_content_list` matches them back onto the returned text items.
        Provider entries may be `(bbox, text)` or `(bbox, text, confidence)`;
        2-tuples (older providers, plugins) simply contribute no score.
        """
        def unpack(entry):
            bounds, text = entry[0], entry[1]
            conf = float(entry[2]) if len(entry) > 2 and entry[2] is not None else None
            return list(bounds), str(text), conf

        try:
            with log_timing(log, "OmniParser: external OCR provider"):
                extra = self._ocr_provider(image) or []
        except Exception as e:
            log.warning("OCR provider failed (%s); using OmniParser OCR only", e)
            return ocr_text, ocr_bbox, None

        entries = [unpack(e) for e in extra]
        entries = [(b, t, c) for (b, t, c) in entries if t and t.strip()]
        scores = [(b, c) for (b, t, c) in entries if c is not None]

        if not self._ocr_ensemble:
            texts = [t for (_b, t, _c) in entries]
            boxes = [b for (b, _t, _c) in entries]
            log.info("OCR (replace): %d boxes from external provider", len(texts))
            return texts, boxes, scores

        base_n = len(ocr_text)
        clean_extra = [(b, t) for (b, t, _c) in entries]

        # Prefer-external union. The external provider runs our upscaling OCR, so
        # where its box overlaps OmniParser's own OCR the external read is the
        # better one — OmniParser's native OCR produced tight garbage reads
        # ("~ctive" for "Active", "VGcJC" for "UGCIHC") in boxes so small they
        # later died in the pipeline's size filter, losing the row entirely. The
        # old gap-fill kept the existing (bad) box and skipped ours. Overlap uses
        # intersection-over-smaller-box, which also collapses OmniParser's
        # glyph-in-cell duplicates ("5" + "5" -> "5 5") into one external box.
        kept_text, kept_bbox, replaced = [], [], 0
        for ob, ot in zip(ocr_bbox, ocr_text):
            if any(self._overlap_min(eb, ob) >= self._ocr_dedup_iou
                   for eb, _ in clean_extra):
                replaced += 1
                continue
            kept_bbox.append(ob)
            kept_text.append(ot)
        for eb, et in clean_extra:
            kept_bbox.append(eb)
            kept_text.append(et)
        log.info("OCR ensemble (prefer-external): OmniParser %d (kept %d, replaced %d) "
                 "+ %d external = %d text boxes",
                 base_n, len(kept_text) - len(clean_extra), replaced,
                 len(clean_extra), len(kept_text))
        return kept_text, kept_bbox, scores

    @staticmethod
    def _overlap_min(a, b) -> float:
        """
        Intersection over the smaller box's area, for two (x1,y1,x2,y2) boxes.

        Unlike IoU, this is ~1.0 when a small box sits inside a much larger one,
        which is exactly the "glyph box inside cell box" duplicate case we need to
        catch for gap-fill dedup.
        """
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        smaller = min(area_a, area_b)
        return inter / smaller if smaller > 0 else 0.0

    def _parse_content_list(
        self,
        parsed_content_list: List[Dict[str, Any]],
        width: int,
        height: int,
        yolo_scores: Optional[List[Tuple[Tuple[float, ...], float]]] = None,
        ocr_scores: Optional[List[Tuple[List[float], float]]] = None,
    ) -> List[Detection]:
        """
        Convert OmniParser's parsed content into Detections.

        Expected item shape (v2), tolerant of missing keys:
            {"type": "text"|"icon", "bbox": [x1,y1,x2,y2] in [0,1],
             "content": str, "interactivity": bool}
        Isolated here so version drift only touches this method.

        `yolo_scores` / `ocr_scores` are `[(pixel_bbox, confidence), ...]`
        captured at the model boundaries (see `_install_yolo_recorder` and
        `_apply_ocr_provider`): OmniParser's own output carries no confidence,
        so each item is matched back to its source box by IoU to recover the
        real score. An unmatched item keeps the historical fallback of 1.0 -
        which from here on means "score unknown", not "certain". Matching is
        best-IoU with a floor of 0.5; OmniParser can shift a box slightly when
        it absorbs an overlapping OCR box, which IoU tolerates and exact
        coordinate lookup would not.
        """
        def matched_score(px_bounds, scored_boxes) -> Optional[float]:
            best, best_iou = None, 0.5
            for sbox, sconf in scored_boxes or []:
                iou = _iou(px_bounds, sbox)
                if iou >= best_iou:
                    best, best_iou = sconf, iou
            return best

        detections: List[Detection] = []
        for item in parsed_content_list or []:
            bbox = item.get("bbox")
            if not bbox or len(bbox) != 4:
                continue

            # OmniParser returns normalized coords when output_coord_in_ratio=True.
            x1, y1, x2, y2 = bbox
            px = (
                int(round(x1 * width)),
                int(round(y1 * height)),
                int(round(x2 * width)),
                int(round(y2 * height)),
            )

            raw_type = (item.get("type") or "unknown").lower()
            content = item.get("content")
            interactable = item.get("interactivity")
            visual_type = self._infer_visual_type(
                raw_type, interactable, content,
                px[2] - px[0], px[3] - px[1], height,
            )

            # Split OCR-read text from the model's semantic caption. OmniParser
            # tags each item "text" (content = OCR-read pixels) or "icon" (content
            # = a Florence-2 caption, i.e. a prediction of what the glyph means).
            # The DOM's `text` must be the literal read value, so only "text"
            # content becomes `text`; an icon caption becomes `label` (leaving
            # `text` empty, since a glyph carries no readable text).
            content = content or None
            if raw_type == "text":
                det_text, det_label = content, None
                score = matched_score(px, ocr_scores)
            else:
                det_text, det_label = None, content
                score = matched_score(px, yolo_scores)
            if score is None:
                score = float(item.get("confidence", 1.0))

            detections.append(
                Detection(
                    bounds=px,
                    visual_type=visual_type,
                    confidence=score,
                    text=det_text,
                    label=det_label,
                    interactable=bool(interactable) if interactable is not None else None,
                    source="omniparser",
                    extra={"omniparser_type": raw_type, "caption": content},
                )
            )
        return detections

    @staticmethod
    def _infer_visual_type(
        raw_type: str,
        interactable: Optional[bool],
        content: Optional[str],
        w: int,
        h: int,
        image_height: int,
    ) -> str:
        """
        Map an OmniParser item to our richer visual-type taxonomy.

        OmniParser only tags each element as ``text`` or ``icon`` plus an
        ``interactivity`` flag; that collapsed everything actionable into
        ``icon``. Here we recover ``button`` / ``input_field`` / ``checkbox`` /
        ``icon`` from interactivity + resolution-aware geometry, so OmniParser's
        (good) boxes also carry the role a test needs. Non-interactive text stays
        ``text``. Thresholds scale with resolution (ref 1080p), matching the rest
        of the pipeline. Heuristic by nature; the raw type is kept in ``extra``.
        """
        scale = max(1.0, image_height / 1080.0)
        text = (content or "").strip()
        text_l = text.lower()
        has_text = bool(text)
        aspect = w / float(max(1, h))
        small = max(w, h) <= 46 * scale
        near_square = 0.6 <= aspect <= 1.7

        # Checkbox/toggle/radio cues from OmniParser's caption. Checkboxes and icons
        # are both small near-square interactive boxes, so geometry alone cannot
        # separate them; the caption ("Checkmark", "Toggle", "Check", ...) is the
        # reliable signal. Without a cue, a small square defaults to icon (below).
        _check_kw = ("check", "tick", "toggle", "radio", "switch", "selected")

        # Non-interactive plain text.
        if raw_type == "text" and not interactable:
            return "text"

        if interactable or raw_type == "icon":
            # 1. Long, entry-height boxes -> input field.
            if aspect >= 3.0 and h >= 22 * scale:
                return "input_field"
            # 2. Caption clearly names a checkbox/toggle/radio.
            if has_text and any(k in text_l for k in _check_kw):
                return "checkbox"
            # 3. Wide, labelled control -> button. Buttons are markedly wider than
            #    icons/checkboxes (measured w ~ 2x), so width is the key separator.
            if has_text and w >= 82 * scale and aspect >= 1.3:
                return "button"
            # 4. Small, square graphic -> icon (icons cluster at aspect ~1, w<=~75).
            if aspect <= 1.35 and max(w, h) <= 78 * scale:
                return "icon"
            # 5. Remaining labelled, wider-than-tall control -> button.
            if has_text and aspect >= 1.3 and h >= 18 * scale:
                return "button"
            # 6. Fallbacks: small -> icon; else labelled -> button.
            if small:
                return "icon"
            return "button" if has_text else "icon"

        # Non-interactive, non-text -> icon.
        return "icon"
