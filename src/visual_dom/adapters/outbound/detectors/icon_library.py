"""
Project icon library: names for the icons a project defines itself.

A caption model has never seen a product's own icons (the fan, seat and
airflow glyphs of an automotive HMI), so it names them wrongly or not at all.
The project knows them exactly: it is a fixed set from a design system. This
module lets the project say so in a folder of reference images and one JSON
file, and the modular detector then names a detected icon by lookup instead
of by prediction.

Layout (``detector.icon_library`` points at the folder or at the JSON file)::

    icons/
      icons.json
      climate_fan.png
      climate_fan_dim.png

    {"icons": [
      {"name": "climate_fan", "label": "Climate fan",
       "aliases": ["fan", "blower"],
       "images": ["climate_fan.png", "climate_fan_dim.png"]}
    ]}

``label`` and ``aliases`` are what a ``desc=`` locator matches; ``name`` is a
stable identifier. ``images`` may list several appearances of one icon.

Matching is by SHAPE, not by pixels: every image is reduced to the edges of
whatever stands out from its own background. A dimmed, a highlighted, a
recoloured, an outlined and a filled rendering of one icon then give nearly
the same signature, as does a dark icon on a light theme.

The lookup abstains. A region is named only when its best match reaches
``min_score`` AND beats every other icon of the library by ``min_margin``;
otherwise it is left to the captioner, exactly as without a library. A wrong
name is worse than none: it makes a ``desc=`` step pass on the wrong element.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)

Box = Tuple[int, int, int, int]

SIGNATURE_SIDE = 32
MANIFEST_NAME = "icons.json"


@dataclass(frozen=True)
class IconMatch:
    name: str
    label: str
    score: float
    runner_up: float        # best score of any OTHER icon of the library


@dataclass(frozen=True)
class _Reference:
    name: str
    label: str
    signature: np.ndarray
    aspect: float
    source: str


def _ink(image: np.ndarray) -> Optional[np.ndarray]:
    """How much each pixel belongs to the shape, 0..1; None for a blank image."""
    import cv2

    if image.ndim == 3 and image.shape[2] == 4:
        alpha = image[:, :, 3].astype(np.float32)
        if alpha.max() - alpha.min() > 32:          # a real cut-out, not an opaque PNG
            return alpha / 255.0
        image = image[:, :, :3]
    gray = (image if image.ndim == 2
            else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)).astype(np.float32)
    height, width = gray.shape
    if min(height, width) < 8:
        return None
    # The background is a plane fitted to the outer frame, not one grey value:
    # on a photographed screen, or over a glow, it brightens across the crop
    # and a constant would count that gradient as part of the shape.
    yy, xx = np.mgrid[0:height, 0:width]
    frame = np.zeros((height, width), dtype=bool)
    frame[:2] = frame[-2:] = True
    frame[:, :2] = frame[:, -2:] = True
    design = np.c_[np.ones(int(frame.sum())), xx[frame], yy[frame]]
    values = gray[frame]
    keep = np.ones(len(values), dtype=bool)
    coeff = np.zeros(3)
    for _ in range(2):          # second round without what the shape put on the frame
        coeff, *_rest = np.linalg.lstsq(design[keep], values[keep], rcond=None)
        residual = np.abs(design @ coeff - values)
        keep = residual <= max(6.0, float(np.percentile(residual, 70)))
    difference = np.abs(gray - (coeff[0] + coeff[1] * xx + coeff[2] * yy))
    peak = float(np.percentile(difference, 98))
    if peak < 12:                                    # nothing stands out
        return None
    return np.clip(difference / peak, 0.0, 1.0).astype(np.float32)


def signature(image: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """
    (unit vector, width/height of the shape) for an icon image, or None when
    the image holds no shape. Brightness, colour and polarity do not matter.

    The vector describes the EDGES of the shape. One icon is drawn as a thin
    outline when inactive and as a filled glyph when active; their pixels
    barely overlap, their edges coincide (measured 2026-11-23 on a climate
    fan: 0.80-0.86 between outline, filled and photographed renderings,
    against -0.03 for the pixels themselves).
    """
    import cv2

    ink = _ink(image)
    if ink is None:
        return None
    rows = np.where(ink.max(axis=1) > 0.35)[0]
    cols = np.where(ink.max(axis=0) > 0.35)[0]
    if len(rows) < 5 or len(cols) < 5:
        return None
    ink = ink[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    height, width = ink.shape
    side = max(height, width)
    square = np.zeros((side, side), dtype=np.float32)
    top, left = (side - height) // 2, (side - width) // 2
    square[top:top + height, left:left + width] = ink
    small = cv2.resize(square, (SIGNATURE_SIDE, SIGNATURE_SIDE), interpolation=cv2.INTER_AREA)
    kernel = np.ones((3, 3), dtype=np.uint8)
    edges = cv2.dilate(small, kernel) - cv2.erode(small, kernel)
    # blur: a pixel of misalignment or a thicker stroke must not halve the score
    edges = cv2.GaussianBlur(edges, (5, 5), 0)
    vector = edges.ravel() - float(edges.mean())
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        return None
    return vector / norm, width / float(height)


class IconLibrary:
    """Reference icons of one project and the lookup against them."""

    def __init__(self, references: Sequence[_Reference], min_score: float = 0.70,
                 min_margin: float = 0.06, max_aspect_ratio: float = 1.4,
                 source: str = ""):
        self._references = list(references)
        self._matrix = (np.stack([r.signature for r in self._references])
                        if self._references else np.zeros((0, SIGNATURE_SIDE ** 2)))
        self.min_score = min_score
        self.min_margin = min_margin
        self.max_aspect_ratio = max_aspect_ratio
        self.source = source

    def __len__(self) -> int:
        return len({r.name for r in self._references})

    @property
    def names(self) -> List[str]:
        return sorted({r.name for r in self._references})

    # -- loading ---------------------------------------------------------- #

    @classmethod
    def load(cls, path: str, **kwargs: Any) -> "IconLibrary":
        """
        Read a library from its folder or its JSON file. A missing manifest or
        malformed entry is an error (the user asked for this library); an
        image that cannot be read or holds no shape is skipped with a warning.
        """
        import cv2

        manifest = Path(path)
        if manifest.is_dir():
            manifest = manifest / MANIFEST_NAME
        if not manifest.is_file():
            raise FileNotFoundError(f"icon library: no {MANIFEST_NAME} at {path}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        entries = data.get("icons") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ValueError(f'icon library {manifest}: expected {{"icons": [...]}}')
        folder = manifest.parent
        references: List[_Reference] = []
        seen = set()
        for index, entry in enumerate(entries):
            name = str((entry or {}).get("name") or "").strip() if isinstance(entry, dict) else ""
            if not name:
                raise ValueError(f"icon library {manifest}: entry {index} has no name")
            if name in seen:
                raise ValueError(f"icon library {manifest}: name {name!r} is used twice")
            seen.add(name)
            label = str(entry.get("label") or name.replace("_", " ")).strip()
            aliases = [str(a).strip() for a in entry.get("aliases") or [] if str(a).strip()]
            if aliases:
                # desc= ranks by word overlap with the label, so the aliases
                # travel inside it (and through the gRPC service unchanged)
                label = f"{label} ({', '.join(aliases)})"
            images = entry.get("images") or entry.get("image") or []
            if isinstance(images, str):
                images = [images]
            if not images:
                raise ValueError(f"icon library {manifest}: {name!r} lists no image")
            for rel in images:
                file = folder / str(rel)
                # np.fromfile: cv2.imread cannot open non-ASCII paths on Windows
                pixels = None
                if file.is_file():
                    pixels = cv2.imdecode(np.fromfile(str(file), dtype=np.uint8),
                                          cv2.IMREAD_UNCHANGED)
                sig = signature(pixels) if pixels is not None else None
                if sig is None:
                    log.warning("icon library: %s (%s) is missing, unreadable or "
                                "blank - skipped", rel, name)
                    continue
                references.append(_Reference(name, label, sig[0], sig[1], str(rel)))
        library = cls(references, source=str(manifest), **kwargs)
        log.info("icon library: %d icon(s), %d image(s) from %s",
                 len(library), len(references), manifest)
        return library

    # -- lookup ----------------------------------------------------------- #

    def match_crop(self, crop: np.ndarray) -> Optional[IconMatch]:
        """The library icon this image shows, or None when it is not sure."""
        if not self._references:
            return None
        sig = signature(crop)
        if sig is None:
            return None
        vector, aspect = sig
        scores = self._matrix @ vector
        best = {}                                   # name -> (score, reference)
        for score, ref in zip(scores.tolist(), self._references):
            ratio = max(aspect, ref.aspect) / max(min(aspect, ref.aspect), 1e-6)
            if ratio > self.max_aspect_ratio:
                continue
            if ref.name not in best or score > best[ref.name][0]:
                best[ref.name] = (score, ref)
        if not best:
            return None
        ranked = sorted(best.values(), key=lambda item: -item[0])
        top_score, top = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if top_score < self.min_score or top_score - runner_up < self.min_margin:
            return None
        return IconMatch(top.name, top.label, float(top_score), float(runner_up))

    def match(self, image: np.ndarray, boxes: Sequence[Box],
              margin: float = 0.15) -> List[Optional[IconMatch]]:
        """
        One result per region of a BGR screenshot. Each region is cut with a
        little surrounding background (``margin`` of its size), which is what
        the signature measures the shape against.
        """
        height, width = image.shape[:2]
        out: List[Optional[IconMatch]] = []
        for (x1, y1, x2, y2) in boxes:
            pad_x = int(round((x2 - x1) * margin)) + 2
            pad_y = int(round((y2 - y1) * margin)) + 2
            crop = image[max(0, y1 - pad_y):min(height, y2 + pad_y),
                         max(0, x1 - pad_x):min(width, x2 + pad_x)]
            out.append(self.match_crop(crop) if crop.size else None)
        return out
