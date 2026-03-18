"""
Main entry point for Visual DOM Viewer.

Run with: python -m tools.visual_dom_viewer
"""

import sys
import argparse


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Visual DOM Viewer - Interactive UI Element Inspector"
    )
    parser.add_argument(
        '--screenshot', '-s',
        help='Path to screenshot file to load'
    )
    parser.add_argument(
        '--dom', '-d',
        help='Path to DOM JSON file to load'
    )
    parser.add_argument(
        '--export', '-e',
        help='Export DOM to Robot Framework resource file and exit'
    )
    parser.add_argument(
        '--plugin-path',
        help='Path to load external plugins from'
    )
    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Run in headless mode (for export only)'
    )
    parser.add_argument(
        '--list-plugins',
        action='store_true',
        help='List available plugins and exit'
    )

    args = parser.parse_args()

    # List plugins
    if args.list_plugins:
        from .plugins import PluginRegistry
        plugins = PluginRegistry.list_plugins()
        print("\nAvailable Plugins:")
        print("-" * 60)
        for plugin in plugins:
            print(f"  {plugin['name']:20} - {plugin['description']}")
            print(f"                       Platforms: {', '.join(plugin['platforms'])}")
        return 0

    # Load external plugins if path provided
    if args.plugin_path:
        from .plugins import PluginRegistry
        discovered = PluginRegistry.discover_external_plugins(args.plugin_path)
        if discovered:
            print(f"Discovered plugins: {', '.join(discovered)}")

    # Headless export mode
    if args.no_gui and args.dom and args.export:
        return run_headless_export(args.dom, args.export)

    # GUI mode
    try:
        from .ui import VisualDOMViewerWindow
        from .ui.main_window import run_viewer

        # Pre-load files if provided
        if args.screenshot or args.dom:
            from .core.model import DOMViewerModel
            model = DOMViewerModel.get_instance()

            if args.dom:
                model.load_dom_from_file(args.dom)
            if args.screenshot:
                model.load_screenshot(args.screenshot)

        return run_viewer()

    except ImportError as e:
        print(f"Error: Could not start GUI: {e}")
        print("Install PyQt5 with: pip install PyQt5")
        return 1


def run_headless_export(dom_path: str, export_path: str) -> int:
    """Run headless export."""
    from .core.tree import DOMTree
    from .export import RobotResourceExporter

    try:
        print(f"Loading DOM from: {dom_path}")
        dom_tree = DOMTree.from_json_file(dom_path)
        print(f"Found {dom_tree.get_element_count()} elements")

        exporter = RobotResourceExporter()
        elements = dom_tree.get_all_elements()

        print(f"Exporting to: {export_path}")
        success = exporter.export(elements, export_path, dom_tree)

        if success:
            print("Export successful!")
            return 0
        else:
            print("Export failed!")
            return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
