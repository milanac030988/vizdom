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

**Code / config.** `src/visual_dom/cv/symbol_detector.py`; pipeline stage 4c.
Config: `symbols.enabled`, `symbols.min_score` (null = calibrated ~0.70; raise =
stricter, lower = recover faint glyphs).

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
absent).

**Result** on the comparison screenshot: every previously missing status text
recovered with correct content; all tile buttons whole; bottom hyperlinks still
separate; calculator and synthetic benchmarks unchanged.

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

## Which knobs are configurable — and why not all of them

The [session config](CONFIGURATION.md) deliberately exposes the tunables a user
can *reason about from symptoms* — detector choice and confidence, merge/dedup
IoUs, hierarchy containment, symbol strictness, size filters. Internal calibration
constants (per-symbol Dice values, geometry boundaries inside the type mapping,
binarisation parameters) stay in code: they were fitted together, changing one in
isolation mostly breaks the others, and exposing them would turn the config into
an untestable surface. Rule of thumb: **a knob goes in the config when a wrong
result tells you which way to turn it.**
