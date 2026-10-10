"""SPEC 3.2 and 3.3: the model interface and its scripted stand-in."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import harness.model as model_pkg
from harness.model import (ModelResponse, ScriptedModel, ScriptExhausted,
                           ToolCall, ToolSpec, get_model, resolve_provider)

ROOT = Path(__file__).resolve().parents[2]


def test_public_names():
    for name in ("ToolSpec", "ToolCall", "ModelResponse", "Model", "ScriptedModel",
                 "ScriptExhausted", "get_model", "resolve_provider"):
        assert hasattr(model_pkg, name), name


def test_scripted_model_replays_in_order():
    model = ScriptedModel([{"text": "first"}, {"text": "second"}])
    one = model.complete(system="s", messages=[{"role": "user", "content": "a"}])
    two = model.complete(system="s", messages=[{"role": "user", "content": "b"}])
    assert isinstance(one, ModelResponse)
    assert (one.text, one.tool_calls, one.stop_reason) == ("first", (), "end")
    assert two.text == "second"
    assert one.usage == {"input_tokens": 0, "output_tokens": 0}


def test_scripted_model_tool_calls_and_ids():
    model = ScriptedModel([
        {"tool_calls": [{"name": "lookup", "arguments": {"q": "x"}},
                        {"name": "lookup", "arguments": {"q": "y"}}]},
        {"text": "thinking", "tool_calls": [{"id": "mine", "name": "sum", "arguments": {}}]},
        {"tool_calls": [{"name": "sum", "arguments": {"a": 1}}]},
        {"text": "cut off", "stop_reason": "max_tokens"},
    ])
    first = model.complete(system="", messages=[])
    assert first.text == "" and first.stop_reason == "tool_use"
    assert first.tool_calls == (ToolCall(id="call_1", name="lookup", arguments={"q": "x"}),
                                ToolCall(id="call_2", name="lookup", arguments={"q": "y"}))
    second = model.complete(system="", messages=[])
    assert second.tool_calls == (ToolCall(id="mine", name="sum", arguments={}),)
    assert second.stop_reason == "tool_use" and second.text == "thinking"
    third = model.complete(system="", messages=[])
    assert third.tool_calls[0].id == "call_3"
    assert model.complete(system="", messages=[]).stop_reason == "max_tokens"


def test_scripted_model_records_what_it_was_sent():
    model = ScriptedModel([{"text": "ok"}])
    tool = ToolSpec(name="lookup", description="Look something up",
                    input_schema={"type": "object", "properties": {}})
    messages = [{"role": "user", "content": "hello"}]
    model.complete(system="be brief", messages=messages, tools=[tool])
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["system"] == "be brief"
    assert call["messages"] == messages
    assert list(call["tools"]) == [tool]


def test_scripted_model_runs_out():
    model = ScriptedModel([{"text": "only"}])
    model.complete(system="", messages=[])
    with pytest.raises(ScriptExhausted):
        model.complete(system="", messages=[])


def test_scripted_model_from_file(tmp_path):
    path = tmp_path / "script.json"
    path.write_text(json.dumps([{"text": "from file"}]), encoding="utf-8")
    assert ScriptedModel.from_file(path).complete(system="", messages=[]).text == "from file"


def test_get_model_scripted_default_and_from_file(monkeypatch, tmp_path):
    assert get_model("scripted").complete(system="", messages=[]).text == "ok"
    path = tmp_path / "script.json"
    path.write_text(json.dumps([{"text": "scripted reply"}]), encoding="utf-8")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.setenv("HARNESS_SCRIPT", str(path))
    assert get_model().complete(system="", messages=[]).text == "scripted reply"


def test_get_model_anthropic_is_built_lazily_with_the_configured_name(monkeypatch):
    """A stand-in `anthropic` module proves the SDK is imported only on request."""
    import types
    made = []
    fake_sdk = types.ModuleType("anthropic")
    fake_sdk.Anthropic = lambda *args, **kwargs: made.append("client") or object()
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    monkeypatch.setenv("HARNESS_MODEL", "configured-name")
    model = get_model("anthropic")
    assert made == ["client"]
    assert type(model).__name__ == "AnthropicModel"
    assert model.model_name == "configured-name"


def test_all_lists_exactly_the_public_names():
    assert sorted(model_pkg.__all__) == sorted(
        ["ToolSpec", "ToolCall", "ModelResponse", "Model", "ScriptedModel",
         "ScriptExhausted", "get_model", "resolve_provider"])
    import harness.model.interface as interface
    assert interface.ToolSpec is ToolSpec and interface.ModelResponse is ModelResponse


def test_get_model_unknown_provider():
    with pytest.raises(ValueError, match="carrier-pigeon"):
        get_model("carrier-pigeon")
    with pytest.raises(ValueError, match="anthropic, auto, claude_code, scripted"):
        get_model("carrier-pigeon")       # the error lists the providers that do exist


def test_a_provider_is_one_entry_in_the_table(monkeypatch):
    """SPEC 3.7: adding or swapping a provider touches only the provider table."""
    from harness.model.providers import PROVIDERS
    assert {"auto", "scripted", "anthropic", "claude_code"} <= set(PROVIDERS)

    class Echo:
        def __init__(self, config):
            self.config = config

        def complete(self, *, system, messages, tools=()):
            return ModelResponse(text=f"echo from {self.config.model_name}", tool_calls=(),
                                 stop_reason="end", usage={"input_tokens": 0, "output_tokens": 0})

    monkeypatch.setitem(PROVIDERS, "echo", Echo)
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "echo")
    monkeypatch.setenv("HARNESS_MODEL", "my-model")
    assert get_model().complete(system="", messages=[]).text == "echo from my-model"


def test_importing_the_model_package_loads_no_provider_sdk():
    code = "import sys, harness.model; print('anthropic' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_only_the_model_package_mentions_a_provider_sdk():
    """Ground rule 3: no file outside harness/model/ imports a provider SDK."""
    offenders = []
    for path in (ROOT / "harness").rglob("*.py"):
        if (ROOT / "harness" / "model") in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        if "import anthropic" in text or "from anthropic" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_the_harness_does_not_name_the_example():
    """Ground rule 2: nothing under harness/ knows about the example domain."""
    offenders = []
    for path in (ROOT / "harness").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sql", ".md", ".json"}:
            text = path.read_text(encoding="utf-8").lower()
            if "wedding" in text or "data/example" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


# SPEC 3.7: the `auto` provider and a missing SDK

@pytest.fixture
def machine(monkeypatch):
    """Control what `auto` can see: the key, the anthropic package and the `claude` command."""
    import importlib.util
    import shutil

    def set_up(*, key=False, package=False, claude=False):
        if key:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        else:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        real_find_spec = importlib.util.find_spec
        monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: (
            object() if package else None) if name == "anthropic" else real_find_spec(name, *a))
        monkeypatch.setattr(shutil, "which", lambda name, *a, **k: "/bin/claude" if claude else None)
    return set_up


def test_auto_is_the_default_provider():
    from harness.config import load_config
    assert load_config().model_provider == "auto"


def test_auto_with_a_key_and_the_package_is_anthropic(monkeypatch, machine):
    import types
    machine(key=True, package=True, claude=True)       # even with Claude Code present
    fake_sdk = types.ModuleType("anthropic")
    fake_sdk.Anthropic = lambda *args, **kwargs: object()
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    assert resolve_provider("auto") == "anthropic"
    monkeypatch.setenv("HARNESS_MODEL", "configured-name")
    model = get_model()
    assert type(model).__name__ == "AnthropicModel" and model.model_name == "configured-name"


def test_auto_without_a_key_uses_claude_code(machine):
    machine(key=False, package=True, claude=True)
    assert resolve_provider("auto") == "claude_code"
    model = get_model()
    assert type(model).__name__ == "ClaudeCodeModel" and model.model_name == "claude-sonnet-5-5"


def test_auto_with_a_key_but_no_package_uses_claude_code(machine):
    machine(key=True, package=False, claude=True)
    assert resolve_provider("auto") == "claude_code"


def test_an_empty_key_counts_as_no_key(monkeypatch, machine):
    machine(key=False, package=True, claude=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert resolve_provider("auto") == "claude_code"


def test_auto_with_nothing_available_says_what_to_do(machine):
    from harness.model.providers import NO_PROVIDER
    machine(key=True, package=False, claude=False)
    with pytest.raises(RuntimeError) as error:
        get_model()
    assert str(error.value) == NO_PROVIDER == (
        "No model provider is available. Install Claude Code and sign in, or set "
        "ANTHROPIC_API_KEY and install the anthropic package, or set "
        "HARNESS_MODEL_PROVIDER to the provider you want.")


def test_a_named_provider_is_never_changed_by_resolving():
    for name in ("scripted", "anthropic", "claude_code", "carrier-pigeon"):
        assert resolve_provider(name) == name


def test_an_explicit_provider_ignores_what_auto_would_pick(machine):
    machine(key=False, package=False, claude=False)
    assert get_model("scripted").complete(system="", messages=[]).text == "ok"


def test_explicit_anthropic_without_the_package(monkeypatch):
    from harness.model.providers import MISSING_PACKAGE
    monkeypatch.setitem(sys.modules, "anthropic", None)         # makes `import anthropic` fail
    with pytest.raises(RuntimeError) as error:
        get_model("anthropic")
    assert str(error.value) == MISSING_PACKAGE.format(
        provider="anthropic", package="anthropic", extra="claude")
    assert "uv sync --extra claude" in str(error.value)
