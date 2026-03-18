"""
Robot Framework keywords for visual GUI automation.
"""

from .capture import CaptureKeywords
from .assertions import AssertionKeywords
from .actions import ActionKeywords


class VisualGuiLibrary(CaptureKeywords, AssertionKeywords, ActionKeywords):
    """
    Robot Framework library for visual GUI automation.

    This library provides keywords for image-based GUI testing using
    Visual DOM for element identification.

    Locator Strategies:
        - text="Login"      : Find by visible text
        - hint="Email"      : Find by hint/placeholder text
        - role=button       : Find by accessibility role
        - within="Form"     : Find within container
        - right_of="Label"  : Find element to the right of another
        - below="Title"     : Find element below another

    Example:
        | Library | VisualGuiLibrary |
        |         |                  |
        | Dump Visual DOM |          |
        | Click Visual | text=Login  |
        | Type Text Visual | hint=Email | user@example.com |
        | Element Should Exist | text=Welcome |
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_VERSION = "0.1.0"

    def __init__(
        self,
        platform: str = "desktop",
        ocr_engine: str = "tesseract",
        click_delay: float = 0.1,
        **kwargs
    ):
        """
        Initialize Visual GUI Library.

        Args:
            platform: Target platform ("desktop", "android")
            ocr_engine: Default OCR engine for DOM generation
            click_delay: Delay after clicks in seconds
            **kwargs: Additional configuration options
        """
        CaptureKeywords.__init__(self)
        AssertionKeywords.__init__(self)
        ActionKeywords.__init__(self, platform=platform, click_delay=click_delay, **kwargs)

        self.platform = platform
        self.ocr_engine = ocr_engine


__all__ = ["VisualGuiLibrary"]
