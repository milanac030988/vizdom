"""
Render LLM-designed UI layouts into images with ground truth.

Takes the JSON output from LLMDesigner and produces:
- Screenshot (PNG)
- Ground truth JSON (VizDOM format)
"""

import numpy as np
import cv2
from typing import Dict, List, Tuple

from .primitives import (
    Element, draw_button, draw_input_field, draw_text_label,
    draw_checkbox, draw_toggle, draw_icon, draw_separator,
    draw_container, draw_dropdown,
)
from .themes import Theme, THEMES
from .ground_truth import build_ground_truth


class LLMRenderer:
    """Render an LLM-designed layout into an image."""

    def __init__(self):
        self._id_counter = 0

    def next_id(self) -> str:
        self._id_counter += 1
        return f"E{self._id_counter}"

    def render(
        self,
        layout: Dict,
        width: int = 800,
        height: int = 600,
    ) -> Tuple[np.ndarray, List[Element], Dict]:
        """
        Render a layout dict into an image with ground truth.

        Args:
            layout: LLM-generated layout dict with "elements", "title", "theme"
            width: Canvas width
            height: Canvas height

        Returns:
            (image, elements, ground_truth_json)
        """
        self._id_counter = 0

        # Resolve theme
        theme_name = layout.get("theme", "light")
        theme = THEMES.get(theme_name, THEMES["light"])

        # Create canvas
        img = np.full((height, width, 3), theme.background, dtype=np.uint8)
        elements = []

        # Render each element from the layout (supports nested elements)
        self._render_recursive(img, layout.get("elements", []), theme, elements)

        # Build ground truth
        gt = build_ground_truth(elements, (width, height))
        gt["layout_title"] = layout.get("title", "Untitled")
        gt["layout_theme"] = theme_name

        return img, elements, gt

    def _render_recursive(
        self,
        img: np.ndarray,
        elem_specs: List[Dict],
        theme: Theme,
        elements: List[Element],
    ):
        """Recursively render elements, handling nested children."""
        for spec in elem_specs:
            rendered = self._render_element(img, spec, theme)
            if rendered:
                elements.append(rendered)
            # Render nested children inside containers
            children = spec.get("elements", [])
            if children:
                self._render_recursive(img, children, theme, elements)

    def _render_element(
        self,
        img: np.ndarray,
        spec: Dict,
        theme: Theme,
    ) -> Element:
        """Render a single element from its spec dict."""
        etype = spec.get("type", "")
        text = str(spec.get("text", ""))
        x = int(spec.get("x", 0))
        y = int(spec.get("y", 0))
        w = int(spec.get("w", 100))
        h = int(spec.get("h", 30))

        # Clamp to canvas
        h_img, w_img = img.shape[:2]
        x = max(0, min(x, w_img - 10))
        y = max(0, min(y, h_img - 10))
        w = max(10, min(w, w_img - x))
        h = max(10, min(h, h_img - y))

        eid = self.next_id()

        if etype == "button":
            return draw_button(img, eid, x, y, w, h, text or "Button",
                               bg_color=theme.primary, text_color=(255, 255, 255))

        elif etype == "input_field":
            return draw_input_field(img, eid, x, y, w, h,
                                    placeholder=text, bg_color=theme.input_bg,
                                    border_color=theme.border)

        elif etype == "text":
            font_sz = 14
            if h > 20:
                font_sz = 18
            if h > 30:
                font_sz = 24
            return draw_text_label(img, eid, x, y, text or "Label",
                                   font_size=font_sz, color=theme.text_primary)

        elif etype == "checkbox":
            checked = spec.get("checked", False)
            return draw_checkbox(img, eid, x, y, size=min(h, 20),
                                 checked=checked, label=text,
                                 box_color=theme.border, check_color=theme.primary,
                                 text_color=theme.text_primary)

        elif etype == "toggle":
            on = spec.get("on", False)
            return draw_toggle(img, eid, x, y, on=on, label=text,
                               on_color=theme.primary, text_color=theme.text_primary)

        elif etype == "icon":
            icon_type = spec.get("icon", "settings")
            return draw_icon(img, eid, x, y, min(w, h), icon_type,
                             color=theme.text_secondary)

        elif etype == "separator":
            return draw_separator(img, eid, x, y, w, color=theme.border)

        elif etype == "container":
            return draw_container(img, eid, x, y, w, h,
                                  bg_color=theme.surface, border_color=theme.border)

        elif etype == "dropdown":
            return draw_dropdown(img, eid, x, y, w, h,
                                 text=text or "Select...",
                                 bg_color=theme.input_bg, border_color=theme.border)

        else:
            # Unknown type — render as text label
            return draw_text_label(img, eid, x, y, text or etype,
                                   font_size=13, color=theme.text_secondary)
