"""
Build vizdom_combined.html: one presentation told as a single argument, from
the deck, the diagrams, the walkthroughs and the benchmark report, without
presenter notes.

OUTLINE below is the storyline: each act places a diagram, a walkthrough or
a report section right after the slide that sets it up, so the evidence is
shown where it is argued, not in an appendix. Deck slides and diagrams the
outline does not place go to Backup, never lost: the build asserts every
one appears exactly once.

    python docs/present/build_combined.py

Sources (unchanged by this script):
  index-standalone.html          the deck (images inlined)
  vizdom_diagrams.html           -> appendix slides, CSS scoped under .slide.dg
  vizdom_walkthrough.html        -> an embedded slide (own page in an iframe)
  desc_walkthrough.html          -> an embedded slide (the deck links to it)
  ../../benchmarks/report_gpu_20261026_run3.html  -> overlay, opened per section

The companion pages keep their own CSS and scripts by running from blob URLs
inside iframes; the deck's companion links, which opened them in a new tab,
now jump inside the file, and B (or the back button) returns to the slide.
Every rewrite asserts it matched, so a changed source fails the build instead
of producing a file with dead links.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "vizdom_combined.html"

# The storyline. Items: ("deck", <h2 prefix> | "title" | "thanks"),
# ("dg", <diagram id>), ("wt"/"dwt", <scenario/step>, <overview title>),
# ("rs", <report section>, <overview title>), ("agenda",).
OUTLINE = [
    ("Opening", None, [("deck", "title"), ("agenda",)]),
    ("I · The gap",
     "Accessibility trees stop at canvases, HMIs and cameras; neither classic CV "
     "nor a per-step grounder gives a test what it needs",
     [("deck", "The problem: automation stops"),
      ("deck", "Why GUI element detection is hard"),
      ("deck", "Methodologies compared"),
      ("deck", "Model landscape: parsers vs grounders"),
      ("deck", "Why compose a parser")]),
    ("II · The idea",
     "Parse each screen once into a Visual DOM; every locator is a query over it",
     [("deck", "System overview"),
      ("dg", "system"),
      ("deck", "On a real application"),
      ("deck", "…and driving it from Robot Framework"),
      ("wt", "suite/0", "Walkthrough: a suite, end to end"),
      ("deck", "The CV pipeline"),
      ("dg", "backends")]),
    ("III · The architecture",
     "Ranked drivers, a scored decision, a hexagonal core, services where the hardware is",
     [("deck", "Architecture drivers"),
      ("deck", "Solution space"),
      ("deck", "The key decision"),
      ("dg", "overview"),
      ("dg", "hexagon"),
      ("deck", "Microservice-oriented"),
      ("dg", "distributed"),
      ("dg", "sequence"),
      ("deck", "Client surface"),
      ("dg", "topologies"),
      ("dg", "physical"),
      ("wt", "camera/0", "Walkthrough: camera in, robot arm out"),
      ("deck", "Quality scenarios")]),
    ("IV · The evidence",
     "514 steps against three end-to-end grounders (ELAM-7B, UI-TARS-1.5-7B, "
     "Aria-UI): clicking, judging, cost",
     [("deck", "Evaluation: methodology"),
      ("deck", "Results — and why one number misleads"),
      ("deck", "Testing effectiveness, end to end"),
      ("rs", "s4", "Result: action-hit per executor"),
      ("rs", "s5", "Result: the oracle row"),
      ("wt", "oracle/0", "Walkthrough: the oracle, an absent target"),
      ("rs", "s6", "Result: cost per step"),
      ("deck", "New capability — locating by description"),
      ("dg", "locators"),
      ("dwt", "lexical/0", "Walkthrough: desc= tiers"),
      ("rs", "s9", "Result: which tier answered")]),
    ("V · Making it better",
     "Four measured improvements, an ablation of our own stages, a bug no detector can fix",
     [("deck", "Improvement 1"),
      ("deck", "Improvement 2"),
      ("deck", "Improvement 3"),
      ("deck", "Improvement 4"),
      ("deck", "Ablation"),
      ("deck", "A correctness bug")]),
    ("VI · Close", "Contributions, limitations stated plainly, what comes next",
     [("deck", "Contributions"),
      ("deck", "Limitations"),
      ("deck", "Roadmap"),
      ("deck", "thanks")]),
]

# Result slides (matched by their <h2>) -> report sections to offer.
RESULT_LINKS = {
    "Model landscape: parsers vs grounders": [("s3", "Results table")],
    "Why compose a parser": [("s6", "Cost per step"), ("s5", "The oracle row")],
    # "Testing effectiveness" and "locating by description" are followed by
    # their result slides, so they carry no row of their own
    "Ablation — what each stage": [("s10", "Run 7 and the ablation")],
    "Limitations — stated plainly": [("s11", "Threats to validity")],
}

REPORT_SECTIONS = [("s1", "Summary"), ("s3", "Results"), ("s4", "Action-hit"),
                   ("s5", "Oracle"), ("s6", "Cost"), ("s7", "Families"),
                   ("s9", "desc= tiers"), ("s10", "Run 7"), ("s11", "Threats")]


def sub(pattern, repl, text, expect=1, flags=0):
    """re.subn that fails the build when the source no longer matches."""
    out, n = re.subn(pattern, repl, text, flags=flags)
    if (expect == "+" and n == 0) or (expect != "+" and n != expect):
        sys.exit(f"build_combined: {pattern!r} matched {n}x, expected {expect}")
    return out


def embed(page_id, html):
    """A page as a JSON string in an inert script tag (no '</' to end it early)."""
    body = json.dumps(html).replace("</", "<\\/")
    return f'<script type="application/json" id="{page_id}">{body}</script>\n'


# --------------------------------------------------------------------------
# companion pages: talk to the deck instead of opening/closing tabs
# --------------------------------------------------------------------------

FORWARD_KEYS = """<script>
/* combined deck: PageDown/PageUp turn the deck's page, Esc hands the keyboard back */
document.addEventListener('keydown', function (e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  var m = {PageDown: 'next', PageUp: 'prev', Escape: '%s'}[e.key];
  if (m) { e.preventDefault(); parent.postMessage({vizdom: m}, '*'); }
});
</script>
"""


def walkthrough(path):
    html = path.read_text(encoding="utf-8")
    html = sub(r"var fromDeck = query\.get\('from'\) === 'deck';",
               "var fromDeck = true;", html)
    html = sub(r"function goBack\(\) \{\n.*?\n  \}",
               "function goBack() { parent.postMessage({vizdom: 'back'}, '*'); }",
               html, flags=re.S)
    return sub(r"</body>", FORWARD_KEYS % "back" + "</body>", html)


SECTION_ONLY = """<script>
/* combined deck, result slide (#only-sN): this one section, in the deck's dark theme.
   Runs after the charts are drawn, so hiding the rest does not change their size. */
(function () {
  var m = /^#only-(s\\d+)$/.exec(location.hash);
  if (!m) return;
  document.documentElement.setAttribute('data-theme', 'dark');
  // a slide is the heading and the section's chart, nothing else: the prose
  // and tables stay in the full report overlay
  var TITLES = %s, STALE = %s, NOTES = %s;
  var main = document.querySelector('main'), on = false, chart = null;
  var h2 = document.getElementById(m[1]);
  if (TITLES[m[1]]) h2.textContent = TITLES[m[1]];
  // sentences about run history: the slide shows one row per executor
  Array.prototype.forEach.call(document.querySelectorAll('p.sub'), function (p) {
    STALE.forEach(function (s) { p.innerHTML = p.innerHTML.replace(s, ''); });
  });
  Array.prototype.forEach.call(main.children, function (el) {
    if (el.tagName === 'H2') on = el.id === m[1];
    var keep = on && (el.tagName === 'H2' || (!chart && el.classList.contains('card')));
    if (on && !chart && el.classList.contains('card')) chart = el;
    el.style.display = keep ? '' : 'none';
  });
  if (chart && NOTES[m[1]]) {
    var note = document.createElement('div');
    note.className = 'callout';
    note.innerHTML = NOTES[m[1]];
    chart.parentNode.insertBefore(note, chart.nextSibling);
  }
  main.style.paddingTop = '2vh';
  main.style.paddingBottom = '0';
  // then scale it into the frame: long row labels overhang the chart on the
  // left, so the overhang counts toward the width
  function fit() {
    document.body.style.zoom = 1;
    var left = 0;
    Array.prototype.forEach.call(document.querySelectorAll('main svg text'), function (t) {
      if (t.offsetParent !== null || t.getClientRects().length)
        left = Math.min(left, t.getBoundingClientRect().left);
    });
    document.body.style.paddingLeft = left < 8 ? (8 - left) + 'px' : '';
    var h = document.documentElement.scrollHeight, w = document.documentElement.scrollWidth;
    document.body.style.zoom = Math.min(1, innerHeight / h, innerWidth / w);
    window.scrollTo(0, 0);
  }
  fit();
  addEventListener('resize', fit);
})();
</script>
"""


# Result slides show one row per executor: its latest run, or its best one
# where the latest was disturbed (the vision tier's run 6 hit Ollama errors).
# Cost keeps the rows measured on the grounders' card model (runs 3 and 6);
# run 7 ran on a slower card and would not be a like-for-like timing.
# {chart id: [(report label, slide label), ...]} in display order.
SLIDE_ROWS = {
    "chart-hit": [
        ("aria-ui (bf16, 96 GB card)", "Aria-UI"),
        ("vizdom-modular + desc= (run 7, 2nd OCR engine)", "VizDOM modular + desc="),
        ("ui-tars-1.5-7b (bf16)", "UI-TARS-1.5-7B"),
        ("elam-7b (bf16)", "ELAM-7B"),
        ("vizdom-omniparser / modular (run 7)", "VizDOM OmniParser / modular, text="),
        ("vizdom-uied (run 7)", "VizDOM UIED, text=")],
    "chart-verify": [
        ("vizdom desc= chain (run 7, 2nd OCR engine)", "VizDOM modular + desc="),
        ("vizdom (all three, run 7, 2nd OCR engine)", "VizDOM text= (all three detectors)"),
        ("ui-tars-1.5-7b", "UI-TARS-1.5-7B"),
        ("elam-7b", "ELAM-7B"),
        ("aria-ui (addendum)", "Aria-UI")],
    "chart-cost": [
        ("vizdom-uied", "VizDOM UIED"),
        ("vizdom-modular", "VizDOM modular"),
        ("vizdom-omniparser", "VizDOM OmniParser"),
        ("vizdom-modular + desc= (run 6)", "VizDOM modular + desc="),
        ("aria-ui (bf16, 96 GB card)", "Aria-UI (96 GB card)"),
        ("ui-tars-1.5-7b (bf16)", "UI-TARS-1.5-7B"),
        ("elam-7b (bf16)", "ELAM-7B")],
    "chart-tiers": [
        ("desc[lexical+slm] (run 7, 2nd OCR engine)", "lexical → SLM (production)"),
        ("desc[slm] (run 7, plain prompt)", "SLM only"),
        ("desc[vlm] (run 4)", "VLM only"),
        ("desc[lexical+vlm] (run 5)", "lexical → VLM")],
}

# Result slides: the takeaway as the headline (the report numbers its
# sections and names runs), and caption sentences that only describe history.
SLIDE_TITLES = {
    "s4": "Action-hit: VizDOM + desc= within half a point of the best grounder",
    "s5": "The oracle: every grounder passes absent targets, VizDOM passes none",
    "s6": "Cost: VizDOM pays per screen, a grounder pays per step",
    "s9": "desc=: 79 % of the steps resolved with no model at all",
}
# Under the chart: what it measures and what it means for the argument.
SLIDE_NOTES = {
    "s4": "<p><b>What it measures.</b> A click step hits when the point an executor produces "
          "lands inside the target element; 213 click steps over 44 screens.</p>"
          "<p><b>What it means.</b> With its own language tier (<code>desc=</code>) VizDOM is "
          "within 0.4 points of Aria-UI and ahead of UI-TARS-1.5-7B and ELAM-7B. With exact "
          "<code>text=</code> locators it trails by 1.4 to 4.6 points, and every one of its misses "
          "is a resolution miss: a caption OCR did not read, or two elements matching. The "
          "exactly-one contract makes VizDOM fail such a step instead of guessing.</p>",
    "s5": "<p><b>What it measures.</b> 301 verify steps; 88 of them check for a label that is "
          "not on the screen, so the right verdict is FAILED. Green is a false pass: the test "
          "reports success on something that is not there.</p>"
          "<p><b>What it means.</b> A grounder always returns a point, so it passes 60 to 88 of "
          "the 88. VizDOM passes none, by construction: a check needs exactly one element in the "
          "DOM, and an absent label has none. Its own errors are false fails (8 to 13), which "
          "stop the test and get looked at: the cheap failure, not the dangerous one.</p>",
    "s6": "<p><b>What it measures.</b> Seconds per test step over the whole 514-step suite, "
          "model load included.</p>"
          "<p><b>What it means.</b> VizDOM parses each of the 44 screens once and answers every "
          "step from the cached DOM; a grounder runs a 7B-class model on every step. That is "
          "0.04 to 0.10 s per step against 1.6 to 4.0 s: roughly 15 to 100 times less time per "
          "step, and the runner itself needs no GPU.</p>",
    "s9": "<p><b>What it measures.</b> Which tier of the <code>desc=</code> chain answered each "
          "of the 514 steps. Grey is “no confident match”, which is the right answer for "
          "the 88 absent targets.</p>"
          "<p><b>What it means.</b> Lexical scoring over the DOM answers 408 steps with no model "
          "call; the 3B text model is asked only for what that cannot settle. The small models on "
          "their own resolve fewer steps and make confident wrong picks, which is why they sit "
          "behind the lexical tier, never in front of it.</p>",
}

SLIDE_STALE = [
    " Faded bars are superseded runs, kept for scale.",
    " The production chain answers 77 % of the steps without any model.",
]

SLIDE_PICK = """<script>
/* combined deck, result slide (#only-sN): one row per executor, no run history */
window.slidePick = (function () {
  if (!/^#only-s\\d+$/.test(location.hash)) return null;
  var pick = %s;
  return function (id, rows) {
    var want = pick[id];
    if (!want) return rows;
    return want.map(function (p) {
      var r = rows.filter(function (x) { return x.label === p[0]; })[0];
      if (!r) throw new Error('slide chart ' + id + ': no row ' + p[0]);
      return Object.assign({}, r, { label: p[1], dim: false });
    });
  };
})();
</script>
"""


def report(path):
    html = path.read_text(encoding="utf-8")
    html = sub(r"<h2>(\d+)\. ", r'<h2 id="s\1">\1. ', html, expect="+")
    # the chart functions filter their rows on a result slide
    for fn in ("hbars(id, rows, opts)", "hstack(id, rows, series, total, grid, aria)"):
        html = sub(re.escape("function " + fn + " {"),
                   lambda m: m.group(0) + "\n    if (window.slidePick) rows = window.slidePick(id, rows);",
                   html)
    for chart, rows in SLIDE_ROWS.items():
        for label, _ in rows:
            if f"label: '{label}'" not in html:
                sys.exit(f"build_combined: report chart {chart} has no row {label!r}")
    pick = (SLIDE_PICK % json.dumps(SLIDE_ROWS, ensure_ascii=False)).replace("\\", r"\\")
    html = sub(r"(<script>\n)(?!.*<script>\n)", pick + r"\1", html, flags=re.S)
    for s in SLIDE_STALE:
        if s not in html:
            sys.exit(f"build_combined: report caption changed, {s!r} not found")
    only = SECTION_ONLY % (json.dumps(SLIDE_TITLES, ensure_ascii=False),
                           json.dumps(SLIDE_STALE, ensure_ascii=False),
                           json.dumps(SLIDE_NOTES, ensure_ascii=False))
    inject = (only + FORWARD_KEYS % "close-report").replace("\\", r"\\")
    return sub(r"</body>", inject + "</body>", html)


# --------------------------------------------------------------------------
# diagrams: sections become deck slides, CSS scoped to .slide.dg
# --------------------------------------------------------------------------

DROP_SELECTORS = re.compile(
    r"^(:root|html|body|\*|\.slide|\.slide\.active|#progress|#hud.*|#count|#hint|"
    r"#notes.*|aside\.notes)$")


def css_rules(css):
    """Top-level (selector, body) pairs; @media bodies are returned raw."""
    rules, i = [], 0
    while True:
        start = css.find("{", i)
        if start < 0:
            return rules
        depth, j = 1, start + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        rules.append((css[i:start].strip(), css[start + 1:j - 1]))
        i = j


def rem(body):
    # rem was the diagrams' root size; on a deck slide it is --dgr
    return re.sub(r"(-?\d*\.?\d+)rem", r"calc(\1 * var(--dgr))", body)


def scope(css):
    out = []
    for selector, body in css_rules(re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        if selector.startswith("@media"):
            if "reduced-motion" in selector:
                continue
            out.append(selector + " {\n" + scope(body) + "}")
            continue
        parts = [s.strip() for s in selector.split(",")]
        if all(DROP_SELECTORS.match(p) for p in parts):
            if parts == ["html"] and "font-size" in body:   # the media-query size
                out.append(".slide.dg { --dgr: %s; }" %
                           re.search(r"font-size:\s*([^;]+);", body).group(1).strip())
            continue
        out.append(", ".join(".slide.dg " + p for p in parts) + " {" + rem(body) + "}")
    return "\n".join(out) + "\n"


DG_BASE = """
/* ---------- appendix: diagrams (vizdom_diagrams.html, scoped) ---------- */
.slide.dg { --dgr: clamp(13px, min(1.22vw, 2.15vh), 23px);
  --ground:#0e1420; --surface:#141c2b; --surface-2:#1b2536; --ink:#e8eef7; --muted:#93a4bd;
  --rule:#26334a; --font-body:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;
  --font-mono:"Cascadia Code",Consolas,"Courier New",monospace;
  font-size:var(--dgr); line-height:1.5; color:var(--ink);
  padding:3vh 4vw max(7vh, calc(3.4 * var(--dgr))) }
.slide.dg.active { justify-content:center }
/* undo the deck's element styles the diagrams never set */
.slide.dg h1, .slide.dg h2 { border:0; padding:0; color:var(--ink) }
.slide.dg h3 { color:var(--ink) }
.slide.dg p, .slide.dg li { font-size:inherit; line-height:inherit; color:inherit }
.slide.dg code { border:0 }
.slide.dg table { margin:0 }
#deck.overview .slide.dg svg { max-height:90px }

/* A full slide centred its content even when it overflowed, so the top of it
   slid up under the headline; now it grows and the slide scrolls instead. */
.grow { flex:1 0 auto; justify-content:safe center }

/* ---------- appendix: embedded pages ---------- */
.slide.frame { padding:0 0 4.2vh }   /* the bottom bar stays clear of the page */
.slide.frame iframe { flex:1; width:100%; border:0; background:#0b1120 }
.slide.frame h2.ov { display:none }
#deck.overview .slide.frame h2.ov { display:block }
#deck.overview .slide.frame iframe { display:none }

/* ---------- in-file jumps and the report overlay ---------- */
.dlinks a.r { color:var(--warn) }
.dlinks.rlinks { margin:-.5em 0 .7em }
#backbtn { position:fixed; top:1.2vh; right:1.3vw; z-index:25; font:inherit; font-size:13px;
  background:var(--bg2); color:var(--accent); border:1px solid var(--accent); border-radius:999px;
  padding:.3em .9em; cursor:pointer }
#rp { position:fixed; inset:0; z-index:50; display:flex; flex-direction:column; background:var(--bg) }
#rp[hidden] { display:none }
#rpbar { display:flex; flex-wrap:wrap; gap:.4em .6em; align-items:center; padding:.55em 1em;
  border-bottom:1px solid var(--line); font-size:13px }
#rpbar .t { font-weight:700; margin-right:.4em }
#rpbar button { font:inherit; background:#1b2536; color:var(--fg); border:1px solid var(--line);
  border-radius:999px; padding:.2em .75em; cursor:pointer }
#rpbar button:hover, #rpbar button[aria-pressed="true"] { border-color:var(--warn); color:#fff }
#rpbar #rpx { margin-left:auto }
#rp iframe { flex:1; width:100%; border:0; background:#fff }
@media print { #backbtn, #rp, .slide.frame { display:none !important } }
"""


def diagram_slides(path):
    html = path.read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    sections = re.findall(r"<section .*?</section>", html, re.S)
    if len(sections) != 12:
        sys.exit(f"build_combined: expected 12 diagram slides, found {len(sections)}")
    slides = {}
    for s in sections:
        s = sub(r"\s*<aside class=\"notes\">.*?</aside>", "", s, flags=re.S)
        key = re.search(r'id="([\w-]+)"', s).group(1)
        slides[key] = sub(r'<section class="slide(?: active)?" id="([\w-]+)"',
                          r'<section class="slide dg" id="dg-\1"', s)
    # the companion's own title/index page has no place in one deck
    del slides["title"]
    return slides, DG_BASE + scope(css)


# --------------------------------------------------------------------------
# the storyline
# --------------------------------------------------------------------------

def deck_slides(deck):
    """{key: section html}: "title", "thanks", else the slide's <h2> text."""
    sections = re.findall(r"<section class=\"slide.*?</section>", deck, re.S)
    out = {}
    for n, s in enumerate(sections):
        h2 = re.search(r"<h2>(.*?)</h2>", s, re.S)
        key = ("title" if n == 0 else "thanks" if n == len(sections) - 1
               else re.sub(r"<[^>]+>", "", h2.group(1)).replace("&amp;", "&"))
        out[key] = sub(r'<section class="slide', f'<section id="d{n + 1}" class="slide', s)
    return out


def frame_slide(page, hash_, title, sid):
    return (f'<section class="slide frame" id="{sid}" data-src="{page}" data-hash="{hash_}">\n'
            f'  <h2 class="ov">{title}</h2>\n'
            f'  <iframe title="{title}"></iframe>\n</section>')


def agenda_slide(acts):
    cards = "".join(
        f'<a class="card act" href="#" data-go="{first}"><b>{name}</b>'
        f'<span>{purpose}</span><i>slides {a}–{b}</i></a>'
        for name, purpose, first, a, b in acts)
    return ('<section class="slide" id="agenda" data-act="Opening">\n'
            '  <h2>The argument, in six steps</h2>\n'
            f'  <div class="grow"><div class="agenda">{cards}</div>\n'
            '  <p class="small" style="margin-top:1.2em">Diagrams, walkthroughs and benchmark '
            'results sit where they are argued. Every slide with numbers links to the full '
            'report (<kbd>r</kbd>); <kbd>b</kbd> returns after a jump.</p></div>\n</section>')


# the hexagonal slide: text in two columns on top, the general picture below
# at full width, scaled to the height that is left
HEX_CSS = """
.hexwrap{flex:1;min-height:0;display:flex;flex-direction:column;gap:.8em}
.hexwrap>div:first-child{columns:2;column-gap:3em}
.hexwrap>div:first-child>p:first-child,.hexwrap>div:first-child h3{margin-top:0}
.hexwrap>div:first-child h3{break-before:column}
.hexwrap .hexfig{flex:1 1 0;min-height:0}
.hexwrap .hexfig img{max-width:100%;max-height:100%;width:auto;height:auto}
"""

AGENDA_CSS = """
/* ---------- agenda and act indicator ---------- */
.agenda { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:1.2vw }
.agenda a.act { display:flex; flex-direction:column; gap:.45em; text-decoration:none; color:var(--fg) }
.agenda a.act b { color:var(--accent); font-size:clamp(15px,1.5vw,21px) }
.agenda a.act span { font-size:clamp(13px,1.15vw,17px); line-height:1.45 }
.agenda a.act i { font-style:normal; color:var(--dim); font-size:clamp(11px,.95vw,13px); margin-top:auto }
.agenda a.act:hover { border-left-color:var(--accent2) }
#act { color:var(--accent) }
.backup-note { color:var(--dim) }
"""


def assemble(deck_by_key, dia_by_id):
    """The slides in story order, then Backup; asserts nothing is lost or doubled."""
    used_deck, used_dg = set(), set()

    def deck_slide(prefix):
        hits = [k for k in deck_by_key if k == prefix or k.startswith(prefix)]
        if len(hits) != 1:
            sys.exit(f"build_combined: outline {prefix!r} matches {hits}")
        if hits[0] in used_deck:
            sys.exit(f"build_combined: {hits[0]!r} placed twice")
        used_deck.add(hits[0])
        return deck_by_key[hits[0]]

    def dg_slide(key):
        if key not in dia_by_id or key in used_dg:
            sys.exit(f"build_combined: diagram {key!r} missing or placed twice")
        used_dg.add(key)
        return dia_by_id[key]

    story, acts, n = [], [], 0
    for name, purpose, items in OUTLINE:
        first = None
        for item in items:
            kind = item[0]
            if kind == "deck":
                html = deck_slide(item[1])
            elif kind == "dg":
                html = dg_slide(item[1])
            elif kind in ("wt", "dwt"):
                html = frame_slide("page-" + kind, item[1], item[2],
                                   f"{kind}-{item[1].split('/')[0]}")
            elif kind == "rs":
                html = frame_slide("page-report", "only-" + item[1], item[2], f"rs-{item[1]}")
            else:
                html = "{{AGENDA}}"
            sid = re.search(r'id="([\w-]+)"', html).group(1) if kind != "agenda" else "agenda"
            first = first or sid
            html = html.replace("<section ", f'<section data-act="{name}" ', 1)
            story.append(html)
            n += 1
            if first == sid:
                start = n
        if purpose:
            acts.append((name, purpose, first, start, n))

    backup = ([deck_by_key[k] for k in deck_by_key if k not in used_deck]
              + [dia_by_id[k] for k in dia_by_id if k not in used_dg])
    divider = ('<section class="slide center" data-act="Backup" id="backup">\n'
               '  <div class="grow center" style="display:flex;flex-direction:column">\n'
               '    <h1 style="font-size:clamp(30px,4vw,52px)">Backup<span style="color:var(--accent)">.</span></h1>\n'
               '    <p class="dim">Kept for questions, not presented in order</p></div>\n</section>')
    backup = [divider] + [s.replace("<section ", '<section data-act="Backup" ', 1) for s in backup]
    story = [s.replace("{{AGENDA}}", agenda_slide(acts)) for s in story]
    return "\n\n".join(story + backup)


# --------------------------------------------------------------------------
# the deck
# --------------------------------------------------------------------------

DECK_JS = r"""
  /* ---------- combined file: in-file jumps, embedded pages, report ---------- */
  function blobUrl(id){
    var el = document.getElementById(id);
    if(!el._url) el._url = URL.createObjectURL(new Blob([JSON.parse(el.textContent)], {type:'text/html'}));
    return el._url;
  }
  // a fresh iframe per load: the pages read their #scenario/step on load only
  function loadFrame(slide, hash){
    var f = slide.querySelector('iframe');
    if(!f || (!hash && f.getAttribute('src'))) return;
    var g = f.cloneNode();
    g.src = blobUrl(slide.dataset.src) + '#' + (hash || slide.dataset.hash);
    f.parentNode.replaceChild(g, f);
  }
  var backStack = [], backBtn = document.getElementById('backbtn');
  function updBack(){
    backBtn.hidden = !backStack.length;
    if(backStack.length) backBtn.textContent = '← back to slide ' + (backStack[backStack.length-1]+1) + '  (B)';
  }
  // a walkthrough link goes to the slide showing that scenario, else to the
  // first slide of that page, loaded at the scenario
  function jump(id, hash, page){
    var k = page
      ? slides.findIndex(function(s){ return s.dataset.src === page && s.dataset.hash === hash; })
      : slides.findIndex(function(s){ return s.id === id; });
    if(k < 0 && page) k = slides.findIndex(function(s){ return s.dataset.src === page; });
    if(k < 0) return;
    if(k !== i) backStack.push(i);
    if(hash) loadFrame(slides[k], hash);
    show(k); updBack();
  }
  function goBackSlide(){
    if(backStack.length){ show(backStack.pop()); updBack(); }
    else if(document.activeElement) document.activeElement.blur();
  }
  backBtn.addEventListener('click', goBackSlide);

  var rp = document.getElementById('rp'), rpf = document.getElementById('rpf');
  function reportOpen(){ return !rp.hidden; }
  function openReport(sec){
    var g = rpf.cloneNode();
    g.src = blobUrl('page-report') + '#' + (sec || 's1');
    rpf.parentNode.replaceChild(g, rpf); rpf = g;
    rp.querySelectorAll('#rpbar button[data-sec]').forEach(function(b){
      b.setAttribute('aria-pressed', String(b.dataset.sec === (sec || 's1')));
    });
    rp.hidden = false;
  }
  function closeReport(){ rp.hidden = true; rpf.removeAttribute('src'); window.focus(); }
  document.getElementById('rpx').addEventListener('click', closeReport);
  rp.querySelectorAll('#rpbar button[data-sec]').forEach(function(b){
    b.addEventListener('click', function(){ openReport(b.dataset.sec); });
  });

  document.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a[data-go],a[data-page],a[data-report]');
    if(!a || deck.classList.contains('overview')) return;
    e.preventDefault();
    if(a.hasAttribute('data-report')) openReport(a.dataset.report);
    else jump(a.dataset.go, a.dataset.frame, a.dataset.page);
  });
  // the act being presented, in the bottom bar
  var actEl = document.getElementById('act');
  function showAct(){ actEl.textContent = slides[i].dataset.act || 'VizDOM'; }
  window.addEventListener('message', function(e){
    var m = e.data && e.data.vizdom;
    if(m === 'back') goBackSlide();
    else if(m === 'next') show(i+1);
    else if(m === 'prev') show(i-1);
    else if(m === 'close-report') closeReport();
  });
"""


def report_chips(deck):
    for title, links in RESULT_LINKS.items():
        m = re.search(r"<h2>" + re.escape(title) + r".*?</section>", deck, re.S)
        if not m:
            sys.exit(f"build_combined: result slide {title!r} not found")
        chips = "<span>Benchmark report</span> " + " ".join(
            f'<a class="r" href="#" data-report="{sec}">{label}</a>' for sec, label in links)
        # under the title, not in the bottom link row: the result slides are
        # the fullest ones, and their content runs over a bottom row
        slide = re.sub(r"(</h2>)", r'\1\n  <p class="dlinks rlinks">' + chips + "</p>",
                       m.group(0), count=1)
        deck = deck[:m.start()] + slide + deck[m.end():]
    return deck


def build():
    deck = (HERE / "index-standalone.html").read_text(encoding="utf-8")

    # presenter notes: the blocks, their CSS, the key and its mentions
    deck = sub(r"\n?[ \t]*<div class=\"notes\">.*?</div>", "", deck, expect="+", flags=re.S)
    deck = sub(r"/\* ---------- notes ---------- \*/\n.*?\n\n", "", deck, flags=re.S)
    deck = sub(r"\.card,\.kpi div,\.notes\{", ".card,.kpi div{", deck)
    deck = sub(r"\n\s*\.notes\{display:none!important\}", "", deck)
    deck = sub(r"<kbd>n</kbd> notes &nbsp; ", "", deck)
    deck = sub(r"<kbd>n</kbd> presenter notes &nbsp;·&nbsp; ", "", deck)
    deck = sub(r"\n\s*if\(k==='n'\|\|k==='N'\)\{ document\.body\.classList\.toggle\('notes-on'\); return; \}",
               "", deck)
    if "notes" in re.sub(r"<style>.*?</style>", "", deck, flags=re.S).lower():
        sys.exit("build_combined: a presenter note survived")

    # companion links: new tab -> in-file jump
    deck = sub(r'<a( class="\w+")? href="vizdom_diagrams\.html\?from=deck#([\w-]+)" target="_blank" rel="noopener">',
               r'<a\1 href="#dg-\2" data-go="dg-\2">', deck, expect="+")
    # "All diagrams" pointed at the companion's index page, which is not kept
    deck = deck.replace('href="#dg-title" data-go="dg-title"', 'href="#dg-system" data-go="dg-system"')
    deck = sub(r'<a( class="\w+")? href="vizdom_walkthrough\.html\?from=deck#([\w/]+)" target="_blank" rel="noopener">',
               r'<a\1 href="#" data-page="page-wt" data-frame="\2">', deck, expect="+")
    deck = sub(r'<a( class="\w+")? href="desc_walkthrough\.html\?from=deck#([\w/]+)" target="_blank" rel="noopener">',
               r'<a\1 href="#" data-page="page-dwt" data-frame="\2">', deck, expect="+")
    deck = sub(r'<div id="title-chip">.*?</div>',
               '<div id="title-chip">VizDOM &nbsp;·&nbsp; <span id="act"></span> &nbsp;·&nbsp; '
               '<a href="#" data-go="agenda">Agenda</a> &nbsp;·&nbsp; '
               '<a href="#" data-report="s1">Benchmark report</a></div>', deck, flags=re.S)
    deck = sub(r'content:" \\2197"', r'content:" \\203A"', deck)
    leftover = re.findall(r'href="(?!#|https?:)[^"]*"', deck)
    if leftover:
        sys.exit(f"build_combined: links still leave the file: {leftover[:5]}")
    deck = sub(r"(<title>)[^<]*(</title>)", r"\1VizDOM — Presentation\2", deck)
    deck = report_chips(deck)
    # the general hexagon picture, then the detailed diagram on the next
    # slide: text above, the picture below at full width so it is readable
    deck = sub(r'(<h2>Architecture: hexagonal ports &amp; adapters</h2>\s*)<div class="cols" style="flex:1;min-height:0">',
               r'\1<div class="hexwrap">', deck)
    deck = sub(r'(<div class="fig)("><img [^>]*alt="Hexagonal architecture")', r"\1 hexfig\2", deck)

    # the storyline replaces the deck's own order
    dia_by_id, dia_css = diagram_slides(HERE / "vizdom_diagrams.html")
    body = assemble(deck_slides(deck), dia_by_id)
    m = re.search(r'(<div id="deck">\n).*(</div><!-- /deck -->)', deck, re.S)
    deck = deck[:m.end(1)] + "\n" + body + "\n\n" + deck[m.start(2):]
    deck = sub(r"</style>", (dia_css + AGENDA_CSS + HEX_CSS).replace("\\", r"\\") + "</style>", deck)
    dangling = [g for g in re.findall(r'data-go="([\w-]+)"', deck)
                if f'id="{g}"' not in deck]
    if dangling:
        sys.exit(f"build_combined: jump targets missing: {sorted(set(dangling))}")

    # chrome: back button, report overlay, help lines
    sec_buttons = "".join(f'<button type="button" data-sec="{s}">{t}</button>'
                          for s, t in REPORT_SECTIONS)
    overlay = (
        '<button id="backbtn" type="button" hidden></button>\n'
        '<div id="rp" hidden><div id="rpbar"><span class="t">Benchmark report</span>'
        '<span class="dim">lifecycle benchmark, 514 steps · runs 3 to 7</span>'
        f'{sec_buttons}<button type="button" id="rpx" title="Close (Esc)">✕ close</button></div>'
        '<iframe id="rpf" title="Benchmark report"></iframe></div>\n')
    deck = sub(r'<div id="num"></div>\n', '<div id="num"></div>\n' + overlay, deck)
    deck = sub(r"(<kbd>o</kbd> overview grid \(click a slide to jump\)<br>)",
               r"\1\n    <kbd>r</kbd> benchmark report &nbsp;·&nbsp; <kbd>b</kbd> back after a jump<br>"
               r"\n    on a walkthrough slide: click it, then <kbd>←</kbd><kbd>→</kbd> step, "
               r"<kbd>Esc</kbd> returns the keys<br>", deck)

    # script: frames load on show, keys for report/back, the jump machinery
    deck = sub(r"(    if\(!deck\.classList\.contains\('overview'\)\) slides\[i\]\.scrollTop = 0;\n)",
               r"\1    if(!deck.classList.contains('overview')) loadFrame(slides[i]);\n"
               r"    showAct();\n"
               r"    if(document.activeElement && document.activeElement.tagName === 'IFRAME') document.activeElement.blur();\n",
               deck)
    deck = sub(r"(    var k = e\.key;\n)",
               r"\1    if(reportOpen()){ if(k==='Escape'){ closeReport(); e.preventDefault(); } return; }\n"
               r"    if((k==='r'||k==='R') && !lbOpen()){ openReport('s1'); return; }\n"
               r"    if((k==='b'||k==='B') && !lbOpen()){ goBackSlide(); return; }\n", deck)
    deck = sub(r"\n  // Companion links carry the deck.*?\n(  var start = )",
               "\n" + DECK_JS.replace("\\", r"\\") + r"\n\1", deck, flags=re.S)

    pages = (embed("page-wt", walkthrough(HERE / "vizdom_walkthrough.html"))
             + embed("page-dwt", walkthrough(HERE / "desc_walkthrough.html"))
             + embed("page-report", report(HERE.parents[1] / "benchmarks" / "report_gpu_20261026_run3.html")))
    deck = sub(r"(<script>\n\(function\(\)\{)", pages.replace("\\", r"\\") + r"\1", deck)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(deck)
    print(f"{OUT.name}: {len(deck) / 1024:.0f} KB")


if __name__ == "__main__":
    build()
