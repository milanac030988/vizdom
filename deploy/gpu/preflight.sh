#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-minute sanity BEFORE the long sweep: load each grounder and ground ONE
# instruction on one benchmark image. A broken adapter fails here, in minute
# one - not two hours into paid GPU time.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
. .venv/bin/activate
export PYTHONPATH=src

python - <<'PY'
import glob
import sys

import cv2

from visual_dom.evaluation.lifecycle.grounders import GROUNDERS

images = sorted(glob.glob("benchmarks/lifecycle-synthetic-v1/**/*.png", recursive=True)) \
    or sorted(glob.glob("tests/samples/*.png"))
assert images, "no benchmark image found"
image = cv2.imread(images[0])
print(f"preflight image: {images[0]} ({image.shape[1]}x{image.shape[0]})")

failures = []
for name, cls in GROUNDERS.items():
    grounder = cls()
    ok, why = grounder.available()
    if not ok:
        print(f"  {name:16} SKIP: {why}")
        continue
    try:
        point = grounder.ground(image, "click the first button")
        print(f"  {name:16} OK    ground -> {point}  "
              f"(load+infer {getattr(grounder, 'last_seconds', '?')}s)")
    except Exception as exc:
        failures.append(name)
        print(f"  {name:16} FAIL  {type(exc).__name__}: {exc}")

# the vizdom side: one pipeline pass with the omniparser weights
try:
    from visual_dom.core.domain.pipeline import VisualDOMPipeline
    import os
    os.environ.setdefault("OMNIPARSER_ROOT", "third_party/OmniParser")
    os.environ.setdefault("OMNIPARSER_ICON_DETECT", "models/omniparser/icon_detect/model.pt")
    os.environ.setdefault("OMNIPARSER_ICON_CAPTION", "models/omniparser/icon_caption_florence")
    pipe = VisualDOMPipeline(ocr_engine="easyocr", detector="omniparser", use_gpu=True)
    result = pipe.process(image)
    print(f"  vizdom-omniparser OK    {result['stats']['final_count']} elements")
except Exception as exc:
    failures.append("vizdom-omniparser")
    print(f"  vizdom-omniparser FAIL  {type(exc).__name__}: {exc}")

sys.exit(1 if failures else 0)
PY
echo "preflight passed. Next: bash deploy/gpu/run_benchmarks.sh"
