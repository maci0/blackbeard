"""Shared helpers for LiteLLM integration."""

from __future__ import annotations

from typing import Any

from blackbeard.config import settings


def build_model_string(provider: str, model: str) -> str:
    """Build the LiteLLM model identifier string from provider and model name.

    Used by config_gen to create proxy config entries (needs provider prefix).
    """
    if provider == "openai" or not provider:
        return model
    return f"{provider}/{model}"


_PASSTHROUGH_PARAMS = (
    "temperature",
    "max_tokens",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "stop",
)


def apply_model_params(target: dict[str, Any], params: dict[str, Any]) -> None:
    """Copy standard LLM parameters into target dict."""
    for key in _PASSTHROUGH_PARAMS:
        if key in params:
            target[key] = params[key]


def apply_vertex_params(target: dict[str, Any], vertex: dict[str, Any]) -> None:
    """Apply Vertex AI project/location to target dict, falling back to global settings."""
    project = vertex.get("project") or settings.google_cloud_project
    location = vertex.get("location") or settings.cloud_ml_region
    if project:
        target["vertex_project"] = project
    if location:
        target["vertex_location"] = location
