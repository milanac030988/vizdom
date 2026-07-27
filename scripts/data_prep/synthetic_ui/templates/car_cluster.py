"""Car infotainment cluster template.

Generates instrument cluster and infotainment center UIs:
- Digital speedometer / tachometer
- Navigation hints
- Media player
- Climate controls
- Vehicle status indicators
- Phone / Bluetooth
"""

import cv2
import numpy as np
from typing import List, Tuple
import math

from .base import UITemplate
from ..primitives import (
    Element, draw_button, draw_text_label, draw_container,
    draw_separator, draw_icon,
)


class CarClusterTemplate(UITemplate):
    name = "car_cluster"

    # Cluster-specific color palettes
    CLUSTER_THEMES = [
        {"bg": (20, 20, 25), "accent": (0, 180, 255), "text": (220, 220, 220), "warn": (0, 80, 255), "name": "blue_sport"},
        {"bg": (15, 15, 20), "accent": (0, 255, 200), "text": (200, 220, 200), "warn": (0, 180, 255), "name": "green_eco"},
        {"bg": (25, 15, 15), "accent": (60, 60, 255), "text": (220, 200, 200), "warn": (0, 0, 255), "name": "red_sport"},
        {"bg": (20, 20, 20), "accent": (200, 200, 200), "text": (230, 230, 230), "warn": (0, 165, 255), "name": "white_classic"},
        {"bg": (10, 10, 15), "accent": (0, 220, 255), "text": (180, 200, 220), "warn": (0, 100, 255), "name": "cyan_modern"},
    ]

    VARIANTS = ["cluster", "infotainment", "climate", "media"]

    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        variant = self.pick(self.VARIANTS)
        colors = self.pick(self.CLUSTER_THEMES)

        img = np.full((self.height, self.width, 3), colors["bg"], dtype=np.uint8)

        if variant == "cluster":
            self._draw_instrument_cluster(img, colors)
        elif variant == "infotainment":
            self._draw_infotainment(img, colors)
        elif variant == "climate":
            self._draw_climate_control(img, colors)
        elif variant == "media":
            self._draw_media_player(img, colors)

        return img, self.elements

    def _draw_instrument_cluster(self, img, colors):
        """Digital instrument cluster with speed, RPM, and info."""
        cx = self.width // 2
        cy = self.height // 2
        accent = colors["accent"]
        text_c = colors["text"]

        # Speed display (center)
        speed = self.rand_int(0, 220)
        self._draw_gauge_arc(img, cx, cy, self.s(180), accent, speed / 260)
        elem = draw_text_label(img, self.next_id(), cx - self.s(50), cy - self.s(30),
                               str(speed), font_size=self.s(64), color=accent, bold=True)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), cx - self.s(28), cy + self.s(35),
                               "km/h", font_size=self.s(16), color=text_c)
        self.elements.append(elem)

        # RPM gauge (left)
        rpm = self.rand_int(800, 6500)
        rpm_x = self.s(180)
        self._draw_gauge_arc(img, rpm_x, cy, self.s(100), accent, rpm / 8000)
        elem = draw_text_label(img, self.next_id(), rpm_x - self.s(30), cy - self.s(15),
                               f"{rpm/1000:.1f}", font_size=self.s(32), color=accent, bold=True)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), rpm_x - self.s(22), cy + self.s(20),
                               "x1000 rpm", font_size=self.s(11), color=text_c)
        self.elements.append(elem)

        # Fuel gauge (right)
        fuel = self.rand_int(10, 100)
        fuel_x = self.width - self.s(180)
        self._draw_gauge_arc(img, fuel_x, cy, self.s(100), accent, fuel / 100)
        elem = draw_text_label(img, self.next_id(), fuel_x - self.s(20), cy - self.s(15),
                               f"{fuel}%", font_size=self.s(28), color=accent, bold=True)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), fuel_x - self.s(14), cy + self.s(20),
                               "FUEL", font_size=self.s(12), color=text_c)
        self.elements.append(elem)

        # Bottom info bar
        by = self.height - self.s(70)
        info_items = [
            ("ODO", f"{self.rand_int(10000, 99999)} km"),
            ("TRIP", f"{self.rand_int(10, 999)}.{self.rand_int(0,9)} km"),
            ("TEMP", f"{self.rand_int(-5, 38)}°C"),
            ("TIME", f"{self.rand_int(0,23):02d}:{self.rand_int(0,59):02d}"),
        ]
        item_w = self.width // len(info_items)
        for i, (label, value) in enumerate(info_items):
            ix = i * item_w + item_w // 2 - self.s(30)
            elem = draw_text_label(img, self.next_id(), ix, by, label,
                                   font_size=self.s(11), color=colors["text"])
            self.elements.append(elem)
            elem = draw_text_label(img, self.next_id(), ix, by + self.s(18), value,
                                   font_size=self.s(14), color=accent)
            self.elements.append(elem)

        # Warning indicators (top)
        ty = self.s(15)
        indicators = self.pick_n(
            ["ABS", "ESP", "EPC", "CHECK", "OIL", "BATT", "BRAKE", "AIRBAG",
             "TPMS", "SRS", "DPF", "4WD", "ECO", "SPORT"],
            self.rand_int(3, 6)
        )
        ix = cx - len(indicators) * self.s(30) // 2
        for ind in indicators:
            active = self.rand_bool(0.3)
            c = colors["warn"] if active else (60, 60, 60)
            elem = draw_text_label(img, self.next_id(), ix, ty, ind,
                                   font_size=self.s(10), color=c)
            self.elements.append(elem)
            ix += self.s(55)

        # Gear indicator
        gear = self.pick(["P", "R", "N", "D", "D1", "D2", "D3", "S", "M"])
        elem = draw_text_label(img, self.next_id(), cx - self.s(10), cy + self.s(70),
                               gear, font_size=self.s(28), color=accent, bold=True)
        self.elements.append(elem)

    def _draw_infotainment(self, img, colors):
        """Infotainment center screen with nav, media, phone."""
        accent = colors["accent"]
        text_c = colors["text"]
        bg = colors["bg"]
        pad = self.s(15)

        # Status bar top
        draw_container(img, self.next_id(), 0, 0, self.width, self.s(35),
                       bg_color=_lighter(bg, 20))
        status_items = [
            f"{self.rand_int(0,23):02d}:{self.rand_int(0,59):02d}",
            f"{self.rand_int(-5,38)}°C",
            self.pick(["LTE", "5G", "WiFi"]),
            f"BT: {self.pick(['Connected', 'Off'])}",
        ]
        sx = pad
        for item in status_items:
            elem = draw_text_label(img, self.next_id(), sx, self.s(8), item,
                                   font_size=self.s(12), color=text_c)
            self.elements.append(elem)
            sx += self.s(120)

        # Main content area
        content_y = self.s(40)

        # Navigation card (left half)
        nav_w = self.width // 2 - self.s(10)
        nav_h = self.height - self.s(120)
        draw_container(img, self.next_id(), pad, content_y, nav_w, nav_h,
                       bg_color=_lighter(bg, 15), border_color=_lighter(bg, 40))

        elem = draw_text_label(img, self.next_id(), pad + self.s(12), content_y + self.s(10),
                               "Navigation", font_size=self.s(16), color=accent, bold=True)
        self.elements.append(elem)

        # Fake map area
        map_y = content_y + self.s(35)
        map_h = nav_h - self.s(80)
        cv2.rectangle(img, (pad + self.s(8), map_y),
                      (pad + nav_w - self.s(8), map_y + map_h),
                      _lighter(bg, 25), -1)
        # Road lines on map
        for _ in range(self.rand_int(3, 6)):
            x1 = self.rand_int(pad + self.s(20), pad + nav_w - self.s(20))
            y1 = self.rand_int(map_y + self.s(10), map_y + map_h - self.s(10))
            x2 = self.rand_int(pad + self.s(20), pad + nav_w - self.s(20))
            y2 = self.rand_int(map_y + self.s(10), map_y + map_h - self.s(10))
            cv2.line(img, (x1, y1), (x2, y2), _lighter(bg, 40), self.s(2), cv2.LINE_AA)

        # Navigation instruction
        nav_text = self.pick([
            "Turn right in 200m", "Continue straight 1.2km",
            "Take exit 5A", "Destination on left", "Rerouting...",
            "Arrive in 15 min", "Turn left at roundabout",
        ])
        elem = draw_text_label(img, self.next_id(), pad + self.s(12),
                               map_y + map_h + self.s(10), nav_text,
                               font_size=self.s(14), color=text_c)
        self.elements.append(elem)

        # Right panel - media + phone
        rx = self.width // 2 + self.s(5)
        rw = self.width // 2 - pad - self.s(5)

        # Media card
        media_h = (nav_h - self.s(10)) // 2
        draw_container(img, self.next_id(), rx, content_y, rw, media_h,
                       bg_color=_lighter(bg, 15), border_color=_lighter(bg, 40))

        elem = draw_text_label(img, self.next_id(), rx + self.s(12), content_y + self.s(10),
                               "Now Playing", font_size=self.s(14), color=accent, bold=True)
        self.elements.append(elem)

        song = self.pick(["Bohemian Rhapsody", "Hotel California", "Stairway to Heaven",
                          "Sweet Child O'Mine", "Wonderwall", "Smells Like Teen Spirit"])
        artist = self.pick(["Queen", "Eagles", "Led Zeppelin", "Guns N' Roses",
                            "Oasis", "Nirvana", "Pink Floyd", "The Beatles"])
        elem = draw_text_label(img, self.next_id(), rx + self.s(12), content_y + self.s(35),
                               song, font_size=self.s(16), color=text_c, bold=True)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), rx + self.s(12), content_y + self.s(55),
                               artist, font_size=self.s(13), color=_lighter(text_c, -60))
        self.elements.append(elem)

        # Media controls
        ctrl_y = content_y + media_h - self.s(45)
        btn_w = self.s(50)
        btn_h = self.s(30)
        bx = rx + (rw - btn_w * 5) // 2
        for label in ["<<", "|<", "||", ">|", ">>"]:
            elem = draw_button(img, self.next_id(), bx, ctrl_y, btn_w, btn_h, label,
                               bg_color=_lighter(bg, 30), text_color=accent,
                               font_size=self.s(14))
            self.elements.append(elem)
            bx += btn_w + self.s(5)

        # Phone card (bottom right)
        phone_y = content_y + media_h + self.s(10)
        phone_h = nav_h - media_h - self.s(10)
        draw_container(img, self.next_id(), rx, phone_y, rw, phone_h,
                       bg_color=_lighter(bg, 15), border_color=_lighter(bg, 40))

        elem = draw_text_label(img, self.next_id(), rx + self.s(12), phone_y + self.s(10),
                               "Phone", font_size=self.s(14), color=accent, bold=True)
        self.elements.append(elem)

        contacts = self.pick_n(["John Doe", "Jane Smith", "Office", "Home",
                                "Mom", "Dad", "Service Center", "Emergency"],
                               self.rand_int(3, 5))
        cy = phone_y + self.s(35)
        for contact in contacts:
            if cy + self.s(22) > phone_y + phone_h:
                break
            elem = draw_text_label(img, self.next_id(), rx + self.s(20), cy, contact,
                                   font_size=self.s(13), color=text_c)
            self.elements.append(elem)
            cy += self.s(24)

        # Bottom button bar
        by = self.height - self.s(55)
        menu_items = self.pick_n(["NAV", "MEDIA", "PHONE", "RADIO", "APPS",
                                   "VEHICLE", "SETTINGS", "HOME"], self.rand_int(4, 7))
        btn_total = self.width - 2 * pad
        btn_each = btn_total // len(menu_items)
        for i, item in enumerate(menu_items):
            bx = pad + i * btn_each
            elem = draw_button(img, self.next_id(), bx, by, btn_each - self.s(4), self.s(38),
                               item, bg_color=_lighter(bg, 25), text_color=accent,
                               font_size=self.s(13))
            self.elements.append(elem)

    def _draw_climate_control(self, img, colors):
        """Climate control panel."""
        accent = colors["accent"]
        text_c = colors["text"]
        bg = colors["bg"]
        pad = self.s(20)
        cx = self.width // 2

        # Title
        elem = draw_text_label(img, self.next_id(), cx - self.s(80), self.s(20),
                               "Climate Control", font_size=self.s(22), color=accent, bold=True)
        self.elements.append(elem)

        # Driver side (left)
        driver_temp = self.rand_int(16, 28)
        elem = draw_text_label(img, self.next_id(), self.s(60), self.s(80),
                               "DRIVER", font_size=self.s(12), color=text_c)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), self.s(40), self.s(110),
                               f"{driver_temp}.0°", font_size=self.s(48), color=accent, bold=True)
        self.elements.append(elem)

        # Temp +/- buttons driver
        elem = draw_button(img, self.next_id(), self.s(40), self.s(170), self.s(50), self.s(40),
                           "-", bg_color=_lighter(bg, 30), text_color=accent, font_size=self.s(24))
        self.elements.append(elem)
        elem = draw_button(img, self.next_id(), self.s(100), self.s(170), self.s(50), self.s(40),
                           "+", bg_color=_lighter(bg, 30), text_color=accent, font_size=self.s(24))
        self.elements.append(elem)

        # Passenger side (right)
        pass_temp = self.rand_int(16, 28)
        px = self.width - self.s(180)
        elem = draw_text_label(img, self.next_id(), px + self.s(20), self.s(80),
                               "PASSENGER", font_size=self.s(12), color=text_c)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), px, self.s(110),
                               f"{pass_temp}.0°", font_size=self.s(48), color=accent, bold=True)
        self.elements.append(elem)

        elem = draw_button(img, self.next_id(), px, self.s(170), self.s(50), self.s(40),
                           "-", bg_color=_lighter(bg, 30), text_color=accent, font_size=self.s(24))
        self.elements.append(elem)
        elem = draw_button(img, self.next_id(), px + self.s(60), self.s(170), self.s(50), self.s(40),
                           "+", bg_color=_lighter(bg, 30), text_color=accent, font_size=self.s(24))
        self.elements.append(elem)

        # Center - SYNC indicator
        sync = self.rand_bool(0.5)
        elem = draw_button(img, self.next_id(), cx - self.s(35), self.s(130), self.s(70), self.s(30),
                           "SYNC" if sync else "DUAL",
                           bg_color=accent if sync else _lighter(bg, 30),
                           text_color=bg if sync else text_c,
                           font_size=self.s(13))
        self.elements.append(elem)

        # Fan speed
        fan_y = self.s(250)
        elem = draw_text_label(img, self.next_id(), cx - self.s(50), fan_y,
                               "Fan Speed", font_size=self.s(14), color=text_c)
        self.elements.append(elem)

        fan_speed = self.rand_int(0, 7)
        bar_y = fan_y + self.s(25)
        for i in range(8):
            bx = cx - self.s(120) + i * self.s(30)
            active = i <= fan_speed
            c = accent if active else _lighter(bg, 30)
            cv2.rectangle(img, (bx, bar_y), (bx + self.s(25), bar_y + self.s(20)), c, -1)
            elem_label = str(i) if i > 0 else "OFF"
            if i == fan_speed:
                draw_text_label(img, self.next_id(), bx + self.s(5), bar_y + self.s(3),
                                elem_label, font_size=self.s(10),
                                color=bg if active else text_c)

        # Bottom controls
        by = self.height - self.s(100)
        controls = self.pick_n(
            ["A/C", "AUTO", "REAR", "DEFROST", "RECIRC", "SEAT HTR", "SEAT COOL"],
            self.rand_int(4, 6)
        )
        btn_w = (self.width - 2 * pad) // len(controls)
        for i, ctrl in enumerate(controls):
            active = self.rand_bool(0.4)
            c = accent if active else _lighter(bg, 25)
            tc = bg if active else text_c
            elem = draw_button(img, self.next_id(), pad + i * btn_w, by,
                               btn_w - self.s(6), self.s(45), ctrl,
                               bg_color=c, text_color=tc, font_size=self.s(12))
            self.elements.append(elem)

        # Air direction buttons
        dir_y = self.s(340)
        directions = ["FACE", "FACE/FEET", "FEET", "FEET/DEF"]
        dir_w = self.s(100)
        dir_start = cx - len(directions) * dir_w // 2
        for i, d in enumerate(directions):
            active = self.rand_bool(0.25)
            elem = draw_button(img, self.next_id(), dir_start + i * dir_w, dir_y,
                               dir_w - self.s(4), self.s(30), d,
                               bg_color=accent if active else _lighter(bg, 25),
                               text_color=bg if active else text_c,
                               font_size=self.s(10))
            self.elements.append(elem)

    def _draw_media_player(self, img, colors):
        """Full-screen media player."""
        accent = colors["accent"]
        text_c = colors["text"]
        bg = colors["bg"]
        cx = self.width // 2

        # Album art area (large centered square)
        art_size = min(self.s(300), self.height - self.s(200))
        art_x = cx - art_size // 2
        art_y = self.s(40)
        # Gradient-ish album art
        for row in range(art_size):
            c1 = self.rand_int(40, 100)
            c2 = self.rand_int(40, 100)
            cv2.line(img, (art_x, art_y + row), (art_x + art_size, art_y + row),
                     (c1, c2, c1 + 30), 1)

        # Song info
        info_y = art_y + art_size + self.s(20)
        song = self.pick(["Bohemian Rhapsody", "Stairway to Heaven", "Hotel California",
                          "Comfortably Numb", "November Rain", "Dream On",
                          "Free Bird", "Wish You Were Here", "Back in Black"])
        artist = self.pick(["Queen", "Led Zeppelin", "Eagles", "Pink Floyd",
                            "Guns N' Roses", "Aerosmith", "Lynyrd Skynyrd", "AC/DC"])
        album = self.pick(["Greatest Hits", "The Wall", "Back in Black",
                           "Appetite for Destruction", "Dark Side of the Moon"])

        elem = draw_text_label(img, self.next_id(), cx - self.s(100), info_y,
                               song, font_size=self.s(22), color=text_c, bold=True)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), cx - self.s(60), info_y + self.s(28),
                               artist, font_size=self.s(16), color=_lighter(text_c, -60))
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), cx - self.s(50), info_y + self.s(50),
                               album, font_size=self.s(13), color=_lighter(text_c, -80))
        self.elements.append(elem)

        # Progress bar
        prog_y = info_y + self.s(75)
        prog_w = self.width - self.s(100)
        prog_x = self.s(50)
        cv2.rectangle(img, (prog_x, prog_y), (prog_x + prog_w, prog_y + self.s(4)),
                      _lighter(bg, 30), -1)
        progress = self.rng.random()
        cv2.rectangle(img, (prog_x, prog_y),
                      (prog_x + int(prog_w * progress), prog_y + self.s(4)),
                      accent, -1)

        # Time labels
        total_sec = self.rand_int(180, 420)
        current_sec = int(total_sec * progress)
        elem = draw_text_label(img, self.next_id(), prog_x, prog_y + self.s(8),
                               f"{current_sec//60}:{current_sec%60:02d}",
                               font_size=self.s(11), color=text_c)
        self.elements.append(elem)
        elem = draw_text_label(img, self.next_id(), prog_x + prog_w - self.s(35), prog_y + self.s(8),
                               f"{total_sec//60}:{total_sec%60:02d}",
                               font_size=self.s(11), color=text_c)
        self.elements.append(elem)

        # Playback controls
        ctrl_y = prog_y + self.s(35)
        btn_h = self.s(40)
        controls = [("SHUF", self.s(55)), ("<<", self.s(50)), ("||", self.s(60)),
                    (">>", self.s(50)), ("RPT", self.s(55))]
        total_btn_w = sum(w for _, w in controls) + self.s(10) * (len(controls) - 1)
        bx = cx - total_btn_w // 2

        for label, bw in controls:
            is_play = label == "||"
            elem = draw_button(img, self.next_id(), bx, ctrl_y, bw, btn_h, label,
                               bg_color=accent if is_play else _lighter(bg, 25),
                               text_color=bg if is_play else accent,
                               font_size=self.s(16 if is_play else 13))
            self.elements.append(elem)
            bx += bw + self.s(10)

        # Source buttons at bottom
        by = self.height - self.s(50)
        sources = self.pick_n(["FM", "AM", "USB", "BT", "AUX", "ONLINE", "DAB"], self.rand_int(4, 6))
        src_w = (self.width - self.s(40)) // len(sources)
        for i, src in enumerate(sources):
            active = i == 0
            elem = draw_button(img, self.next_id(), self.s(20) + i * src_w, by,
                               src_w - self.s(4), self.s(35), src,
                               bg_color=accent if active else _lighter(bg, 20),
                               text_color=bg if active else text_c,
                               font_size=self.s(12))
            self.elements.append(elem)

    def _draw_gauge_arc(self, img, cx, cy, radius, color, fill_ratio):
        """Draw a circular gauge arc."""
        start_angle = 135
        end_angle = 405
        filled_angle = start_angle + int((end_angle - start_angle) * min(fill_ratio, 1.0))

        # Background arc
        cv2.ellipse(img, (cx, cy), (radius, radius), 0, start_angle, end_angle,
                    (40, 40, 40), self.s(6), cv2.LINE_AA)
        # Filled arc
        if filled_angle > start_angle:
            cv2.ellipse(img, (cx, cy), (radius, radius), 0, start_angle, filled_angle,
                        color, self.s(6), cv2.LINE_AA)
        # Tick marks
        for i in range(0, 11):
            angle_rad = math.radians(start_angle + i * (end_angle - start_angle) / 10)
            inner_r = radius - self.s(12)
            outer_r = radius + self.s(4)
            x1 = int(cx + inner_r * math.cos(angle_rad))
            y1 = int(cy + inner_r * math.sin(angle_rad))
            x2 = int(cx + outer_r * math.cos(angle_rad))
            y2 = int(cy + outer_r * math.sin(angle_rad))
            cv2.line(img, (x1, y1), (x2, y2), (80, 80, 80), self.s(2), cv2.LINE_AA)


def _lighter(color, amount=20):
    """Lighten or darken a BGR color."""
    return tuple(max(0, min(255, c + amount)) for c in color)
