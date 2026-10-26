# Rented-GPU benchmark runbook

Purpose: run the hardware-gated benchmarks — the **grounder columns** (ELAM-7B,
UI-TARS-1.5-7B, Aria-UI) for the lifecycle comparison, and the **ADR-027
combos** — on a rented GPU box, spending as little paid time as possible.
Everything is scripted; the human steps are clone, four commands, one download.

Status: first paid run done 2026-10-25 (RTX 4090, Vast.ai). Everything that
went wrong that day is now caught by `setup.sh` or `preflight.sh` — see
"Version pins" below before changing any dependency.

## Renting: what to pick

| Card | VRAM | Runs | Note |
|---|---|---|---|
| RTX 4090 / A5000 / L4 | 24 GB | VizDOM columns, ELAM-7B, UI-TARS-1.5 (bf16), parity | **recommended** — best price/coverage |
| A6000 / L40S | 48 GB | the above **plus Aria-UI** | only if the Aria-UI column is wanted |
| 16 GB cards | 16 GB | 7B columns in 4-bit only | acceptable fallback |

Aria-UI (25 B MoE) does **not** fit 24 GB: bitsandbytes 4-bit skips its
expert weights, so loading OOMs at shard 5/12 (measured 2026-10-26). Its
`available()` reports this below 40 GB, prefetch skips the 50 GB download,
and the sweep skips the column.

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

Downloads (~80 GB) dominate wall time on the box — typically 10–25 min on a
datacenter pipe. Setup ~6 min (two venvs). The sweep itself: ~1 min per VizDOM
column, ~15 min per 7B grounder column in bf16, Aria-UI 4-bit longer. Budget
**2–3 hours total**; at typical 24 GB rates that is 3–5 $ including bandwidth.

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
for ELAM also checks that a verdict comes back. Every failure class seen so
far (missing package, wrong transformers, wrong prompt template, wrong
coordinate scale, OmniParser silently degrading to UIED) fails there in minute
two, not two hours into the sweep as a column of zeros.

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

Column names: `vizdom-uied vizdom-omniparser vizdom-modular elam-7b
ui-tars-1.5-7b aria-ui parity`. Each run writes a new timestamped json+md, so
nothing is overwritten; `summary.md` lists every row found.

## What the sweep produces

`benchmarks/results/gpu-<stamp>/` with one result json+md per column:

- `vizdom-uied`, `vizdom-omniparser`, `vizdom-modular` — our approach
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
- The runner exits non-zero when **every** step of a column errored, so the
  sweep reports FAILED instead of a 0.0 row that looks like a measurement.

## Notes & failure modes

- **Every download is resumable** — rerun `prefetch.sh` after an interruption.
- **One column failing does not kill the sweep** (`run_benchmarks.sh` runs each
  in its own process and keeps going); check its `.log` in the results dir.
- Aria-UI is auto-skipped below 40 GB VRAM (`available()` says why in the log).
- The Qwen2-VL captioner combo is picked up automatically once an
  ollama-backed Captioner lands in `modular_backend._CAPTIONERS`; until then
  `parity_on_box.py` notes it as unavailable, and the Ollama pull in
  `prefetch.sh` is opt-in (`VIZDOM_PREFETCH_OLLAMA=1`).
- The RT-DETR region fine-tune (ADR-027 trigger 2b) is **not** part of this
  sweep — it is a training job; keep the box after the sweep only if that has
  been prepared separately.
- Results drift slightly between machines (easyocr weights, torch, OpenCV
  versions): the 2026-10-25 box gave uied 0.779 / omniparser 0.883 / verify
  0.934 where the laptop had 0.803 / 0.916 / 0.957. Report the environment
  with the number.
