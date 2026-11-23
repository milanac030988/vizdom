"""The contour pass: a model-free second look for icons stage 1 missed (contour_pass.py)."""

import cv2
import numpy as np

from visual_dom.adapters.outbound.detectors.contour_pass import (
    CONTOUR_CONFIDENCE, ContourPassParams, propose_contour_regions,
)
from visual_dom.adapters.outbound.detectors.modular_backend import (
    ModularDetectorBackend, NoneCaptioner,
)
from visual_dom.core.ports.outbound.region_proposer_port import (
    RegionProposal, RegionProposer,
)

W, H = 1280, 720
BG = 22


def _screen():
    return np.full((H, W, 3), BG, dtype=np.uint8)


def _icon(image, cx, cy, grey=130, radius=18):
    """A dim outlined shape, like an inactive icon."""
    cv2.circle(image, (cx, cy), radius, (grey, grey, grey), 2)
    cv2.line(image, (cx - radius, cy), (cx + radius, cy), (grey, grey, grey), 2)


def _covers(box, cx, cy):
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def test_a_dim_isolated_icon_is_proposed_with_a_tight_box():
    image = _screen()
    _icon(image, 500, 40)
    boxes = propose_contour_regions(image, existing=[])
    assert len(boxes) == 1
    x1, y1, x2, y2 = boxes[0]
    assert abs(x1 - 481) <= 3 and abs(y1 - 21) <= 3 and abs(x2 - 520) <= 3 and abs(y2 - 60) <= 3


def test_what_is_already_detected_is_not_proposed_again():
    image = _screen()
    _icon(image, 500, 40)
    _icon(image, 900, 40)
    boxes = propose_contour_regions(image, existing=[(478, 18, 522, 62)])
    assert len(boxes) == 1 and _covers(boxes[0], 900, 40)


def test_an_icon_just_above_a_bright_bar_is_not_welded_to_it():
    image = _screen()
    _icon(image, 500, 40)                                   # bottom edge at y = 59
    cv2.rectangle(image, (300, 63), (900, 70), (255, 255, 255), -1)   # 3 px below it
    boxes = propose_contour_regions(image, existing=[])
    assert len(boxes) == 1 and _covers(boxes[0], 500, 40)
    assert boxes[0][3] <= 62, "the bar is not part of the icon"


def test_lines_text_like_rows_and_border_shapes_are_left_alone():
    image = _screen()
    cv2.line(image, (100, 300), (700, 300), (200, 200, 200), 2)          # a divider
    for i in range(12):                                                  # a row of glyphs
        cv2.rectangle(image, (100 + i * 22, 400), (114 + i * 22, 420), (220, 220, 220), 2)
    cv2.circle(image, (4, 600), 18, (200, 200, 200), 2)                  # cut by the border
    cv2.rectangle(image, (800, 200), (1200, 600), (90, 90, 90), -1)      # a panel
    assert propose_contour_regions(image, existing=[]) == []


def test_too_small_too_faint_or_too_many_gives_nothing():
    image = _screen()
    cv2.circle(image, (300, 300), 4, (200, 200, 200), 1)                 # a dot
    _icon(image, 600, 300, grey=BG + 8)                                  # under min_delta
    assert propose_contour_regions(image, existing=[]) == []

    crowded = _screen()
    for row in range(4):
        for col in range(8):
            _icon(crowded, 100 + col * 140, 100 + row * 150)
    assert propose_contour_regions(crowded, existing=[]) == [], "32 shapes: a texture, not icons"
    assert len(propose_contour_regions(
        crowded, existing=[], params=ContourPassParams(max_candidates=40))) == 32


def test_sizes_scale_with_the_image_height():
    image = cv2.resize(_screen(), (W * 2, H * 2))
    _icon(image, 1000, 80, radius=36)
    boxes = propose_contour_regions(image, existing=[])
    assert len(boxes) == 1 and _covers(boxes[0], 1000, 80)


# --------------------------------------------------------------------------
# in the modular backend
# --------------------------------------------------------------------------

class _Regions(RegionProposer):
    name = "fake"

    def __init__(self, boxes):
        self._boxes = boxes

    def propose(self, image):
        return [RegionProposal(bounds=b, confidence=c) for b, c in self._boxes]


class _Text:
    ocr_engine = "fake"

    def detect(self, image):
        return []


def _backend(regions, **kwargs):
    return ModularDetectorBackend(region_proposer=_Regions(regions), text_detector=_Text(),
                                  captioner=NoneCaptioner(), **kwargs)


def _hmi():
    image = _screen()
    cv2.rectangle(image, (740, 15), (800, 65), (255, 255, 255), 3)      # the icon the model finds
    _icon(image, 500, 40)                                               # the one it does not
    return image


def test_off_by_default_and_the_output_is_unchanged():
    regions = [((738, 13, 802, 67), 0.4)]
    off = _backend(regions).detect(_hmi())
    assert [d.bounds for d in off] == [(738, 13, 802, 67)]


def test_on_adds_the_missed_icon_and_keeps_every_earlier_box():
    # a wide box around both icons, as the icon model gave for the top bar:
    # fusion drops it for the smaller box inside, and the dim icon is then free
    regions = [((440, 5, 845, 76), 0.57), ((738, 13, 802, 67), 0.4)]
    off = _backend(regions).detect(_hmi())
    on = _backend(regions, contour_pass=True).detect(_hmi())
    assert [d.bounds for d in on[:len(off)]] == [d.bounds for d in off]
    added = on[len(off):]
    assert len(added) == 1 and _covers(added[0].bounds, 500, 40)
    assert added[0].visual_type == "icon" and added[0].interactable
    assert added[0].confidence == CONTOUR_CONFIDENCE
    assert added[0].extra["fusion_source"] == "box_contour_content_none"


def test_an_icon_inside_a_detected_button_does_not_replace_the_button():
    image = _screen()
    _icon(image, 500, 300)
    regions = [((440, 250, 700, 350), 0.8)]           # the button around it survives fusion
    on = _backend(regions, contour_pass=True).detect(image)
    assert [d.bounds for d in on] == [(440, 250, 700, 350)]


def test_a_bright_icon_on_a_soft_glow_is_proposed_as_on_a_photographed_screen():
    image = _screen()
    for row in range(20, 80):                       # a glow that brightens downwards
        image[row, 300:700] = BG + (row - 20) // 2
    _icon(image, 500, 45, grey=230, radius=14)
    boxes = propose_contour_regions(image, existing=[])
    assert len(boxes) == 1 and _covers(boxes[0], 500, 45)
    assert propose_contour_regions(
        image, existing=[], params=ContourPassParams(ring_spread_ratio=0.0)) == [], \
        "the fixed allowance alone rejects it"
