"""Dialog template."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_container,
    draw_separator, draw_icon,
)
from ..text_content import DIALOG_TITLES, DIALOG_MESSAGES, BUTTON_LABELS


class DialogTemplate(UITemplate):
    name = "dialog"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Dimmed background overlay
        overlay = np.full_like(img, 100)
        img = cv2_addWeighted(img, 0.4, overlay, 0.6)

        # Dialog card
        dlg_w = self.rand_int(self.s(300), self.s(440))
        dlg_h = self.rand_int(self.s(180), self.s(280))
        dx = (self.width - dlg_w) // 2
        dy = (self.height - dlg_h) // 2

        card = draw_container(img, self.next_id(), dx, dy, dlg_w, dlg_h,
                              bg_color=t.surface, border_color=t.border, shadow=True)
        self.elements.append(card)

        pad = self.s(20)
        y = dy + pad

        # Close icon (top-right)
        if self.rand_bool(0.7):
            elem = draw_icon(img, self.next_id(), dx + dlg_w - self.s(30), dy + self.s(8),
                             self.s(20),
                             "close", color=t.text_secondary)
            self.elements.append(elem)

        # Title
        title = self.pick(DIALOG_TITLES)
        elem = draw_text_label(img, self.next_id(), dx + pad, y, title,
                               font_size=self.s(18), color=t.text_primary, bold=True)
        self.elements.append(elem)
        y += self.s(30)

        # Separator
        elem = draw_separator(img, self.next_id(), dx + pad, y, dlg_w - 2 * pad, color=t.border)
        self.elements.append(elem)
        y += self.s(15)

        # Message
        message = self.pick(DIALOG_MESSAGES)
        # Word-wrap by splitting into lines of ~40 chars
        words = message.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 > 45:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)

        for line in lines:
            elem = draw_text_label(img, self.next_id(), dx + pad, y, line,
                                   font_size=self.s(13), color=t.text_primary)
            self.elements.append(elem)
            y += self.s(18)

        # Buttons at bottom
        y = dy + dlg_h - pad - self.s(32)
        num_btns = self.rand_int(1, 3)
        btn_labels = self.pick_n(["OK", "Cancel", "Yes", "No", "Close", "Confirm", "Retry"], num_btns)

        bx = dx + dlg_w - pad
        for i, label in enumerate(reversed(btn_labels)):
            bw = len(label) * self.s(10) + self.s(20)
            bx -= bw
            if i == len(btn_labels) - 1:
                # Primary button
                elem = draw_button(img, self.next_id(), bx, y, bw, self.s(32), label,
                                   bg_color=t.primary, text_color=(255, 255, 255))
            else:
                # Secondary button
                elem = draw_button(img, self.next_id(), bx, y, bw, self.s(32), label,
                                   bg_color=t.surface, text_color=t.text_primary,
                                   border_color=t.border)
            self.elements.append(elem)
            bx -= self.s(10)

        return img, self.elements


def cv2_addWeighted(img1, alpha, img2, beta):
    """Blend two images."""
    import cv2
    return cv2.addWeighted(img1, alpha, img2, beta, 0)
