# Algorithms & Improvements

This page documents the algorithmic improvements made to the pipeline during the
project, in problem → approach → result form, with pointers to the code and to the
[configuration](CONFIGURATION.md) knobs each one exposes. Benchmark context lives in
[Evaluation](EVALUATION.md).

## 1. OmniParser element-type mapping (roles from text/icon)

**Problem.** OmniParser tags every detection only `text` or `icon`, so the DOM
carried no `button` / `input_field` / `checkbox` roles — element-type accuracy on
actionable controls was **0.09** (trivially correct only on icons), and role-based
test logic couldn't use its DOM.

**Approach (two stages).** A *first fix* inferred roles from interactivity +
geometry (entry-height boxes → input field; width/aspect for button-vs-icon). It
lifted actionable accuracy to 0.73 but **regressed icons to 0.00** — the geometry
rule reclassified small square glyphs as buttons/checkboxes — and checkboxes stayed
at 0.12, being geometrically identical to icons. The *current* mapping adds
OmniParser's **caption** as a third signal (captions naming "check"/"toggle"/
"radio"/"switch" mark a checkbox) and re-tunes the button/icon width boundary.
Thresholds are resolution-aware (referenced to 1080p).

**Result** (per-type accuracy, before → first fix → now): button 0.00→0.91→0.89,
input_field 0.00→0.99→0.99, checkbox 0.00→0.12→0.55, icon 1.00\*→0.00→0.89,
**actionable 0.09→0.73→0.87**. Full table + caveats in
[Evaluation](EVALUATION.md#improvement-omniparser-type-mapping-before--first-fix--now).

**Code / config.** `_infer_visual_type` in
`src/visual_dom/cv/detectors/omniparser_backend.py`; no user knobs (heuristic is
internal), but the backend itself is chosen via `detector.backend`.

## 2. `text` vs `label` semantics (literal read vs semantic name)

**Problem.** OmniParser's `content` field was stored as the element's `text`
regardless of source — but for icons that content is a **Florence-2 caption** (a
model's *prediction*, e.g. "Page" for a maximize `□`), not something read from
pixels. Captions are also unstable: two visually identical captures differing by
invisible re-encoding noise (≤7/255 per channel) flipped a caption from
"Maximize" to "Page". The DOM's `text` therefore mixed reliable OCR with
unreliable guesses, and `label` duplicated it.

**Approach.** Split the two channels end to end. `text` = **literal pixel read**
(OCR, or the symbol reader below); `label` = **semantic name** with priority
*associated nearby label > detection caption > own text*. Concretely: the
detection layer routes OmniParser `text`-items' content to `text` and `icon`-items'
captions to `label`; the hierarchy builder seeds its label slot from the detection
caption instead of overwriting it with own text.

**Result.** A close button reads `text='×'`, `label='Close'`; an unreadable glyph
has `text=None` and keeps its caption as a best-effort `label`. Test guidance:
locate text-bearing controls by `text=`, icon-only controls by `role=` + spatial
relations (captions remain hints, not stable ids).

**Code.** `Detection.label` in `cv/detectors/base.py`; routing in
`omniparser_backend._parse_content_list`; label seeding in
`hierarchy/coarse_builder._create_nodes`.

## 3. Symbol reading v2 (template matching)

**Problem.** Operator keys (`+ − = × ÷`) on keypads read wrongly: OCR returns
garbage on small glyphs, and the old rule-based symbol detector — projection
profiles over the whole button crop — failed on **every** real Calculator key and
false-fired `+` on the hollow maximize `□` (its edge rows *average* to a central
"cross"). Hand-tuned thresholds at real glyph sizes (8–20 px) are inherently
fragile: fixing one shape broke another.

**Approach.** Rewrite as **template matching on the tight glyph**:

1. upscale small regions (anti-aliased strokes dissolve at native size);
2. binarize, then crop to the glyph's own bounding box (scale-normalised);
3. reject hollow outline shapes structurally (edge-only strokes, empty centre);
4. Dice-match the canonicalised (32×32) glyph against **font-rendered templates**
   (Segoe UI / Arial / DejaVu) of `+ - = × ÷ ± . %`, accepting only a confident,
   unambiguous best (calibrated per-symbol thresholds, margin over runner-up).

The recognised set is one list in code — adding a symbol is adding a character.

**Result.** 14/15 on the real Calculator screenshot: `÷ × − + = .` all correct,
title-bar dash → `-`, close → `×`, maximize correctly rejected, digits/icons
correctly `None`. On the synthetic set the detector now fires 4× instead of 21×
on a sample image — the removed hits were false positives (the confidence gate
only accepts sure matches). Known miss: the Windows `±` key draws a diagonal
`⁺∕₋` composite that no template matches — it safely returns nothing rather than
something wrong. Symbol results feed `text` (they are literal pixel reads), so a
`+` key is clickable as `text="+"` even when its caption is noise.

**Second iteration — thick-glyph themes and canonical labels.** A larger capture
(402×625, thick rounded glyphs) broke the reader again: the binarization
*selected the wrong candidate* — an adaptive-threshold **ring artifact** (the
glyph appearing as a hole inside a blob) had the density closest to the selection
heuristic, so a fat `×` matched the filled-dot template (`'.'`) and `÷`/`−` matched
nothing. Fixes: (a) **evaluate every binarization candidate** (both Otsu
polarities + adaptive) through template matching and keep the best overall — ring
artifacts match nothing, the correct polarity wins by score; (b) a structural
gate for `.` (a decimal dot must be tiny relative to its key), killing the
fat-blob false positives class-wide; (c) **bold font templates** for thick-rendered
glyphs. Result: **20/20 across both themes** with zero regressions. Additionally,
a confident glyph read now sets a **canonical semantic label** (`÷`→"Divide",
`×`→"Multiply", `−`→"Minus") outside the title bar, replacing look-alike caption
noise ("Add"/"Close"/"Minimize" on operator keys) — while title-bar controls keep
their captions, where "Close"/"Minimize" are the correct names.

**Third iteration — structure first, templates as evidence.** Scaling the
evaluation up exposed that Dice scores *alone* cannot carry the decision. A
130-case labelled set — four real Windows 11 Calculator renderings (Scientific +
Standard layout, 100% + 125% display scaling, dark + light theme), every key
labelled including the ones that must be **rejected** — scored the v2 detector at
**51/130**. Two systematic failure modes:

- *Confident misreads*: canonicalised to 32×32, a word key ("mod", "exp", "ln"),
  a backspace ⌫ icon, or a digit becomes a bar-like smear that Dice-matches `-`
  or `=` above threshold. Nothing in a similarity score says "this is not even a
  symbol".
- *Degraded binarizations win*: the thin-bar shortcut returned score **1.0**, so
  any candidate binarization that lost structure (the dots of `÷`, the second
  bar of `=`) instantly beat every honest match from a better candidate —
  `÷`→`-` and `=`→`-` at some scales, correct at others.

The rewrite classifies by **connected-component structure** — `÷` must be a wide
bar with one dot above and one below, `=` exactly two stacked solid bars, `+` a
centred cross with empty corners, `×` ink living on both diagonals — with the
font templates demoted to supporting evidence where structure alone is loose.
Candidates are then ranked by **specificity**: a binarization that explains
*more* components wins (`÷` beats `-`), because degradation can only lose
structure, never invent it. A glyph fitting no structure is rejected — which is
what kills the word/icon/digit misreads. Two supporting fixes: a second
low-margin crop pass (a *tight* detector box loses its outer components to the
20% margin — a hamburger ☰ was reading as `-`), and a ☰ veto ranked above the
bar family. Result: **130/130**, plus on the synthetic dashboard the new
detector fixed three false positives *and* recovered two real `%` glyphs the old
one missed. The set is a permanent data-driven pytest
(`tests/unit/test_symbol_detector.py`); a failing new theme belongs in the
manifest, with the fix measured against all renderings at once.

**Known upstream artifact (future work).** Composite key glyphs can defeat OCR in
a *scale-dependent* way — at a narrow window width the `²√x` key's superscript
reads as a bare `2`, and the `±` key's `+/-` reads as `+` — and because those
elements then HAVE text, the symbol reader (which only runs on textless elements)
never gets to correct them. The result is a *duplicate-text* ambiguity
(`text=2`, `text=+` matching two keys). Mitigated today by fallback-chain
ambiguity arbitration (ADR-024 v1.1: the chain's `desc=` judges among the
matched candidates); a fuller fix would let a confident symbol/structure read
override a low-confidence single-character OCR fragment on key-sized elements.

**Code / config.** `src/visual_dom/core/domain/cvops/symbol_detector.py`;
pipeline stage 4c. Config: `symbols.enabled`, `symbols.min_score` (structure
decides; the threshold only vetoes low template agreement).

## 3b. OmniParser + OCR ensemble: prefer-external and split guards

**Problem (from a real-app comparison across four detector/OCR combinations).**
With `omniparser + easyocr`, (a) small status texts (*Active*, *Inactive*,
*Low Protection*, a username) vanished from the DOM even though plain
`uied + easyocr` read them fine, and (b) tile buttons whose caption is two words
("Check Now", "Software Center", "Send Log Logfiles") were split into two or
three half-buttons.

**Diagnosis.** (a) The ADR-016 ensemble *gap-filled* — it only added our
upscaling-OCR boxes where OmniParser had none. Where OmniParser's native OCR
produced a garbage read in a tiny box (`~ctive` for *Active*, `VGcJC` for
*UGCIHC*, 8 px tall), the ensemble kept the garbage and skipped our good read;
the 8 px boxes then died in the pipeline's minimum-size filter, deleting the
row entirely. (b) The rule-based splitter divides any control containing 2+
OCR boxes — correct for UIED's merged blobs, wrong for a single tile whose
caption has two words (EasyOCR emits word boxes; Tesseract emits one line box,
which is why the split only appeared with EasyOCR).

**Fix.** (a) The ensemble is now a **prefer-external union**: external boxes
*replace* overlapped OmniParser OCR boxes (overlap-over-smaller-box), instead of
being skipped — the external read is the higher-quality one by construction.
(b) The splitter now skips any control the detector marked as one interactable
(OmniParser's own segmentation is the better authority), and otherwise requires
a clear gap between texts (≥ 1.5× median text height) before splitting.
Additionally, a configured-but-missing OCR engine now **fails fast** with an
install hint instead of silently degrading the run (observed with `paddleocr`
absent). The probe originally guarded only `connect()` (ADR-020); the **Viewer's
analyze path now runs it too** — before a session directory is created — and a
*runtime* OCR death (engine present but failing mid-run) is recorded by the
pipeline in `stats["text_error"]` and surfaced by the Viewer as a warning
dialog, so a dead engine can no longer masquerade as a text-free screen
(`tests/unit/test_ocr_failfast.py`).

**Result** on the comparison screenshot: every previously missing status text
recovered with correct content; all tile buttons whole; bottom hyperlinks still
separate; calculator and synthetic benchmarks unchanged.

## 3c. OCR line assembly: height-scaled gaps (adjacent links no longer fuse)

**Problem.** In the IWT quick-links row, three distinct links — *Printer
Management >*, *Docupedia >*, *My IT Profile >* — came back as **one** 295 px
text element (session `20260807_094630`, E71). A fused element is unclickable by
construction: no locator can address one link inside it, and nothing downstream
can undo the fusion because the fragments no longer exist.

**Diagnosis.** Initially parked as a smart-merge (Step 6c) defect; measurement
showed otherwise — the session contains **no** `source: "merge"` elements. The
fusion happens earlier, in the OCR adapter's own line assembly
(`TextDetector._merge_text_boxes`): raw EasyOCR returns the three links as
separate boxes, but the assembler chained any same-line boxes closer than a
**fixed 20 px**, and the gaps between these links are 13 px at 15 px text height.
The same rule also fused *IT Incidents > NG Portal >* and *IT Service Portal >
Add/Remove Software* in the same row. Because the ADR-016 ensemble feeds these
pre-merged boxes into OmniParser, the fused box then poisons the detector path
too.

**Fix.** The merge gap now **scales with the text height** (`0.45 ×` the shorter
box's height, floor 3 px) — an inter-word space is a fraction of the cap height,
so what counts as "one phrase" at 40 px headline size is two labels at 15 px body
size. Same-line membership requires **real vertical overlap** (≥ 0.5 of the
shorter box) instead of similar top edges. Assembly is two-pass — rows first,
then left-to-right within each row — which also fixed a latent ordering bug where
2 px of top-edge jitter made the single y-sort visit boxes out of x-order and
miss a genuine merge.

**Result** (all 125 saved sessions, OCR run once, both policies applied to the
same raw boxes): separator-spanning over-merges **104 → 8**, and each remaining 8
is a *correct* merge (browser tab bars, terminal paths whose `\` OCR reads as
`|`). The fix cuts false merges while *repairing more* true splits: on the dense
terminal screen `20260807_004113` the new policy assembles 233 raw boxes into 124
lines vs the old 162 — long paths now form one box, as they should. Covered by
`tests/unit/test_text_merge.py` (13 cases, pure geometry, engine-free).

**Follow-up (same investigation, next day).** Verifying on a fresh IWT capture
(session `20260810_160751`) surfaced two more defects, one of them exposed *by*
the fix:

- **Half-height tile.** The "Send Logfiles" tile came back cut at the
  icon/caption boundary (E13, h=64 of 119). With correct OCR (icon glyph `LoG`
  above, caption below), Step 4b's text-split saw a vertical text arrangement in
  the tile and cut it — the §3b guard ("never split what the detector marked as
  ONE interactable") checked only the element's *own* flag, but the box being
  split was a `rescan` copy (`interactable=None`) of OmniParser's
  `interactable=True` tile at near-identical bounds. Under the old OCR the same
  splitter *also* fired (horizontally, into three full-height slivers) and
  smart-merge glued the slivers back — the old "correct" tile was two bugs
  cancelling out, with the reversed label `Logfiles Send` as the tell. Fixed by
  extending the guard to **coincident copies**: an element whose box matches a
  detector-marked interactable (IoU ≥ 0.8) is never split
  (`tests/unit/test_text_split.py`).
- **Row drift.** Row membership was judged against the *last member appended*,
  so a tall box dragged the row downward until it swallowed the next line: on
  the same screen, `Application Control` (h=17) bridged to `(BlackList)` one
  line below, which then sat between `Low` and `Protection` in x-order and broke
  the status text into two labels. Membership is now judged against the **row's
  running band** (mean y1..y2 of members).

After both: the tile is whole (h=119, correctly labelled `Send Logfiles`),
`Low Protection` is one element again, the corpus numbers above are unchanged,
and the calculator demo screen is byte-identical.

**Code / config.** `_merge_text_boxes` in
`src/visual_dom/adapters/outbound/ocr/text_detector.py`; the coincidence guard
in `_split_by_text_positions` (`src/visual_dom/core/domain/pipeline.py`);
thresholds are method parameters (class defaults `GAP_HEIGHT_RATIO = 0.45`,
`MIN_GAP_PX = 3`, `LINE_OVERLAP_MIN = 0.5`), not yet config-file knobs.

## 3d. Real confidence scores (1.0 was a default, not a measurement)

**Problem.** Every OmniParser element reported `confidence: 1.0` (69 of 86 in a
typical session), and the rest were round constants (0.5–0.8). The Confidence
column was provenance masquerading as certainty: 1.0 meant "came from
OmniParser", 0.6 meant "the UIED checkbox heuristic fired".

**Diagnosis.** OmniParser computes real YOLO confidences (`predict_yolo`
returns logits) but drops them before building its box dicts, so our backend's
`item.get("confidence", 1.0)` always took the fallback. Genuine OCR confidences
were *also* lost: ensemble text boxes round-trip through OmniParser's
`ocr_bbox`/`ocr_text` lists, which have no confidence channel. Only Step-1 text
elements that bypassed the ensemble kept a real score.

**Fix — recover at the boundaries, entirely in our code** (the OmniParser repo
is vendored outside git, so patching it would not survive a re-clone):

- `predict_yolo` is wrapped at import (`_install_yolo_recorder`) to record
  (boxes, logits) into a per-thread slot; the ensemble provider now passes
  `(bbox, text, confidence)` 3-tuples (2-tuples still accepted). After
  `get_som_labeled_img` returns, `_parse_content_list` matches each parsed item
  back to its source box by IoU (≥ 0.5) and restores the real score. An
  unmatched item keeps 1.0, which now means "score unknown".
- **Behaviour is deliberately unchanged.** Raw logits (0.05–0.5 for icons) are
  not on the same scale as the heuristic constants, so: (a) the pipeline's
  generic confidence gate (default 0.3) exempts detector-backend elements — the
  backend already applied its own `box_threshold`, deliberately as low as 0.03
  to keep faint controls; (b) ranking in NMS / dedup / top-N uses
  `_ranking_confidence`, which still treats OmniParser elements as 1.0, so
  which box survives a conflict is decided exactly as before; (c) merging OCR
  text into a detector element no longer rewrites its `source` — that rewrite
  cost the exemption and deleted the calculator's DEG/MR buttons (logits ~0.29)
  during verification.

**Result.** IWT screen: 6 distinct confidence values → 61, with 9 (not 69)
elements at 1.0. Calculator: 1 distinct value → 48, and the element set
(bounds + type + text) **byte-identical** to before. UIED's constants remain
constants — they encode which rule fired and would need real calibration to
mean more.

**Code.** `omniparser_backend.py` (`_install_yolo_recorder`,
`_apply_ocr_provider`, `_parse_content_list`), `pipeline.py`
(`_ranking_confidence`, filter exemption); `tests/unit/test_confidence.py`.

## 4. Detection-threshold sensitivity (faint small controls)

**Problem.** A minimize "–" button detected in one capture vanished in another of
the *same* UI: the captures differed by 23 px of height, and OmniParser's YOLO
(fixed 1280×800 input) scored the faint dash just **under** its default 0.05
confidence cutoff at the new scale.

**Approach & result.** Sweeping the cutoff showed 0.03 recovers the control
cleanly (+2 legitimate detections; 0.01 admits noise). Exposed as
`detector.omniparser_box_threshold` (default unchanged at 0.05) and the
`OMNIPARSER_BOX_THRESHOLD` env var for the Viewer.

## 5. Session provenance (which application was analyzed)

**Problem.** Every Viewer run saves a session folder (screenshot, raw detections,
compiled DOM, stats), but nothing recorded *which application* it came from —
comparing sessions across different apps became guesswork.

**Approach & result.** Identifying the target is a **capture-port concern**, not a
caller's: `CaptureStrategy.describe_target()` (optional override, returns `{}` by
default and never raises) lets each strategy name its own target, so provenance is
platform-agnostic at the call site:

| Strategy | What it reports | Confidence |
|---|---|---|
| `windows` | foreground window title + process, **skipping our own process** by walking the Z-order (a full-screen grab is taken while the Viewer itself is foreground) | authoritative |
| `linux` | active window title via `xdotool`, else `xprop` (X11; Wayland exposes nothing to unprivileged clients) | authoritative on X11 |
| `android` | the **resumed activity** (`package/.Activity`) via `adb shell dumpsys activity` — Android's exact equivalent of a window title | authoritative |
| `camera` | only the capture device: a camera photographs an *external* display, so no OS metadata exists | none (`target_hint`) |
| `grpc` | the remote endpoint (naming the app on that host would need a provenance field in the capture RPC — future work) | endpoint only |

`session_info.json` merges whatever the strategy reports plus `capture_source`;
the window-handler path uses its connected target instead (precise), and opening
an image records `file:<name>` + `source_path`. Inferred values must carry
`guess_source` (e.g. `ocr`, `vlm`) so a guess is never mistaken for a fact. The
dashboard's session cards show the app name and detector. Older sessions simply
lack the fields.

**Camera naming (open question).** For camera capture there is nothing to query.
Options, cheapest first: (1) take the title text from the analysed DOM's top strip
— free, deterministic, but fails on full-screen/kiosk HMIs with no title bar;
(2) an operator-supplied **session label** in the Viewer — most reliable, since
the person aiming the camera knows what it is pointed at; (3) an opt-in **VLM
guess** ("which application is this?") using the existing vision backend — useful
where no title text exists, but it will confidently mislabel look-alike screens,
so it must be stored as a guess with the model recorded. Recommended: (2) as the
default with (1) prefilling it, and (3) strictly opt-in.

## 6. Application targeting and focus (the SUT must be the window we see)

**Problem.** VizDOM grabs the **whole screen** and actuates by **absolute
coordinate**, so both are silently wrong whenever the application under test is not
in front: `capture()` photographs whatever is on top (a DOM of the wrong app), while
`tap()` clicks whatever window is at that point and `type_text()` goes to whatever
holds *keyboard focus* (input delivered to the wrong app). Nothing in the DOM can
detect it — the coordinates were correct for that screenshot, and the screenshot was
correct for its moment. The project had already hit this twice: the Viewer hides
itself before grabbing and carries a hardened Win32 `bring_to_front()`, and
`describe_target()` walks the Z-order *past our own process* precisely because "the
foreground window" and "the SUT" routinely differ.

**Approach & result (ADR-021).** Promote the Viewer's proven implementation to an
optional `focus_target(title) -> bool` on **both** driven ports — the same
optional-hook pattern as `describe_target()`, so no plugin is forced to implement it:

| Strategy | Mechanism | Verifies by |
|---|---|---|
| `windows` capture / `desktop` actuator (Win32) | `SW_RESTORE` → `AttachThreadInput` → synthetic Alt tap → temporary `HWND_TOPMOST` | `GetForegroundWindow()` after a settle delay |
| `linux` / `desktop` (X11) | `wmctrl -a`, then `xdotool windowactivate --sync` | active window title |
| `android` (both ports) | `am start -n pkg/.Activity` (or the `monkey` launcher intent) | the resumed activity |
| `camera` | — (observes an external display it cannot control) | always `False` |
| `grpc` (both ports) | a new **`Focus` RPC**, run server-side | the server's own verification |

Two decisions carry most of the value. First, **verify instead of assume**: the
original code returned `True` whenever it had not thrown, which cannot distinguish
"raised" from "the OS refused" — exactly the case that yields a wrong screenshot.
Second, **focus crosses the wire as its own RPC**, because a window can only be
raised on the machine that owns the screen; without it the feature would be missing
from the one configuration the reference demo uses (capture *and* actuator over
gRPC). Ambiguity fails loudly: a title matching several windows logs the candidates
and returns `False` rather than driving a coin-flip window.

Exposed as an explicit `Bring App To Front  [title]` keyword (fatal on failure,
`required=${False}` to soften) **and** an opt-in `capture.focus_before_capture` flag
that raises `capture.window_title` before every grab, including the ADR-023 recap
(warn-only there — the grab may still be usable and one transient foreground lock
should not abort a suite). Off by default, because raising a window is an *action*:
it can dismiss tooltips and transient popups.

**Verified** on Windows: focus from both ports, through both the in-process and gRPC
paths, plus the negative cases (missing window, ambiguous title, no title
configured, camera) — each returning `False` with a reason rather than a false
positive.

### 6b. Capturing the window, not the screen — and the coordinate space it implies

Focusing makes the SUT *visible*; it does not stop the DOM from containing every other
window. A capture of a dual-monitor desktop produced 131–200 elements where the
application itself has ~50, and a full-screen grab of the *primary* monitor did not
even contain an application sitting on the secondary one. So the capture port gained
`capture_window(title)`, returning the window's client area — and, over gRPC, cropping
**on the machine that owns the screen** (`GrabRequest.window_title`), since only that
machine knows where the window is and a separate "give me the rectangle" call would
race a moving window.

The interesting part is not the cropping but what it forces you to be honest about.
Actuators take **normalized [0,1]** coordinates over the device's space, so a DOM
built from a 402×658 crop and mapped back against a 1920×1080 screen puts every click
in the wrong place. `CaptureFrame` therefore carries the pixels *and* the geometry
(`origin`, `device_origin`, `device_size`), and three separate defects had to be fixed
before a click computed on a crop reliably landed on its button:

| Defect | Symptom | Resolution |
|---|---|---|
| Capture normalized against the **monitor**, actuator against the **desktop** | a click meant for x = −710 on the second display landed at x = +499 on the primary | both ports derive the space from one helper: the **virtual desktop** |
| A **full-screen** grab carried no geometry | once the actuator spanned the desktop, the centre of a primary-monitor grab (0.5) mapped to x = 0 — the boundary between displays | `frame_geometry()`: a strategy states where its plain frames sit; `None` keeps the proportional image-space mapping, which is correct for Android |
| **DPI awareness** is process-global and first-come-first-served | `import pyautogui` calls `SetProcessDPIAware()`; `GetSystemMetrics` then reported the desktop as 4320×1350 instead of 3840×1080, and clicks were ~330 px off | claim per-monitor-v2 awareness **before** importing pyautogui, and read the desktop from the display driver (`EnumDisplaySettings`), which is awareness-independent |

The third is the nastiest: with per-monitor scaling the distortion is **not uniform**
(×1.125 in x, ×1.25 in y on the test machine), so it cannot be undone by a single
factor after the fact. When a foreign import wins the race anyway, the mismatch is
detected and reported with the remedy instead of silently misplacing clicks.

**Verified** end-to-end on a dual-monitor machine with *mixed* scaling (primary 125%,
secondary 100%): a Robot Framework suite drove the Windows Calculator through the
**capture service** with `window_scope`, producing a 53-element Calculator-only DOM
(`image_size` 402×658, not 1920×1080) and clicking `7` then `8` on a window at
**negative** screen coordinates — the display read `78`. The full-screen path
round-trips exactly (960, 540) → (960, 540) and is unchanged for single-monitor users.

**Found while testing** (unrelated to this feature, fixed): the in-process pipeline
computed the project root with one `../` too few after the ADR-014 restructure, so
`backend: "omniparser"` never found its weights and **silently degraded to
OCR-text-only** — the exact trap its own comment warned about. The service had its own
correct copy, which is why only in-process runs were affected.

## Which knobs are configurable — and why not all of them

The [session config](CONFIGURATION.md) deliberately exposes the tunables a user
can *reason about from symptoms* — detector choice and confidence, merge/dedup
IoUs, hierarchy containment, symbol strictness, size filters. Internal calibration
constants (per-symbol Dice values, geometry boundaries inside the type mapping,
binarisation parameters) stay in code: they were fitted together, changing one in
isolation mostly breaks the others, and exposing them would turn the config into
an untestable surface. Rule of thumb: **a knob goes in the config when a wrong
result tells you which way to turn it.**
