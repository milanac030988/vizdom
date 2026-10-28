"""
Ablation of VizDOM's own pipeline stages on the lifecycle benchmark.

The lifecycle columns compare detectors and grounders. This driver holds the
detector fixed (modular by default) and turns VizDOM's own stages off one at
a time through the session config - the column spec syntax of the runner,
``vizdom-modular[roles=off]`` - then scores every column on both levels:

* lifecycle: action-hit / verify accuracy / false-pass over the same 514
  steps (what the stage is worth to a test suite);
* per-stage: detection F1 / recall / mean IoU / OCR character accuracy of the
  dumped DOMs against the element ground truth (what the stage does to the
  DOM), through `visual_dom.evaluation` on the ``<stamp>-doms/`` folder the
  runner keeps.

One column per process is the safe way on a laptop (the parse holds the OCR
and detector models in memory):

    python -m visual_dom.evaluation.lifecycle.ablation --columns "modular[roles=off]"
    python -m visual_dom.evaluation.lifecycle.ablation --report      # merge all ablation-*.json

Each run writes ``ablation-<stamp>.json`` next to the runner's result files;
``--report`` merges every such file in the out dir into one table, control
first, with the deltas against it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from visual_dom.evaluation.lifecycle.runner import (
    VizDomDescExecutor, VizDomExecutor, parse_vizdom_spec, run_benchmark, split_specs,
)

DEFAULT_COLUMNS = [
    "modular",
    "modular[roles=off]",
    "modular[labels=off]",
    "modular[symbols=off]",
    "modular[merge=off]",
    "modular[ocr=plain]",
    "modular[ocr=none]",
    "modular[refiner=on]",
]

STAGE_METRICS = ("mean_f1", "mean_precision", "mean_recall", "mean_iou", "mean_char_accuracy")


def stage_metrics(dom_dir: Path, manifest) -> dict:
    """Per-stage metrics of one column's dumped DOMs against the manifest's GT."""
    from visual_dom.evaluation.evaluator import EvaluationConfig, VisualDOMEvaluator

    preds, gts = [], []
    for state in manifest["states"]:
        pred = dom_dir / f"{state['id']}.json"
        gt = Path(state["gt"])
        if pred.exists() and gt.exists():
            preds.append(json.loads(pred.read_text(encoding="utf-8")))
            gts.append(json.loads(gt.read_text(encoding="utf-8")))
    if not preds:
        return {"samples": 0}
    ev = VisualDOMEvaluator(EvaluationConfig(evaluate_hierarchy=False, evaluate_locators=False))
    batch = ev.evaluate_batch(preds, gts)
    agg = batch.to_dict().get("aggregate_metrics", {})
    out = {"samples": len(preds)}
    out.update({k: agg.get(k) for k in STAGE_METRICS})
    # Per GT type, pooled over samples: recall = the GT element was matched
    # by some prediction (found at all); type accuracy = matched AND the
    # prediction carries the same visual_type (the role a test needs).
    found, typed, support = {}, {}, {}
    for r, pred, gt in zip(batch.results, preds, gts):
        p_type = {e.get("id"): (e.get("visual_type") or e.get("type"))
                  for e in ev._extract_elements(pred)}
        g_type = {e.get("id"): (e.get("visual_type") or e.get("type"))
                  for e in ev._extract_elements(gt)}
        matched = {gt_id: pred_id for pred_id, gt_id, _iou in r.element_metrics.matched_pairs}
        for gid, t in g_type.items():
            support[t] = support.get(t, 0) + 1
            if gid in matched:
                found[t] = found.get(t, 0) + 1
                if p_type.get(matched[gid]) == t:
                    typed[t] = typed.get(t, 0) + 1
    out["recall_by_type"] = {t: round(found.get(t, 0) / n, 4) for t, n in support.items()}
    out["type_accuracy"] = {t: round(typed.get(t, 0) / n, 4) for t, n in support.items()}
    out["support"] = support
    return out


def run_columns(columns, manifest, out_dir, limit_states=None):
    """
    Run each column and score it; returns {spec: row}. The result file is
    rewritten after EVERY column, and a column that cannot run (no Ollama
    for refiner=on, every step erroring) is recorded as {"error": ...} and
    the next one starts - a batch of eight must not lose seven finished
    columns to the eighth (review, 2026-10-28).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = out / f"ablation-{stamp}.json"
    results = {}

    def save():
        path.write_text(json.dumps({"benchmark": manifest.get("benchmark"), "results": results},
                                   indent=1, ensure_ascii=False), encoding="utf-8")

    for spec in columns:
        # "modular[roles=off]+desc": the same stage switch under the desc=
        # resolver (default chain), which is where roles and labels matter -
        # the text= steps never read them.
        desc = spec.endswith("+desc")
        try:
            detector, overrides, suffix = parse_vizdom_spec(spec[:-5] if desc else spec)
            if desc:
                ex = VizDomDescExecutor(detector=detector, overrides=overrides, suffix=suffix)
                ok, reason = ex.available()
                if not ok:
                    raise SystemExit(f"{ex.name} is not runnable here: {reason}")
            else:
                ex = VizDomExecutor(detector=detector, overrides=overrides, suffix=suffix)
            payload = run_benchmark(manifest, [ex], limit_states=limit_states, out_dir=out)
        except (SystemExit, ValueError) as exc:
            code = getattr(exc, "code", None)
            if isinstance(code, int):      # run_benchmark: every step of the column errored
                reason = f"exit {code}: all steps errored - see the column's own result file"
            else:
                reason = " ".join(str(exc).split())[:300] or "failed"
            print(f"!! {spec}: {reason}", file=sys.stderr)
            results[spec] = {"column": f"vizdom-{spec}", "error": reason}
            save()
            continue
        lifecycle = payload["results"][ex.name]["summary"]
        stage = stage_metrics(Path(ex.dom_dump_dir), manifest) if ex.dom_dump_dir else {}
        results[spec] = {"column": ex.name, "overrides": overrides,
                         "lifecycle": lifecycle, "stage": stage,
                         "commit": payload.get("commit")}
        save()
    print(f"-> {path}")
    return results


def _fmt(v, nd=3):
    return "-" if v is None else f"{v:.{nd}f}"


def _delta(v, ref):
    if v is None or ref is None:
        return ""
    d = v - ref
    return f" ({d:+.3f})" if abs(d) >= 0.0005 else " (=)"


def report(out_dir, control="modular"):
    """Merge every ablation-*.json in out_dir into one markdown table."""
    out = Path(out_dir)
    merged = {}
    for f in sorted(out.glob("ablation-*.json")):
        merged.update(json.loads(f.read_text(encoding="utf-8")).get("results", {}))
    if not merged:
        raise SystemExit(f"no ablation-*.json under {out}")
    order = [control] + [k for k in merged if k != control] if control in merged else list(merged)
    ref = merged.get(control, {})
    rl, rs = ref.get("lifecycle", {}), ref.get("stage", {})
    lines = ["| column | action-hit | verify acc | false-pass | parse s/state "
             "| F1 | recall | mIoU | char acc | found: button / input / checkbox "
             "| typed: button / input / checkbox |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in order:
        r = merged[k]
        if r.get("error"):
            # not a measurement: say so in the row, never a table of dashes
            lines.append(f"| `{r['column']}` | FAILED | FAILED | FAILED | - | - | - | - | - "
                         f"| {r['error'].replace('|', '/')[:120]} | |")
            continue
        lc, st = r["lifecycle"], r.get("stage", {})
        rt, ta = st.get("recall_by_type", {}), st.get("type_accuracy", {})
        lines.append(
            f"| `{r['column']}` "
            f"| {_fmt(lc.get('action_hit_rate'))}{_delta(lc.get('action_hit_rate'), rl.get('action_hit_rate'))} "
            f"| {_fmt(lc.get('verify_accuracy'))}{_delta(lc.get('verify_accuracy'), rl.get('verify_accuracy'))} "
            f"| {_fmt(lc.get('false_pass_rate'))} "
            f"| {_fmt((lc.get('cost') or {}).get('parse_seconds_mean'), 2)} "
            f"| {_fmt(st.get('mean_f1'))}{_delta(st.get('mean_f1'), rs.get('mean_f1'))} "
            f"| {_fmt(st.get('mean_recall'))} | {_fmt(st.get('mean_iou'))} "
            f"| {_fmt(st.get('mean_char_accuracy'))} "
            f"| {' / '.join(_fmt(rt.get(t), 2) for t in ('button', 'input_field', 'checkbox'))} "
            f"| {' / '.join(_fmt(ta.get(t), 2) for t in ('button', 'input_field', 'checkbox'))} |")
    table = "\n".join(lines)
    (out / "ablation-report.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    return table


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--manifest", default="benchmarks/lifecycle-synthetic-v1/steps.json")
    p.add_argument("--columns", default=",".join(DEFAULT_COLUMNS),
                   help="comma list of runner column specs without the vizdom- prefix")
    p.add_argument("--out-dir", default="benchmarks/results")
    p.add_argument("--limit-states", type=int, default=None)
    p.add_argument("--report", action="store_true",
                   help="only merge the ablation-*.json files in --out-dir into a table")
    p.add_argument("--control", default="modular")
    args = p.parse_args(argv)
    if args.report:
        report(args.out_dir, args.control)
        return 0
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    columns = split_specs(args.columns)          # commas inside [...] are switches
    results = run_columns(columns, manifest, args.out_dir, limit_states=args.limit_states)
    failed = [k for k, r in results.items() if r.get("error")]
    if failed:
        print(f"{len(failed)} of {len(results)} columns did not run: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
