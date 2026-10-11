"""SPEC 2.2: the Codex adapter. No Codex is needed to run these: a fake
runner stands in for the command-line tool."""
import json

import pytest

from harness.model import ToolCall, ToolSpec, get_model, resolve_provider
from harness.model import providers
from harness.model.claude_code_provider import PREAMBLE, render_conversation
from harness.model.codex_provider import CodexModel

LOOKUP = ToolSpec(name="lookup", description="Look something up",
                  input_schema={"type": "object", "properties": {"q": {"type": "string"}}})


class FakeRunner:
    """Records what the adapter would run, and answers with canned output."""

    def __init__(self, events=None, returncode=0, stdout=None, stderr=""):
        self.events, self.returncode, self.stdout, self.stderr = events, returncode, stdout, stderr
        self.calls = []

    def __call__(self, argv, stdin_text):
        flags = dict(zip(argv, argv[1:]))
        overrides = [value for flag, value in zip(argv, argv[1:]) if flag == "-c"]
        # The instructions and schema files exist only while the call runs, so read them now.
        instructions = next(value.split("=", 1)[1] for value in overrides
                            if value.startswith("model_instructions_file="))
        with open(json.loads(instructions), encoding="utf-8") as file:
            system = file.read()
        schema = None
        if "--output-schema" in flags:
            with open(flags["--output-schema"], encoding="utf-8") as file:
                schema = json.load(file)
        self.calls.append({"argv": argv, "flags": flags, "overrides": overrides,
                           "stdin": stdin_text, "system": system, "schema": schema})
        stdout = self.stdout if self.stdout is not None else "\n".join(json.dumps(e) for e in self.events)
        return self.returncode, stdout, self.stderr


def run_events(text, usage=None):
    """What `codex exec --json` prints for a run that ends with the reply `text`."""
    return [{"type": "thread.started", "thread_id": "t1"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "thinking"}},
            {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": text}},
            {"type": "turn.completed", "usage": usage or {"input_tokens": 120, "cached_input_tokens": 100,
                                                          "output_tokens": 7, "reasoning_output_tokens": 3}}]


def test_plain_reply():
    runner = FakeRunner(run_events("Hello there"))
    model = CodexModel("some-model", runner=runner)
    response = model.complete(system="Be brief.", messages=[{"role": "user", "content": "hi"}])
    assert response.text == "Hello there"
    assert response.tool_calls == () and response.stop_reason == "end"
    assert response.usage == {"input_tokens": 120, "output_tokens": 7}

    call = runner.calls[0]
    argv = call["argv"]
    assert argv[:2] == ["codex", "exec"] and argv[-1] == "-"      # the prompt comes on standard input
    # A plain model: read-only, no approvals, no shell, no web search, none of
    # the person's own Codex settings, and nothing saved.
    for flag in ("--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"):
        assert flag in argv, flag
    assert call["flags"]["--sandbox"] == "read-only"
    for override in ('approval_policy="never"', 'web_search="disabled"', "features.shell_tool=false",
                     "project_doc_max_bytes=0"):
        assert override in call["overrides"], override
    assert call["flags"]["--model"] == "some-model"
    assert "--output-schema" not in argv
    assert call["system"] == PREAMBLE + "\n\nBe brief."
    assert "<user>\nhi\n</user>" in call["stdin"]


def test_a_claude_model_name_means_the_codex_default():
    # HARNESS_MODEL defaults to a Claude model, which Codex cannot run.
    runner = FakeRunner(run_events("ok"))
    model = CodexModel("claude-sonnet-5-5", runner=runner)
    assert model.model_name is None
    model.complete(system="", messages=[])
    assert "--model" not in runner.calls[0]["argv"]


def test_tool_calls_come_back_through_the_reply_shape():
    reply = {"text": "Let me check.",
             "tool_calls": [{"name": "lookup", "arguments": json.dumps({"q": "cash flow"})},
                            {"name": "lookup", "arguments": '{"q": "budget"}'}]}
    runner = FakeRunner(run_events(json.dumps(reply)))
    model = CodexModel("m", runner=runner)
    response = model.complete(system="", messages=[{"role": "user", "content": "go"}], tools=[LOOKUP])
    assert response.text == "Let me check."
    assert response.stop_reason == "tool_use"
    assert [(c.name, c.arguments) for c in response.tool_calls] == [
        ("lookup", {"q": "cash flow"}), ("lookup", {"q": "budget"})]
    ids = [c.id for c in response.tool_calls]
    assert all(isinstance(c, ToolCall) and c.id.startswith("call_") for c in response.tool_calls)
    assert len(set(ids)) == 2

    call = runner.calls[0]
    schema = call["schema"]
    # Strict structured output: every object lists all its keys as required and allows no others,
    # so the free-form arguments travel as a JSON string.
    item = schema["properties"]["tool_calls"]["items"]
    for shape in (schema, item):
        assert shape["additionalProperties"] is False
        assert shape["required"] == list(shape["properties"])
    assert item["properties"]["name"]["enum"] == ["lookup"]
    assert item["properties"]["arguments"]["type"] == "string"
    listing = json.dumps([{"name": "lookup", "description": "Look something up",
                           "input_schema": LOOKUP.input_schema}], indent=2)
    assert call["system"].startswith(PREAMBLE) and call["system"].endswith(listing)
    assert "tool_calls" in call["system"]


def test_history_is_written_out_for_the_model():
    messages = [
        {"role": "user", "content": "add these"},
        {"role": "assistant", "content": "On it.", "tool_calls": [
            {"id": "call_a", "name": "sum", "arguments": {"x": 1}}]},
        {"role": "tool", "tool_call_id": "call_a", "content": "2"},
    ]
    runner = FakeRunner(run_events("ok"))
    CodexModel("m", runner=runner).complete(system="", messages=messages)
    assert runner.calls[0]["stdin"] == render_conversation(messages)


def test_a_passing_error_event_does_not_fail_a_finished_turn():
    # Codex prints an `error` event while it reconnects; the turn can still finish.
    events = run_events("Hello there")
    events.insert(2, {"type": "error", "message": "Reconnecting... 1/5"})
    response = CodexModel("m", runner=FakeRunner(events)).complete(system="", messages=[])
    assert response.text == "Hello there"


def test_errors_are_raised_with_the_reason_on_one_line():
    failed = FakeRunner([{"type": "turn.started"},
                         {"type": "turn.failed", "error": {"message": "The model 'x' does not\nexist."}}],
                        returncode=1)
    with pytest.raises(RuntimeError, match="model 'x' does not exist"):
        CodexModel("m", runner=failed).complete(system="", messages=[])

    garbage = FakeRunner(stdout="", returncode=2, stderr="error: unexpected argument\n'--ignore-rules'")
    with pytest.raises(RuntimeError, match="unexpected argument '--ignore-rules'"):
        CodexModel("m", runner=garbage).complete(system="", messages=[])

    no_structure = FakeRunner(run_events("plain text only"))
    with pytest.raises(RuntimeError, match="structured"):
        CodexModel("m", runner=no_structure).complete(system="", messages=[], tools=[LOOKUP])

    bad_arguments = FakeRunner(run_events(json.dumps(
        {"text": "", "tool_calls": [{"name": "lookup", "arguments": "not json"}]})))
    with pytest.raises(RuntimeError, match="arguments"):
        CodexModel("m", runner=bad_arguments).complete(system="", messages=[], tools=[LOOKUP])


def test_a_missing_command_is_explained():
    model = CodexModel("m", command="no-such-command-anywhere-on-this-machine")
    with pytest.raises(RuntimeError, match="not found"):
        model.complete(system="", messages=[])


def on_path(monkeypatch, *commands):
    monkeypatch.setattr(providers.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in commands else None)


def test_auto_picks_codex_only_when_nothing_else_is_there(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    on_path(monkeypatch, "codex")
    assert resolve_provider("auto") == "codex"
    on_path(monkeypatch, "claude", "codex")
    assert resolve_provider("auto") == "claude_code"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    monkeypatch.setattr(providers, "_package_installed", lambda name: True)
    assert resolve_provider("auto") == "anthropic"
    on_path(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RuntimeError, match="Codex"):
        resolve_provider("auto")


def test_the_codex_provider_is_one_entry_in_the_table(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "codex")
    monkeypatch.setenv("HARNESS_MODEL", "gpt-something")
    model = get_model()
    assert isinstance(model, CodexModel) and model.model_name == "gpt-something"


def test_check_shows_the_provider_default_model(monkeypatch, capsys):
    from harness import __main__ as cli
    runner = FakeRunner(run_events("pong"))
    monkeypatch.setitem(providers.PROVIDERS, "codex", lambda config: CodexModel(config.model_name, runner=runner))
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "codex")
    assert cli.check(None) == 0
    out = capsys.readouterr().out
    assert "provider: codex" in out and "(the provider's default)" in out and "pong" in out
