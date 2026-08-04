"""LiteLLM proxy integration: config generation, helpers, key management, and model sync.

- ``config_gen`` — static proxy YAML generation
- ``helpers`` — model string / param builders shared by config and sync
- ``key_manager`` — per-execution virtual keys with budget caps
- ``model_sync`` — push LLMConnection resources to the live proxy API
"""

from __future__ import annotations

from . import model_sync
from .config_gen import generate_litellm_config
from .helpers import apply_model_params, apply_vertex_params, build_model_string
from .key_manager import VirtualKeyError, VirtualKeyManager

__all__ = [
    "VirtualKeyError",
    "VirtualKeyManager",
    "apply_model_params",
    "apply_vertex_params",
    "build_model_string",
    "generate_litellm_config",
    "model_sync",
]
