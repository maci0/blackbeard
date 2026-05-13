"""LiteLLM proxy integration: config generation, key management, helpers."""

from blackbeard.litellm.config_gen import generate_litellm_config
from blackbeard.litellm.helpers import apply_model_params, apply_vertex_params, build_model_string
from blackbeard.litellm.key_manager import shutdown_key_manager

__all__ = [
    "apply_model_params",
    "apply_vertex_params",
    "build_model_string",
    "generate_litellm_config",
    "shutdown_key_manager",
]
