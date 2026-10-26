"""
Preflight one environment: load the named grounders, ground ONE instruction and
(where the adapter has it) judge ONE statement on one benchmark image; then,
with --pipeline, run one VizDOM pass with the omniparser and the modular
backend.

Called by preflight.sh once per venv (the grounders' Hub code disagrees on the
transformers version, so the sweep uses two envs - see setup.sh). Exit 1 on any
failure. A "FAIL" here costs a minute; the same failure inside the sweep costs
a paid hour and a column of zeros that looks like a result.

    python deploy/gpu/preflight.py --grounders ui-tars-1.5-7b --pipeline
    .venv-legacy/bin/python deploy/gpu/preflight.py --grounders elam-7b,aria-ui
"""

import argparse
import glob
import os
import sys
import time

import cv2

from visual_dom.evaluation.lifecycle.grounders import GROUNDERS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grounders", default="", help="comma list; empty = none")
    ap.add_argument("--pipeline", action="store_true",
                    help="also run one VizDOM pass with the omniparser and modular backends")
    args = ap.parse_args()

    # The manifest's screens are tracked under data/synthetic (tests/samples/*.png
    # is gitignored, so a fresh clone has none of those).
    images = sorted(glob.glob("data/synthetic/test/images/*.png")) \
        or sorted(glob.glob("tests/samples/*.png"))
    assert images, "no benchmark image found"
    image = cv2.imread(images[0])
    print(f"preflight image: {images[0]} ({image.shape[1]}x{image.shape[0]})  "
          f"[{sys.executable}]")

    import torch
    vram_gb = int(torch.cuda.get_device_properties(0).total_memory / 1e9) \
        if torch.cuda.is_available() else 0
    big_card = vram_gb >= 20          # same rule as run_benchmarks.sh / prefetch.sh

    failures = []
    for name in [n.strip() for n in args.grounders.split(",") if n.strip()]:
        cls = GROUNDERS.get(name)
        if cls is None:
            failures.append(name)
            print(f"  {name:16} FAIL  unknown grounder (known: {sorted(GROUNDERS)})")
            continue
        # 7B models run bf16 on a big card (what the sweep does); Aria stays 4-bit.
        quantize = not big_card or name == "aria-ui"
        grounder = cls(quantize=quantize)
        ok, why = grounder.available()
        if not ok:
            # SKIP only for the one reason the sweep also skips on: the card is
            # below the adapter's own VRAM floor (Aria-UI on 24 GB). Anything
            # else - a missing package, no CUDA - is a FAIL: the sweep would
            # otherwise exit "not runnable here" after the time is paid for.
            if vram_gb < getattr(cls, "MIN_VRAM_GB", 0):
                print(f"  {name:16} SKIP  {why}")
            else:
                failures.append(name)
                print(f"  {name:16} FAIL  not available: {why}")
            continue
        try:
            t0 = time.perf_counter()
            point = grounder.ground(image, "click the first button")
            load_s = time.perf_counter() - t0
            if point is None:
                raise RuntimeError("model loaded but produced no point - prompt "
                                   "template or point parser is off (see the INFO "
                                   "line above for the raw answer)")
            h, w = image.shape[:2]
            if not (0 <= point[0] <= w and 0 <= point[1] <= h):
                raise RuntimeError(f"point {point} is outside the {w}x{h} image - "
                                   "coordinate scale is off")
            msg = f"ground -> {point} ({'4-bit' if quantize else 'bf16'}, " \
                  f"load+infer {load_s:.0f}s, infer {grounder.last_latency:.1f}s)"
            # Adapters with a native verdict mode must also return a verdict.
            if name == "elam-7b":
                verdict = grounder.judge(image, "a button is visible")
                if verdict not in ("PASSED", "FAILED"):
                    raise RuntimeError(f"judge returned {verdict!r}, expected "
                                       "PASSED/FAILED - verdict prompt/parser is off")
                msg += f", judge -> {verdict}"
            print(f"  {name:16} OK    {msg}")
        except Exception as exc:
            failures.append(name)
            print(f"  {name:16} FAIL  {type(exc).__name__}: {exc}")
        finally:
            # free the card for the next model (Aria-UI needs most of it)
            grounder._model = None
            grounder._processor = None
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    if args.pipeline:
        from visual_dom.core.domain.pipeline import VisualDOMPipeline
        os.environ.setdefault("OMNIPARSER_ROOT", "third_party/OmniParser")
        os.environ.setdefault("OMNIPARSER_ICON_DETECT",
                              "models/omniparser/icon_detect/model.pt")
        os.environ.setdefault("OMNIPARSER_ICON_CAPTION",
                              "models/omniparser/icon_caption_florence")
        # Both OmniParser-backed columns of the sweep: the monolith and the
        # modular backend (same YOLO as stage 1). Each can silently degrade -
        # the pipeline to UIED when the backend fails to construct, the
        # modular backend's stage 1 to UIED when the YOLO is unusable - and
        # for a preflight that is a failure, not a pass (see the WARNING).
        for detector in ("omniparser", "modular"):
            column = f"vizdom-{detector}"
            try:
                pipe = VisualDOMPipeline(ocr_engine="easyocr", detector=detector,
                                         use_gpu=True)
                backend = pipe._primary_backend
                assert backend is not None, \
                    f"{detector} backend did not initialize - pipeline fell back to uied"
                if detector == "modular":
                    stage1 = getattr(getattr(backend, "_proposer", None), "name", None)
                    assert stage1 == "omniparser", \
                        f"modular stage 1 is {stage1!r}, not the omniparser YOLO"
                result = pipe.process(image)
                print(f"  {column:16} OK    {result['stats']['final_count']} elements")
            except Exception as exc:
                failures.append(column)
                print(f"  {column:16} FAIL  {type(exc).__name__}: {exc}")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
