#!/usr/bin/env bash
# VizDOM Actuator gRPC Service (ADR-019)
# POSIX counterpart of start_actuator.bat. Interpreter resolution: python_env.sh
# (override with VIZDOM_PYTHON; see docs/uv-setup.md).
#
#   ./start_actuator.sh --strategy desktop
#   ./start_actuator.sh --strategy android --serial <device>
#   ./start_actuator.sh --list
#
# The `desktop` strategy uses pyautogui, which on Linux needs python3-xlib and
# a running X server (`sudo apt install python3-xlib scrot`).
set -euo pipefail
cd "$(dirname "$0")"
. ./python_env.sh
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$VIZDOM_PY" -m visual_dom.adapters.inbound.grpc.actuator_server "$@"
