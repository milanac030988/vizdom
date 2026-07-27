"""Color themes for synthetic UI generation."""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class Theme:
    name: str
    background: Tuple[int, int, int]
    surface: Tuple[int, int, int]
    primary: Tuple[int, int, int]
    text_primary: Tuple[int, int, int]
    text_secondary: Tuple[int, int, int]
    border: Tuple[int, int, int]
    input_bg: Tuple[int, int, int]
    error: Tuple[int, int, int]


THEMES = {
    "light": Theme(
        name="light",
        background=(245, 245, 245),
        surface=(255, 255, 255),
        primary=(66, 133, 244),
        text_primary=(33, 33, 33),
        text_secondary=(117, 117, 117),
        border=(224, 224, 224),
        input_bg=(255, 255, 255),
        error=(211, 47, 47),
    ),
    "dark": Theme(
        name="dark",
        background=(48, 48, 48),
        surface=(66, 66, 66),
        primary=(100, 181, 246),
        text_primary=(238, 238, 238),
        text_secondary=(158, 158, 158),
        border=(97, 97, 97),
        input_bg=(55, 55, 55),
        error=(239, 83, 80),
    ),
    "blue": Theme(
        name="blue",
        background=(227, 242, 253),
        surface=(255, 255, 255),
        primary=(25, 118, 210),
        text_primary=(13, 71, 161),
        text_secondary=(100, 100, 100),
        border=(187, 222, 251),
        input_bg=(255, 255, 255),
        error=(198, 40, 40),
    ),
    "high_contrast": Theme(
        name="high_contrast",
        background=(0, 0, 0),
        surface=(30, 30, 30),
        primary=(255, 255, 0),
        text_primary=(255, 255, 255),
        text_secondary=(200, 200, 200),
        border=(255, 255, 255),
        input_bg=(0, 0, 0),
        error=(255, 0, 0),
    ),
    "green": Theme(
        name="green",
        background=(232, 245, 233),
        surface=(255, 255, 255),
        primary=(56, 142, 60),
        text_primary=(27, 94, 32),
        text_secondary=(100, 100, 100),
        border=(200, 230, 201),
        input_bg=(255, 255, 255),
        error=(198, 40, 40),
    ),
}
