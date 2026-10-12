"""SPEC 2.2: the OpenRouter adapter translates both ways. No network is used:
a fake `post` stands in for the HTTP call."""
import json

import pytest

from harness.model import ToolCall, ToolSpec, get_model, resolve_provider
from harness.model.openrouter_provider import OpenRouterModel, openrouter_model_id


class FakePost:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, url, body, headers, timeout):
        self.requests.append({"url": url, "body": body, "headers": headers})
        return self.response


def api_response(content=None, tool_calls=None, finish_reason="stop", usage=(11, 7)):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}


def model_with(response, **options):
    post = FakePost(response)
    return OpenRouterModel("some/model", api_key="key", post=post, **options), post


def test_plain_exchange():
    model, post = model_with(api_response("Hello there"))
    response = model.complete(system="be brief", messages=[{"role": "user", "content": "hi"}])
    assert response.text == "Hello there"
    assert response.tool_calls == ()
    assert response.stop_reason == "end"
    assert response.usage == {"input_tokens": 11, "output_tokens": 7}
    request = post.requests[0]
    assert request["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer key"
    assert request["body"]["model"] == "some/model"
    assert request["body"]["max_tokens"] == 4096
    assert request["body"]["messages"] == [{"role": "system", "content": "be brief"},
                                           {"role": "user", "content": "hi"}]
    assert "tools" not in request["body"]


def test_tool_use_response_and_tool_specs():
    model, post = model_with(api_response("Let me check.", finish_reason="tool_calls", tool_calls=[
        {"id": "call_1", "type": "function",
         "function": {"name": "lookup", "arguments": json.dumps({"q": "cash flow"})}}]))
    tool = ToolSpec(name="lookup", description="Look something up",
                    input_schema={"type": "object", "properties": {"q": {"type": "string"}}})
    response = model.complete(system="", messages=[{"role": "user", "content": "go"}], tools=[tool])
    assert response.text == "Let me check."
    assert response.tool_calls == (ToolCall(id="call_1", name="lookup", arguments={"q": "cash flow"}),)
    assert response.stop_reason == "tool_use"
    body = post.requests[0]["body"]
    assert body["messages"] == [{"role": "user", "content": "go"}]     # no empty system message
    assert body["tools"] == [{"type": "function", "function": {
        "name": "lookup", "description": "Look something up",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}}]


def test_history_with_tool_results_is_translated():
    model, post = model_with(api_response("done"))
    model.complete(system="", messages=[
        {"role": "user", "content": "add these"},
        {"role": "assistant", "content": "On it.", "tool_calls": [
            {"id": "a", "name": "sum", "arguments": {"x": 1}}]},
        {"role": "tool", "tool_call_id": "a", "content": "1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c", "name": "sum", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c", "content": "no such step", "is_error": True},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "thanks"},
    ])
    assert post.requests[0]["body"]["messages"] == [
        {"role": "user", "content": "add these"},
        {"role": "assistant", "content": "On it.", "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "sum", "arguments": '{"x": 1}'}}]},
        {"role": "tool", "tool_call_id": "a", "content": "1"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "sum", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c", "content": "Error: no such step"},
        {"role": "user", "content": "thanks"},
    ]


def test_stop_reasons():
    for api, neutral in [("stop", "end"), ("tool_calls", "tool_use"), ("length", "max_tokens"),
                         ("content_filter", "other"), (None, "other")]:
        model, _ = model_with(api_response("x", finish_reason=api))
        assert model.complete(system="", messages=[]).stop_reason == neutral


def test_an_error_in_the_body_is_raised():
    model, _ = model_with({"error": {"message": "no credits"}})
    with pytest.raises(RuntimeError, match="no credits"):
        model.complete(system="", messages=[])


def test_model_names():
    assert openrouter_model_id("claude-sonnet-5-5") == "anthropic/claude-sonnet-5.5"
    assert openrouter_model_id("openai/gpt-5") == "openai/gpt-5"


def test_a_key_is_needed(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterModel("m")


def test_the_provider_is_in_the_table(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "openrouter")
    model = get_model()
    assert isinstance(model, OpenRouterModel)
    assert model.model_name == "anthropic/claude-sonnet-5.5"


def test_auto_picks_openrouter_when_only_its_key_is_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    assert resolve_provider("auto") == "openrouter"
