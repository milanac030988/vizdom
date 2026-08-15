# Rented-GPU benchmark runbook

Purpose: run the hardware-gated benchmarks — the **grounder columns** (ELAM-7B,
UI-TARS-1.5-7B, Aria-UI) for the lifecycle comparison, and the **ADR-027
combos** — on a rented GPU box, spending as little paid time as possible.
Everything is scripted; the human steps are clone, four commands, one scp.

## Renting: what to pick

| Card | VRAM | Runs | Note |
|---|---|---|---|
| RTX 4090 / A5000 / L4 | 24 GB | everything, Aria-UI in 4-bit | **recommended** — best price/coverage |
| A6000 / L40S | 48 GB | everything, Aria-UI comfortable | pay more only if 24 GB is unavailable |
| 16 GB cards | 16 GB | 7B columns only, **no Aria-UI** | acceptable fallback |

Pick an image with the **CUDA driver preinstalled** (any PyTorch template on
RunPod / Lambda / Vast). Disk: **≥ 150 GB** (models total ~80 GB + caches).

## Cost picture

Downloads (~80 GB) dominate wall time on the box — typically 10–25 min on a
datacenter pipe. Setup ~5 min. The sweep itself: the synthetic manifest is
small; grounder columns run at seconds-per-step on a real GPU (vs
minutes-per-step quantized on the laptop). Budget **2–3 hours total**; at
typical 24 GB rates that is a few dollars.

## The four commands

```bash
git clone https://github.com/milanac030988/vizdom.git && cd vizdom
bash deploy/gpu/setup.sh          # ~5 min: uv, python 3.12, CUDA torch, deps
bash deploy/gpu/prefetch.sh       # ~10-25 min: ALL model downloads in parallel
bash deploy/gpu/preflight.sh      # ~1-2 min: each model grounds ONE image
bash deploy/gpu/run_benchmarks.sh # the unattended sweep
```

**Do not skip preflight.** It loads every model and grounds one instruction —
a broken adapter or OOM fails there in minute one, not two hours into the
sweep.

Then from your own machine:

```bash
scp <box>:~/vizdom/benchmarks/results/gpu-*.tar.gz .
# verify the tarball opens and the .md tables are inside — THEN stop the rental
```

## What the sweep produces

`benchmarks/results/gpu-<stamp>/` with one result json+md per column:

- `vizdom-uied`, `vizdom-omniparser`, `vizdom-modular` — our approach
- `elam-7b`, `ui-tars-1.5-7b`, `aria-ui` — the competing end-to-end grounders
- `parity.txt` — ADR-027 combos incl. per-stage latency on this GPU
- per-column logs (a failed column writes its log and the sweep continues)

Metrics per column: action-hit, verify accuracy, false-pass rate, latency
(load vs parse split) — the lifecycle benchmark from `benchmarks/README.md`.

## Notes & failure modes

- **Every download is resumable** — rerun `prefetch.sh` after an interruption.
- **One column failing does not kill the sweep** (`run_benchmarks.sh` runs each
  in its own process and keeps going); check its `.log` in the results dir.
- Aria-UI is auto-skipped below 20 GB VRAM (`available()` says why in the log).
- The Qwen2-VL captioner combo is picked up automatically once an
  ollama-backed Captioner lands in `modular_backend._CAPTIONERS`; until then
  `parity_on_box.py` notes it as unavailable.
- The RT-DETR region fine-tune (ADR-027 trigger 2b) is **not** part of this
  sweep — it is a training job; keep the box after the sweep only if that has
  been prepared separately.
- HuggingFace rate limits: anonymous downloads usually suffice; if throttled,
  `huggingface-cli login` with a free token before `prefetch.sh`.
