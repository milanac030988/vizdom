#!/usr/bin/env python
"""
Process a GUI screenshot and generate hierarchy JSON.

This script combines:
1. CV Pipeline (UIED element detection + OCR text detection)
2. Coarse Hierarchy Builder (containment, grouping, label association)
3. LLM Refinement (optional - fixes CV errors using small language model)

Usage:
    python scripts/process_gui_image.py <image_path> [options]

Examples:
    # Basic usage (UIED only, no OCR)
    python scripts/process_gui_image.py screenshot.png

    # With OCR text detection
    python scripts/process_gui_image.py screenshot.png --ocr tesseract

    # With LLM refinement (requires Ollama running)
    python scripts/process_gui_image.py screenshot.png --ocr tesseract --llm ollama

    # Save to specific output file
    python scripts/process_gui_image.py screenshot.png --output output/result.json

    # Generate visualization
    python scripts/process_gui_image.py screenshot.png --visualize result.png
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def setup_tesseract():
    """Setup Tesseract environment if available."""
    tesseract_dirs = [
        r"C:\Program Files\Tesseract-OCR",
        r"C:\Program Files (x86)\Tesseract-OCR",
        r"D:\Program Files\Tesseract-OCR",
    ]
    for base_path in tesseract_dirs:
        tessdata_path = os.path.join(base_path, "tessdata")
        if os.path.exists(tessdata_path):
            os.environ["TESSDATA_PREFIX"] = tessdata_path
            return True
    return False


def process_image(
    image_path: str,
    ocr_engine: str = None,
    use_gpu: bool = False,
    confidence_threshold: float = 0.3,
    iou_threshold: float = 0.5,
    min_element_area: int = 100,
    max_elements: int = 200,
    visualize_path: str = None,
    llm_model: str = None,
    llm_host: str = "http://localhost:11434",
) -> dict:
    """
    Process a GUI image and return hierarchy JSON.

    Args:
        image_path: Path to the GUI screenshot
        ocr_engine: OCR engine to use ('tesseract', 'easyocr', 'paddleocr', or None)
        use_gpu: Use GPU acceleration for OCR
        confidence_threshold: Minimum confidence for detections
        visualize_path: Optional path to save visualization
        llm_model: LLM model for hierarchy refinement ('ollama', 'openai', etc.)
        llm_host: Ollama server URL

    Returns:
        Dictionary with elements and hierarchy
    """
    import cv2
    from visual_dom.cv.pipeline import VisualDOMPipeline
    from visual_dom.hierarchy import CoarseHierarchyBuilder, LLMHierarchyRefiner
    from visual_dom.compiler import DOMCompiler

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")

    height, width = image.shape[:2]
    print(f"Image loaded: {width}x{height}")

    # Setup Tesseract if needed
    if ocr_engine == "tesseract":
        setup_tesseract()

    # Run CV pipeline
    print(f"\nRunning CV pipeline...")
    if ocr_engine:
        print(f"  OCR engine: {ocr_engine}")

    pipeline = VisualDOMPipeline(
        ocr_engine=ocr_engine,
        use_gpu=use_gpu,
        confidence_threshold=confidence_threshold,
    )

    detect_text = ocr_engine is not None
    cv_result = pipeline.process(image, detect_text=detect_text, detect_elements=True)

    print(f"  Elements detected: {cv_result['stats']['uied_detected']}")
    print(f"  Text detected: {cv_result['stats']['text_detected']}")
    print(f"  Total: {cv_result['stats']['final_count']}")

    # Build hierarchy
    print(f"\nBuilding hierarchy...")
    builder = CoarseHierarchyBuilder(
        containment_threshold=0.85,
        alignment_tolerance=15,
        label_max_distance=50,
    )

    hierarchy = builder.build(cv_result["elements"])

    print(f"  Nodes: {len(hierarchy['nodes'])}")
    print(f"  Label associations: {len(hierarchy['label_associations'])}")
    print(f"  Groups: {len(hierarchy['groups'])}")

    # LLM refinement (optional)
    llm_result = None
    refined_elements = cv_result["elements"]

    if llm_model:
        print(f"\nRunning LLM refinement ({llm_model})...")
        try:
            refiner = LLMHierarchyRefiner(
                model_name=llm_model,
                use_gpu=use_gpu,
                ollama_host=llm_host,
            )

            llm_result = refiner.refine(
                elements=cv_result["elements"],
                hierarchy=hierarchy["root"],
                image_size=(width, height),
            )

            refined_elements = llm_result["refined_elements"]
            print(f"  Edits applied: {len(llm_result['edits'])}")
            print(f"  Elements after refinement: {len(refined_elements)}")

        except Exception as e:
            print(f"  LLM refinement failed: {e}")
            print(f"  Continuing with CV results only")

    # Compile DOM with locators
    print(f"\nCompiling DOM...")
    compiler = DOMCompiler(generate_locators=True)
    dom = compiler.compile(
        elements=refined_elements,
        hierarchy=hierarchy["root"],
        image_size=(width, height),
    )
    print(f"  Compiled {dom['element_count']} elements")

    # Combine results
    result = {
        "image_path": str(image_path),
        "image_size": cv_result["image_size"],
        "cv_stats": cv_result["stats"],
        "dom": dom,  # Compiled DOM with locators
        "raw_elements": refined_elements,  # Raw elements for debugging
        "hierarchy_tree": hierarchy["root"],
        "nodes": hierarchy["nodes"],
        "label_associations": hierarchy["label_associations"],
        "groups": hierarchy["groups"],
    }

    # Add LLM info if used
    if llm_result:
        result["llm_refinement"] = {
            "model": llm_model,
            "edits": llm_result["edits"],
            "original_count": len(cv_result["elements"]),
            "refined_count": len(refined_elements),
        }

    # Generate visualization if requested
    if visualize_path:
        print(f"\nGenerating visualization...")
        visualize_hierarchy(image, result, visualize_path)
        print(f"  Saved to: {visualize_path}")

    return result


def visualize_hierarchy(image, result: dict, output_path: str):
    """Generate visualization of detected elements and hierarchy."""
    import cv2
    import numpy as np

    img = image.copy()

    # Color scheme for different element types
    colors = {
        "text": (0, 255, 0),        # Green
        "button": (255, 0, 0),       # Blue
        "input_field": (0, 255, 255), # Yellow
        "checkbox": (255, 255, 0),   # Cyan
        "icon": (255, 0, 255),       # Magenta
        "container": (128, 128, 128), # Gray
        "block": (128, 128, 128),    # Gray
        "unknown": (100, 100, 100),  # Dark gray
    }

    # Draw elements - use DOM elements which have locators
    elements = result.get("dom", {}).get("elements", result.get("raw_elements", []))
    for elem in elements:
        x1, y1, x2, y2 = elem["bounds"]
        vtype = elem.get("visual_type", "unknown")
        color = colors.get(vtype, (100, 100, 100))

        # Draw rectangle
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        # Draw label
        label = f"{elem['id']}"
        text = elem.get("ocr_text") or elem.get("text", "")
        if text:
            label += f": {text[:15]}"

        # Background for label
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.35
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, thickness)

        label_y = max(y1 - 5, th + 5)
        cv2.rectangle(img, (x1, label_y - th - 2), (x1 + tw + 4, label_y + 2), color, -1)
        cv2.putText(img, label, (x1 + 2, label_y), font, font_scale, (255, 255, 255), thickness)

    # Draw label associations as lines
    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    for elem_id, label_id in result["label_associations"].items():
        if elem_id in nodes_by_id and label_id in nodes_by_id:
            elem = nodes_by_id[elem_id]
            label = nodes_by_id[label_id]

            # Get centers
            e_cx = (elem["bounds"][0] + elem["bounds"][2]) // 2
            e_cy = (elem["bounds"][1] + elem["bounds"][3]) // 2
            l_cx = (label["bounds"][0] + label["bounds"][2]) // 2
            l_cy = (label["bounds"][1] + label["bounds"][3]) // 2

            # Draw dashed line
            cv2.line(img, (l_cx, l_cy), (e_cx, e_cy), (0, 165, 255), 1, cv2.LINE_AA)

    cv2.imwrite(output_path, img)


def print_tree(node, indent=0):
    """Print tree structure recursively."""
    if node is None:
        return

    prefix = "  " * indent
    info = f"{node['id']}: {node['visual_type']}"

    if node.get("role"):
        info += f" [{node['role']}]"
    if node.get("text"):
        info += f" \"{node['text'][:30]}\""
    if node.get("hint"):
        info += f" hint=\"{node['hint']}\""

    print(f"{prefix}{info}")

    for child in node.get("children", []):
        print_tree(child, indent + 1)


def main():
    parser = argparse.ArgumentParser(
        description="Process GUI screenshot and generate hierarchy JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/process_gui_image.py screenshot.png
  python scripts/process_gui_image.py screenshot.png --ocr tesseract
  python scripts/process_gui_image.py screenshot.png --ocr tesseract --output result.json
  python scripts/process_gui_image.py screenshot.png --visualize output.png
        """
    )

    parser.add_argument("image", help="Path to GUI screenshot")
    parser.add_argument(
        "--ocr", "-o",
        choices=["tesseract", "easyocr", "paddleocr"],
        default=None,
        help="OCR engine for text detection (default: none)"
    )
    parser.add_argument(
        "--output", "-O",
        default=None,
        help="Output JSON file path (default: <image>_hierarchy.json)"
    )
    parser.add_argument(
        "--visualize", "-v",
        default=None,
        help="Generate visualization image"
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use GPU acceleration for OCR"
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        default=0.3,
        help="Minimum confidence threshold (default: 0.3)"
    )
    parser.add_argument(
        "--max-elements", "-m",
        type=int,
        default=200,
        help="Maximum number of elements to return (default: 200)"
    )
    parser.add_argument(
        "--print-tree", "-t",
        action="store_true",
        help="Print hierarchy tree to console"
    )
    parser.add_argument(
        "--llm", "-l",
        default=None,
        help="LLM model for refinement (ollama, openai, qwen2.5-3b, phi-3.5, gemma-2-2b)"
    )
    parser.add_argument(
        "--llm-host",
        default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434)"
    )

    args = parser.parse_args()

    # Check image exists
    if not os.path.exists(args.image):
        print(f"Error: Image not found: {args.image}")
        sys.exit(1)

    # Determine output path
    image_path = Path(args.image)
    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.output:
        output_path = args.output
    else:
        output_path = output_dir / f"{image_path.stem}_hierarchy.json"

    # Default visualization output to output/ dir too
    if args.visualize and not os.path.dirname(args.visualize):
        args.visualize = str(output_dir / args.visualize)

    print("=" * 60)
    print("GUI Image Processor")
    print("=" * 60)
    print(f"Input:  {args.image}")
    print(f"Output: {output_path}")
    if args.ocr:
        print(f"OCR:    {args.ocr}")
    if args.llm:
        print(f"LLM:    {args.llm}")

    # Process image
    try:
        result = process_image(
            args.image,
            ocr_engine=args.ocr,
            use_gpu=args.gpu,
            confidence_threshold=args.confidence,
            visualize_path=args.visualize,
            llm_model=args.llm,
            llm_host=args.llm_host,
        )

        # Save result
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*60}")
        print(f"Result saved to: {output_path}")

        # Print tree if requested
        if args.print_tree:
            print(f"\n{'='*60}")
            print("HIERARCHY TREE")
            print("=" * 60)
            print_tree(result["hierarchy_tree"])

        # Print summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print("=" * 60)
        print(f"  DOM elements: {result['dom']['element_count']}")
        print(f"  Nodes with text: {sum(1 for n in result['nodes'] if n.get('text'))}")
        print(f"  Label associations: {len(result['label_associations'])}")
        print(f"  Alignment groups: {len(result['groups'])}")

        # Count clickable elements
        clickable = sum(1 for e in result['dom']['elements'] if e.get('clickable'))
        print(f"  Clickable elements: {clickable}")

        if "llm_refinement" in result:
            llm_info = result["llm_refinement"]
            print(f"\n  LLM Refinement ({llm_info['model']}):")
            print(f"    Edits applied: {len(llm_info['edits'])}")
            print(f"    Elements: {llm_info['original_count']} -> {llm_info['refined_count']}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
