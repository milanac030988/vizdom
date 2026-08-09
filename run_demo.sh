#!/usr/bin/env bash
# Run a Robot Framework suite with the project's interpreter
# POSIX counterpart of run_demo.bat. Interpreter resolution: python_env.sh
# (override with VIZDOM_PYTHON; see docs/uv-setup.md).
#
# Prerequisite: the three services are running (start_detector.sh /
# start_capture.sh / start_actuator.sh). Results land in output/demo_run.
#
# NOTE: the bundled example drives the WINDOWS Calculator (it launches
# calc.exe), so it cannot pass on Linux. Point this at your own suite:
#   ./run_demo.sh path/to/your_suite.robot
# or pass robot options before the suite path.
set -euo pipefail
cd "$(dirname "$0")"
. ./python_env.sh
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

SUITE="examples/windows_calculator_demo/calculator_demo.robot"
ARGS=()
for arg in "$@"; do
    case "$arg" in
        *.robot) SUITE="$arg" ;;
        *)       ARGS+=("$arg") ;;
    esac
done

# The bundled example launches calc.exe, so warn when it is used off Windows.
if [ "$SUITE" = "examples/windows_calculator_demo/calculator_demo.robot" ]; then
    case "$(uname -s)" in
        Linux*|Darwin*)
            echo "note: the bundled demo drives the WINDOWS Calculator and cannot" >&2
            echo "      pass here. Pass your own suite: ./run_demo.sh my_suite.robot" >&2
            ;;
    esac
fi

exec "$VIZDOM_PY" -m robot --outputdir output/demo_run ${ARGS[@]+"${ARGS[@]}"} "$SUITE"
