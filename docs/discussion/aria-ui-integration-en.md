# Aria-UI: What It Provides, and How It Can Help Our Pipeline

A practical read of *Aria-UI: Visual Grounding for GUI Instructions* — its exact input/output contract, what it can and cannot do, and the concrete points where it plugs into the Visual DOM pipeline.

!!! warning "Source & confidence"
    Based on the paper [arXiv:2412.16256v1](https://arxiv.org/html/2412.16256v1) (Yang, Wang, Li, Luo, Chen, Huang, Li — HKU & Rhymes AI).
     Details of the **exact prompt template and response string format** come from the model implementation, not the paper —
     items marked (verify) must be confirmed against the official model card/repo before coding against them.

## 1. What Aria-UI is

Aria-UI is a vision-language model specialised in **GUI element grounding**: given a screenshot and a
natural-language instruction, it tells you *where* on screen the target element is. Its explicit design premise —
**pure vision, no HTML and no accessibility tree** — is the same problem statement as our project.

| | | |
|---|---|---|
| **Base model** |  | Aria — multimodal MoE , only 3.9B activated parameters (cheaper per inference than a 7B dense model). |
| **ScreenSpot** | 82.4% | Average single-step grounding accuracy. |
| **Max resolution** | 3920×2940 | Extended from 980×980 by splitting the image into blocks with aspect-ratio padding (NaViT-style). |
| **Training scale** | 11.5M | samples over 3.9M elements — web, desktop and mobile (general domain). |

## 2. What it takes as INPUT

**INPUT**
1. **A GUI screenshot** — any resolution up to 3920×2940; high-DPI screens are handled natively by block splitting.
2. **A natural-language instruction** naming *one* target, e.g.
 `"click the Submit button"`, `"the search input field"`.
3. **(Optional) Action history** — previous steps as text or as past screenshots, enabling context-aware grounding
 ("now tap the second item") (verify format).

**OUTPUT**
- **Normalized coordinates in the `[0, 1000]` range** pointing at the target element.
- Effectively a **location / point**, not a labelled tree. (verify: point vs. box)
- One answer per instruction.

### Converting its coordinates to our pixel space

Our DOM uses pixel bounds `[x1, y1, x2, y2]`. Aria-UI returns values normalized to 0–1000, so:

`px = (x_aria / 1000) * image_width
py = (y_aria / 1000) * image_height`

!!! danger "The single most important caveat"
    A grounding model of this type returns **a point, not a bounding box**. Our DOM needs boxes.
     That means Aria-UI *cannot produce our geometry directly* — it can only say “the element is around here”,
     and our CV layer must still supply the actual box. Conveniently, this is exactly what our architecture already demands.

## 3. What it can and cannot do — read this before designing

|  | Capability | Consequence for us |
| --- | --- | --- |
| CAN | Locate a described element on a screenshot with no a11y tree | Works on Qt/OpenGL/custom UIs — our exact target |
| CAN | Handle very high-resolution screens | Relevant to ADR-008 / ADR-012 (resolution & upscaling) |
| CAN | Understand natural-language references ("the blue confirm button") | Enables human-readable locators for Robot Framework |
| CAN | Use action history for context | Useful for multi-step test flows |
| CANNOT | Enumerate *all* elements on a screen | **It is not a detector.** It answers “where is X?”, not “what is on this screen?” — so it cannot replace UIED/YOLO |
| CANNOT | Return a hierarchy / DOM tree | Our DOM contribution stays differentiated |
| CANNOT | Return bounding boxes (returns a point) | CV must still own geometry |
| CANNOT | Plan by itself | Paper states it depends on an external planner and has no error correction |

!!! note "The framing that matters"
    Aria-UI is a **query engine** ("where is X?"), not a **detector** ("list everything").
     Every integration idea below is shaped by that one fact.

## 4. How it can help our pipeline — five concrete uses

### A. Validation against a known expectation (best fit)

!!! danger "First, the trap: circularity"
    If the list of things we ask Aria-UI to find comes from *CV output*, we can only look for elements CV
     already found — which defeats the whole purpose of finding what CV **missed**. A naive implementation
     finds nothing. Aria-UI **cannot do blind discovery**: it is a query engine, so we must already know what to ask for.
     The fix is not to engineer around this — it is to change the question we ask.

#### Discovery vs. validation — asking the right question

| Mode | Question | Aria-UI suited? |
| --- | --- | --- |
| **Discovery** | “What elements exist on this screen?” | NO — that needs a detector/enumerator (UIED/YOLO), not a grounding model |
| **Validation** | “Does element X exist, and is its box correct?” | YES — precisely its strength |

So this stage is **not** a recall-gap *discoverer*; it is a **validator against a known expectation**.
That framing is also more defensible academically: *“validate the DOM against what the tests actually need”* is a sharper
contribution than *“use a VLM to find missed elements.”*

#### Where do the expected targets come from?

Four realistic sources, ordered by usefulness to us:

| # | Source | Why it escapes circularity | Limitation |
| --- | --- | --- | --- |
| 1 | **OCR text** (best for our CV pain) | OCR and element detection are **separate stages**. OCR finds text even where the element detector failed to produce a proper box — so it supplies targets CV's box stage missed. | Cannot find icon-only elements with no text. |
| 2 | **The test script itself** (strongest for a testing tool) | Completely independent of CV. In GUI testing we *already know* what we are looking for — the test states it. | Only covers elements the tests reference. |
| 3 | **A golden / reference DOM** | Comes from a previous known-good build, not from this run's CV. | Requires an established baseline; regression scenarios only. |
| 4 | **A domain vocabulary** (crude fallback) | A fixed checklist, e.g. for a calculator: digits 0–9, operators, `MC/MR/MS`. | Does not generalise; weak to defend in a thesis. |

#### Worked example — our calculator merge problem

This is exactly the failure recorded in ADR-009 (adjacent buttons detected as one element), and source 1 solves it:

`Element detector → ONE merged box E7
OCR → "4", "5", "7", "8" (four separate text runs)

expected_targets = ["4", "5", "7", "8"] # from OCR, not from the box stage

for target in expected_targets:
 pt = aria_ui.ground(screenshot, target) # → a point
 box = find_cv_box_containing(pt)

 if box is None: → element exists but CV produced NO box → rescan region
 elif box is shared by >1 target:
 → MERGED box: 4 points inside E7 → SPLIT it
 else: → confirm box + attach semantic label`

Four distinct points landing inside a single box is direct, measurable evidence that the box must be split —
turning a subjective “the VLM thinks it looks merged” judgement into a geometric fact.

This fits our existing `SLMAdvisor` slot (ADR-009) and **respects our core principle**: Aria-UI only
points; CV still produces the final box.

!!! note "Practical split"
    Use **source 1 (OCR text)** for pipeline-internal split/merge validation — it needs no extra input and attacks
     our known calculator problem directly. Use **source 2 (the test script)** for validation at the Robot Framework level.
     Leave blind discovery to UIED/YOLO — never to a grounding model.

### B. Offline auto-labelling for our YOLO detector (highest long-term value)

Connects directly to the unfinished April thread (synthetic dataset + YOLO). Use Aria-UI **once, offline** to help annotate
real screenshots, then train our own small CPU-friendly detector on the result. We distil its ability into a fast model and
**add no GPU dependency at test-execution time**. Its point output pairs well with CV-proposed boxes: Aria-UI picks
*which* box is the "Submit button", CV supplies the box itself.

### C. Natural-language locators for the Robot Framework library (product value)

Aria-UI turns `"the Submit button"` into a location, which is exactly the locator-resolution problem our RF library solves.
It could serve as a **fallback locator strategy** when DOM-based locators fail — improving robustness without becoming the primary path.

### D. Borrow their ultra-resolution technique (methodology)

They extended 980×980 → 3920×2940 by **splitting the image into blocks with aspect-preserving padding**.
We hit the same wall (small elements at high DPI) and answered it with resolution-aware thresholds (ADR-008) and OCR upscaling (ADR-012).
Their approach is a citable, possibly borrowable alternative for our preprocessing.

### E. Borrow their data-synthesis methodology (most actionable)

The paper's headline contribution is a pipeline that synthesises **diverse, human-like instructions paired with element captions**
at scale, including an **automated traverse agent** that harvests desktop elements. This is directly applicable to our own
synthetic dataset generation and may be worth more to us than the model weights.

## 5. Integration sketch

`┌──────────────────────────────────────────────┐
Screenshot ─┤ CV DETECTION (UIED + OCR + symbol + YOLO) │ ← owns geometry (boxes)
 └───────────────────┬──────────────────────────┘
 │ elements[] with bounds
 ┌───────────────────▼──────────────────────────┐
 │ VALIDATION STAGE [NEW / Aria-UI] │
 │ • ground expected targets → points │
 │ • point inside a box? → confirm + label │
 │ • point with no box? → RECALL GAP, rescan │
 │ • box nobody grounds → possible noise │
 └───────────────────┬──────────────────────────┘
 │ validated elements
 ┌───────────────────▼──────────────────────────┐
 │ COARSE HIERARCHY → LLM REFINER → DOM COMPILER│ ← semantics only
 └───────────────────┬──────────────────────────┘
 ▼
 DOM JSON → Robot Framework library
 └ optional NL-locator fallback (Aria-UI)`

Aria-UI sits **beside** the existing `SLMAdvisor` as a selectable strategy — not as a deletion of the working
3B reviewer. Evaluation numbers should decide which survives.

## 6. What to verify before building

- **Point or box?** Confirm whether the released model can emit a bounding box or only a centre point. This changes the design.

- **Exact prompt/response format** — the paper gives the coordinate range, not the string template. Check the official model card/repo.

- **Licence and weights availability** — must be confirmed before we depend on it.

- **Hardware** — MoE with 3.9B activated is cheaper than 7B dense, but VRAM must hold the full expert set. Measure real latency per screen.

- **Domain check** — run it on *our* screenshots (calculator, desktop, Qt). Its general-domain training makes success far likelier than with an automotive-only model, but this is still the gate.

## 7. Next steps

- Run the **domain check** on 10–20 of our screenshots; measure how often the returned point lands inside the correct CV box.

- If hit-rate is good → prototype **use A (recall-gap validation)** behind a flag, alongside the existing advisor.

- In parallel, mine the **data-synthesis section (use E)** for our YOLO dataset work.

- Record the outcome as a new ADR (proposed: *ADR-015 — Grounding-model validation stage*).

!!! success "Summary in one line"
    Aria-UI gives us **“screenshot + description → where it is”**. It cannot build our DOM and cannot list elements,
     so it is not a replacement for CV — but it is an excellent **validator, auto-labeller and natural-language locator**,
     and its data-synthesis method may be the most valuable part of the paper for us.
