"""
Other screen parsers as benchmark columns.

A grounder answers one step at a time ("where is X"). A screen *parser* does
what VizDOM does: it turns the whole screenshot into a list of typed, boxed,
captioned elements once, and the steps are then resolved from that list. Such
a model is put behind the same contract as the VizDOM column:

* the screen is parsed once per state, the parse time is reported as a cost;
* the parser's output is converted to the compiled DOM format;
* every step is resolved by the same `ElementFinder` (``text=``), a click
  needs exactly one match, a verify passes on one or more.

So a row of this column differs from the VizDOM row in the front end only.
The converted DOMs are written next to the result file; the detection scores
come from them (``python -m visual_dom.evaluation.cli batch``).

First parser: ScreenVLM (Gurbuz et al., "Moving Beyond Sparse Grounding with
Complete Screen Parsing Supervision", ICML 2026), 316 M parameters, trained on
the ScreenParse web-page set. It is a web model: desktop and embedded screens
are outside its training distribution, which every table that shows it must
say.

Column names::

    screenvlm               the contract above
    screenvlm[pick=first]   several matches -> the first in reading order

Needs ``transformers >= 4.55`` (the model was saved with 4.55.2; 4.46 cannot
prepare its images). The project environment is older, so the column is run
from a second environment; ``--parser-doms DIR`` keeps the parsed DOMs so a
set is parsed once and can be re-scored anywhere, without the model.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# ScreenTag -> compiled DOM
# --------------------------------------------------------------------------- #

NORM_SIZE = 500     # ScreenTag boxes are left, top, right, bottom on a 0..500 grid

# One element: <Tag><loc_l><loc_t><loc_r><loc_b>caption. The model card's
# pattern, with spaces, "/" and "-" allowed in the tag (the class list has
# "Navigation Bar", "Column/Browser", "Date-Time picker").
SCREENTAG = re.compile(
    r"<(?P<tag>[A-Za-z][A-Za-z0-9_ /\-]*)>\s*"
    r"<loc_(?P<l>\d+)><loc_(?P<t>\d+)><loc_(?P<r>\d+)><loc_(?P<b>\d+)>"
    r"(?P<text>[^<]*)")

# The 55 ScreenParse classes on the seven visual types. Fixed before any
# result was looked at (2026-11-15); keys are the class names lower-cased with
# everything but letters removed, plural and spelling variants of the dataset
# card included. None = no visual type (as for the Label Studio import).
_TYPE_GROUPS = {
    "button": ("button", "link", "utilitybutton", "tab", "switch", "toggle", "toggles",
               "select", "stepper", "steppers", "picker", "datetimepicker", "slider",
               "pagecontrol", "ratingindicator"),
    "checkbox": ("checkbox", "radiobox"),
    "input_field": ("textinput", "searchfield", "searchbar"),
    "text": ("text", "heading", "badge", "codesnippet", "tooltip", "listitem"),
    "icon": ("logo", "appicon", "fileicon", "avatar"),
    "container": ("card", "modal", "window", "menu", "popupmenu", "contextmenu", "dockmenu",
                  "editmenu", "list", "table", "alert", "notification"),
    "block": ("navigationbar", "tabbar", "toolbar", "sidebar", "statusbar",
              "bottomnavigation", "pagination", "breadcrumb", "screen", "columnbrowser",
              "image", "video", "chart", "carousel", "calendar"),
    None: ("scroll", "progressbar"),
}
CLASS_MAP: Dict[str, Optional[str]] = {name: vtype for vtype, names in _TYPE_GROUPS.items()
                                       for name in names}
UNMAPPED_TYPE = "block"
ROLES = {"button": "button", "checkbox": "checkbox", "input_field": "textField",
         "text": "staticText", "icon": "image", "container": "group", "block": "group"}
CLICKABLE = {"button", "checkbox", "input_field", "icon"}


def class_key(label: str) -> str:
    return re.sub(r"[^a-z]", "", label.lower())


def screentag_to_dom(text: str, image_size: Tuple[int, int], class_map=None) -> dict:
    """
    ScreenTag markup -> a DOM the element finder and the evaluator read.

    Boxes become pixels of the image. A box of no area is dropped, and so is
    an exact repeat (same type, box and caption: a model that loops emits the
    same element many times). Nothing else is filtered: a wrong or invented
    element stays, it is the parser's answer.
    """
    class_map = CLASS_MAP if class_map is None else class_map
    width, height = image_size
    elements, seen, stats = [], set(), {"repeats": 0, "empty_boxes": 0,
                                        "no_type": {}, "unmapped": {}}
    for m in SCREENTAG.finditer(text):
        label = m.group("tag").strip()
        key = class_key(label)
        if key in class_map:
            vtype = class_map[key]
            if vtype is None:
                stats["no_type"][label] = stats["no_type"].get(label, 0) + 1
                continue
        else:
            vtype = UNMAPPED_TYPE
            stats["unmapped"][label] = stats["unmapped"].get(label, 0) + 1
        l, t, r, b = (max(0, min(int(m.group(k)), NORM_SIZE)) for k in "ltrb")
        bounds = [round(min(l, r) / NORM_SIZE * width), round(min(t, b) / NORM_SIZE * height),
                  round(max(l, r) / NORM_SIZE * width), round(max(t, b) / NORM_SIZE * height)]
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            stats["empty_boxes"] += 1
            continue
        caption = " ".join(m.group("text").split())
        identity = (vtype, tuple(bounds), caption)
        if identity in seen:
            stats["repeats"] += 1
            continue
        seen.add(identity)
        el = {"id": f"E{len(elements) + 1}", "bounds": bounds,
              "center": [(bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2],
              "role": ROLES[vtype], "visual_type": vtype,
              "clickable": vtype in CLICKABLE, "editable": vtype == "input_field",
              "scrollable": False, "confidence": 1.0, "source_label": label}
        if caption:
            el["text"] = el["label"] = caption
        elements.append(el)
    return {"version": "1.0", "image_size": [width, height],
            "element_count": len(elements), "elements": elements,
            "parser": {"dropped": stats, "complete": "</screentag>" in text}}


# --------------------------------------------------------------------------- #
# The model
# --------------------------------------------------------------------------- #

class ScreenVlmParser:
    """ScreenVLM behind `parse(image_bgr) -> DOM`, run as its model card says."""

    name = "screenvlm"
    MODEL = "docling-project/ScreenVLM"
    # the `main` (ScreenParse v2) checkpoint as downloaded on 2026-11-15
    REVISION = "78df0cc8498bbea1a03eb2816056fc0a76d2f63d"
    PROMPT = "Generate the screen representation for this UI:"
    MAX_NEW_TOKENS = 6192
    MIN_TRANSFORMERS = (4, 55)

    def __init__(self, model_path: Optional[str] = None, revision: Optional[str] = None,
                 device: Optional[str] = None):
        self.model_path = model_path or os.environ.get("VIZDOM_SCREENVLM_PATH", self.MODEL)
        self.revision = revision or (self.REVISION if self.model_path == self.MODEL else None)
        self.device = device or os.environ.get("VIZDOM_PARSER_DEVICE")
        self.load_seconds = 0.0
        self.last_raw = None
        self.last_tokens = 0
        self._model = self._processor = None

    def available(self) -> Tuple[bool, str]:
        try:
            import torch  # noqa: F401
            import transformers
        except Exception as exc:  # noqa: BLE001
            return False, f"torch/transformers not importable: {exc}"
        version = tuple(int(p) for p in re.findall(r"\d+", transformers.__version__)[:2])
        if version < self.MIN_TRANSFORMERS:
            return False, (f"transformers {transformers.__version__} is too old for ScreenVLM "
                           f"(needs >= {'.'.join(map(str, self.MIN_TRANSFORMERS))}); run this "
                           f"column from a second environment, or re-score saved DOMs with "
                           f"--parser-doms")
        return True, f"{self.model_path} @ {self.revision or 'local'}"

    def _ensure(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor
        t0 = time.perf_counter()
        if not self.device:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        kw = {"revision": self.revision} if self.revision else {}
        self._processor = AutoProcessor.from_pretrained(self.model_path, **kw)
        self._model = AutoModelForVision2Seq.from_pretrained(
            self.model_path, torch_dtype=self._dtype, **kw).to(self.device).eval()
        self.load_seconds = time.perf_counter() - t0

    def generate(self, image_bgr) -> str:
        """The raw ScreenTag text for one screenshot."""
        import torch
        from PIL import Image
        self._ensure()
        image = Image.fromarray(image_bgr[:, :, ::-1].copy())
        messages = [{"role": "user", "content": [{"type": "image"},
                                                 {"type": "text", "text": self.PROMPT}]}]
        prompt = self._processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self._processor(text=prompt, images=[image], return_tensors="pt").to(self.device)
        inputs["pixel_values"] = inputs["pixel_values"].to(self._dtype)
        with torch.no_grad():
            ids = self._model.generate(**inputs, max_new_tokens=self.MAX_NEW_TOKENS,
                                       do_sample=False, use_cache=True)
        n = inputs["input_ids"].shape[1]
        self.last_tokens = int(ids.shape[1] - n)
        return self._processor.batch_decode(ids[:, n:], skip_special_tokens=False)[0].lstrip()

    def parse(self, image_bgr) -> dict:
        raw = self.generate(image_bgr)
        self.last_raw = raw
        height, width = image_bgr.shape[:2]
        dom = screentag_to_dom(raw, (width, height))
        dom["parser"].update({"model": self.model_path, "revision": self.revision,
                              "device": self.device, "new_tokens": self.last_tokens,
                              "truncated": self.last_tokens >= self.MAX_NEW_TOKENS,
                              "raw": raw})
        return dom


PARSERS = {"screenvlm": ScreenVlmParser}

# --------------------------------------------------------------------------- #
# The executor
# --------------------------------------------------------------------------- #

PICKS = ("unique", "first")


def parse_parser_spec(spec: str):
    """`screenvlm` or `screenvlm[pick=first]` -> (parser name, options, suffix)."""
    name, suffix, options = spec, "", {}
    if "[" in spec:
        if not spec.endswith("]"):
            raise ValueError(f"bad column spec {spec!r}: expected parser[key=value,...]")
        name, inner = spec[:-1].split("[", 1)
        suffix = f"[{inner}]"
        for item in [i.strip() for i in inner.split(",") if i.strip()]:
            key, _, value = item.partition("=")
            if key.strip() != "pick" or value.strip() not in PICKS:
                raise ValueError(f"unknown switch {item!r} in {spec!r}; known: "
                                 f"pick={'|'.join(PICKS)}")
            options["pick"] = value.strip()
    if name not in PARSERS:
        raise ValueError(f"unknown parser {name!r}; choose from {sorted(PARSERS)}")
    return name, options, suffix


class ParserExecutor:
    """A whole-screen parser resolved step by step like the VizDOM column."""

    def __init__(self, parser, pick: str = "unique", suffix: str = "",
                 dom_cache_dir: Optional[str] = None):
        if pick not in PICKS:
            raise ValueError(f"pick must be one of {PICKS}")
        self.name = f"{parser.name}{suffix}"
        self.parser = parser
        self.pick = pick
        self.dom_cache_dir = Path(dom_cache_dir) if dom_cache_dir else None
        self.dom_dump_dir = None            # set by run_benchmark
        self._doms: Dict[str, dict] = {}
        self._finders: Dict[str, object] = {}
        self._parse_seconds: Dict[str, float] = {}
        self._reused = 0

    def _dom_for(self, state) -> dict:
        sid = state["id"]
        if sid in self._doms:
            return self._doms[sid]
        cached = self.dom_cache_dir / f"{sid}.json" if self.dom_cache_dir else None
        if cached is not None and cached.is_file():
            dom = json.loads(cached.read_text(encoding="utf-8"))
            self._reused += 1
        else:
            import cv2
            image = cv2.imread(state["image"])
            if image is None:
                raise FileNotFoundError(state["image"])
            if hasattr(self.parser, "_ensure"):
                self.parser._ensure()       # loading is a one-time cost, not parse time
            t0 = time.perf_counter()
            dom = self.parser.parse(image)
            self._parse_seconds[sid] = time.perf_counter() - t0
            dom.setdefault("parser", {})["seconds"] = round(self._parse_seconds[sid], 2)
            if cached is not None:
                self._write(cached, dom)
        if self.dom_dump_dir:
            self._write(Path(self.dom_dump_dir) / f"{sid}.json", dom)
        self._doms[sid] = dom
        return dom

    @staticmethod
    def _write(path: Path, dom: dict):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(dom, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:      # a dump failure must not fail the column
            log.warning("could not write %s: %s", path, exc)

    def run_step(self, state, step):
        from visual_gui_library.locators import ElementFinder, LocatorParser
        sid = state["id"]
        if sid not in self._finders:
            self._finders[sid] = ElementFinder(self._dom_for(state))
        t0 = time.perf_counter()
        matches = self._finders[sid].find(LocatorParser.parse(step["locator"]))
        latency = time.perf_counter() - t0
        if step["kind"] == "action":
            if not matches or (len(matches) != 1 and self.pick == "unique"):
                return {"outcome": None, "latency": latency,
                        "detail": f"{len(matches)} matches"}
            b = matches[0]["bounds"]
            return {"outcome": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2), "latency": latency,
                    "detail": "resolved" if len(matches) == 1
                    else f"first of {len(matches)} matches"}
        return {"outcome": "PASSED" if matches else "FAILED", "latency": latency,
                "detail": f"{len(matches)} matches"}

    def cost_summary(self):
        secs = self._parse_seconds
        return {"parses": len(secs), "doms_reused": self._reused,
                "model_load_seconds": round(getattr(self.parser, "load_seconds", 0.0), 2),
                "parse_seconds_total": round(sum(secs.values()), 2),
                "parse_seconds_mean": round(sum(secs.values()) / len(secs), 2) if secs else None}


def build_executor(spec: str, dom_cache_dir: Optional[str] = None) -> ParserExecutor:
    """A column from its name; refuses when neither the model nor saved DOMs can serve it."""
    name, options, suffix = parse_parser_spec(spec)
    parser = PARSERS[name]()
    ok, reason = parser.available()
    if not ok:
        if not (dom_cache_dir and any(Path(dom_cache_dir).glob("*.json"))):
            raise SystemExit(f"{spec} is not runnable here: {reason}")
        reason = f"saved DOMs from {dom_cache_dir} only ({reason})"
    print(f"{name}{suffix}: {reason}")
    return ParserExecutor(parser, pick=options.get("pick", "unique"), suffix=suffix,
                          dom_cache_dir=dom_cache_dir)


# --------------------------------------------------------------------------- #
# Detection scores of saved DOMs
# --------------------------------------------------------------------------- #

def detection_scores(labels_dir, dom_dir, iou_threshold: float = 0.5) -> dict:
    """
    Boxes of the saved DOMs in `dom_dir` against the labels of the same name.

    Greedy matching at `iou_threshold`, type-agnostic, pooled over the screens
    (the per-stage evaluator's matching). Per labelled type: how many of its
    elements were matched. Works for any column's DOM folder, so two parsers
    are scored by the same code on the same screens.
    """
    from collections import Counter
    from visual_dom.evaluation.evaluator import EvaluationConfig, VisualDOMEvaluator
    ev = VisualDOMEvaluator(EvaluationConfig(iou_threshold=iou_threshold,
                                             evaluate_hierarchy=False, evaluate_locators=False))
    tp = fp = fn = type_ok = screens = 0
    ious, labelled, found = [], Counter(), Counter()
    for f in sorted(Path(dom_dir).glob("*.json")):
        g = Path(labels_dir) / f.name
        if not g.is_file():
            continue
        screens += 1
        pred = ev._extract_elements(json.loads(f.read_text(encoding="utf-8")))
        gt = ev._extract_elements(json.loads(g.read_text(encoding="utf-8")))
        m = ev._evaluate_elements(pred, gt)
        tp, fp, fn = tp + m.true_positives, fp + m.false_positives, fn + m.false_negatives
        ious += m.iou_scores
        by_pred = {str(e.get("id", i)): e for i, e in enumerate(pred)}
        by_gt = {str(e.get("id", i)): e for i, e in enumerate(gt)}
        labelled.update(e.get("visual_type") for e in gt)
        for p_id, g_id, _ in m.matched_pairs:
            vtype = by_gt[str(g_id)].get("visual_type")
            found[vtype] += 1
            type_ok += by_pred[str(p_id)].get("visual_type") == vtype
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"screens": screens, "predicted": tp + fp, "labelled": tp + fn,
            "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(2 * precision * recall / (precision + recall), 3)
            if precision + recall else 0.0,
            "miou_matched": round(sum(ious) / len(ious), 3) if ious else 0.0,
            "type_accuracy_matched": round(type_ok / tp, 3) if tp else 0.0,
            "recall_by_type": {t: [found[t], labelled[t]] for t in sorted(labelled, key=str)}}


def detection_table(rows: Dict[str, dict]) -> str:
    """One markdown table of `detection_scores` results, a row per DOM folder."""
    types = sorted({t for r in rows.values() for t in r["recall_by_type"]}, key=str)
    lines = ["| DOMs | screens | predicted | labelled | precision | recall | F1 "
             "| mIoU of matches | type accuracy | " + " | ".join(f"{t} recall" for t in types) + " |",
             "|" + "---|" * (9 + len(types))]
    for name, r in rows.items():
        cells = []
        for t in types:
            hit, total = r["recall_by_type"].get(t, [0, 0])
            cells.append(f"{hit / total:.3f} ({hit}/{total})" if total else "-")
        lines.append(f"| {name} | {r['screens']} | {r['predicted']} | {r['labelled']} "
                     f"| {r['precision']} | {r['recall']} | {r['f1']} | {r['miou_matched']} "
                     f"| {r['type_accuracy_matched']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Parser columns: detection scores of saved DOMs")
    sub = ap.add_subparsers(dest="command", required=True)
    sc = sub.add_parser("score", help="boxes of saved DOM folders against the labels")
    sc.add_argument("--labels", required=True, help="label folder (<state>.json)")
    sc.add_argument("--doms", required=True, nargs="+",
                    help="DOM folders (<state>.json), one row each; name=folder sets the row name")
    sc.add_argument("--iou", type=float, default=0.5)
    sc.add_argument("--out", default=None, help="write the table here as well")
    args = ap.parse_args()
    rows = {}
    for item in args.doms:
        name, _, folder = item.rpartition("=")
        rows[name or Path(folder).name] = detection_scores(args.labels, folder, args.iou)
    table = detection_table(rows)
    if args.out:
        Path(args.out).write_text(table + "\n", encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
