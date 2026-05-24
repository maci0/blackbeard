"""Generate LiteLLM config.yaml from LLMConnection resources."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml

from blackbeard.litellm.helpers import apply_model_params, apply_vertex_params, build_model_string

if TYPE_CHECKING:
    from blackbeard.models import Resource

logger = logging.getLogger(__name__)

_yaml_dumper: Any = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


def generate_litellm_config(llm_connections: list[Resource]) -> str:
    """Generate a LiteLLM config.yaml from LLMConnection resources.

    Returns the YAML string.
    """
    model_list = []
    skipped = 0

    for conn in llm_connections:
        spec = conn.spec
        provider = spec.get("provider", "")
        model = spec.get("model", "")
        params = spec.get("parameters", {})
        vertex = spec.get("vertex", {})

        if not model:
            logger.warning(
                "LLMConnection '%s' has no model specified, skipping",
                conn.name,
                extra={
                    "event": "litellm_config_skip_no_model",
                    "connection_name": conn.name,
                },
            )
            skipped += 1
            continue

        litellm_model = build_model_string(provider, model)

        litellm_params: dict[str, Any] = {"model": litellm_model}

        if provider == "vertex_ai":
            apply_vertex_params(litellm_params, vertex)

        api_key_env = spec.get("api_key_env")
        if api_key_env:
            # LiteLLM syntax: "os.environ/VAR" resolves the env var at proxy runtime
            litellm_params["api_key"] = f"os.environ/{api_key_env}"

        base_url = spec.get("base_url")
        if base_url:
            litellm_params["api_base"] = base_url

        apply_model_params(litellm_params, params)

        model_entry = {
            "model_name": conn.name,
            "litellm_params": litellm_params,
        }
        model_list.append(model_entry)

    config = {
        "model_list": model_list,
        "litellm_settings": {
            "drop_params": True,  # silently drop unsupported params instead of erroring
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

    logger.info(
        "LiteLLM config generated: models=%d skipped=%d",
        len(model_list),
        skipped,
        extra={
            "event": "litellm_config_generated",
            "model_count": len(model_list),
            "skipped_count": skipped,
            "model_names": [m["model_name"] for m in model_list],
        },
    )
    return yaml.dump(config, Dumper=_yaml_dumper, default_flow_style=False, sort_keys=False)
