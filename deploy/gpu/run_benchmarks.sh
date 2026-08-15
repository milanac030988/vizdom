#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The full unattended sweep. Start it, walk away, collect one tarball.
#
# Runs each executor column as a SEPARATE process so one model's failure (or
# OOM) cannot take down the columns already finished - partial results are
# still results. Everything lands in benchmarks/results/gpu-<timestamp>/ and
# is tarred at the end for scp.
#
#   bash deploy/gpu/run_benchmarks.sh
#   # ...later, from your machine:
#   scp rented-box:~/vizdom/benchmarks/results/gpu-*.tar.gz .
# ---------------------------------------------------------------------------
set -uo pipefail   # NOT -e: one failed column must not kill the sweep
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
. .venv/bin/activate
export PYTHONPATH=src
export OMNIPARSER_ROOT="${OMNIPARSER_ROOT:-$(pwd)/third_party/OmniParser}"
export OMNIPARSER_ICON_DETECT="${OMNIPARSER_ICON_DETECT:-$(pwd)/models/omniparser/icon_detect/model.pt}"
export OMNIPARSER_ICON_CAPTION="${OMNIPARSER_ICON_CAPTION:-$(pwd)/models/omniparser/icon_caption_florence}"

STAMP=$(date +%Y%m%d_%H%M%S)
OUT="benchmarks/results/gpu-${STAMP}"
mkdir -p "$OUT"
echo "results -> $OUT"
nvidia-smi --query-gpu=name,memory.total --format=csv > "$OUT/gpu.txt"

run_column() {
    local name="$1"; shift
    echo; echo "=============== $name ==============="
    local t0=$SECONDS
    if "$@" > "$OUT/$name.log" 2>&1; then
        echo "$name: OK ($((SECONDS - t0))s)"
    else
        echo "$name: FAILED ($((SECONDS - t0))s) - see $OUT/$name.log"
    fi
}

RUN="python -m visual_dom.evaluation.lifecycle.runner"
MANIFEST="benchmarks/lifecycle-synthetic-v1/steps.json"

# --- the VizDOM columns (our approach, per detector) -----------------------
run_column vizdom-uied        $RUN --manifest "$MANIFEST" --executors vizdom-uied        --out-dir "$OUT"
run_column vizdom-omniparser  $RUN --manifest "$MANIFEST" --executors vizdom-omniparser  --out-dir "$OUT"
run_column vizdom-modular     $RUN --manifest "$MANIFEST" --executors vizdom-modular     --out-dir "$OUT"

# --- the grounder columns (the competing end-to-end paradigm) --------------
run_column elam-7b            $RUN --manifest "$MANIFEST" --executors elam-7b            --out-dir "$OUT"
run_column ui-tars-1.5-7b     $RUN --manifest "$MANIFEST" --executors ui-tars-1.5-7b     --out-dir "$OUT"
run_column aria-ui            $RUN --manifest "$MANIFEST" --executors aria-ui            --out-dir "$OUT"

# --- ADR-027: parity + captioner combos on this GPU ------------------------
run_column parity             python "deploy/gpu/parity_on_box.py" "$OUT/parity.txt"

tar czf "benchmarks/results/gpu-${STAMP}.tar.gz" -C benchmarks/results "gpu-${STAMP}"
echo; echo "sweep complete: benchmarks/results/gpu-${STAMP}.tar.gz"
echo "copy it back, then STOP THE RENTAL."
