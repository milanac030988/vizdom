"""Data table template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_container,
    draw_separator, draw_checkbox, draw_input_field, draw_icon,
)
from ..text_content import TABLE_HEADERS, STATUS_VALUES, STAT_VALUES, INPUT_VALUES


class DataTableTemplate(UITemplate):
    name = "data_table"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        pad = self.s(15)
        y = pad

        # Title
        elem = draw_text_label(img, self.next_id(), pad, y, "Data Management",
                               font_size=self.s(18), color=t.text_primary, bold=True)
        self.elements.append(elem)

        # Action buttons (top right)
        rx = self.width - pad
        for label in ["Export", "Add New"]:
            bw = len(label) * self.s(9) + self.s(20)
            rx -= bw
            elem = draw_button(img, self.next_id(), rx, y - self.s(2), bw, self.s(28), label,
                               bg_color=t.primary, text_color=(255, 255, 255),
                               font_size=self.s(12))
            self.elements.append(elem)
            rx -= self.s(8)

        y += self.s(35)

        # Search bar
        search_w = self.rand_int(self.s(200), self.s(300))
        elem = draw_input_field(img, self.next_id(), pad, y, search_w, self.s(28),
                                placeholder="Search...", bg_color=t.input_bg,
                                border_color=t.border, font_size=self.s(12))
        self.elements.append(elem)
        y += self.s(40)

        # Table
        num_cols = self.rand_int(3, 6)
        num_rows = self.rand_int(5, 12)
        has_checkbox = self.rand_bool(0.5)
        has_actions = self.rand_bool(0.6)

        headers = self.pick_n(TABLE_HEADERS, num_cols)
        table_w = self.width - 2 * pad
        checkbox_w = self.s(30) if has_checkbox else 0
        action_w = self.s(80) if has_actions else 0
        data_w = table_w - checkbox_w - action_w
        col_w = data_w // num_cols

        row_h = self.s(26)

        # Header row
        hdr_bg = draw_container(img, self.next_id(), pad, y, table_w, row_h, bg_color=t.surface)

        hx = pad + checkbox_w
        if has_checkbox:
            elem = draw_checkbox(img, self.next_id(), pad + self.s(6), y + self.s(4),
                                 size=self.s(14),
                                 checked=False, box_color=t.border, check_color=t.primary)
            self.elements.append(elem)

        for j, hdr in enumerate(headers):
            elem = draw_text_label(img, self.next_id(), hx + j * col_w + self.s(6),
                                   y + self.s(6),
                                   hdr, font_size=self.s(12), color=t.text_primary)
            self.elements.append(elem)

        if has_actions:
            elem = draw_text_label(img, self.next_id(), pad + table_w - action_w + self.s(6),
                                   y + self.s(6),
                                   "Actions", font_size=self.s(12), color=t.text_primary)
            self.elements.append(elem)

        y += row_h
        elem = draw_separator(img, self.next_id(), pad, y, table_w, color=t.border)
        self.elements.append(elem)
        y += 1

        # Data rows
        for row in range(num_rows):
            if y + row_h > self.height - self.s(40):
                break

            # Alternating background
            if row % 2 == 1:
                draw_container(img, self.next_id(), pad, y, table_w, row_h,
                               bg_color=t.surface)

            hx = pad + checkbox_w

            if has_checkbox:
                elem = draw_checkbox(img, self.next_id(), pad + self.s(6), y + self.s(5),
                                     size=self.s(14),
                                     checked=self.rand_bool(0.3), box_color=t.border,
                                     check_color=t.primary)
                self.elements.append(elem)

            for j in range(num_cols):
                if j == 0:
                    val = str(self.rand_int(1, 999))
                elif "Status" in headers[j]:
                    val = self.pick(STATUS_VALUES[:8])
                elif "Date" in headers[j]:
                    val = f"2026-{self.rand_int(1,12):02d}-{self.rand_int(1,28):02d}"
                elif "Value" in headers[j] or "Count" in headers[j] or "Score" in headers[j]:
                    val = self.pick(STAT_VALUES)
                else:
                    val = self.pick(INPUT_VALUES + STATUS_VALUES)

                elem = draw_text_label(img, self.next_id(), hx + j * col_w + self.s(6),
                                       y + self.s(7),
                                       val[:15], font_size=self.s(11), color=t.text_primary)
                self.elements.append(elem)

            if has_actions:
                ax = pad + table_w - action_w + self.s(4)
                for act_label, act_color in [("Edit", t.primary), ("Del", t.error)]:
                    aw = self.s(32)
                    elem = draw_button(img, self.next_id(), ax, y + self.s(3), aw, self.s(20),
                                       act_label,
                                       bg_color=act_color, text_color=(255, 255, 255),
                                       font_size=self.s(10))
                    self.elements.append(elem)
                    ax += aw + self.s(4)

            y += row_h
            elem = draw_separator(img, self.next_id(), pad, y, table_w, color=t.border)
            self.elements.append(elem)
            y += 1

        # Pagination footer
        y += self.s(10)
        elem = draw_text_label(img, self.next_id(), pad, y,
                               f"Showing 1-{min(num_rows, 10)} of {self.rand_int(50, 500)}",
                               font_size=self.s(11), color=t.text_secondary)
        self.elements.append(elem)

        # Page buttons
        px = self.width - pad
        for page_label in reversed(["Next", "2", "1", "Prev"]):
            pw = len(page_label) * self.s(8) + self.s(12)
            px -= pw
            elem = draw_button(img, self.next_id(), px, y - self.s(4), pw, self.s(22),
                               page_label,
                               bg_color=t.surface, text_color=t.text_primary,
                               border_color=t.border, font_size=self.s(11))
            self.elements.append(elem)
            px -= self.s(4)

        return img, self.elements
