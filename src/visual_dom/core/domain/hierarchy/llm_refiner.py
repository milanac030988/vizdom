"""
LLM-based hierarchy refinement.

Uses a small language model (SLM) to refine the coarse hierarchy:
- Merge over-segmented elements (text split into parts)
- Split merged elements (multiple buttons as one)
- Fix visual_type classifications
- Correct parent-child relationships
- Add semantic roles and flags

Supported models:
- Qwen2.5-3B-Instruct (recommended)
- Phi-3.5-mini-instruct
- Gemma-2-2B-it
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum


class EditOperation(Enum):
    """Allowed tree edit operations."""
    SET_PARENT = "set_parent"
    SET_TYPE = "set_type"
    SET_ROLE = "set_role"
    MERGE_ELEMENTS = "merge_elements"
    SPLIT_ELEMENT = "split_element"
    DELETE_ELEMENT = "delete_element"
    SET_TEXT = "set_text"


@dataclass
class TreeEdit:
    """A single tree edit operation from LLM."""
    operation: EditOperation
    target_id: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation.value,
            "target_id": self.target_id,
            "params": self.params
        }


class LLMHierarchyRefiner:
    """
    Refine DOM hierarchy using a small language model.

    The LLM receives:
    - List of detected elements with positions, types, OCR text
    - Draft hierarchy from coarse builder

    The LLM outputs:
    - Tree edits to improve the hierarchy
    - Does NOT generate coordinates (those come from CV only)
    """

    # Supported model configurations
    MODEL_CONFIGS = {
        "qwen2.5-3b": {
            "hf_name": "Qwen/Qwen2.5-3B-Instruct",
            "type": "transformers",
            "max_tokens": 4096,
        },
        "phi-3.5": {
            "hf_name": "microsoft/Phi-3.5-mini-instruct",
            "type": "transformers",
            "max_tokens": 4096,
        },
        "gemma-2-2b": {
            "hf_name": "google/gemma-2-2b-it",
            "type": "transformers",
            "max_tokens": 4096,
        },
        "ollama": {
            "type": "ollama",
            "model": "qwen2.5:3b",
            "max_tokens": 4096,
        },
        "openai": {
            "type": "openai",
            "model": "gpt-4o-mini",
            "max_tokens": 4096,
        },
    }

    def __init__(
        self,
        model_name: str = "qwen2.5-3b",
        use_gpu: bool = True,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        ollama_host: str = "http://localhost:11434",
        openai_api_key: str = None,
    ):
        """
        Initialize LLM refiner.

        Args:
            model_name: Model name (qwen2.5-3b, phi-3.5, gemma-2-2b, ollama, openai)
            use_gpu: Use GPU for local models
            max_tokens: Maximum tokens for LLM response
            temperature: Sampling temperature (lower = more deterministic)
            ollama_host: Ollama server URL (for ollama backend)
            openai_api_key: OpenAI API key (for openai backend)
        """
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.ollama_host = ollama_host
        self.openai_api_key = openai_api_key

        self._model = None
        self._tokenizer = None
        self._initialized = False

        # Get model config
        if model_name in self.MODEL_CONFIGS:
            self.config = self.MODEL_CONFIGS[model_name]
        else:
            # Assume it's a HuggingFace model name
            self.config = {
                "hf_name": model_name,
                "type": "transformers",
                "max_tokens": max_tokens,
            }

    def _init_model(self):
        """Lazy initialization of LLM."""
        if self._initialized:
            return

        model_type = self.config.get("type", "transformers")

        if model_type == "transformers":
            self._init_transformers()
        elif model_type == "ollama":
            self._init_ollama()
        elif model_type == "openai":
            self._init_openai()
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        self._initialized = True

    def _init_transformers(self):
        """Initialize HuggingFace Transformers model."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            hf_name = self.config["hf_name"]
            print(f"Loading model: {hf_name}")

            self._tokenizer = AutoTokenizer.from_pretrained(hf_name)

            device_map = "auto" if self.use_gpu else "cpu"
            dtype = torch.float16 if self.use_gpu else torch.float32

            self._model = AutoModelForCausalLM.from_pretrained(
                hf_name,
                device_map=device_map,
                torch_dtype=dtype,
                trust_remote_code=True,
            )

            print(f"Model loaded successfully")

        except ImportError:
            raise ImportError(
                "transformers not installed. Run: pip install transformers torch"
            )

    def _init_ollama(self):
        """Initialize Ollama client."""
        # Ollama doesn't need initialization, just verify connection
        try:
            import requests
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code != 200:
                raise ConnectionError(f"Ollama not responding at {self.ollama_host}")
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.ollama_host}: {e}\n"
                "Make sure Ollama is running: ollama serve"
            )

    def _init_openai(self):
        """Initialize OpenAI client."""
        if not self.openai_api_key:
            import os
            self.openai_api_key = os.environ.get("OPENAI_API_KEY")

        if not self.openai_api_key:
            raise ValueError(
                "OpenAI API key not provided. Set OPENAI_API_KEY or pass openai_api_key"
            )

    def _generate(self, prompt: str) -> str:
        """Generate response from LLM."""
        model_type = self.config.get("type", "transformers")

        if model_type == "transformers":
            return self._generate_transformers(prompt)
        elif model_type == "ollama":
            return self._generate_ollama(prompt)
        elif model_type == "openai":
            return self._generate_openai(prompt)

    def _generate_transformers(self, prompt: str) -> str:
        """Generate using HuggingFace Transformers."""
        messages = [{"role": "user", "content": prompt}]

        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self._tokenizer(text, return_tensors="pt")
        if self.use_gpu:
            inputs = inputs.to(self._model.device)

        outputs = self._model.generate(
            **inputs,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            do_sample=self.temperature > 0,
            pad_token_id=self._tokenizer.eos_token_id,
        )

        response = self._tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )

        return response

    def _generate_ollama(self, prompt: str) -> str:
        """Generate using Ollama."""
        import requests

        model = self.config.get("model", "qwen2.5:3b")

        response = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                }
            },
            timeout=120
        )

        if response.status_code != 200:
            raise RuntimeError(f"Ollama error: {response.text}")

        return response.json()["response"]

    def _generate_openai(self, prompt: str) -> str:
        """Generate using OpenAI API."""
        import requests

        model = self.config.get("model", "gpt-4o-mini")

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
            timeout=60
        )

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI error: {response.text}")

        return response.json()["choices"][0]["message"]["content"]

    def refine(
        self,
        elements: List[Dict],
        hierarchy: Dict = None,
        image_size: Tuple[int, int] = None,
    ) -> Dict[str, Any]:
        """
        Refine hierarchy using LLM.

        Args:
            elements: List of detected elements from CV pipeline
            hierarchy: Current hierarchy from coarse builder (optional)
            image_size: (width, height) of the image

        Returns:
            Dictionary with:
            - "edits": List of TreeEdit operations
            - "refined_elements": Elements after applying edits
            - "llm_response": Raw LLM response
        """
        self._init_model()

        # Build prompt
        prompt = self._build_prompt(elements, hierarchy, image_size)

        # Generate response
        print("Calling LLM for hierarchy refinement...")
        response = self._generate(prompt)
        print(f"LLM response received ({len(response)} chars)")

        # Parse edits
        edits = self._parse_response(response)
        print(f"Parsed {len(edits)} edit operations")

        # Debug: save raw response if no edits found
        if not edits and response:
            print(f"LLM response preview: {response[:500]}...")
            # Save full response for debugging
            with open("llm_response_debug.txt", "w", encoding="utf-8") as f:
                f.write(response)

        # Apply edits
        refined_elements = self._apply_edits(elements, edits)

        return {
            "edits": [e.to_dict() for e in edits],
            "refined_elements": refined_elements,
            "llm_response": response,
        }

    def _build_prompt(
        self,
        elements: List[Dict],
        hierarchy: Dict = None,
        image_size: Tuple[int, int] = None
    ) -> str:
        """Build prompt for LLM."""

        # Format elements with relative positions
        elements_text = self._format_elements(elements, image_size)

        prompt = f"""You are a UI element analyzer. Given detected UI elements from a screenshot, analyze and suggest improvements.

## DETECTED ELEMENTS:
{elements_text}

## YOUR TASK:
Analyze these elements and output a JSON array of edit operations to improve the detection:

1. **MERGE** - If text was split into multiple parts, merge them:
   {{"op": "merge", "ids": ["E1", "E2"], "text": "combined text"}}

2. **SPLIT** - If one element contains multiple items (e.g., "4 5 7 8" should be 4 buttons):
   {{"op": "split", "id": "E7", "into": ["4", "5", "7", "8"], "type": "button"}}

3. **RETYPE** - If element type is wrong:
   {{"op": "retype", "id": "E5", "type": "button"}}  (valid types: button, text, input_field, checkbox, icon, image, container)

4. **DELETE** - If element is noise/duplicate:
   {{"op": "delete", "id": "E10"}}

5. **SET_ROLE** - Add semantic role:
   {{"op": "role", "id": "E3", "role": "submit_button"}}

## RULES:
- Output ONLY a valid JSON array, nothing else
- Do NOT generate new coordinates - CV provides those
- Be VERY conservative - only suggest changes you're confident about
- Focus on fixing obvious errors like split text or merged buttons
- IMPORTANT: Only DELETE elements that are clearly duplicates or noise artifacts
- Do NOT delete elements just because they lack text - buttons and icons often have no text
- When in doubt, prefer RETYPE over DELETE
- If no edits needed, output: []

## OUTPUT FORMAT:
You must output ONLY a JSON array starting with [ and ending with ].
Example valid output:
[{{"op": "retype", "id": "E5", "type": "button"}}, {{"op": "delete", "id": "E10"}}]

If no changes needed:
[]

YOUR RESPONSE (JSON array only):"""

        return prompt

    def _format_elements(
        self,
        elements: List[Dict],
        image_size: Tuple[int, int] = None
    ) -> str:
        """Format elements for the prompt."""
        lines = []

        # Get image dimensions for relative positioning
        img_w = image_size[0] if image_size else 1000
        img_h = image_size[1] if image_size else 1000

        for elem in elements:
            elem_id = elem.get("id", "?")
            bounds = elem.get("bounds", [0, 0, 0, 0])
            vtype = elem.get("visual_type", "unknown")
            text = elem.get("ocr_text") or elem.get("text", "")
            conf = elem.get("confidence", 0)

            # Calculate relative position
            x1, y1, x2, y2 = bounds
            cx = (x1 + x2) / 2 / img_w
            cy = (y1 + y2) / 2 / img_h
            w = (x2 - x1) / img_w
            h = (y2 - y1) / img_h

            # Position description
            pos_x = "left" if cx < 0.33 else ("right" if cx > 0.66 else "center")
            pos_y = "top" if cy < 0.33 else ("bottom" if cy > 0.66 else "middle")
            size = "small" if w * h < 0.01 else ("large" if w * h > 0.1 else "medium")

            line = f"{elem_id}: {vtype}"
            if text:
                line += f' "{text}"'
            line += f" [{pos_x}-{pos_y}, {size}]"

            # Add parent info if available
            parent = elem.get("parent_id")
            if parent:
                line += f" (in {parent})"

            lines.append(line)

        return "\n".join(lines)

    def _repair_truncated_json(self, json_str: str) -> str:
        """Attempt to repair truncated JSON array."""
        json_str = json_str.strip()

        # Must start with [
        if not json_str.startswith('['):
            return json_str

        # If already valid, return as-is
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            pass

        # Try to find the last complete object
        # Look for }, and truncate after it, then close the array
        last_complete = json_str.rfind('},')
        if last_complete > 0:
            repaired = json_str[:last_complete + 1] + ']'
            try:
                json.loads(repaired)
                print(f"Repaired truncated JSON (removed incomplete tail)")
                return repaired
            except json.JSONDecodeError:
                pass

        # Try finding last } and close array
        last_brace = json_str.rfind('}')
        if last_brace > 0:
            repaired = json_str[:last_brace + 1] + ']'
            try:
                json.loads(repaired)
                print(f"Repaired truncated JSON (closed array after last object)")
                return repaired
            except json.JSONDecodeError:
                pass

        return json_str

    def _parse_response(self, response: str) -> List[TreeEdit]:
        """Parse LLM response into TreeEdit operations."""
        edits = []

        # Clean up response - remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        # Try to repair truncated JSON
        response = self._repair_truncated_json(response)

        # Try to parse directly first
        operations = None
        try:
            operations = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON array with regex
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                try:
                    operations = json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Try to repair the extracted portion
                    extracted = json_match.group()
                    repaired = self._repair_truncated_json(extracted)
                    try:
                        operations = json.loads(repaired)
                    except json.JSONDecodeError as e:
                        print(f"Warning: Failed to parse extracted JSON: {e}")

        if operations is None:
            print("Warning: No valid JSON array found in LLM response")
            return edits

        if not isinstance(operations, list):
            print("Warning: LLM response is not a JSON array")
            return edits

        # Convert to TreeEdit objects
        for op in operations:
            if not isinstance(op, dict):
                continue

            op_type = op.get("op", "").lower()

            if op_type == "merge":
                ids = op.get("ids", [])
                if len(ids) >= 2:
                    edits.append(TreeEdit(
                        operation=EditOperation.MERGE_ELEMENTS,
                        target_id=ids[0],
                        params={"merge_ids": ids[1:], "text": op.get("text")}
                    ))

            elif op_type == "split":
                target_id = op.get("id")
                if target_id:
                    edits.append(TreeEdit(
                        operation=EditOperation.SPLIT_ELEMENT,
                        target_id=target_id,
                        params={
                            "into": op.get("into", []),
                            "type": op.get("type", "button")
                        }
                    ))

            elif op_type == "retype":
                target_id = op.get("id")
                new_type = op.get("type")
                if target_id and new_type:
                    edits.append(TreeEdit(
                        operation=EditOperation.SET_TYPE,
                        target_id=target_id,
                        params={"type": new_type}
                    ))

            elif op_type == "delete":
                target_id = op.get("id")
                if target_id:
                    edits.append(TreeEdit(
                        operation=EditOperation.DELETE_ELEMENT,
                        target_id=target_id,
                        params={}
                    ))

            elif op_type == "role":
                target_id = op.get("id")
                role = op.get("role")
                if target_id and role:
                    edits.append(TreeEdit(
                        operation=EditOperation.SET_ROLE,
                        target_id=target_id,
                        params={"role": role}
                    ))

        return edits

    def _apply_edits(
        self,
        elements: List[Dict],
        edits: List[TreeEdit]
    ) -> List[Dict]:
        """Apply tree edits to elements."""
        # Create a copy to avoid modifying original
        result = [dict(e) for e in elements]
        elements_by_id = {e["id"]: e for e in result}
        deleted_ids = set()

        for edit in edits:
            target = elements_by_id.get(edit.target_id)

            if edit.operation == EditOperation.SET_TYPE:
                if target:
                    target["visual_type"] = edit.params["type"]

            elif edit.operation == EditOperation.SET_ROLE:
                if target:
                    target["role"] = edit.params["role"]

            elif edit.operation == EditOperation.DELETE_ELEMENT:
                deleted_ids.add(edit.target_id)

            elif edit.operation == EditOperation.MERGE_ELEMENTS:
                if target:
                    merge_ids = edit.params.get("merge_ids", [])
                    new_text = edit.params.get("text")

                    # Merge bounds from all elements
                    all_bounds = [target["bounds"]]
                    for mid in merge_ids:
                        if mid in elements_by_id:
                            all_bounds.append(elements_by_id[mid]["bounds"])
                            deleted_ids.add(mid)

                    # Update target with merged bounds
                    target["bounds"] = [
                        min(b[0] for b in all_bounds),
                        min(b[1] for b in all_bounds),
                        max(b[2] for b in all_bounds),
                        max(b[3] for b in all_bounds),
                    ]

                    if new_text:
                        target["ocr_text"] = new_text

            elif edit.operation == EditOperation.SPLIT_ELEMENT:
                # For split, we just add metadata - actual splitting needs CV info
                if target:
                    target["_split_into"] = edit.params.get("into", [])
                    target["_split_type"] = edit.params.get("type", "button")

        # Remove deleted elements
        result = [e for e in result if e["id"] not in deleted_ids]

        return result


def refine_hierarchy(
    elements: List[Dict],
    model: str = "ollama",
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to refine hierarchy.

    Args:
        elements: List of detected elements
        model: Model to use (ollama, openai, qwen2.5-3b, etc.)
        **kwargs: Additional arguments for LLMHierarchyRefiner

    Returns:
        Refinement result with edits and refined elements
    """
    refiner = LLMHierarchyRefiner(model_name=model, **kwargs)
    return refiner.refine(elements)
