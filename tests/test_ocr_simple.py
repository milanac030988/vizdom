"""
Simple OCR test script.

Run with: python tests/test_ocr_simple.py   (any interpreter with the [ocr] extra)

Supports multiple OCR backends:
- tesseract: Lightweight, requires Tesseract OCR installed
- easyocr: Best accuracy, requires PyTorch
- paddleocr: Fast, multi-language support
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Default OCR engine to test
DEFAULT_OCR = "tesseract"


def test_pillow():
    """Test Pillow installation."""
    print("Testing Pillow...")
    try:
        from PIL import Image
        print(f"  PIL location: {Image.__file__}")
        print("  Pillow: OK")
        return True
    except ImportError as e:
        print(f"  Pillow error: {e}")
        return False


def test_tesseract():
    """Test Tesseract installation."""
    print("\nTesting Tesseract OCR...")

    # Check pytesseract
    try:
        import pytesseract
    except ImportError:
        print("  pytesseract not installed. Run: pip install pytesseract")
        return False

    # Auto-detect Tesseract path on Windows
    tesseract_dirs = [
        r"C:\Program Files\Tesseract-OCR",
        r"C:\Program Files (x86)\Tesseract-OCR",
        r"D:\Program Files\Tesseract-OCR",
    ]

    tesseract_dir = None
    for base_path in tesseract_dirs:
        exe_path = os.path.join(base_path, "tesseract.exe")
        if os.path.exists(exe_path):
            tesseract_dir = base_path
            pytesseract.pytesseract.tesseract_cmd = exe_path
            print(f"  Found Tesseract at: {exe_path}")
            break

    if not tesseract_dir:
        # Try system PATH
        try:
            version = pytesseract.get_tesseract_version()
            print(f"  Tesseract version: {version}")
            return True
        except Exception:
            pass

        print("  Tesseract OCR engine NOT FOUND!")
        print("\n  Installation instructions:")
        print("  1. Download from: https://github.com/UB-Mannheim/tesseract/wiki")
        print("  2. Run installer (64-bit recommended)")
        print("  3. Default path: C:\\Program Files\\Tesseract-OCR")
        print("  4. Re-run this test after installation")
        return False

    # Set TESSDATA_PREFIX environment variable (override any incorrect system setting)
    tessdata_path = os.path.join(tesseract_dir, "tessdata")
    if os.path.exists(tessdata_path):
        # Force override - some systems have incorrect TESSDATA_PREFIX
        old_prefix = os.environ.get("TESSDATA_PREFIX", "")
        os.environ["TESSDATA_PREFIX"] = tessdata_path
        if old_prefix and old_prefix != tessdata_path:
            print(f"  Overriding TESSDATA_PREFIX: {old_prefix} -> {tessdata_path}")
        else:
            print(f"  Set TESSDATA_PREFIX: {tessdata_path}")

        # Check if eng.traineddata exists
        eng_data = os.path.join(tessdata_path, "eng.traineddata")
        if os.path.exists(eng_data):
            print(f"  English language data: OK")
        else:
            print(f"  WARNING: eng.traineddata not found in {tessdata_path}")
            print("  You may need to download language data files.")
    else:
        print(f"  WARNING: tessdata directory not found at {tessdata_path}")

    try:
        version = pytesseract.get_tesseract_version()
        print(f"  Tesseract version: {version}")
        print("  Tesseract: OK")
        return True
    except Exception as e:
        print(f"  Tesseract error: {e}")
        return False


def test_easyocr():
    """Test EasyOCR installation."""
    print("\nTesting EasyOCR...")
    try:
        import easyocr
        print("  EasyOCR: OK")
        return True
    except ImportError as e:
        print(f"  EasyOCR not available: {e}")
        return False

def test_ocr_detection(ocr_engine="tesseract"):
    """Test OCR on sample image."""
    print(f"\nTesting OCR detection with {ocr_engine}...")

    # Ensure TESSDATA_PREFIX is set correctly before any OCR calls
    if ocr_engine == "tesseract":
        tesseract_dir = r"C:\Program Files\Tesseract-OCR"
        tessdata_path = os.path.join(tesseract_dir, "tessdata")
        if os.path.exists(tessdata_path):
            os.environ["TESSDATA_PREFIX"] = tessdata_path

    import cv2
    from visual_dom.adapters.outbound.ocr.text_detector import TextDetector

    samples_dir = project_root / "tests" / "samples"
    image_path = samples_dir / "login_screen.png"

    if not image_path.exists():
        print("  Generating test images...")
        from samples.generate_test_ui import save_test_images
        save_test_images(str(samples_dir))

    print(f"  Loading image: {image_path}")
    image = cv2.imread(str(image_path))

    print(f"  Initializing {ocr_engine} detector...")
    try:
        detector = TextDetector(
            ocr_engine=ocr_engine,
            confidence_threshold=0.3,
            gpu=False
        )

        print("  Running OCR...")
        results = detector.detect(image)

        print(f"\n  Detected {len(results)} text regions:")
        for elem in results:
            print(f"    '{elem.text}' (confidence: {elem.confidence:.2f}) at {elem.bounds}")

        return results

    except Exception as e:
        print(f"  OCR failed: {e}")
        return []

def test_full_pipeline(ocr_engine="tesseract"):
    """Test full pipeline with OCR."""
    print("\n" + "=" * 60)
    print(f"Testing Full CV Pipeline with {ocr_engine}")
    print("=" * 60)

    import cv2
    from visual_dom.core.domain.pipeline import VisualDOMPipeline

    samples_dir = project_root / "tests" / "samples"
    image_path = samples_dir / "login_screen.png"
    image = cv2.imread(str(image_path))

    try:
        pipeline = VisualDOMPipeline(
            ocr_engine=ocr_engine,
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
            vtype = elem["visual_type"]
            print(f"  {elem['id']}: {vtype:12s} '{text}'")

        return result

    except Exception as e:
        print(f"\nPipeline failed: {e}")
        return None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test OCR capabilities")
    parser.add_argument(
        "--engine", "-e",
        choices=["tesseract", "easyocr", "paddleocr"],
        default="tesseract",
        help="OCR engine to use (default: tesseract)"
    )
    args = parser.parse_args()

    ocr_engine = args.engine

    print("=" * 60)
    print("OCR TEST SUITE")
    print("=" * 60)
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")
    print(f"OCR Engine: {ocr_engine}")

    # Test dependencies
    if not test_pillow():
        print("\nPillow not working. Install with:")
        print("  pip install --force-reinstall Pillow")
        sys.exit(1)

    # Test OCR engine
    ocr_ready = False
    if ocr_engine == "tesseract":
        ocr_ready = test_tesseract()
    elif ocr_engine == "easyocr":
        ocr_ready = test_easyocr()
    else:
        print(f"\nTesting {ocr_engine}...")
        ocr_ready = True  # Will fail later if not available

    if not ocr_ready:
        print(f"\n{ocr_engine} not ready. See instructions above.")
        sys.exit(1)

    # Run OCR test
    results = test_ocr_detection(ocr_engine)

    if results:
        # Run full pipeline
        test_full_pipeline(ocr_engine)

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)
