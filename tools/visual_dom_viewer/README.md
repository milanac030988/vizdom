# Visual DOM Viewer

Interactive UI Element Inspector for Visual DOM-based GUI Testing.

A tool similar to UIAutomatorViewer that helps visualize, select, and export UI elements from screenshots for test automation.

## Features

- **Visual Element Selection**: Click on elements in screenshot to select them
- **Explore Mode**: Hover over elements with dashed red rectangle highlighting
- **Tree View**: Hierarchical view of all detected UI elements
- **Property Inspector**: View detailed properties of selected elements
- **Robot Framework Export**: Export selected elements to `.resource` files
- **Pluggable Platform Support**: Extensible architecture for multiple platforms

## Installation

```bash
# Install dependencies
pip install PyQt5 Pillow

# Optional: Install full Visual DOM pipeline
pip install easyocr opencv-python
```

## Usage

### GUI Mode

```bash
# Run the viewer
python -m tools.visual_dom_viewer

# Open with screenshot
python -m tools.visual_dom_viewer --screenshot path/to/screenshot.png

# Open with existing DOM JSON
python -m tools.visual_dom_viewer --dom path/to/dom.json
```

### Headless Export

```bash
# Export DOM to Robot Framework resource file
python -m tools.visual_dom_viewer --no-gui --dom input.json --export output.resource
```

### List Plugins

```bash
python -m tools.visual_dom_viewer --list-plugins
```

## Architecture

```
visual_dom_viewer/
├── core/                   # Core components
│   ├── model.py           # DOMViewerModel (Singleton)
│   ├── tree.py            # DOMTree, DOMElement
│   └── state.py           # ViewerState, StateManager
├── plugins/               # Platform plugins
│   ├── base.py            # PlatformPlugin base class
│   ├── registry.py        # Plugin registry
│   └── visual_dom_plugin.py  # CV-based Visual DOM plugin
├── export/                # Export modules
│   └── robot_exporter.py  # Robot Framework exporter
├── ui/                    # UI components (PyQt5)
│   └── main_window.py     # Main application window
└── __main__.py           # Entry point
```

## Plugin System

### Creating a Custom Plugin

```python
from tools.visual_dom_viewer.plugins.base import PlatformPlugin
from tools.visual_dom_viewer.plugins.registry import register_plugin

@register_plugin
class MyCustomPlugin(PlatformPlugin):
    PLUGIN_NAME = "my_plugin"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "My custom platform plugin"
    SUPPORTED_PLATFORMS = ["my_platform"]

    def connect(self, target: str = None) -> bool:
        # Connect to target
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def capture_screenshot(self) -> bytes:
        # Return screenshot as PNG bytes
        pass

    def get_dom_tree(self) -> DOMTree:
        # Return DOM tree
        pass

    def get_element_at_point(self, x: int, y: int) -> DOMElement:
        # Return element at coordinates
        pass
```

### Loading External Plugins

```bash
python -m tools.visual_dom_viewer --plugin-path /path/to/my/plugins
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Open Screenshot |
| `F5` | Capture Screen |
| `F6` | Analyze Screenshot |
| `Ctrl++` | Zoom In |
| `Ctrl+-` | Zoom Out |
| `Ctrl+0` | Reset View |
| `Ctrl+E` | Export to Robot |
| `Ctrl+T` | Click Selected via Actuator |

## Trying a Locator (Click via Actuator)

Right-click an element on the canvas or in the tree and choose **Click via Actuator**
(or select it and press `Ctrl+T`). The Viewer then does what a Robot test does:

1. captures and analyzes the screen again (Pipeline Settings > Actuation >
   *Capture again before resolving*, on by default);
2. resolves the element's locator, exactly as it will be exported, with the same
   resolver as `Get Visual Element`. If it does not resolve to exactly one element
   you get the reason, and no click is sent;
3. raises the target window and clicks through the configured actuator
   (desktop, android, the gRPC actuator service, or a plugin);
4. captures again so you see the result.

The target window is *Actuation > Window title*, else the connected window, else the
window the last capture was scoped to. The first click of a session asks for
confirmation. **Copy Locator** on the same menu copies the locator string. See
[ADR-028](../../docs/adr/028-viewer-try-locator-via-actuator.md).

## Exported Robot Framework Format

```robotframework
*** Settings ***
Library          VisualGuiLibrary

*** Variables ***
# Element: button | Text: "Submit" | Position: (100, 200)
${BUTTON_SUBMIT}    text=Submit role=button || id=E12

*** Keywords ***
Click Submit
    [Documentation]    Click the Submit button
    Click Visual    ${BUTTON_SUBMIT}
```

Locators contain only properties the locator language understands (text, hint,
role); the element id is a fallback after `||` because ids are renumbered when a
re-analysis finds a new element. Selected properties with no locator equivalent
(position, size, confidence) are named in the comment and left out.

## Platform Support

| Platform | Plugin | Status |
|----------|--------|--------|
| Visual DOM (CV) | `visual_dom` | ✅ Implemented |
| Windows | `windows` | 🔜 Planned |
| Android | `android` | 🔜 Planned |
| Linux | `linux` | 🔜 Planned |
| Web | `web` | 🔜 Planned |

## Integration with Visual DOM Generator

This viewer is part of the Visual DOM Generator project and can directly load DOM JSON files generated by the CV pipeline:

```python
from visual_dom import VisualDOMGenerator

# Generate DOM
generator = VisualDOMGenerator()
dom = generator.process("screenshot.png")
dom.save("screenshot_dom.json")

# View in Visual DOM Viewer
# python -m tools.visual_dom_viewer --dom screenshot_dom.json --screenshot screenshot.png
```

## License

Part of the Visual DOM Generator Master Project.
