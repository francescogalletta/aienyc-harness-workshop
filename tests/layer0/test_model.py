"""SPEC 3.2 and 3.3: the model interface and its scripted stand-in."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.model import (ModelResponse, ScriptedModel, ScriptExhausted,
                           ToolCall, get_model)

ROOT = Path(__file__).resolve().parents[2]


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


def test_scripted_model_runs_out():
    model = ScriptedModel([{"text": "only"}])
    model.complete(system="", messages=[])
    with pytest.raises(ScriptExhausted):
        model.complete(system="", messages=[])


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


def test_get_model_unknown_provider():
    with pytest.raises(ValueError, match="carrier-pigeon"):
        get_model("carrier-pigeon")
    with pytest.raises(ValueError, match="claude_code, scripted"):
        get_model("carrier-pigeon")       # the error lists the providers that do exist


def test_a_provider_is_one_entry_in_the_table(monkeypatch):
    """SPEC 3.7: adding or swapping a provider touches only the provider table."""
    from harness.model.providers import PROVIDERS
    assert {"scripted", "anthropic", "claude_code"} <= set(PROVIDERS)

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
