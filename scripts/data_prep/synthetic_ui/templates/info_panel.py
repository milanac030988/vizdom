"""Information panel template (like CMST, system info, device properties)."""

import numpy as np
from typing import List, Tuple

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_container,
    draw_separator, draw_icon,
)
from ..text_content import FIELD_LABELS, STATUS_VALUES, STAT_VALUES, APP_TITLES


# Domain-specific label-value pairs
INFO_SECTIONS = {
    "System": [
        ("Computer Name", ["PC-001", "WS-LAB-42", "HC-C-004CE", "SRV-PROD-01"]),
        ("Domain", ["APAC\\CORP", "EMEA\\OFFICE", "WORKGROUP", "corp.local"]),
        ("OS Version", ["Windows 11 23H2", "Windows 10 22H2", "Windows Server 2022"]),
        ("Architecture", ["64-bit", "x86_64", "ARM64"]),
        ("Processor", ["Intel i7-12800H", "AMD Ryzen 7 5800X", "Intel Xeon E5"]),
        ("RAM", ["16 GB", "32 GB", "8 GB", "64 GB"]),
        ("Disk Space", ["512 GB SSD", "1 TB HDD", "256 GB NVMe"]),
    ],
    "Network": [
        ("IP Address", ["192.168.1.100", "10.0.0.42", "172.16.0.15"]),
        ("MAC Address", ["AA:BB:CC:DD:EE:FF", "00:1A:2B:3C:4D:5E"]),
        ("Subnet Mask", ["255.255.255.0", "255.255.0.0"]),
        ("Gateway", ["192.168.1.1", "10.0.0.1"]),
        ("DNS Server", ["8.8.8.8", "1.1.1.1", "192.168.1.1"]),
        ("DHCP", ["Enabled", "Disabled"]),
        ("VPN Status", ["Connected", "Disconnected", "Not Configured"]),
    ],
    "Security": [
        ("Protection Level", ["Trusted", "Untrusted (2311)", "Standard"]),
        ("Admin Rights", ["Active", "Disabled", "Temporary"]),
        ("Firewall", ["Enabled", "Disabled"]),
        ("Antivirus", ["Up to date", "Outdated", "Not installed"]),
        ("Encryption", ["BitLocker On", "BitLocker Off"]),
        ("Password Expires", ["139 Days", "30 Days", "Expired", "Never"]),
        ("Last Login", ["2026-03-29 08:15", "2026-03-28 17:30"]),
    ],
    "Software": [
        ("Version", ["3.2.1", "1.0.0-beta", "22.04 LTS", "5.4.3.2"]),
        ("License", ["Enterprise", "Professional", "Community", "Trial"]),
        ("Update Status", ["Up to date", "Update available", "Checking..."]),
        ("Last Updated", ["2026-03-15", "2026-01-20", "Never"]),
        ("Auto Update", ["Enabled", "Disabled"]),
        ("Install Date", ["2025-06-15", "2024-11-01"]),
    ],
}


class InfoPanelTemplate(UITemplate):
    name = "info_panel"

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        img = self.create_canvas()
        t = self.theme

        # Header bar
        bar_h = self.s(42)
        draw_container(img, self.next_id(), 0, 0, self.width, bar_h, bg_color=t.primary)
        title = self.pick(APP_TITLES)
        elem = draw_text_label(img, self.next_id(), self.s(15), self.s(11), title,
                               font_size=self.s(16), color=(255, 255, 255), bold=True)
        self.elements.append(elem)

        # Tab buttons or action buttons in header
        rx = self.width - self.s(15)
        for label in self.pick_n(["Refresh", "Export", "Details", "Help"], self.rand_int(1, 3)):
            bw = len(label) * self.s(8) + self.s(18)
            rx -= bw
            elem = draw_button(img, self.next_id(), rx, self.s(6), bw, self.s(28), label,
                               bg_color=(255, 255, 255), text_color=t.primary,
                               font_size=self.s(12))
            self.elements.append(elem)
            rx -= self.s(8)

        # Content area - label:value pairs
        pad = self.s(20)
        y = bar_h + self.s(10)

        # Pick 2-4 sections
        section_names = list(INFO_SECTIONS.keys())
        num_sections = self.rand_int(2, min(4, len(section_names)))
        selected_sections = self.pick_n(section_names, num_sections)

        label_w = self.s(160)
        value_x = pad + label_w + self.s(15)

        for section_name in selected_sections:
            if y > self.height - self.s(80):
                break

            # Section header
            elem = draw_text_label(img, self.next_id(), pad, y, section_name,
                                   font_size=self.s(15), color=t.text_primary, bold=True)
            self.elements.append(elem)
            y += self.s(24)

            elem = draw_separator(img, self.next_id(), pad, y,
                                  self.width - 2 * pad, color=t.border)
            self.elements.append(elem)
            y += self.s(8)

            # Label-value rows
            items = INFO_SECTIONS[section_name]
            num_items = self.rand_int(3, min(7, len(items)))
            selected_items = self.pick_n(items, num_items)

            for label_text, values in selected_items:
                if y > self.height - self.s(40):
                    break

                value = self.pick(values)

                # Row background (alternating)
                row_h = self.s(22)

                # Label (left, gray)
                elem = draw_text_label(img, self.next_id(), pad + self.s(8), y,
                                       label_text, font_size=self.s(13),
                                       color=t.text_secondary)
                self.elements.append(elem)

                # Value (right, dark)
                # Color-code some values
                val_color = t.text_primary
                if value in ("Enabled", "Active", "Connected", "Up to date", "Trusted"):
                    val_color = (46, 125, 50)  # green
                elif value in ("Disabled", "Disconnected", "Expired", "Not installed"):
                    val_color = (198, 40, 40)  # red
                elif "Untrusted" in value or "Outdated" in value:
                    val_color = (230, 81, 0)  # orange

                elem = draw_text_label(img, self.next_id(), value_x, y,
                                       value, font_size=self.s(13), color=val_color)
                self.elements.append(elem)

                y += self.s(26)

            y += self.s(12)

        # Bottom action buttons
        by = self.height - self.s(45)
        bx = pad
        for label in self.pick_n(["Check Now", "Apply", "Save", "Close", "Reset"], self.rand_int(2, 4)):
            bw = len(label) * self.s(8) + self.s(24)
            is_primary = bx == pad  # First button is primary
            elem = draw_button(img, self.next_id(), bx, by, bw, self.s(32), label,
                               bg_color=t.primary if is_primary else t.surface,
                               text_color=(255, 255, 255) if is_primary else t.text_primary,
                               border_color=None if is_primary else t.border,
                               font_size=self.s(13))
            self.elements.append(elem)
            bx += bw + self.s(10)

        return img, self.elements
