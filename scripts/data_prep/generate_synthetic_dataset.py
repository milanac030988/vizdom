#!/usr/bin/env python
"""
Generate synthetic UI dataset for VizDOM benchmarking and training.

Usage:
    # Generate 100 samples (default)
    python scripts/data_prep/generate_synthetic_dataset.py

    # Custom options
    python scripts/data_prep/generate_synthetic_dataset.py --num-samples 200 --templates login dashboard

    # Only dark theme, specific resolution
    python scripts/data_prep/generate_synthetic_dataset.py --themes dark --width 1024 --height 768
"""

import sys
import os
import json
import argparse
import time
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime

# Add scripts/data_prep to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from synthetic_ui.templates import TEMPLATE_REGISTRY
from synthetic_ui.themes import THEMES
from synthetic_ui.ground_truth import build_ground_truth


def generate_dataset(
    num_samples: int = 100,
    width: int = 800,
    height: int = 600,
    templates: list = None,
    themes: list = None,
    train_ratio: float = 0.8,
    seed: int = 42,
    output_dir: str = None,
):
    """Generate synthetic UI dataset."""

    if output_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = str(project_root / "data" / "synthetic")

    # Setup output directories
    out = Path(output_dir)
    for split in ["train", "test"]:
        (out / split / "images").mkdir(parents=True, exist_ok=True)
        (out / split / "labels").mkdir(parents=True, exist_ok=True)

    # Resolve templates
    if not templates or "all" in templates:
        template_names = list(TEMPLATE_REGISTRY.keys())
    else:
        template_names = [t for t in templates if t in TEMPLATE_REGISTRY]

    # Resolve themes
    if not themes or "random" in themes:
        theme_names = list(THEMES.keys())
    else:
        theme_names = [t for t in themes if t in THEMES]

    print(f"Generating {num_samples} synthetic UI samples")
    print(f"  Resolution: {width}x{height}")
    print(f"  Templates: {', '.join(template_names)}")
    print(f"  Themes: {', '.join(theme_names)}")
    print(f"  Train/test split: {train_ratio:.0%}/{1-train_ratio:.0%}")
    print(f"  Seed: {seed}")
    print(f"  Output: {output_dir}")
    print()

    master_rng = np.random.default_rng(seed)
    manifest = {
        "config": {
            "num_samples": num_samples,
            "width": width,
            "height": height,
            "templates": template_names,
            "themes": theme_names,
            "train_ratio": train_ratio,
            "seed": seed,
            "generated_at": datetime.now().isoformat(),
        },
        "train": [],
        "test": [],
    }

    # Determine train/test split
    num_train = int(num_samples * train_ratio)
    indices = master_rng.permutation(num_samples)
    train_indices = set(indices[:num_train])

    start_time = time.time()
    total_elements = 0

    for i in range(num_samples):
        # Pick template and theme
        tpl_name = template_names[i % len(template_names)]
        theme_name = theme_names[master_rng.integers(0, len(theme_names))]
        theme = THEMES[theme_name]

        # Create seeded RNG for this sample
        sample_seed = seed + i
        rng = np.random.default_rng(sample_seed)

        # Instantiate template
        TemplateClass = TEMPLATE_REGISTRY[tpl_name]
        template = TemplateClass(width, height, theme, rng)

        # Generate
        try:
            img, elements = template.generate()
        except Exception as e:
            print(f"  [{i+1}] FAILED ({tpl_name}/{theme_name}): {e}")
            continue

        # Build ground truth
        gt = build_ground_truth(elements, (width, height))

        # Determine split
        split = "train" if i in train_indices else "test"
        sample_name = f"{tpl_name}_{i+1:04d}"

        # Save image
        img_path = out / split / "images" / f"{sample_name}.png"
        cv2.imwrite(str(img_path), img)

        # Save ground truth JSON
        json_path = out / split / "labels" / f"{sample_name}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(gt, f, indent=2, ensure_ascii=False)

        # Manifest entry
        entry = {
            "name": sample_name,
            "template": tpl_name,
            "theme": theme_name,
            "element_count": len(elements),
            "text_count": sum(1 for e in elements if e.text),
            "image": f"{split}/images/{sample_name}.png",
            "label": f"{split}/labels/{sample_name}.json",
        }
        manifest[split].append(entry)
        total_elements += len(elements)

        if (i + 1) % 10 == 0 or i == num_samples - 1:
            elapsed = time.time() - start_time
            print(f"  [{i+1}/{num_samples}] {sample_name} ({tpl_name}/{theme_name}) "
                  f"- {len(elements)} elements ({elapsed:.1f}s)")

    # Save manifest
    manifest_path = out / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    elapsed = time.time() - start_time
    print()
    print(f"Dataset generated in {elapsed:.1f}s")
    print(f"  Train: {len(manifest['train'])} samples")
    print(f"  Test: {len(manifest['test'])} samples")
    print(f"  Total elements: {total_elements}")
    print(f"  Avg elements/sample: {total_elements/max(num_samples,1):.0f}")
    print(f"  Manifest: {manifest_path}")


def generate_llm_dataset(
    num_samples: int = 25,
    width: int = 800,
    height: int = 600,
    app_types: list = None,
    train_ratio: float = 0.8,
    ollama_model: str = "qwen2.5:3b",
    output_dir: str = None,
):
    """Generate dataset using LLM-designed layouts."""
    from synthetic_ui.llm_designer import LLMDesigner, APP_TYPES
    from synthetic_ui.llm_renderer import LLMRenderer

    if output_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = str(project_root / "data" / "synthetic_llm")

    out = Path(output_dir)
    for split in ["train", "test"]:
        (out / split / "images").mkdir(parents=True, exist_ok=True)
        (out / split / "labels").mkdir(parents=True, exist_ok=True)
        (out / split / "layouts").mkdir(parents=True, exist_ok=True)

    # Pick app types
    if not app_types:
        rng = np.random.default_rng(42)
        indices = rng.choice(len(APP_TYPES), size=min(num_samples, len(APP_TYPES)), replace=False)
        app_types = [APP_TYPES[i] for i in indices]
        # If need more, cycle
        while len(app_types) < num_samples:
            app_types.extend(APP_TYPES[:num_samples - len(app_types)])

    designer = LLMDesigner(model=ollama_model)
    renderer = LLMRenderer()

    print(f"Generating {num_samples} LLM-designed UI samples")
    print(f"  Model: {ollama_model}")
    print(f"  Resolution: {width}x{height}")
    print(f"  Output: {output_dir}")
    print()

    manifest = {
        "config": {
            "mode": "llm",
            "num_samples": num_samples,
            "width": width,
            "height": height,
            "ollama_model": ollama_model,
            "train_ratio": train_ratio,
            "generated_at": datetime.now().isoformat(),
        },
        "train": [],
        "test": [],
    }

    num_train = int(num_samples * train_ratio)
    success = 0
    start_time = time.time()

    for i in range(num_samples):
        app_type = app_types[i % len(app_types)]
        split = "train" if i < num_train else "test"
        safe_name = app_type.replace(" ", "_")[:20]
        sample_name = f"llm_{safe_name}_{i+1:04d}"

        print(f"  [{i+1}/{num_samples}] {app_type}...")

        layout = designer.design(app_type, width, height)
        if not layout:
            print(f"    -> SKIP (LLM failed)")
            continue

        # Save raw layout JSON
        layout_path = out / split / "layouts" / f"{sample_name}.json"
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)

        # Render
        try:
            img, elements, gt = renderer.render(layout, width, height)
        except Exception as e:
            print(f"    -> RENDER FAILED: {e}")
            continue

        # Save image
        img_path = out / split / "images" / f"{sample_name}.png"
        cv2.imwrite(str(img_path), img)

        # Save ground truth
        gt_path = out / split / "labels" / f"{sample_name}.json"
        with open(gt_path, 'w', encoding='utf-8') as f:
            json.dump(gt, f, indent=2, ensure_ascii=False)

        entry = {
            "name": sample_name,
            "app_type": app_type,
            "theme": layout.get("theme", "unknown"),
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
    print(f"LLM dataset generated in {elapsed:.1f}s")
    print(f"  Success: {success}/{num_samples}")
    print(f"  Train: {len(manifest['train'])}, Test: {len(manifest['test'])}")
    print(f"  Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic UI dataset")
    subparsers = parser.add_subparsers(dest="mode", help="Generation mode")

    # Static templates mode
    static = subparsers.add_parser("static", help="Use predefined templates")
    static.add_argument("--num-samples", "-n", type=int, default=100)
    static.add_argument("--width", type=int, default=800)
    static.add_argument("--height", type=int, default=600)
    static.add_argument("--templates", nargs="+", default=["all"],
                        choices=["all"] + list(TEMPLATE_REGISTRY.keys()))
    static.add_argument("--themes", nargs="+", default=["random"],
                        choices=["random"] + list(THEMES.keys()))
    static.add_argument("--train-ratio", type=float, default=0.8)
    static.add_argument("--seed", type=int, default=42)
    static.add_argument("--output-dir", "-o", default=None)

    # LLM-designed mode
    llm = subparsers.add_parser("llm", help="Use LLM to design UI layouts (requires Ollama)")
    llm.add_argument("--num-samples", "-n", type=int, default=25)
    llm.add_argument("--width", type=int, default=800)
    llm.add_argument("--height", type=int, default=600)
    llm.add_argument("--model", default="qwen2.5:3b", help="Ollama model name")
    llm.add_argument("--train-ratio", type=float, default=0.8)
    llm.add_argument("--output-dir", "-o", default=None)

    args = parser.parse_args()

    if args.mode == "llm":
        generate_llm_dataset(
            num_samples=args.num_samples,
            width=args.width,
            height=args.height,
            ollama_model=args.model,
            train_ratio=args.train_ratio,
            output_dir=args.output_dir,
        )
    elif args.mode == "static":
        generate_dataset(
            num_samples=args.num_samples,
            width=args.width,
            height=args.height,
            templates=args.templates,
            themes=args.themes,
            train_ratio=args.train_ratio,
            seed=args.seed,
            output_dir=args.output_dir,
        )
    else:
        # Default: static mode for backward compatibility
        generate_dataset()


if __name__ == "__main__":
    main()
