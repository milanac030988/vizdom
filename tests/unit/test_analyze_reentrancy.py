"""
Analysis re-entrancy guard (the 'maximum recursion depth exceeded' bug).

`_do_analyze_screenshot` pumps QApplication.processEvents() so the UI stays
alive during a slow analysis - but the pump also dispatches queued F5/F6
presses, which used to start another full analysis INSIDE the running one.
Each nesting stacked a whole pipeline on the interpreter stack; enough
impatient presses during a slow remote detect (11.8 s observed in session
20260807_004037) blew the 1000-frame recursion limit, surfacing as
'Error in listener: maximum recursion depth exceeded' spam (the traceback was
recovered from the pixels of session 20260807_004113's screenshot, which
captured the failing console; re-entrancy was then reproduced at 7 nested
analyses from 6 queued presses).

The guard admits one analysis at a time; the assertions live in
`_analyze_reentrancy_harness.py`, executed as a SUBPROCESS because
constructing the full main window inside the pytest process aborts natively
in Qt's offscreen platform (the identical flow is stable as a plain script).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5")

REPO = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).with_name("_analyze_reentrancy_harness.py")


def test_analyze_reentrancy_guard():
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
    assert "PASS phase1" in output, output[-2500:]
    assert "PASS phase2" in output, output[-2500:]
