# VizDOM Project Report

Paper-format project report (general academic report structure), bilingual.

| File | Language | Style |
|------|----------|-------|
| `vizdom_report_en.tex` | English | General academic report (~15-25 pp) |
| `vizdom_report_vi.tex` | Vietnamese | General academic report (~15-25 pp) |
| `vizdom_architecture_en.tex` | English | arc42 architecture doc, 12 sections (~27 pp) |
| `vizdom_architecture_vi.tex` | Vietnamese | arc42 architecture doc, 12 sections (~27 pp) |
| `references.bib` | shared bibliography | |
| `figures/*.png` | diagrams rendered from `docs/diagrams/*.puml` | |

## Build

> **These documents require XeLaTeX (or LuaLaTeX), not pdfLaTeX** — they use
> `fontspec`. Compiling with pdfLaTeX fails with
> *"The fontspec package requires either XeTeX or LuaTeX."*

**On Overleaf:** Menu (top-left) → *Settings* → *Compiler* → **XeLaTeX**, then
*Recompile*. Upload the whole `report/` folder (the `figures/` PNGs and
`references.bib` must be present) and set the **Main document** to the `.tex` you
are building.

**Locally**, use **XeLaTeX** (handles both English and Vietnamese with the default
Latin Modern fonts, no extra font install):

```bash
cd report
# General report (EN + VI)
xelatex vizdom_report_en.tex && bibtex vizdom_report_en && xelatex vizdom_report_en.tex && xelatex vizdom_report_en.tex
xelatex vizdom_report_vi.tex && bibtex vizdom_report_vi && xelatex vizdom_report_vi.tex && xelatex vizdom_report_vi.tex
# Architecture document (arc42; EN + VI)
xelatex vizdom_architecture_en.tex && bibtex vizdom_architecture_en && xelatex vizdom_architecture_en.tex && xelatex vizdom_architecture_en.tex
xelatex vizdom_architecture_vi.tex && bibtex vizdom_architecture_vi && xelatex vizdom_architecture_vi.tex && xelatex vizdom_architecture_vi.tex
```

Or with latexmk (a `latexmkrc` here already defaults to XeLaTeX):

```bash
latexmk -xelatex vizdom_report_en.tex
latexmk -xelatex vizdom_report_vi.tex
latexmk -xelatex vizdom_architecture_en.tex
latexmk -xelatex vizdom_architecture_vi.tex
```

Or build all four at once (Windows):

```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File build.ps1                    # all four
powershell -ExecutionPolicy Bypass -File build.ps1 vizdom_report_en   # just one
```

```bat
:: cmd / double-click (all-in-one: sets MiKTeX PATH, handles locked PDFs)
build.bat
build.bat vizdom_report_en
```

Need TeX first? Install MiKTeX (`winget install MiKTeX.MiKTeX`) or TeX Live, then
reopen the terminal so `xelatex` is on `PATH`. Clean artifacts with `latexmk -c`.

> The Vietnamese file uses `babel` with the `vietnamese` option; XeLaTeX + the
> default Latin Modern fonts render the diacritics. If you prefer pdfLaTeX for the
> Vietnamese file, install `vntex` and add `\usepackage[utf8]{inputenc}` +
> `\usepackage[T5]{fontenc}` to the preamble.

## Figures

The figures are PNGs exported from the PlantUML sources of record in
`docs/diagrams/`. To regenerate after editing a diagram:

```bash
bash report/regen_figures.sh
```

(needs Java on PATH, `tools/plantuml.jar`, and Graphviz for `architecture.puml`.)

## Before submitting

- Fill in the title-page placeholders: `[Author Name]`, `[University / Faculty]`,
  `[Supervisor Name]`.
- Complete the quantitative results table (`tab:results`) once the labelled
  benchmark dataset is ready — the numbers are intentionally left as `--`.
- Verify the entries in `references.bib` (they are starter entries; check author
  lists, years, and venues against the real sources).

## Note

LaTeX build artifacts (`*.aux`, `*.log`, `*.pdf`, `*.bbl`, `*.blg`, `*.out`,
`*.toc`) are not committed — see `.gitignore`.
