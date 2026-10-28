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
# The OCR stage's second engine: runs 1-6 had none (ADR-012 1.1), so every
# VizDOM row of a run must say whether it was there.
echo "tesseract: $(command -v tesseract >/dev/null 2>&1 && tesseract --version 2>&1 | head -1 || echo MISSING)" >> "$OUT/gpu.txt"

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

# --- the desc= columns (ADR-022: VizDOM's language tier over the same DOM) --
# Same parse-once DOM as vizdom-modular; each step resolves the auto-generated
# description ("Save button") instead of text="Save". Three chains: the
# production default (lexical -> slm), and each model tier pinned alone -
# that is the head-to-head with the grounders, both sides then resolve
# language (VizDOM over its DOM candidates via Set-of-Mark, the grounders over
# raw pixels). Needs Ollama with the two small models (prefetch.sh installs
# and pulls them); when it is not reachable the columns are skipped, not
# failed. VIZDOM_GROUNDING_MODEL / VIZDOM_GROUNDING_VISION_MODEL override the
# 3B defaults (e.g. qwen2.5vl:7b on a big card) - keep prefetch.sh in sync.
# Run 4 (2026-10-27) showed the vlm tier pinned ALONE is a harness limit, not
# a model result: the Set-of-Mark overlay caps at 20 marks in DOM order and
# without the lexical shortlist in front fewer than half the targets are among
# them. The -vlm-chain column runs the vision tier the way production does,
# behind the lexical scoring; -desc-vlm is kept for the comparison.
DESC_COLUMNS="vizdom-modular-desc vizdom-modular-desc-slm vizdom-modular-desc-vlm vizdom-modular-desc-vlm-chain"
OLLAMA="${VIZDOM_OLLAMA_HOST:-http://localhost:11434}"
GMODEL="${VIZDOM_GROUNDING_MODEL:-qwen2.5:3b}"
GVISION="${VIZDOM_GROUNDING_VISION_MODEL:-qwen2.5vl:3b}"
desc_wanted=0; for c in $DESC_COLUMNS; do wanted "$c" && desc_wanted=1; done
# The server's own log goes into the tarball: runs 4-6 each lost a block of
# VLM calls to "Ollama error: 500" and the log that would have said why was
# sent to /dev/null (prefetch.sh writes to the same file when it starts the
# server first).
OLLAMA_LOG="${VIZDOM_OLLAMA_LOG:-$HOME/ollama-serve.log}"
if [ "$desc_wanted" -eq 1 ]; then
    if command -v ollama >/dev/null 2>&1 && ! curl -fsS "$OLLAMA/api/tags" >/dev/null 2>&1; then
        (ollama serve >>"$OLLAMA_LOG" 2>&1 &); sleep 3
    fi
    if curl -fsS "$OLLAMA/api/tags" >/dev/null 2>&1; then
        DESC="$RUN --manifest $MANIFEST --executors vizdom-modular+desc --out-dir $OUT
              --grounding-host $OLLAMA --grounding-model $GMODEL --grounding-vision-model $GVISION"
        run_column vizdom-modular-desc     $DESC --grounding-tiers lexical,slm
        run_column vizdom-modular-desc-slm $DESC --grounding-tiers slm
        run_column vizdom-modular-desc-vlm $DESC --grounding-tiers vlm
        run_column vizdom-modular-desc-vlm-chain $DESC --grounding-tiers lexical,vlm
    else
        echo "desc= columns: SKIPPED - Ollama not reachable at $OLLAMA (prefetch.sh installs it and pulls $GMODEL + $GVISION)"
    fi
fi

# --- the stage ablation (benchmarks/README.md sec. 7) ----------------------
# Modular detector held fixed, one stage of VizDOM's own pipeline off per
# column, scored on both levels; the driver writes ablation-<stamp>.json into
# the run dir after every column and keeps going past a failed one (the
# refiner=on column needs the Ollama server started above). About 20 min.
ABLATION_COLUMNS="${VIZDOM_ABLATION_COLUMNS:-modular,modular[roles=off],modular[labels=off],modular[symbols=off],modular[merge=off],modular[ocr=plain],modular[ocr=none],modular[refiner=on],modular+desc,modular[roles=off]+desc,modular[labels=off]+desc}"
run_column ablation python -m visual_dom.evaluation.lifecycle.ablation \
    --manifest "$MANIFEST" --out-dir "$OUT" --columns "$ABLATION_COLUMNS"
wanted ablation && python -m visual_dom.evaluation.lifecycle.ablation --report --out-dir "$OUT" > /dev/null 2>&1 || true

# --- the grounder columns (the competing end-to-end paradigm) --------------
# 7B grounders run in bf16 on a >= 20 GB card (the 4-bit path exists for the
# laptop; Molmo/ELAM under bnb 4-bit fails with a Float/Half dtype error).
VRAM_GB=$(python -c "import torch;print(int(torch.cuda.get_device_properties(0).total_memory/1e9))")
QUANT=""; [ "$VRAM_GB" -ge 20 ] && QUANT="--no-quantize"
# ELAM (Molmo code) and Aria-UI (old Llama attention) need transformers
# <= 4.47/4.48, which UI-TARS (Qwen2.5-VL, >= 4.49) cannot share: setup.sh
# builds .venv-legacy for them. Aria-UI runs bf16 only (the model card's
# recipe; ~50 GB of weights - bnb leaves its MoE experts unquantized, so
# 24 GB OOMs at shard 5/12 and the ~53 GB extrapolation does not fit a
# 48 GB card either). It needs an 80 GB card (A100 80 / H100, which report
# ~85); gate 70, same as AriaUiGrounder.MIN_VRAM_GB - on a smaller card the
# column is skipped here rather than paid for and then marked FAILED.
# VIZDOM_ARIA_OFFLOAD=1 (>= 40 GB card) opts into the experimental offload
# mode instead: the adapter spills the last layers to host RAM. Same rule as
# AriaUiGrounder._offload_requested: empty or 0 is OFF, and the 40 GB floor
# applies here too, so a card the adapter would refuse is not paid for.
aria_offload() {
    case "$(printf '%s' "${VIZDOM_ARIA_OFFLOAD:-}" | tr -d '[:space:]')" in
        ""|0) return 1 ;;
        *)    [ "$VRAM_GB" -ge 40 ] ;;
    esac
}
[ "$VRAM_GB" -ge 70 ] || aria_offload || ONLY="${ONLY:-vizdom-uied vizdom-omniparser vizdom-modular $DESC_COLUMNS ablation elam-7b ui-tars-1.5-7b parity}"
if [ -x .venv-legacy/bin/python ]; then
    LEGACY=".venv-legacy/bin/python -m visual_dom.evaluation.lifecycle.runner"
else
    echo "!! .venv-legacy missing - elam-7b / aria-ui will fail (run setup.sh)"
    LEGACY="$RUN"
fi
run_column elam-7b            $LEGACY --manifest "$MANIFEST" --executors elam-7b        $QUANT --out-dir "$OUT"
run_column ui-tars-1.5-7b     $RUN    --manifest "$MANIFEST" --executors ui-tars-1.5-7b $QUANT --out-dir "$OUT"
run_column aria-ui            $LEGACY --manifest "$MANIFEST" --executors aria-ui        $QUANT --out-dir "$OUT"

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

[ -f "$OLLAMA_LOG" ] && cp "$OLLAMA_LOG" "$OUT/ollama-serve.log"
tar czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
echo; echo "sweep complete: $OUT.tar.gz"
echo "copy it back, verify it opens, then DESTROY THE RENTAL."
