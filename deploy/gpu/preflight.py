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
    ap.add_argument("--grounding", action="store_true",
                    help="check the desc= columns: Ollama reachable, the slm and "
                         "vlm tiers each resolve one description")
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
        # Every grounder runs bf16 on a big card (what the sweep does). Aria-UI
        # too: bnb leaves its MoE experts unquantized, so 4-bit buys nothing
        # and the column needs an 80 GB card either way (its available() gates).
        quantize = not big_card
        grounder = cls(quantize=quantize)
        ok, why = grounder.available()
        if not ok:
            # SKIP only for the one reason the sweep also skips on: the card is
            # below the adapter's own VRAM floor (Aria-UI below 80 GB). Anything
            # else - a missing package, no CUDA - is a FAIL: the sweep would
            # otherwise exit "not runnable here" after the time is paid for.
            if torch.cuda.is_available() and vram_gb < getattr(cls, "MIN_VRAM_GB", 0):
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
        # The OCR stage's second engine (ADR-012): runs 1-6 silently had none
        # on Linux, so a VizDOM column measured without it must fail here.
        from visual_dom.adapters.outbound.ocr.text_detector import find_tesseract
        tess = find_tesseract()
        if tess:
            print(f"  {'tesseract':16} OK    {tess}")
        else:
            failures.append("tesseract")
            print(f"  {'tesseract':16} FAIL  no binary on PATH - apt-get install -y tesseract-ocr "
                  "(setup.sh does this); without it ocr.retry_low_confidence is a no-op")
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

    if args.grounding:
        failures += preflight_grounding(images)

    sys.exit(1 if failures else 0)


def _label_for(image_path):
    """<root>/images/<state>.png -> <root>/labels/<state>.json (os.path, not a
    string replace: the glob yields backslashes on Windows)."""
    stem = os.path.splitext(os.path.basename(image_path))[0]
    return os.path.join(os.path.dirname(os.path.dirname(image_path)), "labels", stem + ".json")


def preflight_grounding(images):
    """
    The desc= columns (ADR-022) resolve against the DOM through Ollama. Build
    the DOM from a screen's ground-truth label (no detector needed here) and
    ask each model tier, pinned alone, to resolve one description. SKIP when
    Ollama is absent - run_benchmarks.sh skips those columns too; FAIL when it
    runs but a model is missing or a tier cannot answer, because then the
    sweep would pay for a FAILED column.
    """
    import json
    from visual_dom.evaluation.lifecycle.runner import VizDomDescExecutor

    # the first screen whose label has a captioned button (dashboards have none)
    dom = target = image = None
    for image_path in images:
        try:
            gt = json.load(open(_label_for(image_path), encoding="utf-8"))
        except OSError:
            continue
        elements = [{"id": e["id"], "role": e.get("visual_type"),
                     "visual_type": e.get("visual_type"),
                     "text": e.get("ocr_text") or "", "bounds": e["bounds"]}
                    for e in gt.get("elements", [])]
        target = next((e for e in elements
                       if e["visual_type"] == "button" and e["text"].strip()), None)
        if target is not None:
            dom = {"image_size": gt.get("image_size"), "elements": elements}
            image = cv2.imread(image_path)
            break
    if target is None:
        print(f"  {'desc=':16} SKIP  no screen with a label and a captioned button "
              f"(needs data/synthetic/test/{{images,labels}})")
        return []
    description = f"{target['text'].strip()} button"
    print(f"  desc= probe: {description!r} on {os.path.basename(image_path)} "
          f"({len(dom['elements'])} GT elements)")

    failures = []
    for tier in ("slm", "vlm"):
        column = f"desc[{tier}]"
        ex = VizDomDescExecutor(
            detector="modular", tiers=[tier],
            host=os.environ.get("VIZDOM_OLLAMA_HOST", VizDomDescExecutor.DEFAULT_HOST),
            model=os.environ.get("VIZDOM_GROUNDING_MODEL", VizDomDescExecutor.DEFAULT_MODEL),
            vision_model=os.environ.get("VIZDOM_GROUNDING_VISION_MODEL",
                                        VizDomDescExecutor.DEFAULT_VISION_MODEL))
        ok, why = ex.available()
        if not ok:
            if "not reachable" in why:
                print(f"  {column:16} SKIP  {why}")
            else:
                failures.append(column)
                print(f"  {column:16} FAIL  {why}")
            continue
        try:
            from visual_gui_library.locators.desc_resolver import DescriptionResolver
            resolver = DescriptionResolver(dom, screenshot=image, tiers=[tier],
                                           backend=ex.backend, model=ex.model,
                                           vision_model=ex.vision_model, host=ex.host)
            t0 = time.perf_counter()
            elem, info = resolver.resolve(description)
            dt = time.perf_counter() - t0
            reason = str(info.get("reason", ""))
            if "unavailable" in reason or "unparseable" in reason:
                raise RuntimeError(reason)
            got = elem.get("id") if elem else None
            verdict = "hit" if got == target["id"] else ("miss" if elem else "no match")
            print(f"  {column:16} OK    {description!r} -> {got} ({verdict}, "
                  f"GT {target['id']}; {ex.model if tier == 'slm' else ex.vision_model}, "
                  f"{dt:.1f}s incl. model load)")
        except Exception as exc:
            failures.append(column)
            print(f"  {column:16} FAIL  {type(exc).__name__}: {exc}")
    return failures


if __name__ == "__main__":
    main()
