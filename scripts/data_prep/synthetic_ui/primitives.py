"""
Drawing primitives for synthetic UI generation.

Uses Pillow for anti-aliased text and OpenCV for shapes.
Each draw function renders a UI element and returns ground truth metadata.
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class Element:
    """Ground truth UI element."""
    id: str
    bounds: List[int]  # [x1, y1, x2, y2]
    visual_type: str
    text: str = ""
    confidence: float = 1.0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = {
            "id": self.id,
            "bounds": self.bounds,
            "visual_type": self.visual_type,
            "confidence": self.confidence,
        }
        if self.text:
            d["ocr_text"] = self.text
        if self.parent_id:
            d["parent_id"] = self.parent_id
        if self.children_ids:
            d["children_ids"] = self.children_ids
        return d


# Font cache
_font_cache = {}


def _get_font(size: int = 14, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a cached TrueType font."""
    key = (size, bold)
    if key not in _font_cache:
        try:
            name = "segoeuib.ttf" if bold else "segoeui.ttf"
            _font_cache[key] = ImageFont.truetype(name, size)
        except OSError:
            try:
                name = "arialbd.ttf" if bold else "arial.ttf"
                _font_cache[key] = ImageFont.truetype(name, size)
            except OSError:
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _text_size(text: str, font_size: int = 14, bold: bool = False) -> Tuple[int, int]:
    """Get text dimensions."""
    font = _get_font(font_size, bold)
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_text(
    img: np.ndarray, text: str,
    x: int, y: int,
    color: Tuple = (50, 50, 50),
    font_size: int = 14,
    bold: bool = False,
) -> Tuple[int, int]:
    """Draw anti-aliased text using Pillow. Returns (width, height)."""
    font = _get_font(font_size, bold)
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    # Convert BGR color to RGB for Pillow
    rgb_color = (color[2], color[1], color[0])
    draw.text((x, y), text, font=font, fill=rgb_color)
    result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    np.copyto(img, result)
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_rounded_rect(
    img: np.ndarray,
    x: int, y: int, w: int, h: int,
    color: Tuple, radius: int = 4,
    border_color: Tuple = None, border_width: int = 1,
):
    """Draw a rounded rectangle."""
    # Fill
    cv2.rectangle(img, (x + radius, y), (x + w - radius, y + h), color, -1)
    cv2.rectangle(img, (x, y + radius), (x + w, y + h - radius), color, -1)
    cv2.circle(img, (x + radius, y + radius), radius, color, -1, cv2.LINE_AA)
    cv2.circle(img, (x + w - radius, y + radius), radius, color, -1, cv2.LINE_AA)
    cv2.circle(img, (x + radius, y + h - radius), radius, color, -1, cv2.LINE_AA)
    cv2.circle(img, (x + w - radius, y + h - radius), radius, color, -1, cv2.LINE_AA)

    # Border
    if border_color:
        cv2.rectangle(img, (x + radius, y), (x + w - radius, y), border_color, border_width)
        cv2.rectangle(img, (x + radius, y + h), (x + w - radius, y + h), border_color, border_width)
        cv2.rectangle(img, (x, y + radius), (x, y + h - radius), border_color, border_width)
        cv2.rectangle(img, (x + w, y + radius), (x + w, y + h - radius), border_color, border_width)
        cv2.ellipse(img, (x + radius, y + radius), (radius, radius), 180, 0, 90, border_color, border_width, cv2.LINE_AA)
        cv2.ellipse(img, (x + w - radius, y + radius), (radius, radius), 270, 0, 90, border_color, border_width, cv2.LINE_AA)
        cv2.ellipse(img, (x + radius, y + h - radius), (radius, radius), 90, 0, 90, border_color, border_width, cv2.LINE_AA)
        cv2.ellipse(img, (x + w - radius, y + h - radius), (radius, radius), 0, 0, 90, border_color, border_width, cv2.LINE_AA)


def draw_button(
    img: np.ndarray, eid: str,
    x: int, y: int, w: int, h: int,
    text: str,
    bg_color: Tuple = (66, 133, 244),
    text_color: Tuple = (255, 255, 255),
    border_color: Tuple = None,
    font_size: int = 13,
) -> Element:
    """Draw a button with rounded corners and anti-aliased text."""
    _draw_rounded_rect(img, x, y, w, h, bg_color, radius=4, border_color=border_color)

    tw, th = _text_size(text, font_size)
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2 - 2
    _draw_text(img, text, tx, ty, text_color, font_size)

    return Element(id=eid, bounds=[x, y, x + w, y + h], visual_type="button", text=text)


def draw_input_field(
    img: np.ndarray, eid: str,
    x: int, y: int, w: int, h: int,
    placeholder: str = "",
    value: str = "",
    bg_color: Tuple = (255, 255, 255),
    border_color: Tuple = (200, 200, 200),
    font_size: int = 13,
) -> Element:
    """Draw an input field."""
    _draw_rounded_rect(img, x, y, w, h, bg_color, radius=3, border_color=border_color)

    display = value or placeholder
    color = (50, 50, 50) if value else (170, 170, 170)
    _draw_text(img, display, x + 8, y + (h - font_size) // 2 - 1, color, font_size)

    return Element(id=eid, bounds=[x, y, x + w, y + h], visual_type="input_field",
                   text=value or placeholder)


def draw_text_label(
    img: np.ndarray, eid: str,
    x: int, y: int,
    text: str,
    font_size: int = 14,
    color: Tuple = (50, 50, 50),
    bold: bool = False,
) -> Element:
    """Draw a text label with anti-aliased rendering."""
    tw, th = _draw_text(img, text, x, y, color, font_size, bold)
    return Element(id=eid, bounds=[x, y, x + tw, y + th + 4], visual_type="text", text=text)


def draw_checkbox(
    img: np.ndarray, eid: str,
    x: int, y: int,
    size: int = 18,
    checked: bool = False,
    label: str = "",
    box_color: Tuple = (200, 200, 200),
    check_color: Tuple = (66, 133, 244),
    text_color: Tuple = (50, 50, 50),
) -> Element:
    """Draw a checkbox with optional label."""
    cv2.rectangle(img, (x, y), (x + size, y + size), box_color, 1, cv2.LINE_AA)
    if checked:
        cv2.line(img, (x + 3, y + size // 2), (x + size // 2 - 1, y + size - 4), check_color, 2, cv2.LINE_AA)
        cv2.line(img, (x + size // 2 - 1, y + size - 4), (x + size - 3, y + 3), check_color, 2, cv2.LINE_AA)

    total_w = size
    if label:
        tw, th = _draw_text(img, label, x + size + 8, y + 1, text_color, 13)
        total_w = size + 8 + tw

    return Element(id=eid, bounds=[x, y, x + total_w, y + size], visual_type="checkbox", text=label)


def draw_toggle(
    img: np.ndarray, eid: str,
    x: int, y: int,
    on: bool = False,
    label: str = "",
    on_color: Tuple = (66, 133, 244),
    off_color: Tuple = (180, 180, 180),
    text_color: Tuple = (50, 50, 50),
) -> Element:
    """Draw a toggle switch."""
    tw_toggle, th = 40, 20
    bg = on_color if on else off_color
    # Track (rounded)
    _draw_rounded_rect(img, x, y, tw_toggle, th, bg, radius=th // 2)
    # Knob
    knob_x = x + tw_toggle - 12 if on else x + 12
    cv2.circle(img, (knob_x, y + th // 2), 7, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, (knob_x, y + th // 2), 7, (220, 220, 220), 1, cv2.LINE_AA)

    total_w = tw_toggle
    if label:
        lw, lh = _draw_text(img, label, x + tw_toggle + 10, y + 2, text_color, 13)
        total_w = tw_toggle + 10 + lw

    return Element(id=eid, bounds=[x, y, x + total_w, y + th], visual_type="checkbox", text=label)


def draw_icon(
    img: np.ndarray, eid: str,
    x: int, y: int,
    size: int = 24,
    icon_type: str = "menu",
    color: Tuple = (100, 100, 100),
) -> Element:
    """Draw a simple icon."""
    if icon_type == "menu":
        for i in range(3):
            cv2.line(img, (x + 4, y + 6 + i * 6), (x + size - 4, y + 6 + i * 6), color, 2, cv2.LINE_AA)
    elif icon_type == "search":
        cv2.circle(img, (x + size // 2 - 2, y + size // 2 - 2), 6, color, 2, cv2.LINE_AA)
        cv2.line(img, (x + size // 2 + 2, y + size // 2 + 2), (x + size - 4, y + size - 4), color, 2, cv2.LINE_AA)
    elif icon_type == "close":
        cv2.line(img, (x + 4, y + 4), (x + size - 4, y + size - 4), color, 2, cv2.LINE_AA)
        cv2.line(img, (x + size - 4, y + 4), (x + 4, y + size - 4), color, 2, cv2.LINE_AA)
    elif icon_type == "settings":
        cv2.circle(img, (x + size // 2, y + size // 2), 6, color, 2, cv2.LINE_AA)
        cv2.circle(img, (x + size // 2, y + size // 2), 2, color, -1, cv2.LINE_AA)
    elif icon_type == "user":
        cv2.circle(img, (x + size // 2, y + 7), 5, color, 2, cv2.LINE_AA)
        cv2.ellipse(img, (x + size // 2, y + size), (8, 6), 0, 180, 360, color, 2, cv2.LINE_AA)

    return Element(id=eid, bounds=[x, y, x + size, y + size], visual_type="icon", text=icon_type)


def draw_separator(
    img: np.ndarray, eid: str,
    x: int, y: int, w: int,
    color: Tuple = (220, 220, 220),
) -> Element:
    """Draw a horizontal separator line."""
    cv2.line(img, (x, y), (x + w, y), color, 1, cv2.LINE_AA)
    return Element(id=eid, bounds=[x, y, x + w, y + 2], visual_type="divider")


def draw_container(
    img: np.ndarray, eid: str,
    x: int, y: int, w: int, h: int,
    bg_color: Tuple = (255, 255, 255),
    border_color: Tuple = None,
    shadow: bool = False,
    radius: int = 6,
) -> Element:
    """Draw a container/card background."""
    if shadow:
        # Soft shadow
        for i in range(3, 0, -1):
            shade = (210 - i * 5, 210 - i * 5, 210 - i * 5)
            cv2.rectangle(img, (x + i, y + i), (x + w + i, y + h + i), shade, -1)
    _draw_rounded_rect(img, x, y, w, h, bg_color, radius=radius, border_color=border_color)
    return Element(id=eid, bounds=[x, y, x + w, y + h], visual_type="block")


def draw_dropdown(
    img: np.ndarray, eid: str,
    x: int, y: int, w: int, h: int,
    text: str = "Select...",
    bg_color: Tuple = (255, 255, 255),
    border_color: Tuple = (200, 200, 200),
) -> Element:
    """Draw a dropdown/combobox."""
    _draw_rounded_rect(img, x, y, w, h, bg_color, radius=3, border_color=border_color)
    _draw_text(img, text, x + 8, y + (h - 13) // 2 - 1, (80, 80, 80), 13)
    # Chevron arrow
    ax = x + w - 18
    ay = y + h // 2
    pts = np.array([[ax, ay - 3], [ax + 8, ay - 3], [ax + 4, ay + 3]], np.int32)
    cv2.fillPoly(img, [pts], (120, 120, 120))
    return Element(id=eid, bounds=[x, y, x + w, y + h], visual_type="input_field", text=text)
