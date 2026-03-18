"""
Run inference with trained YOLO model for UI element detection.

Usage:
    python scripts/training/cv/inference_yolo.py --model models/cv_detection/best.pt --image screenshot.png
"""

import argparse
from pathlib import Path
from typing import List, Dict, Any
import json

try:
    from ultralytics import YOLO
    import cv2
except ImportError:
    print("Please install: pip install ultralytics opencv-python")
    exit(1)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from models.configs.cv_model_registry import UI_ELEMENT_CLASSES


class UIElementDetector:
    """Wrapper for UI element detection using trained YOLO model."""

    def __init__(self, model_path: str, confidence: float = 0.5):
        """
        Initialize detector.

        Args:
            model_path: Path to trained YOLO model (.pt file)
            confidence: Minimum confidence threshold
        """
        self.model_path = model_path
        self.confidence = confidence
        self._model = None

    def load(self):
        """Load model."""
        if self._model is None:
            self._model = YOLO(self.model_path)
            print(f"Loaded model from {self.model_path}")

    def detect(self, image) -> List[Dict[str, Any]]:
        """
        Detect UI elements in image.

        Args:
            image: Path to image or numpy array (BGR)

        Returns:
            List of detected elements with bounds and class
        """
        self.load()

        results = self._model(image, conf=self.confidence, verbose=False)

        elements = []
        for i, result in enumerate(results):
            boxes = result.boxes

            for j, box in enumerate(boxes):
                # Get bounding box
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                # Get class and confidence
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())

                class_name = UI_ELEMENT_CLASSES[cls_id] if cls_id < len(UI_ELEMENT_CLASSES) else "unknown"

                elements.append({
                    "id": f"E{len(elements) + 1}",
                    "bounds": [int(x1), int(y1), int(x2), int(y2)],
                    "visual_type": class_name,
                    "confidence": round(conf, 3)
                })

        return elements

    def detect_and_visualize(self, image_path: str, output_path: str = None) -> List[Dict]:
        """Detect elements and save visualization."""
        self.load()

        # Run detection
        results = self._model(image_path, conf=self.confidence)

        # Get elements
        elements = self.detect(image_path)

        # Save visualization
        if output_path:
            result_img = results[0].plot()
            cv2.imwrite(output_path, result_img)
            print(f"Visualization saved to {output_path}")

        return elements


def main():
    parser = argparse.ArgumentParser(description="Detect UI elements")
    parser.add_argument("--model", type=str, required=True, help="Path to model")
    parser.add_argument("--image", type=str, required=True, help="Input image")
    parser.add_argument("--output", type=str, help="Output visualization")
    parser.add_argument("--json", type=str, help="Output JSON file")
    parser.add_argument("--conf", type=float, default=0.5, help="Confidence threshold")
    args = parser.parse_args()

    detector = UIElementDetector(args.model, args.conf)

    if args.output:
        elements = detector.detect_and_visualize(args.image, args.output)
    else:
        elements = detector.detect(args.image)

    print(f"\nDetected {len(elements)} elements:")
    for elem in elements:
        print(f"  {elem['id']}: {elem['visual_type']} ({elem['confidence']:.2f}) at {elem['bounds']}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"elements": elements}, f, indent=2)
        print(f"\nSaved to {args.json}")


if __name__ == "__main__":
    main()
