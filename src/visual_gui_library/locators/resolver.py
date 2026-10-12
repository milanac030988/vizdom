"""
Locator resolution — one locator string to exactly one element (ADR-024, ADR-028).

This is the logic behind the ``Get Visual Element`` keyword, kept free of Robot
Framework so every client resolves a locator the same way: the RF library at test
runtime, and the Viewer when it *tries* a locator before the test is written
(ADR-028). A locator that fails here fails in the suite, and vice versa.

What it adds on top of `ElementFinder` (which only intersects one AND-group):

- **Fallback chains** (ADR-024): alternatives separated by ``||`` are tried in
  order; the first that resolves to exactly one element wins.
- **desc= escalation** (ADR-022): a lone ``desc=`` that the finder's lexical tier
  misses is escalated through the configured grounding tiers.
- **Ambiguity arbitration** (ADR-024): when a property alternative matches
  several elements, a ``desc=`` elsewhere in the chain judges which one was meant.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from visual_dom.logging_utils import get_logger

from .locator import ElementFinder, LocatorParser, LocatorStrategy

log = get_logger(__name__)


@dataclass
class Resolution:
    """Outcome of resolving a locator chain."""

    locator: str
    element: Optional[Dict[str, Any]] = None
    #: 0-based index of the alternative that resolved (None when nothing did)
    alternative: Optional[int] = None
    #: rendered text of the alternative that resolved
    rendered: Optional[str] = None
    #: (rendered alternative, why it did not resolve) for every alternative tried
    #: before the winner — or all of them on a miss
    attempts: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.element is not None

    @property
    def used_fallback(self) -> bool:
        """A later alternative won: the primary locator may have gone stale."""
        return bool(self.alternative)

    def error_message(self) -> str:
        """The message `LocatorResolver.resolve` raises with on a miss."""
        if not self.attempts:
            return f"Could not parse locator: {self.locator!r}"
        detail = "; ".join(f"#{i + 1} '{r}' -> {why}"
                           for i, (r, why) in enumerate(self.attempts))
        # "not found" would be wrong when the cause was ambiguity, so state the
        # actual contract that failed: exactly one element.
        if len(self.attempts) == 1 and self.attempts[0][1] == "not found":
            return f"Element not found: {self.locator}"
        return (f"Locator did not resolve to exactly one element: {self.locator} "
                f"[tried {detail}]")


def default_desc_resolver_factory(dom: Dict[str, Any], screenshot=None,
                                  grounding=None) -> Callable[[], Any]:
    """
    A lazy `DescriptionResolver` builder for ``dom``. ``grounding`` is the
    ``VizDomConfig.grounding`` section (ADR-022), or None for the defaults.
    """
    cache: Dict[str, Any] = {}

    def factory():
        if "resolver" not in cache:
            from .desc_resolver import DescriptionResolver
            g = grounding
            cache["resolver"] = DescriptionResolver(
                dom,
                screenshot=screenshot,
                tiers=(list(g.tiers) if g else None),
                backend=(g.backend if g else "ollama"),
                model=(g.model if g else "qwen2.5:3b"),
                vision_model=(g.vision_model if g else "qwen2.5-vl:3b"),
                host=(g.host if g else "http://localhost:11434"),
            )
        return cache["resolver"]

    return factory


class LocatorResolver:
    """Resolve locator strings (with ``||`` chains) against one DOM."""

    def __init__(self, finder: ElementFinder,
                 desc_resolver_factory: Optional[Callable[[], Any]] = None):
        """
        Args:
            finder: `ElementFinder` over the DOM to resolve against.
            desc_resolver_factory: zero-argument callable returning the
                `DescriptionResolver` for this DOM; called only when a ``desc=``
                needs escalation or arbitration. Defaults to one built from
                ``finder.dom`` with the default grounding settings.
        """
        self._finder = finder
        self._desc_factory = (desc_resolver_factory
                              or default_desc_resolver_factory(finder.dom))

    @classmethod
    def for_dom(cls, dom: Dict[str, Any], screenshot=None,
                grounding=None) -> "LocatorResolver":
        """Resolver over ``dom`` with grounding from a config section (or defaults)."""
        return cls(ElementFinder(dom),
                   default_desc_resolver_factory(dom, screenshot, grounding))

    # -- public ------------------------------------------------------------

    def resolve(self, locator: str) -> Dict[str, Any]:
        """
        The element ``locator`` resolves to; raises ValueError unless exactly one
        element is found. Logs a warning when a fallback alternative won.
        """
        result = self.explain(locator)
        if not result.ok:
            raise ValueError(result.error_message())
        if result.used_fallback:
            failed = "; ".join(f"{r} ({why})" for r, why in result.attempts)
            log.warning(f"locator fallback — used alternative #{result.alternative + 1} "
                        f"'{result.rendered}' -> {result.element.get('id')}; earlier "
                        f"alternative(s) failed: {failed}. The primary locator may be stale.")
        return result.element

    def explain(self, locator: str) -> Resolution:
        """Resolve without raising; report which alternative won and why others failed."""
        result = Resolution(locator=locator)
        alternatives = LocatorParser.parse_alternatives(locator)
        if not alternatives:
            return result

        # Descriptions available for AMBIGUITY ARBITRATION: when a property
        # locator matches several elements, a desc= elsewhere in the chain can
        # judge WHICH of those candidates was meant — grounding over 2-3
        # candidates is far more reliable than over the whole DOM, so this
        # rescues chains like `text=+ || desc="plus button"` where the ± key's
        # composite glyph also OCRs as "+".
        desc_values = [g[0].value for g in alternatives
                       if len(g) == 1 and g[0].strategy == LocatorStrategy.DESC]

        for index, group in enumerate(alternatives):
            element, reason = self._resolve_alternative(group)
            rendered = LocatorParser.render(group)
            if element is None and desc_values and "Multiple elements match" in reason:
                element = self._disambiguate_with_desc(group, rendered, desc_values)
            if element is not None:
                result.element = element
                result.alternative = index
                result.rendered = rendered
                return result
            result.attempts.append((rendered, reason))
        return result

    def resolve_all(self, locator: str) -> List[Dict[str, Any]]:
        """
        Every element the chain matches: the first alternative that matches
        anything wins; many matches are expected here by design.
        """
        for group in LocatorParser.parse_alternatives(locator):
            found = self._finder.find(group)
            if found:
                return found
        return []

    # -- internals ---------------------------------------------------------

    def _resolve_alternative(self, locators) -> tuple:
        """
        Resolve ONE alternative (an AND-group of locators) to a single element.

        Returns (element_or_None, reason). `reason` explains a miss so a failed
        chain can report why each alternative did not resolve.
        """
        try:
            element = self._finder.find_one(locators)
        except ValueError as exc:              # find_one raises on ambiguity
            return None, str(exc)
        if element is not None:
            return element, "ok"

        # desc= escalation (ADR-022): the finder only runs the deterministic
        # lexical tier. If that missed and this alternative is a lone
        # description, escalate through the configured chain (SLM over DOM,
        # optionally VLM Set-of-Mark over the screenshot).
        if len(locators) == 1 and locators[0].strategy == LocatorStrategy.DESC:
            resolver = self._desc_factory()
            element, info = resolver.resolve(locators[0].value)
            if element is not None:
                log.info(f"desc= resolved by tier '{info['tier']}' "
                         f"({info['reason']}) -> {element.get('id')}")
                return element, "ok"
            cands = ", ".join(str(c) for c in info.get("candidates", [])) or "none"
            return None, f"no grounding tier confident (nearest: {cands})"

        return None, "not found"

    def _disambiguate_with_desc(self, group, rendered: str, desc_values) -> Optional[dict]:
        """
        Ambiguity arbitration (ADR-024): a property locator matched SEVERAL
        elements — let a desc= from the same chain judge which one was meant,
        by grounding the description over just those candidates.

        This runs *before* falling through to the next alternative, because the
        ambiguous matches carry real information: the wanted element is almost
        certainly among them, and a 2-3 element pool is exactly where grounding
        is at its most reliable. Not confident -> return None and the chain
        continues unchanged, so this can rescue a resolution but never corrupt one.
        """
        try:
            candidates = self._finder.find(group)
        except Exception:
            return None
        if len(candidates) < 2:
            return None
        resolver = self._desc_factory()
        for desc in desc_values:
            element, info = resolver.resolve(desc, within=candidates)
            if element is not None:
                ids = ", ".join(str(c.get("id")) for c in candidates)
                log.info(f"'{rendered}' matched {len(candidates)} elements "
                         f"({ids}); desc={desc!r} disambiguated to "
                         f"{element.get('id')} (tier '{info['tier']}', {info['reason']})")
                return element
        return None


__all__ = ["LocatorResolver", "Resolution", "default_desc_resolver_factory"]
