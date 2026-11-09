# Rented-GPU benchmark runbook

Purpose: run the hardware-gated benchmarks — the **grounder columns** (ELAM-7B,
UI-TARS-1.5-7B, Aria-UI) for the lifecycle comparison, the **`desc=` columns**
(VizDOM's own language tier, ADR-022, behind Ollama), and the **ADR-027
combos** — on a rented GPU box, spending as little paid time as possible.
Everything is scripted; the human steps are clone, four commands, one download.

Status: four paid runs so far (2026-10-25 and 2026-10-26 on RTX 4090,
2026-10-26 on RTX 6000 Ada 48 GB, and the Aria-UI column alone on an RTX
PRO 6000 Blackwell 96 GB the same night, all Vast.ai); the last two ran the
kit as committed (`82f0b45`, `411873c`) end to end without intervention.
The offload mode below has not been exercised yet (the 96 GB card is above
the gate, so the whole model sat on the GPU). Everything that went wrong on
the first day is now caught by `setup.sh` or `preflight.sh` — see "Version
pins" below before changing any dependency.

## Renting: what to pick

| Card | VRAM | Runs | Note |
|---|---|---|---|
| RTX 4090 / A5000 / L4 | 24 GB | VizDOM columns, ELAM-7B, UI-TARS-1.5 (bf16), parity | **recommended** — best price/coverage |
| A100 80 GB / H100 | 80 GB | the above **plus Aria-UI** (bf16) | only if the Aria-UI column is wanted |
| A6000 / L40S | 48 GB | same as 24 GB | **not enough for Aria-UI** — see below |
| 16 GB cards | 16 GB | 7B columns in 4-bit only | acceptable fallback |

Aria-UI (25 B MoE) runs **bf16 only**, the recipe its model card documents:
~50 GB of weights. bitsandbytes 4-bit does not help — it skips the expert
weights, so loading OOMs at shard 5/12 on 24 GB (measured 2026-10-26; the
allocation rate extrapolates to ~53 GB for the full load, more than a
48 GB card holds). The gate is 70 GB in `AriaUiGrounder.MIN_VRAM_GB`,
prefetch and the sweep (an 80 GB card reports ~85): below it `available()`
says why, prefetch skips the 50 GB download, and the sweep skips the column.

- Image: any **PyTorch / CUDA 12.x** template (CUDA driver preinstalled).
  Launch mode **SSH**, not Jupyter.
- **Disk: move the slider to 150–200 GB before renting.** It cannot be changed
  afterwards, and the default (16 GB on Vast) dies half-way through prefetch.
  `setup.sh` refuses to start below 120 GB free.
- Vast specifics: Verified host, On-demand (not Interruptible), reliability
  > 99 %, download ≥ 500 Mbps, and look at the **Internet $/TB** line on the
  price card — the run pulls ~80 GB, so 33 $/TB adds ~2.7 $.
- Register your SSH public key in the account *before* launching. The port to
  use is the one mapped to `22/tcp` in the instance's port list.

## Cost picture

Downloads (~85 GB incl. the two Ollama models) dominate wall time on the box
— typically 10–25 min on a datacenter pipe. Setup ~6 min (two venvs). The
sweep itself: ~1 min per VizDOM column, ~5–15 min per `desc=` column (one
Ollama call per step for the model tiers), ~15 min per 7B grounder column in
bf16, Aria-UI bf16 longer (3.9 B active parameters, but 50 GB to load).
Budget **2–3 hours total**; at typical 24 GB rates that is 3–5 $ including
bandwidth, an 80 GB card roughly double.

## The four commands

```bash
tmux new -s bench                 # survive a dropped SSH session (Ctrl-B D detaches, `tmux attach -t bench` returns)
git clone https://github.com/milanac030988/vizdom.git && cd vizdom
bash deploy/gpu/setup.sh          # ~6 min: disk check, uv, two venvs, CUDA torch, pinned deps
bash deploy/gpu/prefetch.sh       # ~10-25 min: ALL model downloads in parallel + OmniParser patch
bash deploy/gpu/preflight.sh      # ~2 min: each model grounds ONE image, in the env the sweep uses
bash deploy/gpu/run_benchmarks.sh # the unattended sweep (prints a summary table at the end)
```

**Do not skip preflight.** It loads every model from the env the sweep will
use it in, grounds one instruction, checks the point is inside the image, and
for ELAM also checks that a verdict comes back; it also runs one VizDOM pass
with the omniparser *and* the modular backend, and asks each `desc=` model
tier (SLM over DOM, VLM Set-of-Mark) through Ollama to resolve one
description. Every failure class seen so far (missing package, wrong
transformers, wrong prompt template, wrong coordinate scale, OmniParser or
the modular stage 1 silently degrading to UIED) fails there in minute two,
not two hours into the sweep as a column of zeros.

Then from your own machine (or the MobaXterm SFTP panel):

```bash
scp -P <port> root@<box>:~/vizdom/benchmarks/results/gpu-*.tar.gz benchmarks/results/
tar tzf benchmarks/results/gpu-*.tar.gz | grep -E "summary.md|parity.txt"
# verify the tarball opens and summary.md is inside — THEN destroy the rental
```

### Re-running one or two columns

After fixing something on the box, re-run only the affected columns into the
same run dir; the tarball and `summary.md` are rebuilt:

```bash
ONLY="elam-7b aria-ui" OUT_DIR=benchmarks/results/gpu-<stamp> bash deploy/gpu/run_benchmarks.sh
```

Column names: `vizdom-uied vizdom-omniparser vizdom-modular
vizdom-modular-desc vizdom-modular-desc-slm vizdom-modular-desc-vlm
vizdom-modular-desc-vlm-chain ablation elam-7b ui-tars-1.5-7b aria-ui parity`. Each run writes a new timestamped json+md, so
nothing is overwritten; `summary.md` lists every row found. `prefetch.sh`
honours the same `ONLY=` so a single-column rental downloads only that
column's weights. `ablation` is the stage ablation of `benchmarks/README.md`
sec. 7 (eleven columns, about 20 min; `VIZDOM_ABLATION_COLUMNS` overrides the
list); its `ablation-<stamp>.json`, `ablation-report.md` and the per-column
runner files land in `<run dir>/ablation/`, a subdirectory of their own so
that its control columns, which carry the main columns' names, do not
replace the main rows in `summary.md`. `ONLY="ablation"` alone also fetches
OmniParser and the Ollama models and starts the server.

### Run 7: the VizDOM columns only (after the Tesseract fix, 2026-10-28)

The grounder columns reproduced bit for bit on an Ada card twice, so a run
that only needs the VizDOM rows re-measured with the OCR retry in place
skips them. About 40 min of a 48 GB card, no 7B download:

```bash
tmux new -s bench
git clone https://github.com/milanac030988/vizdom.git && cd vizdom && git checkout develop
export ONLY="vizdom-uied vizdom-omniparser vizdom-modular vizdom-modular-desc vizdom-modular-desc-slm ablation"
bash deploy/gpu/setup.sh                 # installs tesseract-ocr and prints its version - check that line
bash deploy/gpu/prefetch.sh              # OmniParser weights + Ollama with the two small models only
PYTHONPATH=src USE_TF=0 .venv/bin/python deploy/gpu/preflight.py --pipeline --grounding
#   want:  tesseract         OK  /usr/bin/tesseract
#          vizdom-omniparser OK  N elements      vizdom-modular  OK  N elements
#          slm / vlm tiers   OK  (one description resolved each)
#   a FAIL on tesseract means the OCR stage would run as in runs 1-6: fix before paying for the sweep
bash deploy/gpu/run_benchmarks.sh        # the six columns, then summary.md and the tarball
```

`gpu.txt` in the run dir now records the Tesseract version (or `MISSING`),
so a result file says whether the second OCR engine was there. Expect the
VizDOM rows above those of runs 3 and 6 (laptop: modular `text=` 0.915
against 0.883, the chain 0.958 against 0.934) and the grounder rows to be
quoted from run 3 / run 6 as before.

Done on 2026-10-28 (`gpu-20261028_120820`, RTX A6000, `c6b8e72`, 31 min,
`tesseract 5.3.4`): uied 0.850 / 0.957 / 0, omniparser and modular 0.916 /
0.957 / 0, the chain 0.958 / 0.973 / 0, slm-only 0.639 / 0.877 / 0.017, and
the eleven ablation columns reproduced the laptop figures to three decimals.

### The `desc=` columns (ADR-022, VizDOM's language tier)

The six headline columns resolve VizDOM steps with `text=` only, so they
compare *VizDOM without its language tier* against grounders that are all
language tier. The `desc=` columns close that gap: same parse-once DOM as
`vizdom-modular`, but each step resolves the manifest's auto-generated
description (`Save button`, `Username input field`) through the `desc=`
tier chain — the code behind `Get Visual Element  desc="..."`. One column per
chain:

| Column | `--grounding-tiers` | What it measures |
|---|---|---|
| `vizdom-modular-desc` | `lexical,slm` (the production default) | what a test author gets from `desc=` today, plus the per-tier resolution rate |
| `vizdom-modular-desc-slm` | `slm` pinned | the text LM over the DOM table, alone |
| `vizdom-modular-desc-vlm` | `vlm` pinned | the VLM Set-of-Mark over the screenshot with no shortlist — measured in run 4 at 0.117: the overlay caps at 20 marks in DOM order, so on a DOM with a median of 33 elements fewer than half the targets are even marked. Kept for the comparison, not a model result |
| `vizdom-modular-desc-vlm-chain` | `lexical,vlm` | the vision tier the way production uses it: lexical scoring answers what it can and hands the VLM a shortlist of eight (or the pool when nothing scored) — the fair head-to-head with the grounders (both sides resolve language; VizDOM picks among DOM candidates, the grounders regress a point). Run 5 (2026-10-27): 0.930 / 0.691 / 0.113; it keeps the lexical hits and passes 34 of the 40 nonsense captions the VLM answered, and 68 of its 116 VLM calls were refused by Ollama (HTTP 500) and are recorded as errors. Run 6 (ca1f0f7, same card as run 3): 0.925 / 0.714 / 0.057 with 80 of 116 calls refused — the refusals cover the same block of states in every run (`dashboard_0195` to `settings_0050` on the Ada host) and are the vision model looping into a repeated token, which Ollama aborts with `500 prediction aborted, token repeat limit reached`; the column has never been fully measured, see the benchmark README |

A fresh resolver is built per step (the production per-screen cache would
otherwise answer the verify step from the action step), so the false-pass
rate on the 88 nonsense captions is a real measurement of the tier, not of
the cache. Models: `qwen2.5:3b` (slm) and `qwen2.5vl:3b` (vlm) through Ollama
— `prefetch.sh` installs Ollama and pulls both (~5 GB), `run_benchmarks.sh`
starts the server if needed and **skips** the three columns when it is not
reachable. Override the models with `VIZDOM_GROUNDING_MODEL` /
`VIZDOM_GROUNDING_VISION_MODEL` (both scripts read them; e.g. `qwen2.5vl:7b`
on a big card — then quote the size with the number). Note the Ollama tag is
`qwen2.5vl` (no dash); the project config default was the HF name
`qwen2.5-vl:3b`, which does not pull, until 2026-11-09 (now `qwen2.5vl:7b`;
the runner's own default stays `qwen2.5vl:3b` so column names keep their
meaning). Since run 4 a miss records every tier's own verdict
in the step's `detail` (`no confident match (lexical: tie at 3.00 between 2
candidates ...; vlm returned out-of-range mark 37)`), so a column of misses
can be diagnosed from the tarball alone.

### Run 8: the real-application set (`rw-` columns, 2026-11-02)

`benchmarks/lifecycle-realworld-v1`: 46 screens of 9 desktop applications
with UI Automation ground truth and negatives taken from *other screens of
the same application* (`Export` where only `Import` is shown) — see its
README. Laptop figures exist for the VizDOM columns (`text=` 0 of 92 false
passes, `desc=` 0 of 92 after ADR-022 1.9); what only a GPU gives is the
**grounders on the same plausible negatives**, the comparison the paper
needs. The sweep runs the set into `<run dir>/realworld/` with its own
`summary.md`; the columns are named `rw-...`. A rental for this set alone,
about 2.5 h on a 48 GB card (Aria-UI needs 80 GB and is skipped below it).
Measured on run 8 (RTX PRO 5000 Blackwell, `gpu-20261108_221541`): 2 h 14 min
of columns, of which ELAM-7B alone took 81 min (4.8 s a step on the larger
real screenshots) and UI-TARS 18 min; every VizDOM column took 1-6 min. The
runner logs nothing per step, so a grounder column looks stalled; check
`nvidia-smi`, not the log. The commands:

```bash
tmux new -s bench
git clone https://github.com/milanac030988/vizdom.git && cd vizdom && git checkout develop
export ONLY="vizdom-modular-desc vizdom-modular-desc-verify-chain vizdom-modular-desc-vlm7-chain rw-vizdom-uied rw-vizdom-omniparser rw-vizdom-modular rw-desc rw-desc-verify-chain rw-desc-slm rw-desc-vlm rw-desc-vlm-chain rw-desc-vlm7-chain rw-elam-7b rw-ui-tars-1.5-7b rw-aria-ui"
bash deploy/gpu/setup.sh
bash deploy/gpu/prefetch.sh              # an rw- column fetches what its synthetic namesake needs
PYTHONPATH=src USE_TF=0 .venv/bin/python deploy/gpu/preflight.py --pipeline --grounding \
    --grounders elam-7b,ui-tars-1.5-7b
#   want:  real-world set: 46/46 screens present
bash deploy/gpu/run_benchmarks.sh
```

Since ADR-022 1.9 the verify steps of a production `desc=` chain
(`lexical,slm`, `lexical,vlm`, and the ablation's `+desc`) are scored the way
the assertion keywords score them — lexical only — so on a re-run of the
synthetic set those verify figures move (0.973 → about 0.970 for the chain);
the pinned `slm` / `vlm` columns, the `text=` columns and the grounders are
unchanged. `--desc-verify chain` reproduces the old scoring, and the sweep
runs it as its own column on both sets (`vizdom-modular-desc-verify-chain`,
`rw-desc-verify-chain`; row name `...+desc[lexical+slm][verify=chain]`), so a
run 8 shows run 7's figures and the new default side by side.

The `-desc-vlm7-chain` columns run the production `lexical,vlm` chain with
`qwen2.5vl:7b` (`VIZDOM_GROUNDING_VISION_MODEL_BIG`; prefetch pulls it,
~6 GB): the 3B model loops on Set-of-Mark prompts (runs 4-6). A non-default
model is part of the row name (`...+desc[lexical+vlm][vlm=qwen2.5vl:7b]`).
Preflight checks only the default models; the 7B pull is in the prefetch log.
The `ONLY` above also takes three synthetic columns (the production chain,
its `verify=chain` twin and the 7B chain, ~15 min): the twin should repeat
run 7's 0.958 / 0.973 / 0 under the ADR-022 1.10 number guard.

Reading the tarball (unpacked next to itself on first use): one table per
set with false passes split by negative kind, each column step by step
against run 7 and the laptop baseline, the 3B/7B and keyword/chain twins,
action-hit per application, and every false pass with its explanation.

```bash
PYTHONPATH=src python -m visual_dom.evaluation.lifecycle.compare \
    benchmarks/results/gpu-<stamp>.tar.gz \
    --ref benchmarks/results/gpu-20261028_120820 \
    --ref benchmarks/results/realworld_local --out run8.md
```

### Run 9: what the audit could not measure offline (`run9.sh`, 2026-11-09)

The audit of the evidence (`benchmarks/lifecycle-realworld-v1/AUDIT.md`)
recomputes everything it can from saved result files. Four things need a
card, and `deploy/gpu/run9.sh` is a sweep of its own for them (it reruns half
of some columns, which the full sweep never does):

| Columns | Set, result dir | What they answer |
|---|---|---|
| `rw-elam-7b`, `syn-elam-7b` | main sets, verify steps only | ELAM's verdicts under the official FAILED-first rule; the raw answer is kept in each step's `detail`, so the rule can be re-scored without another rental |
| `rw-ui-tars-1.5-7b`, `rw-ui-tars-yesno`, `syn-ui-tars-yesno` | main sets, verify steps only | UI-TARS asked the statement as a yes/no question (`ui-tars-1.5-7b[verify=yesno]`) beside the proxy "any point is a pass", on one card |
| `nm-vizdom-modular`, `nm-desc`, `nm-desc-vlm7-verify-chain`, `nm-ui-tars-1.5-7b`, `nm-ui-tars-yesno`, `nm-elam-7b` | `lifecycle-realworld-nearmiss-v1`, `nearmiss/` | every column on the 168 near-miss negatives (`Save` where only `Save As` is shown); the `verify-chain` row is the pre-1.9 scoring, where the model tier may vouch |
| `ho-vizdom-modular`, `ho-desc`, `ho-desc-vlm7-chain`, `ho-ui-tars-1.5-7b`, `ho-ui-tars-yesno`, `ho-elam-7b` | `lifecycle-realworld-heldout-v1`, `heldout/` | screens of applications no constant was looked at on; skipped when that manifest is not in the clone (capture recipe in its README) |
| `rw-vizdom-modular`, `rw-desc`, `rw-desc-vlm7-chain`, `syn-desc`, `syn-desc-vlm7-chain` | main sets | the VizDOM rows end to end at this commit (run 8's rows predate the exact-name bonus) |

`--kinds verify` on the runner runs the verify steps only: a grounder's
clicks do not depend on its verdict rule, so they stay run 8's. Such a row
shows action-hit `None (0)`. About 2.5 h of columns on a 48 GB card, of which
ELAM is 1 h 45 min (5.4 s a verify step on real screens, run 8); the cheap
columns run first and ELAM last. A 24 GB card is enough (no Aria-UI).

```bash
tmux new -s bench
git clone https://github.com/milanac030988/vizdom.git && cd vizdom && git checkout develop
bash deploy/gpu/setup.sh
ONLY="vizdom-modular vizdom-modular-desc elam-7b ui-tars-1.5-7b" bash deploy/gpu/prefetch.sh
#   inline, NOT exported: OmniParser, both 7B grounders, Ollama with the 3B pair and qwen2.5vl:7b
PYTHONPATH=src USE_TF=0 .venv/bin/python deploy/gpu/preflight.py --pipeline --grounding \
    --grounders "ui-tars-1.5-7b[verify=yesno]"
#   want:  ui-tars-1.5-7b[verify=yesno] OK  ground -> (x, y) ..., yes/no -> real: 'Yes', nonsense: 'No'
#   a FAIL here means the model does not answer the question with a word: run the
#   sweep anyway with RUN9_ONLY naming the other columns, and say so in the report
PYTHONPATH=src USE_TF=0 .venv-legacy/bin/python deploy/gpu/preflight.py --grounders elam-7b
bash deploy/gpu/run9.sh
```

Columns are selected with `RUN9_ONLY="nm-elam-7b rw-elam-7b"` (and `OUT_DIR`
for a rerun into an existing run dir), not `ONLY`: `prefetch.sh` reads `ONLY`
with the full sweep's column names. Copy the tarball back as usual; `compare`
reads `nearmiss/` and `heldout/` like `realworld/`, pairs the yes/no row with
the proxy row as twins, and takes run 8 as the reference:

```bash
PYTHONPATH=src python -m visual_dom.evaluation.lifecycle.compare \
    benchmarks/results/gpu-<stamp>.tar.gz \
    --ref benchmarks/results/gpu-20261108_221541 --out run9.md
PYTHONPATH=src python -m visual_dom.evaluation.lifecycle.audit \
    --run benchmarks/results/gpu-<stamp> --benchmark lifecycle-realworld-nearmiss-v1 \
    --out run9-nearmiss-audit.md       # clustered intervals by screen and application
```

Give both tools `--out`: their tables contain characters a Windows console
in cp1252 cannot print.

Reading the yes/no row: UI-TARS has no verdict output and was not trained to
answer this prompt, so the row is reported beside the proxy row, never
instead of it. An answer that is neither word is scored as no verdict (wrong
on a present caption, not a false pass on an absent one) and its text is in
the step's `detail`.

### Aria-UI on a 48 GB card: offload mode (experimental)

The clean path for Aria-UI is an 80 GB card. The opt-in alternative is
`VIZDOM_ARIA_OFFLOAD=1` (empty or `0` means off, in the adapter and in the
two shell scripts alike; below 40 GB the scripts skip the column instead of
downloading 50 GB for a load the adapter refuses): the adapter loads bf16 with an accelerate
`max_memory` budget of card-minus-5 GiB on the GPU and the rest in host RAM,
so the last decoder layers stream over PCIe on every generated token. Expect
several seconds per step (2026-10-26 run 3 host: PCIe 4.0 ×8, 13 GB/s) and
budget 1–2 h for the 514 steps. It is untested with Aria's custom MoE code:
**preflight is the load test**, and a FAIL there costs twenty minutes, not
the sweep. Rent ≥ 40 GB VRAM and **≥ 24 GB host RAM** (the spill is ~5 GiB
plus the loader's working set). Aria-UI-only rental, start to finish:

```bash
tmux new -s bench
git clone https://github.com/milanac030988/vizdom.git && cd vizdom && git checkout develop
bash deploy/gpu/setup.sh                                   # ~6 min, builds .venv-legacy too
export VIZDOM_ARIA_OFFLOAD=1 ONLY="aria-ui"
bash deploy/gpu/prefetch.sh                                # only the 50 GB Aria-UI download
PYTHONPATH=src USE_TF=0 .venv-legacy/bin/python deploy/gpu/preflight.py --grounders aria-ui
#   want:  aria-ui   OK    ground -> (x, y) (bf16, load+infer NNNs, infer N.Ns)
#   and in the log above it: "Aria-UI device map: N modules, M on cpu/disk"
#   FAIL / CUDA out of memory / "placed on DISK" -> stop here, destroy the box
bash deploy/gpu/run_benchmarks.sh                          # the aria-ui column only
```

Then copy the tarball as usual. The result JSON carries the column like any
other; quote it as "bf16, CPU-offloaded, 48 GB card" because the latency is
not comparable with an all-on-GPU run (accuracy is: the weights and the
decoding are the same).

## What the sweep produces

`benchmarks/results/gpu-<stamp>/` with one result json+md per column:

- `vizdom-uied`, `vizdom-omniparser`, `vizdom-modular` — our approach
- `vizdom-modular-desc`, `-desc-slm`, `-desc-vlm`, `-desc-vlm-chain` — our
  approach resolving `desc=` through each ADR-022 tier chain (row names carry
  the chain, e.g. `vizdom-modular+desc[lexical+vlm]`; `cost.resolved_by_tier`
  says which tier answered how many steps, and a missed step's `detail` says
  why each tier declined)
- `<stamp>-doms/<executor>/<state>.json` — every DOM a VizDOM column parsed,
  next to its result file, so a missed step can be diagnosed from the DOM it
  actually saw (run 4's false pass needed the GPU DOM of `dialog_0141` and it
  had not been kept). Indented JSON with the flat list and the hierarchy:
  21–35 MB per column uncompressed, which is why a full-sweep tarball is
  ~18 MB from run 6 on (30–57 KB before). Columns parsed by the same
  backend produce byte-identical folders — a free parity check.
- `ollama-serve.log` — the model server's own log for the whole sweep
  (`prefetch.sh` / `run_benchmarks.sh` start it with the log on
  `$VIZDOM_OLLAMA_LOG`, default `~/ollama-serve.log`, and the sweep copies
  it in); needed to say *why* a VLM call came back `Ollama error: 500`
- `elam-7b`, `ui-tars-1.5-7b`, `aria-ui` — the competing end-to-end grounders
- `parity.txt` — ADR-027 combos incl. per-stage latency on this GPU
- `summary.md` — all result rows in one table; `gpu.txt` — card, driver, commit
- `sweep.log` plus one `.log` per column (a failed column writes its log and
  the sweep continues)

Metrics per column: action-hit, verify accuracy, false-pass rate, latency
(load vs parse split) — the lifecycle benchmark from `benchmarks/README.md`.

## Version pins (why setup.sh is picky)

Learned on the first paid run (2026-10-25, RTX 4090 on Vast):

- `huggingface_hub` ≥ 1.0 renamed the CLI to `hf`; `prefetch.sh` handles both.
  Login, if HF throttles anonymous downloads: `hf auth login`.
- The `cu121` torch index stops at 2.5.1 and current transformers refuses
  torch < 2.6 (it then disables PyTorch entirely); `cu126` is the default now,
  `cu128` on Blackwell.
- transformers is pinned to **4.49.0** in the main env: Florence-2 (OmniParser
  captions) breaks at 4.50 and UI-TARS (Qwen2.5-VL) needs ≥ 4.49. ELAM's Molmo
  code needs ≤ 4.48 and Aria-UI ≤ 4.47, so setup.sh builds `.venv-legacy`
  (4.47.1) and `run_benchmarks.sh` runs those two columns with it.
- ELAM's modeling file imports `einops` and `tensorflow` at module top, so
  the legacy env carries `tensorflow-cpu` purely to satisfy the import check
  (`USE_TF=0` everywhere). Aria's tokenizer needs `sentencepiece`.
- OmniParser's `util/utils.py` imports `openai` and `paddleocr` at module top;
  setup installs `openai`, prefetch applies the project's lazy-PaddleOCR patch
  (`scripts/setup_omniparser.py`). Without it the pipeline *silently* runs
  UIED under the omniparser label — preflight now asserts the backend is up.
- 7B grounders run **bf16, unquantized** on a ≥ 20 GB card (`--no-quantize`);
  Molmo/ELAM under bnb 4-bit dies with a Float/Half dtype error, and ELAM in
  bf16 must generate under `torch.autocast` (its processor emits float32
  image tensors). The grounder does both.
- ELAM needs its model-card prompt templates, and its `<point>` coordinates
  are **percent (0–100)**, not fractions — the bare instruction got prose and
  a 0.0 column; rescored offline it was 0.916. The adapter is fixed; preflight
  checks the point lands inside the image and that `judge()` returns a verdict.
- `tests/samples/*.png` is gitignored: preflight and parity use the tracked
  `data/synthetic/test/images/` screens on a fresh clone.
- The runner exits non-zero when **every** step of a column errored and
  writes a `FAILED` row instead of numbers, so the sweep reports FAILED and
  `summary.md` cannot show a 0.0 that looks like a measurement. `summary.md`
  keeps one row per column, the latest, so an `ONLY=` rerun replaces it.

## Notes & failure modes

- **Tesseract is a binary, not a pip package.** `setup.sh` now installs
  `tesseract-ocr` and prints its version; without it the OCR stage's
  low-confidence retry (ADR-012) does not run and the detector warns once.
  Runs 1–6 lacked it (the detector only looked for a Windows install), so
  every VizDOM row of those runs is a lower bound: the laptop with the
  retry measures modular `text=` 0.915 / 0.957 against the hosts' 0.883 /
  0.934 (`benchmarks/README.md` §7).
- **Every download is resumable** — rerun `prefetch.sh` after an interruption.
- **One column failing does not kill the sweep** (`run_benchmarks.sh` runs each
  in its own process and keeps going); check its `.log` in the results dir.
- Aria-UI is auto-skipped below 70 GB VRAM (`available()` says why in the log).
  Preflight prints SKIP for that one reason only; a grounder that is
  unavailable for any other reason (missing package) is a FAIL.
- The `desc=` columns are skipped (not failed) when Ollama is not reachable;
  preflight prints SKIP for that one reason and FAIL when Ollama runs but a
  model is missing or a tier cannot answer. Ollama shares the card with the
  pipeline (the two 3B models take ~5 GB), fine on anything ≥ 16 GB. If
  Ollama dies mid-column, the steps whose model tier reports `unavailable`
  are recorded as errors (not misses), and a column of nothing but errors is
  marked FAILED and exits 1 like any other column. A step detail reading
  `Ollama error: 500 {"error":"prediction aborted, token repeat limit
  reached"}` is **not** the server dying: it is the model looping on that
  prompt (qwen2.5vl:3b emits `8888…` on some 1080p Set-of-Mark overlays at
  temperature 0, runs 4–6) and Ollama ≥ 0.40 cutting it off. Such steps are
  errors too; the server keeps serving the next call. `ollama-serve.log` in
  the tarball shows them as aborted slots.
- The Qwen2-VL captioner combo is picked up automatically once an
  ollama-backed Captioner lands in `modular_backend._CAPTIONERS`; until then
  `parity_on_box.py` notes it as unavailable. The Ollama pull it needs is the
  same one the `desc=` columns make.
- The RT-DETR region fine-tune (ADR-027 trigger 2b) is **not** part of this
  sweep — it is a training job; keep the box after the sweep only if that has
  been prepared separately.
- Results drift slightly between machines (easyocr weights, torch, OpenCV
  versions): the 2026-10-25 box gave uied 0.779 / omniparser 0.883 / verify
  0.934 where the laptop had 0.803 / 0.916 / 0.957. Report the environment
  with the number.
