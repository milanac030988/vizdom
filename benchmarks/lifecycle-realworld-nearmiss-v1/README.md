# lifecycle-realworld-nearmiss-v1

168 verify steps on 35 of the 46 screens of `lifecycle-realworld-v1`, every
one a negative: the caption is **not** on the screen, but it shares words
with a caption that is. `Save` where only `Save As` is shown.

## Why this set exists

The negatives of `lifecycle-realworld-v1` are captions of another screen of
the same application, and its generator leaves out any caption that contains,
or is contained in, a name on the screen (`generate._absent_here`). That
keeps a negative from being arguably present, and it also removes the
hardest negatives a test author can write. The audit of 2026-11-09
(`../lifecycle-realworld-v1/AUDIT.md`, section 7) built those left-out
captions and scored the VizDOM locators on them offline. This manifest makes
the same captions runnable, so the grounders are measured on them too.

## How a step is built

`audit.near_miss_negatives`, kind `sibling`: a real caption of another screen
of the same application whose words contain, or are contained in, the words
of a name on this screen, while no name on this screen reads exactly those
words. The rule reads labels and the source manifest only; it does not look
at how any locator scores. The step fields and the instruction wording are
those of the source set (`the 'Save' button is visible`, description
`Save button`, `expect: FAILED`, `negative_kind: sibling`).

The `truncation` kind of the audit (a caption of this screen with its last
word removed) is not in the manifest: whether `Find` is absent from a screen
showing `Find Next` is a matter of opinion, a sibling caption is not.

```
python -m visual_dom.evaluation.lifecycle.audit --benchmark lifecycle-realworld-v1 \
    --near-miss-manifest benchmarks/lifecycle-realworld-nearmiss-v1/steps.json
```

Deterministic; a unit test fails when the committed file and the rule
disagree. Regenerate after any change to the source manifest or the labels.

## Reading a result

- Negatives only. A row's present → pass rate is the one it has on
  `lifecycle-realworld-v1`, which shows the same screens; a column that
  answers "absent" to everything scores 0 false passes here and must be read
  with that rate beside it.
- Verify accuracy on this set is 1 minus the false-pass rate.
- The steps of one screen are not independent; count screens (35) and
  applications (7) when quoting an interval, as the audit does.

## Results

Offline, from the saved DOMs of run 8 (`AUDIT.md` section 7):

| Locator | False passes |
|---|---|
| `text=` (exact, then substring) | 39 / 168 |
| `text=` exact match only (not in the product) | 1 / 168 |
| `desc=` lexical | 45 / 168 |
| `desc=` lexical with the exact-name rule (not in the product) | 0 / 168 |

Run 9 (`benchmarks/results/gpu-20261109_232648`, commit 4aae87a, RTX PRO
6000), end to end. Every step expects FAILED, so verify accuracy is the
absent-to-fail rate; the interval is Wilson over the 168 steps (the audit's
clustered interval, over 7 applications, is wider):

| Executor | False passes | Rate [95 % CI] | Median step |
|---|---|---|---|
| `vizdom-modular` (`text=`) | 39 / 168 | 0.232 [0.175, 0.302] | GPU chain, cached DOM |
| `vizdom-modular+desc[lexical+slm]` (`desc=`, keyword verify) | 45 / 168 | 0.268 [0.207, 0.339] | |
| `vizdom-modular+desc[lexical+vlm][verify=chain]` (pre-1.9 scoring) | 81 / 168 | 0.482 [0.408, 0.557] | 0.34 s |
| `ui-tars-1.5-7b` (point proxy) | 158 / 168 | 0.940 [0.894, 0.967] | 0.48 s |
| `ui-tars-1.5-7b[verify=yesno]` | 2 / 168 | 0.012 [0.003, 0.042] | 0.31 s |
| `elam-7b` (official FAILED-first rule) | 168 / 168 | 1.000 [0.978, 1.000] | 3.8 s |
| `aria-ui` (point proxy) | 137 / 168 | 0.815 [0.750, 0.867] | 2.7 s |

The end-to-end VizDOM rows reproduce the offline audit exactly (39 and 45).
The two VLM point proxies and ELAM pass nearly every sibling caption: asked
to point at something, a grounder points at the nearest match. Asked the
same statement as a yes/no question, UI-TARS answers "no" on 166 of the 168
(the two "yes" answers: the `Always` radio button in Notepad++'s new-document
page and the `Extensions, group` tree item in VS Code). On this set the
yes/no verdict is a stronger verifier than VizDOM's substring `text=` and
keyword `desc=` rules; the exact-match rules of the audit (1 and 0 of 168)
would close that gap but are not in the product.
