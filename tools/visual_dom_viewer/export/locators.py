"""
Locator strings the Viewer exports — and tries (ADR-028).

One place builds the locator for an element or a user definition, so the string
written to the Robot resource is exactly the string the Viewer's
"Click via actuator" resolves. Only properties the locator language understands
(`visual_gui_library.locators.LocatorStrategy`) become locator parts; the rest
are reported back instead of being written out and silently ignored by the
parser at test time.

Shape: ``<semantic AND-group> || id=E7``. The semantic part (text / role / hint)
survives a re-analysis; the element id is positional — the compiler numbers
elements in order, so it can shift when the screen changes — and is therefore
only the last-resort fallback (ADR-024), never AND-ed in, where it would make the
whole locator as fragile as the id alone.
"""

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

if TYPE_CHECKING:
    from ..core.element_definition import ElementDefinition
    from ..core.tree import DOMElement

#: Viewer property -> locator strategy, for properties with a locator equivalent.
#: "type" is the Viewer's display type, derived from the DOM's role/visual_type;
#: the locator language matches on the DOM ``role``, so it maps to that.
_PROPERTY_STRATEGY = {
    "text": "text",
    "hint": "hint",
    "type": "role",
    "role": "role",
}


def quote_value(value: Any) -> Optional[str]:
    """
    A locator value, quoted when it contains whitespace or the ``||`` chain
    separator (both would otherwise split it). The parser has no escape for a
    literal double quote, so a value containing one cannot be expressed:
    returns None rather than an altered value that would never match.
    """
    text = str(value)
    if '"' in text:
        return None
    needs_quotes = any(ch.isspace() for ch in text) or "||" in text
    return f'"{text}"' if needs_quotes else text


def expressible(value: Any) -> bool:
    """True when ``value`` can be written as a locator value (see quote_value)."""
    return value is not None and str(value).strip() != "" and quote_value(value) is not None


def build_locator(parts: Iterable[Tuple[str, Any]],
                  element_id: Optional[str] = None) -> str:
    """
    ``[("text", "Save"), ("role", "button")], "E7"`` ->
    ``text=Save role=button || id=E7``. Values the parser cannot express (empty,
    or containing a double quote) are dropped; the id alone is used when no
    semantic part remains.
    """
    seen = set()
    rendered = []
    for strategy, value in parts:
        if not expressible(value) or strategy in seen:
            continue
        seen.add(strategy)
        rendered.append(f"{strategy}={quote_value(value)}")
    primary = " ".join(rendered)
    if element_id:
        fallback = f"id={element_id}"
        return f"{primary} || {fallback}" if primary else fallback
    return primary


def element_locator(element: "DOMElement") -> str:
    """Default locator for an element: its text (or hint) and role, then its id."""
    props = element.properties or {}
    parts: List[Tuple[str, Any]] = []
    if expressible(element.text):
        parts.append(("text", element.text))
    elif expressible(props.get("hint")):
        parts.append(("hint", props["hint"]))
    role = props.get("role")
    if role and role != "unknown":
        parts.append(("role", role))
    return build_locator(parts, element.id)


def definition_locator(defn: "ElementDefinition") -> Tuple[str, List[str]]:
    """
    Locator for a user definition from the properties the user selected.

    Returns ``(locator, skipped)`` where ``skipped`` lists selected properties
    that have no locator equivalent (geometry, confidence, ...) and were left out.
    """
    values: Dict[str, Any] = defn.property_values or {}
    parts: List[Tuple[str, Any]] = []
    skipped: List[str] = []
    use_id = False
    # Stable order regardless of set iteration: text, hint, role, then the rest.
    order = {"text": 0, "hint": 1, "type": 2, "role": 2, "id": 3}
    for prop in sorted(defn.selected_properties, key=lambda p: (order.get(p, 9), p)):
        if prop == "id":
            use_id = True
            continue
        strategy = _PROPERTY_STRATEGY.get(prop)
        if strategy is None:
            skipped.append(prop)
            continue
        # The DOM role is the matchable value; the display type is only a fallback
        # for definitions saved without the raw role.
        value = values.get("role") if strategy == "role" else values.get(prop)
        if strategy == "role" and not value:
            value = values.get("type")
        if value == "unknown" or not expressible(value):
            skipped.append(prop)
            continue
        parts.append((strategy, value))
    locator = build_locator(parts, defn.element_id if (use_id or not parts) else None)
    return locator, skipped


__all__ = ["build_locator", "element_locator", "definition_locator", "expressible",
           "quote_value"]
