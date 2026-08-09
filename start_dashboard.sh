#!/usr/bin/env bash
# VizDOM session dashboard (Streamlit)
# POSIX counterpart of start_dashboard.bat. Interpreter resolution: python_env.sh
# (override with VIZDOM_PYTHON; see docs/uv-setup.md).
#
# Needs the [dashboard] group: uv pip install -e ".[dashboard]" 
set -euo pipefail
cd "$(dirname "$0")"
. ./python_env.sh
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$VIZDOM_PY" -m streamlit run tools/dashboard/app.py --server.port 8501
