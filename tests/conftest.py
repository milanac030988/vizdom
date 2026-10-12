"""Shared pytest setup."""

import logging

import pytest


@pytest.fixture(autouse=True)
def _visual_dom_logs_reach_caplog():
    """
    The ``visual_dom`` logger does not propagate to the root logger (it owns
    its console and file handlers; see logging_utils), so ``caplog`` sees
    nothing unless propagation is on for the duration of the test.
    """
    logger = logging.getLogger("visual_dom")
    before = logger.propagate
    logger.propagate = True
    yield
    logger.propagate = before
