"""Generate LiteLLM config.yaml from LLMConnection resources."""

from __future__ import annotations

import logging
import yaml

from blackbeard.config import settings
from blackbeard.litellm.helpers import build_model_string
from blackbeard.models.resource import Resource

logger = logging.getLogger(__name__)


def generate_litellm_config(llm_connections: list[Resource]) -> str:
    """Generate a LiteLLM config.yaml from LLMConnection resources.

    Returns the YAML string.
    """
    model_list = []

    for conn in llm_connections:
        spec = conn.spec
        provider = spec.get("provider", "")
        model = spec.get("model", "")
        params = spec.get("parameters", {})
        vertex = spec.get("vertex", {})

        # Build model string
        litellm_model = build_model_string(provider, model)

        litellm_params: dict = {"model": litellm_model}

        # Vertex AI params
        if provider == "vertex_ai":
            project = vertex.get("project") or settings.google_cloud_project
            location = vertex.get("location") or settings.cloud_ml_region
            if project:
                litellm_params["vertex_project"] = project
            if location:
                litellm_params["vertex_location"] = location

        # API key
        api_key_env = spec.get("api_key_env")
        if api_key_env:
            litellm_params["api_key"] = f"os.environ/{api_key_env}"

        # Base URL
        base_url = spec.get("base_url")
        if base_url:
            litellm_params["api_base"] = base_url

        # Model parameters
        if "temperature" in params:
            litellm_params["temperature"] = params["temperature"]
        if "max_tokens" in params:
            litellm_params["max_tokens"] = params["max_tokens"]

        model_entry = {
            "model_name": conn.name,
            "litellm_params": litellm_params,
        }
        model_list.append(model_entry)

    config = {
        "model_list": model_list,
        "litellm_settings": {
            "drop_params": True,
            "set_verbose": False,
            "num_retries": 3,
            "request_timeout": 120,
        },
        "general_settings": {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
        },
        "router_settings": {
            "routing_strategy": "simple-shuffle",
        },
    }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)
