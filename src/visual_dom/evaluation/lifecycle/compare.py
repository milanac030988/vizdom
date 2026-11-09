"""
Compare lifecycle result runs step by step.

A run is a directory of runner result files (``<stamp>.json``), or the
``gpu-<stamp>.tar.gz`` a rental produces (unpacked next to itself); a run
dir with a ``realworld/``, ``nearmiss/`` or ``heldout/`` subdirectory holds
one more set per subdirectory and all are read.
For every set the tool prints, in Markdown:

* one row per executor: action-hit, verify accuracy, false passes as a
  count over the negatives (split by negative kind), errors, tiers used;
* each executor against the same executor in every reference run: steps
  with an identical outcome, gains and losses (with the step ids);
* pairs inside the new run that differ only in the model
  (``[vlm=qwen2.5vl:7b]``) or in the verify scoring (``[verify=chain]``);
* every false pass, with the resolver's own explanation.

Executors are matched by name with the verify mode made explicit: runs
before ADR-022 1.9 scored every desc= chain with ``verify=chain`` and did
not say so, so their ``...+desc[lexical+slm]`` row pairs with a later
``...+desc[lexical+slm][verify=chain]`` row, not with the new default.

    python -m visual_dom.evaluation.lifecycle.compare \\
        benchmarks/results/gpu-<stamp>.tar.gz \\
        --ref benchmarks/results/gpu-20261028_120820 \\
        --ref benchmarks/results/realworld_local > run8.md
"""

import argparse
import json
import math
import re
import shutil
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

_SUFFIX = re.compile(r"\[(verify|vlm|slm)=([^\]]+)\]")
_UNSAFE_FS = re.compile(r'[<>:"\\|?*]')
#: subdirectories of a run dir that hold one more benchmark set each
#: (realworld since run 8; nearmiss and heldout since run 9)
SET_DIRS = ("realworld", "nearmiss", "heldout")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def unpack(path):
    """A run dir as given, or the run dir a tarball unpacks to (once)."""
    path = Path(path)
    if path.is_dir():
        return path
    if not path.name.endswith(".tar.gz"):
        raise ValueError(f"{path}: neither a directory nor a .tar.gz")
    target = path.with_name(path.name[:-len(".tar.gz")])
    if not target.is_dir():
        with tarfile.open(path) as tar:
            members = tar.getmembers()
            # the sweep tars "<run dir name>/..." - refuse anything that
            # would land outside it
            if any(m.name.startswith(("/", "..")) or ".." in Path(m.name).parts
                   for m in members):
                raise ValueError(f"{path}: unsafe member paths")
            # a Linux box may name a DOM folder "...[vlm=qwen2.5vl:7b]",
            # which Windows cannot create (run 8)
            for m in members:
                m.name = "/".join(_UNSAFE_FS.sub("_", p) for p in m.name.split("/"))
            # unpack beside the target and rename, so a failed unpack never
            # leaves a half run dir that the next call would take as done
            tmp = path.with_name(target.name + ".unpacking")
            if tmp.exists():
                shutil.rmtree(tmp)
            tar.extractall(tmp, members=members)
            (tmp / target.name).rename(target)
            shutil.rmtree(tmp)
    return target


def load_sets(run_dir):
    """{benchmark name: {executor name: result}} of one run dir; within a
    set the latest result file wins (an ONLY= rerun replaces the old row)."""
    run_dir = Path(run_dir)
    sets = defaultdict(dict)
    # the run dir and one directory per further set. Named, not globbed:
    # ablation/ holds runner files too, and its control columns carry the
    # main columns' names.
    for d in [run_dir] + [run_dir / s for s in SET_DIRS]:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("[0-9]*_[0-9]*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            for name, res in data.get("results", {}).items():
                res = dict(res, _file=f.name, _commit=data.get("commit", "?"))
                sets[data["benchmark"]][name] = res
    return dict(sets)


def load_manifest(benchmark, root="benchmarks"):
    path = Path(root) / benchmark / "steps.json"
    if not path.exists():
        return None
    m = json.loads(path.read_text(encoding="utf-8"))
    return {s["id"]: s for s in m["steps"]}


# --------------------------------------------------------------------------- #
# matching and scoring
# --------------------------------------------------------------------------- #

def verify_mode(name, result):
    """The verify scoring a desc= row used: recorded since ADR-022 1.9,
    'chain' for every desc= row before it, None for non-desc rows."""
    if "+desc[" not in name:
        return None
    return (result.get("summary", {}).get("cost", {}) or {}).get("verify", "chain")


def match_key(name, result):
    """Executor identity across runs: the name without its verify suffix,
    plus the verify mode that was actually used. Only for desc= rows: a
    grounder's ``[verify=yesno]`` row asks the model another question, so it
    is another executor and never pairs with the plain row of an older run
    (inside one run the two show up as twins)."""
    if "+desc[" not in name:
        return name, None
    base = re.sub(r"\[verify=[^\]]+\]", "", name)
    return base, verify_mode(name, result)


def step_ok(row):
    return bool(row.get("hit") if row["kind"] == "action" else row.get("correct"))


def same_outcome(a, b):
    return a.get("outcome") == b.get("outcome") and step_ok(a) == step_ok(b)


def wilson(k, n, z=1.96):
    """95 % Wilson score interval of k successes in n; (None, None) for n=0.
    Unlike the normal approximation it stays inside [0, 1] and gives a
    usable upper bound for 0 of n (0 false passes of 92 -> at most 4.0 %)."""
    if not n:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar(a_rows, b_rows):
    """Exact two-sided McNemar test of two executors on the steps both
    scored: (only a right, only b right, p). Steps both got right or both
    got wrong carry no information about which is better."""
    b = {r["step"]: step_ok(r) for r in b_rows}
    only_a = only_b = 0
    for r in a_rows:
        if r["step"] not in b:
            continue
        ok_a, ok_b = step_ok(r), b[r["step"]]
        only_a += ok_a and not ok_b
        only_b += ok_b and not ok_a
    n = only_a + only_b
    if n == 0:
        return only_a, only_b, 1.0
    tail = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n
    return only_a, only_b, min(1.0, 2 * tail)


def summarize(result, manifest):
    rows = result["steps"]
    acts = [r for r in rows if r["kind"] == "action"]
    vers = [r for r in rows if r["kind"] != "action"]
    negs = [r for r in vers if manifest and manifest.get(r["step"], {}).get("expect") == "FAILED"]
    poss = [r for r in vers if manifest and manifest.get(r["step"], {}).get("expect") != "FAILED"]
    # the two halves of verify accuracy: an executor that answers "present"
    # to everything scores 100 % on the first and 0 % on the second, and its
    # balanced accuracy is a coin flip's
    present_pass = sum(step_ok(r) for r in poss) / len(poss) if poss else None
    absent_fail = sum(step_ok(r) for r in negs) / len(negs) if negs else None
    fp = Counter()
    for r in vers:
        if r.get("false_pass"):
            kind = (manifest or {}).get(r["step"], {}).get("negative_kind", "nonsense")
            fp[kind] += 1
    neg_kinds = Counter((manifest or {}).get(r["step"], {}).get("negative_kind", "nonsense")
                        for r in negs)
    errors = sum(1 for r in rows if str(r.get("detail", "")).startswith("error:"))
    hits = sum(step_ok(r) for r in acts)
    return {
        "action_hit": hits / len(acts) if acts else None,
        "action_ci": wilson(hits, len(acts)),
        "actions": len(acts),
        "present_pass": present_pass,
        "absent_fail": absent_fail,
        "balanced": (present_pass + absent_fail) / 2
                    if present_pass is not None and absent_fail is not None else None,
        # a negative can also end in an error, which is neither correct nor
        # a false pass - the interval is of the false passes themselves
        "fp_ci": wilson(sum(fp.values()), len(negs)),
        "verify_acc": sum(step_ok(r) for r in vers) / len(vers) if vers else None,
        "verifies": len(vers),
        "false_passes": sum(fp.values()),
        "negatives": len(negs) if manifest else None,
        "fp_by_kind": dict(fp),
        "neg_kinds": dict(neg_kinds),
        "errors": errors,
        "tiers": (result.get("summary", {}).get("cost", {}) or {}).get("resolved_by_tier"),
    }


def diff(new, ref):
    """(identical, gains, losses) over the steps both results share."""
    a = {r["step"]: r for r in ref["steps"]}
    identical, gains, losses = 0, [], []
    for r in new["steps"]:
        o = a.get(r["step"])
        if o is None:
            continue
        if same_outcome(r, o):
            identical += 1
        elif step_ok(r) and not step_ok(o):
            gains.append(r["step"])
        elif step_ok(o) and not step_ok(r):
            losses.append(r["step"])
    return identical, gains, losses


def model_twins(names):
    """Pairs of executors in one run whose names differ only in a model or
    verify suffix: (base, variant)."""
    out = []
    for n in names:
        if not _SUFFIX.search(n):
            continue
        base = n
        for m in reversed(list(_SUFFIX.finditer(n))):
            stripped = n[:m.start()] + n[m.end():]
            if stripped in names:
                base = stripped
                break
        if base != n:
            out.append((base, n))
    return out


def by_app(result):
    """{app: (hits, actions)} - the state id is <app>__<state>."""
    acc = defaultdict(lambda: [0, 0])
    for r in result["steps"]:
        if r["kind"] == "action":
            app = r["step"].split("__")[0]
            acc[app][0] += step_ok(r)
            acc[app][1] += 1
    return {k: tuple(v) for k, v in sorted(acc.items())}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def _pct(x):
    return "-" if x is None else f"{x:.3f}"


def _p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _ids(ids, n=8):
    return ", ".join(ids[:n]) + (f" (+{len(ids) - n})" if len(ids) > n else "")


def report(new_dir, ref_dirs=(), manifest_root="benchmarks"):
    new_dir = unpack(new_dir)
    new = load_sets(new_dir)
    refs = [(Path(unpack(d)).name, load_sets(unpack(d))) for d in ref_dirs]
    out = [f"# {new_dir.name}", ""]
    gpu = new_dir / "gpu.txt"
    if gpu.exists():
        out += ["```", gpu.read_text(encoding="utf-8").strip(), "```", ""]
    for bench in sorted(new):
        execs = new[bench]
        manifest = load_manifest(bench, manifest_root)
        out += [f"## {bench}", ""]
        if manifest is None:
            out += [f"(no manifest at {manifest_root}/{bench}/steps.json - "
                    "false passes are not split by kind)", ""]
        out += ["| executor | action-hit | verify acc | false passes | errors | tiers |",
                "|---|---|---|---|---|---|"]
        sums = {n: summarize(r, manifest) for n, r in execs.items()}
        for n, s in sums.items():
            fp = f"{s['false_passes']}"
            if s["negatives"] is not None:
                fp += f" / {s['negatives']}"
                if s["fp_by_kind"]:
                    fp += " (" + ", ".join(f"{k} {v}" for k, v in sorted(s["fp_by_kind"].items())) + ")"
            tiers = ", ".join(f"{k} {v}" for k, v in (s["tiers"] or {}).items())
            out.append(f"| {n} | {_pct(s['action_hit'])} ({s['actions']}) | "
                       f"{_pct(s['verify_acc'])} ({s['verifies']}) | {fp} | "
                       f"{s['errors']} | {tiers} |")
        out.append("")

        # the verify split and the 95 % intervals (needs the manifest)
        if manifest is not None:
            out += ["### verify split and 95 % intervals", "",
                    "Present → pass and absent → fail are the two halves of verify "
                    "accuracy; balanced accuracy is their mean (0.5 for an executor "
                    "that answers the same on every step). Intervals are Wilson.", "",
                    "| executor | action-hit [95 % CI] | present → pass | absent → fail | "
                    "balanced | false-pass rate [95 % CI] |",
                    "|---|---|---|---|---|---|"]
            for n, s in sums.items():
                lo, hi = s["action_ci"]
                flo, fhi = s["fp_ci"]
                rate = s["false_passes"] / s["negatives"] if s["negatives"] else None
                out.append(f"| {n} | {_pct(s['action_hit'])} [{_pct(lo)}, {_pct(hi)}] | "
                           f"{_pct(s['present_pass'])} | {_pct(s['absent_fail'])} | "
                           f"{_pct(s['balanced'])} | {_pct(rate)} [{_pct(flo)}, {_pct(fhi)}] |")
            out.append("")

        # paired tests: every VizDOM row against every grounder row
        grounders = [n for n in execs if not n.startswith("vizdom")]
        ours = [n for n in execs if n.startswith("vizdom")]
        if grounders and ours:
            # verify steps split as in the table above: pooled, an executor
            # that says "present" to everything wins on the many positives
            def expect(r):
                return (manifest or {}).get(r["step"], {}).get("expect")
            kinds = [("clicks", lambda r: r["kind"] == "action")]
            if manifest is not None:
                kinds += [("present", lambda r: r["kind"] != "action" and expect(r) != "FAILED"),
                          ("absent", lambda r: r["kind"] != "action" and expect(r) == "FAILED")]
            else:
                kinds += [("verifies", lambda r: r["kind"] != "action")]
            out += ["### paired against the grounders (exact McNemar)", "",
                    "Counts are steps only the VizDOM row / only the grounder got right; "
                    "p < 0.05 means the difference is unlikely to be chance.", "",
                    "| VizDOM row | grounder | "
                    + " | ".join(f"{k}: ours / theirs | p" for k, _ in kinds) + " |",
                    "|---|---|" + "---|---|" * len(kinds)]
            for n in ours:
                for g in grounders:
                    cells = []
                    for _, kind_ok in kinds:
                        a = [r for r in execs[n]["steps"] if kind_ok(r)]
                        b = [r for r in execs[g]["steps"] if kind_ok(r)]
                        oa, ob, p = mcnemar(a, b)
                        cells += [f"{oa} / {ob}", _p(p)]
                    out.append(f"| {n} | {g} | " + " | ".join(cells) + " |")
            out.append("")

        # against the reference runs
        for ref_name, ref_sets in refs:
            ref = ref_sets.get(bench)
            if not ref:
                continue
            ref_keys = {match_key(n, r): n for n, r in ref.items()}
            lines = []
            for n, r in execs.items():
                rn = ref_keys.get(match_key(n, r))
                if rn is None:
                    continue
                same, gains, losses = diff(r, ref[rn])
                # over the steps both runs scored (a manifest may have grown)
                total = len({s["step"] for s in r["steps"]} & {s["step"] for s in ref[rn]["steps"]})
                lines.append(f"| {n} | {rn} | {same}/{total} | +{len(gains)} | -{len(losses)} | "
                             f"{_ids(gains)} | {_ids(losses)} |")
            if lines:
                out += [f"### against {ref_name}", "",
                        "| executor | reference row | identical | gains | losses | gained steps | lost steps |",
                        "|---|---|---|---|---|---|---|", *lines, ""]

        # model and verify twins inside this run
        twins = model_twins(set(execs))
        if twins:
            out += ["### twins in this run (same chain, other model or verify scoring)", "",
                    "| base | variant | identical | variant better | variant worse | p (McNemar) |",
                    "|---|---|---|---|---|---|"]
            for base, var in twins:
                same, gains, losses = diff(execs[var], execs[base])
                p = mcnemar(execs[var]["steps"], execs[base]["steps"])[2]
                out.append(f"| {base} | {var} | {same}/{len(execs[var]['steps'])} | "
                           f"+{len(gains)} | -{len(losses)} | {_p(p)} |")
            out.append("")

        # per application (real-world set)
        if any("__" in r["step"] for res in execs.values() for r in res["steps"][:1]):
            apps = sorted({a for res in execs.values() for a in by_app(res)})
            if apps:        # none on a set, or in a rerun, of verify steps only
                out += ["### action-hit per application", "",
                        "| executor | " + " | ".join(apps) + " |",
                        "|---|" + "---|" * len(apps)]
                for n, res in execs.items():
                    per = by_app(res)
                    out.append(f"| {n} | " + " | ".join(
                        f"{per[a][0]}/{per[a][1]}" if a in per else "-" for a in apps) + " |")
                out.append("")

        # every false pass
        fps = [(n, r) for n, res in execs.items() for r in res["steps"] if r.get("false_pass")]
        if fps:
            out += ["### false passes", "", "| executor | step | description | kind | detail |",
                    "|---|---|---|---|---|"]
            for n, r in fps:
                m = (manifest or {}).get(r["step"], {})
                detail = str(r.get("detail", "")).replace("|", "/")[:160]
                out.append(f"| {n} | {r['step']} | {m.get('description', '')} | "
                           f"{m.get('negative_kind', 'nonsense')} | {detail} |")
            out.append("")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description="Compare lifecycle result runs step by step")
    p.add_argument("run", help="run dir or gpu-<stamp>.tar.gz")
    p.add_argument("--ref", action="append", default=[],
                   help="reference run dir or tarball (repeatable)")
    p.add_argument("--manifests", default="benchmarks",
                   help="root holding <benchmark>/steps.json")
    p.add_argument("--out", help="write the Markdown here instead of stdout")
    a = p.parse_args()
    text = report(a.run, a.ref, a.manifests)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(a.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
