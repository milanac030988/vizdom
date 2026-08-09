#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Resolve ONE Python interpreter for every VizDOM launcher (POSIX counterpart
# of python_env.bat). Source it, do not execute it:
#
#     . "$(dirname "$0")/python_env.sh"
#
# Resolution order (first hit wins), documented in docs/uv-setup.md:
#   1. $VIZDOM_PYTHON            explicit override - always wins
#   2. .venv/bin/python          the uv environment (Linux, macOS)
#   3. .venv/Scripts/python.exe  the uv environment under Git Bash on Windows
#   4. python3.12 / 3.11 / 3.10 / 3.9   a versioned interpreter on PATH
#   5. python3, then python      last resort
#
# Exports VIZDOM_PY, or returns 1 with an actionable message.
# ---------------------------------------------------------------------------

VIZDOM_PY=""
_vizdom_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# 1. explicit override
if [ -n "${VIZDOM_PYTHON:-}" ]; then
    if [ -x "$VIZDOM_PYTHON" ]; then
        VIZDOM_PY="$VIZDOM_PYTHON"
    else
        echo "[python_env] VIZDOM_PYTHON is set but not executable: $VIZDOM_PYTHON" >&2
        return 1 2>/dev/null || exit 1
    fi
fi

# 2/3. in-project environment created by `uv venv`
if [ -z "$VIZDOM_PY" ]; then
    for _cand in "$_vizdom_root/.venv/bin/python" "$_vizdom_root/.venv/Scripts/python.exe"; do
        [ -x "$_cand" ] && { VIZDOM_PY="$_cand"; break; }
    done
fi

# 4/5. an interpreter on PATH, newest first
if [ -z "$VIZDOM_PY" ]; then
    for _cand in python3.12 python3.11 python3.10 python3.9 python3 python; do
        if command -v "$_cand" >/dev/null 2>&1; then
            # must be >= 3.9; a bare `python` may still be 2.7 on old systems
            if "$_cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
                VIZDOM_PY="$(command -v "$_cand")"
                break
            fi
        fi
    done
fi

if [ -z "$VIZDOM_PY" ]; then
    cat >&2 <<'EOF'
[python_env] No usable Python (>= 3.9) found.
             Create an environment:
                 uv venv --python 3.12 && uv pip install -e ".[ocr,grpc]"
             or point at one:
                 export VIZDOM_PYTHON=/path/to/python
             See docs/uv-setup.md
EOF
    return 1 2>/dev/null || exit 1
fi

# A resolved interpreter is not necessarily a PREPARED one: candidate 4/5 can
# find a bare python3 on PATH that has none of the project's dependencies, and
# the failure would surface much later as `ModuleNotFoundError: No module named
# 'cv2'`. Say so up front, once, without blocking (the user may be mid-install).
if ! "$VIZDOM_PY" -c 'import cv2, numpy' >/dev/null 2>&1; then
    echo "[python_env] $VIZDOM_PY lacks the project dependencies." >&2
    echo "             Install them:  uv pip install --python \"$VIZDOM_PY\" -e \".[ocr,grpc]\"" >&2
    echo "             or select another interpreter:  export VIZDOM_PYTHON=/path/to/python" >&2
fi

export VIZDOM_PY
export VIZDOM_ROOT="$_vizdom_root"
