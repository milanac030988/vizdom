"""
Visual DOM Generator

Convert GUI screenshots into UIAutomator-like DOM JSON using CV + small LLM.

Quick start::

    from visual_dom import connect
    session = connect("vizdom.config.json")   # or connect() for defaults
    dom = session.analyze("screenshot.png")
"""

__version__ = "0.1.0"


def connect(config=None):
    """Start a configured VizDOM session. See :func:`visual_dom.context.connect`.

    Imported lazily so ``import visual_dom`` stays cheap and free of heavy CV
    dependencies until a session is actually created.
    """
    from visual_dom.context import connect as _connect
    return _connect(config)


def load_config(source=None):
    """Load a :class:`visual_dom.config.VizDomConfig` from a file/dict/None."""
    from visual_dom.config import VizDomConfig
    return VizDomConfig.load(source)


__all__ = ["connect", "load_config", "__version__"]