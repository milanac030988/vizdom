"""
Description-based element resolution (ADR-022).

Resolves a natural-language locator like ``desc="settings button"`` against the
Visual DOM via a tiered escalation chain, each tier cheaper and more
deterministic than the next, stopping at the first confident hit:

* Tier 0 - lexical over DOM (no model, always available)
* Tier 1 - SLM over DOM (small text LM picks an element id; needs Ollama/OpenAI)
* Tier 2 - VLM over image via Set-of-Mark (numbered boxes; needs a vision model)

Cross-cutting: per-DOM caching, id validation (hallucinated ids rejected),
temperature 0, and every resolution records which tier answered.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Tier 0 - lexical scoring
# ---------------------------------------------------------------------------

# Words that describe an element's kind -> acceptable role/visual_type values.
ROLE_WORDS = {
    "button": {"button", "pushbutton"},
    "btn": {"button"},
    "key": {"button"},
    "icon": {"icon"},
    "glyph": {"icon"},
    "field": {"input_field", "textfield", "edittext"},
    "input": {"input_field", "textfield", "edittext"},
    "textbox": {"input_field", "textfield"},
    "box": {"input_field", "textfield", "checkbox"},
    "checkbox": {"checkbox"},
    "check": {"checkbox"},
    "toggle": {"checkbox", "switch"},
    "switch": {"checkbox", "switch"},
    "text": {"text", "statictext", "label"},
    "label": {"text", "statictext", "label"},
    "link": {"link", "text", "statictext"},
    "image": {"image", "icon"},
    "tab": {"tab", "button"},
    "menu": {"menu", "button"},
}

# Positional words -> predicate over normalized center (cx, cy in [0,1]).
POSITION_WORDS = {
    "top": lambda cx, cy: cy < 0.34,
    "bottom": lambda cx, cy: cy > 0.66,
    "left": lambda cx, cy: cx < 0.34,
    "right": lambda cx, cy: cx > 0.66,
    "center": lambda cx, cy: 0.25 < cx < 0.75 and 0.25 < cy < 0.75,
    "middle": lambda cx, cy: 0.25 < cx < 0.75 and 0.25 < cy < 0.75,
    "first": lambda cx, cy: True,   # ordering handled separately if ever needed
}

_WORD_RE = re.compile(r"[a-z0-9]+")

# Function words that never name an element. Only used to decide whether a
# description names something (see `lexical_rank`); they still take part in
# the overlap so that existing scores do not move.
_STOP_WORDS = {"the", "a", "an", "at", "of", "in", "on", "to", "for", "with",
               "that", "this", "which", "and", "or", "is", "it", "its", "one"}

# Words that qualify an element's look without naming it ("the small blue
# button at the top left"). Like the stop words they do not make a description
# "naming" (review, 2026-10-28, second round); the DOM has no field for them,
# so the lexical tier neither checks nor penalises them. Any other adjective
# still counts as a name, on purpose: an unknown word the element does not
# carry makes the tier decline rather than guess.
_QUALIFIER_WORDS = {
    "small", "big", "large", "little", "tiny", "huge", "wide", "narrow", "tall",
    "short", "long", "main", "primary", "secondary", "bold", "plain", "round",
    "square", "dark", "light", "bright", "blue", "red", "green", "yellow",
    "orange", "grey", "gray", "black", "white", "purple", "pink", "brown",
    "highlighted", "selected", "visible", "upper", "lower", "inner", "outer",
    "same", "other", "second", "third", "last", "only",
}

# A position word counts as a position only in a positional phrase: next to
# another position word ("top left"), after a preposition or article ("at the
# right", "the left field"), or before a part or role word ("right side",
# "left button"). Elsewhere it is an ordinary word: "right now", "left over",
# "right click" (review, 2026-10-28, second round: "the button that checks
# for updates right now" filtered every candidate with cx <= 0.66).
_POSITION_BEFORE = {"at", "on", "in", "to", "the", "near", "toward", "towards",
                    "from", "upper", "lower", "far"}
_POSITION_AFTER = {"side", "corner", "edge", "half", "area", "region", "pane",
                   "panel", "column", "row", "part", "hand", "most", "section",
                   "bar", "toolbar", "sidebar", "margin"} | set(ROLE_WORDS)


def _tokens(s: str) -> List[str]:
    return _WORD_RE.findall((s or "").lower())


def _is_positional(toks: List[str], i: int) -> bool:
    prev = toks[i - 1] if i > 0 else None
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if prev is None and nxt is None:
        return True                      # the whole description is "left"
    return (prev in POSITION_WORDS or nxt in POSITION_WORDS
            or prev in _POSITION_BEFORE or nxt in _POSITION_AFTER)


def parse_description(description: str):
    """
    Split a description into what it says about the element.

    Returns:
        (name_tokens, naming, role_types, pos_preds):
        name_tokens - every token that is neither a role word nor a position
                      (these take part in the overlap score);
        naming      - the name tokens that actually name something: stop
                      words and qualifiers removed ("the button at the top
                      left" names nothing, "Purple Elephant button" does);
        role_types  - acceptable role / visual_type values;
        pos_preds   - predicates over the normalized centre.
    """
    toks = _tokens(description)
    role_types: set = set()
    pos_preds = []
    name_tokens: List[str] = []
    for i, t in enumerate(toks):
        if t in ROLE_WORDS:
            role_types |= ROLE_WORDS[t]
        elif t in POSITION_WORDS and _is_positional(toks, i):
            pos_preds.append(POSITION_WORDS[t])
        else:
            name_tokens.append(t)
    naming = [t for t in name_tokens
              if t not in _STOP_WORDS and t not in _QUALIFIER_WORDS]
    return name_tokens, naming, role_types, pos_preds


def _norm_center(elem: Dict[str, Any], image_size) -> Tuple[float, float]:
    b = elem.get("bounds", [0, 0, 0, 0])
    cx = (b[0] + b[2]) / 2.0
    cy = (b[1] + b[3]) / 2.0
    if image_size:
        w, h = image_size
        if w and h:
            return cx / w, cy / h
    return 0.5, 0.5


def lexical_rank(
    elements: List[Dict[str, Any]],
    description: str,
    image_size: Optional[Tuple[int, int]] = None,
) -> List[Tuple[float, Dict[str, Any]]]:
    """
    Score every element against a description. Pure and deterministic.

    Score = 2.0 * name-token overlap (label/text/hint)
          + 1.0 * role-word match (role/visual_type)
          + 0.5 * positional-word match.

    Role and position words say *which kind* and *where*, not *which one*.
    When the description names something ("Purple Elephant button") and the
    element carries none of those words, they earn half credit, capped at
    1.0: enough to order a shortlist for the model tiers, never enough to
    clear `lexical_confident`'s floor on their own. Otherwise "top left
    Frobnicate button" would confidently resolve to whatever button sits
    top-left (review, 2026-10-28). A description that names nothing ("the
    small button at the top left") is unaffected; see `parse_description`
    for what counts as a name and when a word counts as a position.

    Returns:
        (score, element) pairs with score > 0, best first.
    """
    name_tokens, naming, role_types, pos_preds = parse_description(description)
    if not (name_tokens or role_types or pos_preds):
        return []

    ranked = []
    for elem in elements:
        name_score = 0.0

        # name-token overlap against label / text / hint
        if name_tokens:
            fields = " ".join(
                str(elem.get(k) or "") for k in ("label", "text", "hint")
            )
            elem_tokens = set(_tokens(fields))
            if elem_tokens:
                hits = sum(1 for t in name_tokens if t in elem_tokens)
                # substring bonus catches "setting" vs "settings"
                subs = sum(
                    1 for t in name_tokens
                    if t not in elem_tokens and any(t in e for e in elem_tokens)
                )
                overlap = (hits + 0.7 * subs) / len(name_tokens)
                name_score = 2.0 * overlap

        kind_score = 0.0

        # role words
        if role_types:
            role = str(elem.get("role") or "").lower()
            vtype = str(elem.get("visual_type") or "").lower().replace("_", "")
            wanted = {r.replace("_", "") for r in role_types}
            if role.replace("_", "") in wanted or vtype in wanted:
                kind_score += 1.0

        # positional words
        if pos_preds:
            cx, cy = _norm_center(elem, image_size)
            if all(p(cx, cy) for p in pos_preds):
                kind_score += 0.5 * len(pos_preds)

        if naming and name_score == 0:
            kind_score = min(0.5 * kind_score, 1.0)   # see the docstring
        score = name_score + kind_score

        if score > 0:
            ranked.append((score, elem))

    ranked.sort(key=lambda se: -se[0])
    return ranked


def lexical_confident(
    ranked: List[Tuple[float, Dict[str, Any]]],
    min_score: float = 1.5,
    min_margin: float = 0.5,
) -> Optional[Dict[str, Any]]:
    """The top element iff its score clears the floor AND the margin to #2."""
    if not ranked:
        return None
    top_score, top = ranked[0]
    if top_score < min_score:
        return None
    if len(ranked) > 1 and (top_score - ranked[1][0]) < min_margin:
        return None
    return top


# ---------------------------------------------------------------------------
# Resolver chain
# ---------------------------------------------------------------------------

class DescriptionResolver:
    """
    Resolve ``desc=`` locators via the tier chain configured in the session's
    ``grounding`` section. One instance per DOM (the cache is per-screen).
    """

    def __init__(
        self,
        dom: Dict[str, Any],
        screenshot=None,               # BGR ndarray, needed only for the vlm tier
        tiers: Optional[List[str]] = None,
        backend: str = "ollama",
        model: str = "qwen2.5:3b",
        vision_model: str = "qwen2.5-vl:3b",
        host: str = "http://localhost:11434",
    ):
        self.dom = dom
        self.elements = dom.get("elements", [])
        self.screenshot = screenshot
        self.tiers = list(tiers) if tiers else ["lexical", "slm"]
        self.backend = backend
        self.model = model
        self.vision_model = vision_model
        self.host = host
        self._cache: Dict[str, Tuple[Optional[Dict], Dict]] = {}

    # -- public ------------------------------------------------------------

    def resolve(
        self,
        description: str,
        within: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Resolve a description to an element.

        Args:
            description: The natural-language description.
            within: Optional restriction of the search space to these elements.
                Used to *disambiguate*: when a property locator (``text=+``)
                matched several elements, grounding the description over just
                those candidates is both cheaper and far more reliable than over
                the whole DOM — two candidates instead of fifty, so even the
                model-free lexical tier usually separates them, and the SLM/VLM
                tiers judge a short, focused list.

        Returns:
            (element or None, info) where info = {"tier": ..., "reason": ...,
            "candidates": [...ids...]} for logging / error messages.
        """
        key = description.strip().lower()
        if within is not None:
            key = (key, tuple(sorted(str(e.get("id")) for e in within)))
        if key in self._cache:
            return self._cache[key]

        result = self._resolve_uncached(description, within=within)
        self._cache[key] = result
        return result

    # -- tiers -------------------------------------------------------------

    def _image_size(self) -> Optional[Tuple[int, int]]:
        sz = self.dom.get("image_size")
        if isinstance(sz, dict):
            return sz.get("width"), sz.get("height")
        if isinstance(sz, (list, tuple)) and len(sz) == 2:
            return sz[0], sz[1]
        return None

    def _resolve_uncached(self, description: str, within=None):
        pool = within if within is not None else self.elements
        ranked = []
        # Each tier's own verdict is kept so that a miss explains itself:
        # "no confident match" alone cannot tell a null answer from an
        # out-of-range mark or a low confidence (lifecycle run 4, 2026-10-27).
        why: List[str] = []
        if "lexical" in self.tiers:
            ranked = lexical_rank(pool, description, self._image_size())
            elem = lexical_confident(ranked)
            if elem is not None:
                return elem, {"tier": "lexical", "reason": f"score={ranked[0][0]:.2f}",
                              "candidates": [e.get("id") for _, e in ranked[:5]]}
            why.append(self._lexical_why(ranked))

        # Positional words are deterministic geometry - small LMs reason poorly
        # about coordinates (a 3B model happily calls top-left "top right"), so
        # they are enforced here, not by the model: candidates that are not
        # where the description says are filtered out BEFORE the shortlist is
        # padded (filtering after padding could cut the table back to one row,
        # the case SHORTLIST_MIN exists for - review, 2026-10-28), and a model
        # answer that lands outside the described position is rejected.
        in_place = self._position_predicate(description, pool)
        candidates = self._shortlist(ranked, pool, in_place)

        if "slm" in self.tiers:
            elem, reason = self._resolve_slm(description, candidates)
            elem, reason = self._enforce_position("slm", elem, reason, in_place)
            if elem is not None:
                return elem, {"tier": "slm", "reason": reason,
                              "candidates": [e.get("id") for e in candidates[:5]]}
            why.append(reason)

        if "vlm" in self.tiers:
            if self.screenshot is None:
                why.append("vlm skipped: no screenshot")
            else:
                elem, reason = self._resolve_vlm(description, candidates)
                elem, reason = self._enforce_position("vlm", elem, reason, in_place)
                if elem is not None:
                    return elem, {"tier": "vlm", "reason": reason,
                                  "candidates": [e.get("id") for e in candidates[:5]]}
                why.append(reason)

        return None, {"tier": None,
                      "reason": "no confident match (" + "; ".join(why) + ")",
                      "candidates": [e.get("id") for _, e in ranked[:5]]}

    #: the model tiers see at most this many candidates ...
    SHORTLIST_MAX = 8
    #: ... and at least this many. A table of ONE row turns "which of these
    #: matches?" into "is this it?", and a 3B model says yes to a plausible-
    #: sounding name: lifecycle run 4's single false pass ("Purple Elephant
    #: button" -> the only button of a dialog whose other button OCR had not
    #: read, confidence 0.85). With two or more rows the same model declines.
    #: Lifecycle run 6 confirmed it: the same step declines at 0.00 and the
    #: chain's false-pass is 0 of 88.
    SHORTLIST_MIN = 3

    @classmethod
    def _shortlist(cls, ranked: List[Tuple[float, Dict[str, Any]]],
                   pool: List[Dict[str, Any]], in_place=None) -> List[Dict[str, Any]]:
        """The candidates handed to the model tiers: the lexical top-8, padded
        from the pool (in DOM order) to at least SHORTLIST_MIN so the model
        always has a real choice; the whole pool when nothing scored.

        `in_place`, when given, is the description's positional predicate
        (see `_position_predicate`): scored candidates that fail it are
        dropped first, and padding prefers pool elements that pass it, so
        the filter can never leave the model a one-row table."""
        keep = in_place or (lambda e: True)
        cands = [e for _, e in ranked[:cls.SHORTLIST_MAX] if keep(e)]
        if not cands:
            cands = [e for e in pool if keep(e)]
        if len(cands) < cls.SHORTLIST_MIN:
            seen = {id(e) for e in cands}
            # elements in the described place first, then the rest in DOM order
            for e in [e for e in pool if keep(e)] + [e for e in pool if not keep(e)]:
                if len(cands) >= cls.SHORTLIST_MIN:
                    break
                if id(e) not in seen:
                    cands.append(e)
                    seen.add(id(e))
        return cands

    def _position_predicate(self, description: str, pool: List[Dict[str, Any]]):
        """A predicate over elements for the description's position words
        ("top", "left", ...), or None when it has none or nothing in the
        pool satisfies them (then the words are not used as a filter)."""
        pos_preds = parse_description(description)[3]
        if not pos_preds:
            return None
        size = self._image_size()

        def in_place(e):
            return all(p(*_norm_center(e, size)) for p in pos_preds)

        return in_place if any(in_place(e) for e in pool) else None

    @staticmethod
    def _enforce_position(tier: str, elem, reason: str, in_place):
        """A model answer that is not where the description says is a miss,
        not a match: the padded rows of the shortlist may lie elsewhere."""
        if elem is not None and in_place is not None and not in_place(elem):
            return None, (f"{tier} picked {elem.get('id')} outside the described "
                          f"position ({reason})")
        return elem, reason

    @staticmethod
    def _lexical_why(ranked: List[Tuple[float, Dict[str, Any]]],
                     min_score: float = 1.5, min_margin: float = 0.5) -> str:
        """Why lexical_confident() declined, in the words a log reader needs."""
        if not ranked:
            return "lexical: no element shares a token or role word"
        top = ranked[0][0]
        if top < min_score:
            return f"lexical: best score {top:.2f} < {min_score}"
        second = ranked[1][0]
        tied = sum(1 for s, _ in ranked if top - s < min_margin)
        return (f"lexical: tie at {top:.2f} between {tied} candidates "
                f"(runner-up {second:.2f}, margin < {min_margin})")

    # -- tier 1: SLM over DOM ---------------------------------------------

    def _element_table(self, elements: List[Dict[str, Any]]) -> str:
        """Compact, prompt-friendly table of candidate elements."""
        size = self._image_size() or (1, 1)
        w, h = (size[0] or 1), (size[1] or 1)
        lines = []
        for e in elements:
            b = e.get("bounds", [0, 0, 0, 0])
            cx, cy = (b[0] + b[2]) / 2 / w, (b[1] + b[3]) / 2 / h
            parts = [
                f"id={e.get('id')}",
                f"role={e.get('role') or e.get('visual_type')}",
            ]
            if e.get("text"):
                parts.append(f"text={e['text']!r}")
            if e.get("label") and e.get("label") != e.get("text"):
                parts.append(f"label={e['label']!r}")
            if e.get("hint"):
                parts.append(f"hint={e['hint']!r}")
            parts.append(f"center=({cx:.2f},{cy:.2f})")
            lines.append("  " + " ".join(parts))
        return "\n".join(lines)

    def _make_advisor(self, model: str):
        from visual_dom.adapters.outbound.refiner.slm_advisor import SLMAdvisor
        return SLMAdvisor(backend=self.backend, model=model, host=self.host,
                          temperature=0.0)

    def _resolve_slm(self, description: str, candidates: List[Dict[str, Any]]):
        """Ask a text LM to pick the best-matching element id from the table."""
        table = self._element_table(candidates)
        # Keep the wording plain. An explanatory null rule ("answer null
        # unless text or role clearly corresponds; a matching role alone is
        # NOT a match", 22e50c0) made the 3B model *more* willing to answer
        # on long tables: on the whole DOM it picked a button for six of six
        # nonsense captions (lifecycle run 6, slm-only column, false-pass
        # 0.020 -> 0.126; reproduced on the laptop against the same model,
        # where the plain wording below declines five of the six). The
        # one-row case that motivated the rule is handled by the shortlist
        # padding (SHORTLIST_MIN), not by the prompt.
        prompt = (
            "You match a natural-language description to ONE UI element, "
            "or to none.\n"
            f"Description: {description!r}\n"
            "Elements (center is normalized 0-1, (0,0)=top-left):\n"
            f"{table}\n\n"
            "Reply with ONLY a JSON object: "
            '{"id": "<element id or null>", "confidence": 0.0-1.0, "reason": "..."}\n'
            "Use null if no element matches the description."
        )
        try:
            advisor = self._make_advisor(self.model)
            response = advisor._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001 - service down is a soft failure
            return None, f"slm unavailable: {exc}"

        parsed = self._parse_id_json(response)
        if not parsed:
            return None, "unparseable slm response"
        elem_id, conf, reason = parsed
        if elem_id is None or conf < 0.5:
            return None, f"slm not confident ({conf:.2f})"
        # Validate against the DOM - a hallucinated id is rejected.
        by_id = {str(e.get("id")): e for e in self.elements}
        elem = by_id.get(str(elem_id))
        if elem is None:
            return None, f"slm returned unknown id {elem_id!r}"
        return elem, f"conf={conf:.2f}: {reason}"

    # -- tier 2: VLM over image via Set-of-Mark ----------------------------

    def _resolve_vlm(self, description: str, candidates: List[Dict[str, Any]]):
        """
        Set-of-Mark grounding: draw numbered boxes for the candidate elements
        on the screenshot and ask a vision model WHICH NUMBER matches. The
        answer is a DOM element by construction (no coordinate regression).
        """
        try:
            import cv2
            import base64 as b64
            import tempfile
            import os

            marks = candidates[:20]  # keep the overlay legible
            canvas = self.screenshot.copy()
            for i, e in enumerate(marks, start=1):
                x1, y1, x2, y2 = e.get("bounds", [0, 0, 0, 0])
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(canvas, str(i), (x1 + 2, max(12, y1 + 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            cv2.imwrite(path, canvas)
            with open(path, "rb") as fh:
                image_b64 = b64.b64encode(fh.read()).decode("utf-8")
            os.unlink(path)

            prompt = (
                "The screenshot shows UI elements marked with red numbered boxes.\n"
                f"Description: {description!r}\n"
                "Which numbered box matches the description? The description "
                "may refer to nothing that is marked; answer null unless a box "
                "clearly shows it.\n"
                'Reply with ONLY a JSON object: {"number": <int or null>, '
                '"confidence": 0.0-1.0}.'
            )
            advisor = self._make_advisor(self.vision_model)
            response = advisor._call_llm(prompt, image_b64=image_b64)
        except Exception as exc:  # noqa: BLE001
            return None, f"vlm unavailable: {exc}"

        m = re.search(r'"number"\s*:\s*(\d+|null)', response or "")
        if not m or m.group(1) == "null":
            return None, "vlm found no match"
        idx = int(m.group(1))
        if not (1 <= idx <= len(marks)):
            return None, f"vlm returned out-of-range mark {idx}"
        conf_m = re.search(r'"confidence"\s*:\s*([0-9.]+)', response or "")
        conf = float(conf_m.group(1)) if conf_m else 0.0
        if conf < 0.5:
            return None, f"vlm not confident ({conf:.2f})"
        return marks[idx - 1], f"mark #{idx}, conf={conf:.2f}"

    # -- parsing -----------------------------------------------------------

    @staticmethod
    def _parse_id_json(response: str):
        """Extract {"id":..., "confidence":..., "reason":...} from a reply."""
        if not response:
            return None
        m = re.search(r"\{.*\}", response, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        elem_id = data.get("id")
        if isinstance(elem_id, str) and elem_id.lower() in ("null", "none", ""):
            elem_id = None
        try:
            conf = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        return elem_id, conf, str(data.get("reason", ""))
