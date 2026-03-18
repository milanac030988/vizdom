"""
Model registry for supported Small Language Models.

Recommended models for UI hierarchy refinement task:
1. Qwen2.5-3B-Instruct - Best for structured JSON output
2. Phi-3.5-mini-instruct - Good reasoning, efficient
3. Gemma-2-2B-it - Easy to finetune, good baseline
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ModelConfig:
    """Configuration for a supported model."""
    name: str
    hf_model_id: str
    model_type: str  # "causal" or "seq2seq"
    context_length: int
    recommended_max_new_tokens: int
    quantization_supported: bool
    memory_gb: float  # Approximate GPU memory needed (fp16)
    notes: str


# Recommended models for UI hierarchy refinement
MODEL_REGISTRY: Dict[str, ModelConfig] = {
    # === TOP RECOMMENDATIONS ===

    "qwen2.5-3b": ModelConfig(
        name="Qwen2.5-3B-Instruct",
        hf_model_id="Qwen/Qwen2.5-3B-Instruct",
        model_type="causal",
        context_length=32768,
        recommended_max_new_tokens=1024,
        quantization_supported=True,
        memory_gb=7.0,
        notes="Best for structured JSON output. Excellent instruction following."
    ),

    "phi-3.5-mini": ModelConfig(
        name="Phi-3.5-mini-instruct",
        hf_model_id="microsoft/Phi-3.5-mini-instruct",
        model_type="causal",
        context_length=128000,
        recommended_max_new_tokens=1024,
        quantization_supported=True,
        memory_gb=8.0,
        notes="Strong reasoning. Long context. Microsoft UI/code background."
    ),

    "gemma-2-2b": ModelConfig(
        name="Gemma-2-2B-it",
        hf_model_id="google/gemma-2-2b-it",
        model_type="causal",
        context_length=8192,
        recommended_max_new_tokens=512,
        quantization_supported=True,
        memory_gb=5.0,
        notes="Smallest recommended. Easy to finetune. Good baseline."
    ),

    # === ALTERNATIVES ===

    "llama-3.2-3b": ModelConfig(
        name="Llama-3.2-3B-Instruct",
        hf_model_id="meta-llama/Llama-3.2-3B-Instruct",
        model_type="causal",
        context_length=128000,
        recommended_max_new_tokens=1024,
        quantization_supported=True,
        memory_gb=7.0,
        notes="Meta's latest. Requires license acceptance on HF."
    ),

    "smollm2-1.7b": ModelConfig(
        name="SmolLM2-1.7B-Instruct",
        hf_model_id="HuggingFaceTB/SmolLM2-1.7B-Instruct",
        model_type="causal",
        context_length=8192,
        recommended_max_new_tokens=512,
        quantization_supported=True,
        memory_gb=4.0,
        notes="Very small. Good for resource-constrained environments."
    ),

    "qwen2.5-1.5b": ModelConfig(
        name="Qwen2.5-1.5B-Instruct",
        hf_model_id="Qwen/Qwen2.5-1.5B-Instruct",
        model_type="causal",
        context_length=32768,
        recommended_max_new_tokens=1024,
        quantization_supported=True,
        memory_gb=3.5,
        notes="Smaller Qwen. Still good at structured output."
    ),
}


def get_model_config(model_key: str) -> ModelConfig:
    """Get model configuration by key."""
    if model_key not in MODEL_REGISTRY:
        available = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(f"Unknown model: {model_key}. Available: {available}")
    return MODEL_REGISTRY[model_key]


def list_models() -> None:
    """Print available models."""
    print("Available models for UI hierarchy refinement:\n")
    for key, config in MODEL_REGISTRY.items():
        print(f"  {key}:")
        print(f"    Model: {config.hf_model_id}")
        print(f"    Memory: ~{config.memory_gb}GB (fp16)")
        print(f"    Context: {config.context_length} tokens")
        print(f"    Notes: {config.notes}")
        print()


if __name__ == "__main__":
    list_models()
