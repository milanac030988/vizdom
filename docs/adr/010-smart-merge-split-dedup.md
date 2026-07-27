# ADR-010: Smart Merge, Text-Position Split, and Redundancy Removal

## Status

Accepted

## Date

2026-03-30

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-03-30 | 1.0 | Initial version |

## Context

The original CV pipeline had three critical issues:

1. **Text swallowing**: Large container elements (e.g., 980x479px panel) merged ALL contained OCR text into one giant string, destroying individual text elements
2. **Merged buttons**: Adjacent same-color buttons (e.g., "+", "-", "=") detected as one element by contour analysis
3. **Redundant overlapping elements**: Multiple detection passes (coarse, fine, special, rescan) produced overlapping duplicates

## Decision

### 1. Smart Merge (Step 4 rewrite)

Rewrote `_merge_text_and_elements()` with container-aware logic:

- **Container threshold**: Elements larger than `scaled(30000)` area or type `block` are treated as containers and **never** merge text into themselves
- **Smallest-first processing**: Sort UIED elements by area ascending, so small interactive elements (buttons, inputs) claim overlapping text before large containers
- **Text stays standalone**: Unclaimed text elements remain as separate items, preserving individual labels like "User Name", "IP Address"

**Before**: 1 block with text="User Name Client ClientType BCNC SCCM..."
**After**: 67 individual text elements + container block without text

### 2. Rule-Based Text-Position Split (Step 4b)

New `_split_by_text_positions()` method:

- For each non-text, non-block element: find contained OCR text regions
- If 2+ non-overlapping texts exist inside one element → split
- Determine horizontal vs vertical arrangement (x_spread vs y_spread)
- Split at midpoints between adjacent text positions
- Parent element becomes `block`, children inherit type

This catches merged buttons like `[12 | 26]` without needing SLM.

### 3. Priority-Based Cross-Type NMS (Step 5b rewrite)

Rewrote `_apply_cross_type_nms()` with explicit priority system:

```
Priority: (has_text, type_rank, confidence)
  - has_text: 1 if element has OCR text, 0 otherwise
  - type_rank: button/input=5, checkbox=4, icon/text=3, divider=2, block=1, unknown=0
```

- **IoU threshold lowered**: 0.5 → 0.4 (catches more overlapping pairs)
- **Containment threshold lowered**: 0.85 → 0.75
- **Parent-child preserved**: block containing specific type kept as both
- **Size ratio check**: elements with area ratio < 0.2 kept as parent-child

### 4. Near-Duplicate Removal (Step 6b, new)

New `_remove_duplicates()` method:

- **Position-based**: bounds within 5px on all sides → duplicate
- **Text-based**: same OCR text + IoU > 0.3 → duplicate
- Higher-priority element kept, text transferred if needed

Catches duplicates from coarse+fine+rescan detection passes.

## Consequences

### Positive
- CMST app: 1 merged element → 87 individual text elements
- Calculator: eliminated overlapping button pairs
- Text-position split works without SLM (fast, deterministic)
- Priority system ensures elements with text are never suppressed by textless overlaps

### Negative
- Container threshold (30000 area) is a heuristic — may need tuning for very small UIs
- Text-position split requires OCR to have detected individual text regions correctly

## Files Changed

- `src/visual_dom/cv/pipeline.py` — Rewrote `_merge_text_and_elements()`, `_apply_cross_type_nms()`, added `_split_by_text_positions()`, `_remove_duplicates()`
