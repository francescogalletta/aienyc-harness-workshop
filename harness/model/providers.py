"""The provider table (SPEC 3.7): the one place that knows which adapters exist.

To add a provider, write one file in this folder with a class that has a
`complete` method (see interface.py), then add one entry here. Nothing else
in the harness changes.
"""
from .scripted import ScriptedModel


def _scripted(config):
    if config.script_path is None:
        return ScriptedModel([{"text": "ok"}])
    return ScriptedModel.from_file(config.script_path)


def _anthropic(config):
    from .anthropic_provider import AnthropicModel      # imported only when asked for
    return AnthropicModel(config.model_name)


def _claude_code(config):
    from .claude_code_provider import ClaudeCodeModel
    return ClaudeCodeModel(config.model_name)


# name -> function that takes the Config and returns a Model
PROVIDERS = {
    "scripted": _scripted,
    "anthropic": _anthropic,
    "claude_code": _claude_code,
}
