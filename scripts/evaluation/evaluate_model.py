"""
Evaluate finetuned model on UI hierarchy refinement task.

Metrics:
- Edit accuracy: % of edits correctly predicted
- Tree similarity: Structural similarity between predicted and target trees
- JSON validity: % of outputs that are valid JSON
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.model_registry import get_model_config


@dataclass
class EvalResult:
    """Evaluation result for a single example."""
    example_id: str
    json_valid: bool
    edit_precision: float
    edit_recall: float
    edit_f1: float
    predicted_edits: List[Dict]
    target_edits: List[Dict]


def load_model(model_path: str, base_model: str):
    """Load finetuned model."""
    config = get_model_config(base_model)

    tokenizer = AutoTokenizer.from_pretrained(model_path)

    # Load base model
    base = AutoModelForCausalLM.from_pretrained(
        config.hf_model_id,
        torch_dtype=torch.float16,
        device_map="auto"
    )

    # Load LoRA weights
    model = PeftModel.from_pretrained(base, model_path)
    model.eval()

    return model, tokenizer


def generate_edits(
    model,
    tokenizer,
    elements: str,
    tree_draft: Dict,
    max_new_tokens: int = 512
) -> Tuple[List[Dict], bool]:
    """Generate tree edits from model."""

    system_prompt = """You are a UI hierarchy analyzer. Given detected UI elements and a draft tree structure, suggest edits to improve the hierarchy.

RULES:
1. NEVER generate or modify coordinates/bounds
2. Only output these operations as JSON array:
   - {"op": "set_parent", "element": "E1", "parent": "C1"}
   - {"op": "create_container", "id": "C1", "type": "LinearLayout", "children": ["E1", "E2"]}
   - {"op": "set_role", "element": "E1", "role": "Button"}
   - {"op": "set_flags", "element": "E1", "clickable": true}"""

    user_prompt = f"""ELEMENTS:
{elements}

DRAFT TREE:
{json.dumps(tree_draft)}

Generate tree edits as JSON array:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
    else:
        prompt = f"{system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    # Parse JSON from response
    try:
        # Try to extract JSON array from response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            edits = json.loads(response[start:end])
            return edits, True
        else:
            return [], False
    except json.JSONDecodeError:
        return [], False


def compute_edit_metrics(predicted: List[Dict], target: List[Dict]) -> Tuple[float, float, float]:
    """Compute precision, recall, F1 for edit prediction."""
    if not target:
        return (1.0, 1.0, 1.0) if not predicted else (0.0, 1.0, 0.0)

    if not predicted:
        return (1.0, 0.0, 0.0)

    # Convert to comparable format
    def edit_key(edit):
        return (edit.get("op"), edit.get("element", edit.get("id")))

    predicted_set = set(edit_key(e) for e in predicted)
    target_set = set(edit_key(e) for e in target)

    if not predicted_set:
        return (1.0, 0.0, 0.0)

    true_positives = len(predicted_set & target_set)

    precision = true_positives / len(predicted_set)
    recall = true_positives / len(target_set)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return precision, recall, f1


def evaluate(model, tokenizer, test_data_path: str) -> List[EvalResult]:
    """Evaluate model on test data."""
    results = []

    with open(test_data_path) as f:
        for i, line in enumerate(f):
            example = json.loads(line)

            predicted_edits, json_valid = generate_edits(
                model, tokenizer,
                example["elements"],
                example["tree_draft"]
            )

            precision, recall, f1 = compute_edit_metrics(
                predicted_edits,
                example["edits"]
            )

            results.append(EvalResult(
                example_id=f"example_{i}",
                json_valid=json_valid,
                edit_precision=precision,
                edit_recall=recall,
                edit_f1=f1,
                predicted_edits=predicted_edits,
                target_edits=example["edits"]
            ))

    return results


def print_summary(results: List[EvalResult]):
    """Print evaluation summary."""
    n = len(results)

    json_valid_rate = sum(r.json_valid for r in results) / n
    avg_precision = sum(r.edit_precision for r in results) / n
    avg_recall = sum(r.edit_recall for r in results) / n
    avg_f1 = sum(r.edit_f1 for r in results) / n

    print("\n" + "=" * 50)
    print("EVALUATION RESULTS")
    print("=" * 50)
    print(f"Examples evaluated: {n}")
    print(f"JSON validity rate: {json_valid_rate:.1%}")
    print(f"Edit Precision:     {avg_precision:.3f}")
    print(f"Edit Recall:        {avg_recall:.3f}")
    print(f"Edit F1:            {avg_f1:.3f}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Evaluate finetuned model")
    parser.add_argument("--model", type=str, required=True, help="Path to finetuned model")
    parser.add_argument("--base", type=str, default="qwen2.5-3b", help="Base model key")
    parser.add_argument("--test_data", type=str, default="data/processed/test/test_data.jsonl")
    parser.add_argument("--output", type=str, default="evaluation_results.json")
    args = parser.parse_args()

    print(f"Loading model from {args.model}")
    model, tokenizer = load_model(args.model, args.base)

    print(f"Evaluating on {args.test_data}")
    results = evaluate(model, tokenizer, args.test_data)

    print_summary(results)

    # Save detailed results
    with open(args.output, "w") as f:
        json.dump([vars(r) for r in results], f, indent=2)
    print(f"\nDetailed results saved to {args.output}")


if __name__ == "__main__":
    main()
