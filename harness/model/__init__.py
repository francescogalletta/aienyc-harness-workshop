"""The harness talks to a model only through this package (SPEC 3.2).

Importing it loads no provider SDK.
"""
from ..config import load_config
from .interface import Model, ModelResponse, ToolCall, ToolSpec
from .providers import PROVIDERS
from .scripted import ScriptedModel, ScriptExhausted

__all__ = ["ToolSpec", "ToolCall", "ModelResponse", "Model", "ScriptedModel",
           "ScriptExhausted", "get_model"]


def get_model(provider: str | None = None) -> Model:
    """Return the model for `provider`, or for the configured provider."""
    config = load_config()
    provider = provider or config.model_provider
    if provider not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown model provider: {provider!r} (known: {known})")
    return PROVIDERS[provider](config)
