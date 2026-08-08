"""
SLM Advisor for CV Pipeline.

Uses a small language model (text or vision) to review CV detection results
and identify elements that need splitting or retyping.

The SLM acts as a "smart reviewer" between CV detection and hierarchy
building. It does NOT generate coordinates — it only identifies problems
and the CV pipeline handles the actual splitting using text positions.

Supports:
- Text-only models: qwen2.5:3b (for retype suggestions)
- Vision models: minicpm-v, llava, qwen2.5-vl (can see the screenshot)
"""

import base64
import json
import re
from typing import List, Dict, Any, Optional, Tuple

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


# Models known to support vision
VISION_MODELS = {
    "minicpm-v", "llava", "llava:7b", "llava:13b",
    "qwen2.5-vl", "qwen2.5-vl:3b", "qwen2.5-vl:7b",
    "llava-phi3", "bakllava", "moondream",
}


class SLMAdvisor:
    """
    Small Language Model advisor for post-CV review.

    Reviews detected elements and suggests:
    - Which elements are likely merged and should be split
    - Which elements are misclassified
    - Which elements are noise

    Supports Ollama (recommended) and OpenAI backends.
    """

    def __init__(
        self,
        backend: str = "ollama",
        model: str = None,
        host: str = "http://localhost:11434",
        api_key: str = None,
        temperature: float = 0.3,
        timeout: int = 120,
    ):
        """
        Initialize SLM advisor.

        Args:
            backend: "ollama" or "openai"
            model: Model name (default: qwen2.5:3b for ollama, gpt-4o-mini for openai)
            host: Ollama server URL
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            temperature: Sampling temperature
            timeout: Request timeout in seconds
        """
        self.backend = backend
        self.host = host
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout

        if model:
            self.model = model
        elif backend == "ollama":
            self.model = "qwen2.5:3b"
        else:
            self.model = "gpt-4o-mini"

    @property
    def is_vision_model(self) -> bool:
        """Check if the configured model supports vision/images."""
        model_base = self.model.split(":")[0].lower()
        return model_base in VISION_MODELS

    def review_elements(
        self,
        elements: List[Dict[str, Any]],
        image_size: Tuple[int, int],
        image_path: str = None,
        merge_candidates: List[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Review CV-detected elements and return correction suggestions.

        Args:
            elements: List of element dicts from CV pipeline
            image_size: (width, height)
            image_path: Optional path to screenshot (used with vision models)
            merge_candidates: Optional list of id-groups that look over-segmented
                (from the pipeline's geometric analysis) for the SLM to confirm.

        Returns:
            List of suggestions, each a dict with:
            - "action": "split" | "retype" | "merge" | "label"
            - "id": target element ID (split/retype/label)
            - "reason": why
            - split: "texts" list of expected sub-element texts
            - retype: "type" new type
            - merge: "ids" list of element IDs to combine, optional "label"
            - label: "label" the element's semantic name
        """
        # Use vision prompt if we have an image and a VLM
        use_vision = self.is_vision_model and image_path
        prompt = self._build_review_prompt(elements, image_size, use_vision,
                                           merge_candidates=merge_candidates)

        if not prompt:
            log.info("SLM: no suspicious elements found, skipping")
            return []

        try:
            # Warm up: ensure model is loaded (first call can be slow)
            if self.backend == "ollama":
                self._warmup_ollama()

            # Log elements being reviewed
            mode = "VLM (with image)" if use_vision else "text-only"
            log.info(f"SLM reviewing {len(elements)} elements [{mode}], prompt: {len(prompt)} chars")
            for elem in elements:
                text = elem.get("ocr_text", "")
                if text:
                    eid = elem.get("id", "?")
                    vtype = elem.get("visual_type", "?")
                    bounds = elem.get("bounds", [0,0,0,0])
                    w = bounds[2] - bounds[0]
                    h = bounds[3] - bounds[1]
                    log.info(f"{eid}: {vtype} {w}x{h} text=\"{text}\"")

            # Encode image for VLM
            image_b64 = None
            if use_vision:
                image_b64 = self._encode_image(image_path)

            response = self._call_llm(prompt, image_b64=image_b64)
            log.info(f"SLM response ({len(response)} chars): {response[:300]}")
            suggestions = self._parse_suggestions(response)
            if suggestions:
                log.info(f"SLM parsed {len(suggestions)} suggestions")
            else:
                log.info(f"SLM: no actionable suggestions parsed")
            return suggestions
        except Exception as e:
            log.warning(f"SLM advisor failed: {e}")
            return []

    def _encode_image(self, image_path: str) -> Optional[str]:
        """Encode image to base64 for VLM API."""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            log.warning(f"could not encode image: {e}")
            return None

    def _warmup_ollama(self):
        """Pre-load the model in Ollama to avoid timeout on first real request."""
        import requests
        try:
            log.info("SLM: warming up model...")
            payload = {
                "model": self.model,
                "prompt": "hi",
                "stream": False,
                "options": {"num_predict": 1},
            }
            requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            log.info("SLM: model ready")
        except Exception:
            pass  # If warmup fails, the real call will report the error

    def _build_review_prompt(
        self,
        elements: List[Dict],
        image_size: Tuple[int, int],
        use_vision: bool = False,
        merge_candidates: List[List[str]] = None,
    ) -> str:
        """Build a focused prompt with suspicious elements + merge candidates."""
        img_w, img_h = image_size
        by_id = {e.get("id"): e for e in elements}

        # Filter to only suspicious elements to keep prompt short
        suspicious = []
        for elem in elements:
            text = elem.get("ocr_text", "")
            vtype = elem.get("visual_type", "unknown")
            if not text:
                continue

            is_suspicious = False

            # Text with spaces or mixed content → possibly merged
            if " " in text.strip():
                is_suspicious = True
            # Short text with mixed types (letter+number like "+12")
            if len(text) <= 4 and any(c.isdigit() for c in text) and any(not c.isdigit() for c in text):
                is_suspicious = True
            # Wrong type candidates
            if vtype in ("unknown", "checkbox", "input_field"):
                is_suspicious = True

            if is_suspicious:
                suspicious.append(elem)

        # Build merge-candidate section (over-segmentation groups to confirm)
        candidate_lines = []
        for group in (merge_candidates or []):
            parts = []
            for gid in group:
                e = by_id.get(gid)
                if e:
                    parts.append(f'{gid}="{e.get("ocr_text", "")}"')
            if len(parts) >= 2:
                candidate_lines.append("  [" + ", ".join(parts) + "]")
        candidates_text = "\n".join(candidate_lines)

        if not suspicious and not candidates_text:
            return ""

        merge_instr = ""
        if candidates_text:
            merge_instr = f"""

MERGE CANDIDATES (each group may be ONE element that got over-segmented, OR
separate elements like breadcrumb links — decide from the screenshot):
{candidates_text}
For each group that is truly one element, emit a merge with the correct full label.
"""

        lines = []
        for elem in suspicious:
            eid = elem.get("id", "?")
            vtype = elem.get("visual_type", "unknown")
            text = elem.get("ocr_text", "")
            bounds = elem.get("bounds", [0, 0, 0, 0])
            w = bounds[2] - bounds[0]
            h = bounds[3] - bounds[1]
            line = f'{eid}: type={vtype}, size={w}x{h}, text="{text}"'
            lines.append(line)

        elements_text = "\n".join(lines)

        if use_vision:
            return f"""You are a JSON API reviewing UI elements detected in this screenshot.
Judge every fix against what you actually SEE in the image, not against any
assumed app. Only report a fix when you are confident.

ELEMENTS:
{elements_text}
{merge_instr}
ACTIONS you may return (only when warranted):
1. SPLIT  - one box actually covers several separate controls side by side.
2. RETYPE - the visual_type is wrong (e.g. it is clearly a button, icon, or input).
3. MERGE  - several boxes are really ONE element (a multi-line control split into
   pieces, or a text line broken into fragments). Prefer the MERGE CANDIDATES above;
   do NOT merge distinct controls (e.g. separate buttons, breadcrumb links).
4. LABEL  - the element's human name: its own visible text, or the adjacent text
   label to its left/above for controls that have no text of their own.

Output ONLY a JSON array (empty [] if nothing needs fixing), no other text.
Schema (values are placeholders — use the real ids/text you see):
[{{"action":"split","id":"<id>","texts":["<part1>","<part2>"],"reason":"..."}},
 {{"action":"retype","id":"<id>","type":"button","reason":"..."}},
 {{"action":"merge","ids":["<id1>","<id2>"],"label":"<full text>","reason":"..."}},
 {{"action":"label","id":"<id>","label":"<name>","reason":"..."}}]

JSON:"""
        else:
            return f"""Review these UI elements detected in a screenshot and report only
warranted fixes. Do not invent problems.

ELEMENTS:
{elements_text}
{merge_instr}
ACTIONS you may return:
1. SPLIT  - text of one box contains several separate items → list the parts.
2. RETYPE - the visual_type looks wrong → give the correct type.
3. MERGE  - separate boxes that are really ONE element (see MERGE CANDIDATES);
   do NOT merge genuinely distinct controls.
4. LABEL  - the element's human name (its own text, or an adjacent label).

Output ONLY a JSON array (empty [] if nothing needs fixing).
Schema (placeholders — use the real ids/text):
[{{"action":"split","id":"<id>","texts":["<part1>","<part2>"],"reason":"..."}},
 {{"action":"retype","id":"<id>","type":"button","reason":"..."}},
 {{"action":"merge","ids":["<id1>","<id2>"],"label":"<full text>","reason":"..."}},
 {{"action":"label","id":"<id>","label":"<name>","reason":"..."}}]

Answer:"""

    def _call_llm(self, prompt: str, image_b64: str = None) -> str:
        """Call the LLM backend, optionally with an image for VLM."""
        import requests

        if self.backend == "ollama":
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": 1024,
                },
            }
            # Add image for vision models
            if image_b64:
                payload["images"] = [image_b64]

            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                raise RuntimeError(f"Ollama error: {response.status_code}")
            return response.json()["response"]

        elif self.backend == "openai":
            api_key = self.api_key
            if not api_key:
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not set")

            # Build message content
            content = []
            if image_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                })
            content.append({"type": "text", "text": prompt})

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "temperature": self.temperature,
                    "max_tokens": 1024,
                },
                timeout=self.timeout,
            )
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI error: {response.status_code}")
            return response.json()["choices"][0]["message"]["content"]

        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def _parse_suggestions(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM response into suggestion dicts."""
        response = response.strip()

        # Strip markdown code blocks
        if "```" in response:
            # Extract content between code blocks
            match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
            if match:
                response = match.group(1).strip()

        # Try direct parse
        try:
            result = json.loads(response)
            if isinstance(result, list):
                return [s for s in result if isinstance(s, dict) and "action" in s]
        except json.JSONDecodeError:
            pass

        # Try regex extraction of JSON array
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return [s for s in result if isinstance(s, dict) and "action" in s]
            except json.JSONDecodeError:
                pass

        # Last resort: extract individual JSON objects
        suggestions = []
        for obj_match in re.finditer(r'\{[^{}]+\}', response):
            try:
                obj = json.loads(obj_match.group())
                if isinstance(obj, dict) and "action" in obj:
                    suggestions.append(obj)
            except json.JSONDecodeError:
                continue
        return suggestions
