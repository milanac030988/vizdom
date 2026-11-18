# VizDOM Datasets

This directory holds the datasets used to develop and evaluate VizDOM. Only the
**labelled synthetic benchmark** (`synthetic/`, ~42 MB) is tracked in git; the
large derived sets are reconstructable and are **not** committed (see
`.gitignore`). Use the download / regeneration steps below to obtain them.

## `synthetic/` — labelled benchmark (tracked)

Programmatically generated UI screenshots at **1920×1080** with **exact ground
truth**, used for every number in the [Evaluation](../docs/EVALUATION.md) page.

| Split | Images | Path |
|---|---|---|
| train | 167 | `synthetic/train/{images,labels}` |
| test | 44 | `synthetic/test/{images,labels}` |
| yolo | (mirror) | `synthetic/yolo/` — same data in YOLO txt format |

**Label format** — one JSON per image (same schema as VizDOM output), e.g.:

```json
{
  "image_size": {"width": 1920, "height": 1080},
  "elements": [
    {"id": "E1", "bounds": [0, 0, 1920, 79], "visual_type": "block",
     "confidence": 1.0, "children_ids": ["E3", "E7"]},
    {"id": "E3", "bounds": [24, 20, 180, 60], "visual_type": "button",
     "text": "File", "confidence": 1.0}
  ]
}
```

`visual_type` ∈ `{button, text, input_field, checkbox, icon, container, block}`;
`bounds` is `[x1, y1, x2, y2]`; containment is encoded via `children_ids`.
`manifest.json` lists the split membership.

**Regenerate from scratch** (deterministic):

```bash
python scripts/data_prep/generate_synthetic_dataset.py
```

## Derived sets (not tracked — reconstruct on demand)

| Set | Size | How to reconstruct |
|---|---|---|
| `synthetic_camera/` | ~582 MB | `python scripts/data_prep/augment_camera.py` (perspective/glare/noise augmentation simulating a screen seen through a camera) |
| `synthetic_claude/`, `synthetic_llm/` | small | `python scripts/data_prep/generate_with_claude.py` |

## One layout for every benchmark set

The lifecycle benchmark reads the same layout whatever the screens are, so a
new source only needs to be brought into it once:

```
<root>/images/<app>__<state>.png
<root>/labels/<app>__<state>.json     # the label format above
```

`<app>` groups the screens of one application: same-application negatives are
drawn inside it. Three sources write this layout today:

| Source | Truth comes from | Tool |
|---|---|---|
| synthetic screens | the generator | `scripts/data_prep/generate_synthetic_dataset.py` |
| real desktop applications (`realworld/`, `realworld-heldout/`) | the Windows UI Automation tree | `python -m visual_dom.evaluation.lifecycle.harvest capture` |
| screens labelled by hand in Label Studio | the annotator's boxes | `python -m visual_dom.evaluation.lifecycle.labelstudio convert` |

Beyond the base format a label file may carry `all_names` (every caption the
screen shows, so a negative is never drawn from one), and per element
`ocr_text` (the caption), `role_word`, `parent_id` / `children_ids`, `review`
(a note for the human pass) and, for imported sets, `origin` and `ls_label`.

### Importing a Label Studio export

```bash
python -m visual_dom.evaluation.lifecycle.labelstudio convert \
    --exports <export dir> [<export dir> ...] --images <picture dir> \
    --out <root> [--ocr] [--origins manual prediction-changed]
python -m visual_dom.evaluation.lifecycle.generate --labels <root>/labels \
    --images <root>/images --negatives same-app --dedupe-app \
    --benchmark <name> --out <root>/steps.json
python -m visual_dom.evaluation.lifecycle.harvest review --root <root> --steps <root>/steps.json
```

The converter reads both export shapes (a task list, and one annotation per
file), keeps the most recent annotation of each picture, maps the classes onto
`visual_type`, builds the containment tree and writes `<root>/index.json` with
what was kept, dropped and missing. Three things to know before using such a
set for a number:

- **Who drew the box.** Each element keeps Label Studio's `origin`: `manual`,
  `prediction` (a model's proposal the annotator left as it was) or
  `prediction-changed`. Do not score a detector against proposals of a related
  detector; `--origins manual prediction-changed` keeps only what a person
  drew or moved.
- **Captions are not in the export.** `--ocr` proposes one per text box with
  Tesseract and marks it `caption_source: "ocr"`. The pipeline can use the same
  engine, so review the captions on the review sheet before reporting click or
  verify results on them. Icons get no caption.
- **Classes outside the format** (separator lines, scroll bars, progress bars)
  are left out and counted in the index; a `selected` marker becomes a flag on
  the element under it.

Keep a set that is not yours to publish outside git (`.gitignore`), as its
`<root>` can live anywhere.

## Download the published dataset

The **full dataset** — `synthetic/`, `synthetic_camera/`, `synthetic_claude/`,
`synthetic_llm/` (~654 MB, ~564 MB compressed) — is published on **Zenodo**
(citable DOI, archival). Download and unpack it into this directory:

```bash
python scripts/data_prep/download_data.py \
    --url "https://zenodo.org/records/<RECORD_ID>/files/vizdom-data.zip?download=1"
```

<!-- After publishing, replace <RECORD_ID> above and add the DOI badge/citation below. -->
- **DOI:** `10.5281/zenodo.<RECORD_ID>` *(fill in after publishing)*
- The archive holds top-level `synthetic/`, `synthetic_camera/`,
  `synthetic_claude/`, `synthetic_llm/` folders and unpacks straight into `data/`.
  (`synthetic_camera/` etc. are **not** in git — this is the only download that
  restores them without regenerating.)

> **How to publish (maintainer, ~10 min incl. upload).**
> 1. Sign in at <https://zenodo.org> (ORCID or GitHub login works).
> 2. **New upload** → drag in `vizdom-data.zip` (the full dataset, ~564 MB —
>    Zenodo allows up to 50 GB/record).
> 3. Fill metadata: *Title* "VizDOM GUI Dataset (synthetic + camera-augmented)",
>    *Type* Dataset, *Authors*, *License* (match the project), *Description* (copy
>    the sections above). Optionally link the GitHub repo.
> 4. **Publish** → Zenodo mints a DOI. Copy the file's download URL and the DOI
>    into this file (the two placeholders above).
>
> A **Reserve DOI** button lets you cite the DOI in the report *before* publishing.
> If you prefer a lighter download for evaluation-only users, you can additionally
> attach a `vizdom-synthetic.zip` (the 42 MB labelled benchmark) as a second file.

## License & citation

The synthetic images are generated by this project's own code and carry the
project license. If you use this benchmark, please cite the VizDOM project
(<https://github.com/milanac030988/vizdom>).
