"""Unit tests for locator parsing."""

import pytest
from visual_gui_library.locators.locator import (
    LocatorParser,
    Locator,
    LocatorStrategy
)


class TestLocatorParser:
    """Tests for LocatorParser."""

    def test_parse_simple_text_locator(self):
        """Test parsing simple text locator."""
        result = LocatorParser.parse('text="Login"')

        assert len(result) == 1
        assert result[0].strategy == LocatorStrategy.TEXT
        assert result[0].value == "Login"

    def test_parse_unquoted_value(self):
        """Test parsing locator without quotes."""
        result = LocatorParser.parse("role=Button")

        assert len(result) == 1
        assert result[0].strategy == LocatorStrategy.ROLE
        assert result[0].value == "Button"

    def test_parse_multiple_locators(self):
        """Test parsing multiple locators."""
        result = LocatorParser.parse('text="Submit" role=Button')

        assert len(result) == 2
        assert result[0].strategy == LocatorStrategy.TEXT
        assert result[0].value == "Submit"
        assert result[1].strategy == LocatorStrategy.ROLE
        assert result[1].value == "Button"

    def test_parse_hint_locator(self):
        """Test parsing hint locator."""
        result = LocatorParser.parse('hint="Enter email"')

        assert len(result) == 1
        assert result[0].strategy == LocatorStrategy.HINT
        assert result[0].value == "Enter email"

    def test_parse_relative_locators(self):
        """Test parsing relative position locators."""
        result = LocatorParser.parse('below="Username" right_of="Label"')

        assert len(result) == 2
        assert result[0].strategy == LocatorStrategy.BELOW
        assert result[1].strategy == LocatorStrategy.RIGHT_OF

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty list."""
        result = LocatorParser.parse("")
        assert len(result) == 0

    def test_parse_within_locator(self):
        """Test parsing structural locator."""
        result = LocatorParser.parse('within="LoginForm"')

        assert len(result) == 1
        assert result[0].strategy == LocatorStrategy.WITHIN
        assert result[0].value == "LoginForm"
