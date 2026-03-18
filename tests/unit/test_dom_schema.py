"""Unit tests for DOM schema validation."""

import pytest
from visual_dom.schema.dom_schema import DOM_SCHEMA, validate_dom


class TestDOMSchema:
    """Tests for DOM schema validation."""

    def test_valid_minimal_dom(self):
        """Test validation of minimal valid DOM."""
        dom = {
            "version": "1.0",
            "hierarchy": {
                "id": "root",
                "bounds": [0, 0, 1080, 1920],
                "role": "FrameLayout"
            }
        }

        assert validate_dom(dom) is True

    def test_valid_dom_with_elements(self):
        """Test validation of DOM with raw elements."""
        dom = {
            "version": "1.0",
            "elements": [
                {
                    "id": "e1",
                    "bounds": [100, 200, 300, 250],
                    "visual_type": "button",
                    "confidence": 0.95
                }
            ],
            "hierarchy": {
                "id": "root",
                "bounds": [0, 0, 1080, 1920],
                "role": "FrameLayout",
                "children": [
                    {
                        "id": "btn1",
                        "bounds": [100, 200, 300, 250],
                        "role": "Button",
                        "text": "Login",
                        "clickable": True
                    }
                ]
            }
        }

        assert validate_dom(dom) is True

    def test_invalid_missing_version(self):
        """Test validation fails without version."""
        dom = {
            "hierarchy": {
                "id": "root",
                "bounds": [0, 0, 100, 100],
                "role": "Layout"
            }
        }

        with pytest.raises((ValueError, Exception)):
            validate_dom(dom)

    def test_invalid_missing_hierarchy(self):
        """Test validation fails without hierarchy."""
        dom = {
            "version": "1.0"
        }

        with pytest.raises((ValueError, Exception)):
            validate_dom(dom)
