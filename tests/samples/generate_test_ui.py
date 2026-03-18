"""
Generate synthetic UI screenshots for testing the CV pipeline.

This creates realistic-looking UI mockups with known element positions,
useful for validating the detection pipeline.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple


def draw_button(
    img: np.ndarray,
    x: int, y: int, w: int, h: int,
    text: str,
    bg_color: Tuple[int, int, int] = (66, 133, 244),
    text_color: Tuple[int, int, int] = (255, 255, 255),
    radius: int = 5
) -> Dict:
    """Draw a button with rounded corners."""
    # Draw rounded rectangle (simplified as regular rect)
    cv2.rectangle(img, (x, y), (x + w, y + h), bg_color, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), (50, 50, 50), 1)

    # Draw text centered
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness = 1
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    text_x = x + (w - text_size[0]) // 2
    text_y = y + (h + text_size[1]) // 2

    cv2.putText(img, text, (text_x, text_y), font, font_scale, text_color, thickness)

    return {"type": "button", "bounds": [x, y, x + w, y + h], "text": text}


def draw_input_field(
    img: np.ndarray,
    x: int, y: int, w: int, h: int,
    placeholder: str = "",
    value: str = ""
) -> Dict:
    """Draw an input field."""
    # White background
    cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)
    # Border
    cv2.rectangle(img, (x, y), (x + w, y + h), (200, 200, 200), 1)

    # Text
    font = cv2.FONT_HERSHEY_SIMPLEX
    display_text = value if value else placeholder
    text_color = (50, 50, 50) if value else (180, 180, 180)

    cv2.putText(img, display_text, (x + 10, y + h - 10), font, 0.45, text_color, 1)

    return {"type": "input_field", "bounds": [x, y, x + w, y + h], "text": placeholder}


def draw_text_label(
    img: np.ndarray,
    x: int, y: int,
    text: str,
    font_scale: float = 0.5,
    color: Tuple[int, int, int] = (50, 50, 50)
) -> Dict:
    """Draw a text label."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 1
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]

    cv2.putText(img, text, (x, y), font, font_scale, color, thickness)

    return {"type": "text", "bounds": [x, y - text_size[1], x + text_size[0], y], "text": text}


def draw_checkbox(
    img: np.ndarray,
    x: int, y: int,
    size: int = 20,
    checked: bool = False,
    label: str = ""
) -> Dict:
    """Draw a checkbox."""
    # Box
    cv2.rectangle(img, (x, y), (x + size, y + size), (200, 200, 200), 1)

    if checked:
        # Checkmark
        cv2.line(img, (x + 4, y + size // 2), (x + size // 2, y + size - 4), (66, 133, 244), 2)
        cv2.line(img, (x + size // 2, y + size - 4), (x + size - 4, y + 4), (66, 133, 244), 2)

    # Label
    if label:
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, label, (x + size + 8, y + size - 4), font, 0.45, (50, 50, 50), 1)

    return {"type": "checkbox", "bounds": [x, y, x + size, y + size], "text": label}


def draw_icon(
    img: np.ndarray,
    x: int, y: int,
    size: int = 24,
    icon_type: str = "menu"
) -> Dict:
    """Draw a simple icon."""
    if icon_type == "menu":
        # Hamburger menu
        for i in range(3):
            cv2.line(img, (x + 4, y + 6 + i * 6), (x + size - 4, y + 6 + i * 6), (100, 100, 100), 2)
    elif icon_type == "search":
        # Search icon
        cv2.circle(img, (x + size // 2 - 2, y + size // 2 - 2), 6, (100, 100, 100), 2)
        cv2.line(img, (x + size // 2 + 2, y + size // 2 + 2), (x + size - 4, y + size - 4), (100, 100, 100), 2)
    elif icon_type == "close":
        # X icon
        cv2.line(img, (x + 4, y + 4), (x + size - 4, y + size - 4), (100, 100, 100), 2)
        cv2.line(img, (x + size - 4, y + 4), (x + 4, y + size - 4), (100, 100, 100), 2)

    return {"type": "icon", "bounds": [x, y, x + size, y + size], "text": icon_type}


def draw_card(
    img: np.ndarray,
    x: int, y: int, w: int, h: int
) -> Dict:
    """Draw a card container with shadow."""
    # Shadow
    cv2.rectangle(img, (x + 3, y + 3), (x + w + 3, y + h + 3), (220, 220, 220), -1)
    # Card
    cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), (230, 230, 230), 1)

    return {"type": "container", "bounds": [x, y, x + w, y + h], "text": ""}


def generate_login_screen(width: int = 400, height: int = 600) -> Tuple[np.ndarray, List[Dict]]:
    """Generate a login screen mockup."""
    # Create white background
    img = np.ones((height, width, 3), dtype=np.uint8) * 245

    elements = []

    # Header
    cv2.rectangle(img, (0, 0), (width, 60), (66, 133, 244), -1)
    elements.append(draw_text_label(img, 20, 38, "Login", 0.8, (255, 255, 255)))
    elements.append(draw_icon(img, width - 40, 18, 24, "close"))

    # Logo/Title area
    elements.append(draw_text_label(img, width // 2 - 60, 120, "Welcome Back", 0.7, (50, 50, 50)))
    elements.append(draw_text_label(img, width // 2 - 80, 150, "Sign in to continue", 0.45, (150, 150, 150)))

    # Form card
    card_x, card_y = 30, 180
    card_w, card_h = width - 60, 320
    elements.append(draw_card(img, card_x, card_y, card_w, card_h))

    # Email field
    elements.append(draw_text_label(img, card_x + 20, card_y + 40, "Email", 0.45, (100, 100, 100)))
    elements.append(draw_input_field(img, card_x + 20, card_y + 50, card_w - 40, 40, "Enter your email"))

    # Password field
    elements.append(draw_text_label(img, card_x + 20, card_y + 120, "Password", 0.45, (100, 100, 100)))
    elements.append(draw_input_field(img, card_x + 20, card_y + 130, card_w - 40, 40, "Enter password"))

    # Remember me checkbox
    elements.append(draw_checkbox(img, card_x + 20, card_y + 190, 18, True, "Remember me"))

    # Login button
    elements.append(draw_button(img, card_x + 20, card_y + 230, card_w - 40, 45, "Sign In"))

    # Forgot password link
    elements.append(draw_text_label(img, card_x + 80, card_y + 300, "Forgot Password?", 0.4, (66, 133, 244)))

    # Sign up text
    elements.append(draw_text_label(img, width // 2 - 80, height - 40, "Don't have an account? Sign Up", 0.4, (100, 100, 100)))

    return img, elements


def generate_dashboard_screen(width: int = 800, height: int = 600) -> Tuple[np.ndarray, List[Dict]]:
    """Generate a dashboard screen mockup."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 250

    elements = []

    # Top navbar
    cv2.rectangle(img, (0, 0), (width, 50), (255, 255, 255), -1)
    cv2.line(img, (0, 50), (width, 50), (230, 230, 230), 1)

    elements.append(draw_icon(img, 15, 13, 24, "menu"))
    elements.append(draw_text_label(img, 50, 32, "Dashboard", 0.6, (50, 50, 50)))
    elements.append(draw_icon(img, width - 50, 13, 24, "search"))

    # Sidebar
    cv2.rectangle(img, (0, 50), (180, height), (40, 44, 52), -1)
    sidebar_items = ["Home", "Analytics", "Reports", "Settings", "Help"]
    for i, item in enumerate(sidebar_items):
        y = 80 + i * 45
        if i == 0:
            cv2.rectangle(img, (0, y - 10), (180, y + 25), (66, 133, 244), -1)
        elements.append(draw_text_label(img, 20, y + 10, item, 0.45, (200, 200, 200)))

    # Main content area
    content_x = 200

    # Stats cards
    card_width = 170
    for i in range(3):
        x = content_x + 20 + i * (card_width + 20)
        elements.append(draw_card(img, x, 70, card_width, 100))
        elements.append(draw_text_label(img, x + 15, 100, ["Users", "Sales", "Revenue"][i], 0.4, (150, 150, 150)))
        elements.append(draw_text_label(img, x + 15, 130, ["1,234", "$5,678", "$12,345"][i], 0.7, (50, 50, 50)))

    # Large card
    elements.append(draw_card(img, content_x + 20, 190, width - content_x - 40, 200))
    elements.append(draw_text_label(img, content_x + 40, 220, "Recent Activity", 0.5, (50, 50, 50)))

    # Table-like content
    for i in range(4):
        y = 250 + i * 30
        elements.append(draw_text_label(img, content_x + 40, y, f"Activity item {i + 1}", 0.4, (100, 100, 100)))

    # Action buttons
    elements.append(draw_button(img, content_x + 20, 420, 120, 35, "Add New", (76, 175, 80)))
    elements.append(draw_button(img, content_x + 160, 420, 120, 35, "Export", (255, 255, 255), (50, 50, 50)))

    return img, elements


def save_test_images(output_dir: str = "tests/samples"):
    """Generate and save test images."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate login screen
    login_img, login_elements = generate_login_screen()
    cv2.imwrite(str(output_path / "login_screen.png"), login_img)

    # Save ground truth
    import json
    with open(output_path / "login_screen_gt.json", "w") as f:
        json.dump({"elements": login_elements}, f, indent=2)

    print(f"Generated: login_screen.png ({len(login_elements)} elements)")

    # Generate dashboard
    dashboard_img, dashboard_elements = generate_dashboard_screen()
    cv2.imwrite(str(output_path / "dashboard_screen.png"), dashboard_img)

    with open(output_path / "dashboard_screen_gt.json", "w") as f:
        json.dump({"elements": dashboard_elements}, f, indent=2)

    print(f"Generated: dashboard_screen.png ({len(dashboard_elements)} elements)")

    return output_path


if __name__ == "__main__":
    output_dir = save_test_images()
    print(f"\nTest images saved to: {output_dir}")
