"""
Full-lifecycle benchmark: one unified step set, executed by every system under
comparison (VizDOM detector backends AND per-step grounding models), scored on
the same outcomes.

Design (see docs/EVALUATION.md):
- Steps carry a DUAL representation - a locator (for DOM systems) and a
  natural-language instruction (for grounders) - plus ground-truth target
  bounds and, for verification steps, an expected PASSED/FAILED verdict.
- Action steps score "action-hit": would the produced click land inside the
  ground-truth element's bounds.
- Verification steps score oracle quality, including FALSE PASSES on
  deliberately-absent targets - the metric that distinguishes a *testing*
  benchmark from an agent benchmark.
"""

from .generate import generate_steps
from .runner import run_benchmark
