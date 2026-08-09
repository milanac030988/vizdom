# ADR-007: CV Pipeline with Optional LLM Hierarchy Refinement

## Status

Accepted

## Date

2025-01-26

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2025-01-26 | 1.0 | Initial version |

## Context

The Visual DOM system uses a Computer Vision (CV) pipeline to detect UI elements from screenshots. The pipeline needs to:

1. Detect text elements (OCR)
2. Detect non-text UI elements (buttons, inputs, icons)
3. Merge and deduplicate detections
4. Build a hierarchical DOM tree structure
5. Generate locators for automation

The initial rule-based hierarchy builder has limitations:
- Cannot understand semantic relationships
- May incorrectly merge or split elements
- Cannot infer element roles from context
- Limited ability to fix OCR errors

## Decision

Implement a **two-stage hierarchy building approach**:

1. **Stage 1: Rule-based Coarse Hierarchy** (Always runs)
   - Fast, deterministic, no external dependencies
   - Uses spatial relationships (containment, alignment)

2. **Stage 2: LLM-based Refinement** (Optional)
   - Uses Small Language Models (SLMs) to refine the hierarchy
   - Fixes common CV detection errors
   - Adds semantic understanding

### Complete Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        VISUAL DOM PIPELINE                               │
└─────────────────────────────────────────────────────────────────────────┘

Screenshot
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: CV Detection (VisualDOMPipeline)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐                           │
│  │  Text Detection  │    │  UIED Detection  │                           │
│  │    (EasyOCR)     │    │ (Non-text elems) │                           │
│  └────────┬─────────┘    └────────┬─────────┘                           │
│           │                       │                                      │
│           └───────────┬───────────┘                                      │
│                       ▼                                                  │
│              ┌─────────────────┐                                         │
│              │ Merge & NMS     │                                         │
│              │ Deduplication   │                                         │
│              └────────┬────────┘                                         │
│                       │                                                  │
└───────────────────────┼──────────────────────────────────────────────────┘
                        ▼
              List of Detected Elements
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: Hierarchy Building (CoarseHierarchyBuilder)                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Rule-based Hierarchy (ALWAYS RUNS)                               │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ • Containment-based parent inference                             │    │
│  │ • Alignment grouping (rows, columns)                             │    │
│  │ • Label association (text → input)                               │    │
│  │ • Role assignment based on visual type                           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└───────────────────────┼──────────────────────────────────────────────────┘
                        ▼
              Coarse Hierarchy Tree
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: LLM Refinement (LLMHierarchyRefiner) [OPTIONAL]               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LLM-based Refinement (OPTIONAL - Requires LLM backend)           │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ • Merge over-segmented elements                                  │    │
│  │ • Split incorrectly merged elements                              │    │
│  │ • Fix visual_type classifications                                │    │
│  │ • Add semantic roles                                             │    │
│  │ • Delete noise/duplicates                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Supported LLM Backends:                                                 │
│  • Qwen2.5-3B-Instruct (local, recommended)                             │
│  • Phi-3.5-mini-instruct (local)                                        │
│  • Gemma-2-2B-it (local)                                                │
│  • Ollama (local server)                                                │
│  • OpenAI GPT-4o-mini (cloud API)                                       │
│                                                                          │
└───────────────────────┼──────────────────────────────────────────────────┘
                        ▼
              Refined Hierarchy Tree
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: DOM Compilation (DOMCompiler)                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  • Generate unique element IDs                                           │
│  • Calculate center points                                               │
│  • Assign accessibility roles                                            │
│  • Set clickable/editable/scrollable flags                              │
│  • Generate multiple locator strategies                                  │
│                                                                          │
└───────────────────────┼──────────────────────────────────────────────────┘
                        ▼
              Final DOM JSON Output
```

### LLM Refinement Operations

The LLM can perform these tree edit operations:

| Operation | Description | Example |
|-----------|-------------|---------|
| **MERGE** | Combine split text elements | "Sub" + "mit" → "Submit" |
| **SPLIT** | Separate merged elements | "1 2 3 4" → 4 buttons |
| **RETYPE** | Change element type | text → button |
| **DELETE** | Remove noise/duplicates | Remove artifacts |
| **SET_ROLE** | Add semantic role | "submit_button" |

### LLM Prompt Design

```python
# The LLM receives a structured prompt:
"""
## DETECTED ELEMENTS:
E1: button "Submit" [center, medium]
E2: text "Username" [left-top, small]
E3: input_field [center, medium] (in E5)
...

## YOUR TASK:
Output a JSON array of edit operations:
- MERGE: {"op": "merge", "ids": ["E1", "E2"], "text": "combined"}
- SPLIT: {"op": "split", "id": "E7", "into": ["4", "5"]}
- RETYPE: {"op": "retype", "id": "E5", "type": "button"}
- DELETE: {"op": "delete", "id": "E10"}
- ROLE: {"op": "role", "id": "E3", "role": "submit_button"}

## OUTPUT:
[{"op": "retype", "id": "E5", "type": "button"}]
"""
```

### Usage Examples

#### Basic Pipeline (No LLM)

```python
from visual_dom.cv.pipeline import VisualDOMPipeline
from visual_dom.hierarchy.coarse_builder import CoarseHierarchyBuilder
from visual_dom.compiler.dom_compiler import DOMCompiler

# Step 1: CV Detection
pipeline = VisualDOMPipeline(use_gpu=True)
result = pipeline.process("screenshot.png")
elements = result["elements"]

# Step 2: Build Coarse Hierarchy
builder = CoarseHierarchyBuilder()
hierarchy_result = builder.build(elements)
hierarchy = hierarchy_result.get("root")

# Step 3: Compile DOM
compiler = DOMCompiler(generate_locators=True)
dom = compiler.compile(elements, hierarchy, result["image_size"])

# Save output
compiler.save("output.json")
```

#### With LLM Refinement

```python
from visual_dom.cv.pipeline import VisualDOMPipeline
from visual_dom.hierarchy.coarse_builder import CoarseHierarchyBuilder
from visual_dom.hierarchy.llm_refiner import LLMHierarchyRefiner
from visual_dom.compiler.dom_compiler import DOMCompiler

# Step 1: CV Detection
pipeline = VisualDOMPipeline(use_gpu=True)
result = pipeline.process("screenshot.png")
elements = result["elements"]

# Step 2: Build Coarse Hierarchy
builder = CoarseHierarchyBuilder()
hierarchy_result = builder.build(elements)

# Step 3: LLM Refinement (Optional)
refiner = LLMHierarchyRefiner(
    model_name="ollama",  # or "qwen2.5-3b", "openai"
    use_gpu=True,
    temperature=0.1,
)
refinement = refiner.refine(
    elements=elements,
    hierarchy=hierarchy_result.get("root"),
    image_size=(result["image_size"]["width"], result["image_size"]["height"])
)

# Use refined elements
refined_elements = refinement["refined_elements"]
print(f"Applied {len(refinement['edits'])} edits")

# Step 4: Compile DOM with refined elements
compiler = DOMCompiler(generate_locators=True)
dom = compiler.compile(refined_elements, hierarchy_result.get("root"), result["image_size"])
```

### Current Integration Status

| Component | Status | Location |
|-----------|--------|----------|
| CV Pipeline | **Integrated** | `src/visual_dom/cv/pipeline.py` |
| Coarse Hierarchy | **Integrated** | `src/visual_dom/hierarchy/coarse_builder.py` |
| DOM Compiler | **Integrated** | `src/visual_dom/compiler/dom_compiler.py` |
| **LLM Refiner** | **Implemented, NOT integrated** | `src/visual_dom/hierarchy/llm_refiner.py` |

The viewer currently uses:
```
Screenshot → CV Pipeline → CoarseHierarchyBuilder → DOMCompiler → DOM JSON
```

LLM refinement is **available for programmatic use** but **not integrated into the viewer GUI** yet.

## Consequences

### Positive

- **Modular design**: Each stage can be used independently
- **Flexible LLM support**: Multiple backends (local and cloud)
- **No LLM required**: System works without LLM (rule-based only)
- **Improved accuracy**: LLM can fix common CV detection errors
- **Semantic understanding**: LLM adds contextual knowledge

### Negative

- **LLM latency**: Adds 1-5 seconds per image (depending on model)
- **Model requirements**: Local LLMs need 4-8GB GPU memory
- **API costs**: Cloud LLMs have per-token costs
- **Non-deterministic**: LLM outputs may vary

### Neutral

- LLM refinement is optional and can be enabled per-analysis
- Rule-based hierarchy is always available as fallback
- LLM edits are logged for debugging

## Alternatives Considered

### 1. LLM-Only Hierarchy Building (Rejected)

Use LLM to build hierarchy from scratch without rule-based stage.

Rejected because:
- Much slower (LLM processes all elements)
- More expensive (more tokens)
- Less reliable (LLM may miss spatial relationships)

### 2. Vision-Language Model (VLM) for Detection (Deferred)

Use VLMs like GPT-4V or Florence-2 for element detection.

Deferred because:
- Higher latency than CV-only approach
- Higher cost for cloud APIs
- Research ongoing in `research/` folder

### 3. Fine-tuned Detection Model (Deferred)

Train a custom model for UI element detection.

Deferred because:
- Requires labeled training data
- Significant development effort
- EasyOCR + UIED works well for MVP

## References

- Source: `src/visual_dom/cv/pipeline.py`
- Source: `src/visual_dom/hierarchy/coarse_builder.py`
- Source: `src/visual_dom/hierarchy/llm_refiner.py`
- Source: `src/visual_dom/compiler/dom_compiler.py`
- ADR-002: CV Pipeline Design (UIED + EasyOCR)
- ADR-004: DOM Compiler JSON Format
