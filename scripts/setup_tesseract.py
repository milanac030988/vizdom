"""
Tesseract OCR Setup Helper for Windows.

This script helps you set up Tesseract OCR for the Visual DOM pipeline.
"""

import os
import sys
import subprocess
from pathlib import Path

# Common Tesseract installation paths on Windows
TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"D:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
]


def find_tesseract():
    """Find Tesseract executable."""
    # Check PATH first
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return "tesseract"
    except FileNotFoundError:
        pass

    # Check common paths
    for path in TESSERACT_PATHS:
        if os.path.exists(path):
            return path

    return None


def test_tesseract(tesseract_path):
    """Test Tesseract installation."""
    try:
        result = subprocess.run(
            [tesseract_path, "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"Tesseract found: {version}")
            return True
    except Exception as e:
        print(f"Error testing Tesseract: {e}")
    return False


def configure_pytesseract(tesseract_path):
    """Configure pytesseract to use the found Tesseract."""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        print(f"Configured pytesseract to use: {tesseract_path}")
        return True
    except ImportError:
        print("pytesseract not installed. Run: pip install pytesseract")
        return False


def main():
    print("=" * 60)
    print("Tesseract OCR Setup Helper")
    print("=" * 60)

    # Check if Tesseract is installed
    tesseract_path = find_tesseract()

    if tesseract_path:
        print(f"\nTesseract found at: {tesseract_path}")
        if test_tesseract(tesseract_path):
            configure_pytesseract(tesseract_path)
            print("\nTesseract is ready to use!")
            print("\nTo use in the pipeline:")
            print("  from visual_dom.adapters.outbound.ocr.text_detector import TextDetector")
            print("  detector = TextDetector(ocr_engine='tesseract')")
            return 0
    else:
        print("\nTesseract OCR is NOT installed.")
        print("\n" + "=" * 60)
        print("INSTALLATION INSTRUCTIONS")
        print("=" * 60)
        print("""
1. Download Tesseract for Windows:
   https://github.com/UB-Mannheim/tesseract/wiki

2. Run the installer (choose the 64-bit version)
   - Default path: C:\\Program Files\\Tesseract-OCR

3. During installation, select additional languages if needed
   (English is included by default)

4. After installation, run this script again to verify.

Alternative: Install via Chocolatey (if you have it):
   choco install tesseract

After installation, you may need to add Tesseract to PATH:
   - Add 'C:\\Program Files\\Tesseract-OCR' to your system PATH
   - Or the script will auto-detect common installation paths
""")
        return 1


if __name__ == "__main__":
    sys.exit(main())
