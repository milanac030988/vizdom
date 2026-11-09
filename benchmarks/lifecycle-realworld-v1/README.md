# lifecycle-realworld-v1 — real-application states

The synthetic set (`lifecycle-synthetic-v1`) is generated, which is the first
thing a reviewer will hold against it. This set is the same benchmark (same
step schema, same runner, same scoring) on screenshots of **real desktop
applications**, with two changes:

- **Ground truth from UI Automation.** `harvest.py` photographs a window and
  dumps its Windows UIA tree in the same moment; the tree is the answer key.
  The executors still see only the screenshot. The tree exists here because
  these are ordinary desktop applications, and is absent on the canvases,
  HMIs and camera feeds VizDOM is for — so this set measures VizDOM where its
  answer can be checked.
- **Same-app negatives.** Each state gets two negative verify steps whose
  captions exist on *another* screen of the same application but not on this
  one ("Export" where only "Import" is shown), instead of invented words. A
  step carries `negative_kind: same-app` (or `nonsense` when an application
  has too few other captions and the list is topped up).

## Protocol

1. **Pick applications.** Open-source or Windows built-ins only — no employer
   software without clearance. Aim for about 10 applications × 4–5 states
   (40–50 states, comparable to the synthetic 44), mixing toolkits: Win32
   (Notepad++, 7-Zip, KeePass), Qt (VLC, qBittorrent), WinUI (Settings,
   Calculator), Electron (VS Code), Java (a Swing app), dialogs as their own
   windows (Find/Replace, Options, Save As).
2. **Capture each state.** Put the window in the state, move the mouse off it,
   then

   ```
   python -m visual_dom.evaluation.lifecycle.harvest windows          # exact titles
   python -m visual_dom.evaluation.lifecycle.harvest capture --title "Notepad++" --app notepadpp --state main
   python -m visual_dom.evaluation.lifecycle.harvest capture --title "Replace" --app notepadpp --state replace-dialog
   ```

   The whole window is captured (title bar and Win32 menu bar included),
   clipped to the monitor's work area so the taskbar never enters a
   screenshot. The capture is refused when the window changed while its tree
   was read, and when most labelled boxes are blank on the screenshot - a page
   still loading has its full UIA tree before it is drawn (Windows Settings,
   2026-11-08; wait and use `--delay`). Look at every screenshot once: a modal (a first-run welcome or
   sign-in dialog) leaves the controls behind it in the tree, and those
   states must be recaptured with the modal dismissed.
   `--delay 5` gives time to open a menu by hand. Use ids
   `<app>__<state>`: the app part groups states for the negatives.
3. **Generate the steps.**

   ```
   python -m visual_dom.evaluation.lifecycle.generate --labels data/realworld/labels \
       --images data/realworld/images --negatives same-app --dedupe-app \
       --benchmark lifecycle-realworld-v1 --out benchmarks/lifecycle-realworld-v1/steps.json
   ```

   `--dedupe-app` keeps a click/verify step only on the first screen of its
   application with that caption and role: the pages of a settings dialog
   repeat their navigation tree, and counting each tree item once per page
   would overstate the independent steps (on the first 41 states: 845 click
   steps without, 429 with). Report both; the committed manifest is deduped.
   After changing the OCR reader, `harvest recheck` re-reads the demoted
   elements of the saved screenshots without recapturing.

4. **Review — required.** `python -m visual_dom.evaluation.lifecycle.harvest review`
   writes `data/realworld/review.html`: green boxes become steps, orange ones
   do not. Per state:
   - a green box whose caption is not printed inside it → set its
     `visual_type` to `"icon"` in the label JSON;
   - an orange box that prints a usable caption (Calculator's "Memory recall"
     key prints "MR") → set `visual_type` to `"button"` and `ocr_text` to the
     **printed** text;
   - each listed negative must be **absent from the screen** (also not inside
     an editor's content, which UIA does not name); if it is visible, add it to
     that state's `all_names` so it is never drawn.

   Regenerate the steps after edits; the generator is deterministic.
5. **Run** exactly as the synthetic set, with
   `--manifest benchmarks/lifecycle-realworld-v1/steps.json`.

## What the harvester does to a UIA tree

- keeps visible, on-screen, named elements inside the captured window;
- folds a child that repeats its ancestor's name (a Button's own Text) into
  the ancestor, or every label would count twice and fail the uniqueness rule;
- maps Button, MenuItem, TabItem, ListItem, TreeItem, Hyperlink → `button`
  (with `role_word` for the instruction: "click the 'File' menu item"),
  CheckBox / RadioButton → `checkbox`, Text → `text`;
- turns Edit / ComboBox into `block`: their UIA name is usually a label drawn
  beside the field, so a text step would aim at the wrong box;
- demotes to `icon` (no step) an actionable element that looks icon-only
  (small, roughly square, a name of three or more characters) or whose name
  Tesseract does not find printed inside its box. The OCR reading is stored as
  `printed`, shown on the review sheet, and only proposes: the reviewer
  decides.

## Results

998 steps over 46 states of 9 applications: 453 clicks, 545 verifications,
92 negatives (mostly same-app). False passes are counted over the 92
negatives. Every row names its host and commit; read a run with
`python -m visual_dom.evaluation.lifecycle.compare` (deploy/gpu/README.md).

| Column | Host, commit | Action-hit | Verify acc | False passes |
|---|---|---|---|---|
| `text=` vizdom-uied | laptop, `0fe5ce3` (2026-11-09) | 0.777 | 0.877 | 0 / 92 |
| `text=` vizdom-modular | laptop, `19f800d` (2026-11-09) | 0.795 | 0.879 | 0 / 92 |
| `desc=` lexical → slm (keyword verify) | laptop, `19f800d` (2026-11-09) | 0.792 | 0.826 | 0 / 92 |
| `desc=` lexical → slm, before ADR-022 1.9 | laptop (2026-11-02) | 0.645 | 0.798 | 6 / 92 |
| `desc=` lexical → slm + exact-name bonus and `id=` fix (1.11, 1.13; tuned on this set) | laptop, code of `48ad68d` (2026-11-09) | 0.834 | 0.881 | 0 / 92 |
| `text=` vizdom-uied | run 8, `0fe5ce3` | 0.779 | 0.877 | 0 / 92 |
| `text=` vizdom-omniparser | run 8, `0fe5ce3` | 0.808 | 0.883 | 0 / 92 |
| `text=` vizdom-modular | run 8, `0fe5ce3` | 0.797 | 0.879 | 0 / 92 |
| `desc=` lexical → slm (keyword verify) | run 8, `0fe5ce3` | 0.795 | 0.826 | 0 / 92 |
| `desc=` lexical → slm, `verify=chain` | run 8, `0fe5ce3` | 0.790 | 0.883 | 1 / 92 |
| `desc=` slm pinned | run 8, `0fe5ce3` | 0.494 | 0.732 | 10 / 92 |
| `desc=` vlm pinned (3B) | run 8, `0fe5ce3` | 0.108 | 0.655 | 35 / 92 |
| `desc=` lexical → vlm, 3B | run 8, `0fe5ce3` | 0.850 | 0.826 | 0 / 92 |
| `desc=` lexical → vlm, 7B | run 8, `0fe5ce3` | **0.861** | 0.826 | 0 / 92 |
| ELAM-7B | run 8, `0fe5ce3` | 0.857 | 0.833 | 91 / 92 |
| UI-TARS-1.5-7B | run 8, `0fe5ce3` | 0.821 | 0.903 | 53 / 92 |

Run 8 is `gpu-20261108_221541` (RTX PRO 5000 Blackwell 48 GB, Tesseract
5.3.4); every run-8 row ran on that one card. Laptop result files:
`benchmarks/results/realworld_local/20261109_051530` (uied), `_052030`
(modular), `_052807` (desc), local and not committed. The 1.9 fixes were
derived from this set, so the 2026-11-02 row is reported beside the fixed
one; applications captured after them are the held-out check
(`../lifecycle-realworld-heldout-v1`, see below). `19f800d`
differs from `0fe5ce3` only by the comparison tool, so laptop and run-8 rows
share one pipeline. The `id=` answer fix (ADR-022 1.11) came after run 8's
commit.

What the run shows:

- **Reproducible across hosts.** uied on the laptop and on the rental agree
  on 997 of 998 steps, modular on 981; desc= on 973 (the SLM is not
  deterministic across Ollama builds).
- **Only the lexical-first chains keep 0 false passes on real screens.**
  The grounders accept almost every same-app negative: ELAM-7B 91 of 92,
  UI-TARS 53 of 92. Their plain verify accuracy is therefore not comparable
  to the VizDOM rows: ELAM's 0.833 is mostly a "yes" to everything.
- **The 7B vision chain is level with the grounders on clicks** (0.861,
  ELAM 0.857, UI-TARS 0.821; paired McNemar p = 0.92 and 0.11) with no
  false pass; the 3B one is 0.850. Of the 998 steps, 7B is better on 11 and
  worse on 6 (p = 0.33, not significant). The production lexical → slm chain
  is significantly behind ELAM on clicks (0.795, p = 0.012) and level with
  UI-TARS (p = 0.35).
- **Balanced verify accuracy**, the mean of present → pass and absent →
  fail, is the fair verify figure here: production 0.895, `text=` 0.926-0.929,
  ELAM 0.505 (a coin flip: it passes all 453 present elements and 91 of 92
  absent ones), UI-TARS 0.712. On present elements alone the grounders are
  significantly better (production fails 95 of 453), on absent ones VizDOM
  is (p < 0.001 both ways). 0 false passes of 92 bounds the rate at 4.0 %
  (95 % Wilson upper limit).
- **Keyword verify stays the default.** `verify=chain` gains 33 verify steps
  and loses 4, and buys them with the set's only VizDOM false pass: the SLM
  took a "Tab Bar" element for the absent "Mark tab"
  (`notepadpp__prefs-editing`).
- **A tier alone is not a locator.** Pinned SLM 0.494 with 10 false passes;
  pinned qwen2.5vl:3b 0.108 with 35, and 242 of its steps ended on Ollama's
  token-repeat guard (the 3B looping already seen in run 6).
- **Per application** (`compare` prints the table): UI-TARS is best on
  VS Code (22/24) and Settings, worst on PuTTY (31/72); the VizDOM rows are
  weakest on VS Code (8-18 of 24), whose icon-only activity bar the text
  locator cannot name.
- **After the exact-name bonus** (laptop, `20261109_144106`) the CPU chain
  gains 18 clicks over run 8's production row and loses none: 0.834, level
  with ELAM (paired McNemar p = 0.38) and UI-TARS (p = 0.66), still 0 of 92
  false passes. The bonus was found on this set, so this row is tuned on it.
- **Held-out check** (2026-11-10, `../lifecycle-realworld-heldout-v1`, 14
  states of 5 applications not in this set, laptop): the same chain clicks
  0.815 (66/81, Wilson 0.72–0.88) and verifies 0.890, so the click and
  verify figures generalise; but it passed 1 of 28 negatives, a stop-word
  plus role-word match described in that README. Reported, not fixed. Across
  both sets: 1 of 120 for the chain, 0 of 120 for `text=`.

## Threats to state in the results

- **Selection bias towards readable text.** The printed check uses Tesseract,
  which is also one of VizDOM's OCR engines; elements it cannot read are
  dropped unless the reviewer restores them. Report how many were restored.
- **UIA coverage.** Owner-drawn controls (Win32 toolbars, canvases) expose no
  elements and simply have no steps — the set under-represents exactly the
  surfaces VizDOM targets; the synthetic and camera sets cover those. The
  yield per toolkit says so plainly: Win32 and Qt dialogs give 15–45 steps a
  screen, WinUI (Windows Settings) 2–5, because its toggles are named after
  a label drawn beside them and print only "On", and Paint.NET's custom
  controls 1–17.
- **One capture per state.** No variation in theme, scale or window size
  unless captured deliberately as separate states.

## Audit of this evidence (2026-11-09)

`python -m visual_dom.evaluation.lifecycle.audit` recomputes, from the run-8
files and with no model, how far the numbers above can be trusted; the full
tables are in [`AUDIT.md`](AUDIT.md) and the same audit of the synthetic set
in `../lifecycle-synthetic-v1/AUDIT.md`. What it found:

- **Steps are clustered; the conclusions survive it.** About twenty steps
  share a screen. Cluster-bootstrap intervals over the 46 screens are wider
  than Wilson (modular action-hit 0.797: [0.719, 0.861] against [0.757,
  0.831]; UI-TARS 0.821: [0.724, 0.913]). The false-pass comparisons, named
  as the primary ones, hold with the screen as the unit (p < 0.001) and with
  the application as the unit (p = 0.004, the smallest value nine
  applications allow). Every click comparison is non-significant after a
  Holm adjustment, including the one that was nominally significant (CPU
  chain against ELAM, McNemar 0.012, by screens 0.025, adjusted 0.15):
  "level with" is the claim, in both directions.
- **Zero false passes is zero on 46 screens of 9 applications**, which
  bounds the share of screens that would show one at 6.3 % (one-sided 95 %),
  a weaker and more honest statement than "0 of 92".
- **The 92 absent targets are absent.** Two OCR engines searched every
  negative caption on its own screenshot: one hit, "100%" read by Tesseract
  where a spin box shows 100 beside its arrows (Paint.NET, hue/saturation),
  which is no "100%" control. `data/realworld/negatives_review.html` is the
  contact sheet for a human pass.
- **A third of the actionable controls never became a step.** Of 1 415 named
  actionable UIA elements, 321 are icon-only and 131 have a name that is not
  printed (VS Code 72 % dropped, Windows Settings 70 %). The comparison is on
  captioned controls and says nothing about icon-only ones, where a grounder
  can act and a caption locator cannot.
- **The constants sit at an edge here, on a plateau on the synthetic set.**
  One constant moved at a time: floor 1.25 gives 1 false pass and 1.0 gives
  3; margin 0 gives 6; name weight 2.5, substring 1.0 or role 1.5 give 2
  each. Stricter values give none. On the synthetic set no value in the
  same ranges gives any. The shipped values were set by hand, two of them on
  this set, so screens the scorer has not seen are what would tell tuning
  from robustness.
- **Near-miss absent targets are passed, by both locators.** The benchmark's
  negatives never share a word sequence with a name on their screen
  (`_absent_here` leaves those out). Built separately, 168 real sibling
  captions of that kind ("Add" where only "Add to archive" is shown):
  `text=` passes 39 (it falls back from exact to substring match), `desc=`
  45. A stricter rule, the matched element must read exactly the caption,
  passes 1 and 0, and costs 13 points of present → pass (0.857 → 0.726); it
  is evaluated in the audit only and is not in the product. **The
  zero-false-pass result is therefore a result for absent targets that do
  not share words with a present caption**; for the others the locators are
  partial-match locators and behave as such.
