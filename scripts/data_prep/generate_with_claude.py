#!/usr/bin/env python
"""
Generate synthetic UI datasets using Claude Code as the UI designer.

Usage:
    # Generate 10 UIs
    python scripts/data_prep/generate_with_claude.py -n 10

    # Specific app type
    python scripts/data_prep/generate_with_claude.py -n 5 --app-type "car infotainment"

    # Custom resolution
    python scripts/data_prep/generate_with_claude.py -n 10 --width 1920 --height 1080
"""

import sys
import os
import json
import subprocess
import argparse
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from synthetic_ui.llm_renderer import LLMRenderer
from synthetic_ui.llm_designer import APP_TYPES
import numpy as np
import cv2


CLAUDE_PROMPT_TEMPLATE = """You are a UI designer. Generate a JSON layout for a "{app_type}" application screen.

Canvas size: {width}x{height} pixels.

Output ONLY a valid JSON object with this structure:
{{
  "title": "App Title",
  "theme": "light" or "dark",
  "elements": [
    {{"type": "container", "x": 0, "y": 0, "w": {width}, "h": 40, "elements": [
      {{"type": "text", "text": "Title", "x": 15, "y": 10, "w": 200, "h": 24}}
    ]}},
    {{"type": "text", "text": "Label", "x": 20, "y": 60, "w": 100, "h": 16}},
    {{"type": "input_field", "text": "placeholder", "x": 20, "y": 80, "w": 300, "h": 32}},
    {{"type": "button", "text": "Submit", "x": 20, "y": 130, "w": 120, "h": 36}},
    {{"type": "checkbox", "text": "Remember me", "x": 20, "y": 180, "w": 150, "h": 20}},
    {{"type": "dropdown", "text": "Select...", "x": 20, "y": 210, "w": 200, "h": 30}},
    {{"type": "separator", "x": 20, "y": 250, "w": 760, "h": 1}},
    {{"type": "toggle", "text": "Enable", "x": 20, "y": 260, "w": 100, "h": 20}},
    {{"type": "icon", "icon": "settings", "x": 750, "y": 10, "w": 24, "h": 24}}
  ]
}}

Supported types: button, input_field, text, checkbox, toggle, icon, separator, container, dropdown
Icons: menu, search, close, settings, user

Rules:
- Use realistic positions, no overlapping elements
- Leave 15-20px margins, 8-12px spacing between elements
- Buttons: 80-200w x 30-40h. Input fields: 150-400w x 28-34h
- Group related elements. Use containers for sections
- Design 20-40 elements for a realistic looking app
- Nested elements inside containers are supported
- Output ONLY the JSON, no explanation

JSON:"""


def call_claude(prompt: str, timeout: int = 60) -> str:
    """Call Claude Code CLI and return the response."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            timeout=timeout,
            cwd=os.path.dirname(__file__),
            encoding="utf-8",
            errors="replace",
        )
        if result.stdout:
            return result.stdout.strip()
        return ""
    except FileNotFoundError:
        raise RuntimeError(
            "Claude Code CLI not found. Install from: https://claude.ai/claude-code\n"
            "Or use: npm install -g @anthropic-ai/claude-code"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude timed out after {timeout}s")


def parse_json_from_response(response: str) -> dict:
    """Extract JSON from Claude's response."""
    import re

    # Strip markdown code blocks
    if "```" in response:
        match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
        if match:
            response = match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON object
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def main():
    parser = argparse.ArgumentParser(description="Generate UIs using Claude Code")
    parser.add_argument("-n", "--num-samples", type=int, default=10)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--app-type", default=None,
                        help="Specific app type (default: random from built-in list)")
    parser.add_argument("--output-dir", "-o", default=None)
    parser.add_argument("--timeout", type=int, default=90,
                        help="Claude timeout per request in seconds")
    parser.add_argument("--train-ratio", type=float, default=0.8)

    args = parser.parse_args()

    if args.output_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        args.output_dir = str(project_root / "data" / "synthetic_claude")

    out = Path(args.output_dir)
    for split in ["train", "test"]:
        (out / split / "images").mkdir(parents=True, exist_ok=True)
        (out / split / "labels").mkdir(parents=True, exist_ok=True)
        (out / split / "layouts").mkdir(parents=True, exist_ok=True)

    # App types to generate
    if args.app_type:
        app_types = [args.app_type] * args.num_samples
    else:
        rng = np.random.default_rng(42)
        all_types = APP_TYPES + [
            "car instrument cluster with speedometer and gauges",
            "car infotainment center with navigation and media",
            "car climate control panel",
            "industrial HMI control panel",
            "medical device monitoring screen",
            "point of sale terminal",
            "smart home control panel",
            "flight booking application",
            "hotel check-in kiosk",
            "ATM banking interface",
            "warehouse management system",
            "restaurant ordering kiosk",
        ]
        indices = rng.choice(len(all_types), size=args.num_samples, replace=True)
        app_types = [all_types[i] for i in indices]

    renderer = LLMRenderer()
    num_train = int(args.num_samples * args.train_ratio)

    manifest = {
        "config": {
            "mode": "claude",
            "num_samples": args.num_samples,
            "width": args.width,
            "height": args.height,
            "generated_at": datetime.now().isoformat(),
        },
        "train": [],
        "test": [],
    }

    print(f"Generating {args.num_samples} UIs using Claude Code")
    print(f"  Resolution: {args.width}x{args.height}")
    print(f"  Output: {args.output_dir}")
    print()

    success = 0
    start_time = time.time()

    for i in range(args.num_samples):
        app_type = app_types[i]
        split = "train" if i < num_train else "test"
        safe_name = app_type.replace(" ", "_")[:25].replace("/", "_")
        sample_name = f"claude_{safe_name}_{i+1:04d}"

        print(f"  [{i+1}/{args.num_samples}] {app_type}...")

        # Ask Claude
        prompt = CLAUDE_PROMPT_TEMPLATE.format(
            app_type=app_type,
            width=args.width,
            height=args.height,
        )

        try:
            response = call_claude(prompt, timeout=args.timeout)
        except RuntimeError as e:
            print(f"    -> SKIP: {e}")
            continue

        layout = parse_json_from_response(response)
        if not layout:
            print(f"    -> SKIP: could not parse JSON")
            continue

        # Save raw layout
        layout_path = out / split / "layouts" / f"{sample_name}.json"
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)

        # Render
        try:
            renderer._id_counter = 0
            img, elements, gt = renderer.render(layout, args.width, args.height)
        except Exception as e:
            print(f"    -> RENDER FAILED: {e}")
            continue

        # Save image + ground truth
        img_path = out / split / "images" / f"{sample_name}.png"
        cv2.imwrite(str(img_path), img)

        gt_path = out / split / "labels" / f"{sample_name}.json"
        with open(gt_path, 'w', encoding='utf-8') as f:
            json.dump(gt, f, indent=2, ensure_ascii=False)

        entry = {
            "name": sample_name,
            "app_type": app_type,
            "element_count": len(elements),
            "image": f"{split}/images/{sample_name}.png",
            "label": f"{split}/labels/{sample_name}.json",
            "layout": f"{split}/layouts/{sample_name}.json",
        }
        manifest[split].append(entry)
        success += 1
        print(f"    -> {len(elements)} elements")

    # Save manifest
    manifest_path = out / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    elapsed = time.time() - start_time
    print()
    print(f"Done in {elapsed:.0f}s")
    print(f"  Success: {success}/{args.num_samples}")
    print(f"  Train: {len(manifest['train'])}, Test: {len(manifest['test'])}")
    print(f"  Output: {args.output_dir}")


if __name__ == "__main__":
    main()
