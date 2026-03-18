"""
Platform adapters for executing GUI actions.
"""

from .base import BaseAdapter
from .desktop import DesktopAdapter
from .android import AndroidAdapter

__all__ = ["BaseAdapter", "DesktopAdapter", "AndroidAdapter"]
