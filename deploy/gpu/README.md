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
vizdom-modular-desc-vlm-chain elam-7b ui-tars-1.5-7b aria-ui parity`. Each run writes a new timestamped json+md, so
nothing is overwritten; `summary.md` lists every row found. `prefetch.sh`
honours the same `ONLY=` so a single-column rental downloads only that
column's weights.

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
`qwen2.5vl` (no dash); the project config default `qwen2.5-vl:3b` is the HF
name and does not pull. Since run 4 a miss records every tier's own verdict
in the step's `detail` (`no confident match (lexical: tie at 3.00 between 2
candidates ...; vlm returned out-of-range mark 37)`), so a column of misses
can be diagnosed from the tarball alone.

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
