"""
Run the lifecycle benchmark: every executor over the same steps, one table out.

Executors
---------
- ``vizdom:<detector>``  the real VizDOM stack: pipeline once per STATE
  (parse-once), then each step is a locator resolution in the cached DOM.
  Clicks score "action-hit" (element centre inside GT bounds); verifications
  answer from the exactly-one contract.
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
table, both stamped with dataset id, git commit, and executor config.
"""

import json
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Executors
# --------------------------------------------------------------------------- #

class VizDomExecutor:
    """The production stack: parse each state once, resolve steps from the DOM."""

    def __init__(self, detector: str, ocr: str = "easyocr"):
        self.name = f"vizdom-{detector}"
        self.detector = detector
        self.ocr = ocr
        self._session = None
        self._dom_cache = {}
        self._parse_seconds = {}

    def _connect(self):
        if self._session is None:
            from visual_dom import connect
            self._session = connect({
                "detector": {"backend": self.detector},
                "ocr": {"engine": self.ocr},
            })
        return self._session

    def _dom_for(self, state):
        sid = state["id"]
        if sid not in self._dom_cache:
            t0 = time.perf_counter()
            dom = self._connect().analyze(state["image"])
            self._parse_seconds[sid] = time.perf_counter() - t0
            self._dom_cache[sid] = dom
        return self._dom_cache[sid]

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
        return {"parses": len(self._parse_seconds),
                "parse_seconds_total": round(sum(self._parse_seconds.values()), 2)}


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

    all_results = {}
    for ex in executors:
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

    payload = {
        "benchmark": manifest["benchmark"],
        "commit": commit,
        "generated_steps": len(step_list),
        "results": all_results,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    (out / f"{stamp}.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = ["| executor | action-hit | verify acc | false-pass | median step (s) | cost |",
             "|---|---|---|---|---|---|"]
    for name, res in all_results.items():
        s = res["summary"]
        lines.append(f"| {name} | {s['action_hit_rate']} ({s['actions']}) "
                     f"| {s['verify_accuracy']} ({s['verifies']}) "
                     f"| {s['false_pass_rate']} | {s['median_step_latency_s']} "
                     f"| {s['cost']} |")
    table = "\n".join(lines)
    (out / f"{stamp}.md").write_text(table, encoding="utf-8")
    print(table)
    return payload


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run the full-lifecycle benchmark")
    parser.add_argument("--manifest", default="benchmarks/lifecycle-synthetic-v1/steps.json")
    parser.add_argument("--executors", default="vizdom-uied",
                        help="comma list: vizdom-uied, vizdom-omniparser, "
                             "elam-7b, ui-tars-1.5-7b, aria-ui")
    parser.add_argument("--limit-states", type=int, default=None)
    parser.add_argument("--no-quantize", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    executors = []
    for name in [n.strip() for n in args.executors.split(",") if n.strip()]:
        if name.startswith("vizdom-"):
            executors.append(VizDomExecutor(detector=name.split("-", 1)[1]))
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

    run_benchmark(manifest, executors, limit_states=args.limit_states)


if __name__ == "__main__":
    main()
