"""The provider table (SPEC 3.7): the one place that knows which adapters exist.

To add a provider, write one file in this folder with a class that has a
`complete` method (see interface.py), then add one entry here. Nothing else
in the harness changes.
"""
import importlib.util
import os
import shutil

from .scripted import ScriptedModel

NO_PROVIDER = ("No model provider is available. Install Claude Code and sign in, or set "
               "ANTHROPIC_API_KEY and install the anthropic package, or set "
               "HARNESS_MODEL_PROVIDER to the provider you want.")

MISSING_PACKAGE = ("The '{provider}' provider needs the '{package}' package. "
                   "Install it with: uv sync --extra {extra}  "
                   "(or choose another provider with HARNESS_MODEL_PROVIDER).")


def _package_installed(name):
    try:
        return importlib.util.find_spec(name) is not None
    except ValueError:                  # already imported, so it is there
        return True


def resolve_provider(name):
    """Turn a provider name into a concrete one: `auto` picks, any other name is returned as is."""
    if name != "auto":
        return name
    if os.environ.get("ANTHROPIC_API_KEY") and _package_installed("anthropic"):
        return "anthropic"
    if shutil.which("claude"):
        return "claude_code"
    raise RuntimeError(NO_PROVIDER)


def _scripted(config):
    if config.script_path is None:
        return ScriptedModel([{"text": "ok"}])
    return ScriptedModel.from_file(config.script_path)


def _auto(config):
    return PROVIDERS[resolve_provider("auto")](config)


def _anthropic(config):
    try:
        from .anthropic_provider import AnthropicModel      # imported only when asked for
        return AnthropicModel(config.model_name)
    except ImportError:
        raise RuntimeError(MISSING_PACKAGE.format(
            provider="anthropic", package="anthropic", extra="claude")) from None


def _claude_code(config):
    from .claude_code_provider import ClaudeCodeModel
    return ClaudeCodeModel(config.model_name)


# name -> function that takes the Config and returns a Model
PROVIDERS = {
    "auto": _auto,
    "scripted": _scripted,
    "anthropic": _anthropic,
    "claude_code": _claude_code,
}
