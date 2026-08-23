"""LiteLLM proxy integration: helpers, key management, and model sync.

- ``helpers`` — model string / param builders
- ``key_manager`` — per-execution virtual keys with budget caps
- ``model_sync`` — push LLMConnection resources to the live proxy API
"""

from __future__ import annotations

from . import model_sync
from .helpers import apply_model_params, apply_vertex_params, build_model_string
from .key_manager import VirtualKeyError, VirtualKeyManager

__all__ = [
    "VirtualKeyError",
    "VirtualKeyManager",
    "apply_model_params",
    "apply_vertex_params",
    "build_model_string",
    "model_sync",
]
