#!/usr/bin/env python
"""
Camera capture augmentation tool.

Transforms clean screenshots to look like they were photographed
from an external camera (phone/DSLR pointing at a screen).

Usage:
    # Single image
    python scripts/data_prep/augment_camera.py screenshot.png -o output.png

    # Augment entire dataset directory
    python scripts/data_prep/augment_camera.py data/synthetic/train/images/ -o data/augmented/

    # With specific effects
    python scripts/data_prep/augment_camera.py screenshot.png --effects perspective noise blur glare

    # Multiple variants per image
    python scripts/data_prep/augment_camera.py data/synthetic/ -o data/augmented/ --variants 3
"""

import cv2
import numpy as np
import os
import sys
import json
import argparse
import shutil
from pathlib import Path
from typing import Tuple, List, Optional


class CameraAugmentor:
    """Apply camera-capture effects to clean screenshots."""

    def __init__(self, rng: np.random.Generator = None):
        self.rng = rng or np.random.default_rng()

    def augment(
        self,
        img: np.ndarray,
        effects: List[str] = None,
        intensity: float = 1.0,
    ) -> Tuple[np.ndarray, dict]:
        """
        Apply camera-capture augmentation to an image.

        Args:
            img: BGR image
            effects: List of effects to apply (None = random selection)
            intensity: 0.0 (subtle) to 1.0 (strong)

        Returns:
            (augmented_image, metadata_dict)
        """
        result = img.copy()
        meta = {"effects": [], "intensity": intensity}

        all_effects = [
            "perspective", "noise", "blur", "glare",
            "color_shift", "brightness_gradient", "moire",
            "vignette", "barrel_distortion",
        ]

        if effects is None:
            # Random subset (3-6 effects)
            n = self.rng.integers(3, min(7, len(all_effects) + 1))
            effects = list(self.rng.choice(all_effects, size=n, replace=False))

        # Apply in a sensible order
        order = [
            "perspective", "barrel_distortion", "color_shift",
            "brightness_gradient", "moire", "glare",
            "blur", "noise", "vignette",
        ]
        for effect in order:
            if effect not in effects:
                continue
            try:
                result, effect_meta = getattr(self, f"_apply_{effect}")(result, intensity)
                meta["effects"].append({"name": effect, **effect_meta})
            except Exception as e:
                meta["effects"].append({"name": effect, "error": str(e)})

        return result, meta

    def _apply_perspective(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply perspective warp (angled camera view)."""
        h, w = img.shape[:2]
        max_shift = int(min(w, h) * 0.08 * intensity)

        # Random corner displacements
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32([
            [self.rng.integers(0, max_shift + 1), self.rng.integers(0, max_shift + 1)],
            [w - self.rng.integers(0, max_shift + 1), self.rng.integers(0, max_shift + 1)],
            [w - self.rng.integers(0, max_shift + 1), h - self.rng.integers(0, max_shift + 1)],
            [self.rng.integers(0, max_shift + 1), h - self.rng.integers(0, max_shift + 1)],
        ])

        M = cv2.getPerspectiveTransform(src, dst)
        result = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)

        return result, {"max_shift": max_shift}

    def _apply_barrel_distortion(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply barrel/pincushion lens distortion."""
        h, w = img.shape[:2]
        k1 = self.rng.uniform(-0.15, 0.15) * intensity
        k2 = self.rng.uniform(-0.05, 0.05) * intensity

        # Camera matrix
        fx = fy = max(w, h)
        cx, cy = w / 2, h / 2
        camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
        dist_coeffs = np.array([k1, k2, 0, 0, 0], dtype=np.float64)

        result = cv2.undistort(img, camera_matrix, dist_coeffs)
        return result, {"k1": round(k1, 4), "k2": round(k2, 4)}

    def _apply_noise(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply camera sensor noise (Gaussian + salt-and-pepper)."""
        # Gaussian noise
        sigma = self.rng.uniform(5, 25) * intensity
        noise = self.rng.normal(0, sigma, img.shape).astype(np.float32)
        result = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        # Salt and pepper (sparse)
        sp_ratio = 0.001 * intensity
        num_sp = int(img.shape[0] * img.shape[1] * sp_ratio)
        # Salt
        coords = (self.rng.integers(0, img.shape[0], num_sp),
                  self.rng.integers(0, img.shape[1], num_sp))
        result[coords[0], coords[1]] = 255
        # Pepper
        coords = (self.rng.integers(0, img.shape[0], num_sp),
                  self.rng.integers(0, img.shape[1], num_sp))
        result[coords[0], coords[1]] = 0

        return result, {"sigma": round(sigma, 1), "sp_ratio": round(sp_ratio, 5)}

    def _apply_blur(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply blur (Gaussian + optional motion blur)."""
        # Gaussian blur
        ksize = int(self.rng.choice([3, 5, 7]) * max(1, intensity))
        if ksize % 2 == 0:
            ksize += 1
        result = cv2.GaussianBlur(img, (ksize, ksize), 0)

        # Optional motion blur
        if self.rng.random() < 0.4 * intensity:
            motion_size = int(self.rng.integers(3, 8) * intensity)
            if motion_size > 1:
                angle = self.rng.uniform(0, 180)
                kernel = np.zeros((motion_size, motion_size))
                kernel[motion_size // 2, :] = 1.0 / motion_size
                M = cv2.getRotationMatrix2D((motion_size // 2, motion_size // 2), angle, 1)
                kernel = cv2.warpAffine(kernel, M, (motion_size, motion_size))
                kernel = kernel / kernel.sum()
                result = cv2.filter2D(result, -1, kernel)

        return result, {"gaussian_ksize": ksize}

    def _apply_glare(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply screen glare/reflection hotspot."""
        h, w = img.shape[:2]
        result = img.astype(np.float32)

        # 1-3 glare spots
        num_spots = self.rng.integers(1, max(2, int(3 * intensity) + 1))
        spots = []

        for _ in range(num_spots):
            cx = self.rng.integers(w // 4, 3 * w // 4)
            cy = self.rng.integers(h // 4, 3 * h // 4)
            radius = self.rng.integers(int(min(w, h) * 0.1), int(min(w, h) * 0.3))
            strength = self.rng.uniform(0.1, 0.4) * intensity

            # Create radial gradient
            Y, X = np.ogrid[:h, :w]
            dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(np.float32)
            mask = np.clip(1.0 - dist / radius, 0, 1)
            mask = mask ** 2  # Smoother falloff

            # Add glare (brighten)
            for c in range(3):
                result[:, :, c] += mask * 255 * strength

            spots.append({"cx": int(cx), "cy": int(cy), "radius": int(radius)})

        result = np.clip(result, 0, 255).astype(np.uint8)
        return result, {"spots": len(spots)}

    def _apply_color_shift(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply color temperature shift (warm/cool screen appearance)."""
        result = img.astype(np.float32)

        # Random per-channel gain (simulates screen color temp + camera white balance)
        b_gain = 1.0 + self.rng.uniform(-0.12, 0.12) * intensity
        g_gain = 1.0 + self.rng.uniform(-0.06, 0.06) * intensity
        r_gain = 1.0 + self.rng.uniform(-0.12, 0.12) * intensity

        result[:, :, 0] *= b_gain
        result[:, :, 1] *= g_gain
        result[:, :, 2] *= r_gain

        # Slight overall brightness shift
        brightness = self.rng.uniform(-15, 15) * intensity
        result += brightness

        result = np.clip(result, 0, 255).astype(np.uint8)
        return result, {
            "b_gain": round(b_gain, 3),
            "g_gain": round(g_gain, 3),
            "r_gain": round(r_gain, 3),
        }

    def _apply_brightness_gradient(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply uneven lighting gradient across the image."""
        h, w = img.shape[:2]

        # Random gradient direction
        angle = self.rng.uniform(0, 2 * np.pi)
        strength = self.rng.uniform(0.05, 0.25) * intensity

        # Create gradient
        Y, X = np.meshgrid(np.linspace(-1, 1, h), np.linspace(-1, 1, w), indexing='ij')
        gradient = (X * np.cos(angle) + Y * np.sin(angle)) * strength
        gradient = gradient.astype(np.float32)

        result = img.astype(np.float32)
        for c in range(3):
            result[:, :, c] *= (1.0 + gradient)

        result = np.clip(result, 0, 255).astype(np.uint8)
        return result, {"angle": round(np.degrees(angle), 1), "strength": round(strength, 3)}

    def _apply_moire(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply moiré pattern (screen pixel grid interference)."""
        h, w = img.shape[:2]

        # Create interference pattern
        freq = self.rng.uniform(0.3, 0.8) * intensity
        angle = self.rng.uniform(0, np.pi)
        strength = self.rng.uniform(5, 20) * intensity

        Y, X = np.meshgrid(np.arange(h), np.arange(w), indexing='ij')
        pattern = np.sin(2 * np.pi * freq * (X * np.cos(angle) + Y * np.sin(angle)))
        pattern = (pattern * strength).astype(np.float32)

        result = img.astype(np.float32)
        for c in range(3):
            result[:, :, c] += pattern

        result = np.clip(result, 0, 255).astype(np.uint8)
        return result, {"freq": round(freq, 3), "strength": round(strength, 1)}

    def _apply_vignette(self, img: np.ndarray, intensity: float) -> Tuple[np.ndarray, dict]:
        """Apply lens vignette (dark corners)."""
        h, w = img.shape[:2]
        strength = self.rng.uniform(0.3, 0.7) * intensity

        Y, X = np.ogrid[:h, :w]
        cy, cx = h / 2, w / 2
        max_dist = np.sqrt(cx ** 2 + cy ** 2)
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(np.float32) / max_dist

        mask = 1.0 - (dist ** 2) * strength
        mask = np.clip(mask, 0, 1)

        result = img.astype(np.float32)
        for c in range(3):
            result[:, :, c] *= mask

        result = np.clip(result, 0, 255).astype(np.uint8)
        return result, {"strength": round(strength, 3)}


def augment_file(
    input_path: str,
    output_path: str,
    augmentor: CameraAugmentor,
    effects: List[str] = None,
    intensity: float = 1.0,
) -> dict:
    """Augment a single image file."""
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Could not read: {input_path}")

    result, meta = augmentor.augment(img, effects=effects, intensity=intensity)
    cv2.imwrite(output_path, result)

    meta["source"] = os.path.basename(input_path)
    return meta


def augment_dataset(
    input_dir: str,
    output_dir: str,
    variants: int = 1,
    effects: List[str] = None,
    intensity: float = 1.0,
    seed: int = 42,
    copy_labels: bool = True,
):
    """Augment an entire dataset directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Detect dataset structure
    has_splits = (input_path / "train").exists()

    if has_splits:
        splits = ["train", "test"]
    else:
        splits = ["."]

    rng = np.random.default_rng(seed)
    total = 0
    manifest_entries = []

    for split in splits:
        img_dir = input_path / split / "images" if has_splits else input_path
        label_dir = input_path / split / "labels" if has_splits else None

        if not img_dir.exists():
            continue

        out_img_dir = output_path / split / "images" if has_splits else output_path
        out_label_dir = output_path / split / "labels" if has_splits else None
        out_img_dir.mkdir(parents=True, exist_ok=True)
        if out_label_dir:
            out_label_dir.mkdir(parents=True, exist_ok=True)

        images = sorted(img_dir.glob("*.png"))
        print(f"  {split}: {len(images)} images x {variants} variants")

        for img_file in images:
            stem = img_file.stem

            for v in range(variants):
                augmentor = CameraAugmentor(rng=np.random.default_rng(seed + total))

                suffix = f"_cam{v+1}" if variants > 1 else "_cam"
                out_name = f"{stem}{suffix}.png"
                out_path = out_img_dir / out_name

                try:
                    meta = augment_file(
                        str(img_file), str(out_path),
                        augmentor, effects=effects, intensity=intensity,
                    )
                    manifest_entries.append({
                        "source": str(img_file.relative_to(input_path)),
                        "output": str(out_path.relative_to(output_path)),
                        "effects": [e["name"] for e in meta["effects"]],
                    })
                    total += 1

                    # Copy label file (ground truth still valid for most augmentations)
                    if copy_labels and label_dir:
                        label_file = label_dir / f"{stem}.json"
                        if label_file.exists():
                            out_label = out_label_dir / f"{stem}{suffix}.json"
                            shutil.copy2(label_file, out_label)

                except Exception as e:
                    print(f"    FAILED: {img_file.name}: {e}")

    # Save augmentation manifest
    manifest = {
        "source_dir": str(input_path),
        "output_dir": str(output_path),
        "variants": variants,
        "intensity": intensity,
        "total_augmented": total,
        "entries": manifest_entries,
    }
    manifest_path = output_path / "augmentation_manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"\n  Total: {total} augmented images")
    print(f"  Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Camera capture augmentation for UI screenshots"
    )
    parser.add_argument("input", help="Input image file or dataset directory")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file or directory")
    parser.add_argument("--effects", nargs="+", default=None,
                        choices=["perspective", "noise", "blur", "glare",
                                 "color_shift", "brightness_gradient", "moire",
                                 "vignette", "barrel_distortion"],
                        help="Specific effects to apply (default: random)")
    parser.add_argument("--intensity", type=float, default=0.7,
                        help="Effect intensity 0.0-1.0 (default: 0.7)")
    parser.add_argument("--variants", type=int, default=1,
                        help="Number of augmented variants per image (default: 1)")
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    if os.path.isfile(args.input):
        # Single file mode
        augmentor = CameraAugmentor(rng=np.random.default_rng(args.seed))
        meta = augment_file(args.input, args.output, augmentor,
                            effects=args.effects, intensity=args.intensity)
        print(f"Augmented: {args.input} -> {args.output}")
        print(f"Effects: {', '.join(e['name'] for e in meta['effects'])}")

    elif os.path.isdir(args.input):
        # Dataset directory mode
        print(f"Augmenting dataset: {args.input}")
        print(f"  Intensity: {args.intensity}")
        print(f"  Variants per image: {args.variants}")
        augment_dataset(
            args.input, args.output,
            variants=args.variants,
            effects=args.effects,
            intensity=args.intensity,
            seed=args.seed,
        )
    else:
        print(f"Error: {args.input} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
