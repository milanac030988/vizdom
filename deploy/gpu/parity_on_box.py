"""
ADR-027 combos on the rented GPU: parity re-check + the Qwen2-VL captioner
combo (trigger condition 2), written to the file given as argv[1].

Reuses the reference screens shipped in tests/samples plus any session
screenshots present. Latency per stage is the number that matters here -
the captioner combo lives or dies on caption throughput (Florence-2 batches
128 crops; an Ollama VLM is per-crop).
"""

import glob
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ.setdefault("OMNIPARSER_ROOT", os.path.abspath("third_party/OmniParser"))
os.environ.setdefault("OMNIPARSER_ICON_DETECT",
                      os.path.abspath("models/omniparser/icon_detect/model.pt"))
os.environ.setdefault("OMNIPARSER_ICON_CAPTION",
                      os.path.abspath("models/omniparser/icon_caption_florence"))

import cv2  # noqa: E402

from visual_dom.adapters.outbound.detectors.registry import create_detector  # noqa: E402
from visual_dom.adapters.outbound.ocr.text_detector import TextDetector  # noqa: E402

out_path = sys.argv[1] if len(sys.argv) > 1 else "parity.txt"
report = open(out_path, "w", encoding="utf-8")


def say(line=""):
    print(line)
    report.write(line + "\n")
    report.flush()


screens = sorted(glob.glob("output/sessions/*/screenshot.png"))[:3] \
    or sorted(glob.glob("tests/samples/*_screen.png"))
say(f"screens: {screens}")

shared = TextDetector(ocr_engine="easyocr", gpu=True)
backends = {
    "monolith": create_detector(
        "omniparser",
        ocr_provider=lambda img: [(t.bounds, t.text, t.confidence)
                                  for t in shared.detect(img)]),
    "modular+florence": create_detector(
        "modular", region_proposer="omniparser", captioner="florence",
        text_detector=shared),
}
# The Qwen2-VL captioner combo is future work behind an Ollama-backed
# Captioner implementation; when it lands in modular_backend._CAPTIONERS this
# block picks it up automatically.
try:
    backends["modular+qwen2vl"] = create_detector(
        "modular", region_proposer="omniparser", captioner="qwen2vl",
        text_detector=shared)
except Exception as exc:
    say(f"(qwen2vl captioner not available yet: {exc})")

for shot in screens:
    image = cv2.imread(shot)
    if image is None:
        continue
    say(f"\n=== {shot} ({image.shape[1]}x{image.shape[0]}) ===")
    for name, backend in backends.items():
        t0 = time.perf_counter()
        dets = backend.detect(image)
        dt = time.perf_counter() - t0
        interactable = sum(1 for d in dets if d.interactable)
        labelled = sum(1 for d in dets if d.label)
        say(f"  {name:20} {len(dets):3d} detections "
            f"({interactable} interactable, {labelled} labelled) in {dt:5.1f}s")

say("\ndone")
report.close()
