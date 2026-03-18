"""
Evaluation Report Generator

Generates detailed reports in various formats (text, JSON, HTML, Markdown).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .evaluator import EvaluationResult, BatchEvaluationResult


class EvaluationReport:
    """
    Generate evaluation reports in various formats.

    Usage:
        report = EvaluationReport(evaluation_result)
        report.save_json("results.json")
        report.save_markdown("results.md")
        print(report.to_text())
    """

    def __init__(
        self,
        result: EvaluationResult,
        predicted_path: Optional[str] = None,
        ground_truth_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.result = result
        self.predicted_path = predicted_path
        self.ground_truth_path = ground_truth_path
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp,
            "metadata": {
                "predicted_file": self.predicted_path,
                "ground_truth_file": self.ground_truth_path,
                **self.metadata,
            },
            "results": self.result.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save_json(self, path: str) -> None:
        """Save report as JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    def to_text(self) -> str:
        """Generate plain text report."""
        return self.result.summary()

    def to_markdown(self) -> str:
        """Generate Markdown report."""
        r = self.result
        em = r.element_metrics
        ocr = r.ocr_metrics
        hm = r.hierarchy_metrics
        lm = r.locator_metrics

        lines = [
            "# Visual DOM Evaluation Report",
            "",
            f"**Generated:** {self.timestamp}",
            "",
        ]

        if self.predicted_path or self.ground_truth_path:
            lines.extend([
                "## Files",
                "",
                f"- **Predicted:** `{self.predicted_path or 'N/A'}`",
                f"- **Ground Truth:** `{self.ground_truth_path or 'N/A'}`",
                "",
            ])

        lines.extend([
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Predicted Elements | {r.predicted_count} |",
            f"| Ground Truth Elements | {r.ground_truth_count} |",
            f"| Overall F1 Score | {em.f1_score:.2%} |",
            f"| Overall Precision | {em.precision:.2%} |",
            f"| Overall Recall | {em.recall:.2%} |",
            "",
            "## Element Detection Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| True Positives | {em.true_positives} |",
            f"| False Positives | {em.false_positives} |",
            f"| False Negatives | {em.false_negatives} |",
            f"| Precision | {em.precision:.4f} ({em.precision:.2%}) |",
            f"| Recall | {em.recall:.4f} ({em.recall:.2%}) |",
            f"| F1 Score | {em.f1_score:.4f} ({em.f1_score:.2%}) |",
            f"| Mean IoU | {em.mean_iou:.4f} ({em.mean_iou:.2%}) |",
            "",
        ])

        # Per-class metrics
        if em.class_metrics:
            lines.extend([
                "### Per-Class Metrics",
                "",
                "| Class | Precision | Recall | F1 | Support |",
                "|-------|-----------|--------|-----|---------|",
            ])
            for cls, metrics in sorted(em.class_metrics.items()):
                lines.append(
                    f"| {cls} | {metrics['precision']:.2%} | {metrics['recall']:.2%} | "
                    f"{metrics['f1']:.2%} | {metrics['support']} |"
                )
            lines.append("")

        lines.extend([
            "## OCR Accuracy Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Character Error Rate (CER) | {ocr.cer:.4f} |",
            f"| Word Error Rate (WER) | {ocr.wer:.4f} |",
            f"| Character Accuracy | {ocr.char_accuracy:.2%} |",
            f"| Word Accuracy | {ocr.word_accuracy:.2%} |",
            f"| Exact Match Rate | {ocr.exact_match_rate:.2%} |",
            f"| Mean Similarity | {ocr.mean_similarity:.4f} |",
            f"| Total Comparisons | {ocr.total_comparisons} |",
            "",
            "## Hierarchy Structure Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Parent Accuracy | {hm.parent_accuracy:.2%} |",
            f"| Depth Accuracy | {hm.depth_accuracy:.2%} |",
            f"| Sibling Order Accuracy | {hm.sibling_order_accuracy:.2%} |",
            f"| Tree Edit Distance | {hm.tree_edit_distance} |",
            f"| Structure Similarity | {hm.structure_similarity:.2%} |",
            "",
            "## Locator Quality Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Coverage | {lm.coverage:.2%} |",
            f"| Text Locator Rate | {lm.text_locator_rate:.2%} |",
            f"| Uniqueness Rate | {lm.uniqueness_rate:.2%} |",
            f"| Duplicate Rate | {lm.duplicate_rate:.2%} |",
            f"| Total Elements | {lm.total_elements} |",
            "",
        ])

        # Locator type distribution
        if lm.locator_type_counts:
            lines.extend([
                "### Locator Type Distribution",
                "",
                "| Type | Count |",
                "|------|-------|",
            ])
            for loc_type, count in sorted(lm.locator_type_counts.items()):
                lines.append(f"| {loc_type} | {count} |")
            lines.append("")

        lines.extend([
            "---",
            "",
            "*Report generated by Visual DOM Evaluation Framework*",
        ])

        return "\n".join(lines)

    def save_markdown(self, path: str) -> None:
        """Save report as Markdown file."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_markdown())

    def to_html(self) -> str:
        """Generate HTML report."""
        r = self.result
        em = r.element_metrics
        ocr = r.ocr_metrics
        hm = r.hierarchy_metrics
        lm = r.locator_metrics

        # Color coding for scores
        def score_color(val: float) -> str:
            if val >= 0.9:
                return "#28a745"  # Green
            elif val >= 0.7:
                return "#ffc107"  # Yellow
            else:
                return "#dc3545"  # Red

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visual DOM Evaluation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
        .metric-card {{
            display: inline-block;
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 10px;
            min-width: 150px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
        }}
        .metric-label {{
            color: #666;
            font-size: 0.9em;
        }}
        .score-good {{ color: #28a745; }}
        .score-medium {{ color: #ffc107; }}
        .score-poor {{ color: #dc3545; }}
        .timestamp {{ color: #888; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Visual DOM Evaluation Report</h1>
        <p class="timestamp">Generated: {self.timestamp}</p>

        <h2>Summary</h2>
        <div class="metric-cards">
            <div class="metric-card">
                <div class="metric-value" style="color: {score_color(em.f1_score)}">{em.f1_score:.1%}</div>
                <div class="metric-label">F1 Score</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" style="color: {score_color(em.precision)}">{em.precision:.1%}</div>
                <div class="metric-label">Precision</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" style="color: {score_color(em.recall)}">{em.recall:.1%}</div>
                <div class="metric-label">Recall</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" style="color: {score_color(ocr.char_accuracy)}">{ocr.char_accuracy:.1%}</div>
                <div class="metric-label">OCR Accuracy</div>
            </div>
        </div>

        <h2>Element Detection</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>True Positives</td><td>{em.true_positives}</td></tr>
            <tr><td>False Positives</td><td>{em.false_positives}</td></tr>
            <tr><td>False Negatives</td><td>{em.false_negatives}</td></tr>
            <tr><td>Precision</td><td>{em.precision:.4f} ({em.precision:.2%})</td></tr>
            <tr><td>Recall</td><td>{em.recall:.4f} ({em.recall:.2%})</td></tr>
            <tr><td>F1 Score</td><td>{em.f1_score:.4f} ({em.f1_score:.2%})</td></tr>
            <tr><td>Mean IoU</td><td>{em.mean_iou:.4f} ({em.mean_iou:.2%})</td></tr>
        </table>

        <h2>OCR Accuracy</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Character Error Rate (CER)</td><td>{ocr.cer:.4f}</td></tr>
            <tr><td>Word Error Rate (WER)</td><td>{ocr.wer:.4f}</td></tr>
            <tr><td>Character Accuracy</td><td>{ocr.char_accuracy:.2%}</td></tr>
            <tr><td>Word Accuracy</td><td>{ocr.word_accuracy:.2%}</td></tr>
            <tr><td>Exact Match Rate</td><td>{ocr.exact_match_rate:.2%}</td></tr>
        </table>

        <h2>Hierarchy Structure</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Parent Accuracy</td><td>{hm.parent_accuracy:.2%}</td></tr>
            <tr><td>Depth Accuracy</td><td>{hm.depth_accuracy:.2%}</td></tr>
            <tr><td>Structure Similarity</td><td>{hm.structure_similarity:.2%}</td></tr>
        </table>

        <h2>Locator Quality</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Coverage</td><td>{lm.coverage:.2%}</td></tr>
            <tr><td>Text Locator Rate</td><td>{lm.text_locator_rate:.2%}</td></tr>
            <tr><td>Uniqueness Rate</td><td>{lm.uniqueness_rate:.2%}</td></tr>
        </table>
    </div>
</body>
</html>"""
        return html

    def save_html(self, path: str) -> None:
        """Save report as HTML file."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_html())


class BatchEvaluationReport:
    """Generate reports for batch evaluation results."""

    def __init__(self, result: BatchEvaluationResult):
        self.result = result
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "results": self.result.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save_json(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    def to_markdown(self) -> str:
        r = self.result
        lines = [
            "# Batch Evaluation Report",
            "",
            f"**Generated:** {self.timestamp}",
            f"**Samples:** {r.count}",
            "",
            "## Aggregate Metrics",
            "",
            "| Metric | Mean Value |",
            "|--------|------------|",
            f"| F1 Score | {r.mean_f1:.2%} |",
            f"| Precision | {r.mean_precision:.2%} |",
            f"| Recall | {r.mean_recall:.2%} |",
            f"| IoU | {r.mean_iou:.2%} |",
            f"| Char Accuracy | {r.mean_char_accuracy:.2%} |",
            "",
            "## Per-Sample Results",
            "",
            "| Sample | F1 | Precision | Recall | IoU |",
            "|--------|-----|-----------|--------|-----|",
        ]

        for i, sample in enumerate(r.results):
            em = sample.element_metrics
            lines.append(
                f"| {i+1} | {em.f1_score:.2%} | {em.precision:.2%} | "
                f"{em.recall:.2%} | {em.mean_iou:.2%} |"
            )

        return "\n".join(lines)

    def save_markdown(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_markdown())
