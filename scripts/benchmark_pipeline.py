#!/usr/bin/env python
"""
Pipeline Benchmark Tool

Runs the same screenshot through different pipeline configurations
and compares results against ground truth (or against each other).

Usage:
    # Benchmark against ground truth XML (Snoop/UIA export)
    python scripts/benchmark_pipeline.py screenshot.png --ground-truth ui_tree.xml

    # Benchmark against ground truth JSON (manual annotation)
    python scripts/benchmark_pipeline.py screenshot.png --ground-truth annotations.json

    # Compare configurations without ground truth (self-comparison)
    python scripts/benchmark_pipeline.py screenshot.png

    # Custom configurations
    python scripts/benchmark_pipeline.py screenshot.png --configs configs.json
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@dataclass
class BenchmarkConfig:
    """A single pipeline configuration to benchmark."""
    name: str
    ocr_engine: str = "easyocr"
    confidence_threshold: float = 0.3
    use_gpu: bool = False
    slm_backend: Optional[str] = None
    slm_model: Optional[str] = None
    upscale: bool = True

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "ocr_engine": self.ocr_engine,
            "confidence_threshold": self.confidence_threshold,
            "use_gpu": self.use_gpu,
            "slm_backend": self.slm_backend,
            "slm_model": self.slm_model,
            "upscale": self.upscale,
        }


@dataclass
class BenchmarkResult:
    """Result of running one configuration."""
    config: BenchmarkConfig
    duration_ms: float
    element_count: int
    text_detected: int
    uied_detected: int
    elements_with_text: int
    elements_without_text: int
    detected_texts: List[str] = field(default_factory=list)

    # Metrics (computed if ground truth available)
    text_precision: float = 0.0
    text_recall: float = 0.0
    text_f1: float = 0.0
    ocr_accuracy: float = 0.0  # avg text similarity for matched items
    mean_confidence: float = 0.0

    # Element type distribution
    type_distribution: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "config": self.config.to_dict(),
            "duration_ms": round(self.duration_ms, 1),
            "element_count": self.element_count,
            "text_detected": self.text_detected,
            "uied_detected": self.uied_detected,
            "elements_with_text": self.elements_with_text,
            "elements_without_text": self.elements_without_text,
            "text_precision": round(self.text_precision, 4),
            "text_recall": round(self.text_recall, 4),
            "text_f1": round(self.text_f1, 4),
            "ocr_accuracy": round(self.ocr_accuracy, 4),
            "mean_confidence": round(self.mean_confidence, 4),
            "type_distribution": self.type_distribution,
            "detected_texts": self.detected_texts,
        }


def get_default_configs() -> List[BenchmarkConfig]:
    """Default configurations to benchmark."""
    return [
        # --- OCR engine comparison ---
        BenchmarkConfig(
            name="easyocr",
            ocr_engine="easyocr",
        ),
        BenchmarkConfig(
            name="easyocr_no_upscale",
            ocr_engine="easyocr",
            upscale=False,
        ),
        BenchmarkConfig(
            name="tesseract",
            ocr_engine="tesseract",
        ),
        BenchmarkConfig(
            name="tesseract_no_upscale",
            ocr_engine="tesseract",
            upscale=False,
        ),
        # --- SLM text-only comparison ---
        BenchmarkConfig(
            name="easyocr+qwen2.5:3b",
            ocr_engine="easyocr",
            slm_backend="ollama",
            slm_model="qwen2.5:3b",
        ),
        BenchmarkConfig(
            name="easyocr+llama3.1",
            ocr_engine="easyocr",
            slm_backend="ollama",
            slm_model="llama3.1",
        ),
        # --- VLM comparison ---
        BenchmarkConfig(
            name="easyocr+minicpm-v",
            ocr_engine="easyocr",
            slm_backend="ollama",
            slm_model="minicpm-v",
        ),
    ]


def get_available_ollama_models() -> List[str]:
    """Query Ollama for installed models."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            return [m['name'] for m in response.json().get('models', [])]
    except Exception:
        pass
    return []


def filter_configs_by_available_models(configs: List[BenchmarkConfig]) -> List[BenchmarkConfig]:
    """Remove configs that require SLM models not installed in Ollama."""
    available = get_available_ollama_models()
    if not available:
        # Ollama not running — keep only non-SLM configs
        filtered = [c for c in configs if c.slm_backend is None]
        if len(filtered) < len(configs):
            print(f"  Ollama not available, skipping {len(configs) - len(filtered)} SLM configs")
        return filtered

    print(f"  Ollama models available: {', '.join(available)}")

    filtered = []
    for c in configs:
        if c.slm_backend is None:
            filtered.append(c)
        elif c.slm_model in available:
            filtered.append(c)
        else:
            print(f"  Skipping {c.name}: model '{c.slm_model}' not installed")

    return filtered


def parse_ground_truth_xml(xml_path: str) -> List[Dict[str, Any]]:
    """
    Parse Snoop/UIA XML export to extract ground truth text elements.

    Returns list of {"text": str, "type": str, "bounds": [x1,y1,w,h]}
    """
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_path)
    root = tree.getroot()

    gt_elements = []
    for node in root.iter('node'):
        props = {}
        prop_elems = node.find('properties')
        if prop_elems is not None:
            for p in prop_elems.findall('property'):
                props[p.get('displayName')] = p.get('value')

        name = props.get('Name', '')
        ctrl_type = props.get('AutomationControlType', '')
        class_name = props.get('ClassName', '')
        bbox_str = props.get('BoundingRectangle', '')

        if name and ctrl_type in ('Text', 'Edit', 'Button', 'CheckBox', 'ComboBox'):
            bounds = None
            if bbox_str:
                try:
                    parts = [int(x) for x in bbox_str.split(',')]
                    if len(parts) == 4:
                        bounds = parts  # [x, y, w, h]
                except ValueError:
                    pass

            gt_elements.append({
                "text": name.strip(),
                "type": ctrl_type.lower(),
                "class": class_name,
                "bounds": bounds,
            })

    return gt_elements


def parse_ground_truth_json(json_path: str) -> List[Dict[str, Any]]:
    """Parse JSON ground truth file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    gt_elements = []
    elements = data.get('elements', data if isinstance(data, list) else [])
    for elem in elements:
        text = elem.get('text', elem.get('ocr_text', ''))
        if text:
            gt_elements.append({
                "text": text.strip(),
                "type": elem.get('type', elem.get('visual_type', 'unknown')),
                "bounds": elem.get('bounds'),
            })

    return gt_elements


def text_similarity(text1: str, text2: str) -> float:
    """Compute similarity between two strings (0-1)."""
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def run_benchmark(
    image_path: str,
    config: BenchmarkConfig,
) -> Tuple[BenchmarkResult, Dict]:
    """Run pipeline with a specific configuration and collect metrics."""
    from visual_dom.core.domain.pipeline import VisualDOMPipeline

    # Create pipeline
    pipeline = VisualDOMPipeline(
        ocr_engine=config.ocr_engine,
        use_gpu=config.use_gpu,
        confidence_threshold=config.confidence_threshold,
        slm_backend=config.slm_backend,
        slm_model=config.slm_model,
    )

    # Override upscale setting on text detector
    pipeline.text_detector.upscale = config.upscale

    # Run pipeline
    start = time.time()
    result = pipeline.process(image_path)
    duration = (time.time() - start) * 1000

    elements = result.get('elements', [])
    stats = result.get('stats', {})

    # Collect metrics
    texts_found = []
    confidences = []
    type_dist = {}

    for e in elements:
        vtype = e.get('visual_type', 'unknown')
        type_dist[vtype] = type_dist.get(vtype, 0) + 1
        confidences.append(e.get('confidence', 0))
        text = e.get('ocr_text', '')
        if text:
            texts_found.append(text)

    benchmark_result = BenchmarkResult(
        config=config,
        duration_ms=duration,
        element_count=len(elements),
        text_detected=stats.get('text_detected', 0),
        uied_detected=stats.get('uied_detected', 0),
        elements_with_text=len(texts_found),
        elements_without_text=len(elements) - len(texts_found),
        detected_texts=texts_found,
        mean_confidence=sum(confidences) / len(confidences) if confidences else 0,
        type_distribution=type_dist,
    )

    return benchmark_result, result


def evaluate_against_ground_truth(
    result: BenchmarkResult,
    gt_elements: List[Dict],
    similarity_threshold: float = 0.6,
) -> BenchmarkResult:
    """Compute precision/recall/F1 for text detection against ground truth."""
    gt_texts = set()
    for gt in gt_elements:
        text = gt.get('text', '')
        if text:
            gt_texts.add(text.strip())

    if not gt_texts:
        return result

    # Match detected texts to ground truth (fuzzy matching)
    matched_gt = set()
    matched_det = set()
    similarities = []

    for det_text in result.detected_texts:
        best_sim = 0
        best_gt = None
        for gt_text in gt_texts:
            if gt_text in matched_gt:
                continue
            sim = text_similarity(det_text, gt_text)
            if sim > best_sim:
                best_sim = sim
                best_gt = gt_text

        if best_sim >= similarity_threshold and best_gt:
            matched_gt.add(best_gt)
            matched_det.add(det_text)
            similarities.append(best_sim)

    tp = len(matched_gt)
    fp = len(result.detected_texts) - len(matched_det)
    fn = len(gt_texts) - len(matched_gt)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    ocr_acc = sum(similarities) / len(similarities) if similarities else 0

    result.text_precision = precision
    result.text_recall = recall
    result.text_f1 = f1
    result.ocr_accuracy = ocr_acc

    return result


def print_comparison_table(results: List[BenchmarkResult], gt_available: bool):
    """Print formatted comparison table."""
    print()
    print("=" * 100)
    print("PIPELINE BENCHMARK RESULTS")
    print("=" * 100)

    # Header
    if gt_available:
        header = f"{'Config':<25} {'Time':>7} {'Elem':>5} {'Text':>5} {'NoTxt':>5} {'Prec':>7} {'Recall':>7} {'F1':>7} {'OCR%':>7} {'Conf':>6}"
    else:
        header = f"{'Config':<25} {'Time':>7} {'Elem':>5} {'Text':>5} {'NoTxt':>5} {'Conf':>6} {'Types':<30}"
    print(header)
    print("-" * 100)

    for r in results:
        if gt_available:
            print(
                f"{r.config.name:<25} "
                f"{r.duration_ms:>6.0f}ms "
                f"{r.element_count:>5} "
                f"{r.elements_with_text:>5} "
                f"{r.elements_without_text:>5} "
                f"{r.text_precision:>6.1%} "
                f"{r.text_recall:>6.1%} "
                f"{r.text_f1:>6.1%} "
                f"{r.ocr_accuracy:>6.1%} "
                f"{r.mean_confidence:>5.2f}"
            )
        else:
            types_str = ", ".join(f"{k}:{v}" for k, v in sorted(r.type_distribution.items()))
            print(
                f"{r.config.name:<25} "
                f"{r.duration_ms:>6.0f}ms "
                f"{r.element_count:>5} "
                f"{r.elements_with_text:>5} "
                f"{r.elements_without_text:>5} "
                f"{r.mean_confidence:>5.2f} "
                f"{types_str[:30]}"
            )

    print("-" * 100)

    # Best config
    if gt_available:
        best = max(results, key=lambda r: r.text_f1)
        print(f"\nBest F1: {best.config.name} ({best.text_f1:.1%})")
        fastest = min(results, key=lambda r: r.duration_ms)
        print(f"Fastest: {fastest.config.name} ({fastest.duration_ms:.0f}ms)")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark Visual DOM pipeline configurations"
    )
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument(
        "--ground-truth", "-gt",
        help="Ground truth file (XML from Snoop/UIA or JSON)"
    )
    parser.add_argument(
        "--configs", "-c",
        help="JSON file with custom configurations"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file for results"
    )
    parser.add_argument(
        "--similarity", "-s",
        type=float, default=0.6,
        help="Text similarity threshold for matching (default: 0.6)"
    )
    parser.add_argument(
        "--skip-slm",
        action="store_true",
        help="Skip SLM/VLM configurations (OCR-only benchmark)"
    )
    parser.add_argument(
        "--ocr-only",
        action="store_true",
        help="Only benchmark OCR engines (no upscale variants, no SLM)"
    )

    args = parser.parse_args()

    # Check image
    if not os.path.exists(args.image):
        print(f"Error: Image not found: {args.image}")
        sys.exit(1)

    # Load ground truth
    gt_elements = None
    if args.ground_truth:
        gt_path = args.ground_truth
        if not os.path.exists(gt_path):
            print(f"Error: Ground truth not found: {gt_path}")
            sys.exit(1)

        if gt_path.endswith('.xml'):
            gt_elements = parse_ground_truth_xml(gt_path)
        else:
            gt_elements = parse_ground_truth_json(gt_path)

        # Deduplicate ground truth texts
        seen = set()
        unique_gt = []
        for gt in gt_elements:
            if gt['text'] not in seen:
                seen.add(gt['text'])
                unique_gt.append(gt)
        gt_elements = unique_gt

        print(f"Ground truth: {len(gt_elements)} elements from {gt_path}")

    # Load configurations
    if args.configs:
        with open(args.configs) as f:
            config_data = json.load(f)
        configs = [BenchmarkConfig(**c) for c in config_data]
    else:
        configs = get_default_configs()

    # Filter configs based on flags
    if args.ocr_only:
        configs = [c for c in configs if c.slm_backend is None and c.upscale]
        print("  Mode: OCR-only (no upscale variants, no SLM)")
    elif args.skip_slm:
        configs = [c for c in configs if c.slm_backend is None]
        print("  Mode: Skipping SLM/VLM configs")
    else:
        # Auto-filter by available Ollama models
        configs = filter_configs_by_available_models(configs)

    print(f"Image: {args.image}")
    print(f"Configurations: {len(configs)}")
    for c in configs:
        slm_info = f" + {c.slm_model}" if c.slm_backend else ""
        upscale_info = "" if c.upscale else " (no upscale)"
        print(f"  - {c.name}: {c.ocr_engine}{upscale_info}{slm_info}")
    print()

    # Run benchmarks
    results = []
    for i, config in enumerate(configs):
        print(f"[{i+1}/{len(configs)}] Running: {config.name}...")
        try:
            bench_result, raw_result = run_benchmark(args.image, config)

            if gt_elements:
                bench_result = evaluate_against_ground_truth(
                    bench_result, gt_elements, args.similarity
                )

            results.append(bench_result)
            print(f"  -> {bench_result.element_count} elements, "
                  f"{bench_result.elements_with_text} with text, "
                  f"{bench_result.duration_ms:.0f}ms")

        except Exception as e:
            print(f"  -> FAILED: {e}")
            import traceback
            traceback.print_exc()

    # Print comparison
    print_comparison_table(results, gt_elements is not None)

    # Save results
    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(output_dir / f"benchmark_{timestamp}.json")

    report = {
        "timestamp": datetime.now().isoformat(),
        "image": args.image,
        "ground_truth": args.ground_truth,
        "similarity_threshold": args.similarity,
        "results": [r.to_dict() for r in results],
    }

    if gt_elements:
        report["ground_truth_count"] = len(gt_elements)
        report["ground_truth_texts"] = [gt['text'] for gt in gt_elements]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Results saved to: {output_path}")

    # Generate HTML dashboard
    html_path = output_path.replace('.json', '.html')
    generate_html_dashboard(report, results, html_path, gt_elements is not None)
    print(f"Dashboard saved to: {html_path}")


def generate_html_dashboard(
    report: Dict,
    results: List[BenchmarkResult],
    html_path: str,
    gt_available: bool,
):
    """Generate an HTML dashboard with charts and tables."""

    config_names = [r.config.name for r in results]
    config_names_js = json.dumps(config_names)

    # Metrics arrays
    f1_scores = [round(r.text_f1 * 100, 1) for r in results]
    precisions = [round(r.text_precision * 100, 1) for r in results]
    recalls = [round(r.text_recall * 100, 1) for r in results]
    ocr_accs = [round(r.ocr_accuracy * 100, 1) for r in results]
    durations = [round(r.duration_ms / 1000, 1) for r in results]
    elem_counts = [r.element_count for r in results]
    text_counts = [r.elements_with_text for r in results]
    notext_counts = [r.elements_without_text for r in results]
    confidences = [round(r.mean_confidence, 3) for r in results]

    # Best highlights
    best_f1_idx = f1_scores.index(max(f1_scores)) if f1_scores else 0
    fastest_idx = durations.index(min(durations)) if durations else 0

    # Type distribution table rows
    all_types = sorted(set(t for r in results for t in r.type_distribution))

    type_header = "".join(f"<th>{t}</th>" for t in all_types)
    type_rows = ""
    for r in results:
        cells = "".join(f"<td>{r.type_distribution.get(t, 0)}</td>" for t in all_types)
        type_rows += f"<tr><td><b>{r.config.name}</b></td>{cells}</tr>\n"

    # Detected texts comparison (only first 3 configs to keep it readable)
    texts_section = ""
    if gt_available:
        gt_texts = report.get("ground_truth_texts", [])
        texts_section = _build_texts_comparison_html(results[:4], gt_texts)

    gt_info = ""
    if gt_available:
        gt_count = report.get("ground_truth_count", 0)
        gt_info = f"<p>Ground truth: <b>{gt_count}</b> text elements | Similarity threshold: {report.get('similarity_threshold', 0.6)}</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VizDOM Pipeline Benchmark</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #f5f5f5; color: #333; padding: 20px; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ font-size: 24px; margin-bottom: 5px; }}
    .subtitle {{ color: #666; margin-bottom: 20px; font-size: 14px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }}
    .card {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .card .label {{ font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
    .card .value {{ font-size: 28px; font-weight: 700; margin-top: 4px; }}
    .card .value.green {{ color: #2e7d32; }}
    .card .value.blue {{ color: #1565c0; }}
    .card .value.orange {{ color: #e65100; }}
    .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px; }}
    .chart-box {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .chart-box h3 {{ font-size: 15px; margin-bottom: 12px; color: #555; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
    th {{ background: #f8f8f8; font-weight: 600; color: #555; }}
    tr:hover {{ background: #f5f9ff; }}
    .highlight {{ background: #e8f5e9 !important; }}
    .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
    .tag-best {{ background: #c8e6c9; color: #2e7d32; }}
    .tag-fast {{ background: #bbdefb; color: #1565c0; }}
    .section {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }}
    .section h3 {{ font-size: 15px; margin-bottom: 12px; color: #555; }}
    .match {{ color: #2e7d32; }}
    .miss {{ color: #c62828; }}
    .partial {{ color: #e65100; }}
    @media (max-width: 900px) {{ .charts {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
    <h1>VizDOM Pipeline Benchmark</h1>
    <p class="subtitle">
        {report.get('timestamp', '')[:19]} |
        Image: {os.path.basename(report.get('image', ''))} |
        {len(results)} configurations tested
    </p>
    {gt_info}

    <div class="cards">
        <div class="card">
            <div class="label">Best F1 Score</div>
            <div class="value green">{max(f1_scores):.1f}%</div>
            <div class="label">{config_names[best_f1_idx]}</div>
        </div>
        <div class="card">
            <div class="label">Fastest</div>
            <div class="value blue">{min(durations):.1f}s</div>
            <div class="label">{config_names[fastest_idx]}</div>
        </div>
        <div class="card">
            <div class="label">Best Recall</div>
            <div class="value orange">{max(recalls):.1f}%</div>
            <div class="label">{config_names[recalls.index(max(recalls))]}</div>
        </div>
        <div class="card">
            <div class="label">Configs Tested</div>
            <div class="value">{len(results)}</div>
        </div>
    </div>

    <div class="charts">
        <div class="chart-box">
            <h3>Detection Quality (Precision / Recall / F1)</h3>
            <canvas id="qualityChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>Performance (Time in seconds)</h3>
            <canvas id="timeChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>Element Count (With Text / Without Text)</h3>
            <canvas id="elemChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>OCR Accuracy & Confidence</h3>
            <canvas id="ocrChart"></canvas>
        </div>
    </div>

    <div class="section">
        <h3>Results Table</h3>
        <table>
            <thead>
                <tr>
                    <th>Configuration</th>
                    <th>OCR</th>
                    <th>SLM</th>
                    <th>Time</th>
                    <th>Elements</th>
                    <th>With Text</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>F1</th>
                    <th>OCR Acc</th>
                    <th>Confidence</th>
                </tr>
            </thead>
            <tbody>
                {"".join(
                    f'''<tr class="{'highlight' if i == best_f1_idx else ''}">
                    <td><b>{r.config.name}</b>
                        {' <span class="tag tag-best">BEST F1</span>' if i == best_f1_idx else ''}
                        {' <span class="tag tag-fast">FASTEST</span>' if i == fastest_idx else ''}
                    </td>
                    <td>{r.config.ocr_engine}{"" if r.config.upscale else " (no up)"}</td>
                    <td>{r.config.slm_model or "-"}</td>
                    <td>{r.duration_ms/1000:.1f}s</td>
                    <td>{r.element_count}</td>
                    <td>{r.elements_with_text}</td>
                    <td>{r.text_precision:.1%}</td>
                    <td>{r.text_recall:.1%}</td>
                    <td><b>{r.text_f1:.1%}</b></td>
                    <td>{r.ocr_accuracy:.1%}</td>
                    <td>{r.mean_confidence:.2f}</td>
                    </tr>'''
                    for i, r in enumerate(results)
                )}
            </tbody>
        </table>
    </div>

    <div class="section">
        <h3>Element Type Distribution</h3>
        <table>
            <thead><tr><th>Configuration</th>{type_header}</tr></thead>
            <tbody>{type_rows}</tbody>
        </table>
    </div>

    {texts_section}
</div>

<script>
const names = {config_names_js};

new Chart(document.getElementById('qualityChart'), {{
    type: 'bar',
    data: {{
        labels: names,
        datasets: [
            {{ label: 'Precision', data: {json.dumps(precisions)}, backgroundColor: 'rgba(33,150,243,0.7)' }},
            {{ label: 'Recall', data: {json.dumps(recalls)}, backgroundColor: 'rgba(76,175,80,0.7)' }},
            {{ label: 'F1', data: {json.dumps(f1_scores)}, backgroundColor: 'rgba(255,152,0,0.7)' }},
        ]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{ y: {{ beginAtZero: true, max: 100, title: {{ display: true, text: '%' }} }} }}
    }}
}});

new Chart(document.getElementById('timeChart'), {{
    type: 'bar',
    data: {{
        labels: names,
        datasets: [{{ label: 'Time (s)', data: {json.dumps(durations)}, backgroundColor: 'rgba(156,39,176,0.7)' }}]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'seconds' }} }} }}
    }}
}});

new Chart(document.getElementById('elemChart'), {{
    type: 'bar',
    data: {{
        labels: names,
        datasets: [
            {{ label: 'With Text', data: {json.dumps(text_counts)}, backgroundColor: 'rgba(76,175,80,0.7)' }},
            {{ label: 'Without Text', data: {json.dumps(notext_counts)}, backgroundColor: 'rgba(244,67,54,0.4)' }},
        ]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{ y: {{ beginAtZero: true, stacked: true }}, x: {{ stacked: true }} }}
    }}
}});

new Chart(document.getElementById('ocrChart'), {{
    type: 'bar',
    data: {{
        labels: names,
        datasets: [
            {{ label: 'OCR Accuracy', data: {json.dumps(ocr_accs)}, backgroundColor: 'rgba(0,150,136,0.7)' }},
            {{ label: 'Mean Confidence x100', data: {json.dumps([round(c*100,1) for c in confidences])}, backgroundColor: 'rgba(255,193,7,0.7)' }},
        ]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{ y: {{ beginAtZero: true, max: 100, title: {{ display: true, text: '%' }} }} }}
    }}
}});
</script>
</body>
</html>"""

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)


def _build_texts_comparison_html(
    results: List[BenchmarkResult],
    gt_texts: List[str],
) -> str:
    """Build HTML section comparing detected texts across configs vs ground truth."""
    if not gt_texts:
        return ""

    rows = ""
    for gt_text in sorted(gt_texts):
        cells = ""
        for r in results:
            # Find best match in this config's detections
            best_match = ""
            best_sim = 0
            for det in r.detected_texts:
                sim = text_similarity(det, gt_text)
                if sim > best_sim:
                    best_sim = sim
                    best_match = det

            if best_sim >= 0.9:
                css = "match"
                display = best_match
            elif best_sim >= 0.6:
                css = "partial"
                display = f"{best_match} ({best_sim:.0%})"
            else:
                css = "miss"
                display = "MISS"

            cells += f'<td class="{css}">{display}</td>'

        rows += f"<tr><td><b>{gt_text}</b></td>{cells}</tr>\n"

    headers = "".join(f"<th>{r.config.name}</th>" for r in results)

    return f"""
    <div class="section">
        <h3>Text Detection Comparison (vs Ground Truth)</h3>
        <p style="color:#888;font-size:12px;margin-bottom:10px;">
            <span class="match">Green</span> = exact match |
            <span class="partial">Orange</span> = partial match |
            <span class="miss">Red</span> = not detected
        </p>
        <table>
            <thead><tr><th>Ground Truth</th>{headers}</tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


if __name__ == "__main__":
    main()
