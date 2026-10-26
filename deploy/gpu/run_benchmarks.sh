#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The full unattended sweep. Start it, walk away, collect one tarball.
#
# Runs each executor column as a SEPARATE process so one model's failure (or
# OOM) cannot take down the columns already finished - partial results are
# still results. Everything lands in benchmarks/results/gpu-<timestamp>/ and
# is tarred at the end for scp. Run it inside tmux: the box keeps going when
# the laptop's SSH session drops.
#
#   bash deploy/gpu/run_benchmarks.sh
#
# Re-run only some columns into an EXISTING run dir (after fixing something):
#
#   ONLY="elam-7b aria-ui" OUT_DIR=benchmarks/results/gpu-20261025_221752 \
#       bash deploy/gpu/run_benchmarks.sh
#
# Later, from your machine:
#   scp -P <port> root@<box>:~/vizdom/benchmarks/results/gpu-*.tar.gz .
# ---------------------------------------------------------------------------
set -uo pipefail   # NOT -e: one failed column must not kill the sweep
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
. .venv/bin/activate
export PYTHONPATH=src
export USE_TF=0
export OMNIPARSER_ROOT="${OMNIPARSER_ROOT:-$(pwd)/third_party/OmniParser}"
export OMNIPARSER_ICON_DETECT="${OMNIPARSER_ICON_DETECT:-$(pwd)/models/omniparser/icon_detect/model.pt}"
export OMNIPARSER_ICON_CAPTION="${OMNIPARSER_ICON_CAPTION:-$(pwd)/models/omniparser/icon_caption_florence}"

OUT="${OUT_DIR:-benchmarks/results/gpu-$(date +%Y%m%d_%H%M%S)}"
OUT="${OUT%/}"
ONLY="${ONLY:-}"
mkdir -p "$OUT"
# everything this script prints also goes into the run dir
exec > >(tee -a "$OUT/sweep.log") 2>&1
echo "results -> $OUT   (columns: ${ONLY:-all})"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > "$OUT/gpu.txt"
{ echo "commit: $(git rev-parse --short HEAD 2>/dev/null)"; date -u; } >> "$OUT/gpu.txt"

wanted() { [ -z "$ONLY" ] || [[ " $ONLY " == *" $1 "* ]]; }

run_column() {
    local name="$1"; shift
    wanted "$name" || { echo "$name: skipped (ONLY=$ONLY)"; return; }
    echo; echo "=============== $name ==============="
    local t0=$SECONDS
    if "$@" > "$OUT/$name.log" 2>&1; then
        echo "$name: OK ($((SECONDS - t0))s)"
        tail -1 "$OUT/$name.log"           # the result row
    else
        echo "$name: FAILED ($((SECONDS - t0))s) - see $OUT/$name.log"
        grep -m1 -E "Error|error:|FATAL" "$OUT/$name.log" || true
    fi
}

RUN="python -m visual_dom.evaluation.lifecycle.runner"
MANIFEST="benchmarks/lifecycle-synthetic-v1/steps.json"

# --- the VizDOM columns (our approach, per detector) -----------------------
run_column vizdom-uied        $RUN --manifest "$MANIFEST" --executors vizdom-uied        --out-dir "$OUT"
run_column vizdom-omniparser  $RUN --manifest "$MANIFEST" --executors vizdom-omniparser  --out-dir "$OUT"
run_column vizdom-modular     $RUN --manifest "$MANIFEST" --executors vizdom-modular     --out-dir "$OUT"

# --- the grounder columns (the competing end-to-end paradigm) --------------
# 7B grounders run in bf16 on a >= 20 GB card (the 4-bit path exists for the
# laptop; Molmo/ELAM under bnb 4-bit fails with a Float/Half dtype error).
VRAM_GB=$(python -c "import torch;print(int(torch.cuda.get_device_properties(0).total_memory/1e9))")
QUANT=""; [ "$VRAM_GB" -ge 20 ] && QUANT="--no-quantize"
# ELAM (Molmo code) and Aria-UI (old Llama attention) need transformers
# <= 4.47/4.48, which UI-TARS (Qwen2.5-VL, >= 4.49) cannot share: setup.sh
# builds .venv-legacy for them. Aria-UI needs a 48 GB card (its MoE experts
# are not quantized by bnb; 24 GB OOMs at shard 5/12, ~50 GB extrapolated,
# so an A100 40 GB - which reports 42 - is out too; gate 46, same as
# AriaUiGrounder.MIN_VRAM_GB) - on a smaller card the column is skipped
# here rather than paid for and then marked FAILED.
[ "$VRAM_GB" -ge 46 ] || ONLY="${ONLY:-vizdom-uied vizdom-omniparser vizdom-modular elam-7b ui-tars-1.5-7b parity}"
if [ -x .venv-legacy/bin/python ]; then
    LEGACY=".venv-legacy/bin/python -m visual_dom.evaluation.lifecycle.runner"
else
    echo "!! .venv-legacy missing - elam-7b / aria-ui will fail (run setup.sh)"
    LEGACY="$RUN"
fi
run_column elam-7b            $LEGACY --manifest "$MANIFEST" --executors elam-7b        $QUANT --out-dir "$OUT"
run_column ui-tars-1.5-7b     $RUN    --manifest "$MANIFEST" --executors ui-tars-1.5-7b $QUANT --out-dir "$OUT"
run_column aria-ui            $LEGACY --manifest "$MANIFEST" --executors aria-ui                --out-dir "$OUT"

# --- ADR-027: parity + captioner combos on this GPU ------------------------
run_column parity             python "deploy/gpu/parity_on_box.py" "$OUT/parity.txt"

# --- one table with every column that produced a result --------------------
{
    echo "# $(basename "$OUT")"; echo; cat "$OUT/gpu.txt"; echo
    echo "| executor | action-hit | verify acc | false-pass | median step (s) | cost |"
    echo "|---|---|---|---|---|---|"
    # One row per executor, the LATEST one: an ONLY= rerun into the same dir
    # writes a second <stamp>.md for that column and the old row (possibly a
    # FAILED one) must not stay in the table. awk, not tail: the runner's .md
    # has no trailing newline, so tail glued the rows onto one line.
    for md in $(ls "$OUT"/*_*.md 2>/dev/null | sort); do
        awk 'NR > 2' "$md"
    done | awk -F'|' '{
        k = $2
        if (!(k in row)) order[++n] = k
        row[k] = $0
    } END { for (i = 1; i <= n; i++) print row[order[i]] }'
} > "$OUT/summary.md"
echo; cat "$OUT/summary.md"

tar czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
echo; echo "sweep complete: $OUT.tar.gz"
echo "copy it back, verify it opens, then DESTROY THE RENTAL."
