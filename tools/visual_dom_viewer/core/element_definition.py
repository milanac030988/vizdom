"""
Element Definition - User-defined element naming and locator properties.

Allows users to:
- Name elements with custom identifiers (e.g., "Button_Number_4")
- Select which properties define the element (text, type, position, etc.)
- Export these definitions for use in Robot Framework tests
"""

from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json


class LocatorProperty(Enum):
    """Properties that can be used to locate an element."""
    TEXT = "text"
    TYPE = "type"
    BBOX = "bbox"
    CENTER = "center"
    INDEX = "index"
    PARENT_TEXT = "parent_text"
    CONFIDENCE = "confidence"
    # Custom properties from DOM
    CLASS = "class"
    RESOURCE_ID = "resource_id"
    CONTENT_DESC = "content_desc"


@dataclass
class ElementDefinition:
    """
    User-defined element with custom name and selected locator properties.

    Attributes:
        element_id: Original DOM element ID
        name: User-defined name (e.g., "Button_Number_4")
        selected_properties: Properties selected to define this element
        property_values: Actual values for the selected properties
        description: Optional description/notes
    """
    element_id: str
    name: str
    selected_properties: Set[str] = field(default_factory=set)
    property_values: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self):
        """Ensure selected_properties is a set."""
        if isinstance(self.selected_properties, list):
            self.selected_properties = set(self.selected_properties)

    def add_property(self, prop: str, value: Any) -> None:
        """Add a property to the locator definition."""
        self.selected_properties.add(prop)
        self.property_values[prop] = value

    def remove_property(self, prop: str) -> None:
        """Remove a property from the locator definition."""
        self.selected_properties.discard(prop)
        self.property_values.pop(prop, None)

    def toggle_property(self, prop: str, value: Any = None) -> bool:
        """Toggle a property. Returns True if now selected."""
        if prop in self.selected_properties:
            self.remove_property(prop)
            return False
        else:
            self.add_property(prop, value)
            return True

    def get_locator_dict(self) -> Dict[str, Any]:
        """Get dictionary of selected properties and their values."""
        return {
            prop: self.property_values.get(prop)
            for prop in self.selected_properties
            if prop in self.property_values
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'element_id': self.element_id,
            'name': self.name,
            'selected_properties': list(self.selected_properties),
            'property_values': self.property_values,
            'description': self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ElementDefinition':
        """Create from dictionary."""
        return cls(
            element_id=data['element_id'],
            name=data['name'],
            selected_properties=set(data.get('selected_properties', [])),
            property_values=data.get('property_values', {}),
            description=data.get('description', ''),
        )


class ElementDefinitionManager:
    """
    Manages collection of user-defined element definitions.

    Provides:
    - Add/remove/update definitions
    - Persistence (save/load)
    - Export to various formats
    """

    def __init__(self):
        self._definitions: Dict[str, ElementDefinition] = {}  # keyed by element_id
        self._listeners: List[callable] = []

    def add_listener(self, callback: callable) -> None:
        """Add change listener."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        """Notify listeners of changes."""
        for callback in self._listeners:
            try:
                callback(self._definitions)
            except Exception as e:
                print(f"Error in definition listener: {e}")

    def add_definition(self, definition: ElementDefinition) -> None:
        """Add or update an element definition."""
        self._definitions[definition.element_id] = definition
        self._notify()

    def remove_definition(self, element_id: str) -> Optional[ElementDefinition]:
        """Remove a definition by element ID."""
        definition = self._definitions.pop(element_id, None)
        if definition:
            self._notify()
        return definition

    def get_definition(self, element_id: str) -> Optional[ElementDefinition]:
        """Get definition for an element."""
        return self._definitions.get(element_id)

    def has_definition(self, element_id: str) -> bool:
        """Check if element has a definition."""
        return element_id in self._definitions

    def get_all_definitions(self) -> List[ElementDefinition]:
        """Get all definitions."""
        return list(self._definitions.values())

    def get_definition_count(self) -> int:
        """Get number of definitions."""
        return len(self._definitions)

    def clear(self) -> None:
        """Clear all definitions."""
        self._definitions.clear()
        self._notify()

    def update_definition(
        self,
        element_id: str,
        name: Optional[str] = None,
        selected_properties: Optional[Set[str]] = None,
        property_values: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None
    ) -> Optional[ElementDefinition]:
        """Update an existing definition."""
        definition = self._definitions.get(element_id)
        if not definition:
            return None

        if name is not None:
            definition.name = name
        if selected_properties is not None:
            definition.selected_properties = selected_properties
        if property_values is not None:
            definition.property_values = property_values
        if description is not None:
            definition.description = description

        self._notify()
        return definition

    def to_dict(self) -> Dict[str, Any]:
        """Convert all definitions to dictionary."""
        return {
            'definitions': [d.to_dict() for d in self._definitions.values()]
        }

    def save_to_file(self, filepath: str) -> bool:
        """Save definitions to JSON file."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving definitions: {e}")
            return False

    def load_from_file(self, filepath: str) -> bool:
        """Load definitions from JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._definitions.clear()
            for def_data in data.get('definitions', []):
                definition = ElementDefinition.from_dict(def_data)
                self._definitions[definition.element_id] = definition

            self._notify()
            return True
        except Exception as e:
            print(f"Error loading definitions: {e}")
            return False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ElementDefinitionManager':
        """Create manager from dictionary."""
        manager = cls()
        for def_data in data.get('definitions', []):
            definition = ElementDefinition.from_dict(def_data)
            manager._definitions[definition.element_id] = definition
        return manager
