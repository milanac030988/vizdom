"""
Central logging for the Visual DOM project.

Goals
-----
* Timestamped, level-tagged, module-tagged log lines (millisecond precision).
* One line to get a logger anywhere:  ``log = get_logger(__name__)``
* Logs go to the console AND a rotating file under ``logs/`` so slow runs can be
  diagnosed after the fact.
* A ``log_timing`` context manager to measure how long a phase takes — used to
  investigate performance (e.g. model load vs. inference).

This is intentionally dependency-free (stdlib ``logging`` only) so it can be
imported from any module, including inside detector backends and the CLI.

Usage
-----
    from visual_dom.logging_utils import get_logger, log_timing

    log = get_logger(__name__)
    log.info("starting")

    with log_timing(log, "load caption model"):
        model = load_model()          # logs "done in 3.41s"

Configuration via environment:
    VIZDOM_LOG_LEVEL   e.g. DEBUG, INFO (default), WARNING
    VIZDOM_LOG_DIR     directory for the log file (default: <project>/logs)
    VIZDOM_LOG_FILE    log file name (default: vizdom.log)
    VIZDOM_LOG_CONSOLE "0" to silence console output (file still written)
"""

import logging
import os
import time
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ROOT_LOGGER_NAME = "visual_dom"
_configured = False

_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-5s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _default_log_dir() -> Path:
    """<project root>/logs, overridable via VIZDOM_LOG_DIR."""
    env = os.environ.get("VIZDOM_LOG_DIR")
    if env:
        return Path(env)
    # this file: <root>/src/visual_dom/logging_utils.py -> parents[2] == <root>
    try:
        root = Path(__file__).resolve().parents[2]
    except IndexError:  # pragma: no cover - unusual layout
        root = Path.cwd()
    return root / "logs"


def configure_logging(
    level: str = None,
    log_file: str = None,
    to_console: bool = None,
    force: bool = False,
) -> logging.Logger:
    """
    Configure the ``visual_dom`` package logger once (idempotent).

    Subsequent calls are no-ops unless ``force=True``. Returns the package logger.
    Handlers are attached to the ``visual_dom`` logger (not the root logger) so we
    do not interfere with other libraries' logging.
    """
    global _configured
    pkg_logger = logging.getLogger(_ROOT_LOGGER_NAME)

    if _configured and not force:
        return pkg_logger

    # Resolve settings (args > env > default)
    level_name = (level or os.environ.get("VIZDOM_LOG_LEVEL") or "INFO").upper()
    resolved_level = getattr(logging, level_name, logging.INFO)
    file_name = log_file or os.environ.get("VIZDOM_LOG_FILE") or "vizdom.log"
    if to_console is None:
        to_console = os.environ.get("VIZDOM_LOG_CONSOLE", "1") != "0"

    pkg_logger.setLevel(resolved_level)
    # Clear our own handlers on force-reconfigure to avoid duplicates.
    if force:
        for h in list(pkg_logger.handlers):
            pkg_logger.removeHandler(h)
    pkg_logger.handlers = [h for h in pkg_logger.handlers
                           if getattr(h, "_vizdom", False) is False] if pkg_logger.handlers else []

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    if to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        ch._vizdom = True  # tag so we can identify our handlers
        pkg_logger.addHandler(ch)

    # Rotating file handler; failure to open a file must never break the app.
    try:
        log_dir = _default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / file_name,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        fh._vizdom = True
        pkg_logger.addHandler(fh)
    except Exception as e:  # pragma: no cover - defensive
        pkg_logger.warning("Could not open log file: %s", e)

    # Don't double-log through the root logger.
    pkg_logger.propagate = False
    _configured = True
    return pkg_logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Return a logger under the ``visual_dom`` namespace, configuring on first use.

    Pass ``__name__`` from the calling module. Names outside the ``visual_dom``
    package are re-homed under it so all project logs share one configuration and
    file (e.g. a script's ``__main__`` becomes ``visual_dom.__main__``).
    """
    configure_logging()
    if not name or name == _ROOT_LOGGER_NAME:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    if name.startswith(_ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    # Re-home foreign names (e.g. "__main__", "tools.viewer...") under the package.
    short = name.split(".")[-1]
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{short}")


@contextmanager
def log_timing(logger: logging.Logger, label: str, level: int = logging.INFO):
    """
    Context manager that logs the wall-clock duration of a block.

    Emits ``"<label>..."`` on entry (DEBUG) and ``"<label> done in X.XXs"`` on
    exit (at ``level``). On exception, logs ``"<label> FAILED after X.XXs"`` and
    re-raises, so timing is captured even for failures.
    """
    logger.debug("%s ...", label)
    start = time.perf_counter()
    try:
        yield
    except BaseException:
        elapsed = time.perf_counter() - start
        logger.error("%s FAILED after %.2fs", label, elapsed)
        raise
    else:
        elapsed = time.perf_counter() - start
        logger.log(level, "%s done in %.2fs", label, elapsed)
