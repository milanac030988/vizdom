"""Login form template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_input_field, draw_text_label,
    draw_checkbox, draw_container, draw_separator, draw_icon,
)
from ..text_content import BUTTON_LABELS, INPUT_PLACEHOLDERS


class LoginFormTemplate(UITemplate):
    name = "login"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Form card centered
        card_w = self.s(self.rand_int(280, 380))
        card_h = self.s(self.rand_int(320, 420))
        cx = (self.width - card_w) // 2
        cy = (self.height - card_h) // 2
        pad = self.s(20)

        card = draw_container(img, self.next_id(), cx, cy, card_w, card_h,
                              bg_color=t.surface, border_color=t.border, shadow=True)
        self.elements.append(card)

        y = cy + pad

        # Title
        title = self.pick(["Sign In", "Login", "Welcome Back", "Account Login"])
        elem = draw_text_label(img, self.next_id(), cx + pad, y, title,
                               font_size=self.s(20), color=t.text_primary, bold=True)
        self.elements.append(elem)
        y += self.s(40)

        # Optional subtitle
        if self.rand_bool(0.6):
            sub = self.pick(["Enter your credentials", "Please sign in to continue",
                             "Access your account"])
            elem = draw_text_label(img, self.next_id(), cx + pad, y, sub,
                                   font_size=self.s(13), color=t.text_secondary)
            self.elements.append(elem)
            y += self.s(25)

        y += self.s(10)

        # Fields (2-4)
        fields = self.pick_n(["Username", "Email", "Password", "Confirm Password"], self.rand_int(2, 4))
        field_w = card_w - 2 * pad

        for label_text in fields:
            elem = draw_text_label(img, self.next_id(), cx + pad, y, label_text,
                                   font_size=self.s(13), color=t.text_primary)
            self.elements.append(elem)
            y += self.s(18)

            placeholder = label_text.lower()
            elem = draw_input_field(img, self.next_id(), cx + pad, y, field_w, self.s(32),
                                    placeholder=placeholder, bg_color=t.input_bg,
                                    border_color=t.border, font_size=self.s(13))
            self.elements.append(elem)
            y += self.s(42)

        # Remember me checkbox
        if self.rand_bool(0.7):
            elem = draw_checkbox(img, self.next_id(), cx + pad, y, size=self.s(16),
                                 checked=self.rand_bool(), label="Remember me",
                                 text_color=t.text_primary)
            self.elements.append(elem)
            y += self.s(28)

        # Submit button
        btn_text = self.pick(["Sign In", "Login", "Submit", "Continue"])
        elem = draw_button(img, self.next_id(), cx + pad, y, field_w, self.s(36),
                           btn_text, bg_color=t.primary, text_color=(255, 255, 255),
                           font_size=self.s(14))
        self.elements.append(elem)
        y += self.s(46)

        # Optional separator + social login
        if self.rand_bool(0.4):
            elem = draw_separator(img, self.next_id(), cx + pad, y, field_w, color=t.border)
            self.elements.append(elem)
            y += self.s(15)

            elem = draw_text_label(img, self.next_id(), cx + pad + field_w // 2 - self.s(30), y,
                                   "or sign in with", font_size=self.s(11), color=t.text_secondary)
            self.elements.append(elem)
            y += self.s(25)

            # Social buttons
            social = self.pick_n(["Google", "GitHub", "Microsoft", "Apple"], self.rand_int(1, 3))
            bx = cx + pad
            bw = (field_w - self.s(10) * (len(social) - 1)) // len(social)
            for s_name in social:
                elem = draw_button(img, self.next_id(), bx, y, bw, self.s(30), s_name,
                                   bg_color=t.surface, text_color=t.text_primary,
                                   border_color=t.border, font_size=self.s(13))
                self.elements.append(elem)
                bx += bw + self.s(10)

        # Forgot password link
        if self.rand_bool(0.6):
            y += self.s(40)
            elem = draw_text_label(img, self.next_id(), cx + pad, y, "Forgot password?",
                                   font_size=self.s(11), color=t.primary)
            self.elements.append(elem)

        return img, self.elements
