"""
Audit of a lifecycle benchmark's evidence, from files a run already left.

``compare`` says what each executor scored. This module asks how far those
scores can be trusted, without running any model:

1. **Clustered statistics.** Steps share screens and screens share
   applications, so a step-level Wilson interval or McNemar test is too
   optimistic. Per executor: cluster-bootstrap intervals over states and
   over applications; for a zero false-pass count, the number of clusters
   it held on and the bound that gives. Per pair: a paired sign-flip
   permutation test over states (exact over applications), Holm-adjusted,
   with the false-pass comparisons named as the primary ones.
2. **Cost-weighted verification.** A false pass costs more than a false
   fail; the cost per verify step for a range of cost ratios.
3. **Are the absent targets absent?** Every negative caption is searched in
   an OCR read of its own screenshot (two engines), and a contact sheet is
   written for a human pass.
4. **What the ground-truth filter removed.** Named UIA elements kept as
   steps against those dropped as icon-only or not printed, per application.
5. **Sensitivity of the hand-set constants.** The lexical tier re-scored over
   the saved DOMs with the floor, the margin and each weight moved one at a
   time. The product code is not edited: the module's functions are patched
   in memory for the sweep and restored.
6. **Near-miss negatives.** Absent captions that share words with a caption
   on the screen ("Save" where only "Save As" is shown), built by rules that
   do not look at the scorer, and scored for ``text=`` and ``desc=`` as they
   are and under a stricter exact-name rule that is NOT in the product.

    python -m visual_dom.evaluation.lifecycle.audit \\
        --run benchmarks/results/gpu-20261108_221541 \\
        --benchmark lifecycle-realworld-v1 \\
        --out benchmarks/lifecycle-realworld-v1/AUDIT.md --ocr
"""
from __future__ import annotations

import argparse
import html
import inspect
import json
import math
import re
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from visual_dom.evaluation.lifecycle.compare import (
    SET_DIRS, load_sets, mcnemar, step_ok, unpack, wilson,
)

_WORD = re.compile(r"[a-z0-9]+")
COST_RATIOS = (1, 5, 10, 50)


# --------------------------------------------------------------------------- #
# clusters
# --------------------------------------------------------------------------- #

def state_of(step_id: str) -> str:
    return step_id.split("/", 1)[0]


def group_of(step_id: str) -> str:
    """The application of a real-application step (``<app>__<state>``), the
    screen family of a synthetic one (``form_sidebar_0007`` -> form_sidebar)."""
    state = state_of(step_id)
    return state.split("__", 1)[0] if "__" in state else re.sub(r"_\d+$", "", state)


def cluster_bootstrap(rows, cluster, n_boot=5000, seed=7):
    """95 % percentile interval of sum(ok) / n when whole clusters are
    resampled with replacement. ``rows`` are (step id, ok)."""
    k, n = defaultdict(int), defaultdict(int)
    for step, ok in rows:
        c = cluster(step)
        k[c] += bool(ok)
        n[c] += 1
    if not n:
        return None, None
    keys = sorted(n)
    kc = np.array([k[c] for c in keys], dtype=float)
    nc = np.array([n[c] for c in keys], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    rate = kc[idx].sum(axis=1) / nc[idx].sum(axis=1)
    lo, hi = np.percentile(rate, [2.5, 97.5])
    return float(lo), float(hi)


def zero_of_clusters_bound(m, alpha=0.05):
    """One-sided 95 % upper bound on the share of clusters that would show the
    event, when it was seen in 0 of m (Clopper-Pearson)."""
    return 1 - alpha ** (1.0 / m) if m else None


def cluster_permutation(a_rows, b_rows, cluster, n_perm=20000, seed=7):
    """
    Paired sign-flip test with the cluster as the unit. Per cluster,
    d = (steps only A got right) - (steps only B got right); under "no
    difference" each cluster's d is as likely to be -d. Exact when there are
    at most 16 clusters, Monte Carlo otherwise. Returns (sum d, p).
    """
    b = dict(b_rows)
    d = defaultdict(int)
    for step, ok in a_rows:
        if step in b:
            d[cluster(step)] += int(bool(ok)) - int(bool(b[step]))
    vals = np.array([v for v in d.values() if v != 0], dtype=float)
    total = float(sum(d.values()))
    if len(vals) == 0:
        return total, 1.0
    if len(vals) <= 16:
        signs = np.array([[1 if (i >> j) & 1 else -1 for j in range(len(vals))]
                          for i in range(2 ** len(vals))], dtype=float)
        p = float(np.mean(np.abs(signs @ vals) >= abs(vals.sum()) - 1e-9))
        return total, p
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(vals)))
    hits = int(np.sum(np.abs(signs @ vals) >= abs(vals.sum()) - 1e-9))
    return total, (hits + 1) / (n_perm + 1)


def holm(pvals):
    """Holm step-down adjusted p-values, in the input order."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    adj, running = [0.0] * len(pvals), 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(pvals) - rank) * pvals[i])
        adj[i] = min(1.0, running)
    return adj


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _f(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def _ci(pair):
    return "-" if pair[0] is None else f"[{pair[0]:.3f}, {pair[1]:.3f}]"


def _p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _tokens(s):
    return _WORD.findall((s or "").lower())


def split_rows(result, manifest):
    """{'clicks' | 'present' | 'absent': [(step id, ok)]} of one executor."""
    out = {"clicks": [], "present": [], "absent": []}
    for r in result["steps"]:
        if r["kind"] == "action":
            out["clicks"].append((r["step"], step_ok(r)))
        elif manifest.get(r["step"], {}).get("expect") == "FAILED":
            out["absent"].append((r["step"], step_ok(r)))
        else:
            out["present"].append((r["step"], step_ok(r)))
    return out


def default_rows(execs):
    """The VizDOM rows a reader is shown: text=, and the description chains
    that start with the lexical tier and are scored as the keywords score."""
    return [n for n in execs
            if n.startswith("vizdom") and "[verify=" not in n
            and ("+desc[" not in n or "+desc[lexical" in n)]


# --------------------------------------------------------------------------- #
# 1 + 2: statistics
# --------------------------------------------------------------------------- #

def stats_section(execs, manifest, rows=None):
    rows = rows or default_rows(execs)
    grounders = [n for n in execs if not n.startswith("vizdom")]
    split = {n: split_rows(execs[n], manifest) for n in execs}
    out = ["## 1. Clustered intervals", "",
           "A step is not an independent draw: about twenty share a screen and several "
           "screens share an application. The step-level Wilson interval is shown beside "
           "two cluster-bootstrap intervals (5 000 resamples of whole states, and of whole "
           "applications or screen families). Where the cluster intervals are wider, they "
           "are the ones to quote.", ""]
    for kind, title in (("clicks", "action-hit"), ("present", "present → pass")):
        out += [f"### {title}", "",
                "| executor | rate | Wilson (steps) | bootstrap (states) | bootstrap (apps) |",
                "|---|---|---|---|---|"]
        for n in rows + grounders:
            r = split[n][kind]
            k, tot = sum(ok for _, ok in r), len(r)
            out.append(f"| {n} | {_f(k / tot if tot else None)} ({k}/{tot}) | {_ci(wilson(k, tot))} | "
                       f"{_ci(cluster_bootstrap(r, state_of))} | {_ci(cluster_bootstrap(r, group_of))} |")
        out.append("")

    out += ["### false passes on absent targets", "",
            "For a count of zero a bootstrap interval is [0, 0] and says nothing. The honest "
            "statement is per cluster: the event was seen on 0 of m screens, which bounds the "
            "share of screens that would show it (one-sided 95 %).", "",
            "| executor | false passes | Wilson (steps) | screens with one | apps with one | "
            "bound on screens |", "|---|---|---|---|---|---|"]
    for n in rows + grounders:
        r = split[n]["absent"]
        fps = [s for s, ok in r if not ok and
               any(x["step"] == s and x.get("false_pass") for x in execs[n]["steps"])]
        states = {state_of(s) for s, _ in r}
        apps = {group_of(s) for s, _ in r}
        bad_states = {state_of(s) for s in fps}
        bad_apps = {group_of(s) for s in fps}
        bound = zero_of_clusters_bound(len(states)) if not fps else None
        out.append(f"| {n} | {len(fps)}/{len(r)} | {_ci(wilson(len(fps), len(r)))} | "
                   f"{len(bad_states)}/{len(states)} | {len(bad_apps)}/{len(apps)} | "
                   f"{'≤ ' + _f(bound) if bound is not None else '-'} |")
    out.append("")

    if grounders and rows:
        out += ["## 2. Paired tests with the cluster as the unit", "",
                "Exact McNemar treats every step as its own coin. The permutation test "
                "flips whole screens (Monte Carlo, 20 000 draws) or whole applications "
                "(exact). **Primary comparisons, named before looking at these tables: the "
                "false-pass comparison of each quoted VizDOM row with each grounder** "
                "(the `absent` rows). Everything else is secondary and Holm-adjusted "
                "together; a secondary p that does not survive the adjustment is not a "
                "finding.", "",
                "| VizDOM row | grounder | steps | only ours / only theirs | McNemar p | "
                "p (screens) | p (apps) | Holm (screens) | family |",
                "|---|---|---|---|---|---|---|---|---|"]
        tests = []
        for n in rows:
            for g in grounders:
                for kind in ("absent", "clicks", "present"):
                    a, b = split[n][kind], split[g][kind]
                    ra = [{"step": s, "kind": "verify", "correct": ok} for s, ok in a]
                    rb = [{"step": s, "kind": "verify", "correct": ok} for s, ok in b]
                    oa, ob, p_mc = mcnemar(ra, rb)
                    _, p_state = cluster_permutation(a, b, state_of)
                    _, p_app = cluster_permutation(a, b, group_of)
                    tests.append([n, g, kind, oa, ob, p_mc, p_state, p_app])
        for family in ("primary", "secondary"):
            idx = [i for i, t in enumerate(tests) if (t[2] == "absent") == (family == "primary")]
            for i, adj in zip(idx, holm([tests[i][6] for i in idx])):
                tests[i] += [adj, family]
        for n, g, kind, oa, ob, p_mc, p_state, p_app, adj, family in tests:
            out.append(f"| {n} | {g} | {kind} | {oa} / {ob} | {_p(p_mc)} | {_p(p_state)} | "
                       f"{_p(p_app)} | {_p(adj)} | {family} |")
        out.append("")

    out += ["## 3. Cost-weighted verification", "",
            "A false pass (an absent target accepted) hides a defect; a false fail (a "
            "present target rejected) stops a test and is looked at. Cost per verify step "
            "with a false fail costing 1 and a false pass costing c:", "",
            "| executor | false fails | false passes | "
            + " | ".join(f"c = {c}" for c in COST_RATIOS) + " |",
            "|---|---|---|" + "---|" * len(COST_RATIOS)]
    for n in rows + grounders:
        ff = sum(1 for _, ok in split[n]["present"] if not ok)
        fp = sum(1 for r in execs[n]["steps"] if r.get("false_pass"))
        total = len(split[n]["present"]) + len(split[n]["absent"])
        out.append(f"| {n} | {ff} | {fp} | "
                   + " | ".join(_f((ff + c * fp) / total) for c in COST_RATIOS) + " |")
    out.append("")
    return out


# --------------------------------------------------------------------------- #
# 3: are the absent targets absent?
# --------------------------------------------------------------------------- #

def contains_sequence(haystack, needle):
    """needle's tokens occur in haystack's tokens, in order and adjacent."""
    if not needle:
        return False
    return any(haystack[i:i + len(needle)] == needle
               for i in range(len(haystack) - len(needle) + 1))


def ocr_readers():
    """{engine name: image (BGR) -> token list}; an engine that cannot load is
    left out with a note instead of failing the audit."""
    readers, notes = {}, []
    try:
        import pytesseract

        from visual_dom.adapters.outbound.ocr.text_detector import find_tesseract
        exe = find_tesseract()
        if not exe:
            raise RuntimeError("no tesseract binary")
        pytesseract.pytesseract.tesseract_cmd = exe

        def tess(image):
            import cv2
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            return _tokens(" ".join(pytesseract.image_to_string(big, config=f"--psm {m}")
                                    for m in (6, 11)))
        readers["tesseract"] = tess
    except Exception as exc:  # noqa: BLE001
        notes.append(f"tesseract not used: {exc}")
    try:
        import easyocr
        reader = easyocr.Reader(["en"], verbose=False)

        def easy(image):
            return _tokens(" ".join(t for _, t, _ in reader.readtext(image)))
        readers["easyocr"] = easy
    except Exception as exc:  # noqa: BLE001
        notes.append(f"easyocr not used: {exc}")
    return readers, notes


def negatives_section(manifest_file, run_ocr, sheet_path=None):
    import cv2

    data = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    states = {s["id"]: s for s in data["states"]}
    negs = [s for s in data["steps"] if s.get("expect") == "FAILED"]
    caption = lambda s: re.match(r'text="(.*)"$', s["locator"]).group(1)   # noqa: E731
    out = ["## 4. Are the absent targets absent?", "",
           f"{len(negs)} negative steps. By construction none equals, contains or is contained "
           "in any UIA name of its screen (`generate._absent_here`). UIA does not see everything "
           "that is painted, so each caption is also searched, as an adjacent word sequence, in "
           "a whole-screen OCR read by engines independent of each other.", ""]
    found = defaultdict(list)
    if run_ocr:
        readers, notes = ocr_readers()
        out += [f"- {n}" for n in notes] + ([""] if notes else [])
        reads = {}
        for step in negs:
            sid = step["state"]
            if sid not in reads:
                image = cv2.imread(states[sid]["image"])
                reads[sid] = {name: read(image) for name, read in readers.items()}
            for name, toks in reads[sid].items():
                if contains_sequence(toks, _tokens(caption(step))):
                    found[step["id"]].append(name)
        out += [f"Engines: {', '.join(readers) or 'none'}. Captions found printed on their own "
                f"screen: **{len(found)} of {len(negs)}**.", ""]
        if found:
            out += ["| step | caption | read by |", "|---|---|---|"]
            out += [f"| {sid} | {caption(manifest_step)} | {', '.join(found[sid])} |"
                    for sid in sorted(found)
                    for manifest_step in [next(s for s in negs if s["id"] == sid)]]
            out.append("")
    else:
        out += ["(OCR check not run; pass `--ocr`.)", ""]
    if sheet_path:
        by_state = defaultdict(list)
        for s in negs:
            by_state[s["state"]].append(s)
        sheet = Path(sheet_path)
        parts = ["<!doctype html><meta charset='utf-8'><title>Absent targets, by screen</title>",
                 "<style>body{font:14px system-ui;margin:24px;max-width:1100px}"
                 "section{margin:0 0 36px;border-top:1px solid #ccc;padding-top:12px}"
                 "img{max-width:100%;border:1px solid #999}li{margin:4px 0}"
                 ".hit{color:#b00020;font-weight:600}</style>",
                 f"<h1>Absent targets, by screen ({len(negs)} steps on {len(by_state)} screens)</h1>",
                 "<p>For each screen: is any listed caption visible as a control of that kind? "
                 "It should not be. A caption an OCR engine found on the screen is marked.</p>"]
        for sid in sorted(by_state):
            rel = Path(states[sid]["image"]).resolve().relative_to(sheet.parent.resolve()).as_posix() \
                if sheet.parent.resolve() in Path(states[sid]["image"]).resolve().parents \
                else Path(states[sid]["image"]).resolve().as_uri()
            parts.append(f"<section><h2>{html.escape(sid)}</h2><ul>")
            for s in by_state[sid]:
                mark = (f" <span class='hit'>found by {', '.join(found[s['id']])}</span>"
                        if s["id"] in found else "")
                parts.append(f"<li>{html.escape(s['instruction'])} "
                             f"<small>({s.get('negative_kind', 'nonsense')})</small>{mark}</li>")
            parts.append(f"</ul><img src='{rel}' loading='lazy'></section>")
        sheet.write_text("\n".join(parts), encoding="utf-8")
        out += [f"Contact sheet for the human pass: `{sheet.as_posix()}`.", ""]
    return out


# --------------------------------------------------------------------------- #
# 4: the ground-truth filter
# --------------------------------------------------------------------------- #

def filter_section(labels_dir, manifest):
    per = defaultdict(Counter)
    for f in sorted(Path(labels_dir).glob("*.json")):
        gt = json.loads(f.read_text(encoding="utf-8"))
        app = f.stem.split("__", 1)[0]
        for e in gt["elements"]:
            if e.get("visual_type") in ("button", "input_field", "checkbox", "icon"):
                per[app][e.get("review") or "kept"] += 1
    steps = Counter(group_of(s) for s, m in manifest.items() if m["kind"] == "action")
    out = ["## 5. What the ground-truth filter removed", "",
           "A step exists only for an actionable element whose UIA name the harvester could "
           "confirm as printed (Tesseract on the element's box), and whose caption is unique "
           "on the screen. That keeps the truth honest (a spoken name such as \"Memory "
           "recall\" is not a caption) and it also selects for captions an OCR engine can "
           "read, which is the input VizDOM depends on and the grounders do not. The size of "
           "that selection, over actionable elements:", "",
           "| application | kept | icon-only | name not printed | share dropped | click steps |",
           "|---|---|---|---|---|---|"]
    tot = Counter()
    for app in sorted(per):
        c = per[app]
        tot.update(c)
        n = sum(c.values())
        out.append(f"| {app} | {c['kept']} | {c['icon-only?']} | {c['name not printed']} | "
                   f"{_f((n - c['kept']) / n if n else None, 2)} | {steps.get(app, 0)} |")
    n = sum(tot.values())
    out += [f"| **all** | {tot['kept']} | {tot['icon-only?']} | {tot['name not printed']} | "
            f"{_f((n - tot['kept']) / n if n else None, 2)} | {sum(steps.values())} |", "",
            "Icon-only controls carry no caption to locate by, for any locator that names a "
            "caption; a grounder can still click them from an instruction such as \"click the "
            "bold icon\", and this benchmark does not ask it to. The comparison is therefore a "
            "comparison **on captioned controls**, and says nothing about icon-only ones.", ""]
    return out


# --------------------------------------------------------------------------- #
# 5 + 6: offline lexical scoring, the sweep and the near-miss negatives
# --------------------------------------------------------------------------- #

DEFAULTS = {"floor": 1.5, "margin": 0.5, "name": 2.0, "substring": 0.7, "role": 1.0,
            "exact_bonus": 0.5}
_WEIGHT_PATTERNS = {            # literal in lexical_rank -> placeholder
    "name": ("name_score = 2.0 * overlap", "name_score = {v} * overlap"),
    "substring": ("(hits + 0.7 * subs)", "(hits + {v} * subs)"),
    "role": ("                kind_score += 1.0", "                kind_score += {v}"),
}


@contextmanager
def scorer_settings(**overrides):
    """
    The lexical scorer with some constants changed, for the duration of the
    block. Nothing on disk changes: ``lexical_confident`` is wrapped for the
    floor and the margin, ``EXACT_NAME_BONUS`` is set, and for a weight the
    source of ``lexical_rank`` is re-compiled with that one literal replaced
    (each literal must occur exactly once, or the sweep refuses to run rather
    than sweep something else).
    """
    from visual_gui_library.locators import desc_resolver as dr

    unknown = set(overrides) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown constants {sorted(unknown)}")
    cfg = dict(DEFAULTS, **overrides)
    saved = (dr.lexical_rank, dr.lexical_confident, dr.EXACT_NAME_BONUS)
    try:
        src = inspect.getsource(saved[0])
        changed = False
        for key, (literal, template) in _WEIGHT_PATTERNS.items():
            if src.count(literal) != 1:
                raise RuntimeError(f"lexical_rank no longer contains {literal!r} exactly once")
            if cfg[key] != DEFAULTS[key]:
                src = src.replace(literal, template.format(v=repr(float(cfg[key]))))
                changed = True
        if changed:
            scope = dict(vars(dr))
            exec(compile(src, "<lexical_rank sweep>", "exec"), scope)   # noqa: S102
            dr.lexical_rank = scope["lexical_rank"]
        confident = saved[1]
        dr.lexical_confident = lambda ranked, min_score=None, min_margin=None: confident(
            ranked, cfg["floor"] if min_score is None else min_score,
            cfg["margin"] if min_margin is None else min_margin)
        dr.EXACT_NAME_BONUS = cfg["exact_bonus"]
        yield cfg
    finally:
        dr.lexical_rank, dr.lexical_confident, dr.EXACT_NAME_BONUS = saved


def load_doms(run_dirs, benchmark, column="vizdom-modular"):
    """{state id: dom} of the newest dump of ``column`` for ``benchmark``."""
    for run in reversed([Path(r) for r in run_dirs]):
        for base in [run / s for s in SET_DIRS] + [run]:
            for res in sorted(base.glob("[0-9]*_[0-9]*.json"), reverse=True):
                data = json.loads(res.read_text(encoding="utf-8"))
                if data.get("benchmark") != benchmark or column not in data.get("results", {}):
                    continue
                d = base / f"{res.stem}-doms" / column
                if d.is_dir():
                    return {f.stem: json.loads(f.read_text(encoding="utf-8"))
                            for f in d.glob("*.json")}
    return {}


def _inside(elem, bounds):
    if elem is None or not bounds:
        return False
    b = elem.get("bounds", [0, 0, 0, 0])
    x, y = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]


def desc_match(dom, description):
    """What ``Visual Should Exist  desc=...`` matches: the finder's lexical element or None."""
    from visual_gui_library.locators.locator import ElementFinder, Locator, LocatorStrategy
    found = ElementFinder(dom).find([Locator(LocatorStrategy.DESC, description)])
    return found[0] if found else None


def text_matches(dom, caption):
    from visual_gui_library.locators.locator import ElementFinder, LocatorParser
    return ElementFinder(dom).find(LocatorParser.parse(f'text="{caption}"'))


def exact_name(elem, description, dom):
    """The stricter rule that is NOT in the product: the matched element has
    a field that reads exactly the description's name words, in order."""
    from visual_gui_library.locators import desc_resolver as dr
    name_tokens = dr.parse_description(description, dr.element_tokens(dom.get("elements", [])))[0]
    return bool(name_tokens) and any(
        dr._tokens(str(elem.get(k) or "")) == name_tokens for k in ("label", "text", "hint"))


def lexical_scores(steps, doms, strict=False):
    """Clicks, present and absent counts of the lexical tier alone over saved DOMs."""
    c = Counter()
    for s in steps:
        dom = doms.get(s["state"])
        if dom is None:
            continue
        elem = desc_match(dom, s["description"])
        if strict and elem is not None and not exact_name(elem, s["description"], dom):
            elem = None
        if s["kind"] == "action":
            c["clicks"] += 1
            c["click_hit"] += _inside(elem, s.get("target_bounds"))
        elif s.get("expect") == "FAILED":
            c["absent"] += 1
            c["false_pass"] += elem is not None
        else:
            c["present"] += 1
            c["present_pass"] += elem is not None
    return c


def near_miss_negatives(labels, steps):
    """
    Absent captions that share words with a caption the screen does show.

    ``sibling``: a real caption of another screen of the same application
    whose words contain, or are contained in, the words of a name on this
    screen, while no name on this screen reads exactly those words. These are
    the captions ``generate._absent_here`` deliberately left out of the
    benchmark's negatives. ``truncation``: a caption of this screen with its
    last word removed, when no name on the screen reads that. Neither rule
    looks at how any locator scores.
    """
    by_app = defaultdict(set)
    here = defaultdict(list)
    for s in steps:
        if s["kind"] == "verify" and s.get("expect") == "PASSED":
            cap = re.match(r'text="(.*)"$', s["locator"]).group(1)
            word = s["description"][len(cap):].strip() or "button"
            by_app[s["state"].split("__", 1)[0]].add((cap, word, s["state"]))
            here[s["state"]].append((cap, word))
    out = []
    for state, gt in sorted(labels.items()):
        names = [e.get("ocr_text") or "" for e in gt["elements"]] + list(gt.get("all_names", []))
        own = {tuple(_tokens(n)) for n in names if _tokens(n)}
        seen = set()

        def add(cap, word, kind):
            toks = tuple(_tokens(cap))
            if not toks or toks in own or toks in seen or len("".join(toks)) < 3:
                return
            seen.add(toks)
            out.append({"id": f"{state}/near-miss/{cap.replace(' ', '_')}", "state": state,
                        "kind": "verify", "locator": f'text="{cap}"',
                        "description": f"{cap} {word}", "expect": "FAILED",
                        "negative_kind": kind})

        for cap, word, sid in sorted(by_app[state.split("__", 1)[0]]):
            toks = list(_tokens(cap))
            if sid != state and any(contains_sequence(list(o), toks) or contains_sequence(toks, list(o))
                                    for o in own):
                add(cap, word, "sibling")
        for cap, word in here[state]:
            words = cap.split()
            if len(words) >= 2:
                add(" ".join(words[:-1]), word, "truncation")
    return out


NEAR_MISS_BENCHMARK = "lifecycle-realworld-nearmiss-v1"


def near_miss_manifest(data, labels, kinds=("sibling",), benchmark=NEAR_MISS_BENCHMARK):
    """
    The near-miss negatives of a real-application manifest as a manifest the
    runner takes, so that every column - the grounders included - can be
    measured on them (run 9). Negatives only: a row's present -> pass rate is
    the one it has on the source set, which shows the same screens.
    """
    steps = []
    for n in near_miss_negatives(labels, data["steps"]):
        if n["negative_kind"] not in kinds:
            continue
        cap = re.match(r'text="(.*)"$', n["locator"]).group(1)
        word = n["description"][len(cap):].strip()
        steps.append({"id": n["id"], "state": n["state"], "kind": "verify",
                      "locator": n["locator"],
                      "instruction": f"the '{cap}' {word} is visible",   # generate.py's wording
                      "description": n["description"], "expect": "FAILED",
                      "target_id": None, "target_bounds": None,
                      "negative_kind": n["negative_kind"]})
    used = {s["state"] for s in steps}
    return {"benchmark": benchmark, "source": data["benchmark"], "seed": data.get("seed"),
            "negative_kinds": sorted(kinds),
            "states": [s for s in data["states"] if s["id"] in used], "steps": steps}


def _load_labels(data):
    labels = {}
    for d in {Path(s["gt"]).parent for s in data["states"]}:
        for f in d.glob("*.json"):
            labels[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return labels


def near_miss_section(labels, steps, doms):
    negs = near_miss_negatives(labels, steps)
    kinds = Counter(n["negative_kind"] for n in negs)
    rows = Counter()
    examples = defaultdict(list)
    for n in negs:
        dom = doms.get(n["state"])
        if dom is None:
            continue
        cap = re.match(r'text="(.*)"$', n["locator"]).group(1)
        k = n["negative_kind"]
        rows[(k, "n")] += 1
        t = text_matches(dom, cap)
        t_exact = [e for e in t if _tokens(e.get("text") or "") == _tokens(cap)]
        d = desc_match(dom, n["description"])
        for name, hit, got in (("text=", bool(t), t[0] if t else None),
                               ("text= exact only", bool(t_exact), t_exact[0] if t_exact else None),
                               ("desc=", d is not None, d),
                               ("desc= exact name", d is not None and exact_name(d, n["description"], dom), d)):
            rows[(k, name)] += hit
            if hit and len(examples[(k, name)]) < 4:
                examples[(k, name)].append(f"`{cap}` → `{(got.get('text') or got.get('label') or '')[:30]}`")
    cols = ("text=", "text= exact only", "desc=", "desc= exact name")
    out = ["## 7. Near-miss negatives", "",
           "The benchmark's absent targets never share a word sequence with a name on their "
           "screen: `generate._absent_here` treats \"Save\" as *not absent* from a screen that "
           "shows \"Save As\", and leaves such captions out. This section builds exactly those, "
           "by two rules that do not look at any scorer (see `near_miss_negatives`), and asks "
           "each locator whether the caption is there. A pass is a false pass.", "",
           "| kind | negatives | " + " | ".join(f"`{c}`" for c in cols) + " |",
           "|---|---|" + "---|" * len(cols)]
    for k in sorted(kinds):
        out.append(f"| {k} | {rows[(k, 'n')]} | "
                   + " | ".join(f"{rows[(k, c)]} ({_f(rows[(k, c)] / rows[(k, 'n')] if rows[(k, 'n')] else None, 2)})"
                                for c in cols) + " |")
    total = sum(rows[(k, "n")] for k in kinds)
    out.append(f"| **all** | {total} | "
               + " | ".join(f"{sum(rows[(k, c)] for k in kinds)}" for c in cols) + " |")
    out += ["", "`text=` falls back from an exact match to a substring match, so it passes an "
            "absent caption that is the beginning of a present one; `desc=` passes one whose "
            "words all occur in a present caption. The two `exact` columns are a stricter "
            "rule evaluated here only, not shipped: the matched element must read exactly "
            "the caption's words.", "",
            "The `sibling` kind is the fair measure: each is a caption that exists as a "
            "control on another screen of the same application and is not a control here. "
            "The `truncation` kind is a stress test of partial matching and overstates the "
            "problem: a tester who writes the first words of a caption often means the whole "
            "control, and OCR sometimes prints the shorter string as a fragment of its own "
            "(the exact-only columns show how often).", "",
            "Examples (absent caption → element that passed it):", ""]
    for (k, name), ex in sorted(examples.items()):
        out.append(f"- {k}, `{name}`: " + "; ".join(ex))
    out.append("")
    return out, negs


def sweep_section(steps, doms, near_miss):
    out = ["## 6. Sensitivity of the hand-set constants", "",
           "The lexical tier alone, re-scored over the saved DOMs with one constant moved at "
           "a time (the others at their shipped value, marked ◀). No constant was re-tuned; "
           "the question is whether the shipped values sit on a plateau or on an edge. "
           "`near-miss` is the false-pass count on the negatives of section 7.", "",
           "| constant | value | clicks | present → pass | false passes (benchmark) | "
           "false passes (near-miss) |", "|---|---|---|---|---|---|"]
    grid = {"floor": (1.0, 1.25, 1.5, 1.75, 2.0, 2.5),
            "margin": (0.0, 0.25, 0.5, 0.75, 1.0),
            "name": (1.5, 2.0, 2.5),
            "substring": (0.0, 0.35, 0.7, 1.0),
            "role": (0.5, 1.0, 1.5),
            "exact_bonus": (0.0, 0.25, 0.5, 0.75)}
    for const, values in grid.items():
        for v in values:
            with scorer_settings(**{const: v}):
                c = lexical_scores(steps, doms)
                nm = lexical_scores(near_miss, doms)
            mark = " ◀" if v == DEFAULTS[const] else ""
            near = f"{nm['false_pass']}/{nm['absent']}" if nm["absent"] else "-"
            out.append(f"| {const} | {v}{mark} | {_f(c['click_hit'] / c['clicks'])} | "
                       f"{_f(c['present_pass'] / c['present'])} | {c['false_pass']}/{c['absent']} | "
                       f"{near} |")
    out += ["", "How to read it: a neighbouring value that already shows false passes on the "
            "benchmark's own negatives means the shipped value sits at the edge of this set's "
            "zero, not on a plateau. These constants were set by hand and two of them (the "
            "exact-name bonus, the digit rule) on this very set, so only screens the scorer "
            "has never seen can tell tuning from robustness.", "",
            "The stricter exact-name rule of section 7, applied to verification only "
            "(clicks unchanged):", ""]
    c = lexical_scores(steps, doms, strict=True)
    nm = lexical_scores(near_miss, doms, strict=True)
    base = lexical_scores(steps, doms)
    out += ["| verify rule | present → pass | false passes (benchmark) | false passes (near-miss) |",
            "|---|---|---|---|",
            f"| shipped (lexical match) | {_f(base['present_pass'] / base['present'])} | "
            f"{base['false_pass']}/{base['absent']} | "
            f"{lexical_scores(near_miss, doms)['false_pass']}/{nm['absent']} |",
            f"| exact name (not shipped) | {_f(c['present_pass'] / c['present'])} | "
            f"{c['false_pass']}/{c['absent']} | {nm['false_pass']}/{nm['absent']} |", ""]
    return out


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #

def audit(run_dirs, benchmark, manifests_root="benchmarks", run_ocr=False, sheet=None, rows=None):
    run_dirs = [unpack(r) for r in run_dirs]
    execs = {}
    for r in run_dirs:                       # later runs replace earlier rows
        execs.update(load_sets(r).get(benchmark, {}))
    manifest_file = Path(manifests_root) / benchmark / "steps.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest = {s["id"]: s for s in data["steps"]}
    out = [f"# Audit of {benchmark}", "",
           "Generated by `python -m visual_dom.evaluation.lifecycle.audit` from "
           + ", ".join(f"`{r.name}`" for r in run_dirs)
           + ". No model was run: every number below is recomputed from saved step outcomes, "
           "saved DOMs, the manifest and the labels.", ""]
    if execs:
        out += stats_section(execs, manifest, rows)
    out += negatives_section(manifest_file, run_ocr, sheet)
    labels_dirs = {Path(s["gt"]).parent for s in data["states"]}
    labels = _load_labels(data)
    real =any("__" in s for s in labels)
    if real:
        out += filter_section(next(iter(labels_dirs)), manifest)
    doms = load_doms(run_dirs, benchmark)
    if doms:
        near_section, near = near_miss_section(labels, data["steps"], doms) if real else ([], [])
        out += sweep_section(data["steps"], doms, near)
        out += near_section
    else:
        out += ["(no saved DOMs of `vizdom-modular` for this benchmark in the given runs: "
                "sections 6 and 7 skipped)", ""]
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run", action="append", default=[],
                   help="run dir or tarball; repeat to merge (a later run's row replaces an earlier one's)")
    p.add_argument("--near-miss-manifest", metavar="STEPS_JSON",
                   help="write the near-miss negatives of --benchmark as a runnable manifest and stop "
                        f"(no --run needed; benchmark name {NEAR_MISS_BENCHMARK})")
    p.add_argument("--near-miss-kinds", default="sibling",
                   help="comma list from sibling,truncation for --near-miss-manifest")
    p.add_argument("--benchmark", default="lifecycle-realworld-v1")
    p.add_argument("--manifests", default="benchmarks")
    p.add_argument("--rows", help="comma list of VizDOM rows to quote (default: text= and lexical-first desc=)")
    p.add_argument("--ocr", action="store_true", help="search every negative caption in an OCR read of its screen")
    p.add_argument("--sheet", help="write the contact sheet of the negatives here (HTML)")
    p.add_argument("--out", help="write the Markdown here instead of stdout")
    a = p.parse_args(argv)
    if a.near_miss_manifest:
        data = json.loads((Path(a.manifests) / a.benchmark / "steps.json").read_text(encoding="utf-8"))
        kinds = tuple(k.strip() for k in a.near_miss_kinds.split(",") if k.strip())
        m = near_miss_manifest(data, _load_labels(data), kinds)
        out = Path(a.near_miss_manifest)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{out}: {len(m['steps'])} negatives on {len(m['states'])} screens")
        return 0
    if not a.run:
        p.error("--run is required (unless --near-miss-manifest is given)")
    text = audit(a.run, a.benchmark, a.manifests, a.ocr, a.sheet,
                 [r.strip() for r in a.rows.split(",")] if a.rows else None)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        print(a.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
