"""
Capture screenshots for annotation.

Supports:
- Desktop screenshots (pyautogui)
- Android screenshots (ADB)
- Batch capture with naming
- Auto-organize by app/screen

Usage:
    # Single desktop screenshot
    python scripts/annotation/capture_screenshots.py --platform desktop --output data/raw/screenshots

    # Android screenshot
    python scripts/annotation/capture_screenshots.py --platform android --output data/raw/screenshots

    # Batch capture (press Enter for each, 'q' to quit)
    python scripts/annotation/capture_screenshots.py --platform desktop --batch --prefix login_flow
"""

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import subprocess


def capture_desktop(output_path: str, region: Optional[tuple] = None) -> str:
    """Capture desktop screenshot using pyautogui."""
    try:
        import pyautogui
        from PIL import Image
    except ImportError:
        print("Please install: pip install pyautogui Pillow")
        return None

    if region:
        screenshot = pyautogui.screenshot(region=region)
    else:
        screenshot = pyautogui.screenshot()

    screenshot.save(output_path)
    return output_path


def capture_android(output_path: str, device: Optional[str] = None) -> str:
    """Capture Android screenshot using ADB."""
    adb_cmd = ["adb"]
    if device:
        adb_cmd.extend(["-s", device])

    # Capture on device
    device_path = "/sdcard/screenshot_temp.png"
    subprocess.run(adb_cmd + ["shell", "screencap", "-p", device_path], check=True)

    # Pull to local
    subprocess.run(adb_cmd + ["pull", device_path, output_path], check=True)

    # Clean up device
    subprocess.run(adb_cmd + ["shell", "rm", device_path], check=True)

    return output_path


def generate_filename(prefix: str, output_dir: Path, index: int = None) -> str:
    """Generate unique filename for screenshot."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if index is not None:
        filename = f"{prefix}_{index:03d}_{timestamp}.png"
    else:
        filename = f"{prefix}_{timestamp}.png"

    return str(output_dir / filename)


def batch_capture(
    platform: str,
    output_dir: Path,
    prefix: str,
    device: Optional[str] = None,
    delay: float = 0.5
):
    """Interactive batch capture mode."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 50)
    print("BATCH CAPTURE MODE")
    print("=" * 50)
    print(f"Platform: {platform}")
    print(f"Output: {output_dir}")
    print(f"Prefix: {prefix}")
    print("\nControls:")
    print("  [Enter] - Capture screenshot")
    print("  [s]     - Skip (don't save)")
    print("  [q]     - Quit")
    print("=" * 50 + "\n")

    index = 1
    captured = []

    while True:
        user_input = input(f"Screenshot {index} > ").strip().lower()

        if user_input == 'q':
            break
        elif user_input == 's':
            print("  Skipped")
            continue

        # Delay before capture (for UI to settle)
        time.sleep(delay)

        # Generate filename
        output_path = generate_filename(prefix, output_dir, index)

        # Capture
        try:
            if platform == "android":
                capture_android(output_path, device)
            else:
                capture_desktop(output_path)

            print(f"  Saved: {Path(output_path).name}")
            captured.append(output_path)
            index += 1

        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nCaptured {len(captured)} screenshots")
    return captured


def list_android_devices() -> list:
    """List connected Android devices."""
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().split("\n")[1:]
        devices = [line.split("\t")[0] for line in lines if "\tdevice" in line]
        return devices
    except:
        return []


def main():
    parser = argparse.ArgumentParser(description="Capture screenshots for annotation")
    parser.add_argument(
        "--platform",
        choices=["desktop", "android"],
        default="desktop",
        help="Capture platform"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/raw/screenshots",
        help="Output directory"
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="screenshot",
        help="Filename prefix"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Interactive batch capture mode"
    )
    parser.add_argument(
        "--device",
        type=str,
        help="Android device serial (for multiple devices)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay before capture in seconds"
    )
    parser.add_argument(
        "--region",
        type=str,
        help="Desktop region to capture: x,y,width,height"
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse region if provided
    region = None
    if args.region:
        region = tuple(map(int, args.region.split(",")))

    # List Android devices if platform is android
    if args.platform == "android":
        devices = list_android_devices()
        if not devices:
            print("No Android devices connected. Please connect a device and enable USB debugging.")
            return
        print(f"Found Android devices: {devices}")
        if not args.device and len(devices) > 1:
            print(f"Multiple devices found. Use --device to specify.")
            return

    # Batch or single capture
    if args.batch:
        batch_capture(
            args.platform,
            output_dir,
            args.prefix,
            args.device,
            args.delay
        )
    else:
        output_path = generate_filename(args.prefix, output_dir)

        time.sleep(args.delay)

        if args.platform == "android":
            capture_android(output_path, args.device)
        else:
            capture_desktop(output_path, region)

        print(f"Screenshot saved: {output_path}")


if __name__ == "__main__":
    main()
