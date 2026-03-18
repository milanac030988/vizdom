"""
Command-line interface for Visual DOM evaluation.

Usage:
    python -m visual_dom.evaluation.cli predicted.json ground_truth.json
    python -m visual_dom.evaluation.cli --batch predictions/ ground_truths/
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List

from .evaluator import VisualDOMEvaluator, EvaluationConfig
from .report import EvaluationReport, BatchEvaluationReport


def evaluate_single(
    predicted_path: str,
    ground_truth_path: str,
    config: EvaluationConfig,
    output_format: str = "text",
    output_path: str = None,
) -> int:
    """Evaluate a single prediction against ground truth."""
    print(f"Evaluating: {predicted_path}")
    print(f"Against:    {ground_truth_path}")
    print()

    evaluator = VisualDOMEvaluator(config)

    try:
        result = evaluator.evaluate_from_files(predicted_path, ground_truth_path)
    except Exception as e:
        print(f"Error during evaluation: {e}", file=sys.stderr)
        return 1

    report = EvaluationReport(
        result,
        predicted_path=predicted_path,
        ground_truth_path=ground_truth_path,
    )

    # Output based on format
    if output_format == "json":
        output = report.to_json()
    elif output_format == "markdown":
        output = report.to_markdown()
    elif output_format == "html":
        output = report.to_html()
    else:
        output = report.to_text()

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Report saved to: {output_path}")
    else:
        print(output)

    return 0


def evaluate_batch(
    predictions_dir: str,
    ground_truths_dir: str,
    config: EvaluationConfig,
    output_format: str = "text",
    output_path: str = None,
) -> int:
    """Evaluate multiple predictions against ground truths."""
    pred_dir = Path(predictions_dir)
    gt_dir = Path(ground_truths_dir)

    if not pred_dir.is_dir():
        print(f"Predictions directory not found: {pred_dir}", file=sys.stderr)
        return 1

    if not gt_dir.is_dir():
        print(f"Ground truths directory not found: {gt_dir}", file=sys.stderr)
        return 1

    # Find matching files
    pred_files = sorted(pred_dir.glob("*.json"))
    predictions = []
    ground_truths = []

    for pred_file in pred_files:
        gt_file = gt_dir / pred_file.name
        if gt_file.exists():
            with open(pred_file, 'r', encoding='utf-8') as f:
                predictions.append(json.load(f))
            with open(gt_file, 'r', encoding='utf-8') as f:
                ground_truths.append(json.load(f))
            print(f"  Matched: {pred_file.name}")
        else:
            print(f"  Skipped (no GT): {pred_file.name}")

    if not predictions:
        print("No matching prediction/ground-truth pairs found.", file=sys.stderr)
        return 1

    print(f"\nEvaluating {len(predictions)} samples...")

    evaluator = VisualDOMEvaluator(config)
    result = evaluator.evaluate_batch(predictions, ground_truths)

    report = BatchEvaluationReport(result)

    if output_format == "json":
        output = report.to_json()
    elif output_format == "markdown":
        output = report.to_markdown()
    else:
        output = result.summary()

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\nReport saved to: {output_path}")
    else:
        print()
        print(output)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Visual DOM predictions against ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file evaluation
  python -m visual_dom.evaluation.cli predicted.json ground_truth.json

  # Batch evaluation
  python -m visual_dom.evaluation.cli --batch predictions/ ground_truths/

  # Save report as Markdown
  python -m visual_dom.evaluation.cli pred.json gt.json -f markdown -o report.md

  # Custom IoU threshold
  python -m visual_dom.evaluation.cli pred.json gt.json --iou-threshold 0.75
        """,
    )

    parser.add_argument(
        "predicted",
        help="Predicted DOM JSON file or directory (for batch mode)",
    )
    parser.add_argument(
        "ground_truth",
        help="Ground truth DOM JSON file or directory (for batch mode)",
    )
    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Batch evaluation mode (treat args as directories)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown", "html"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.5,
        help="IoU threshold for matching (default: 0.5)",
    )
    parser.add_argument(
        "--no-hierarchy",
        action="store_true",
        help="Skip hierarchy evaluation",
    )
    parser.add_argument(
        "--no-locators",
        action="store_true",
        help="Skip locator evaluation",
    )

    args = parser.parse_args()

    config = EvaluationConfig(
        iou_threshold=args.iou_threshold,
        evaluate_hierarchy=not args.no_hierarchy,
        evaluate_locators=not args.no_locators,
    )

    if args.batch:
        return evaluate_batch(
            args.predicted,
            args.ground_truth,
            config,
            args.format,
            args.output,
        )
    else:
        return evaluate_single(
            args.predicted,
            args.ground_truth,
            config,
            args.format,
            args.output,
        )


if __name__ == "__main__":
    sys.exit(main())
