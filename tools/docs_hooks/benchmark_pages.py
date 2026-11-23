"""ProperDocs hook: publish the benchmark write-ups under benchmarks/ on the docs site.

The benchmark method, results and analysis live next to the data in benchmarks/
(README.md, the set READMEs and audits, the HTML reports). This hook adds them to
the site at build time, so there is one copy of each text:

    benchmarks/README.md                              -> benchmarks/index.md
    benchmarks/lifecycle-<set>/README.md, AUDIT.md     -> benchmarks/<page>.md
    benchmarks/report_*.html (English reports only)    -> benchmarks/report_*.html

Links between these files, written either as Markdown links or as code spans
naming the file (`lifecycle-realworld-v1/README.md`), point to the site pages.
Other relative links into the repository point to GitHub.

Registered in properdocs.yml under `hooks:`.
"""

import os
import posixpath
import re

from properdocs.structure.files import File

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GITHUB = "https://github.com/milanac030988/vizdom/blob/HEAD/"

# repository path -> path on the site (relative to docs_dir)
PAGES = {
    "benchmarks/README.md": "benchmarks/index.md",
    "benchmarks/lifecycle-synthetic-v1/AUDIT.md": "benchmarks/synthetic-audit.md",
    "benchmarks/lifecycle-realworld-v1/README.md": "benchmarks/realworld.md",
    "benchmarks/lifecycle-realworld-v1/AUDIT.md": "benchmarks/realworld-audit.md",
    "benchmarks/lifecycle-realworld-heldout-v1/README.md": "benchmarks/heldout.md",
    "benchmarks/lifecycle-realworld-nearmiss-v1/README.md": "benchmarks/nearmiss.md",
}
STATIC = {
    "benchmarks/report_gpu_20261026_run3.html": "benchmarks/report_gpu_20261026_run3.html",
    "benchmarks/report_gpu_20261026.html": "benchmarks/report_gpu_20261026.html",
    "benchmarks/report_lifecycle_summary.html": "benchmarks/report_lifecycle_summary.html",
}
ALL = {**PAGES, **STATIC}
SOURCE_OF = {dest: src for src, dest in PAGES.items()}

FENCE = re.compile(r"^(```|~~~)", re.M)
MD_LINK = re.compile(r"(\]\()([^)\s#]+)(#[^)\s]*)?(\))")
CODE_SPAN = re.compile(r"(?<![`\[])`([^`\s]+\.(?:md|html))`(?!`|\])")


def on_files(files, config):
    for src, dest in ALL.items():
        path = os.path.join(REPO, *src.split("/"))
        if os.path.isfile(path):
            files.append(File.generated(config, dest, abs_src_path=path))
    return files


def _resolve(target, src_dir):
    """Repository path a relative link names, or None."""
    for base in (src_dir, ""):
        cand = posixpath.normpath(posixpath.join(base, target))
        if not cand.startswith("..") and os.path.exists(os.path.join(REPO, *cand.split("/"))):
            return cand
    return None


def _href(repo_path, page_dir):
    if repo_path in ALL:
        return posixpath.relpath(ALL[repo_path], page_dir)
    if repo_path.startswith("docs/"):
        return posixpath.relpath(repo_path[len("docs/"):], page_dir)
    return GITHUB + repo_path


def _rewrite(text, src_dir, page_dir):
    def link(m):
        if re.match(r"[a-z]+:", m.group(2)):
            return m.group(0)
        path = _resolve(m.group(2), src_dir)
        if not path:
            return m.group(0)
        return m.group(1) + _href(path, page_dir) + (m.group(3) or "") + m.group(4)

    def span(m):
        path = _resolve(m.group(1), src_dir)
        if path not in ALL:
            return m.group(0)
        return f"[`{m.group(1)}`]({_href(path, page_dir)})"

    return CODE_SPAN.sub(span, MD_LINK.sub(link, text))


def on_page_markdown(markdown, page, config, files):
    src = SOURCE_OF.get(page.file.src_uri)
    if not src:
        return markdown
    src_dir = posixpath.dirname(src)
    page_dir = posixpath.dirname(page.file.src_uri)
    # rewrite outside fenced code blocks only
    parts, out, inside = FENCE.split(markdown), [], False
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i % 2 == 1:  # a fence marker
            out.append(chunk)
            inside = not inside
        else:
            out.append(chunk if inside else _rewrite(chunk, src_dir, page_dir))
        i += 1
    note = (
        f"\n\n*Source: [`{src}`]({GITHUB + src}) in the repository; "
        "this page is built from it.*\n"
    )
    return "".join(out) + note
