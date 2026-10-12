"""
Locator strategies for finding visual elements.
"""

from .locator import LocatorParser, Locator, LocatorStrategy, ElementFinder
from .resolver import LocatorResolver, Resolution

__all__ = ["LocatorParser", "Locator", "LocatorStrategy", "ElementFinder",
           "LocatorResolver", "Resolution"]
