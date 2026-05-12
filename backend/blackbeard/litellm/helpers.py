"""Shared helpers for LiteLLM integration."""


def build_model_string(provider: str, model: str) -> str:
    """Build the LiteLLM model identifier string from provider and model name."""
    if provider == "vertex_ai":
        return f"vertex_ai/{model}"
    elif provider == "openai":
        return model
    else:
        return f"{provider}/{model}" if provider else model
