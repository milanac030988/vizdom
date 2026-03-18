#!/usr/bin/env python3
"""
Test Vision-Language Models (VLMs) for GUI element detection.

Supported models:
- Qwen2-VL-2B/7B (Alibaba)
- Florence-2 (Microsoft) - Good for visual grounding
- Phi-3.5-Vision (Microsoft) - Small but capable
- MiniCPM-V-2.6 (OpenBMB) - Efficient multimodal
- InternVL2 (Shanghai AI Lab) - Strong visual understanding
- LLaVA-1.6 (Various) - Popular open-source VLM

These models can analyze screenshots and identify UI elements with positions.
"""

import argparse
import json
import time
import re
from pathlib import Path
from abc import ABC, abstractmethod


# Model registry
MODEL_REGISTRY = {
    # Qwen2-VL models
    "qwen2-vl-2b": {
        "hf_name": "Qwen/Qwen2-VL-2B-Instruct",
        "family": "qwen2-vl",
        "vram_gb": 5,
    },
    "qwen2-vl-7b": {
        "hf_name": "Qwen/Qwen2-VL-7B-Instruct",
        "family": "qwen2-vl",
        "vram_gb": 15,
    },
    # Florence-2 models (Microsoft) - excellent for grounding
    "florence-2-base": {
        "hf_name": "microsoft/Florence-2-base",
        "family": "florence2",
        "vram_gb": 2,
    },
    "florence-2-large": {
        "hf_name": "microsoft/Florence-2-large",
        "family": "florence2",
        "vram_gb": 4,
    },
    # Phi-3.5-Vision (Microsoft)
    "phi-3.5-vision": {
        "hf_name": "microsoft/Phi-3.5-vision-instruct",
        "family": "phi3-vision",
        "vram_gb": 8,
    },
    # MiniCPM-V (OpenBMB) - efficient
    "minicpm-v-2.6": {
        "hf_name": "openbmb/MiniCPM-V-2_6",
        "family": "minicpm-v",
        "vram_gb": 8,
    },
    # InternVL2 (Shanghai AI Lab)
    "internvl2-2b": {
        "hf_name": "OpenGVLab/InternVL2-2B",
        "family": "internvl2",
        "vram_gb": 5,
    },
    "internvl2-8b": {
        "hf_name": "OpenGVLab/InternVL2-8B",
        "family": "internvl2",
        "vram_gb": 16,
    },
}


class VLMBase(ABC):
    """Base class for Vision-Language Models."""

    def __init__(self, model_name: str, use_gpu: bool = True):
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.model = None
        self.processor = None

    @abstractmethod
    def load(self):
        """Load model and processor."""
        pass

    @abstractmethod
    def detect_elements(self, image_path: str, prompt: str = None) -> str:
        """Detect GUI elements in image."""
        pass

    def get_device(self):
        import torch
        if self.use_gpu and torch.cuda.is_available():
            return "cuda"
        return "cpu"


class Qwen2VLModel(VLMBase):
    """Qwen2-VL model family."""

    def load(self):
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        import torch

        print(f"Loading Qwen2-VL: {self.model_name}")

        device = self.get_device()
        dtype = torch.float16 if device == "cuda" else torch.float32

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else "cpu",
            trust_remote_code=True,
        )
        self.processor = AutoProcessor.from_pretrained(
            self.model_name, trust_remote_code=True
        )

    def detect_elements(self, image_path: str, prompt: str = None) -> str:
        from qwen_vl_utils import process_vision_info

        if prompt is None:
            prompt = self._get_default_prompt()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": f"file://{image_path}"},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=0.1,
            do_sample=True,
        )

        response = self.processor.batch_decode(
            [outputs[0][inputs["input_ids"].shape[1]:]],
            skip_special_tokens=True,
        )[0]

        return response

    def _get_default_prompt(self):
        return """Analyze this GUI screenshot and identify all interactive UI elements.
For each element, provide: type, bounding box [x1,y1,x2,y2], text content.
Output as JSON array:
[{"type": "button", "bbox": [x1,y1,x2,y2], "text": "OK"}, ...]
If no elements found, output: []"""


class Florence2Model(VLMBase):
    """Microsoft Florence-2 model - excellent for visual grounding."""

    def load(self):
        from transformers import AutoProcessor, AutoModelForCausalLM
        import torch

        print(f"Loading Florence-2: {self.model_name}")

        device = self.get_device()
        # Florence-2 works better with float32 to avoid dtype mismatches
        dtype = torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            trust_remote_code=True,
        )
        if device == "cuda":
            self.model = self.model.cuda()

        self.processor = AutoProcessor.from_pretrained(
            self.model_name, trust_remote_code=True
        )

        self.dtype = dtype

    def detect_elements(self, image_path: str, prompt: str = None) -> str:
        from PIL import Image

        image = Image.open(image_path).convert("RGB")

        # Florence-2 task prompts:
        # <OD> - Object Detection
        # <CAPTION_TO_PHRASE_GROUNDING> - Ground specific phrases
        # <OCR_WITH_REGION> - OCR with regions
        # <DENSE_REGION_CAPTION> - Dense captioning of regions
        # <REGION_PROPOSAL> - Region proposals

        results = {}

        # 1. Run Object Detection to find all objects
        task = "<OD>"
        inputs = self.processor(text=task, images=image, return_tensors="pt")
        if self.get_device() == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            num_beams=3,
        )

        od_result = self.processor.batch_decode(outputs, skip_special_tokens=False)[0]
        od_parsed = self.processor.post_process_generation(
            od_result, task=task, image_size=image.size
        )
        results["object_detection"] = od_parsed.get(task, {})

        # 2. Run Region Proposals to find clickable regions
        task = "<REGION_PROPOSAL>"
        inputs = self.processor(text=task, images=image, return_tensors="pt")
        if self.get_device() == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            num_beams=3,
        )

        region_result = self.processor.batch_decode(outputs, skip_special_tokens=False)[0]
        region_parsed = self.processor.post_process_generation(
            region_result, task=task, image_size=image.size
        )
        results["region_proposals"] = region_parsed.get(task, {})

        # 3. Run OCR with regions for text
        task = "<OCR_WITH_REGION>"
        inputs = self.processor(text=task, images=image, return_tensors="pt")
        if self.get_device() == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            num_beams=3,
        )

        ocr_result = self.processor.batch_decode(outputs, skip_special_tokens=False)[0]
        ocr_parsed = self.processor.post_process_generation(
            ocr_result, task=task, image_size=image.size
        )
        results["ocr"] = ocr_parsed.get(task, {})

        return json.dumps(results, indent=2)


class Phi3VisionModel(VLMBase):
    """Microsoft Phi-3.5-Vision model."""

    def load(self):
        from transformers import AutoModelForCausalLM, AutoProcessor
        import torch

        print(f"Loading Phi-3.5-Vision: {self.model_name}")

        device = self.get_device()
        dtype = torch.float16 if device == "cuda" else torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else None,
            trust_remote_code=True,
            _attn_implementation="eager",
        )

        self.processor = AutoProcessor.from_pretrained(
            self.model_name, trust_remote_code=True
        )

    def detect_elements(self, image_path: str, prompt: str = None) -> str:
        from PIL import Image

        if prompt is None:
            prompt = """<|image_1|>
Analyze this GUI screenshot and list all UI elements with their bounding boxes.
Format: [{"type": "button", "bbox": [x1,y1,x2,y2], "text": "label"}, ...]"""

        image = Image.open(image_path).convert("RGB")

        messages = [
            {"role": "user", "content": prompt}
        ]

        inputs = self.processor(
            text=self.processor.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            ),
            images=[image],
            return_tensors="pt",
        )

        if self.get_device() == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=0.1,
            do_sample=True,
        )

        response = self.processor.batch_decode(
            outputs[:, inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )[0]

        return response


class MiniCPMVModel(VLMBase):
    """OpenBMB MiniCPM-V model - efficient multimodal."""

    def load(self):
        from transformers import AutoModel, AutoTokenizer
        import torch

        print(f"Loading MiniCPM-V: {self.model_name}")

        device = self.get_device()
        dtype = torch.float16 if device == "cuda" else torch.float32

        self.model = AutoModel.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            trust_remote_code=True,
        )
        if device == "cuda":
            self.model = self.model.cuda()
        self.model.eval()

        self.processor = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )

    def detect_elements(self, image_path: str, prompt: str = None) -> str:
        from PIL import Image

        if prompt is None:
            prompt = """Analyze this GUI screenshot and identify all UI elements.
Output as JSON: [{"type": "button", "bbox": [x1,y1,x2,y2], "text": "label"}, ...]"""

        image = Image.open(image_path).convert("RGB")

        msgs = [{"role": "user", "content": [image, prompt]}]

        response = self.model.chat(
            image=None,
            msgs=msgs,
            tokenizer=self.processor,
            max_new_tokens=2048,
            temperature=0.1,
        )

        return response


class InternVL2Model(VLMBase):
    """InternVL2 model family."""

    def load(self):
        from transformers import AutoModel, AutoTokenizer
        import torch

        print(f"Loading InternVL2: {self.model_name}")

        device = self.get_device()
        dtype = torch.float16 if device == "cuda" else torch.float32

        self.model = AutoModel.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            trust_remote_code=True,
            device_map="auto" if device == "cuda" else None,
        )

        self.processor = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )

    def detect_elements(self, image_path: str, prompt: str = None) -> str:
        from PIL import Image
        import torchvision.transforms as T
        from torchvision.transforms.functional import InterpolationMode

        if prompt is None:
            prompt = """<image>
Analyze this GUI screenshot and list all interactive UI elements.
For each element provide: type, bounding box [x1,y1,x2,y2], text.
Output as JSON array."""

        image = Image.open(image_path).convert("RGB")

        # InternVL2 uses specific image preprocessing
        def build_transform():
            return T.Compose([
                T.Lambda(lambda img: img.convert('RGB')),
                T.Resize((448, 448), interpolation=InterpolationMode.BICUBIC),
                T.ToTensor(),
                T.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))
            ])

        transform = build_transform()
        pixel_values = transform(image).unsqueeze(0)

        if self.get_device() == "cuda":
            pixel_values = pixel_values.cuda().half()

        generation_config = dict(max_new_tokens=2048, do_sample=False)

        response = self.model.chat(
            self.processor,
            pixel_values,
            prompt,
            generation_config,
        )

        return response


def get_model_class(family: str):
    """Get model class by family name."""
    classes = {
        "qwen2-vl": Qwen2VLModel,
        "florence2": Florence2Model,
        "phi3-vision": Phi3VisionModel,
        "minicpm-v": MiniCPMVModel,
        "internvl2": InternVL2Model,
    }
    return classes.get(family)


def load_model(model_key: str, use_gpu: bool = True):
    """Load a VLM model by key."""
    if model_key not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(MODEL_REGISTRY.keys())}")

    config = MODEL_REGISTRY[model_key]
    model_class = get_model_class(config["family"])

    if model_class is None:
        raise ValueError(f"No implementation for family: {config['family']}")

    model = model_class(config["hf_name"], use_gpu=use_gpu)

    start = time.time()
    model.load()
    print(f"Model loaded in {time.time() - start:.1f}s")

    return model


def parse_json_response(response: str) -> list:
    """Try to parse JSON from model response."""
    # Try direct parse
    try:
        data = json.loads(response)

        # Handle Florence-2 format
        if isinstance(data, dict):
            elements = []

            # Parse dense region captions (UI elements with descriptions)
            if "dense_regions" in data:
                dense_data = data["dense_regions"]
                bboxes = dense_data.get("bboxes", [])
                labels = dense_data.get("labels", [])
                for i, bbox in enumerate(bboxes):
                    label = labels[i] if i < len(labels) else "region"
                    # Classify based on label content
                    label_lower = label.lower()
                    if "button" in label_lower or "key" in label_lower:
                        elem_type = "button"
                    elif "input" in label_lower or "field" in label_lower or "text box" in label_lower:
                        elem_type = "input"
                    elif "icon" in label_lower:
                        elem_type = "icon"
                    else:
                        elem_type = "region"
                    elements.append({
                        "type": elem_type,
                        "bbox": [int(b) for b in bbox],
                        "text": label,
                    })

            # Parse grounded buttons
            if "grounded_buttons" in data:
                grounded_data = data["grounded_buttons"]
                bboxes = grounded_data.get("bboxes", [])
                labels = grounded_data.get("labels", [])
                for i, bbox in enumerate(bboxes):
                    label = labels[i] if i < len(labels) else "button"
                    elements.append({
                        "type": "button",
                        "bbox": [int(b) for b in bbox],
                        "text": label,
                    })

            # Parse object detection results (from <OD> task)
            if "object_detection" in data:
                obj_data = data["object_detection"]
                bboxes = obj_data.get("bboxes", [])
                labels = obj_data.get("labels", [])
                for i, bbox in enumerate(bboxes):
                    label = labels[i] if i < len(labels) else "object"
                    elements.append({
                        "type": "object",
                        "bbox": [int(b) for b in bbox],
                        "text": label,
                    })

            # Parse region proposals (from <REGION_PROPOSAL> task)
            if "region_proposals" in data:
                region_data = data["region_proposals"]
                bboxes = region_data.get("bboxes", [])
                labels = region_data.get("labels", [])
                for i, bbox in enumerate(bboxes):
                    label = labels[i] if i < len(labels) else f"region_{i}"
                    elements.append({
                        "type": "region",
                        "bbox": [int(b) for b in bbox],
                        "text": label,
                    })

            # Parse OCR results and create both text and button estimates
            if "ocr" in data:
                ocr_data = data["ocr"]
                quad_boxes = ocr_data.get("quad_boxes", [])
                labels = ocr_data.get("labels", [])
                for i, quad in enumerate(quad_boxes):
                    # Convert quad (8 points) to bbox (4 points)
                    if len(quad) == 8:
                        x_coords = [quad[j] for j in [0, 2, 4, 6]]
                        y_coords = [quad[j] for j in [1, 3, 5, 7]]
                        text_bbox = [int(min(x_coords)), int(min(y_coords)),
                                     int(max(x_coords)), int(max(y_coords))]
                        text = labels[i] if i < len(labels) else ""

                        # Add text element
                        elements.append({
                            "type": "text",
                            "bbox": text_bbox,
                            "text": text,
                        })

                        # Create expanded button estimate from text bbox
                        # Expand by ~50% of text height to approximate button area
                        text_h = text_bbox[3] - text_bbox[1]
                        text_w = text_bbox[2] - text_bbox[0]
                        padding_x = max(text_h // 2, 5)  # Use text height as guide
                        padding_y = max(text_h // 2, 3)
                        button_bbox = [
                            max(0, text_bbox[0] - padding_x),
                            max(0, text_bbox[1] - padding_y),
                            text_bbox[2] + padding_x,
                            text_bbox[3] + padding_y
                        ]
                        elements.append({
                            "type": "button",
                            "bbox": button_bbox,
                            "text": text,
                        })

            if elements:
                return elements

        # Handle list format
        if isinstance(data, list):
            return data

    except:
        pass

    # Try to extract JSON array
    match = re.search(r'\[.*\]', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass

    return []


def visualize_results(image_path: str, elements: list, output_path: str):
    """Draw detected elements on image."""
    import cv2

    image = cv2.imread(image_path)
    if image is None:
        print(f"Could not load image: {image_path}")
        return

    h, w = image.shape[:2]

    colors = {
        "button": (0, 255, 0),      # Green
        "input": (255, 0, 0),        # Blue
        "text": (0, 165, 255),       # Orange
        "icon": (255, 255, 0),       # Cyan
        "checkbox": (255, 0, 255),   # Magenta
        "region": (128, 128, 128),   # Gray
        "object": (0, 255, 255),     # Yellow
    }

    valid_count = 0
    for elem in elements:
        bbox = elem.get("bbox", elem.get("bounding_box", []))
        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = [int(b) for b in bbox]

        # Check if bbox is within image bounds
        if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            continue

        valid_count += 1
        elem_type = elem.get("type", "unknown").lower()
        text = elem.get("text", "")

        color = colors.get(elem_type, (128, 128, 128))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

        label = f"{elem_type}"
        if text:
            label += f": {text[:15]}"
        cv2.putText(image, label, (x1, y1 - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    cv2.imwrite(output_path, image)
    print(f"Visualization saved: {output_path} ({valid_count} valid elements)")


def main():
    parser = argparse.ArgumentParser(
        description="Test Vision-Language Models for GUI element detection"
    )
    parser.add_argument("image", help="Path to GUI screenshot")
    parser.add_argument(
        "--model", "-m",
        choices=list(MODEL_REGISTRY.keys()),
        default="florence-2-base",
        help=f"Model to test (default: florence-2-base)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output visualization path"
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        default=True,
        help="Use GPU (default: True)"
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Force CPU inference"
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models and exit"
    )

    args = parser.parse_args()

    # List models
    if args.list_models:
        print("\nAvailable models:")
        print("-" * 60)
        for key, config in MODEL_REGISTRY.items():
            print(f"  {key:20} - {config['hf_name']}")
            print(f"                       VRAM: ~{config['vram_gb']}GB")
        return

    use_gpu = args.gpu and not args.no_gpu

    # Load model
    print(f"\n{'='*60}")
    print(f"Testing: {args.model}")
    print(f"Image: {args.image}")
    print(f"Device: {'GPU' if use_gpu else 'CPU'}")
    print(f"{'='*60}\n")

    model = load_model(args.model, use_gpu=use_gpu)

    # Get absolute path
    image_path = str(Path(args.image).absolute())

    # Run detection
    print("\nDetecting GUI elements...")
    start = time.time()
    response = model.detect_elements(image_path)
    elapsed = time.time() - start
    print(f"Detection completed in {elapsed:.1f}s")

    # Show response
    print(f"\n{'='*60}")
    print("Model Response:")
    print(f"{'='*60}")
    print(response[:2000] + "..." if len(response) > 2000 else response)

    # Try to parse elements
    elements = parse_json_response(response)
    if elements:
        print(f"\nParsed {len(elements)} elements")

        # Check for valid bboxes
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size

        valid = [e for e in elements if all(
            0 <= c <= max(w, h) for c in e.get("bbox", e.get("bounding_box", [0,0,0,0]))
        )]
        print(f"Valid elements (within image {w}x{h}): {len(valid)}")

        if args.output and valid:
            visualize_results(image_path, valid, args.output)

    print("\nDone!")


if __name__ == "__main__":
    import sys
    import io
    # Handle Unicode on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
