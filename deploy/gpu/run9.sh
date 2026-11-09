#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Run 9: the measurements the audit of 2026-11-09 could not make offline
# (benchmarks/lifecycle-realworld-v1/AUDIT.md). A sweep of its own, not more
# columns in run_benchmarks.sh: it reruns HALF of some columns (verify steps
# only) and adds two sets, and none of that belongs in the full sweep.
#
#   1. The grounders' verify steps again, with nothing to blame on our side:
#      ELAM-7B scored by the official FAILED-first rule (its raw answer is
#      now kept in the result file), and UI-TARS-1.5 asked the statement as a
#      yes/no question instead of the "any point is a pass" proxy.
#   2. The near-miss negatives (lifecycle-realworld-nearmiss-v1: 168 real
#      captions of a sibling screen that share words with a caption on this
#      one), for every column. The audit measured VizDOM on them offline;
#      the grounders have never seen them.
#   3. The held-out screens (lifecycle-realworld-heldout-v1), when that
#      manifest is in the clone: applications no constant was looked at on.
#   4. The VizDOM rows of the real-application set end to end at this commit.
#
# Same environment as the full sweep: setup.sh, prefetch.sh and preflight
# first (deploy/gpu/README.md, "Run 9"). Cheap columns run first, ELAM last,
# so a rental cut short still has the rows that cost minutes.
#
#   bash deploy/gpu/run9.sh
#   RUN9_ONLY="nm-elam-7b rw-elam-7b" OUT_DIR=benchmarks/results/gpu-<stamp> \
#       bash deploy/gpu/run9.sh            # rerun some columns into a run dir
#
# RUN9_ONLY, not ONLY: prefetch.sh reads ONLY with the full sweep's column
# names, and an exported ONLY would switch every column here off.
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
ONLY="${RUN9_ONLY:-}"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/sweep.log") 2>&1
echo "run 9 -> $OUT   (columns: ${ONLY:-all})"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > "$OUT/gpu.txt"
{ echo "commit: $(git rev-parse --short HEAD 2>/dev/null)"; date -u; echo "sweep: run9.sh"; } >> "$OUT/gpu.txt"
echo "tesseract: $(command -v tesseract >/dev/null 2>&1 && tesseract --version 2>&1 | head -1 || echo MISSING)" >> "$OUT/gpu.txt"

SYN="benchmarks/lifecycle-synthetic-v1/steps.json"
RW="benchmarks/lifecycle-realworld-v1/steps.json"
NM="benchmarks/lifecycle-realworld-nearmiss-v1/steps.json"
HO="benchmarks/lifecycle-realworld-heldout-v1/steps.json"
for m in "$SYN" "$RW" "$NM"; do
    [ -f "$m" ] || { echo "FATAL: $m is missing - git checkout develop && git pull"; exit 1; }
done
have_heldout=0
if [ -f "$HO" ]; then
    have_heldout=1
else
    echo "held-out set: no $HO in this clone - the ho- columns are skipped"
fi

wanted() { [ -z "$ONLY" ] || [[ " $ONLY " == *" $1 "* ]]; }

column() {   # column <name> <result dir> <command...>
    local name="$1" dir="$2"; shift 2
    wanted "$name" || { echo "$name: skipped (RUN9_ONLY=$ONLY)"; return; }
    mkdir -p "$dir"
    echo; echo "=============== $name ==============="
    local t0=$SECONDS
    if "$@" --out-dir "$dir" > "$dir/$name.log" 2>&1; then
        echo "$name: OK ($((SECONDS - t0))s)"
        tail -1 "$dir/$name.log"           # the result row
    else
        echo "$name: FAILED ($((SECONDS - t0))s) - see $dir/$name.log"
        grep -m1 -E "Error|error:|FATAL" "$dir/$name.log" || true
    fi
}

RUN="python -m visual_dom.evaluation.lifecycle.runner"
VRAM_GB=$(python -c "import torch;print(int(torch.cuda.get_device_properties(0).total_memory/1e9))")
QUANT=""; [ "$VRAM_GB" -ge 20 ] && QUANT="--no-quantize"
if [ -x .venv-legacy/bin/python ]; then
    LEGACY=".venv-legacy/bin/python -m visual_dom.evaluation.lifecycle.runner"
else
    echo "!! .venv-legacy missing - the elam-7b columns will fail (run setup.sh)"
    LEGACY="$RUN"
fi

OLLAMA="${VIZDOM_OLLAMA_HOST:-http://localhost:11434}"
GMODEL="${VIZDOM_GROUNDING_MODEL:-qwen2.5:3b}"
GVISION="${VIZDOM_GROUNDING_VISION_MODEL:-qwen2.5vl:3b}"
GVISION_BIG="${VIZDOM_GROUNDING_VISION_MODEL_BIG:-qwen2.5vl:7b}"
OLLAMA_LOG="${VIZDOM_OLLAMA_LOG:-$HOME/ollama-serve.log}"
if command -v ollama >/dev/null 2>&1 && ! curl -fsS "$OLLAMA/api/tags" >/dev/null 2>&1; then
    (ollama serve >>"$OLLAMA_LOG" 2>&1 &); sleep 3
fi
have_ollama=0
curl -fsS "$OLLAMA/api/tags" >/dev/null 2>&1 && have_ollama=1
[ "$have_ollama" -eq 1 ] || echo "desc= columns: SKIPPED - Ollama not reachable at $OLLAMA (prefetch.sh installs it)"

DESC_OPTS="--grounding-host $OLLAMA --grounding-model $GMODEL --grounding-vision-model $GVISION"
YESNO="ui-tars-1.5-7b[verify=yesno]"

# --- VizDOM rows (minutes each) ---------------------------------------------
vizdom_rows() {   # vizdom_rows <prefix> <manifest> <result dir>
    local p="$1" m="$2" d="$3"
    column "$p-vizdom-modular" "$d" $RUN --manifest "$m" --executors vizdom-modular
    [ "$have_ollama" -eq 1 ] || return
    column "$p-desc"            "$d" $RUN --manifest "$m" --executors vizdom-modular+desc $DESC_OPTS \
        --grounding-tiers lexical,slm
    column "$p-desc-vlm7-chain" "$d" $RUN --manifest "$m" --executors vizdom-modular+desc $DESC_OPTS \
        --grounding-tiers lexical,vlm --grounding-vision-model "$GVISION_BIG"
}
vizdom_rows rw "$RW" "$OUT/realworld"
# The near-miss set has verify steps only, and a lexical-first chain verifies
# with the lexical scoring alone (ADR-022 1.9): lexical,slm and lexical,vlm
# give the same row there. What is worth a row is the old scoring, where the
# model tier may vouch for a caption: it shows what 1.9 keeps out.
column nm-vizdom-modular "$OUT/nearmiss" $RUN --manifest "$NM" --executors vizdom-modular
if [ "$have_ollama" -eq 1 ]; then
    column nm-desc "$OUT/nearmiss" $RUN --manifest "$NM" --executors vizdom-modular+desc $DESC_OPTS \
        --grounding-tiers lexical,slm
    column nm-desc-vlm7-verify-chain "$OUT/nearmiss" $RUN --manifest "$NM" --executors vizdom-modular+desc $DESC_OPTS \
        --grounding-tiers lexical,vlm --grounding-vision-model "$GVISION_BIG" --desc-verify chain
fi
[ "$have_heldout" -eq 1 ] && vizdom_rows ho "$HO" "$OUT/heldout"
if [ "$have_ollama" -eq 1 ]; then
    column syn-desc            "$OUT" $RUN --manifest "$SYN" --executors vizdom-modular+desc $DESC_OPTS \
        --grounding-tiers lexical,slm
    column syn-desc-vlm7-chain "$OUT" $RUN --manifest "$SYN" --executors vizdom-modular+desc $DESC_OPTS \
        --grounding-tiers lexical,vlm --grounding-vision-model "$GVISION_BIG"
fi

# --- UI-TARS-1.5: the proxy verdict and the yes/no verdict (about 1 s a step)
# One process per column: two adapters in one process would hold the 16 GB
# weights twice. On the real-application set only the verify steps run (the
# clicks are run 8's, same weights and prompt); the proxy row is repeated
# there so the two verdict modes are compared on one card.
column nm-ui-tars-1.5-7b "$OUT/nearmiss"  $RUN --manifest "$NM" --executors ui-tars-1.5-7b $QUANT
column nm-ui-tars-yesno  "$OUT/nearmiss"  $RUN --manifest "$NM" --executors "$YESNO"       $QUANT
column rw-ui-tars-1.5-7b "$OUT/realworld" $RUN --manifest "$RW" --executors ui-tars-1.5-7b $QUANT --kinds verify
column rw-ui-tars-yesno  "$OUT/realworld" $RUN --manifest "$RW" --executors "$YESNO"       $QUANT --kinds verify
if [ "$have_heldout" -eq 1 ]; then
    column ho-ui-tars-1.5-7b "$OUT/heldout" $RUN --manifest "$HO" --executors ui-tars-1.5-7b $QUANT
    column ho-ui-tars-yesno  "$OUT/heldout" $RUN --manifest "$HO" --executors "$YESNO"       $QUANT --kinds verify
fi
column syn-ui-tars-yesno "$OUT" $RUN --manifest "$SYN" --executors "$YESNO" $QUANT --kinds verify

# --- ELAM-7B, official verdict rule (about 5 s a step: the long columns) -----
column nm-elam-7b "$OUT/nearmiss"  $LEGACY --manifest "$NM" --executors elam-7b $QUANT
column rw-elam-7b "$OUT/realworld" $LEGACY --manifest "$RW" --executors elam-7b $QUANT --kinds verify
[ "$have_heldout" -eq 1 ] && \
    column ho-elam-7b "$OUT/heldout" $LEGACY --manifest "$HO" --executors elam-7b $QUANT
column syn-elam-7b "$OUT" $LEGACY --manifest "$SYN" --executors elam-7b $QUANT --kinds verify

# --- one table per set with every column that produced a result -------------
summarize() {   # summarize <dir>: summary.md of the latest row per executor
    local dir="$1"
    [ -d "$dir" ] || return
{
    echo "# $(basename "$OUT")$([ "$dir" != "$OUT" ] && echo " - $(basename "$dir")")"
    echo; cat "$OUT/gpu.txt"; echo
    echo "A row with action-hit None (0) ran the verify steps only (--kinds verify)."
    echo
    echo "| executor | action-hit | verify acc | false-pass | median step (s) | cost |"
    echo "|---|---|---|---|---|---|"
    for md in $(ls "$dir"/*_*.md 2>/dev/null | sort); do
        awk 'NR > 2' "$md"
    done | awk -F'|' '{
        k = $2
        if (!(k in row)) order[++n] = k
        row[k] = $0
    } END { for (i = 1; i <= n; i++) print row[order[i]] }'
} > "$dir/summary.md"
echo; cat "$dir/summary.md"
}
summarize "$OUT"
summarize "$OUT/realworld"
summarize "$OUT/nearmiss"
summarize "$OUT/heldout"

[ -f "$OLLAMA_LOG" ] && cp "$OLLAMA_LOG" "$OUT/ollama-serve.log"
tar czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
echo; echo "run 9 complete: $OUT.tar.gz"
echo "copy it back, verify it opens, then DESTROY THE RENTAL."
