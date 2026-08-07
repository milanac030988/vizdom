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


def _tokens(s: str) -> List[str]:
    return _WORD_RE.findall((s or "").lower())


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

    Returns:
        (score, element) pairs with score > 0, best first.
    """
    desc_tokens = _tokens(description)
    if not desc_tokens:
        return []

    role_types: set = set()
    pos_preds = []
    name_tokens: List[str] = []
    for t in desc_tokens:
        if t in ROLE_WORDS:
            role_types |= ROLE_WORDS[t]
        elif t in POSITION_WORDS:
            pos_preds.append(POSITION_WORDS[t])
        else:
            name_tokens.append(t)

    ranked = []
    for elem in elements:
        score = 0.0

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
                score += 2.0 * overlap

        # role words
        if role_types:
            role = str(elem.get("role") or "").lower()
            vtype = str(elem.get("visual_type") or "").lower().replace("_", "")
            wanted = {r.replace("_", "") for r in role_types}
            if role.replace("_", "") in wanted or vtype in wanted:
                score += 1.0

        # positional words
        if pos_preds:
            cx, cy = _norm_center(elem, image_size)
            if all(p(cx, cy) for p in pos_preds):
                score += 0.5 * len(pos_preds)

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
        if "lexical" in self.tiers:
            ranked = lexical_rank(pool, description, self._image_size())
            elem = lexical_confident(ranked)
            if elem is not None:
                return elem, {"tier": "lexical", "reason": f"score={ranked[0][0]:.2f}",
                              "candidates": [e.get("id") for _, e in ranked[:5]]}

        candidates = [e for _, e in ranked[:8]] or pool

        # Positional words are deterministic geometry - small LMs reason poorly
        # about coordinates (a 3B model happily calls top-left "top right"), so
        # enforce them here: if the description names positions and some
        # candidates satisfy them, drop the ones that don't before any model.
        pos_preds = [POSITION_WORDS[t] for t in _tokens(description)
                     if t in POSITION_WORDS]
        if pos_preds:
            size = self._image_size()
            satisfying = [
                e for e in candidates
                if all(p(*_norm_center(e, size)) for p in pos_preds)
            ]
            if satisfying:
                candidates = satisfying

        if "slm" in self.tiers:
            elem, reason = self._resolve_slm(description, candidates)
            if elem is not None:
                return elem, {"tier": "slm", "reason": reason,
                              "candidates": [e.get("id") for e in candidates[:5]]}

        if "vlm" in self.tiers and self.screenshot is not None:
            elem, reason = self._resolve_vlm(description, candidates)
            if elem is not None:
                return elem, {"tier": "vlm", "reason": reason,
                              "candidates": [e.get("id") for e in candidates[:5]]}

        return None, {"tier": None, "reason": "no tier produced a confident match",
                      "candidates": [e.get("id") for _, e in ranked[:5]]}

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
        prompt = (
            "You match a natural-language description to ONE UI element.\n"
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
                "Which numbered box best matches the description?\n"
                'Reply with ONLY a JSON object: {"number": <int or null>, '
                '"confidence": 0.0-1.0}. Use null if none match.'
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
