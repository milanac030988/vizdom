"""
JSON Schema for Visual DOM output.

Defines the UIAutomator-like schema for automation consumption.
"""

from typing import Any, Dict

DOM_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Visual DOM Schema",
    "description": "UIAutomator-like DOM JSON generated from screenshots",
    "type": "object",
    "required": ["version", "hierarchy"],
    "properties": {
        "version": {
            "type": "string",
            "description": "Schema version"
        },
        "elements": {
            "type": "array",
            "description": "Raw detected elements (for debugging)",
            "items": {
                "$ref": "#/definitions/element"
            }
        },
        "hierarchy": {
            "$ref": "#/definitions/node",
            "description": "DOM tree for automation"
        }
    },
    "definitions": {
        "bounds": {
            "type": "array",
            "description": "Bounding box [x1, y1, x2, y2]",
            "items": {"type": "integer"},
            "minItems": 4,
            "maxItems": 4
        },
        "element": {
            "type": "object",
            "required": ["id", "bounds", "visual_type", "confidence"],
            "properties": {
                "id": {"type": "string"},
                "bounds": {"$ref": "#/definitions/bounds"},
                "visual_type": {
                    "type": "string",
                    "enum": ["button", "icon", "input_field", "checkbox",
                             "container", "image", "text", "unknown"]
                },
                "ocr_text": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            }
        },
        "node": {
            "type": "object",
            "required": ["id", "bounds", "role"],
            "properties": {
                "id": {"type": "string"},
                "bounds": {"$ref": "#/definitions/bounds"},
                "role": {
                    "type": "string",
                    "description": "UI role (Button, EditText, TextView, etc.)"
                },
                "text": {"type": "string"},
                "hint": {"type": "string"},
                "clickable": {"type": "boolean", "default": False},
                "editable": {"type": "boolean", "default": False},
                "scrollable": {"type": "boolean", "default": False},
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/node"}
                }
            }
        }
    }
}


def validate_dom(dom: Dict[str, Any]) -> bool:
    """
    Validate DOM JSON against schema.

    Args:
        dom: DOM dictionary to validate

    Returns:
        True if valid

    Raises:
        jsonschema.ValidationError if invalid
    """
    try:
        import jsonschema
        jsonschema.validate(dom, DOM_SCHEMA)
        return True
    except ImportError:
        # Fallback: basic validation
        if "version" not in dom or "hierarchy" not in dom:
            raise ValueError("DOM must have 'version' and 'hierarchy' keys")
        return True
