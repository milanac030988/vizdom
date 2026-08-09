#!/usr/bin/env bash
# VizDOM Viewer (PyQt5 element inspector)
# POSIX counterpart of start_viewer.bat. Interpreter resolution: python_env.sh
# (override with VIZDOM_PYTHON; see docs/uv-setup.md).
#
# Needs the [viewer] group: uv pip install -e ".[viewer]" 
set -euo pipefail
cd "$(dirname "$0")"
. ./python_env.sh
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$VIZDOM_PY" -m tools.visual_dom_viewer "$@"
