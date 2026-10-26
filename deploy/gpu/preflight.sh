#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Two-minute sanity BEFORE the long sweep: load every model the sweep will use,
# in the env the sweep will use it from, and ground ONE instruction (ELAM also
# judges one statement). A broken adapter, a missing package, a wrong prompt
# template or a wrong coordinate scale fails here, in minute two - not two
# hours into paid GPU time with a column of zeros that looks like a result.
#
# Main env (.venv, transformers 4.49):    UI-TARS-1.5, VizDOM + OmniParser
# Legacy env (.venv-legacy, 4.47):        ELAM-7B (Molmo code), Aria-UI
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH=src
export USE_TF=0   # tensorflow-cpu is installed only to satisfy ELAM's import check

fail=0
echo "=== main env ==="
.venv/bin/python deploy/gpu/preflight.py --grounders ui-tars-1.5-7b --pipeline || fail=1

if [ -x .venv-legacy/bin/python ]; then
    echo "=== legacy env ==="
    .venv-legacy/bin/python deploy/gpu/preflight.py --grounders elam-7b,aria-ui || fail=1
else
    echo "!! .venv-legacy missing (setup.sh builds it): elam-7b and aria-ui will FAIL in the sweep"
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    echo; echo "preflight FAILED - fix the lines marked FAIL before running the sweep."
    exit 1
fi
echo; echo "preflight passed. Next: bash deploy/gpu/run_benchmarks.sh"
