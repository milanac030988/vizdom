"""Dashboard template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_container,
    draw_separator, draw_icon,
)
from ..text_content import STAT_LABELS, STAT_VALUES, MENU_ITEMS, TABLE_HEADERS, STATUS_VALUES


class DashboardTemplate(UITemplate):
    name = "dashboard"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Top navbar
        nav = draw_container(img, self.next_id(), 0, 0, self.width, self.s(44), bg_color=t.primary)
        self.elements.append(nav)

        elem = draw_icon(img, self.next_id(), self.s(10), self.s(10), self.s(24), "menu",
                         color=(255, 255, 255))
        self.elements.append(elem)

        elem = draw_text_label(img, self.next_id(), self.s(44), self.s(14), "Dashboard",
                               font_size=self.s(16), color=(255, 255, 255), bold=True)
        self.elements.append(elem)

        # Nav buttons
        nav_items = self.pick_n(MENU_ITEMS, self.rand_int(3, 5))
        nx = self.width - self.s(15)
        for item in reversed(nav_items):
            ts = len(item) * self.s(8) + self.s(16)
            nx -= ts
            elem = draw_text_label(img, self.next_id(), nx + self.s(8), self.s(16), item,
                                   font_size=self.s(13), color=(230, 230, 230))
            self.elements.append(elem)

        # Optional sidebar
        sidebar_w = 0
        if self.rand_bool(0.5):
            sidebar_w = self.rand_int(self.s(140), self.s(180))
            sb = draw_container(img, self.next_id(), 0, self.s(44), sidebar_w,
                                self.height - self.s(44),
                                bg_color=t.surface, border_color=t.border)
            self.elements.append(sb)

            sy = self.s(60)
            sb_items = self.pick_n(MENU_ITEMS, self.rand_int(4, 8))
            for item in sb_items:
                elem = draw_text_label(img, self.next_id(), self.s(15), sy, item,
                                       font_size=self.s(13), color=t.text_primary)
                self.elements.append(elem)
                sy += self.s(28)

        # Stat cards
        content_x = sidebar_w + self.s(15)
        content_w = self.width - content_x - self.s(15)
        card_count = self.rand_int(3, 6)
        card_w = (content_w - self.s(10) * (card_count - 1)) // card_count
        card_h = self.s(70)

        y = self.s(60)
        stats = list(zip(
            self.pick_n(STAT_LABELS, card_count),
            self.pick_n(STAT_VALUES, card_count),
        ))

        for i, (label, value) in enumerate(stats):
            cx = content_x + i * (card_w + self.s(10))
            card = draw_container(img, self.next_id(), cx, y, card_w, card_h,
                                  bg_color=t.surface, border_color=t.border, shadow=True)
            self.elements.append(card)

            elem = draw_text_label(img, self.next_id(), cx + self.s(10), y + self.s(10), label,
                                   font_size=self.s(11), color=t.text_secondary)
            self.elements.append(elem)

            elem = draw_text_label(img, self.next_id(), cx + self.s(10), y + self.s(32), value,
                                   font_size=self.s(18), color=t.text_primary, bold=True)
            self.elements.append(elem)

        # Data table
        y += card_h + self.s(20)
        table_x = content_x
        table_w = content_w

        elem = draw_text_label(img, self.next_id(), table_x, y, "Recent Activity",
                               font_size=self.s(14), color=t.text_primary, bold=True)
        self.elements.append(elem)
        y += self.s(28)

        # Table header
        num_cols = self.rand_int(3, 5)
        headers = self.pick_n(TABLE_HEADERS, num_cols)
        col_w = table_w // num_cols

        # Header row background
        draw_container(img, self.next_id(), table_x, y, table_w, self.s(24), bg_color=t.border)

        for j, hdr in enumerate(headers):
            elem = draw_text_label(img, self.next_id(), table_x + j * col_w + self.s(8),
                                   y + self.s(6),
                                   hdr, font_size=self.s(11), color=t.text_primary)
            self.elements.append(elem)
        y += self.s(26)

        # Table rows
        num_rows = self.rand_int(3, 8)
        for row in range(num_rows):
            if y > self.height - self.s(30):
                break

            # Alternating row background
            if row % 2 == 1:
                draw_container(img, self.next_id(), table_x, y, table_w, self.s(22),
                               bg_color=t.surface)

            for j in range(num_cols):
                if j == 0:
                    val = str(self.rand_int(1000, 9999))
                elif headers[j] == "Status":
                    val = self.pick(STATUS_VALUES[:6])
                else:
                    val = self.pick(STATUS_VALUES + STAT_VALUES)

                elem = draw_text_label(img, self.next_id(), table_x + j * col_w + self.s(8),
                                       y + self.s(5),
                                       val, font_size=self.s(11), color=t.text_primary)
                self.elements.append(elem)
            y += self.s(24)

            elem = draw_separator(img, self.next_id(), table_x, y - self.s(1), table_w,
                                  color=t.border)
            self.elements.append(elem)

        return img, self.elements
