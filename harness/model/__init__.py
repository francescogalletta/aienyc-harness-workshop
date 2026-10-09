"""The model interface and its providers. Other code imports from here (SPEC 3.2)."""
from ..config import load_config
from .interface import Model, ModelResponse, ToolCall, ToolSpec
from .scripted import ScriptedModel, ScriptExhausted

__all__ = ["ToolSpec", "ToolCall", "ModelResponse", "Model", "ScriptedModel",
           "ScriptExhausted", "get_model"]


def get_model(provider: str | None = None) -> Model:
    """Return the model for `provider`, or for the configured provider when none is given."""
    config = load_config()
    if provider is None:
        provider = config.model_provider
    if provider == "scripted":
        if config.script_path is None:
            return ScriptedModel([{"text": "ok"}])
        return ScriptedModel.from_file(config.script_path)
    if provider == "anthropic":
        from .anthropic_provider import AnthropicModel     # the SDK is loaded only on request
        return AnthropicModel(config.model_name)
    raise ValueError(f"unknown model provider: {provider!r}")
