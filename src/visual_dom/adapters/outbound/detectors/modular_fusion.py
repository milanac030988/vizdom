"""
Fusion for the modular detector (ADR-027): merge stage-1 regions with stage-2
text boxes.

This is a faithful port of OmniParser's `remove_overlap_new`
(third_party/OmniParser/util/utils.py) - the one piece of the monolith that is
pure logic rather than a model. Faithfulness matters more than elegance here:
the parity combo (icon_detect + easyocr + florence2) must reproduce the
monolithic backend's output within noise before any alternative stage is
credible, and the smart-merge history (IMPROVEMENTS 3c, two bugs cancelling)
shows how subtly fused-box behaviour can hide errors. Where the original has
order-dependent quirks, the port keeps them and the docstrings say so.

Semantics (per original):
  1. All OCR text boxes enter the result up front.
  2. A region is DROPPED when it is the LARGER of a high-overlap pair of
     regions (overlap uses max(IoU, inter/area1, inter/area2) - so a small box
     fully inside a big one counts as high overlap; "keep the smaller box").
  3. A surviving region absorbs every OCR box sitting INSIDE it
     (intersection/ocr_area > 0.80): their texts concatenate into the region's
     content, the OCR boxes leave the result.
  4. A region sitting inside an OCR box is DROPPED (the text box wins).
  5. Surviving regions carry content (absorbed text) or None (to be captioned
     by stage 3).

Kept quirk: absorption (3) and inside-ocr (4) are evaluated in OCR-list order
within one pass; a region that first absorbs a small OCR box and only then
meets a bigger OCR box containing it has already consumed the small box. The
original behaves identically.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Box = Tuple[int, int, int, int]

# Same defaults as get_som_labeled_img / remove_overlap_new.
DEFAULT_REGION_OVERLAP = 0.9
INSIDE_RATIO = 0.80


@dataclass
class FusedBox:
    """One fused element, before visual-type inference and captioning."""

    bounds: Box
    kind: str                       # "text" | "icon"
    content: Optional[str]          # OCR text (text boxes / absorbed), else None
    interactable: bool
    confidence: float               # stage model's own score
    source: str                     # box_ocr_content_ocr | box_yolo_content_ocr | box_yolo_content_yolo


def _area(b: Box) -> float:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _intersection(a: Box, b: Box) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def _overlap(a: Box, b: Box) -> float:
    """The original's hybrid 'IoU': max of true IoU and both containment ratios."""
    inter = _intersection(a, b)
    union = _area(a) + _area(b) - inter + 1e-6
    if _area(a) > 0 and _area(b) > 0:
        r1, r2 = inter / _area(a), inter / _area(b)
    else:
        r1 = r2 = 0.0
    return max(inter / union, r1, r2)


def _inside(inner: Box, outer: Box) -> bool:
    """inner sits inside outer: intersection covers > 0.80 of inner."""
    area = _area(inner)
    return area > 0 and _intersection(inner, outer) / area > INSIDE_RATIO


def fuse(
    regions: Sequence[Tuple[Box, float]],
    texts: Sequence[Tuple[Box, str, float]],
    region_overlap: float = DEFAULT_REGION_OVERLAP,
) -> List[FusedBox]:
    """
    Fuse stage-1 region proposals with stage-2 OCR boxes.

    Args:
        regions: [(bounds, confidence), ...] interactable candidates.
        texts:   [(bounds, text, confidence), ...] OCR results.
        region_overlap: threshold for dropping the larger of two regions.

    Returns:
        FusedBoxes in the original's order: OCR boxes first (minus absorbed
        ones), then surviving regions in input order.
    """
    ocr_entries: List[FusedBox] = [
        FusedBox(bounds=b, kind="text", content=t, interactable=False,
                 confidence=c, source="box_ocr_content_ocr")
        for (b, t, c) in texts
    ]
    result: List[FusedBox] = list(ocr_entries)

    region_boxes = [b for (b, _c) in regions]
    for i, (bounds, conf) in enumerate(regions):
        # (2) keep-the-smaller: drop this region if it is the larger of any
        # high-overlap region pair.
        dropped = False
        for j, other in enumerate(region_boxes):
            if i != j and _overlap(bounds, other) > region_overlap \
                    and _area(bounds) > _area(other):
                dropped = True
                break
        if dropped:
            continue

        # (3)/(4) against ALL OCR boxes in list order, original quirks intact:
        # the geometric test always runs against the full OCR list, so a text
        # already absorbed by an earlier region still contributes its label to
        # a later region that contains it - only the box's removal from the
        # result happens once (the original's remove() throws into a bare
        # except on the second absorption, keeping the label it already
        # concatenated).
        absorbed_text = ""
        inside_ocr = False
        for ocr in ocr_entries:
            if _inside(ocr.bounds, bounds):            # ocr inside region
                absorbed_text += (ocr.content or "") + " "
                if ocr in result:
                    result.remove(ocr)
            elif _inside(bounds, ocr.bounds):          # region inside ocr
                inside_ocr = True
                break
        if inside_ocr:
            continue

        if absorbed_text:
            result.append(FusedBox(bounds=bounds, kind="icon",
                                   content=absorbed_text.strip() or None,
                                   interactable=True, confidence=conf,
                                   source="box_yolo_content_ocr"))
        else:
            result.append(FusedBox(bounds=bounds, kind="icon", content=None,
                                   interactable=True, confidence=conf,
                                   source="box_yolo_content_yolo"))
    return result
