# ADR-004: DOM Compiler and JSON Output Format

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

After CV detection and hierarchy building, we need to produce output that:

1. Is compatible with existing UI automation tools
2. Contains enough information for element locating
3. Supports multiple locator strategies
4. Is human-readable for debugging
5. Can be used by Robot Framework library

The output format should be similar to UIAutomator dumps but enriched with visual detection metadata.

## Decision

Implement a **DOM Compiler** that produces UIAutomator-compatible JSON with enhanced locator support.

### Output JSON Structure

```json
{
  "image_path": "screenshot.png",
  "image_size": {"width": 1920, "height": 1080},
  "cv_stats": {
    "text_detected": 45,
    "uied_detected": 120,
    "final_count": 89
  },
  "dom": {
    "version": "1.0",
    "image_size": [1920, 1080],
    "element_count": 89,
    "hierarchy": {
      "id": "ROOT",
      "bounds": [0, 0, 1920, 1080],
      "center": [960, 540],
      "role": "root",
      "visual_type": "container",
      "clickable": false,
      "editable": false,
      "scrollable": false,
      "confidence": 1.0,
      "children": [...]
    }
  }
}
```

### Element Structure

```json
{
  "id": "E42",
  "bounds": [100, 200, 250, 240],
  "center": [175, 220],
  "role": "button",
  "visual_type": "button",
  "text": "Submit",
  "clickable": true,
  "editable": false,
  "scrollable": false,
  "confidence": 0.85,
  "locators": {
    "id": "E42",
    "text": "Submit",
    "type_index": "button[3]",
    "bounds": "bounds(100,200,250,240)",
    "center": "point(175,220)"
  },
  "children": []
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique element identifier (E1, E2, ...) |
| `bounds` | [x1, y1, x2, y2] | Bounding box coordinates |
| `center` | [x, y] | Center point for clicking |
| `role` | string | Accessibility role (button, textField, etc.) |
| `visual_type` | string | Visual classification (button, icon, input_field) |
| `text` | string | Text content (from OCR) |
| `clickable` | boolean | Whether element is likely clickable |
| `editable` | boolean | Whether element accepts text input |
| `scrollable` | boolean | Whether element is scrollable |
| `confidence` | float | Detection confidence (0.0-1.0) |
| `locators` | object | Multiple locator strategies |
| `children` | array | Child elements |

### Locator Strategies

```python
locators = {
    # 1. ID locator (always unique)
    "id": "E42",

    # 2. Text locator (if has text)
    "text": "Submit",           # Unique text
    "text": "Submit[0]",        # Indexed if duplicate

    # 3. Type + index locator
    "type_index": "button[3]",  # 4th button on screen

    # 4. Bounds locator (always works)
    "bounds": "bounds(100,200,250,240)",

    # 5. Center point locator
    "center": "point(175,220)"
}
```

### Role Mapping

Visual types are mapped to accessibility roles:

```python
ROLE_MAPPING = {
    "button": "button",
    "text": "staticText",
    "input_field": "textField",
    "checkbox": "checkBox",
    "icon": "image",
    "container": "group",
    "block": "group",
    "divider": "separator",
}
```

### Compiler Implementation

```python
from visual_dom.compiler.dom_compiler import DOMCompiler

compiler = DOMCompiler(generate_locators=True)

dom_result = compiler.compile(
    elements=detected_elements,      # From CV pipeline
    hierarchy=hierarchy_tree,        # From hierarchy builder
    image_size=(1920, 1080),
)

# Save to file
compiler.save("output.json")

# Access elements
button = compiler.get_element_by_text("Submit")
all_buttons = compiler.get_elements_by_type("button")
clickables = compiler.get_clickable_elements()
```

## Consequences

### Positive

- **UIAutomator compatible**: Familiar format for mobile automation engineers
- **Multiple locators**: Flexibility in element identification
- **Human readable**: Easy to debug and inspect
- **Rich metadata**: Confidence scores, visual types, interaction flags
- **Hierarchical**: Preserves parent-child relationships

### Negative

- **File size**: JSON can be large for complex UIs (100-500KB typical)
- **Coordinate precision**: Bounds depend on CV detection accuracy
- **No dynamic IDs**: IDs are generated, not from actual UI

### Neutral

- Locator uniqueness depends on UI complexity
- Some elements may have multiple valid locators
- JSON format can be extended with custom fields

## Alternatives Considered

### 1. XML Format (Like UIAutomator) (Rejected)

Use XML instead of JSON.

Rejected because:
- JSON more widely used in Python ecosystem
- Easier to parse and manipulate
- Better tooling support

### 2. Flat Element List Only (Rejected)

Output only a flat list without hierarchy.

Rejected because:
- Loses structural information
- Harder to understand element relationships
- Cannot support tree-based locator strategies

### 3. Protocol Buffers (Deferred)

Use protobuf for more efficient serialization.

Deferred because:
- JSON sufficient for current needs
- Easier debugging with JSON
- Can add protobuf output later for performance

## References

- UIAutomator dump format reference
- JSON Schema: https://json-schema.org/
- Source: `src/visual_dom/compiler/dom_compiler.py`
- Source: `src/visual_dom/hierarchy/coarse_builder.py`
