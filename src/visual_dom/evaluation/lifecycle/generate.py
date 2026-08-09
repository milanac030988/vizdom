"""
Derive lifecycle benchmark steps from the labelled element ground truth.

The expensive part of any benchmark is annotation; this module gets a large,
unbiased step set for free by exploiting what the element GT already contains:

- every actionable element (button / input_field / checkbox) whose caption text
  is UNIQUE in its state becomes an ACTION step - locator ``text=<caption>``,
  instruction "click the '<caption>' <type>", target = the element's bounds;
- the same uniqueness rule yields positive VERIFY steps ("'<caption>' is
  visible" -> PASSED);
- deliberately-absent captions yield negative VERIFY steps (expect FAILED),
  which is what measures FALSE PASSES - a testing system that "finds"
  nonexistent elements is worse than one that misses real ones.

Only unique captions are used: an ambiguous ``text=`` locator fails by design
in VizDOM (exactly-one contract), and grading a system on deliberately
ambiguous input would measure the benchmark, not the system.
"""

import json
import random
from collections import Counter
from pathlib import Path

ACTIONABLE = ("button", "input_field", "checkbox")

# Captions guaranteed absent, for negative verification steps. Chosen to be
# plausible UI words so a lazy oracle cannot reject them on shape alone.
_ABSENT_CAPTIONS = [
    "Purple Elephant", "Frobnicate", "Quantum Sync", "Zylophone",
    "Warp Cores", "Moon Cheese", "Antigravity", "Bogus Panel",
]


def _caption_for(elem, by_id):
    """An actionable element's caption: own ocr_text, else a child text's."""
    text = (elem.get("ocr_text") or "").strip()
    if text:
        return text
    for cid in elem.get("children_ids") or []:
        child = by_id.get(cid)
        if child and child.get("visual_type") == "text":
            text = (child.get("ocr_text") or "").strip()
            if text:
                return text
    return ""


def generate_steps(labels_dir, images_dir, seed: int = 42):
    """
    Build the manifest dict from a labels/ + images/ directory pair.

    Deterministic for a given seed, so the generated manifest can be committed
    and results reproduced.
    """
    rng = random.Random(seed)
    labels_dir, images_dir = Path(labels_dir), Path(images_dir)
    states, steps = [], []

    for label_path in sorted(labels_dir.glob("*.json")):
        state_id = label_path.stem
        image_path = images_dir / f"{state_id}.png"
        if not image_path.exists():
            continue
        gt = json.loads(label_path.read_text(encoding="utf-8"))
        elements = gt.get("elements", [])
        by_id = {e["id"]: e for e in elements}

        # caption -> count over ALL texts in the state (uniqueness must consider
        # every occurrence a locator could match, not just actionable ones)
        counts = Counter()
        for e in elements:
            t = (e.get("ocr_text") or "").strip()
            if t:
                counts[t.lower()] += 1

        states.append({
            "id": state_id,
            "image": str(image_path).replace("\\", "/"),
            "gt": str(label_path).replace("\\", "/"),
            "image_size": gt.get("image_size"),
        })

        seen_captions = set()
        for e in elements:
            if e.get("visual_type") not in ACTIONABLE:
                continue
            caption = _caption_for(e, by_id)
            if not caption or counts[caption.lower()] != 1:
                continue
            if caption.lower() in seen_captions:
                continue
            seen_captions.add(caption.lower())
            kind_word = {"button": "button", "input_field": "input field",
                         "checkbox": "checkbox"}[e["visual_type"]]
            steps.append({
                "id": f"{state_id}/act/{e['id']}",
                "state": state_id,
                "kind": "action",
                "action": "click",
                "locator": f'text="{caption}"',
                "instruction": f"click the '{caption}' {kind_word}",
                "target_id": e["id"],
                "target_bounds": e["bounds"],
            })
            steps.append({
                "id": f"{state_id}/verify/{e['id']}",
                "state": state_id,
                "kind": "verify",
                "locator": f'text="{caption}"',
                "instruction": f"the '{caption}' {kind_word} is visible",
                "expect": "PASSED",
                "target_id": e["id"],
                "target_bounds": e["bounds"],
            })

        # negative oracle steps: two absent captions per state
        for caption in rng.sample(_ABSENT_CAPTIONS, 2):
            steps.append({
                "id": f"{state_id}/verify-neg/{caption.replace(' ', '_')}",
                "state": state_id,
                "kind": "verify",
                "locator": f'text="{caption}"',
                "instruction": f"the '{caption}' button is visible",
                "expect": "FAILED",
                "target_id": None,
                "target_bounds": None,
            })

    return {
        "benchmark": "lifecycle-synthetic-v1",
        "seed": seed,
        "states": states,
        "steps": steps,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate lifecycle benchmark steps from element GT")
    parser.add_argument("--labels", default="data/synthetic/test/labels")
    parser.add_argument("--images", default="data/synthetic/test/images")
    parser.add_argument("--out", default="benchmarks/lifecycle-synthetic-v1/steps.json")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    manifest = generate_steps(args.labels, args.images, seed=args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    kinds = Counter(s["kind"] for s in manifest["steps"])
    print(f"{out}: {len(manifest['states'])} states, {len(manifest['steps'])} steps {dict(kinds)}")


if __name__ == "__main__":
    main()
