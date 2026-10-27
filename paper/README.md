# Paper draft

`vizdom_paper.tex` — IEEE conference format (IEEEtran). Build:

```powershell
powershell -ExecutionPolicy Bypass -File paper/build.ps1     # -> paper/vizdom_paper.pdf
```

The build needs MiKTeX with auto-install on (the script sets it); `ieeetran`
was installed on 2026-10-28. For ISSTA, switch the class to `acmart`
(`\documentclass[sigconf,review]{acmart}`), keep the body.

## Claim and venue

The claim is the oracle one, not the parser one: *per-step vision grounders
cannot serve as GUI test oracles; a resolved DOM can, and keeps the property
when a model is put in the loop in the right form*. The lifecycle benchmark
with negative oracle steps is the methodological contribution; VizDOM is the
vehicle.

Venues (testing, not vision): ICST or ISSTA main track once the real-world
rows exist; AST or A-TEST workshop otherwise; ICSE SEIP for the industrial
angle. An arXiv preprint first establishes the date. Check the employer's
publication-clearance process early; it can take weeks.

## Where each section comes from

| Paper section | Source |
|---|---|
| I Introduction | `report/vizdom_report_en.tex` sec. 1; deck slide 12c |
| II Background | report sec. 2 (landscape, capability matrix) |
| III Lifecycle benchmark | `benchmarks/README.md` sec. 1–5; report `sec:lifecycle` |
| IV VizDOM | report sec. 3–4; `sec:desc`; ADR-022, ADR-024, ADR-027 |
| V Setup | `benchmarks/report_gpu_20261026_run3.html` sec. 2 (test configuration) |
| VI Results | `benchmarks/README.md` sec. 6; run-3 report sec. 3–9 |
| VII Threats | run-3 report sec. 10; report "Discussion and Limitations" |

Every number traces to a result JSON under `benchmarks/results/gpu-<stamp>/`
(gitignored; keep the tarballs) by the run id and commit in Table II.

## Before submission (the `\todo{}` marks in the source)

1. **Real-application states** in the same schema, with their rows in
   Table III and Section VII. This is the one a reviewer can reject on.
2. **Harder negatives**: plausible-but-absent labels (defect injection).
3. **Human-written or paraphrased descriptions** for the `desc=` rows.
4. **Repeat the grounder columns** (two more runs) for error bars.
5. **Rerun the vision-chain column** (run 5 lost 68 of 116 calls to an
   Ollama outage); optionally 7B tiers.
6. Author order, affiliations, second author's email; publication clearance.
7. Artifact: repository URL, Zenodo DOI for the manifest and tarballs.
8. Verify the bibliography entries marked `verify` against the published
   versions (author lists, venues, pages).
9. Figures: Fig. 1 reuses the report's PlantUML overview, whose text is small
   in a column; redraw it (and optionally a three-box tier-chain figure) for
   print. A bar chart of Table IV (verify outcomes) would carry the headline
   well; the run-3 HTML report has the same chart in SVG.
