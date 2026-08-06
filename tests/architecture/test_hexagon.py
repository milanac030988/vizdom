"""
Architecture fitness test: enforce the hexagonal dependency direction.

The rule (ports & adapters): the domain **core** must not depend on concrete
**adapters** — dependencies point inward. `adapters/` may import `core/` (they
implement its ports); `core/` may only import `core/` and stdlib/third-party.

Rather than assert a clean slate that isn't true yet, this test pins the current
core -> adapter edges as a **known-debt ledger**. It fails if a *new* violation
appears, and flags when a known one is finally removed. The listed debts are the
pipeline newing-up concrete backends directly; they retire when OCR/refiner move
behind ports (the OmniParser-decomposition work, ADR-024).

Run: `pytest tests/architecture/` or `python tests/architecture/test_hexagon.py`.
"""
from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "visual_dom"
CORE = SRC / "core"

# (core file relative to src/visual_dom, imported adapter module) pairs that
# are currently tolerated. Every entry is a debt to be retired, not a licence.
KNOWN_DEBT = {
    ("core/domain/pipeline.py", "visual_dom.adapters.outbound.ocr.text_detector"),
    ("core/domain/pipeline.py", "visual_dom.adapters.outbound.detectors.uied_detection"),
    ("core/domain/pipeline.py", "visual_dom.adapters.outbound.refiner.slm_advisor"),
    ("core/domain/pipeline.py", "visual_dom.adapters.outbound.detectors"),
}


def _adapter_imports_in(pyfile: pathlib.Path):
    """Yield adapter module names imported by a core file (any depth, incl. lazy)."""
    tree = ast.parse(pyfile.read_text(encoding="utf-8"), filename=str(pyfile))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("visual_dom.adapters"):
                yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("visual_dom.adapters"):
                    yield alias.name


def _current_edges():
    edges = set()
    for py in CORE.rglob("*.py"):
        rel = py.relative_to(SRC).as_posix()
        for mod in _adapter_imports_in(py):
            edges.add((rel, mod))
    return edges


def test_core_does_not_import_adapters_beyond_known_debt():
    edges = _current_edges()
    new_violations = edges - KNOWN_DEBT
    assert not new_violations, (
        "New hexagon violation(s) — core/ must not import adapters/:\n"
        + "\n".join(f"  {f}  ->  {m}" for f, m in sorted(new_violations))
        + "\n(If intentional, move the dependency behind a port; do NOT add to "
        "KNOWN_DEBT without an ADR.)"
    )


def test_ports_are_pure():
    """Ports define interfaces only — they must not import adapters at all."""
    bad = set()
    for py in (CORE / "ports").rglob("*.py"):
        for mod in _adapter_imports_in(py):
            bad.add((py.relative_to(SRC).as_posix(), mod))
    assert not bad, "Ports must not import adapters:\n" + "\n".join(map(str, sorted(bad)))


def test_known_debt_is_still_real():
    """Flag debts that have been fixed so KNOWN_DEBT can be trimmed."""
    edges = _current_edges()
    retired = KNOWN_DEBT - edges
    assert not retired, (
        "These KNOWN_DEBT edges no longer exist — remove them from the ledger:\n"
        + "\n".join(f"  {f}  ->  {m}" for f, m in sorted(retired))
    )


if __name__ == "__main__":
    edges = _current_edges()
    print(f"core -> adapter edges found: {len(edges)}")
    for f, m in sorted(edges):
        tag = "known-debt" if (f, m) in KNOWN_DEBT else "** NEW VIOLATION **"
        print(f"  [{tag}] {f} -> {m}")
    new = edges - KNOWN_DEBT
    print("\nPASS" if not new else f"\nFAIL: {len(new)} new violation(s)")
