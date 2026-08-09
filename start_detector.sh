#!/usr/bin/env bash
# VizDOM Detector gRPC Service (ADR-017)
# POSIX counterpart of start_detector.bat. Interpreter resolution: python_env.sh
# (override with VIZDOM_PYTHON; see docs/uv-setup.md).
#
# Usage:
#   ./start_detector.sh                                  (uied, port 50051)
#   ./start_detector.sh --backend omniparser --ocr easyocr
#   ./start_detector.sh --backend yolo --yolo-model models/pretrained/best.pt
#
#   Pass --ocr <engine> so the OCR text ensemble runs ON THIS SERVICE: the
#   client's OCR callable cannot cross gRPC, and without it a remote OmniParser
#   silently falls back to its own weaker OCR (ADR-016).
set -euo pipefail
cd "$(dirname "$0")"
. ./python_env.sh
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

if [ "$#" -eq 0 ]; then
    # no args -> lightweight uied service for a quick connectivity test
    exec "$VIZDOM_PY" -m visual_dom.adapters.inbound.grpc.detector_server         --backend uied --port 50051
fi
exec "$VIZDOM_PY" -m visual_dom.adapters.inbound.grpc.detector_server "$@"
