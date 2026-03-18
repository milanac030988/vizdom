#!/usr/bin/env python3
"""
Test LLM-based post-processing to refine CV pipeline results.

This research script evaluates whether Small Language Models (SLMs) can improve
the quality of UI element detection by refining the output from the CV pipeline.

Research Questions:
1. Can LLMs fix common CV detection errors (split text, merged buttons)?
2. Does LLM refinement improve element classification accuracy?
3. What is the trade-off between accuracy improvement and inference time?
4. Which LLM backend works best for this task?

Supported LLM Backends:
- Ollama (local): qwen2.5:3b, llama3.2:3b, phi3:mini
- OpenAI (cloud): gpt-4o-mini, gpt-3.5-turbo
- HuggingFace (local): Qwen/Qwen2.5-3B-Instruct, microsoft/Phi-3.5-mini-instruct

Usage:
    # Test with Ollama (recommended for local testing)
    python research/test_llm_refinement.py screenshot.png --backend ollama

    # Test with OpenAI
    python research/test_llm_refinement.py screenshot.png --backend openai

    # Test with local HuggingFace model
    python research/test_llm_refinement.py screenshot.png --backend hf --model qwen2.5-3b

    # Compare before/after with visualization
    python research/test_llm_refinement.py screenshot.png --backend ollama -o output_dir/

    # Batch evaluation on multiple images
    python research/test_llm_refinement.py test_images/ --backend ollama --batch
"""

import argparse
import json
import time
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class RefinementResult:
    """Result of LLM refinement on CV pipeline output."""
    image_path: str

    # CV Pipeline results (before)
    cv_elements: List[Dict] = field(default_factory=list)
    cv_element_count: int = 0
    cv_time_sec: float = 0.0

    # LLM Refinement results (after)
    refined_elements: List[Dict] = field(default_factory=list)
    refined_element_count: int = 0
    llm_time_sec: float = 0.0

    # Edits applied
    edits: List[Dict] = field(default_factory=list)
    edit_count: int = 0

    # Edit breakdown
    merge_count: int = 0
    split_count: int = 0
    retype_count: int = 0
    delete_count: int = 0
    role_count: int = 0

    # LLM response info
    llm_response: str = ""
    llm_backend: str = ""
    llm_model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "cv_pipeline": {
                "element_count": self.cv_element_count,
                "time_sec": round(self.cv_time_sec, 2),
            },
            "llm_refinement": {
                "element_count": self.refined_element_count,
                "time_sec": round(self.llm_time_sec, 2),
                "backend": self.llm_backend,
                "model": self.llm_model,
            },
            "edits": {
                "total": self.edit_count,
                "merge": self.merge_count,
                "split": self.split_count,
                "retype": self.retype_count,
                "delete": self.delete_count,
                "role": self.role_count,
            },
            "element_change": self.refined_element_count - self.cv_element_count,
            "total_time_sec": round(self.cv_time_sec + self.llm_time_sec, 2),
        }


def run_cv_pipeline(image_path: str, use_gpu: bool = True) -> Tuple[List[Dict], Dict, float]:
    """
    Run CV pipeline on image.

    Returns:
        Tuple of (elements, stats, time_sec)
    """
    from visual_dom.cv.pipeline import VisualDOMPipeline

    print(f"[CV] Running pipeline on: {image_path}")
    start = time.time()

    pipeline = VisualDOMPipeline(
        ocr_engine="easyocr",
        use_gpu=use_gpu,
        confidence_threshold=0.3,
    )

    result = pipeline.process(image_path)
    elapsed = time.time() - start

    elements = result["elements"]
    stats = result["stats"]

    print(f"[CV] Detected {len(elements)} elements in {elapsed:.1f}s")
    print(f"[CV] Stats: text={stats['text_detected']}, uied={stats['uied_detected']}")

    return elements, result, elapsed


def run_llm_refinement(
    elements: List[Dict],
    image_size: Tuple[int, int],
    backend: str = "ollama",
    model: str = None,
    use_gpu: bool = True,
) -> Tuple[List[Dict], List[Dict], str, float]:
    """
    Run LLM refinement on CV pipeline elements.

    Args:
        elements: Elements from CV pipeline
        image_size: (width, height) of image
        backend: LLM backend ("ollama", "openai", "hf")
        model: Specific model name (optional)
        use_gpu: Use GPU for local models

    Returns:
        Tuple of (refined_elements, edits, llm_response, time_sec)
    """
    from visual_dom.hierarchy.llm_refiner import LLMHierarchyRefiner

    # Map backend to model name
    model_map = {
        "ollama": "ollama",
        "openai": "openai",
        "hf": model or "qwen2.5-3b",
        "qwen": "qwen2.5-3b",
        "phi": "phi-3.5",
    }

    model_name = model_map.get(backend, backend)

    print(f"[LLM] Running refinement with: {model_name}")
    start = time.time()

    refiner = LLMHierarchyRefiner(
        model_name=model_name,
        use_gpu=use_gpu,
        temperature=0.1,
        max_tokens=2048,
    )

    result = refiner.refine(
        elements=elements,
        image_size=image_size,
    )

    elapsed = time.time() - start

    refined = result["refined_elements"]
    edits = result["edits"]
    response = result["llm_response"]

    print(f"[LLM] Refinement complete in {elapsed:.1f}s")
    print(f"[LLM] Applied {len(edits)} edits, {len(refined)} elements remaining")

    return refined, edits, response, elapsed


def analyze_edits(edits: List[Dict]) -> Dict[str, int]:
    """Analyze edit operations."""
    counts = {
        "merge": 0,
        "split": 0,
        "retype": 0,
        "delete": 0,
        "role": 0,
        "other": 0,
    }

    for edit in edits:
        op = edit.get("operation", "").lower()
        if "merge" in op:
            counts["merge"] += 1
        elif "split" in op:
            counts["split"] += 1
        elif "type" in op:
            counts["retype"] += 1
        elif "delete" in op:
            counts["delete"] += 1
        elif "role" in op:
            counts["role"] += 1
        else:
            counts["other"] += 1

    return counts


def visualize_comparison(
    image_path: str,
    cv_elements: List[Dict],
    refined_elements: List[Dict],
    output_dir: str,
):
    """Create side-by-side visualization of before/after refinement."""
    import cv2
    import numpy as np

    image = cv2.imread(image_path)
    if image is None:
        print(f"Could not load image: {image_path}")
        return

    h, w = image.shape[:2]

    # Create two copies
    img_before = image.copy()
    img_after = image.copy()

    # Colors by type
    colors = {
        "text": (0, 255, 0),       # Green
        "button": (255, 0, 0),     # Blue
        "input_field": (0, 255, 255),  # Yellow
        "icon": (255, 0, 255),     # Magenta
        "checkbox": (255, 128, 0), # Orange
        "block": (128, 128, 128),  # Gray
        "container": (100, 100, 100),
    }

    def draw_elements(img, elements, label):
        for elem in elements:
            bounds = elem.get("bounds", [])
            if len(bounds) != 4:
                continue

            x1, y1, x2, y2 = [int(b) for b in bounds]
            vtype = elem.get("visual_type", "unknown")
            text = elem.get("ocr_text", elem.get("text", ""))

            color = colors.get(vtype, (200, 200, 200))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

            # Label
            lbl = f"{vtype}"
            if text:
                lbl += f": {text[:15]}"
            cv2.putText(img, lbl, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

        # Add title
        cv2.putText(img, label, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(img, f"Elements: {len(elements)}", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    draw_elements(img_before, cv_elements, "BEFORE (CV Pipeline)")
    draw_elements(img_after, refined_elements, "AFTER (LLM Refined)")

    # Create side-by-side
    combined = np.hstack([img_before, img_after])

    # Save outputs
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = Path(image_path).stem
    cv2.imwrite(str(output_dir / f"{base_name}_before.png"), img_before)
    cv2.imwrite(str(output_dir / f"{base_name}_after.png"), img_after)
    cv2.imwrite(str(output_dir / f"{base_name}_comparison.png"), combined)

    print(f"[VIZ] Saved visualizations to: {output_dir}")


def print_element_diff(cv_elements: List[Dict], refined_elements: List[Dict]):
    """Print detailed diff of elements."""
    print("\n" + "="*70)
    print("ELEMENT COMPARISON")
    print("="*70)

    # Count by type
    def count_types(elements):
        types = {}
        for elem in elements:
            vtype = elem.get("visual_type", "unknown")
            types[vtype] = types.get(vtype, 0) + 1
        return types

    cv_types = count_types(cv_elements)
    refined_types = count_types(refined_elements)

    all_types = set(cv_types.keys()) | set(refined_types.keys())

    print(f"\n{'Type':<15} {'Before':>10} {'After':>10} {'Change':>10}")
    print("-" * 50)

    for vtype in sorted(all_types):
        before = cv_types.get(vtype, 0)
        after = refined_types.get(vtype, 0)
        change = after - before
        change_str = f"+{change}" if change > 0 else str(change)
        print(f"{vtype:<15} {before:>10} {after:>10} {change_str:>10}")

    print("-" * 50)
    print(f"{'TOTAL':<15} {len(cv_elements):>10} {len(refined_elements):>10} {len(refined_elements)-len(cv_elements):>+10}")
    print()


def print_edits(edits: List[Dict]):
    """Print applied edits."""
    if not edits:
        print("\n[LLM] No edits applied - CV pipeline output unchanged")
        return

    print("\n" + "="*70)
    print("LLM EDITS APPLIED")
    print("="*70)

    for i, edit in enumerate(edits, 1):
        op = edit.get("operation", "unknown")
        target = edit.get("target_id", "?")
        params = edit.get("params", {})

        print(f"\n{i}. {op.upper()}")
        print(f"   Target: {target}")
        if params:
            for k, v in params.items():
                print(f"   {k}: {v}")

    print()


def test_single_image(
    image_path: str,
    backend: str = "ollama",
    model: str = None,
    use_gpu: bool = True,
    output_dir: str = None,
    verbose: bool = True,
) -> RefinementResult:
    """
    Test LLM refinement on a single image.

    Args:
        image_path: Path to screenshot
        backend: LLM backend
        model: Specific model name
        use_gpu: Use GPU
        output_dir: Output directory for visualizations
        verbose: Print detailed output

    Returns:
        RefinementResult with all metrics
    """
    result = RefinementResult(image_path=image_path)

    # Step 1: Run CV Pipeline
    cv_elements, cv_result, cv_time = run_cv_pipeline(image_path, use_gpu)
    result.cv_elements = cv_elements
    result.cv_element_count = len(cv_elements)
    result.cv_time_sec = cv_time

    # Get image size
    image_size = (
        cv_result["image_size"]["width"],
        cv_result["image_size"]["height"]
    )

    # Step 2: Run LLM Refinement
    try:
        refined, edits, response, llm_time = run_llm_refinement(
            elements=cv_elements,
            image_size=image_size,
            backend=backend,
            model=model,
            use_gpu=use_gpu,
        )

        result.refined_elements = refined
        result.refined_element_count = len(refined)
        result.llm_time_sec = llm_time
        result.edits = edits
        result.edit_count = len(edits)
        result.llm_response = response
        result.llm_backend = backend
        result.llm_model = model or backend

        # Analyze edits
        edit_counts = analyze_edits(edits)
        result.merge_count = edit_counts["merge"]
        result.split_count = edit_counts["split"]
        result.retype_count = edit_counts["retype"]
        result.delete_count = edit_counts["delete"]
        result.role_count = edit_counts["role"]

    except Exception as e:
        print(f"[ERROR] LLM refinement failed: {e}")
        result.refined_elements = cv_elements
        result.refined_element_count = len(cv_elements)
        result.llm_response = str(e)

    # Print results
    if verbose:
        print_element_diff(result.cv_elements, result.refined_elements)
        print_edits(result.edits)

    # Visualize
    if output_dir:
        visualize_comparison(
            image_path,
            result.cv_elements,
            result.refined_elements,
            output_dir,
        )

    return result


def test_batch(
    input_path: str,
    backend: str = "ollama",
    model: str = None,
    use_gpu: bool = True,
    output_dir: str = None,
) -> List[RefinementResult]:
    """Test LLM refinement on multiple images."""
    input_path = Path(input_path)

    if input_path.is_file():
        images = [input_path]
    else:
        images = list(input_path.glob("*.png")) + list(input_path.glob("*.jpg"))

    if not images:
        print(f"No images found in: {input_path}")
        return []

    print(f"\n{'='*70}")
    print(f"BATCH EVALUATION: {len(images)} images")
    print(f"Backend: {backend}")
    print(f"{'='*70}\n")

    results = []

    for i, img_path in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}] Processing: {img_path.name}")
        print("-" * 50)

        result = test_single_image(
            str(img_path),
            backend=backend,
            model=model,
            use_gpu=use_gpu,
            output_dir=output_dir,
            verbose=False,
        )
        results.append(result)

    # Print summary
    print_batch_summary(results)

    return results


def print_batch_summary(results: List[RefinementResult]):
    """Print summary of batch evaluation."""
    if not results:
        return

    print("\n" + "="*70)
    print("BATCH EVALUATION SUMMARY")
    print("="*70)

    total_cv_elements = sum(r.cv_element_count for r in results)
    total_refined_elements = sum(r.refined_element_count for r in results)
    total_edits = sum(r.edit_count for r in results)
    total_cv_time = sum(r.cv_time_sec for r in results)
    total_llm_time = sum(r.llm_time_sec for r in results)

    total_merge = sum(r.merge_count for r in results)
    total_split = sum(r.split_count for r in results)
    total_retype = sum(r.retype_count for r in results)
    total_delete = sum(r.delete_count for r in results)
    total_role = sum(r.role_count for r in results)

    print(f"\nImages processed: {len(results)}")
    print(f"\nElement Counts:")
    print(f"  CV Pipeline:   {total_cv_elements}")
    print(f"  After LLM:     {total_refined_elements}")
    print(f"  Change:        {total_refined_elements - total_cv_elements:+d}")

    print(f"\nEdits Applied:")
    print(f"  Total:         {total_edits}")
    print(f"  Merge:         {total_merge}")
    print(f"  Split:         {total_split}")
    print(f"  Retype:        {total_retype}")
    print(f"  Delete:        {total_delete}")
    print(f"  Set Role:      {total_role}")

    print(f"\nTiming:")
    print(f"  CV Pipeline:   {total_cv_time:.1f}s ({total_cv_time/len(results):.1f}s avg)")
    print(f"  LLM Refine:    {total_llm_time:.1f}s ({total_llm_time/len(results):.1f}s avg)")
    print(f"  Total:         {total_cv_time + total_llm_time:.1f}s")

    # Edit rate
    if total_cv_elements > 0:
        edit_rate = total_edits / total_cv_elements * 100
        print(f"\nEdit Rate: {edit_rate:.1f}% of elements modified")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Test LLM-based refinement of CV pipeline results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with Ollama (local)
  python research/test_llm_refinement.py screenshot.png --backend ollama

  # Test with OpenAI
  python research/test_llm_refinement.py screenshot.png --backend openai

  # Test with visualization output
  python research/test_llm_refinement.py screenshot.png --backend ollama -o results/

  # Batch test on directory
  python research/test_llm_refinement.py test_images/ --backend ollama --batch
        """
    )

    parser.add_argument(
        "input",
        help="Path to image file or directory (for batch mode)"
    )
    parser.add_argument(
        "--backend", "-b",
        choices=["ollama", "openai", "hf", "qwen", "phi"],
        default="ollama",
        help="LLM backend (default: ollama)"
    )
    parser.add_argument(
        "--model", "-m",
        help="Specific model name (optional)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory for visualizations"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch mode - process all images in directory"
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Disable GPU acceleration"
    )
    parser.add_argument(
        "--json",
        help="Save results to JSON file"
    )

    args = parser.parse_args()

    use_gpu = not args.no_gpu

    print("\n" + "="*70)
    print("LLM REFINEMENT RESEARCH TEST")
    print("="*70)
    print(f"Input: {args.input}")
    print(f"Backend: {args.backend}")
    print(f"GPU: {'Yes' if use_gpu else 'No'}")
    print("="*70)

    # Run test
    if args.batch or Path(args.input).is_dir():
        results = test_batch(
            args.input,
            backend=args.backend,
            model=args.model,
            use_gpu=use_gpu,
            output_dir=args.output,
        )
    else:
        result = test_single_image(
            args.input,
            backend=args.backend,
            model=args.model,
            use_gpu=use_gpu,
            output_dir=args.output,
        )
        results = [result]

    # Save JSON results
    if args.json and results:
        output_data = {
            "test_config": {
                "backend": args.backend,
                "model": args.model,
                "gpu": use_gpu,
            },
            "results": [r.to_dict() for r in results],
        }

        with open(args.json, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to: {args.json}")

    print("\nDone!")


if __name__ == "__main__":
    import io
    # Handle Unicode on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
