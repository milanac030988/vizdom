"""
Test the CV pipeline on sample screenshots.

Usage:
    python tests/test_cv_pipeline.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import cv2
import numpy as np


def generate_test_images():
    """Generate test images if they don't exist."""
    samples_dir = project_root / "tests" / "samples"

    if not (samples_dir / "login_screen.png").exists():
        print("Generating test images...")
        from samples.generate_test_ui import save_test_images
        save_test_images(str(samples_dir))

    return samples_dir


def test_uied_detection():
    """Test UIED-style element detection (no OCR)."""
    print("\n" + "=" * 60)
    print("TEST: UIED Element Detection (Traditional CV)")
    print("=" * 60)

    samples_dir = generate_test_images()
    image_path = samples_dir / "login_screen.png"

    # Load image
    image = cv2.imread(str(image_path))
    print(f"\nImage: {image_path.name}")
    print(f"Size: {image.shape[1]}x{image.shape[0]}")

    # Run UIED detection
    from visual_dom.cv.uied_detection import UIEDDetector

    detector = UIEDDetector(
        min_element_area=100,
        min_block_area=500,
    )

    elements = detector.detect(image)

    print(f"\nDetected {len(elements)} elements:")
    for elem in elements[:15]:
        print(f"  {elem.id}: {elem.element_type.value:12s} conf={elem.confidence:.2f} bounds={elem.bounds}")

    if len(elements) > 15:
        print(f"  ... and {len(elements) - 15} more")

    # Visualize
    output_path = samples_dir / "login_uied_result.png"
    visualize_detections(image, elements, str(output_path))
    print(f"\nVisualization saved: {output_path}")

    return elements


def test_text_detection():
    """Test text detection with OCR."""
    print("\n" + "=" * 60)
    print("TEST: Text Detection (OCR)")
    print("=" * 60)

    samples_dir = generate_test_images()
    image_path = samples_dir / "login_screen.png"

    image = cv2.imread(str(image_path))

    # Check if OCR is available
    try:
        from visual_dom.cv.text_detector import TextDetector

        detector = TextDetector(
            ocr_engine="easyocr",
            confidence_threshold=0.3,
            gpu=False  # Use CPU for testing
        )

        print("\nRunning OCR (this may take a moment on first run)...")
        elements = detector.detect(image)

        print(f"\nDetected {len(elements)} text elements:")
        for elem in elements:
            print(f"  {elem.id}: '{elem.text}' conf={elem.confidence:.2f}")

        return elements

    except ImportError as e:
        print(f"\nOCR not available: {e}")
        print("Install with: pip install easyocr")
        return []

    except Exception as e:
        print(f"\nOCR failed: {e}")
        return []


def test_full_pipeline():
    """Test the complete CV pipeline."""
    print("\n" + "=" * 60)
    print("TEST: Full CV Pipeline (UIED + OCR)")
    print("=" * 60)

    samples_dir = generate_test_images()
    image_path = samples_dir / "login_screen.png"

    image = cv2.imread(str(image_path))

    try:
        from visual_dom.cv.pipeline import VisualDOMPipeline

        pipeline = VisualDOMPipeline(
            ocr_engine="easyocr",
            use_gpu=False,
            confidence_threshold=0.3,
        )

        print("\nRunning full pipeline...")
        result = pipeline.process(image)

        print(f"\nPipeline Statistics:")
        print(f"  Text detected: {result['stats']['text_detected']}")
        print(f"  UIED detected: {result['stats']['uied_detected']}")
        print(f"  Final count:   {result['stats']['final_count']}")

        print(f"\nDetected Elements:")
        for elem in result["elements"][:20]:
            text = elem.get("ocr_text", "")[:25] if elem.get("ocr_text") else ""
            parent = f" (parent: {elem.get('parent_id')})" if elem.get("parent_id") else ""
            print(f"  {elem['id']}: {elem['visual_type']:12s} '{text}'{parent}")

        if len(result["elements"]) > 20:
            print(f"  ... and {len(result['elements']) - 20} more")

        # Save result
        output_json = samples_dir / "login_pipeline_result.json"
        with open(output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResult saved: {output_json}")

        # Visualize
        output_path = samples_dir / "login_pipeline_result.png"
        visualize_pipeline_result(image, result, str(output_path))
        print(f"Visualization saved: {output_path}")

        return result

    except ImportError as e:
        print(f"\nPipeline dependencies not available: {e}")
        print("Install with: pip install easyocr opencv-python")
        return None


def test_without_ocr():
    """Test pipeline without OCR (faster, for quick testing)."""
    print("\n" + "=" * 60)
    print("TEST: Pipeline without OCR (UIED only)")
    print("=" * 60)

    samples_dir = generate_test_images()
    image_path = samples_dir / "login_screen.png"

    image = cv2.imread(str(image_path))

    from visual_dom.cv.pipeline import VisualDOMPipeline

    pipeline = VisualDOMPipeline(
        confidence_threshold=0.3,
    )

    print("\nRunning pipeline (UIED only, no OCR)...")
    result = pipeline.process(image, detect_text=False, detect_elements=True)

    print(f"\nDetected {result['stats']['final_count']} elements:")
    for elem in result["elements"][:15]:
        print(f"  {elem['id']}: {elem['visual_type']:12s} bounds={elem['bounds']}")

    # Visualize
    output_path = samples_dir / "login_uied_only_result.png"
    visualize_pipeline_result(image, result, str(output_path))
    print(f"\nVisualization saved: {output_path}")

    return result


def visualize_detections(image, elements, output_path):
    """Visualize UIED detection results."""
    img = image.copy()

    colors = {
        "block": (128, 128, 128),
        "button": (255, 0, 0),
        "input_field": (0, 255, 255),
        "checkbox": (255, 255, 0),
        "icon": (255, 0, 255),
        "text": (0, 255, 0),
        "divider": (200, 200, 200),
        "unknown": (100, 100, 100),
    }

    for elem in elements:
        x1, y1, x2, y2 = elem.bounds
        color = colors.get(elem.element_type.value, (100, 100, 100))

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        label = f"{elem.id}: {elem.element_type.value}"
        cv2.putText(img, label, (x1, max(y1 - 5, 15)),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

    cv2.imwrite(output_path, img)


def visualize_pipeline_result(image, result, output_path):
    """Visualize full pipeline results."""
    img = image.copy()

    colors = {
        "text": (0, 255, 0),
        "button": (255, 0, 0),
        "input_field": (0, 255, 255),
        "checkbox": (255, 255, 0),
        "icon": (255, 0, 255),
        "container": (128, 128, 128),
        "block": (128, 128, 128),
        "unknown": (100, 100, 100),
    }

    for elem in result["elements"]:
        x1, y1, x2, y2 = elem["bounds"]
        color = colors.get(elem["visual_type"], (100, 100, 100))

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        label = elem["visual_type"]
        if elem.get("ocr_text"):
            label += f": {elem['ocr_text'][:12]}"

        cv2.putText(img, label, (x1, max(y1 - 5, 15)),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

    cv2.imwrite(output_path, img)


def compare_with_ground_truth():
    """Compare detection results with ground truth."""
    print("\n" + "=" * 60)
    print("TEST: Compare with Ground Truth")
    print("=" * 60)

    samples_dir = generate_test_images()

    # Load ground truth
    gt_path = samples_dir / "login_screen_gt.json"
    with open(gt_path) as f:
        ground_truth = json.load(f)

    print(f"\nGround truth: {len(ground_truth['elements'])} elements")

    # Run detection
    result = test_without_ocr()

    if result:
        detected = len(result["elements"])
        expected = len(ground_truth["elements"])

        print(f"\nComparison:")
        print(f"  Expected: {expected} elements")
        print(f"  Detected: {detected} elements")
        print(f"  Ratio:    {detected / expected * 100:.1f}%")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CV PIPELINE TEST SUITE")
    print("=" * 60)

    # Generate test images
    samples_dir = generate_test_images()
    print(f"\nTest images in: {samples_dir}")

    # Test 1: UIED detection only (fastest)
    test_uied_detection()

    # Test 2: Pipeline without OCR
    test_without_ocr()

    # Test 3: Ground truth comparison
    compare_with_ground_truth()

    # Test 4: Full pipeline with OCR (optional - slower)
    print("\n" + "-" * 60)
    response = input("Run full pipeline with OCR? (y/n, requires easyocr): ").strip().lower()
    if response == 'y':
        test_text_detection()
        test_full_pipeline()

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)
    print(f"\nCheck results in: {samples_dir}")


if __name__ == "__main__":
    main()
