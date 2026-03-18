"""
Locator parsing and element finding logic.

Supported locator strategies:
- By text: text="Login", hint="Email"
- By role/type: role=Button, role=EditText
- By structure: within="LoginForm", near text="Password"
- By relative position: right_of="Username", below="Title"
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import re


class LocatorStrategy(Enum):
    """Available locator strategies."""
    TEXT = "text"
    HINT = "hint"
    ROLE = "role"
    WITHIN = "within"
    NEAR = "near"
    RIGHT_OF = "right_of"
    LEFT_OF = "left_of"
    ABOVE = "above"
    BELOW = "below"


@dataclass
class Locator:
    """Parsed locator with strategy and value."""
    strategy: LocatorStrategy
    value: str
    modifiers: Dict[str, Any] = field(default_factory=dict)


class LocatorParser:
    """Parse locator strings into Locator objects."""

    PATTERN = re.compile(r'(\w+)=(?:"([^"]+)"|([^\s]+))')

    @classmethod
    def parse(cls, locator_string: str) -> List[Locator]:
        """
        Parse a locator string into list of Locator objects.

        Args:
            locator_string: Locator string like 'text="Login" role=Button'

        Returns:
            List of Locator objects

        Example:
            >>> LocatorParser.parse('text="Login"')
            [Locator(strategy=TEXT, value="Login")]
        """
        locators = []
        matches = cls.PATTERN.findall(locator_string)

        for match in matches:
            key = match[0].lower()
            value = match[1] if match[1] else match[2]

            try:
                strategy = LocatorStrategy(key)
                locators.append(Locator(strategy=strategy, value=value))
            except ValueError:
                # Unknown strategy - treat as modifier
                if locators:
                    locators[-1].modifiers[key] = value

        return locators


class ElementFinder:
    """Find elements in DOM using locators."""

    def __init__(self, dom: Dict[str, Any]):
        """
        Initialize finder with DOM.

        Args:
            dom: Visual DOM dictionary (compiled DOM format)
        """
        self.dom = dom
        self.elements = dom.get("elements", [])
        self._index = self._build_index()

    def _build_index(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Build searchable index from DOM elements."""
        index = {
            "by_text": {},
            "by_hint": {},
            "by_role": {},
            "by_type": {},
            "by_id": {}
        }

        for elem in self.elements:
            elem_id = elem.get("id", "")
            text = elem.get("text", "")
            hint = elem.get("hint", "")
            role = elem.get("role", "")
            vtype = elem.get("visual_type", "")

            # Index by ID (always unique)
            index["by_id"][elem_id] = [elem]

            # Index by text
            if text:
                text_lower = text.lower()
                if text_lower not in index["by_text"]:
                    index["by_text"][text_lower] = []
                index["by_text"][text_lower].append(elem)

            # Index by hint
            if hint:
                hint_lower = hint.lower()
                if hint_lower not in index["by_hint"]:
                    index["by_hint"][hint_lower] = []
                index["by_hint"][hint_lower].append(elem)

            # Index by role
            if role:
                role_lower = role.lower()
                if role_lower not in index["by_role"]:
                    index["by_role"][role_lower] = []
                index["by_role"][role_lower].append(elem)

            # Index by visual type
            if vtype:
                vtype_lower = vtype.lower()
                if vtype_lower not in index["by_type"]:
                    index["by_type"][vtype_lower] = []
                index["by_type"][vtype_lower].append(elem)

        return index

    def find(self, locators: List[Locator]) -> List[Dict]:
        """
        Find elements matching all locators.

        Args:
            locators: List of Locator objects

        Returns:
            List of matching element dictionaries
        """
        if not locators:
            return []

        # Start with all elements for first locator
        candidates = None

        for locator in locators:
            matches = self._find_by_strategy(locator)

            if candidates is None:
                candidates = set(id(e) for e in matches)
                candidates_list = matches
            else:
                # Intersect with previous matches
                match_ids = set(id(e) for e in matches)
                candidates = candidates & match_ids
                candidates_list = [e for e in candidates_list if id(e) in candidates]

        return candidates_list if candidates_list else []

    def _find_by_strategy(self, locator: Locator) -> List[Dict]:
        """Find elements using a single locator strategy."""
        value = locator.value.lower()

        if locator.strategy == LocatorStrategy.TEXT:
            # Exact or partial text match
            exact = self._index["by_text"].get(value, [])
            if exact:
                return exact
            # Partial match
            return [e for e in self.elements
                    if value in (e.get("text", "") or "").lower()]

        elif locator.strategy == LocatorStrategy.HINT:
            exact = self._index["by_hint"].get(value, [])
            if exact:
                return exact
            return [e for e in self.elements
                    if value in (e.get("hint", "") or "").lower()]

        elif locator.strategy == LocatorStrategy.ROLE:
            return self._index["by_role"].get(value, [])

        elif locator.strategy in (LocatorStrategy.WITHIN, LocatorStrategy.NEAR):
            # Find container element first
            container = self._find_container(value)
            if not container:
                return []
            return self._find_within_bounds(container.get("bounds", [0,0,0,0]))

        elif locator.strategy == LocatorStrategy.RIGHT_OF:
            ref_elem = self._find_reference(value)
            if not ref_elem:
                return []
            return self._find_relative(ref_elem, "right")

        elif locator.strategy == LocatorStrategy.LEFT_OF:
            ref_elem = self._find_reference(value)
            if not ref_elem:
                return []
            return self._find_relative(ref_elem, "left")

        elif locator.strategy == LocatorStrategy.ABOVE:
            ref_elem = self._find_reference(value)
            if not ref_elem:
                return []
            return self._find_relative(ref_elem, "above")

        elif locator.strategy == LocatorStrategy.BELOW:
            ref_elem = self._find_reference(value)
            if not ref_elem:
                return []
            return self._find_relative(ref_elem, "below")

        return []

    def _find_container(self, value: str) -> Optional[Dict]:
        """Find container element by text or ID."""
        # Try by ID first
        by_id = self._index["by_id"].get(value, [])
        if by_id:
            return by_id[0]
        # Try by text
        by_text = self._index["by_text"].get(value.lower(), [])
        if by_text:
            return by_text[0]
        return None

    def _find_reference(self, value: str) -> Optional[Dict]:
        """Find reference element for relative positioning."""
        return self._find_container(value)

    def _find_within_bounds(self, bounds: List[int]) -> List[Dict]:
        """Find elements within given bounds."""
        x1, y1, x2, y2 = bounds
        results = []
        for elem in self.elements:
            eb = elem.get("bounds", [0, 0, 0, 0])
            # Check if element center is within bounds
            cx = (eb[0] + eb[2]) / 2
            cy = (eb[1] + eb[3]) / 2
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                results.append(elem)
        return results

    def _find_relative(self, ref: Dict, direction: str) -> List[Dict]:
        """Find elements in relative position to reference."""
        rb = ref.get("bounds", [0, 0, 0, 0])
        ref_cx = (rb[0] + rb[2]) / 2
        ref_cy = (rb[1] + rb[3]) / 2

        results = []
        for elem in self.elements:
            if elem.get("id") == ref.get("id"):
                continue
            eb = elem.get("bounds", [0, 0, 0, 0])
            cx = (eb[0] + eb[2]) / 2
            cy = (eb[1] + eb[3]) / 2

            if direction == "right" and cx > rb[2]:
                results.append((abs(cy - ref_cy), elem))
            elif direction == "left" and cx < rb[0]:
                results.append((abs(cy - ref_cy), elem))
            elif direction == "below" and cy > rb[3]:
                results.append((abs(cx - ref_cx), elem))
            elif direction == "above" and cy < rb[1]:
                results.append((abs(cx - ref_cx), elem))

        # Sort by proximity and return elements
        results.sort(key=lambda x: x[0])
        return [e for _, e in results]

    def find_one(self, locators: List[Locator]) -> Optional[Dict]:
        """
        Find exactly one element matching locators.

        Args:
            locators: List of Locator objects

        Returns:
            Matching element or None

        Raises:
            ValueError if multiple elements match
        """
        matches = self.find(locators)
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise ValueError(f"Multiple elements match locator: {len(matches)} found")
        return matches[0]

    def find_by_locator_string(self, locator_string: str) -> List[Dict]:
        """
        Convenience method to find by locator string.

        Args:
            locator_string: Locator string like 'text="Login"'

        Returns:
            List of matching elements
        """
        locators = LocatorParser.parse(locator_string)
        return self.find(locators)
