# lifecycle-realworld-heldout-v1

Screens of applications that are **not** in `lifecycle-realworld-v1`,
captured after every constant of the description scorer was fixed
(`desc_resolver.py` at the commit of the capture). The scorer's floor, margin
and exact-name bonus were set by hand, two of them on the 46 screens of the
main set, and the audit shows the shipped values sit at the edge of that
set's zero (`../lifecycle-realworld-v1/AUDIT.md`, section 6). Only screens
the scorer has never seen can tell tuning from robustness. This set is that
check, and nothing may be tuned on it: a failure found here is reported, not
fixed, until the set is replaced.

`steps.json` is not in the repository until the screens are captured. The
sweep (`deploy/gpu/run9.sh`) runs the `ho-` columns when the file exists.

## Capture (Windows, about 30 minutes)

Same tool and same rules as the main set
(`../lifecycle-realworld-v1/README.md`), with its own data root. Ten to
fifteen states, at least two per application: the negatives of a screen are
captions of the other screens of its application.

Applications already used, so not allowed here: 7-Zip, Firefox, Notepad++,
paint.net, PuTTY, TeXstudio, TortoiseGit, VS Code, Windows Settings.

A set that needs no account and shows no personal data:

| App id | States | How to open |
|---|---|---|
| `notepad` | `main`, `find`, `settings` | Notepad with an empty document; Ctrl+F; the gear icon |
| `paint` | `main`, `resize`, `properties` | Paint with a blank canvas; Ctrl+W; Ctrl+E |
| `charmap` | `main`, `advanced` | `charmap`; tick "Advanced view" |
| `mouseprops` | `buttons`, `pointer-options`, `wheel` | `main.cpl`, one state per tab |
| `folderopts` | `general`, `view`, `search` | `control folders`, one state per tab |

```
set PYTHONPATH=src
python -m visual_dom.evaluation.lifecycle.harvest windows
python -m visual_dom.evaluation.lifecycle.harvest capture --root data/realworld-heldout --title "Notepad" --app notepad --state main
python -m visual_dom.evaluation.lifecycle.harvest capture --root data/realworld-heldout --title "Mouse Properties" --app mouseprops --state buttons
```

`--delay 5` gives time to open a menu or move the mouse away. One capture
per state; a refused capture says why (window changed, page not drawn yet).

Before anything is committed, look at every image in
`data/realworld-heldout/images`:

- no user name, e-mail address, host name, recent-file list or file path;
- no taskbar at the bottom edge, no other window showing through;
- no modal in front of the window that was meant.

## Generate and review

```
python -m visual_dom.evaluation.lifecycle.generate --labels data/realworld-heldout/labels ^
    --images data/realworld-heldout/images --negatives same-app --dedupe-app ^
    --benchmark lifecycle-realworld-heldout-v1 --out benchmarks/lifecycle-realworld-heldout-v1/steps.json
python -m visual_dom.evaluation.lifecycle.harvest review --root data/realworld-heldout ^
    --steps benchmarks/lifecycle-realworld-heldout-v1/steps.json
```

Review `data/realworld-heldout/review.html` as for the main set (green boxes
whose caption is not printed become icons; every listed negative must be
absent from the screen), regenerate, then commit `data/realworld-heldout/`
and `steps.json` and push before renting.

A laptop row needs no GPU:

```
python -m visual_dom.evaluation.lifecycle.runner --manifest benchmarks/lifecycle-realworld-heldout-v1/steps.json ^
    --executors vizdom-modular --out-dir benchmarks/results/heldout_local
```

## Capture (2026-11-10)

14 states of the five applications in the table above, captured at commit
`8db4f2c` (scorer constants as in ADR-022 1.13): `charmap` main / advanced,
`mouseprops` buttons / pointer-options / wheel, `folderopts` general / view /
search (the window is titled "File Explorer Options" on Windows 11),
`notepad` main / find / settings, `paint` main / resize / properties.
190 steps: 81 clicks, 109 verifications, 28 same-app negatives.

Edits made for privacy, before any run:

- **Paint** exposes the account button as "Signed in as <full name>" and
  draws the account photo. In the three `paint__*` labels that element is
  renamed `Account` (it was an icon with no step either way) and the photo is
  painted over with the toolbar colour.
- **Notepad** restores the user's previous session; the states were captured
  in a separate new window holding only the sentence "The quick brown fox
  jumps over the lazy dog." and closed without saving.

## Results

Laptop, commit `8db4f2c`, files `benchmarks/results/heldout_local/20261110_000129`
(modular) and `_000352` (desc), local and not committed. Beside them the same
chain on the main set at the same scorer (laptop, `20261109_144106`), which
is the set the scorer was tuned on.

| Column | Set | Action-hit | Present → pass | Absent → fail | Verify acc | False passes |
|---|---|---|---|---|---|---|
| `text=` vizdom-modular | held-out, 14 states / 5 apps | 0.765 (62/81) | 0.778 | 28/28 | 0.835 | 0 / 28 |
| `desc=` lexical → slm (keyword verify) | held-out, 14 states / 5 apps | 0.815 (66/81) | 0.864 | 27/28 | 0.890 | **1 / 28** |
| `desc=` lexical → slm (keyword verify) | main, 46 states / 9 apps (tuned) | 0.834 | 0.857 | 92/92 | 0.881 | 0 / 92 |

The set is small: 81 clicks give a 95 % Wilson interval of 0.72–0.88 for
the chain's 0.815, so the 0.02 drop from the main set is well inside the
noise, and verification did not drop at all (present → pass 0.864 against
0.857). **The click and verify figures generalise to applications the scorer
has not seen; the zero false passes do not, quite.**

**The false pass** (`folderopts__view`, "Single-click to open an item (point
to select) radio button", a caption of the General tab): the lexical tier
accepted the static sentence "You can apply this view (such as Details or
Icons) to all" at 1.68, over the 1.5 floor and exactly the 0.5 margin above
the next candidate. Two known weaknesses add up:

1. **A role word inside the caption.** "item" is a role word since ADR-022
   1.9 (tree and list items) and admits static text, so "open an item" earned
   the full role credit (+1.0) on a plain text element and lost "item" from
   the name tokens.
2. **Stop words in the overlap.** Of the eight name tokens only "to" (twice)
   and "an" (as a substring of "can") match: 2.7 / 8 × 2 = 0.68, without a
   single naming word in common.

This is the near-miss limit of the audit
(`../lifecycle-realworld-v1/AUDIT.md`) in a new form: the negative shares no
naming word with the screen, only function words and a role word. Per this
set's rule it is reported and **not fixed**. The candidate fix (overlap over
naming words only, and a role word that is part of the caption does not
score) waits for the next set of held-out screens to be judged.

Across both sets the chain passed 1 of 120 absent targets (95 % Wilson upper
limit 4.6 %); `text=` passed 0 of 120 (3.1 %).
