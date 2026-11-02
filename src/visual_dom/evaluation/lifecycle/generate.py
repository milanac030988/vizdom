"""
Derive lifecycle benchmark steps from the labelled element ground truth.

The expensive part of any benchmark is annotation; this module gets a large,
unbiased step set for free by exploiting what the element GT already contains:

- every actionable element (button / input_field / checkbox) whose caption text
  is UNIQUE in its state becomes an ACTION step - locator ``text=<caption>``,
  instruction "click the '<caption>' <type>", description "<caption> <type>"
  (the ``desc=`` form of the same intent, ADR-022), target = the element's
  bounds;
- the same uniqueness rule yields positive VERIFY steps ("'<caption>' is
  visible" -> PASSED);
- deliberately-absent captions yield negative VERIFY steps (expect FAILED),
  which is what measures FALSE PASSES - a testing system that "finds"
  nonexistent elements is worse than one that misses real ones.

Negatives come in two kinds. ``nonsense`` (the synthetic set) draws from a
fixed list of invented words. ``same-app`` (the real-application set, see
harvest.py) draws captions that exist on ANOTHER screen of the same
application but not on this one - "Export" where only "Import" is shown -
which a reader of the screen cannot reject on vocabulary alone.

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


def _positive_targets(elements):
    """(element, caption, kind word) for every actionable element whose
    caption occurs exactly once in the state, first occurrence only."""
    by_id = {e["id"]: e for e in elements}
    # caption -> count over ALL texts in the state (uniqueness must consider
    # every occurrence a locator could match, not just actionable ones)
    counts = Counter()
    for e in elements:
        t = (e.get("ocr_text") or "").strip()
        if t:
            counts[t.lower()] += 1

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
        # a harvested element names its own role ("tab", "menu item")
        kind_word = e.get("role_word") or {"button": "button", "input_field": "input field",
                                           "checkbox": "checkbox"}[e["visual_type"]]
        yield e, caption, kind_word


def app_of(state_id: str) -> str:
    """The application a real-application state belongs to: ``<app>__<state>``."""
    return state_id.split("__", 1)[0]


def _absent_here(caption: str, names) -> bool:
    """True when no name on the screen equals or contains the caption, or the
    reverse: "Save" is not absent from a screen showing "Save As"."""
    c = caption.lower()
    return not any(c in n or n in c for n in names if n)


def _same_app_negatives(rng, state_id, own_names, pool, k=2):
    """k captions from other screens of this application that this screen
    does not show; fewer when the application offers fewer."""
    candidates = sorted(
        {(cap, word) for sid, cap, word in pool
         if sid != state_id and app_of(sid) == app_of(state_id)
         and _absent_here(cap, own_names)},
        key=lambda cw: cw[0].lower())
    return rng.sample(candidates, min(k, len(candidates)))


def generate_steps(labels_dir, images_dir, seed: int = 42, negatives: str = "nonsense",
                   benchmark: str = "lifecycle-synthetic-v1", dedupe_app: bool = False):
    """
    Build the manifest dict from a labels/ + images/ directory pair.

    Deterministic for a given seed, so the generated manifest can be committed
    and results reproduced. ``negatives`` is "nonsense" or "same-app" (see the
    module docstring); a same-app state whose application has too few other
    captions is topped up from the nonsense list, and every same-app negative
    carries ``negative_kind`` so the two can be reported apart.

    ``dedupe_app`` keeps a positive step only on the first state (in id
    order) of its application that has that caption and role: the pages of
    a settings dialog repeat their navigation tree, and counting the same
    tree item once per page would overstate how many independent steps the
    set holds. Negatives are drawn from the full, undeduplicated pool.
    """
    if negatives not in ("nonsense", "same-app"):
        raise ValueError(f"negatives must be 'nonsense' or 'same-app', not {negatives!r}")
    rng = random.Random(seed)
    labels_dir, images_dir = Path(labels_dir), Path(images_dir)
    states, steps = [], []

    loaded = []
    for label_path in sorted(labels_dir.glob("*.json")):
        state_id = label_path.stem
        image_path = images_dir / f"{state_id}.png"
        if not image_path.exists():
            continue
        gt = json.loads(label_path.read_text(encoding="utf-8"))
        loaded.append((state_id, label_path, image_path, gt))

    # same-app pool: every positive caption of every state, found up front
    pool = []
    if negatives == "same-app":
        for state_id, _, _, gt in loaded:
            for _e, caption, word in _positive_targets(gt.get("elements", [])):
                pool.append((state_id, caption, word))

    seen_in_app = set()
    for state_id, label_path, image_path, gt in loaded:
        elements = gt.get("elements", [])

        states.append({
            "id": state_id,
            "image": str(image_path).replace("\\", "/"),
            "gt": str(label_path).replace("\\", "/"),
            "image_size": gt.get("image_size"),
        })

        for e, caption, kind_word in _positive_targets(elements):
            if dedupe_app:
                key = (app_of(state_id), caption.lower(), kind_word)
                if key in seen_in_app:
                    continue
                seen_in_app.add(key)
            # Three forms of ONE intent, all derived from the same caption so
            # no executor gets extra information: the property locator, the
            # grounder instruction, and the desc= description (what a test
            # author would write as desc="Save button").
            steps.append({
                "id": f"{state_id}/act/{e['id']}",
                "state": state_id,
                "kind": "action",
                "action": "click",
                "locator": f'text="{caption}"',
                "instruction": f"click the '{caption}' {kind_word}",
                "description": f"{caption} {kind_word}",
                "target_id": e["id"],
                "target_bounds": e["bounds"],
            })
            steps.append({
                "id": f"{state_id}/verify/{e['id']}",
                "state": state_id,
                "kind": "verify",
                "locator": f'text="{caption}"',
                "instruction": f"the '{caption}' {kind_word} is visible",
                "description": f"{caption} {kind_word}",
                "expect": "PASSED",
                "target_id": e["id"],
                "target_bounds": e["bounds"],
            })

        # negative oracle steps: two absent captions per state
        if negatives == "nonsense":
            chosen = [(c, "button", None) for c in rng.sample(_ABSENT_CAPTIONS, 2)]
        else:
            # every name the screen carries, visible text or not, so a caption
            # the labels did not step on is still never claimed absent
            own = {(e.get("ocr_text") or "").strip().lower() for e in elements}
            own |= {n.strip().lower() for n in gt.get("all_names", [])}
            chosen = [(c, w, "same-app")
                      for c, w in _same_app_negatives(rng, state_id, own, pool)]
            fill = [c for c in _ABSENT_CAPTIONS if _absent_here(c, own)]
            chosen += [(c, "button", "nonsense")
                       for c in rng.sample(fill, max(0, 2 - len(chosen)))]
        for caption, word, kind in chosen:
            step = {
                "id": f"{state_id}/verify-neg/{caption.replace(' ', '_')}",
                "state": state_id,
                "kind": "verify",
                "locator": f'text="{caption}"',
                "instruction": f"the '{caption}' {word} is visible",
                "description": f"{caption} {word}",
                "expect": "FAILED",
                "target_id": None,
                "target_bounds": None,
            }
            if kind:
                step["negative_kind"] = kind
            steps.append(step)

    return {
        "benchmark": benchmark,
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
    parser.add_argument("--negatives", choices=("nonsense", "same-app"), default="nonsense",
                        help="absent captions: invented words, or captions from other "
                             "screens of the same application (state ids <app>__<state>)")
    parser.add_argument("--benchmark", default="lifecycle-synthetic-v1",
                        help="name written into the manifest")
    parser.add_argument("--dedupe-app", action="store_true",
                        help="keep a positive step only on the first state of its "
                             "application with that caption and role")
    args = parser.parse_args()

    manifest = generate_steps(args.labels, args.images, seed=args.seed,
                              negatives=args.negatives, benchmark=args.benchmark,
                              dedupe_app=args.dedupe_app)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    kinds = Counter(s["kind"] for s in manifest["steps"])
    print(f"{out}: {len(manifest['states'])} states, {len(manifest['steps'])} steps {dict(kinds)}")


if __name__ == "__main__":
    main()
