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

## Results

None yet. Report the rows beside those of the main set, with the number of
screens and applications, and say that the set is small.
