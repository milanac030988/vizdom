#!/usr/bin/env python3
"""
Test Qwen2-VL models for GUI element detection.

Tests:
- Qwen/Qwen2-VL-2B-Instruct (smaller, faster)
- Qwen/Qwen2-VL-7B-Instruct (larger, more accurate)

These vision-language models can analyze screenshots and identify UI elements
with their positions.
"""

import argparse
import json
import time
from pathlib import Path


def load_model(model_name: str, use_gpu: bool = True, use_flash_attn: bool = False):
    """Load Qwen2-VL model and processor."""
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    import torch

    print(f"Loading model: {model_name}")
    print(f"Device: {'GPU (CUDA)' if use_gpu and torch.cuda.is_available() else 'CPU'}")
    start = time.time()

    # Model configuration
    if use_gpu and torch.cuda.is_available():
        model_kwargs = {
            "torch_dtype": torch.float16,
            "device_map": "auto",
            "trust_remote_code": True,
        }
    else:
        model_kwargs = {
            "torch_dtype": torch.float32,
            "device_map": "cpu",
            "trust_remote_code": True,
        }

    # Use flash attention if available (faster inference)
    if use_flash_attn and use_gpu:
        model_kwargs["attn_implementation"] = "flash_attention_2"

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_name,
        **model_kwargs
    )

    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

    print(f"Model loaded in {time.time() - start:.1f}s")
    return model, processor


def detect_gui_elements(model, processor, image_path: str, prompt: str = None):
    """
    Use Qwen2-VL to detect GUI elements in a screenshot.

    Args:
        model: Qwen2-VL model
        processor: Model processor
        image_path: Path to screenshot
        prompt: Custom prompt (optional)

    Returns:
        Model response with detected elements
    """
    from qwen_vl_utils import process_vision_info
    from PIL import Image

    # Default prompt for GUI element detection
    if prompt is None:
        prompt = """Analyze this GUI screenshot and identify all interactive UI elements.

For each element, provide:
1. Element type (button, input_field, checkbox, dropdown, icon, text_label, etc.)
2. Bounding box coordinates as [x1, y1, x2, y2] in pixels
3. Text content (if any)
4. Brief description

Output as a JSON array:
[
  {"type": "button", "bbox": [x1, y1, x2, y2], "text": "Submit", "description": "Submit button"},
  ...
]

Be thorough and identify ALL clickable/interactive elements."""

    # Prepare message with image
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": f"file://{image_path}"},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    # Process input
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    image_inputs, video_inputs = process_vision_info(messages)

    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    # Generate response
    print("Generating response...")
    start = time.time()

    generated_ids = model.generate(
        **inputs,
        max_new_tokens=2048,
        temperature=0.1,
        do_sample=True,
    )

    # Decode response
    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    response = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]

    print(f"Generated in {time.time() - start:.1f}s")
    return response


def detect_with_grounding(model, processor, image_path: str):
    """
    Use Qwen2-VL's grounding capability to detect elements with precise bboxes.

    Qwen2-VL supports special tokens for grounding:
    - <|box_start|>(x1,y1),(x2,y2)<|box_end|> for bounding boxes
    - <|object_ref_start|>object<|object_ref_end|> for object references
    """
    from qwen_vl_utils import process_vision_info

    # Grounding prompt - asks model to output coordinates
    prompt = """Detect all UI elements in this screenshot. For each element, output:
<|object_ref_start|>element_type: text_content<|object_ref_end|><|box_start|>(x1,y1),(x2,y2)<|box_end|>

Example:
<|object_ref_start|>button: OK<|object_ref_end|><|box_start|>(100,200),(150,230)<|box_end|>

List ALL buttons, input fields, checkboxes, icons, and text labels:"""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": f"file://{image_path}"},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    image_inputs, video_inputs = process_vision_info(messages)

    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    print("Generating grounded response...")
    start = time.time()

    generated_ids = model.generate(
        **inputs,
        max_new_tokens=2048,
        temperature=0.1,
        do_sample=True,
    )

    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    response = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=False,  # Keep special tokens for parsing
        clean_up_tokenization_spaces=False,
    )[0]

    print(f"Generated in {time.time() - start:.1f}s")
    return response


def parse_grounded_response(response: str, image_size: tuple):
    """Parse grounded response to extract elements with coordinates."""
    import re

    elements = []

    # Pattern for grounded outputs
    # <|object_ref_start|>type: text<|object_ref_end|><|box_start|>(x1,y1),(x2,y2)<|box_end|>
    pattern = r'<\|object_ref_start\|>([^<]+)<\|object_ref_end\|><\|box_start\|>\((\d+),(\d+)\),\((\d+),(\d+)\)<\|box_end\|>'

    matches = re.findall(pattern, response)

    for match in matches:
        ref_text = match[0]
        x1, y1, x2, y2 = int(match[1]), int(match[2]), int(match[3]), int(match[4])

        # Parse type and text from reference
        if ":" in ref_text:
            elem_type, text = ref_text.split(":", 1)
            elem_type = elem_type.strip()
            text = text.strip()
        else:
            elem_type = "unknown"
            text = ref_text.strip()

        elements.append({
            "type": elem_type,
            "text": text,
            "bbox": [x1, y1, x2, y2],
        })

    return elements


def visualize_detections(image_path: str, elements: list, output_path: str):
    """Draw detected elements on the image."""
    import cv2

    image = cv2.imread(image_path)
    if image is None:
        print(f"Could not load image: {image_path}")
        return

    colors = {
        "button": (0, 255, 0),
        "input_field": (255, 0, 0),
        "checkbox": (255, 0, 255),
        "icon": (255, 255, 0),
        "text": (0, 165, 255),
        "unknown": (128, 128, 128),
    }

    for elem in elements:
        bbox = elem.get("bbox", [])
        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox
        elem_type = elem.get("type", "unknown").lower()
        text = elem.get("text", "")

        color = colors.get(elem_type, colors["unknown"])
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

        label = f"{elem_type}"
        if text:
            label += f": {text[:20]}"

        cv2.putText(image, label, (x1, y1 - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    cv2.imwrite(output_path, image)
    print(f"Visualization saved to: {output_path}")


def test_simple_detection(model, processor, image_path: str):
    """Simple test: ask model to describe what it sees."""
    from qwen_vl_utils import process_vision_info

    prompt = "What UI elements do you see in this screenshot? List them briefly."

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": f"file://{image_path}"},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    image_inputs, video_inputs = process_vision_info(messages)

    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    generated_ids = model.generate(
        **inputs,
        max_new_tokens=512,
        temperature=0.1,
        do_sample=True,
    )

    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    response = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]

    return response


def main():
    parser = argparse.ArgumentParser(
        description="Test Qwen2-VL for GUI element detection"
    )
    parser.add_argument(
        "image",
        help="Path to GUI screenshot"
    )
    parser.add_argument(
        "--model", "-m",
        choices=["2b", "7b"],
        default="2b",
        help="Model size: 2b or 7b (default: 2b)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output visualization path"
    )
    parser.add_argument(
        "--mode",
        choices=["simple", "json", "grounding"],
        default="simple",
        help="Detection mode (default: simple)"
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        default=True,
        help="Use GPU for inference (default: True)"
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Force CPU inference (disable GPU)"
    )
    parser.add_argument(
        "--flash-attn",
        action="store_true",
        help="Use flash attention (requires flash-attn package)"
    )

    args = parser.parse_args()

    # Handle GPU flag
    use_gpu = args.gpu and not args.no_gpu

    # Select model
    if args.model == "2b":
        model_name = "Qwen/Qwen2-VL-2B-Instruct"
    else:
        model_name = "Qwen/Qwen2-VL-7B-Instruct"

    # Load model
    model, processor = load_model(model_name, use_gpu=use_gpu, use_flash_attn=args.flash_attn)

    # Get absolute image path
    image_path = str(Path(args.image).absolute())
    print(f"\nProcessing: {image_path}")

    if args.mode == "simple":
        # Simple description
        print("\n=== Simple Detection ===")
        response = test_simple_detection(model, processor, image_path)
        print("\nModel Response:")
        print(response)

    elif args.mode == "json":
        # JSON output
        print("\n=== JSON Detection ===")
        response = detect_gui_elements(model, processor, image_path)
        print("\nModel Response:")
        print(response)

        # Try to parse JSON
        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                elements = json.loads(json_match.group())
                print(f"\nParsed {len(elements)} elements")

                if args.output:
                    visualize_detections(image_path, elements, args.output)
        except json.JSONDecodeError as e:
            print(f"Could not parse JSON: {e}")

    elif args.mode == "grounding":
        # Grounding with special tokens
        print("\n=== Grounding Detection ===")
        response = detect_with_grounding(model, processor, image_path)
        print("\nRaw Response:")
        print(response[:1000] + "..." if len(response) > 1000 else response)

        # Parse grounded response
        from PIL import Image
        img = Image.open(image_path)
        elements = parse_grounded_response(response, img.size)
        print(f"\nParsed {len(elements)} grounded elements:")
        for elem in elements[:10]:  # Show first 10
            print(f"  {elem}")

        if args.output and elements:
            visualize_detections(image_path, elements, args.output)

    print("\nDone!")


if __name__ == "__main__":
    import sys
    import io
    # Handle Unicode output on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
