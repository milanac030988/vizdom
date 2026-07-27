"""Settings panel template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_toggle, draw_checkbox,
    draw_container, draw_separator, draw_dropdown, draw_input_field,
)
from ..text_content import FIELD_LABELS, STATUS_VALUES


class SettingsPanelTemplate(UITemplate):
    name = "settings"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Title bar
        draw_container(img, self.next_id(), 0, 0, self.width, self.s(40), bg_color=t.primary)
        self.elements.append(
            draw_text_label(img, self.next_id(), self.s(15), self.s(12), "Settings",
                            font_size=self.s(18), color=(255, 255, 255), bold=True)
        )

        # Content area
        y = self.s(55)
        pad = self.s(20)
        content_w = self.width - 2 * pad

        # Generate 2-5 setting groups
        groups = self.rand_int(2, 5)
        group_names = self.pick_n(
            ["General", "Display", "Network", "Security", "Privacy",
             "Notifications", "Audio", "Advanced", "Account"],
            groups
        )

        for group_name in group_names:
            # Group header
            elem = draw_text_label(img, self.next_id(), pad, y, group_name,
                                   font_size=self.s(16), color=t.text_primary, bold=True)
            self.elements.append(elem)
            y += self.s(28)

            # Settings items (2-5 per group)
            num_items = self.rand_int(2, 5)
            labels = self.pick_n(FIELD_LABELS, num_items)

            for label in labels:
                # Setting row
                elem = draw_text_label(img, self.next_id(), pad + self.s(10), y, label,
                                       font_size=self.s(13), color=t.text_primary)
                self.elements.append(elem)

                # Random control on the right side
                control_type = self.rand_int(0, 2)
                cx = self.width - pad - self.s(100)

                if control_type == 0:
                    # Toggle
                    elem = draw_toggle(img, self.next_id(), cx, y - self.s(2),
                                       on=self.rand_bool(), on_color=t.primary)
                    self.elements.append(elem)
                elif control_type == 1:
                    # Dropdown
                    val = self.pick(STATUS_VALUES)
                    elem = draw_dropdown(img, self.next_id(), cx - self.s(20), y - self.s(4),
                                         self.s(120), self.s(24),
                                         text=val, bg_color=t.input_bg, border_color=t.border)
                    self.elements.append(elem)
                else:
                    # Checkbox
                    elem = draw_checkbox(img, self.next_id(), cx + self.s(20), y - self.s(2),
                                         size=self.s(16),
                                         checked=self.rand_bool(), box_color=t.border,
                                         check_color=t.primary)
                    self.elements.append(elem)

                y += self.s(30)

            # Separator between groups
            elem = draw_separator(img, self.next_id(), pad, y, content_w, color=t.border)
            self.elements.append(elem)
            y += self.s(15)

            if y > self.height - self.s(60):
                break

        # Bottom buttons
        y = self.height - self.s(45)
        btn_w = self.s(80)
        elem = draw_button(img, self.next_id(), self.width - pad - btn_w, y, btn_w, self.s(32),
                           "Save", bg_color=t.primary, text_color=(255, 255, 255))
        self.elements.append(elem)

        elem = draw_button(img, self.next_id(), self.width - pad - btn_w * 2 - self.s(10), y,
                           btn_w, self.s(32),
                           "Cancel", bg_color=t.surface, text_color=t.text_primary,
                           border_color=t.border)
        self.elements.append(elem)

        return img, self.elements
