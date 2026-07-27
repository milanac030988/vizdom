"""
LLM-based UI Designer.

Asks an LLM (via Ollama) to describe a UI layout as JSON,
then the generator renders it into a screenshot with ground truth.
"""

import json
import re
from typing import Dict, List, Optional


# Supported element types that the generator can render
SUPPORTED_TYPES = [
    "button", "input_field", "text", "checkbox", "toggle",
    "icon", "separator", "container", "dropdown",
]

DESIGN_PROMPT = """You are a UI designer. Design a {app_type} application screen.

Output a JSON object describing the UI layout. The JSON must have:
- "title": app title string
- "theme": "light" or "dark"
- "elements": array of UI elements

Each element must have:
- "type": one of {types}
- "text": display text (required for button, text, input_field, checkbox, dropdown)
- "x": x position (0-{max_x})
- "y": y position (0-{max_y})
- "w": width in pixels
- "h": height in pixels

Layout rules:
- Canvas is {width}x{height} pixels
- Leave 10-20px margins
- Group related elements vertically
- Buttons: typical size 80-150w x 30-36h
- Input fields: typical 200-300w x 28-32h
- Text labels: h=16-20, w varies by text length
- Use containers (type=container) to group sections
- Place a title at the top

Design a realistic {app_type} with 15-30 elements.

Output ONLY valid JSON, no other text:"""


class LLMDesigner:
    """Generate UI layout descriptions using an LLM."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        temperature: float = 0.8,
        timeout: int = 120,
    ):
        self.host = host
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def design(
        self,
        app_type: str = "settings panel",
        width: int = 800,
        height: int = 600,
    ) -> Optional[Dict]:
        """
        Ask LLM to design a UI layout.

        Args:
            app_type: Description of the app (e.g., "login form", "email client",
                      "file manager", "music player", "chat application")
            width: Canvas width
            height: Canvas height

        Returns:
            Parsed JSON layout dict, or None if failed
        """
        prompt = DESIGN_PROMPT.format(
            app_type=app_type,
            types=", ".join(SUPPORTED_TYPES),
            width=width,
            height=height,
            max_x=width - 20,
            max_y=height - 20,
        )

        try:
            response = self._call_ollama(prompt)
            layout = self._parse_layout(response)

            if layout and self._validate_layout(layout, width, height):
                return layout
            else:
                print(f"  LLM designer: invalid layout, retrying...")
                # Retry once with stricter prompt
                response = self._call_ollama(prompt + "\nRemember: output ONLY valid JSON.")
                layout = self._parse_layout(response)
                if layout and self._validate_layout(layout, width, height):
                    return layout

        except Exception as e:
            print(f"  LLM designer failed: {e}")

        return None

    def design_batch(
        self,
        app_types: List[str],
        width: int = 800,
        height: int = 600,
    ) -> List[Dict]:
        """Design multiple UI layouts."""
        results = []
        for app_type in app_types:
            print(f"  Designing: {app_type}...")
            layout = self.design(app_type, width, height)
            if layout:
                results.append(layout)
                print(f"    -> {len(layout.get('elements', []))} elements")
            else:
                print(f"    -> FAILED")
        return results

    def _call_ollama(self, prompt: str) -> str:
        import requests
        response = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": 2048,
                },
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Ollama error: {response.status_code}")
        return response.json()["response"]

    def _parse_layout(self, response: str) -> Optional[Dict]:
        """Parse LLM response into layout dict."""
        response = response.strip()

        # Strip markdown
        if "```" in response:
            match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
            if match:
                response = match.group(1).strip()

        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON object
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _validate_layout(self, layout: Dict, width: int, height: int) -> bool:
        """Validate that the layout is usable."""
        if not isinstance(layout, dict):
            return False

        elements = layout.get("elements", [])
        if not elements or len(elements) < 3:
            return False

        valid_count = 0
        for elem in elements:
            if not isinstance(elem, dict):
                continue
            etype = elem.get("type", "")
            if etype not in SUPPORTED_TYPES:
                continue
            # Check bounds are reasonable
            x = elem.get("x", -1)
            y = elem.get("y", -1)
            w = elem.get("w", 0)
            h = elem.get("h", 0)
            if x >= 0 and y >= 0 and w > 0 and h > 0:
                valid_count += 1

        return valid_count >= 3


# Common app types for diverse dataset generation
APP_TYPES = [
    "login form",
    "user registration form",
    "settings panel with toggles and dropdowns",
    "email inbox with message list",
    "file manager with folder tree and file list",
    "music player with playlist and controls",
    "chat application with message area and contacts",
    "calendar with event list",
    "dashboard with statistics cards and charts",
    "shopping cart with product list and checkout",
    "photo gallery with thumbnails",
    "text editor with toolbar and formatting options",
    "task manager with to-do list and filters",
    "contact list with search and details panel",
    "system monitor with CPU, memory, and disk stats",
    "database browser with table view and query editor",
    "network configuration panel with IP settings",
    "printer settings dialog",
    "video player with playlist and controls",
    "password manager with entry list",
    "notification center with message cards",
    "package manager with install and update buttons",
    "terminal emulator with command history",
    "device manager with tree view of hardware",
    "form builder with drag and drop elements",
]
