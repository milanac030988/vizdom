#!/usr/bin/env bash
# Regenerate report figures from the PlantUML sources of record.
# Needs: Java on PATH, tools/plantuml.jar, and Graphviz (dot) for architecture.puml.
set -e
cd "$(dirname "$0")/.."   # repo root

export GRAPHVIZ_DOT="${GRAPHVIZ_DOT:-C:/Program Files/Graphviz/bin/dot.exe}"
OUT="report/figures"
mkdir -p "$OUT"

for f in system_overview architecture cv_pipeline_detail sequence component problem_space desc_grounding; do
  echo "rendering $f ..."
  java -jar tools/plantuml.jar -tpng -o "$(pwd)/$OUT" "docs/diagrams/$f.puml"
done

echo "done -> $OUT"
ls -1 "$OUT"
