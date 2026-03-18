"""
Visual DOM Plugin - Screenshot-based CV detection plugin.

Uses the Visual DOM Generator pipeline to extract UI elements from screenshots.
This is the primary plugin for image-based GUI testing.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import json

from .base import PlatformPlugin
from ..core.tree import DOMTree, DOMElement, BoundingBox, ElementType


class VisualDOMPlugin(PlatformPlugin):
    """
    Plugin for screenshot-based Visual DOM extraction.

    Uses Computer Vision + OCR + LLM pipeline to detect UI elements
    from screenshots without accessing application internals.

    Supports any platform that can provide screenshots:
    - Windows (screenshot capture)
    - Android (ADB screencap)
    - Linux (screenshot tools)
    - Web (browser screenshot)
    - Any image file
    """

    PLUGIN_NAME = "visual_dom"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_DESCRIPTION = "Visual DOM Generator - CV-based UI element detection from screenshots"
    SUPPORTED_PLATFORMS = ["windows", "android", "linux", "web", "any"]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # Pipeline components (lazy loaded)
        self._cv_extractor = None
        self._hierarchy_builder = None
        self._llm_refiner = None
        self._dom_compiler = None

        # Current state
        self._screenshot_path: Optional[Path] = None
        self._screenshot_data: Optional[bytes] = None
        self._current_dom: Optional[DOMTree] = None

        # Configuration
        self._use_llm = config.get('use_llm', True) if config else True
        self._llm_model = config.get('llm_model', 'qwen2.5:3b') if config else 'qwen2.5:3b'

    def _load_pipeline(self) -> bool:
        """Lazy load pipeline components."""
        if self._cv_extractor is not None:
            return True

        try:
            # Try to import pipeline components
            from visual_dom.cv_pipeline import CVEvidenceExtractor
            from visual_dom.hierarchy_builder import CoarseHierarchyBuilder
            from visual_dom.llm_refiner import LLMHierarchyRefiner
            from visual_dom.dom_compiler import DOMCompiler

            self._cv_extractor = CVEvidenceExtractor()
            self._hierarchy_builder = CoarseHierarchyBuilder()
            if self._use_llm:
                self._llm_refiner = LLMHierarchyRefiner(model=self._llm_model)
            self._dom_compiler = DOMCompiler()

            return True

        except ImportError as e:
            print(f"Warning: Could not load full pipeline: {e}")
            print("Running in basic mode (JSON loading only)")
            return False

    def connect(self, target: str = None) -> bool:
        """
        Connect to target (load screenshot or set source).

        Args:
            target: Path to screenshot file, or None for live capture

        Returns:
            True if connected successfully
        """
        if target:
            path = Path(target)
            if path.exists():
                if path.suffix.lower() == '.json':
                    # Load existing DOM JSON
                    return self._load_dom_json(path)
                elif path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp']:
                    # Load screenshot
                    return self._load_screenshot(path)

        self._connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect and cleanup."""
        self._screenshot_path = None
        self._screenshot_data = None
        self._current_dom = None
        self._connected = False

    def _load_screenshot(self, path: Path) -> bool:
        """Load screenshot from file."""
        try:
            with open(path, 'rb') as f:
                self._screenshot_data = f.read()
            self._screenshot_path = path
            self._connected = True
            return True
        except Exception as e:
            print(f"Error loading screenshot: {e}")
            return False

    def _load_dom_json(self, path: Path) -> bool:
        """Load existing DOM JSON file."""
        try:
            self._current_dom = DOMTree.from_json_file(str(path))
            self._connected = True
            return True
        except Exception as e:
            print(f"Error loading DOM JSON: {e}")
            return False

    def capture_screenshot(self) -> Optional[bytes]:
        """
        Capture or return current screenshot.

        Returns:
            Screenshot image data as bytes
        """
        if self._screenshot_data:
            return self._screenshot_data

        # Try platform-specific capture
        screenshot = self._capture_platform_screenshot()
        if screenshot:
            self._screenshot_data = screenshot

        return self._screenshot_data

    def _capture_platform_screenshot(self) -> Optional[bytes]:
        """Capture screenshot using platform-specific method."""
        import platform
        system = platform.system().lower()

        try:
            if system == 'windows':
                return self._capture_windows_screenshot()
            elif system == 'linux':
                return self._capture_linux_screenshot()
            elif system == 'darwin':
                return self._capture_macos_screenshot()
        except Exception as e:
            print(f"Error capturing screenshot: {e}")

        return None

    def _capture_windows_screenshot(self) -> Optional[bytes]:
        """Capture screenshot on Windows."""
        try:
            from PIL import ImageGrab
            import io

            screenshot = ImageGrab.grab()
            buffer = io.BytesIO()
            screenshot.save(buffer, format='PNG')
            return buffer.getvalue()
        except ImportError:
            print("PIL not available for screenshot capture")
            return None

    def _capture_linux_screenshot(self) -> Optional[bytes]:
        """Capture screenshot on Linux."""
        try:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                temp_path = f.name

            # Try different screenshot tools
            for cmd in [
                ['gnome-screenshot', '-f', temp_path],
                ['scrot', temp_path],
                ['import', '-window', 'root', temp_path],
            ]:
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    with open(temp_path, 'rb') as f:
                        return f.read()
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

        except Exception as e:
            print(f"Error capturing Linux screenshot: {e}")

        return None

    def _capture_macos_screenshot(self) -> Optional[bytes]:
        """Capture screenshot on macOS."""
        try:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                temp_path = f.name

            subprocess.run(['screencapture', '-x', temp_path], check=True)
            with open(temp_path, 'rb') as f:
                return f.read()

        except Exception as e:
            print(f"Error capturing macOS screenshot: {e}")

        return None

    def get_dom_tree(self) -> Optional[DOMTree]:
        """
        Extract DOM tree from current screenshot.

        Returns:
            DOMTree object
        """
        if self._current_dom:
            return self._current_dom

        if not self._screenshot_data:
            screenshot = self.capture_screenshot()
            if not screenshot:
                return None

        # Try to use full pipeline
        if self._load_pipeline() and self._cv_extractor:
            return self._extract_dom_with_pipeline()

        # Fallback: create basic DOM from screenshot dimensions
        return self._create_basic_dom()

    def _extract_dom_with_pipeline(self) -> Optional[DOMTree]:
        """Extract DOM using full CV pipeline."""
        try:
            import tempfile
            from PIL import Image
            import io

            # Save screenshot to temp file for pipeline
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                f.write(self._screenshot_data)
                temp_path = f.name

            # Get image dimensions
            img = Image.open(io.BytesIO(self._screenshot_data))
            width, height = img.size

            # Run pipeline
            evidence = self._cv_extractor.extract(temp_path)
            coarse_dom = self._hierarchy_builder.build(evidence)

            if self._use_llm and self._llm_refiner:
                refined_dom = self._llm_refiner.refine(coarse_dom)
            else:
                refined_dom = coarse_dom

            dom_tree = self._dom_compiler.compile(
                refined_dom,
                screen_width=width,
                screen_height=height
            )

            self._current_dom = dom_tree
            return dom_tree

        except Exception as e:
            print(f"Error in pipeline extraction: {e}")
            return self._create_basic_dom()

    def _create_basic_dom(self) -> DOMTree:
        """Create basic DOM tree from screenshot dimensions."""
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(self._screenshot_data))
            width, height = img.size

            tree = DOMTree(
                screen_width=width,
                screen_height=height,
                title="Screenshot",
                source="visual_dom"
            )

            # Create root element
            root = DOMElement(
                id="root",
                type=ElementType.WINDOW,
                bbox=BoundingBox(0, 0, width, height),
                text="Screenshot Root"
            )
            tree.set_root(root)

            self._current_dom = tree
            return tree

        except Exception as e:
            print(f"Error creating basic DOM: {e}")
            return None

    def get_element_at_point(self, x: int, y: int) -> Optional[DOMElement]:
        """
        Get element at specific coordinates.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            DOMElement at the point
        """
        if not self._current_dom:
            self.get_dom_tree()

        if self._current_dom:
            return self._current_dom.find_element_at_point(x, y)

        return None

    def refresh(self) -> bool:
        """Refresh DOM tree from screenshot."""
        self._current_dom = None
        return self.get_dom_tree() is not None

    def analyze_screenshot(self, screenshot_path: str) -> Optional[DOMTree]:
        """
        Analyze a screenshot file and return DOM tree.

        Args:
            screenshot_path: Path to screenshot file

        Returns:
            DOMTree object
        """
        if self._load_screenshot(Path(screenshot_path)):
            self._current_dom = None  # Force re-analysis
            return self.get_dom_tree()
        return None

    def get_available_targets(self) -> List[Dict[str, str]]:
        """Get list of available screenshot sources."""
        targets = [
            {'id': 'screen', 'name': 'Current Screen'},
            {'id': 'file', 'name': 'Load from File'},
        ]

        # Add platform-specific sources
        import platform
        if platform.system() == 'Windows':
            targets.append({'id': 'window', 'name': 'Select Window'})

        return targets

    def export_to_robot(self, elements: List[DOMElement], output_path: str) -> bool:
        """
        Export selected elements to Robot Framework resource file.

        Args:
            elements: List of elements to export
            output_path: Path for output .resource file

        Returns:
            True if export successful
        """
        try:
            lines = [
                "*** Variables ***",
                "# Auto-generated by Visual DOM Viewer",
                f"# Source: {self._screenshot_path or 'Screenshot'}",
                "",
            ]

            for elem in elements:
                var_name = self._generate_variable_name(elem)
                locator = elem.to_robot_locator()
                lines.append(f"${{{var_name}}}    {locator}")

            lines.append("")
            lines.append("*** Keywords ***")

            for elem in elements:
                keyword_name = self._generate_keyword_name(elem)
                var_name = self._generate_variable_name(elem)

                if elem.type == ElementType.BUTTON:
                    lines.extend([
                        f"Click {keyword_name}",
                        f"    Click Element    ${{{var_name}}}",
                        "",
                    ])
                elif elem.type == ElementType.INPUT_FIELD:
                    lines.extend([
                        f"Input To {keyword_name}",
                        f"    [Arguments]    ${{text}}",
                        f"    Input Text    ${{{var_name}}}    ${{text}}",
                        "",
                    ])

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            return True

        except Exception as e:
            print(f"Error exporting to Robot: {e}")
            return False

    def _generate_variable_name(self, elem: DOMElement) -> str:
        """Generate Robot Framework variable name for element."""
        base = elem.text or elem.type.value
        # Clean up the name
        name = ''.join(c if c.isalnum() else '_' for c in base)
        name = name.strip('_').upper()
        return f"{elem.type.value.upper()}_{name}" if name else elem.id.upper()

    def _generate_keyword_name(self, elem: DOMElement) -> str:
        """Generate Robot Framework keyword name for element."""
        base = elem.text or elem.type.value
        # Title case with spaces
        name = ''.join(c if c.isalnum() else ' ' for c in base)
        return ' '.join(word.capitalize() for word in name.split())
