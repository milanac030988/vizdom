"""
Run the lifecycle benchmark: every executor over the same steps, one table out.

Executors
---------
- ``vizdom-<detector>``  the real VizDOM stack: pipeline once per STATE
  (parse-once), then each step is a locator resolution in the cached DOM.
  Clicks score "action-hit" (element centre inside GT bounds); verifications
  answer from the exactly-one contract.
- ``vizdom-<detector>+desc``  the same DOM, but each step resolves the
  step's natural-language *description* through the ``desc=`` tier chain
  (ADR-022: lexical / SLM over DOM / VLM Set-of-Mark) instead of ``text=``.
  ``--grounding-tiers`` pins the chain, so one column per tier is possible.
- ``<grounder>``         a per-step model (ELAM-7B, UI-TARS, ...): one
  inference per step, no DOM, no reuse.

Scoring
-------
action steps   hit        = produced point inside GT bounds
verify steps   correct    = verdict matches expectation; the FALSE-PASS rate
                            (PASSED on an absent target) is reported separately
                            because in testing a false pass is the worst error.
cost           parses, inferences, and wall-clock are recorded per step so the
               parse-once economics is measured, not argued.

Results are written as JSON (full per-step detail) plus a Markdown summary
table, both stamped with dataset id, git commit, and executor config. The
VizDOM executors also write every parsed DOM to ``<stamp>-doms/<executor>/``
next to the result file, so a step can be diagnosed from the DOM it saw.
"""

import json
import os
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

from typing import List

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Executors
# --------------------------------------------------------------------------- #

#: Ablation switches a column spec may name, `vizdom-modular[roles=off,...]`
#: (benchmarks/README.md sec. 7): each turns one stage of VizDOM's own
#: pipeline off (or the optional refiner on) through the session config, so
#: the column measures what that stage adds on the same detector and steps.
#: Any other `section.key=value` is passed to the config as given.
ABLATION_SWITCHES = {
    ("roles", "off"): {"detector": {"infer_roles": False}},
    ("labels", "off"): {"hierarchy": {"label_max_distance": 0}},
    ("symbols", "off"): {"symbols": {"enabled": False}},
    ("merge", "off"): {"merge": {"merge_oversegmented": False}},
    ("ocr", "plain"): {"ocr": {"upscale": False, "retry_low_confidence": False}},
    ("ocr", "none"): {"ocr": {"engine": "none"}},
    ("ensemble", "off"): {"detector": {"omniparser_text_ensemble": False}},
    ("refiner", "on"): {"refiner": {"enabled": True}},
}


def _coerce(value: str):
    low = value.lower()
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _deep_merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def split_specs(value: str) -> List[str]:
    """
    Split a comma list of column specs without cutting inside brackets:
    "vizdom-modular[roles=off,ocr=plain],elam-7b" -> two specs. A plain
    str.split(",") broke every combined column (review, 2026-10-28).
    """
    out, buf, depth = [], [], 0
    for ch in value:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def parse_vizdom_spec(spec: str):
    """
    `modular` or `modular[roles=off,ocr=plain]` -> (detector, overrides, suffix).

    `suffix` is the bracket part as written (or ""), kept in the column name
    so a result file says which stages were off.
    """
    detector, suffix, overrides = spec, "", {}
    if "[" in spec:
        if not spec.endswith("]"):
            raise ValueError(f"bad column spec {spec!r}: expected detector[key=value,...]")
        detector, inner = spec[:-1].split("[", 1)
        suffix = f"[{inner}]"
        for item in [i.strip() for i in inner.split(",") if i.strip()]:
            if "=" not in item:
                raise ValueError(f"bad switch {item!r} in {spec!r}: expected key=value")
            key, value = (p.strip() for p in item.split("=", 1))
            if (key, value.lower()) in ABLATION_SWITCHES:
                _deep_merge(overrides, json.loads(json.dumps(ABLATION_SWITCHES[(key, value.lower())])))
            elif "." in key:
                section, field = key.split(".", 1)
                _deep_merge(overrides, {section: {field: _coerce(value)}})
            else:
                raise ValueError(f"unknown switch {item!r}; known: "
                                 f"{sorted(f'{k}={v}' for k, v in ABLATION_SWITCHES)} "
                                 f"or section.key=value")
    return detector, overrides, suffix


class VizDomExecutor:
    """The production stack: parse each state once, resolve steps from the DOM."""

    def __init__(self, detector: str, ocr: str = "easyocr", overrides=None, suffix=""):
        self.name = f"vizdom-{detector}{suffix}"
        self.detector = detector
        self.ocr = ocr
        self.overrides = overrides or {}
        self._session = None
        self._dom_cache = {}
        self._parse_seconds = {}
        self._load_seconds = 0.0
        # run_benchmark points this at <out>/<stamp>-doms/<executor>/ so every
        # parsed DOM lands in the tarball: a miss can then be diagnosed from
        # the DOM the step actually saw, not from a laptop re-parse (run 4's
        # false pass needed the GPU DOM of dialog_0141 and it was not kept).
        self.dom_dump_dir = None

    def _connect(self):
        # Session creation loads the models. That is a ONE-TIME warm-up cost -
        # precisely the amortization claim under test (NFR3) - so it is timed
        # separately and must never contaminate any state's parse time.
        if self._session is None:
            import numpy as np
            from visual_dom import connect
            t0 = time.perf_counter()
            self._session = connect(_deep_merge({
                "detector": {"backend": self.detector},
                "ocr": {"engine": self.ocr},
            }, json.loads(json.dumps(self.overrides))))
            # Warm-up analyze on a dummy frame: several components (the easyocr
            # reader, detector weights) initialize lazily on FIRST USE, and
            # without this they would land inside one arbitrary state's parse
            # time instead of the load figure.
            try:
                self._session.analyze(np.zeros((64, 64, 3), dtype=np.uint8))
            except Exception:
                pass  # a dummy-frame quirk must not fail the benchmark
            self._load_seconds = time.perf_counter() - t0
        return self._session

    def _dom_for(self, state):
        sid = state["id"]
        if sid not in self._dom_cache:
            session = self._connect()          # outside the parse timing
            t0 = time.perf_counter()
            dom = session.analyze(state["image"])
            self._parse_seconds[sid] = time.perf_counter() - t0
            self._dom_cache[sid] = dom
            self._dump_dom(sid, dom)
        return self._dom_cache[sid]

    def _dump_dom(self, sid, dom):
        if not self.dom_dump_dir:
            return
        try:
            d = Path(self.dom_dump_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{sid}.json").write_text(
                json.dumps(dom, indent=1, ensure_ascii=False, default=str),
                encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - a dump failure must not fail the column
            log.warning("could not dump DOM of %s: %s", sid, exc)

    def _finder_for(self, state):
        sid = state["id"]
        if sid not in getattr(self, "_finder_cache", {}):
            from visual_gui_library.locators import ElementFinder
            self._finder_cache = getattr(self, "_finder_cache", {})
            self._finder_cache[sid] = ElementFinder(self._dom_for(state))
        return self._finder_cache[sid]

    def run_step(self, state, step):
        from visual_gui_library.locators import LocatorParser
        # Parse cost is amortized across every step of a state - that is the
        # design under test - so it is reported in cost_summary, not folded
        # into one arbitrary step's latency.
        finder = self._finder_for(state)
        t0 = time.perf_counter()
        matches = finder.find(LocatorParser.parse(step["locator"]))
        latency = time.perf_counter() - t0
        if step["kind"] == "action":
            if len(matches) != 1:
                return {"outcome": None, "latency": latency,
                        "detail": f"{len(matches)} matches"}
            b = matches[0].get("bounds", [0, 0, 0, 0])
            point = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
            return {"outcome": point, "latency": latency, "detail": "resolved"}
        # verify: the exactly-one contract answers existence
        verdict = "PASSED" if len(matches) >= 1 else "FAILED"
        return {"outcome": verdict, "latency": latency,
                "detail": f"{len(matches)} matches"}

    def cost_summary(self):
        parses = self._parse_seconds
        return {"parses": len(parses),
                "model_load_seconds": round(self._load_seconds, 2),
                "parse_seconds_total": round(sum(parses.values()), 2),
                "parse_seconds_mean": round(sum(parses.values()) / len(parses), 2)
                if parses else None}


class VizDomDescExecutor(VizDomExecutor):
    """
    The production stack resolving ``desc=`` (ADR-022) instead of ``text=``.

    Same parse-once DOM as `VizDomExecutor`; each step is then ONE
    natural-language resolution through `DescriptionResolver` - the code behind
    ``Get Visual Element  desc="Save button"`` - with the tier chain pinned by
    ``tiers``. Pinning ``["vlm"]`` (or ``["slm"]``) makes the column a head-to-
    head with the grounders: both sides then resolve language, VizDOM over its
    DOM candidates (Set-of-Mark), the grounders over raw pixels.

    A FRESH resolver per step, deliberately: the production per-screen cache
    would answer the verify step from the action step's result (same
    description), and here every step must be its own measurement.
    """

    TIERS = ("lexical", "slm", "vlm")
    DEFAULT_TIERS = ("lexical", "slm")          # VizDomConfig.grounding default
    DEFAULT_MODEL = "qwen2.5:3b"
    # Ollama's library tag is qwen2.5vl (no dash); the config default
    # "qwen2.5-vl:3b" is the HF-style name and 404s on `ollama pull`.
    DEFAULT_VISION_MODEL = "qwen2.5vl:3b"
    DEFAULT_HOST = "http://localhost:11434"

    def __init__(self, detector: str, tiers=DEFAULT_TIERS, backend: str = "ollama",
                 model: str = DEFAULT_MODEL, vision_model: str = DEFAULT_VISION_MODEL,
                 host: str = DEFAULT_HOST, ocr: str = "easyocr",
                 resolver_factory=None, overrides=None, suffix=""):
        super().__init__(detector, ocr, overrides=overrides, suffix=suffix)
        self.tiers = [t.strip() for t in tiers if t.strip()]
        unknown = [t for t in self.tiers if t not in self.TIERS]
        if not self.tiers or unknown:
            raise ValueError(f"grounding tiers must be a non-empty subset of "
                             f"{list(self.TIERS)}, got {list(tiers)!r}")
        self.name = f"vizdom-{detector}{suffix}+desc[{'+'.join(self.tiers)}]"
        self.backend, self.model, self.vision_model, self.host = \
            backend, model, vision_model, host
        # tests inject a factory(dom, screenshot) -> resolver; production builds
        # the real DescriptionResolver
        self._resolver_factory = resolver_factory
        self._tier_counts = Counter()
        self._images = {}

    # -- availability (the same honesty contract as Grounder.available) --------

    def available(self):
        """(ok, reason): can the model tiers of this chain run here?"""
        need = {t: m for t, m in (("slm", self.model), ("vlm", self.vision_model))
                if t in self.tiers}
        if not need:
            return True, "lexical tier only - no model needed"
        if self.backend != "ollama":
            return True, f"backend {self.backend}: {need}"
        import requests
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            have = {m.get("name") for m in r.json().get("models", [])}
        except Exception as exc:  # noqa: BLE001 - any failure means "not here"
            return False, (f"Ollama not reachable at {self.host} ({exc}); "
                           f"start it with `ollama serve`")
        missing = [m for m in need.values()
                   if m not in have and f"{m}:latest" not in have]
        if missing:
            return False, (f"Ollama at {self.host} lacks {missing}; "
                           f"run `ollama pull {' '.join(missing)}`")
        return True, "Ollama at %s: %s" % (
            self.host, ", ".join(f"{t}={m}" for t, m in need.items()))

    # -- per step -----------------------------------------------------------

    def _image_for(self, state):
        sid = state["id"]
        if sid not in self._images:
            import cv2
            self._images[sid] = cv2.imread(state["image"])
        return self._images[sid]

    def _resolver(self, state, dom):
        screenshot = self._image_for(state) if "vlm" in self.tiers else None
        if self._resolver_factory is not None:
            return self._resolver_factory(dom, screenshot)
        from visual_gui_library.locators.desc_resolver import DescriptionResolver
        return DescriptionResolver(dom, screenshot=screenshot, tiers=self.tiers,
                                   backend=self.backend, model=self.model,
                                   vision_model=self.vision_model, host=self.host)

    def run_step(self, state, step):
        description = step.get("description")
        if not description:
            raise RuntimeError("step has no 'description' - regenerate the manifest "
                               "(python -m visual_dom.evaluation.lifecycle.generate)")
        dom = self._dom_for(state)                 # parse once per state, as above
        resolver = self._resolver(state, dom)      # fresh per step (no cache)
        t0 = time.perf_counter()
        elem, info = resolver.resolve(description)
        latency = time.perf_counter() - t0
        full_reason = str(info.get("reason", ""))
        if elem is None and "unavailable" in full_reason:
            # The resolver swallows a dead Ollama ("slm unavailable: ...") so
            # production falls through to the next tier. Here that is a broken
            # environment, not a measurement: raising makes the runner record
            # the step as an error (an all-error column exits 1), instead of
            # scoring a quiet miss that even passes the negative verifies
            # (bench review, 2026-10-27).
            raise RuntimeError(full_reason)
        tier = info.get("tier") or "none"
        self._tier_counts[tier] += 1
        reason = " ".join(full_reason.split())[:160]
        detail = f"tier={tier} {reason}".strip()
        if step["kind"] == "action":
            if elem is None:
                return {"outcome": None, "latency": latency, "detail": detail}
            b = elem.get("bounds", [0, 0, 0, 0])
            point = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
            return {"outcome": point, "latency": latency, "detail": detail}
        # verify: a confident resolution asserts existence, like exactly-one does
        verdict = "PASSED" if elem is not None else "FAILED"
        return {"outcome": verdict, "latency": latency, "detail": detail}

    def cost_summary(self):
        base = super().cost_summary()
        base.update({"tiers": list(self.tiers),
                     "resolved_by_tier": dict(self._tier_counts),
                     "grounding": {"backend": self.backend, "model": self.model,
                                   "vision_model": self.vision_model}})
        return base


class GrounderExecutor:
    """A per-step grounding model behind the Grounder interface."""

    def __init__(self, grounder):
        self.name = grounder.name
        self.grounder = grounder
        self._inferences = 0

    def run_step(self, state, step):
        import cv2
        image = cv2.imread(state["image"])
        self._inferences += 1
        if step["kind"] == "action":
            point = self.grounder.ground(image, step["instruction"])
            return {"outcome": point, "latency": self.grounder.last_latency,
                    "detail": "grounded" if point else "no point"}
        verdict = self.grounder.judge(image, step["instruction"])
        return {"outcome": verdict, "latency": self.grounder.last_latency,
                "detail": "judged"}

    def cost_summary(self):
        return {"inferences": self._inferences}


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def _inside(point, bounds):
    return (point is not None and bounds is not None
            and bounds[0] <= point[0] <= bounds[2]
            and bounds[1] <= point[1] <= bounds[3])


def _score(step, outcome):
    if step["kind"] == "action":
        return {"hit": _inside(outcome, step["target_bounds"])}
    correct = outcome == step["expect"]
    false_pass = (step["expect"] == "FAILED" and outcome == "PASSED")
    return {"correct": correct, "false_pass": false_pass}


def run_benchmark(manifest, executors, limit_states=None, out_dir="benchmarks/results"):
    states = {s["id"]: s for s in manifest["states"]}
    step_list = manifest["steps"]
    if limit_states:
        keep = set(list(states)[:limit_states])
        step_list = [s for s in step_list if s["state"] in keep]

    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")

    all_results = {}
    for ex in executors:
        if hasattr(ex, "dom_dump_dir"):
            # keep the parsed DOMs next to the result file (one dir per executor)
            ex.dom_dump_dir = out / f"{stamp}-doms" / ex.name.replace("+", "_")
        rows, agg = [], defaultdict(list)
        log.info("Executor %s: %d steps over %d states",
                 ex.name, len(step_list), len({s['state'] for s in step_list}))
        for step in step_list:
            state = states[step["state"]]
            try:
                r = ex.run_step(state, step)
            except Exception as exc:  # a model failure is a scored miss, not a crash
                log.warning("%s failed on %s: %s", ex.name, step["id"], exc)
                r = {"outcome": None, "latency": 0.0, "detail": f"error: {exc}"}
            score = _score(step, r["outcome"])
            rows.append({"step": step["id"], "kind": step["kind"],
                         "outcome": (list(r["outcome"])
                                     if isinstance(r["outcome"], tuple) else r["outcome"]),
                         "latency": round(r["latency"], 4),
                         "detail": r["detail"], **score})
            for k, v in score.items():
                agg[k].append(v)
            agg[f"latency_{step['kind']}"].append(r["latency"])

        def rate(key):
            vals = agg.get(key, [])
            return round(sum(vals) / len(vals), 4) if vals else None

        summary = {
            "action_hit_rate": rate("hit"),
            "actions": len(agg.get("hit", [])),
            "verify_accuracy": rate("correct"),
            "verifies": len(agg.get("correct", [])),
            "false_pass_rate": rate("false_pass"),
            "median_step_latency_s": round(statistics.median(
                agg["latency_action"] + agg["latency_verify"]), 4)
            if (agg.get("latency_action") or agg.get("latency_verify")) else None,
            "cost": ex.cost_summary(),
        }
        all_results[ex.name] = {"summary": summary, "steps": rows}
        log.info("%s: %s", ex.name, summary)
        errors = sum(1 for r in rows if str(r["detail"]).startswith("error:"))
        if rows and errors == len(rows):
            # Every step raised: that is a broken environment, not a measured
            # zero. Say so loudly and exit non-zero so an unattended sweep marks
            # the column FAILED instead of filing a table of 0.0s.
            log.error("%s: ALL %d steps errored - first: %s",
                      ex.name, errors, rows[0]["detail"])
            all_results[ex.name]["summary"]["all_steps_errored"] = True
        elif errors:
            log.warning("%s: %d of %d steps errored", ex.name, errors, len(rows))

    payload = {
        "benchmark": manifest["benchmark"],
        "commit": commit,
        "generated_steps": len(step_list),
        "results": all_results,
    }
    (out / f"{stamp}.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = ["| executor | action-hit | verify acc | false-pass | median step (s) | cost |",
             "|---|---|---|---|---|---|"]
    for name, res in all_results.items():
        s = res["summary"]
        if s.get("all_steps_errored"):
            # Not a measurement: say so in the row itself, so a sweep summary
            # built from these files cannot show the column as 0.0.
            # One markdown cell: a traceback spans lines and transformers'
            # import errors carry '|', either of which would split the row.
            first = " ".join(str(res["steps"][0]["detail"]).split()) \
                .replace("|", "/")[:120]
            lines.append(f"| {name} | FAILED | FAILED | FAILED | - "
                         f"| all {len(res['steps'])} steps errored: {first} |")
            continue
        lines.append(f"| {name} | {s['action_hit_rate']} ({s['actions']}) "
                     f"| {s['verify_accuracy']} ({s['verifies']}) "
                     f"| {s['false_pass_rate']} | {s['median_step_latency_s']} "
                     f"| {s['cost']} |")
    table = "\n".join(lines)
    (out / f"{stamp}.md").write_text(table, encoding="utf-8")
    print(table)
    if any(r["summary"].get("all_steps_errored") for r in all_results.values()):
        raise SystemExit(1)
    return payload


def _require_descriptions(manifest):
    """A desc= column needs the 'description' field on every step."""
    missing = [s["id"] for s in manifest["steps"] if not s.get("description")]
    if missing:
        raise SystemExit(f"{len(missing)} steps have no 'description' (first: "
                         f"{missing[0]}) - the manifest predates the desc= column; "
                         f"regenerate it: python -m visual_dom.evaluation.lifecycle.generate")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run the full-lifecycle benchmark")
    parser.add_argument("--manifest", default="benchmarks/lifecycle-synthetic-v1/steps.json")
    parser.add_argument("--executors", default="vizdom-uied",
                        help="comma list: vizdom-uied, vizdom-omniparser, "
                             "vizdom-modular, vizdom-<detector>+desc, "
                             "elam-7b, ui-tars-1.5-7b, aria-ui")
    parser.add_argument("--limit-states", type=int, default=None)
    parser.add_argument("--no-quantize", action="store_true")
    parser.add_argument("--out-dir", default="benchmarks/results",
                        help="directory for the timestamped result json/md "
                             "(deploy/gpu sweep points each column at one run dir)")
    g = parser.add_argument_group("desc= columns (vizdom-<detector>+desc, ADR-022)")
    g.add_argument("--grounding-tiers", default=",".join(VizDomDescExecutor.DEFAULT_TIERS),
                   help="comma list from lexical,slm,vlm - the chain, in order; "
                        "pin one tier (e.g. vlm) for a per-tier column")
    g.add_argument("--grounding-backend", default="ollama", help="ollama | openai")
    g.add_argument("--grounding-model", default=VizDomDescExecutor.DEFAULT_MODEL,
                   help="text model for the slm tier")
    g.add_argument("--grounding-vision-model", default=VizDomDescExecutor.DEFAULT_VISION_MODEL,
                   help="vision model for the vlm (Set-of-Mark) tier")
    g.add_argument("--grounding-host",
                   default=os.environ.get("VIZDOM_OLLAMA_HOST", VizDomDescExecutor.DEFAULT_HOST))
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    executors = []
    for name in split_specs(args.executors):
        if name.startswith("vizdom-"):
            spec = name[len("vizdom-"):]
            if spec.endswith("+desc"):
                _require_descriptions(manifest)
                detector, overrides, suffix = parse_vizdom_spec(spec[:-len("+desc")])
                ex = VizDomDescExecutor(
                    detector=detector, overrides=overrides, suffix=suffix,
                    tiers=args.grounding_tiers.split(","),
                    backend=args.grounding_backend, model=args.grounding_model,
                    vision_model=args.grounding_vision_model,
                    host=args.grounding_host)
                ok, reason = ex.available()
                if not ok:
                    raise SystemExit(f"{ex.name} is not runnable here: {reason}")
                print(f"{ex.name}: {reason}")
                executors.append(ex)
            else:
                detector, overrides, suffix = parse_vizdom_spec(spec)
                executors.append(VizDomExecutor(detector=detector, overrides=overrides,
                                                suffix=suffix))
            continue
        from .grounders import GROUNDERS
        cls = GROUNDERS.get(name)
        if cls is None:
            raise SystemExit(f"unknown executor {name!r}; choose from "
                             f"vizdom-<detector> or {sorted(GROUNDERS)}")
        grounder = cls(quantize=not args.no_quantize)
        ok, reason = grounder.available()
        if not ok:
            raise SystemExit(f"{name} is not runnable here: {reason}")
        print(f"{name}: {reason}")
        executors.append(GrounderExecutor(grounder))

    run_benchmark(manifest, executors, limit_states=args.limit_states,
                  out_dir=args.out_dir)


if __name__ == "__main__":
    main()
