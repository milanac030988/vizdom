# The GUI Understanding Landscape: A Five-Way Comparison

Where our Visual DOM Generator sits among OmniParser, Aria-UI, ELAM-7B and Jedi — and, honestly, where our contribution actually lies now.

!!! warning "Source & confidence"
    Compiled from: the OmniParser repository (microsoft/omniparser), *Aria-UI* (arXiv:2412.16256v1),
     the ELAM-7B model card (sparks-solutions/ELAM-7B), and the OSWorld-G / Jedi project page
     (*Scaling Computer-Use Grounding via User Interface Decomposition and Synthesis*).
     All reported numbers are from the authors of each system. Statements about our own pipeline reflect the current
     `D:\Project\MasterProject` repository. This is a decision-support note, not an independent benchmark study.

## 1. Summary in 60 seconds

!!! note "The three things that matter"
    1. **Microsoft's OmniParser has independently built our architecture** — YOLO detection + OCR + a captioning model for semantics, emitting boxes with labels. This validates our design instinct and simultaneously threatens our novelty.
    2. **Nobody in this landscape produces a hierarchy.** OmniParser emits a *flat list*; the three grounding models emit a *single point*. The DOM tree remains genuinely ours.
    3. **They all target agents; we target testing.** Determinism, reuse, explainability and assertions are our requirements, not theirs. That is a real and defensible difference.

## 2. The five systems

| | |
|---|---|
| **Visual DOM Generator (ours)** | CV (UIED + OCR + symbol/screen detectors, YOLO planned) → rule-based coarse hierarchy → LLM refiner (Qwen2.5-3b) → DOM compiler → Robot Framework library.
    Principle: CV owns geometry, the LLM owns semantics . Output: UIAutomator-like DOM JSON tree . |
| **OmniParser (Microsoft)** | Screenshot → structured elements. YOLO-based icon detection + integrated OCR + Florence-2 captioning (V2; BLIP2 in V1.5).
    Output: bounding boxes + semantic labels + interactability . V1.5 added fine-grained small-icon detection. V2 released Feb 2025. |
| **Aria-UI (HKU / Rhymes AI)** | Pure-vision grounding, explicitly no HTML/accessibility tree. Base: Aria MoE, 3.9B activated.
    Input: screenshot + NL instruction (+ optional action history). Output: normalized [0,1000] point .
    11.5M training samples; ultra-resolution to 3920×2940. |
| **ELAM-7B (sparks-solutions)** | Base Molmo-7B-D (Qwen2-7B backbone). Two tasks: action grounding, and expected-result evaluation returning PASSED/FAILED . Trained on 17,708 instructions over 6,230 automotive UI images. Apache 2.0. |
| **Jedi / OSWorld-G (grounding research)** | Jedi-3B/7B models + a 4M-example synthesised dataset built by decomposing UIs (icons, components, documents, slides, sheets, layouts).
    OSWorld-G benchmark: 564 samples across text matching, element recognition, layout understanding, fine-grained manipulation and refusal . |

## 3. Capability matrix — the key table

| Capability | Ours | OmniParser | Aria-UI | ELAM-7B | Jedi |
| --- | --- | --- | --- | --- | --- |
| **Enumerates all elements** ("what is on screen?") | YES | YES | no | no | no |
| **Emits bounding boxes** | YES | YES | point only | point only | point only |
| **Hierarchy / DOM tree** | YES | flat list | no | no | no |
| **Grounds from NL instruction** ("where is X?") | via DOM query | no | YES | YES | YES |
| **Semantic labels / roles** | YES | YES | implicit | implicit | implicit |
| **Pass/fail evaluation built in** | via RF assertions | no | no | YES | no |
| **Explicit refusal** ("not present") | rule-based | n/a | weak | weak | measured |
| **Reusable across many actions** | YES — one parse | YES — one parse | re-infer each time | re-infer | re-infer |
| **Runs without GPU** | YES (CPU path) | partly | no | no | no |
| **Target consumer** | **Test automation** | Agents | Agents | HMI testing | Agents |

!!! note "Read the table this way"
    There are two distinct families here: **parsers** (ours, OmniParser) that answer *“what is on this screen?”*,
     and **grounders** (Aria-UI, ELAM, Jedi) that answer *“where is X?”*. They are complementary, not interchangeable.
     Within the parser family, the only row where we stand alone is **hierarchy**.

## 4. Benchmarks — and why they must not be pooled

!!! danger "Do not put these numbers in one column"
    Each figure below comes from a **different benchmark of different difficulty**. Comparing them directly is invalid
     and would be an easy point of criticism in a thesis defence.

| System | Benchmark | Score | Note |
| --- | --- | --- | --- |
| ELAM-7B | AutomotiveUI-Bench-4K | 87.6% grounding / 78.2% evaluation | Automotive domain only |
| Aria-UI | ScreenSpot | 82.4% | Single-step grounding; the easiest of these |
| Jedi-7B | OSWorld-G (564 samples) | 54.1% | vs UI-TARS-7B 47.5%; realistic, harder |
| OmniParser V2 | ScreenSpot Pro | 39.5% | Deliberately hard benchmark |
| Aria-UI | OSWorld (agentic) | 15.15% | End-to-end task success |
| Jedi-7B + GPT-4o / + o3 | OSWorld (agentic) | 27.0% / 50.2% | o3 run improves a 23% baseline |

!!! success "The finding worth citing"
    Grounding on easy benchmarks looks close to solved (82–88%), but on realistic ones it drops to **40–54%**,
     and end-to-end agentic success sits between **15% and 50%**.
     **Grounding is not the bottleneck; reliable, structured, repeatable execution is.**
     That gap is precisely the argument for a deterministic DOM in a *testing* context.

## 5. The uncomfortable finding: OmniParser

OmniParser is not a competing paradigm — it is **our paradigm, implemented by Microsoft Research**:

| Stage | Our pipeline | OmniParser |
| --- | --- | --- |
| Element geometry | UIED / YOLO detection | YOLO-based icon detection |
| Text | OCR — EasyOCR / PaddleOCR / Tesseract | Integrated OCR |
| Semantics | LLM refiner + SLM advisor (never coordinates) | Florence-2 captioning → functional description |
| Extra signal | visual\_type / role assignment | Interactability prediction |
| Output | **Hierarchical DOM JSON** | Flat list of labelled boxes |

#### Two readings, both true

- (Validation) An industrial research lab converging on the same architecture is strong external evidence that
 “CV owns geometry, a model adds semantics” is the right decomposition. This is citable support for our central claim.

- (Novelty threat) If OmniParser already turns a screenshot into labelled boxes, then **element detection is no longer a contribution**.
 A committee will ask what remains. We should answer that ourselves, now — not at the defence.

## 6. So where is our contribution now?

Stripping away everything the landscape already provides, four things remain genuinely ours:

| | |
|---|---|
| **1. Hierarchy construction** | Containment, alignment, label association and parent–child structure — turning a flat element list into a queryable tree. No system in this comparison does this. This is the strongest remaining claim. |
| **2. Testing orientation** | Locator strategies, assertions and Robot Framework keywords. Every other system targets agents , whose requirements
  (autonomy, task success) differ fundamentally from testing's (determinism, repeatability, diagnosability). |
| **3. Reuse economics** | One DOM serves many locators and assertions; grounding models re-infer per instruction. In a regression suite of thousands of steps
  this is the difference between a practical and an impractical tool. |
| **4. Explainability** | A failing test must be diagnosable. An inspectable tree with traceable rules explains why an element was matched;
  a coordinate from a black box does not. |

!!! note "Proposed one-sentence thesis claim"
    *“Existing systems either enumerate flat elements (OmniParser) or ground single targets from language (Aria-UI, ELAM, Jedi).
     This work contributes the missing layer — compiling detected elements into a reusable, explainable DOM hierarchy — and demonstrates
     that this representation, not per-instruction grounding, is the appropriate abstraction for deterministic GUI test automation.”*

## 7. Three strategic options

| Option | What it means | Pros | Cons |
| --- | --- | --- | --- |
| **A. Keep building our own CV** (status quo) | Continue improving UIED/OCR/YOLO ourselves. | Full control; no external licence issues. | Competing with Microsoft on our *weakest* component; the merge/split recall problems have persisted since January. |
| **B. Adopt OmniParser as the detection layer** (recommended) | Use OmniParser for boxes + labels; focus our work on hierarchy, DOM compilation and the RF library. | De-risks the weakest stage; stands on a maintained, benchmarked detector; moves the contribution to where we are actually novel.   (update) its AGPL detector adds *no new* licence obligation — we are already on AGPL via Ultralytics (see §9.2). | External dependency; less “we built it all” narrative. |
| **C. Hybrid / comparative** (safe fallback) | Keep our CV as the default, add OmniParser as a selectable backend, and compare the two empirically. | Produces a real evaluation chapter; avoids licence lock-in; keeps both paths open. | More engineering; two code paths to maintain. |

**Note:** options B and C both require the same abstraction — a pluggable *detector backend* behind a stable
element interface. Building that interface is worthwhile regardless of which option is finally chosen.

## 8. What to borrow from each

| From | What to take | Why |
| --- | --- | --- |
| OmniParser | **Interactability prediction** | Marking which elements are actionable is directly useful for test locators; we do not model this explicitly today. |
| OmniParser | Detection layer itself (option B) | Removes our long-standing recall weakness. |
| Jedi / OSWorld-G | **“Refusal” as a measured property** | In testing, a false positive (clicking the wrong element and “passing”) is worse than a failure. Refusal must be measured, not assumed. |
| Jedi / OSWorld-G | **The 5-category evaluation taxonomy** | Text matching, element recognition, layout understanding, fine-grained manipulation, refusal — a ready-made structure for our evaluation chapter. |
| Aria-UI | Ultra-resolution block splitting | Addresses the same small-element/high-DPI problem as ADR-008 and ADR-012. |
| Aria-UI + Jedi | **Data-synthesis methodology** | Two independent teams identify synthesis as the unlock (11.5M and 4M examples). This validates our synthetic-dataset/YOLO direction. |
| ELAM-7B | Expected-result evaluation (PASSED/FAILED) | Maps directly onto Robot Framework assertion keywords for fuzzy visual checks. |

## 9. Licensing & practical constraints

### 9.1 Verified licence status (confirmed 2026-07-20)

| Component | Licence | How verified |
| --- | --- | --- |
| OmniParser repository (`microsoft/OmniParser`) | **CC-BY-4.0** | Repository `LICENSE` file |
| OmniParser-v2.0 model card (overall) | MIT | Hugging Face model card |
| → `icon_detect` (the detector) | **AGPL-3.0** | Standard FSF AGPL-3.0 text in `icon_detect/LICENSE` |
| → `icon_caption` | MIT | Model card |
| ELAM-7B | Apache 2.0 | Model card |
| Aria-UI, Jedi | not yet verified | — |

Microsoft states it explicitly: *“Please note that icon\_detect model is under AGPL license, and icon\_caption is under MIT license.”*
The `icon_detect` weights are a YOLOv8 fine-tune, and Ultralytics distributes YOLOv8 under AGPL-3.0 — that is where the obligation is inherited from.

### 9.2 The finding that changes the decision

!!! danger "We are already on AGPL — independently of OmniParser"
    A scan of this repository shows the project **already depends on Ultralytics**:
     `pyproject.toml` (`ultralytics>=8.0.0`), `requirements-training.txt`,
     `scripts/training/cv/inference_yolo.py` (`from ultralytics import YOLO`) and
     `models/configs/cv_model_registry.py` (registers `yolov8n/s/m`).

    **Consequence:** AGPL is *not* an OmniParser-specific risk that can be avoided by declining OmniParser.
     The April decision to adopt YOLO already brought AGPL-3.0 into the project. Adopting OmniParser's detector introduces
     **no new licence class** — it is the same obligation we are already under. This materially weakens the
     licence argument against option B.

### 9.3 What AGPL-3.0 requires, by scenario

| Scenario | Impact |
| --- | --- |
| Thesis research, run locally, not distributed | Fine — AGPL does not trigger on private use |
| Publishing the thesis code publicly | The combined work must be licensed **AGPL-3.0** |
| Releasing the Robot Framework library for others | Must be **AGPL-3.0** |
| Serving it over a network (dashboard / API / SaaS) | **§13 network clause** — complete corresponding source must be offered to users |
| Commercial, closed-source product | Requires a paid **Ultralytics commercial licence** |

!!! warning "Legal caveat — not legal advice"
    Whether trained *weights* are subject to AGPL, and whether running inference creates a derivative work, is genuinely
     unsettled; Ultralytics asserts a broad reading. For any use beyond academic research, the university and (where relevant)
     an employer should be consulted before relying on this analysis.

### 9.4 The permissive escape route, if we ever need it

If the Robot Framework library is ever intended for workplace or commercial reuse, a permissively licensed detector should be
planned **early** — swapping detectors late is expensive.

- **RT-DETR** (original `lyuwenyu/RT-DETR`) — Apache 2.0. Notably, our own `cv_model_registry.py` already lists RT-DETR as the accuracy option.

- **YOLOX** (Megvii) — Apache 2.0

- **DETR** (Meta) — Apache 2.0

!!! danger "Trap to avoid"
    Using RT-DETR **through the `ultralytics` package is still AGPL**. The licence follows the
     *implementation*, not the architecture. A permissive path requires the original upstream repository.

!!! success "This justifies the detector-backend abstraction twice over"
    A pluggable detector interface now serves two purposes: it enables the empirical comparison of our CV against OmniParser,
     *and* it allows an AGPL detector to be replaced with a permissive one without rewriting the pipeline.
     That makes it the highest-value next piece of engineering regardless of which strategic option is chosen.

### 9.5 Other practical constraints

- **Hardware:** all three grounding models require a GPU; our CPU path is a genuine differentiator for test rigs and embedded targets.

- **Reproducibility:** every number here is author-reported. Any figure we cite as fact should first be reproduced on our own screenshots.

- **Domain:** ELAM is automotive-only; the others are general. Domain must be controlled in any comparison we run.

## 10. Recommendation & next steps

!!! success "Recommended path"
    Pursue **option C now, option B if the licence permits**: introduce a pluggable detector backend, run our CV and OmniParser
     side by side, and move the thesis's centre of gravity to **hierarchy construction + DOM compilation + Robot Framework integration**,
     where the landscape leaves a real gap.

- ~~Resolve the AGPL question for OmniParser's detector.~~ (done — see §9)
 Confirmed AGPL-3.0, but we are **already** under the same obligation through Ultralytics, so it no longer blocks option B.
 The remaining decision is a *project* one: is the RF library ever meant for workplace or commercial reuse? If yes, plan a permissive detector now (§9.4).

- **Define a detector-backend interface** (`detect(image) → elements[]`) so our CV, OmniParser and any permissive detector are interchangeable — now justified by both comparison and licence flexibility.

- **Run a like-for-like comparison** on our own screenshots (calculator, desktop, Qt): recall, merge/split errors, latency, CPU vs GPU.

- **Adopt the OSWorld-G taxonomy** for our evaluation chapter, adding *hierarchy correctness* — a dimension none of these benchmarks measure, and one where only we can compete.

- **Write the contribution paragraph** (section 6) and take it to the supervisor before further implementation.

- **Record the decision** as an ADR (proposed: *ADR-015 — Detector backend strategy and positioning*).

!!! note "Closing thought"
    The landscape has not invalidated this project — it has **clarified** it. Element detection is now a solved,
     commoditised layer, and continuing to compete there is the weakest available strategy. The unsolved problems are
     **structure, reuse, explainability and trustworthy failure** — all of which matter most in testing, which is exactly
     the domain this project already targets.
