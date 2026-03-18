"""
CV Model registry for UI element detection.

Two approaches:
1. Traditional CV (no training needed) - edge detection, contours
2. Deep Learning detectors (need training) - YOLO, Faster R-CNN

Recommended: YOLOv8 for speed, or RT-DETR for accuracy
"""

from dataclasses import dataclass
from typing import Dict, List
from enum import Enum


class DetectorType(Enum):
    """Types of UI element detectors."""
    TRADITIONAL = "traditional"  # No ML, uses OpenCV
    YOLO = "yolo"               # Fast, good for real-time
    RTDETR = "rt-detr"          # Accurate, transformer-based
    FASTER_RCNN = "faster-rcnn" # Classic, very accurate


@dataclass
class CVModelConfig:
    """Configuration for CV detection model."""
    name: str
    detector_type: DetectorType
    model_id: str  # HuggingFace or Ultralytics model ID
    input_size: tuple  # (width, height)
    num_classes: int
    class_names: List[str]
    memory_gb: float
    notes: str


# UI Element classes to detect
UI_ELEMENT_CLASSES = [
    "button",
    "text",
    "icon",
    "input_field",
    "checkbox",
    "radio_button",
    "toggle",
    "slider",
    "dropdown",
    "image",
    "container",
    "toolbar",
    "navbar",
    "card",
    "list_item",
]


CV_MODEL_REGISTRY: Dict[str, CVModelConfig] = {
    # === NO TRAINING NEEDED ===
    "traditional": CVModelConfig(
        name="Traditional CV",
        detector_type=DetectorType.TRADITIONAL,
        model_id="none",
        input_size=(0, 0),
        num_classes=0,
        class_names=[],
        memory_gb=0.5,
        notes="No ML. Uses edge detection, contours, color analysis. Good baseline."
    ),

    # === RECOMMENDED FOR TRAINING ===
    "yolov8n": CVModelConfig(
        name="YOLOv8 Nano",
        detector_type=DetectorType.YOLO,
        model_id="yolov8n.pt",
        input_size=(640, 640),
        num_classes=len(UI_ELEMENT_CLASSES),
        class_names=UI_ELEMENT_CLASSES,
        memory_gb=2.0,
        notes="Fastest. Good for real-time. Easy to train with Ultralytics."
    ),

    "yolov8s": CVModelConfig(
        name="YOLOv8 Small",
        detector_type=DetectorType.YOLO,
        model_id="yolov8s.pt",
        input_size=(640, 640),
        num_classes=len(UI_ELEMENT_CLASSES),
        class_names=UI_ELEMENT_CLASSES,
        memory_gb=4.0,
        notes="Good balance of speed and accuracy. Recommended starting point."
    ),

    "yolov8m": CVModelConfig(
        name="YOLOv8 Medium",
        detector_type=DetectorType.YOLO,
        model_id="yolov8m.pt",
        input_size=(640, 640),
        num_classes=len(UI_ELEMENT_CLASSES),
        class_names=UI_ELEMENT_CLASSES,
        memory_gb=6.0,
        notes="More accurate than small. Good for production."
    ),

    "rt-detr-l": CVModelConfig(
        name="RT-DETR Large",
        detector_type=DetectorType.RTDETR,
        model_id="rtdetr-l.pt",
        input_size=(640, 640),
        num_classes=len(UI_ELEMENT_CLASSES),
        class_names=UI_ELEMENT_CLASSES,
        memory_gb=8.0,
        notes="Transformer-based. Most accurate. Slower than YOLO."
    ),
}


def get_cv_model_config(model_key: str) -> CVModelConfig:
    """Get CV model configuration by key."""
    if model_key not in CV_MODEL_REGISTRY:
        available = ", ".join(CV_MODEL_REGISTRY.keys())
        raise ValueError(f"Unknown model: {model_key}. Available: {available}")
    return CV_MODEL_REGISTRY[model_key]


def list_cv_models() -> None:
    """Print available CV models."""
    print("Available CV models for UI element detection:\n")
    for key, config in CV_MODEL_REGISTRY.items():
        print(f"  {key}:")
        print(f"    Type: {config.detector_type.value}")
        print(f"    Memory: ~{config.memory_gb}GB")
        print(f"    Notes: {config.notes}")
        print()


if __name__ == "__main__":
    list_cv_models()
