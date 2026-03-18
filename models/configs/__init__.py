"""Model configuration module."""

from .model_registry import MODEL_REGISTRY, get_model_config, list_models, ModelConfig
from .cv_model_registry import (
    CV_MODEL_REGISTRY,
    get_cv_model_config,
    list_cv_models,
    CVModelConfig,
    UI_ELEMENT_CLASSES,
)

__all__ = [
    # LLM models
    "MODEL_REGISTRY",
    "get_model_config",
    "list_models",
    "ModelConfig",
    # CV models
    "CV_MODEL_REGISTRY",
    "get_cv_model_config",
    "list_cv_models",
    "CVModelConfig",
    "UI_ELEMENT_CLASSES",
]
