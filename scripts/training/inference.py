"""
Inference script for running the finetuned model.

Usage:
    python scripts/training/inference.py --model models/finetuned/qwen2.5-3b-lora --elements elements.json
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.model_registry import get_model_config, MODEL_REGISTRY


class HierarchyRefiner:
    """Wrapper for hierarchy refinement inference."""

    def __init__(self, model_path: str, base_model: str = "qwen2.5-3b"):
        self.model_path = model_path
        self.base_model = base_model
        self._model = None
        self._tokenizer = None

    def load(self):
        """Load model and tokenizer."""
        if self._model is not None:
            return

        config = get_model_config(self.base_model)

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)

        # Check if this is a LoRA model or full model
        adapter_config = Path(self.model_path) / "adapter_config.json"

        if adapter_config.exists():
            # Load as LoRA
            base = AutoModelForCausalLM.from_pretrained(
                config.hf_model_id,
                torch_dtype=torch.float16,
                device_map="auto"
            )
            self._model = PeftModel.from_pretrained(base, self.model_path)
        else:
            # Load as full model
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                device_map="auto"
            )

        self._model.eval()
        print(f"Model loaded from {self.model_path}")

    def refine(
        self,
        elements: List[Dict],
        tree_draft: Dict,
        max_new_tokens: int = 512
    ) -> List[Dict]:
        """
        Generate hierarchy refinement edits.

        Args:
            elements: Detected UI elements
            tree_draft: Draft tree from coarse builder
            max_new_tokens: Max tokens to generate

        Returns:
            List of tree edit operations
        """
        self.load()

        # Format elements for prompt
        elements_text = self._format_elements(elements)

        system_prompt = """You are a UI hierarchy analyzer. Given detected UI elements and a draft tree structure, suggest edits to improve the hierarchy.

RULES:
1. NEVER generate or modify coordinates/bounds
2. Only output these operations as JSON array:
   - {"op": "set_parent", "element": "E1", "parent": "C1"}
   - {"op": "create_container", "id": "C1", "type": "LinearLayout", "children": ["E1", "E2"]}
   - {"op": "set_role", "element": "E1", "role": "Button"}
   - {"op": "set_flags", "element": "E1", "clickable": true}"""

        user_prompt = f"""ELEMENTS:
{elements_text}

DRAFT TREE:
{json.dumps(tree_draft, indent=2)}

Generate tree edits as JSON array:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        if hasattr(self._tokenizer, "apply_chat_template"):
            prompt = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            prompt = f"{system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"

        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.1,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id
            )

        response = self._tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )

        # Parse JSON
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        return []

    def _format_elements(self, elements: List[Dict]) -> str:
        """Format elements for prompt without coordinates."""
        lines = []
        sorted_elems = sorted(elements, key=lambda e: (e["bounds"][1], e["bounds"][0]))

        for elem in sorted_elems:
            elem_id = elem["id"]
            vtype = elem.get("visual_type", "unknown")
            text = elem.get("ocr_text", "")

            if text:
                lines.append(f"{elem_id}: {vtype} '{text}'")
            else:
                lines.append(f"{elem_id}: {vtype}")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run hierarchy refinement")
    parser.add_argument("--model", type=str, required=True, help="Path to model")
    parser.add_argument("--base", type=str, default="qwen2.5-3b", help="Base model")
    parser.add_argument("--elements", type=str, required=True, help="Elements JSON file")
    parser.add_argument("--draft", type=str, help="Draft tree JSON file")
    parser.add_argument("--output", type=str, help="Output file for edits")
    args = parser.parse_args()

    # Load elements
    with open(args.elements) as f:
        elements = json.load(f)

    # Load or create draft
    if args.draft:
        with open(args.draft) as f:
            tree_draft = json.load(f)
    else:
        # Simple flat draft
        tree_draft = {
            "id": "root",
            "role": "FrameLayout",
            "children": [{"id": e["id"], "role": "Unknown"} for e in elements]
        }

    # Run inference
    refiner = HierarchyRefiner(args.model, args.base)
    edits = refiner.refine(elements, tree_draft)

    print("\nGenerated edits:")
    print(json.dumps(edits, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(edits, f, indent=2)
        print(f"\nEdits saved to {args.output}")


if __name__ == "__main__":
    main()
