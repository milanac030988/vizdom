"""
Viewer "Click via Actuator" end to end (ADR-028).

The assertions live in `_try_locator_harness.py`, run as a SUBPROCESS for the
same reason as test_analyze_reentrancy: constructing the full main window
inside the pytest process aborts natively in Qt's offscreen platform.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5")

REPO = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).with_name("_try_locator_harness.py")


def test_click_via_actuator_flow():
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(REPO / "src"), str(REPO / "tools")]),
        QT_QPA_PLATFORM="offscreen",
    )
    result = subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=str(REPO), env=env,
        capture_output=True, text=True, timeout=180,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"harness failed:\n{output[-2500:]}"
    for phase in ("phase1", "phase2", "phase3"):
        assert f"PASS {phase}" in output, output[-2500:]
