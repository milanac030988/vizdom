"""
LoRA finetuning script for UI hierarchy refinement model.

Usage:
    python scripts/training/finetune_lora.py --model qwen2.5-3b --data data/processed/train

This script finetunes a small LLM to:
- Understand UI element descriptions (without coordinates)
- Generate tree-edit operations for hierarchy refinement
- Output valid JSON structure edits
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Any

import torch
from datasets import Dataset, load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.model_registry import get_model_config, MODEL_REGISTRY


def parse_args():
    parser = argparse.ArgumentParser(description="Finetune SLM for UI hierarchy")
    parser.add_argument(
        "--model",
        type=str,
        default="qwen2.5-3b",
        choices=list(MODEL_REGISTRY.keys()),
        help="Model to finetune"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/processed/train",
        help="Path to training data"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/finetuned",
        help="Output directory for finetuned model"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=4,
        help="Training batch size"
    )
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=2e-4,
        help="Learning rate"
    )
    parser.add_argument(
        "--lora_r",
        type=int,
        default=16,
        help="LoRA rank"
    )
    parser.add_argument(
        "--lora_alpha",
        type=int,
        default=32,
        help="LoRA alpha"
    )
    parser.add_argument(
        "--use_4bit",
        action="store_true",
        help="Use 4-bit quantization (QLoRA)"
    )
    return parser.parse_args()


def load_training_data(data_path: str) -> Dataset:
    """Load and format training data."""
    data_path = Path(data_path)

    # Load from JSONL files
    examples = []
    for jsonl_file in data_path.glob("*.jsonl"):
        with open(jsonl_file, "r") as f:
            for line in f:
                examples.append(json.loads(line))

    if not examples:
        raise ValueError(f"No training data found in {data_path}")

    return Dataset.from_list(examples)


def format_prompt(example: Dict[str, Any]) -> str:
    """Format a training example into prompt format."""
    system_prompt = """You are a UI hierarchy analyzer. Given detected UI elements and a draft tree structure, suggest edits to improve the hierarchy.

RULES:
1. NEVER generate or modify coordinates/bounds - these come from CV only
2. Only output these operations as JSON:
   - {"op": "set_parent", "element": "E1", "parent": "C1"}
   - {"op": "create_container", "id": "C1", "type": "LinearLayout", "children": ["E1", "E2"]}
   - {"op": "set_role", "element": "E1", "role": "Button"}
   - {"op": "set_flags", "element": "E1", "clickable": true, "editable": false}
"""

    user_prompt = f"""ELEMENTS:
{example['elements']}

DRAFT TREE:
{example['tree_draft']}

Generate tree edits as JSON array:"""

    assistant_response = json.dumps(example['edits'], indent=2)

    return {
        "system": system_prompt,
        "user": user_prompt,
        "assistant": assistant_response
    }


def tokenize_for_training(
    example: Dict[str, Any],
    tokenizer,
    max_length: int = 2048
) -> Dict[str, torch.Tensor]:
    """Tokenize example for causal LM training."""
    formatted = format_prompt(example)

    # Format as chat (model-specific)
    messages = [
        {"role": "system", "content": formatted["system"]},
        {"role": "user", "content": formatted["user"]},
        {"role": "assistant", "content": formatted["assistant"]}
    ]

    # Use chat template if available
    if hasattr(tokenizer, "apply_chat_template"):
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False
        )
    else:
        # Fallback format
        text = f"{formatted['system']}\n\nUser: {formatted['user']}\n\nAssistant: {formatted['assistant']}"

    # Tokenize
    tokenized = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt"
    )

    tokenized["labels"] = tokenized["input_ids"].clone()

    return {k: v.squeeze(0) for k, v in tokenized.items()}


def main():
    args = parse_args()

    # Get model config
    config = get_model_config(args.model)
    print(f"Finetuning {config.name} ({config.hf_model_id})")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(config.hf_model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model with optional quantization
    model_kwargs = {
        "torch_dtype": torch.float16,
        "device_map": "auto",
    }

    if args.use_4bit:
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

    model = AutoModelForCausalLM.from_pretrained(
        config.hf_model_id,
        **model_kwargs
    )

    if args.use_4bit:
        model = prepare_model_for_kbit_training(model)

    # Configure LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load and process data
    print(f"Loading training data from {args.data}")
    dataset = load_training_data(args.data)

    # Tokenize
    tokenized_dataset = dataset.map(
        lambda x: tokenize_for_training(x, tokenizer),
        remove_columns=dataset.column_names
    )

    # Training arguments
    output_dir = Path(args.output) / f"{args.model}-lora"
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.learning_rate,
        fp16=True,
        logging_steps=10,
        save_steps=100,
        save_total_limit=3,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        report_to="none",  # or "wandb" if you want logging
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True),
    )

    # Train
    print("Starting training...")
    trainer.train()

    # Save
    print(f"Saving model to {output_dir}")
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)

    print("Done!")


if __name__ == "__main__":
    main()
