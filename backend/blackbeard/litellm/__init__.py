"""LiteLLM proxy integration: config generation, helpers, and key management."""

from __future__ import annotations

from blackbeard.litellm.config_gen import generate_litellm_config
from blackbeard.litellm.helpers import apply_model_params, apply_vertex_params, build_model_string
from blackbeard.litellm.key_manager import VirtualKeyError, VirtualKeyManager

__all__ = [
    "VirtualKeyError",
    "VirtualKeyManager",
    "apply_model_params",
    "apply_vertex_params",
    "build_model_string",
    "generate_litellm_config",
]
