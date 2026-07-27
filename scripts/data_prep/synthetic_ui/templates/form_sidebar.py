"""Form with sidebar navigation template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_input_field, draw_text_label,
    draw_checkbox, draw_container, draw_separator, draw_dropdown, draw_icon,
)
from ..text_content import (
    FIELD_LABELS, INPUT_VALUES, INPUT_PLACEHOLDERS, BUTTON_LABELS,
    MENU_ITEMS, STATUS_VALUES, APP_TITLES,
)


class FormSidebarTemplate(UITemplate):
    name = "form_sidebar"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Top bar
        bar_h = self.s(38)
        draw_container(img, self.next_id(), 0, 0, self.width, bar_h, bg_color=t.primary)
        title = self.pick(APP_TITLES)
        elem = draw_text_label(img, self.next_id(), self.s(12), self.s(10), title,
                               font_size=self.s(16), color=(255, 255, 255), bold=True)
        self.elements.append(elem)

        # Sidebar
        sidebar_w = self.s(self.rand_int(160, 200))
        sidebar = draw_container(img, self.next_id(), 0, bar_h, sidebar_w,
                                 self.height - bar_h, bg_color=t.surface, border_color=t.border)
        self.elements.append(sidebar)

        sy = bar_h + self.s(15)
        nav_items = self.pick_n(MENU_ITEMS, self.rand_int(5, 10))
        active_idx = self.rand_int(0, len(nav_items) - 1)

        for i, item in enumerate(nav_items):
            if i == active_idx:
                # Active item highlight
                draw_container(img, self.next_id(), 0, sy - self.s(2),
                               sidebar_w, self.s(24), bg_color=t.primary)
                elem = draw_text_label(img, self.next_id(), self.s(16), sy,
                                       item, font_size=self.s(13), color=(255, 255, 255))
            else:
                elem = draw_text_label(img, self.next_id(), self.s(16), sy,
                                       item, font_size=self.s(13), color=t.text_primary)
            self.elements.append(elem)
            sy += self.s(28)

        # Main content - Form
        cx = sidebar_w + self.s(25)
        cy = bar_h + self.s(15)
        content_w = self.width - sidebar_w - self.s(50)

        # Section title
        section = self.pick(["General", "Account", "Configuration", "Properties", "Details"])
        elem = draw_text_label(img, self.next_id(), cx, cy, section,
                               font_size=self.s(18), color=t.text_primary, bold=True)
        self.elements.append(elem)
        cy += self.s(30)

        elem = draw_separator(img, self.next_id(), cx, cy, content_w, color=t.border)
        self.elements.append(elem)
        cy += self.s(15)

        # Form fields (label-value pairs, 2-column layout)
        num_fields = self.rand_int(6, 14)
        labels = self.pick_n(FIELD_LABELS, min(num_fields, len(FIELD_LABELS)))
        col_w = (content_w - self.s(20)) // 2

        for i, label in enumerate(labels):
            # Alternate between left and right columns
            col = i % 2
            field_x = cx + col * (col_w + self.s(20))
            field_y = cy + (i // 2) * self.s(60)

            if field_y + self.s(60) > self.height - self.s(60):
                break

            # Label
            elem = draw_text_label(img, self.next_id(), field_x, field_y, label,
                                   font_size=self.s(12), color=t.text_secondary)
            self.elements.append(elem)

            # Input or dropdown
            if self.rand_bool(0.7):
                value = self.pick(INPUT_VALUES) if self.rand_bool(0.5) else ""
                placeholder = self.pick(INPUT_PLACEHOLDERS) if not value else ""
                elem = draw_input_field(img, self.next_id(), field_x, field_y + self.s(18),
                                        col_w, self.s(30), placeholder=placeholder,
                                        value=value, bg_color=t.input_bg,
                                        border_color=t.border, font_size=self.s(13))
            else:
                val = self.pick(STATUS_VALUES)
                elem = draw_dropdown(img, self.next_id(), field_x, field_y + self.s(18),
                                     col_w, self.s(30), text=val,
                                     bg_color=t.input_bg, border_color=t.border)
            self.elements.append(elem)

        # Bottom buttons
        by = self.height - self.s(50)
        elem = draw_button(img, self.next_id(), cx, by, self.s(90), self.s(34),
                           "Save", bg_color=t.primary, text_color=(255, 255, 255),
                           font_size=self.s(14))
        self.elements.append(elem)

        elem = draw_button(img, self.next_id(), cx + self.s(100), by, self.s(90), self.s(34),
                           "Cancel", bg_color=t.surface, text_color=t.text_primary,
                           border_color=t.border, font_size=self.s(14))
        self.elements.append(elem)

        if self.rand_bool(0.5):
            elem = draw_button(img, self.next_id(), cx + self.s(200), by, self.s(90), self.s(34),
                               "Reset", bg_color=t.surface, text_color=t.error,
                               border_color=t.error, font_size=self.s(14))
            self.elements.append(elem)

        return img, self.elements
