#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Run 10: the ScreenVLM column (another whole-screen parser) on a rented card.
#
# ScreenVLM (316 M parameters, trained on the ScreenParse web-page set) is run
# under the VizDOM contract: one parse per state, steps resolved from the
# parsed elements by the same element finder (lifecycle/parsers.py). It was
# first measured on a 6 GB laptop GPU (benchmarks/README.md, 2026-11-15) at
# about 14 tokens/s. This sweep repeats it on the card the other columns ran
# on and adds what the laptop run did not have:
#
#   1. the four sets (held-out, synthetic, real-application, near-miss), both
#      column variants, with every parsed DOM kept in the tarball;
#   2. a second parse of the held-out screens: are two parses of one screen
#      the same text? (on the laptop the output changed with the precision)
#   3. the detection table on the synthetic test screens, next to VizDOM when
#      its row is run here too;
#   4. with SV_WITH_VIZDOM=1 and the main environment present (setup.sh,
#      prefetch.sh): the vizdom-modular rows of the same four sets at this
#      commit, so both parsers are timed on one machine.
#
# Small rental: the checkpoint is 0.75 GB and fits any card of 8 GB or more;
# 30 GB of disk is enough without the VizDOM rows. The script builds its own
# environment (.venv-parser, transformers 4.55.2: the main environment's 4.49
# cannot prepare this model's images), so setup.sh is NOT needed for 1 to 3.
#
#   git clone <repo> && cd <repo> && git checkout develop
#   tmux new -s run10
#   bash deploy/gpu/run10.sh
#   RUN10_ONLY="smoke" bash deploy/gpu/run10.sh               # 2-minute check first
#   RUN10_ONLY="rw nm" OUT_DIR=benchmarks/results/gpu-<stamp> bash deploy/gpu/run10.sh
#
# Steps (RUN10_ONLY names): smoke ho syn rw nm repeat vizdom detection
# Parsed DOMs are reused when a step is rerun into the same OUT_DIR.
# ---------------------------------------------------------------------------
set -uo pipefail   # NOT -e: one failed step must not kill the sweep
cd "$(dirname "$0")/../.."
export PYTHONPATH=src
export USE_TF=0
export PATH="$HOME/.local/bin:$PATH"

OUT="${OUT_DIR:-benchmarks/results/gpu-$(date +%Y%m%d_%H%M%S)}"
OUT="${OUT%/}"
ONLY="${RUN10_ONLY:-}"
COLUMNS='screenvlm,screenvlm[pick=first]'
REVISION="78df0cc8498bbea1a03eb2816056fc0a76d2f63d"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/sweep.log") 2>&1
echo "run 10 -> $OUT   (steps: ${ONLY:-all})"

nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > "$OUT/gpu.txt" || {
    echo "FATAL: no NVIDIA driver visible"; exit 1; }
{ echo "commit: $(git rev-parse --short HEAD 2>/dev/null)"; date -u; echo "sweep: run10.sh"; } >> "$OUT/gpu.txt"

SYN="benchmarks/lifecycle-synthetic-v1/steps.json"
RW="benchmarks/lifecycle-realworld-v1/steps.json"
NM="benchmarks/lifecycle-realworld-nearmiss-v1/steps.json"
HO="benchmarks/lifecycle-realworld-heldout-v1/steps.json"
for m in "$SYN" "$RW" "$NM" "$HO"; do
    [ -f "$m" ] || { echo "FATAL: $m is missing - git checkout develop && git pull"; exit 1; }
done

# --- environment: .venv-parser (built once, about 3 minutes) -----------------
PY="${PARSER_PY:-.venv-parser/bin/python}"   # PARSER_PY: an environment that is already there
if [ ! -x "$PY" ]; then
    echo "=== building .venv-parser ==="
    command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
    # the same wheel choice as setup.sh: Blackwell cards need cu128
    COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
    CUDA_INDEX="https://download.pytorch.org/whl/cu126"
    case "$COMPUTE_CAP" in 12.*|10.*) CUDA_INDEX="https://download.pytorch.org/whl/cu128" ;; esac
    uv python install 3.12 && uv venv --python 3.12 .venv-parser \
        && VIRTUAL_ENV="$(pwd)/.venv-parser" uv pip install torch torchvision --index-url "$CUDA_INDEX" \
        && VIRTUAL_ENV="$(pwd)/.venv-parser" uv pip install -r requirements.txt "huggingface_hub[cli]" \
        && VIRTUAL_ENV="$(pwd)/.venv-parser" uv pip install "transformers==4.55.2" \
        || { echo "FATAL: could not build .venv-parser"; exit 1; }
fi
"$PY" - <<'PY' | tee -a "$OUT/gpu.txt" || { echo "FATAL: .venv-parser is not usable"; exit 1; }
import torch, transformers
assert torch.cuda.is_available(), "torch sees no CUDA - wrong wheel or driver"
from visual_dom.evaluation.lifecycle.parsers import ScreenVlmParser
ok, reason = ScreenVlmParser().available()
assert ok, reason
print(f"parser env: torch {torch.__version__}, transformers {transformers.__version__}, {reason}")
PY

echo "=== checkpoint (0.75 GB) ==="
"$PY" -c "from huggingface_hub import snapshot_download; print(snapshot_download('docling-project/ScreenVLM', revision='$REVISION'))" \
    || { echo "FATAL: checkpoint download failed"; exit 1; }

wanted() { [ -z "$ONLY" ] || [[ " $ONLY " == *" $1 "* ]]; }
RUN="$PY -m visual_dom.evaluation.lifecycle.runner"

column() {   # column <name> <result dir> <command...>
    local name="$1" dir="$2"; shift 2
    mkdir -p "$dir"
    echo; echo "=============== $name ==============="
    local t0=$SECONDS
    if "$@" --out-dir "$dir" > "$dir/$name.log" 2>&1; then
        echo "$name: OK ($((SECONDS - t0))s)"
        grep -E "^\| " "$dir/$name.log" | tail -n +3      # the result rows
    else
        echo "$name: FAILED ($((SECONDS - t0))s) - see $dir/$name.log"
        grep -m1 -E "Error|error:|FATAL" "$dir/$name.log" || true
    fi
}

parse_stats() {   # parse_stats <dom dir>: tokens, speed and cut-off outputs of a set
    "$PY" - "$1" <<'PY'
import json, sys
from pathlib import Path
doms = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(sys.argv[1]).glob("*.json"))]
ps = [d["parser"] for d in doms if d.get("parser", {}).get("seconds")]
if ps:
    tokens, seconds = sum(p["new_tokens"] for p in ps), sum(p["seconds"] for p in ps)
    print(f"  {Path(sys.argv[1]).name}: {len(ps)} parses, {tokens} tokens in {seconds:.0f} s = "
          f"{tokens / seconds:.1f} tokens/s, mean {seconds / len(ps):.1f} s a screen, "
          f"cut at the token limit {sum(bool(p['truncated']) for p in ps)}, "
          f"elements {sum(d['element_count'] for d in doms)}")
PY
}

# --- smoke: one synthetic screen, before the meter runs for hours ------------
if wanted smoke; then
    column smoke "$OUT/smoke" $RUN --manifest "$SYN" --executors screenvlm --limit-states 1 \
        --parser-doms "$OUT/smoke/doms"
    parse_stats "$OUT/smoke/doms" || true
    if ! ls "$OUT"/smoke/doms/*.json >/dev/null 2>&1; then
        echo "FATAL: the smoke parse produced nothing - fix this before the sweep"; exit 1
    fi
    echo "want: a row with action-hit above 0 and a speed well above the laptop's 14 tokens/s"
fi

# --- the four sets (short ones first; near-miss reuses the real-world parses)
wanted ho  && column ho-screenvlm  "$OUT/heldout"   $RUN --manifest "$HO"  --executors "$COLUMNS" --parser-doms "$OUT/doms/heldout"
wanted syn && column syn-screenvlm "$OUT/synthetic" $RUN --manifest "$SYN" --executors "$COLUMNS" --parser-doms "$OUT/doms/synthetic"
wanted rw  && column rw-screenvlm  "$OUT/realworld" $RUN --manifest "$RW"  --executors "$COLUMNS" --parser-doms "$OUT/doms/realworld"
wanted nm  && column nm-screenvlm  "$OUT/nearmiss"  $RUN --manifest "$NM"  --executors "$COLUMNS" --parser-doms "$OUT/doms/realworld"

# --- are two parses of one screen the same? (held-out, 14 screens) -----------
if wanted repeat; then
    column ho-screenvlm-repeat "$OUT/repeat" $RUN --manifest "$HO" --executors screenvlm \
        --parser-doms "$OUT/doms/heldout-repeat"
    "$PY" - "$OUT/doms/heldout" "$OUT/doms/heldout-repeat" <<'PY' | tee "$OUT/repeat/same_output.txt"
import json, sys
from pathlib import Path
a, b = Path(sys.argv[1]), Path(sys.argv[2])
names = sorted(p.name for p in a.glob("*.json") if (b / p.name).is_file())
raw = lambda d, n: json.loads((d / n).read_text(encoding="utf-8"))["parser"]["raw"]
differ = [n for n in names if raw(a, n) != raw(b, n)]
print(f"second parse: {len(names) - len(differ)} of {len(names)} screens gave the same text"
      + (f"; different: {', '.join(n[:-5] for n in differ)}" if differ else ""))
PY
fi

# --- optional: the VizDOM rows on this card (needs setup.sh + prefetch.sh) ---
VIZ_SYN_DOMS=""
if wanted vizdom && [ "${SV_WITH_VIZDOM:-0}" = "1" ]; then
    if [ -x .venv/bin/python ]; then
        export OMNIPARSER_ROOT="${OMNIPARSER_ROOT:-$(pwd)/third_party/OmniParser}"
        export OMNIPARSER_ICON_DETECT="${OMNIPARSER_ICON_DETECT:-$(pwd)/models/omniparser/icon_detect/model.pt}"
        export OMNIPARSER_ICON_CAPTION="${OMNIPARSER_ICON_CAPTION:-$(pwd)/models/omniparser/icon_caption_florence}"
        VRUN=".venv/bin/python -m visual_dom.evaluation.lifecycle.runner"
        column ho-vizdom-modular  "$OUT/heldout"   $VRUN --manifest "$HO"  --executors vizdom-modular
        column syn-vizdom-modular "$OUT/synthetic" $VRUN --manifest "$SYN" --executors vizdom-modular
        column rw-vizdom-modular  "$OUT/realworld" $VRUN --manifest "$RW"  --executors vizdom-modular
        column nm-vizdom-modular  "$OUT/nearmiss"  $VRUN --manifest "$NM"  --executors vizdom-modular
        VIZ_SYN_DOMS=$(ls -d "$OUT"/synthetic/*-doms/vizdom-modular 2>/dev/null | tail -1)
    else
        echo "vizdom rows: SKIPPED - no .venv (bash deploy/gpu/setup.sh && bash deploy/gpu/prefetch.sh)"
    fi
fi

# --- detection on the synthetic test screens --------------------------------
if wanted detection && ls "$OUT"/doms/synthetic/*.json >/dev/null 2>&1; then
    echo; echo "=============== detection (synthetic test, IoU >= 0.5) ==============="
    ROWS=("screenvlm=$OUT/doms/synthetic")
    [ -n "$VIZ_SYN_DOMS" ] && ROWS=("vizdom-modular=$VIZ_SYN_DOMS" "${ROWS[@]}")
    "$PY" -m visual_dom.evaluation.lifecycle.parsers score --labels data/synthetic/test/labels \
        --doms "${ROWS[@]}" --out "$OUT/detection.md" || echo "detection: FAILED"
fi

# --- one summary -------------------------------------------------------------
{
    echo "# $(basename "$OUT") - ScreenVLM column (run 10)"
    echo; cat "$OUT/gpu.txt"; echo
    echo "A row with action-hit None (0) is the near-miss set: verify steps only."
    for set in heldout synthetic realworld nearmiss; do
        ls "$OUT/$set"/*_*.md >/dev/null 2>&1 || continue
        echo; echo "## $set"; echo
        echo "| executor | action-hit | verify acc | false-pass | median step (s) | cost |"
        echo "|---|---|---|---|---|---|"
        for md in $(ls "$OUT/$set"/*_*.md | sort); do awk 'NR > 2' "$md"; done | awk -F'|' '{
            k = $2
            if (!(k in row)) order[++n] = k
            row[k] = $0
        } END { for (i = 1; i <= n; i++) print row[order[i]] }'
    done
    echo; echo "## Parsing"; echo; echo '```'
    for d in "$OUT"/doms/*/; do [ -d "$d" ] && parse_stats "${d%/}"; done
    [ -f "$OUT/repeat/same_output.txt" ] && cat "$OUT/repeat/same_output.txt"
    echo '```'
    [ -f "$OUT/detection.md" ] && { echo; echo "## Detection (synthetic test)"; echo; cat "$OUT/detection.md"; }
} > "$OUT/summary.md"
echo; cat "$OUT/summary.md"

if tar czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"; then
    echo; echo "run 10 complete: $OUT.tar.gz"
    echo "copy it back, verify it opens, then DESTROY THE RENTAL."
else
    echo; echo "run 10 finished but the tarball FAILED - copy the folder $OUT itself"
fi
