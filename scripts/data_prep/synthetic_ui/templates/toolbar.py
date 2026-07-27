"""Toolbar template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_container,
    draw_separator, draw_icon, draw_input_field,
)
from ..text_content import BUTTON_LABELS


class ToolbarTemplate(UITemplate):
    name = "toolbar"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Toolbar bar
        bar_h = self.rand_int(self.s(36), self.s(48))
        bar = draw_container(img, self.next_id(), 0, 0, self.width, bar_h,
                             bg_color=t.surface, border_color=t.border)
        self.elements.append(bar)

        x = self.s(8)
        icon_size = bar_h - self.s(12)

        # Icon buttons (4-8)
        num_icons = self.rand_int(4, 8)
        icon_types = ["menu", "search", "settings", "close", "user"]

        for i in range(num_icons):
            itype = self.pick(icon_types)
            elem = draw_icon(img, self.next_id(), x, self.s(6), icon_size, itype,
                             color=t.text_secondary)
            self.elements.append(elem)
            x += icon_size + self.s(8)

            # Occasional separator
            if self.rand_bool(0.3) and i < num_icons - 1:
                elem = draw_separator(img, self.next_id(), x, self.s(4), 1, color=t.border)
                self.elements.append(elem)
                x += self.s(8)

        # Optional search field
        if self.rand_bool(0.6):
            x += self.s(10)
            search_w = self.rand_int(self.s(120), self.s(200))
            elem = draw_input_field(img, self.next_id(), x, self.s(6), search_w,
                                    bar_h - self.s(12),
                                    placeholder="Search...", bg_color=t.input_bg,
                                    border_color=t.border, font_size=self.s(12))
            self.elements.append(elem)
            x += search_w + self.s(10)

        # Right-aligned text buttons
        rx = self.width - self.s(10)
        btn_labels = self.pick_n(BUTTON_LABELS, self.rand_int(2, 4))
        for label in reversed(btn_labels):
            bw = len(label) * self.s(9) + self.s(16)
            rx -= bw
            elem = draw_button(img, self.next_id(), rx, self.s(5), bw, bar_h - self.s(10),
                               label, bg_color=t.primary, text_color=(255, 255, 255),
                               font_size=self.s(12))
            self.elements.append(elem)
            rx -= self.s(6)

        # Content area below toolbar — simple text area or form
        y = bar_h + self.s(20)
        pad = self.s(20)

        # Title
        elem = draw_text_label(img, self.next_id(), pad, y, "Document Editor",
                               font_size=self.s(16), color=t.text_primary, bold=True)
        self.elements.append(elem)
        y += self.s(35)

        # Simulated content lines
        num_lines = self.rand_int(5, 12)
        for _ in range(num_lines):
            if y > self.height - self.s(30):
                break
            line_w = self.rand_int(self.width // 3, self.width - 2 * pad)
            line_text = " ".join(self.pick_n(
                ["Lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
                 "adipiscing", "elit", "sed", "do", "eiusmod", "tempor"],
                self.rand_int(4, 8)
            ))
            elem = draw_text_label(img, self.next_id(), pad, y, line_text,
                                   font_size=self.s(12), color=t.text_primary)
            self.elements.append(elem)
            y += self.s(20)

        return img, self.elements
