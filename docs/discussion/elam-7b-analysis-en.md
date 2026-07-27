# ELAM-7B vs. the Visual DOM Pipeline

An analysis of a VLM-native GUI-testing model and what it means for a CV-first, DOM-generation architecture.

!!! warning "Source & confidence"
    Facts about ELAM-7B are drawn from its Hugging Face model card
     (`sparks-solutions/ELAM-7B`). Benchmark numbers are the authors' own, reported on the
     *automotive* UI domain. Claims about the Visual DOM pipeline reflect the current state of the
     `D:\Project\MasterProject` repository. Treat this as a decision-support note, not a verified benchmark study.

## 1. What ELAM-7B is

**ELAM (Evaluative Large Action Model)** is a vision-language model (VLM) fine-tuned for
GUI test automation. Rather than describing a screen, it acts on it: given a screenshot and an English
instruction, it returns where to tap and whether an expected result holds.

| | | |
|---|---|---|
| **Base model** |  | Molmo-7B-D (AllenAI), built on a Qwen2-7B backbone. Molmo is chosen for its native pointing / grounding ability. |
| **Task 1 — Action Grounding** | 87.6% | Screenshot + instruction → tap coordinates for the target element. |
| **Task 2 — Result Evaluation** | 78.2% | Validates a UI state, returns PASSED / FAILED + element coords. |
| **License** | Apache 2.0 | Commercially usable. transformers ≥ 4.48.2, bf16, trust_remote_code=True . |

- **Input / output:** UI screenshot + English text → normalized `[x, y]` coordinates (0–1) plus explanatory text.

- **Training data:** 17,708 instructions across 6,230 **automotive** UI images (German & English text; English prompts).

- **Benchmark:** AutomotiveUI-Bench-4K — Action Grounding 87.6%, Expected-Result Grounding 77.5%, Expected-Result Evaluation 78.2%.

## 2. Our pipeline in one page

The Visual DOM Generator converts a screenshot into an Android-UIAutomator-like **DOM JSON tree**,
so a Robot Framework library can locate and act on elements — even when no accessibility tree exists.

- **Design principle:** *CV handles geometry, the LLM handles semantics*. The LLM is explicitly forbidden from inventing coordinates.

- **3-stage hierarchy:** rule-based coarse builder → LLM refinement → DOM compiler.

- **Detection stack:** UIED + OCR (EasyOCR / PaddleOCR / Tesseract, dual-engine + upscale), plus newer symbol / screen detectors and an SLM advisor.

- **Output:** a reusable, inspectable hierarchy — not a single tap point.

- **Open thread (Apr 2026):** adding **YOLO** as an optional detector, and whether agentic patterns help.

## 3. The core tension: two opposite bets

!!! note "The one idea to take away"
    ELAM and our pipeline make **opposite architectural bets on who owns geometry.**
     ELAM lets the neural model emit coordinates directly (end-to-end grounding). We deliberately keep
     coordinates in the deterministic CV layer and let the LLM touch only *meaning*. This single
     difference drives every trade-off below.

This makes ELAM less of a plug-in component and more of a **competing paradigm** — which is
exactly what makes it valuable to your thesis. It gives you a concrete, published rival to define your
contribution against.

## 4. Head-to-head comparison

| Dimension | Visual DOM Pipeline (ours) | ELAM-7B |
| --- | --- | --- |
| Who produces coordinates | Deterministic CV (UIED/OCR/YOLO) | The VLM itself (grounding) |
| Primary output | Full DOM hierarchy (JSON tree) | Single tap point / pass-fail verdict |
| Reusability | One DOM serves many actions & assertions | Re-inference per instruction |
| Explainability | High — inspectable tree, traceable rules | Lower — end-to-end black box + text rationale |
| Compute | Runs on CPU; LLM optional/small | 7B VLM, GPU + bf16 effectively required |
| Domain evidence | General/custom UIs (Qt, OpenGL, calculator…) | Strong on *automotive* UIs; general-domain unproven |
| Evaluation built in | Via RF assertion keywords | Native "Expected Result Evaluation" (PASSED/FAILED) |
| Maturity of numbers | Internal, in progress | Published benchmark (author-reported) |
| License | Own code | Apache 2.0 (reusable) |

## 5. Four ways ELAM could fit

### A. As a baseline to compare against (recommended)

The cleanest, lowest-risk use. ELAM gives you a published, Apache-licensed rival with a public benchmark.
Comparing your DOM pipeline against it — on accuracy, compute, reusability and explainability — makes a strong
"related work" and "evaluation" chapter, and sharpens the argument for *why* a DOM intermediate representation earns its keep.

### B. As the evaluation / assertion stage (promising)

ELAM's "Expected Result Evaluation" (`PASSED`/`FAILED` + coords) maps almost directly onto
your Robot Framework assertion keywords. You could keep CV-driven DOM for locating and acting, and borrow a
VLM-style check for hard-to-express visual assertions ("is the warning banner shown?").

### C. As the SLM advisor / refiner (possible)

You already have an SLM-advisor stage (ADR-009) that reviews CV output. A grounding-capable VLM could
cross-check or repair the DOM — but note the philosophical friction: if it starts emitting coordinates, it
crosses your "no coordinates from the model" line. Usable, but bounds it to *reviewing*, not *producing*, geometry.

### D. As a signal to rethink the architecture (high-stakes)

If a 7B VLM grounds at ~88% end-to-end, one must ask whether the modular CV-first stack is still justified.
The honest answer for your thesis is a defensible *yes, under conditions*: DOM reusability, CPU-friendliness,
explainability, no per-action GPU inference, and producing a full tree (not one point). Make that argument
explicit rather than assumed.

## 6. Risks & limitations

!!! danger "Domain gap"
    ELAM is trained and benchmarked on **automotive** UIs. Its 87.6% does *not* transfer
     guaranteed to calculators, desktop apps, or Qt/OpenGL surfaces. Any comparison must control for domain, or it is unfair to both sides.

- **Compute cost:** a 7B VLM needs a GPU with bf16; your CV path can run on CPU. This matters for a "works anywhere" testing tool.

- **No hierarchy:** ELAM returns points/verdicts, not a structured tree — you lose the reusable DOM that your RF library is built around.

- **English-only prompts;** coordinate outputs are normalized 0–1 and need mapping back to pixels.

- **Reproducibility:** benchmark numbers are author-reported; independent replication on your own images is needed before citing them as fact.

## 7. Recommendation

!!! success "Suggested stance"
    Adopt ELAM-7B as a baseline and an optional evaluation module, not as a replacement for the DOM pipeline.

    It strengthens the thesis in two ways at once: (1) a credible, published comparator that legitimizes your
     problem, and (2) a ready-made visual-assertion capability you can bolt onto the Robot Framework side. Keep the
     CV-first DOM as your core contribution; use ELAM to define and defend its boundaries.

## 8. Open questions & next steps

- **Scope decision:** Is ELAM a comparison baseline, an integrated module, or both? (Recommendation: both, in that order.)

- **Fair benchmark:** Can we run ELAM on a small set of *our* screenshots (calculator, desktop, Qt) and measure grounding accuracy vs. our CV+DOM output?

- **Hardware:** Do we have a GPU with enough VRAM + bf16 to run 7B inference at a usable speed?

- **Integration point:** If we adopt the evaluation task, where does it sit — inside the RF assertion keywords, or as a post-DOM check?

- **Thesis framing:** Write one crisp paragraph: "Why a DOM intermediate representation beats direct VLM grounding for *our* use case." This is the intellectual core.
