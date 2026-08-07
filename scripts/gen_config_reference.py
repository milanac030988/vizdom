"""
Generate the full config parameter reference in docs/CONFIGURATION.md.

The reference is derived from the source of truth — the config dataclasses
(names, types, defaults) plus the in-code ``_FIELD_HELP`` strings (meaning) —
and injected between markers in the docs page, so it cannot drift from the
code. ``tests/unit/test_config_reference.py`` fails whenever it is out of date;
re-run this script to fix.

Usage:
    python scripts/gen_config_reference.py            # rewrite the docs section
    python scripts/gen_config_reference.py --check    # exit 1 if out of date
"""

import re
import sys
from dataclasses import MISSING, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DOC = ROOT / "docs" / "CONFIGURATION.md"
BEGIN = "<!-- BEGIN GENERATED CONFIG REFERENCE (scripts/gen_config_reference.py) -->"
END = "<!-- END GENERATED CONFIG REFERENCE -->"


def _default_repr(f) -> str:
    if f.default is not MISSING:
        v = f.default
    elif f.default_factory is not MISSING:  # type: ignore[misc]
        v = f.default_factory()             # type: ignore[misc]
    else:
        return "—"
    if v is None:
        return "`null`"
    if isinstance(v, bool):
        return f"`{str(v).lower()}`"
    if isinstance(v, str):
        return f'`"{v}"`'
    return f"`{v!r}`"


def _type_repr(f) -> str:
    t = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str(f.type))
    t = t.replace("typing.", "").replace("Optional[", "").rstrip("]") \
        if "Optional[" in t else t
    return t.replace("List[str]", "list of str")


def generate() -> str:
    from visual_dom.config import VizDomConfig, _FIELD_HELP

    out = [BEGIN, ""]
    out.append("## 5. Full parameter reference")
    out.append("")
    out.append("Every field, generated from the config dataclasses and their in-code help")
    out.append("(the same text `--init` embeds as the template's `_help` block) — a unit test")
    out.append("keeps this section in sync with the code. `null` means \"use the default")
    out.append("described here\".")
    out.append("")
    for section in fields(VizDomConfig):
        sub = section.default_factory()
        title = _FIELD_HELP.get(section.name, "")
        out.append(f"### `{section.name}` — {title}")
        out.append("")
        out.append("| Parameter | Type | Default | Meaning |")
        out.append("|---|---|---|---|")
        for f in fields(sub):
            key = f"{section.name}.{f.name}"
            help_text = _FIELD_HELP.get(key)
            if help_text is None:
                raise SystemExit(
                    f"_FIELD_HELP has no entry for {key} - add one in "
                    f"src/visual_dom/config.py (the docs reference and the --init "
                    f"template both come from it).")
            help_text = help_text.replace("|", "\\|")
            out.append(f"| `{f.name}` | {_type_repr(f)} | {_default_repr(f)} | {help_text} |")
        out.append("")
    out.append(END)
    return "\n".join(out)


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    block = generate()
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        new = pattern.sub(lambda _: block, text)
    else:
        new = text.rstrip() + "\n\n" + block + "\n"

    if "--check" in sys.argv:
        if new != text:
            print("docs/CONFIGURATION.md parameter reference is OUT OF DATE - "
                  "run: python scripts/gen_config_reference.py")
            return 1
        print("config reference up to date")
        return 0

    DOC.write_text(new, encoding="utf-8")
    print(f"wrote parameter reference ({block.count(chr(10))} lines) into {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
