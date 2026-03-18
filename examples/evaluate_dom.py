#!/usr/bin/env python
"""
Example: Evaluate Visual DOM output against ground truth.

This script demonstrates how to use the evaluation framework to
measure the quality of Visual DOM detection.

Usage:
    python examples/evaluate_dom.py [predicted.json] [ground_truth.json]
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from visual_dom.evaluation import (
    VisualDOMEvaluator,
    EvaluationConfig,
    EvaluationReport,
)


def main():
    # Default files for demo
    if len(sys.argv) >= 3:
        predicted_path = sys.argv[1]
        ground_truth_path = sys.argv[2]
    else:
        # Use calculator example
        base_dir = os.path.dirname(os.path.dirname(__file__))
        predicted_path = os.path.join(base_dir, "output", "calculator_llm_dom6.json")
        ground_truth_path = predicted_path  # Self-compare for demo

        print("Usage: python evaluate_dom.py <predicted.json> <ground_truth.json>")
        print()
        print(f"No files specified, using demo file: {predicted_path}")
        print("(Self-comparison will show perfect scores)")
        print()

    # Configure evaluation
    config = EvaluationConfig(
        iou_threshold=0.5,          # 50% IoU to consider a match
        evaluate_hierarchy=True,    # Evaluate parent-child relationships
        evaluate_locators=True,     # Evaluate locator quality
    )

    # Create evaluator
    evaluator = VisualDOMEvaluator(config)

    # Run evaluation
    print("=" * 60)
    print("Running Visual DOM Evaluation")
    print("=" * 60)
    print(f"Predicted:    {predicted_path}")
    print(f"Ground Truth: {ground_truth_path}")
    print()

    try:
        result = evaluator.evaluate_from_files(predicted_path, ground_truth_path)
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        return 1
    except Exception as e:
        print(f"Error during evaluation: {e}")
        return 1

    # Print summary
    print(result.summary())

    # Detailed per-class metrics
    if result.element_metrics.class_metrics:
        print("\nPer-Class Detection Metrics:")
        print("-" * 50)
        print(f"{'Class':<15} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>10}")
        print("-" * 50)
        for cls, metrics in sorted(result.element_metrics.class_metrics.items()):
            print(f"{cls:<15} {metrics['precision']:>10.2%} {metrics['recall']:>10.2%} "
                  f"{metrics['f1']:>10.2%} {metrics['support']:>10}")

    # Generate reports
    report = EvaluationReport(
        result,
        predicted_path=predicted_path,
        ground_truth_path=ground_truth_path,
    )

    # Save reports
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, 'evaluation_report.json')
    md_path = os.path.join(output_dir, 'evaluation_report.md')
    html_path = os.path.join(output_dir, 'evaluation_report.html')

    report.save_json(json_path)
    report.save_markdown(md_path)
    report.save_html(html_path)

    print(f"\nReports saved to:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")
    print(f"  - {html_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
