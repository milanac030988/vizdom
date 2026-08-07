"""
Drift guards for the config documentation (ADR-020).

1. Every config field must have a help string in ``_FIELD_HELP`` — that text is
   the single source for both the ``--init`` template's ``_help`` block and the
   generated docs reference.
2. The generated parameter reference inside docs/CONFIGURATION.md must match
   what the code would generate now. When this fails, run:

       python scripts/gen_config_reference.py
"""

import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def test_every_config_field_has_help():
    from visual_dom.config import VizDomConfig, _FIELD_HELP

    missing = [
        f"{section.name}.{f.name}"
        for section in fields(VizDomConfig)
        for f in fields(section.default_factory())
        if f"{section.name}.{f.name}" not in _FIELD_HELP
    ]
    assert not missing, (
        f"config fields without a _FIELD_HELP entry: {missing} - add them in "
        f"src/visual_dom/config.py")


def test_docs_reference_is_up_to_date():
    import gen_config_reference as gen

    text = gen.DOC.read_text(encoding="utf-8")
    block = gen.generate()
    assert gen.BEGIN in text and gen.END in text, (
        "docs/CONFIGURATION.md lost the generated-reference markers")
    current = text[text.index(gen.BEGIN): text.index(gen.END) + len(gen.END)]
    assert current == block, (
        "docs/CONFIGURATION.md parameter reference is out of date - run: "
        "python scripts/gen_config_reference.py")
