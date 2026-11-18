"""
VizDOM Studio bridge: the local HTTP/WebSocket API the Electron GUI talks to.

The Electron app (``tools/vizdom_studio``) starts this as a child process,
bound to 127.0.0.1 with a random port and a per-launch token. Everything the
GUI does goes through the same Python code the PyQt Viewer and the Robot
library use - ``visual_dom.connect().analyze()``, the capture and actuator
registries, ``LocatorResolver``, the Viewer's locator and Robot exporters - so
a locator proved in the GUI is the string a suite resolves.

Sessions are written to ``output/sessions/<id>/`` in the Viewer's format
(``screenshot.png``, ``dom_result.json``, ``session_info.json``), so either
tool opens the other's results.
"""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    from .server import create_app as _create
    return _create(*args, **kwargs)
