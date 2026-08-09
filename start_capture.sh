#!/usr/bin/env bash
# VizDOM Capture gRPC Service (ADR-018)
# POSIX counterpart of start_capture.bat. Interpreter resolution: python_env.sh
# (override with VIZDOM_PYTHON; see docs/uv-setup.md).
#
# Runs where the application under test is visible.
#   ./start_capture.sh --strategy linux --window-title "Calculator"
#   ./start_capture.sh --strategy android --serial <device>
#   ./start_capture.sh --list
#
# On Linux the `linux` strategy needs an X11 display ($DISPLAY) and mss;
# focus_target additionally needs wmctrl or xdotool (ADR-021). Wayland exposes
# no equivalent to unprivileged clients, so focus returns False there.
set -euo pipefail
cd "$(dirname "$0")"
. ./python_env.sh
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$VIZDOM_PY" -m visual_dom.adapters.inbound.grpc.capture_server "$@"
