"""The project icon library: names for a project's own icons by lookup (icon_library.py)."""

import json

import cv2
import numpy as np
import pytest

from visual_dom.adapters.outbound.detectors.icon_library import IconLibrary, signature
from visual_dom.adapters.outbound.detectors.modular_backend import ModularDetectorBackend
from visual_dom.core.ports.outbound.captioner_port import Captioner
from visual_dom.core.ports.outbound.region_proposer_port import (
    RegionProposal, RegionProposer,
)

BG = 22


def _canvas(side=64, bg=BG):
    return np.full((side, side, 3), bg, dtype=np.uint8)


def _fan(image, cx, cy, r=16, grey=255, filled=False):
    """Four petals around a centre: drawn as an outline or filled."""
    for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        centre = (int(cx + dx * r * 0.5), int(cy + dy * r * 0.5))
        cv2.circle(image, centre, int(r * 0.5), (grey,) * 3, -1 if filled else 1)


def _seat(image, cx, cy, r=16, grey=255):
    cv2.circle(image, (cx + r // 2, cy - r + 4), 4, (grey,) * 3, -1)
    cv2.line(image, (cx - r, cy + r - 4), (cx - 2, cy), (grey,) * 3, 5)
    cv2.line(image, (cx - 2, cy), (cx + r - 2, cy - 4), (grey,) * 3, 5)


def _picture(image, cx, cy, r=16, grey=255):
    cv2.rectangle(image, (cx - r, cy - r), (cx + r, cy + r), (grey,) * 3, 2)
    cv2.circle(image, (cx - r // 2, cy - r // 2), 3, (grey,) * 3, -1)
    cv2.line(image, (cx - r, cy + r), (cx, cy), (grey,) * 3, 2)
    cv2.line(image, (cx, cy), (cx + r, cy + r), (grey,) * 3, 2)


def _reference(draw, **kwargs):
    image = _canvas()
    draw(image, 32, 32, **kwargs)
    return image


@pytest.fixture
def folder(tmp_path):
    cv2.imwrite(str(tmp_path / "fan.png"), _reference(_fan))
    cv2.imwrite(str(tmp_path / "seat.png"), _reference(_seat))
    cv2.imwrite(str(tmp_path / "picture.png"), _reference(_picture))
    (tmp_path / "icons.json").write_text(json.dumps({"icons": [
        {"name": "climate_fan", "label": "Climate fan", "aliases": ["blower"],
         "images": ["fan.png"]},
        {"name": "seat_airflow", "images": "seat.png"},
        {"name": "gallery", "label": "Gallery", "image": "picture.png"},
    ]}), encoding="utf-8")
    return tmp_path


def test_a_library_loads_from_its_folder_or_its_json_file(folder):
    library = IconLibrary.load(str(folder))
    assert len(library) == 3 and library.names == ["climate_fan", "gallery", "seat_airflow"]
    assert len(IconLibrary.load(str(folder / "icons.json"))) == 3


def test_an_icon_is_named_in_every_rendering_of_it(folder):
    library = IconLibrary.load(str(folder))
    renderings = {
        "as the reference": _reference(_fan),
        "dimmed": _reference(_fan, grey=90),
        "filled, not outlined": _reference(_fan, filled=True),
        "larger": cv2.resize(_reference(_fan), (150, 150), interpolation=cv2.INTER_CUBIC),
        "smaller": cv2.resize(_reference(_fan), (40, 40), interpolation=cv2.INTER_AREA),
    }
    light = _canvas(bg=235)
    _fan(light, 32, 32, grey=40)
    renderings["dark on a light theme"] = light
    glow = _canvas()
    glow[:] = np.linspace(15, 60, 64, dtype=np.uint8)[:, None, None]     # brightens downwards
    _fan(glow, 32, 32, grey=200)
    renderings["over a glow"] = glow
    for what, image in renderings.items():
        match = library.match_crop(image)
        assert match is not None and match.name == "climate_fan", what
        assert match.score >= library.min_score and match.score - match.runner_up >= library.min_margin


def test_the_label_carries_the_aliases_and_defaults_to_the_name(folder):
    library = IconLibrary.load(str(folder))
    assert library.match_crop(_reference(_fan)).label == "Climate fan (blower)"
    assert library.match_crop(_reference(_seat)).label == "seat airflow"
    assert library.match_crop(_reference(_picture)).label == "Gallery"


def test_it_abstains_on_what_it_does_not_know(folder):
    library = IconLibrary.load(str(folder))
    unknown = _canvas()
    cv2.drawMarker(unknown, (32, 32), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 30, 3)
    assert library.match_crop(unknown) is None
    assert library.match_crop(_canvas()) is None, "a blank region"
    text = _canvas(96)
    cv2.putText(text, "Wifi", (8, 56), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    assert library.match_crop(text) is None


def test_it_abstains_when_two_library_icons_fit_equally(folder):
    data = json.loads((folder / "icons.json").read_text(encoding="utf-8"))
    data["icons"].append({"name": "vent_fan", "images": ["fan.png"]})      # a twin
    (folder / "icons.json").write_text(json.dumps(data), encoding="utf-8")
    library = IconLibrary.load(str(folder))
    assert library.match_crop(_reference(_fan)) is None, "two names for one shape: no name"
    assert library.match_crop(_reference(_seat)).name == "seat_airflow"


def test_several_images_of_one_icon_do_not_compete_with_each_other(folder):
    cv2.imwrite(str(folder / "fan_dim.png"), _reference(_fan, grey=90))
    data = json.loads((folder / "icons.json").read_text(encoding="utf-8"))
    data["icons"][0]["images"] = ["fan.png", "fan_dim.png"]
    (folder / "icons.json").write_text(json.dumps(data), encoding="utf-8")
    assert IconLibrary.load(str(folder)).match_crop(_reference(_fan)).name == "climate_fan"


def test_a_wrong_manifest_is_an_error_and_a_bad_image_only_a_warning(folder, tmp_path):
    with pytest.raises(FileNotFoundError):
        IconLibrary.load(str(tmp_path / "nowhere"))
    for broken in ({"icons": [{"label": "no name", "images": ["fan.png"]}]},
                   {"icons": [{"name": "a", "images": ["fan.png"]}, {"name": "a", "images": ["fan.png"]}]},
                   {"icons": [{"name": "a"}]},
                   ["not", "an", "object"]):
        (folder / "icons.json").write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(ValueError):
            IconLibrary.load(str(folder))
    cv2.imwrite(str(folder / "blank.png"), _canvas())
    (folder / "icons.json").write_text(json.dumps({"icons": [
        {"name": "fan", "images": ["fan.png", "missing.png", "blank.png"]}]}), encoding="utf-8")
    library = IconLibrary.load(str(folder))
    assert len(library) == 1 and library.match_crop(_reference(_fan)).name == "fan"


def test_a_transparent_png_is_read_from_its_alpha_channel(folder):
    grey = cv2.cvtColor(_reference(_fan), cv2.COLOR_BGR2GRAY)
    cutout = np.dstack([np.zeros_like(grey)] * 3 + [grey])        # black glyph, alpha = shape
    cv2.imwrite(str(folder / "fan.png"), cutout)
    assert IconLibrary.load(str(folder)).match_crop(_reference(_fan, grey=120)).name == "climate_fan"
    assert signature(cutout) is not None


# --------------------------------------------------------------------------
# in the modular backend
# --------------------------------------------------------------------------

class _Regions(RegionProposer):
    name = "fake"

    def __init__(self, boxes):
        self._boxes = boxes

    def propose(self, image):
        return [RegionProposal(bounds=b, confidence=0.5) for b in self._boxes]


class _Text:
    ocr_engine = "fake"

    def detect(self, image):
        return []


class _Recorder(Captioner):
    name = "recorder"

    def __init__(self):
        self.asked = []

    def caption(self, image, boxes):
        self.asked.append(list(boxes))
        return ["a guess"] * len(boxes)


def _screen():
    image = np.full((300, 600, 3), BG, dtype=np.uint8)
    _fan(image, 100, 100, grey=90)                                   # dimmed, in the library
    cv2.drawMarker(image, (400, 100), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 30, 3)   # not in it
    return image, [(80, 80, 120, 120), (382, 82, 418, 118)]


def test_the_backend_names_library_icons_and_leaves_the_rest_to_the_captioner(folder):
    image, boxes = _screen()
    captioner = _Recorder()
    backend = ModularDetectorBackend(region_proposer=_Regions(boxes), text_detector=_Text(),
                                     captioner=captioner, icon_library=str(folder))
    fan, cross = backend.detect(image)
    assert fan.label == "Climate fan (blower)" and fan.text is None
    assert fan.extra["fusion_source"] == "box_library_content_climate_fan"
    assert cross.label == "a guess"
    assert captioner.asked == [[boxes[1]]], "the named icon never reached the captioner"


def test_without_a_library_nothing_changes(folder):
    image, boxes = _screen()
    captioner = _Recorder()
    backend = ModularDetectorBackend(region_proposer=_Regions(boxes), text_detector=_Text(),
                                     captioner=captioner)
    assert [d.label for d in backend.detect(image)] == ["a guess", "a guess"]
    assert captioner.asked == [boxes]
    blank = ModularDetectorBackend(region_proposer=_Regions(boxes), text_detector=_Text(),
                                   captioner=_Recorder(), icon_library="  ")
    assert [d.label for d in blank.detect(image)] == ["a guess", "a guess"]


def test_a_library_name_is_a_label_even_beside_a_reading_captioner(folder):
    image, boxes = _screen()

    class _Reader(_Recorder):
        literal = True

    backend = ModularDetectorBackend(region_proposer=_Regions(boxes), text_detector=_Text(),
                                     captioner=_Reader(), icon_library=str(folder))
    fan, cross = backend.detect(image)
    assert (fan.label, fan.text) == ("Climate fan (blower)", None)
    assert (cross.label, cross.text) == (None, "a guess")


# --------------------------------------------------------------------------
# search: library icons that have no box yet
# --------------------------------------------------------------------------

def _hmi():
    """A dimmed fan nobody detected, a fan inside a detected tile, a detected seat, a stranger."""
    image = np.full((400, 800, 3), BG, dtype=np.uint8)
    _fan(image, 100, 100, grey=90)
    cv2.rectangle(image, (250, 40), (550, 160), (60, 60, 60), 1)        # a tile ...
    _fan(image, 300, 100, grey=255, filled=True)                        # ... with a fan in it
    _seat(image, 650, 100)
    cv2.drawMarker(image, (100, 300), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 30, 3)
    return image


def _near(box, centre, tolerance=6):
    return (abs((box[0] + box[2]) / 2 - centre[0]) <= tolerance
            and abs((box[1] + box[3]) / 2 - centre[1]) <= tolerance)


def test_search_finds_library_icons_that_have_no_box(folder):
    library = IconLibrary.load(str(folder))
    tile, seat = (250, 40, 550, 160), (630, 80, 670, 120)
    found = library.search(_hmi(), [tile, seat])
    assert [m.name for _box, m in found] == ["climate_fan", "climate_fan"]
    assert _near(found[0][0], (100, 100)), "the dimmed one"
    assert _near(found[1][0], (300, 100)), "a far larger box around an icon does not hide it"
    everything = library.search(_hmi(), [])
    assert sorted(m.name for _box, m in everything) == ["climate_fan", "climate_fan", "seat_airflow"]
    assert not any(_near(box, (100, 300)) for box, _m in everything), "the stranger gets no box"
    assert library.search(np.full((400, 800, 3), BG, dtype=np.uint8), []) == []


def test_the_backend_adds_the_found_icons_already_named(folder):
    image = _hmi()
    tile, seat = (250, 40, 550, 160), (630, 80, 670, 120)
    captioner = _Recorder()
    backend = ModularDetectorBackend(region_proposer=_Regions([tile, seat]), text_detector=_Text(),
                                     captioner=captioner, icon_library=str(folder))
    detections = backend.detect(image)
    added = [d for d in detections
             if d.extra["fusion_source"] == "box_librarysearch_content_climate_fan"]
    assert len(added) == 2 and all(d.label == "Climate fan (blower)" and d.text is None
                                   and d.confidence >= 0.70 for d in added)
    assert len(detections) == 4
    assert captioner.asked == [[tile]], "only the tile needed a caption"

    off = ModularDetectorBackend(region_proposer=_Regions([tile, seat]), text_detector=_Text(),
                                 captioner=_Recorder(), icon_library=str(folder),
                                 icon_library_search=False)
    assert len(off.detect(image)) == 2
