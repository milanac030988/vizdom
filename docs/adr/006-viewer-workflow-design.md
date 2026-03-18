# ADR-006: Visual DOM Viewer Workflow Design

## Status

Accepted

## Date

2025-01-26

## Author

Development Team

## Reviewer

- Project Lead

## History

| Date | Version | Description |
|------|---------|-------------|
| 2025-01-26 | 1.0 | Initial version |

## Context

The Visual DOM Viewer is a PyQt5-based GUI application that allows users to:

1. Connect to target applications
2. Capture screenshots
3. Analyze with Visual DOM pipeline
4. Explore and select elements
5. Define elements for export
6. Export to Robot Framework

The original design had separate buttons for "Capture Screen", "Analyze", and "Explore Mode" which was confusing. Users expected a simpler workflow.

## Decision

Redesign the viewer workflow around a **Connect → Capture & Analyze → Define → Export** flow.

### New Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                      VIEWER WORKFLOW                         │
└─────────────────────────────────────────────────────────────┘

Step 1: Connect
┌─────────────────────────────────────────────────────────────┐
│  [Connect] → Dialog opens                                    │
│    ├─ Select Platform (Windows/Android/...)                 │
│    ├─ See list of available targets                         │
│    └─ Select target → [Connect]                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 2: Capture & Analyze
┌─────────────────────────────────────────────────────────────┐
│  [Capture & Analyze] (F5)                                    │
│    ├─ Minimize viewer                                        │
│    ├─ Bring target to front                                  │
│    ├─ Capture screenshot                                     │
│    ├─ Run CV pipeline (OCR + UIED)                          │
│    ├─ Build hierarchy                                        │
│    ├─ Compile DOM with locators                             │
│    └─ Display results in viewer                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 3: Explore & Define
┌─────────────────────────────────────────────────────────────┐
│  Explore Mode (enabled by default)                           │
│    ├─ Hover over screenshot → highlight elements            │
│    ├─ Click element → select it                             │
│    ├─ View properties in right panel                        │
│    ├─ Name element → [Add to Export List]                   │
│    └─ Repeat for all needed elements                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 4: Export
┌─────────────────────────────────────────────────────────────┐
│  [Export to Robot] (Ctrl+E)                                  │
│    ├─ Generate .resource file                               │
│    └─ Contains locators for all defined elements            │
└─────────────────────────────────────────────────────────────┘
```

### Toolbar Actions

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Connect] [Disconnect] │ [Capture & Analyze] [Re-Analyze] │         │
│                        │                                   │         │
│ [Open Image] [Open DOM] │ [Explore Mode ✓] [Zoom+] [Zoom-] │ [Export]│
└──────────────────────────────────────────────────────────────────────┘
```

| Button | Shortcut | Description |
|--------|----------|-------------|
| Connect | Ctrl+N | Open platform/target selection dialog |
| Disconnect | - | Disconnect from current target |
| Capture & Analyze | F5 | Capture screenshot and run full pipeline |
| Re-Analyze | F6 | Re-analyze current screenshot with new settings |
| Open Image | Ctrl+O | Load screenshot from file (offline mode) |
| Open DOM | - | Load existing DOM JSON (offline mode) |
| Explore Mode | - | Toggle element selection mode |
| Zoom +/- | Ctrl++/- | Zoom canvas |
| Export | Ctrl+E | Export to Robot Framework |

### Connect Dialog

```
┌────────────────────────────────────────────────────────────┐
│                   Connect to Target                         │
├────────────────────────────────────────────────────────────┤
│ Platform                                                    │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ [Windows ▼]                                             │ │
│ │ Windows desktop applications                            │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                             │
│ Target Application                                          │
│ ┌─────────────────────────────────────────┬──────────────┐ │
│ │ Calculator                               │ [Refresh]    │ │
│ │ Notepad                                  │              │ │
│ │ Visual Studio Code                       │              │ │
│ │ Chrome - Google                          │              │ │
│ └─────────────────────────────────────────┴──────────────┘ │
│                                                             │
│ Target Information                                          │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ Title: Calculator                                       │ │
│ │ Process: Calculator.exe                                 │ │
│ │ Size: 320 x 500                                         │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                             │
│                              [Connect]    [Cancel]          │
└────────────────────────────────────────────────────────────┘
```

### Status Bar

```
┌────────────────────────────────────────────────────────────────────┐
│ Ready                                    │ Connected: Calculator │ │
└────────────────────────────────────────────────────────────────────┘
```

Shows:
- Current operation status
- Progress bar during analysis
- Connection status

### Capture Process

```python
def _capture_and_analyze(self):
    # 1. Hide viewer to not interfere
    self.hide()
    time.sleep(0.3)

    # 2. Bring target window to front
    for _ in range(3):  # Multiple attempts
        handler.bring_to_front()
        time.sleep(0.3)

    # 3. Capture screenshot
    screenshot = manager.capture_screenshot()

    # 4. Restore viewer
    self.show()
    self.activateWindow()

    # 5. Run full pipeline
    pipeline = VisualDOMPipeline(...)
    result = pipeline.process(screenshot)

    hierarchy_builder = CoarseHierarchyBuilder()
    hierarchy = hierarchy_builder.build(result["elements"])

    compiler = DOMCompiler(generate_locators=True)
    dom = compiler.compile(elements, hierarchy, image_size)

    # 6. Display in viewer
    self._model.set_dom_tree(DOMTree.from_dict(dom))
```

## Consequences

### Positive

- **Intuitive workflow**: Linear flow matches user mental model
- **Single action capture**: One click for screenshot + analysis
- **Connection management**: Clear target selection
- **Offline support**: Can still load images/DOM files manually
- **Progress feedback**: Status bar shows what's happening

### Negative

- **Slower capture**: Must minimize viewer and restore (adds ~1 second)
- **Window focus issues**: Sometimes target doesn't come to front
- **No live mode**: Must manually trigger each capture

### Neutral

- Keyboard shortcuts match common conventions
- Connection state persisted until disconnect
- Can switch between live capture and offline modes

## Alternatives Considered

### 1. Separate Capture and Analyze Buttons (Rejected)

Keep original two-step process.

Rejected because:
- Users found it confusing
- Extra clicks for common workflow
- No clear use case for capture-only

### 2. Always-On-Top Viewer (Rejected)

Keep viewer visible during capture.

Rejected because:
- Viewer often covers target window
- Complicates screenshot (must exclude viewer)
- Platform-specific behavior issues

### 3. Transparent Overlay Mode (Deferred)

Show translucent viewer overlay on target.

Deferred because:
- Complex to implement cross-platform
- May interfere with user interactions
- Can add as enhancement later

## References

- PyQt5 documentation: https://www.riverbankcomputing.com/static/Docs/PyQt5/
- Source: `tools/visual_dom_viewer/ui/main_window.py`
- Source: `tools/visual_dom_viewer/ui/connect_dialog.py`
- Source: `tools/visual_dom_viewer/plugins/platform_manager.py`
