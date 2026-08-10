# Brand assets

The VizDOM application icon is **drawn in code**, not stored as a bitmap:
[`tools/visual_dom_viewer/ui/branding.py`](../visual_dom_viewer/ui/branding.py)
is the single source of truth. The Viewer renders it at startup, so the app needs
no asset files to look right.

## The mark

A **locator reticle** (four corner brackets — find the element) around a **DOM
tree** (three connected nodes — the structure that comes out). Screenshot in,
structure out.

| | |
|---|---|
| Tile gradient | `#22334F` → `#0E1626` |
| Reticle | `#F2F6FC` |
| Accent (nodes) | `#4FD1C5` |

Each size is drawn for that size rather than resampled from one master:

- **≥ 48 px** — the full three-node tree.
- **≤ 32 px** — one node instead of the tree (its connector legs would be
  shorter than a node is wide), geometry snapped to whole pixels with
  antialiasing off, and the reticle optically enlarged. An anti-aliased
  1.2-pixel bracket is a grey haze that reads as a plain frame.

## Regenerating the files

The generated files exist only for consumers that cannot call Python:

```bash
python tools/assets/make_app_icon.py            # write the files
python tools/assets/make_app_icon.py --preview  # plus a size sheet to eyeball
```

| Output | Used by |
|--------|---------|
| `tools/visual_dom_viewer/resources/vizdom.ico` | Windows shortcuts, `.exe` packaging |
| `tools/visual_dom_viewer/resources/vizdom-256.png` | Streamlit dashboard tab icon, slides, report |
| `docs/img/favicon.png` | the ProperDocs site (`properdocs.yml` → `theme.favicon`) |
| `tools/visual_dom_viewer/resources/vizdom-sizes.png` | `--preview` only: every size on one strip |

Only PyQt5 is required — already a Viewer dependency — so anyone can regenerate
the icon without installing extra tooling. The script asserts that Qt can read
back every size it wrote to the `.ico`, since an ICO Qt rejects is one Explorer
may also refuse.

## Changing the icon

Edit `branding.py`, then **re-run the generator** — the checked-in files do not
update themselves. Check the small sizes with `--preview` before committing: 16 px
is the size users actually see in the taskbar, and it is the one that breaks first.
