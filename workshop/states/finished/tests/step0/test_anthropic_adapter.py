"""SPEC 3.4: the Claude adapter translates both ways. No network is used:
a fake client stands in for the SDK."""
from types import SimpleNamespace

from harness.model import ToolCall, ToolSpec
from harness.model.anthropic_provider import AnthropicModel


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def api_response(blocks, stop_reason="end_turn", usage=(11, 7)):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]))


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def test_plain_exchange():
    client = FakeClient(api_response([text_block("Hello "), text_block("there")]))
    model = AnthropicModel("some-model", client=client)
    response = model.complete(system="be brief", messages=[{"role": "user", "content": "hi"}])
    assert response.text == "Hello there"
    assert response.tool_calls == ()
    assert response.stop_reason == "end"
    assert response.usage == {"input_tokens": 11, "output_tokens": 7}
    request = client.messages.requests[0]
    assert request["model"] == "some-model"
    assert request["system"] == "be brief"
    assert request["max_tokens"] == 4096
    assert request["messages"] == [{"role": "user", "content": "hi"}]
    assert "tools" not in request


def test_tool_use_response_and_tool_specs():
    client = FakeClient(api_response(
        [text_block("Let me check."), tool_block("toolu_1", "lookup", {"q": "cash flow"})],
        stop_reason="tool_use"))
    model = AnthropicModel("some-model", client=client, max_tokens=500)
    tool = ToolSpec(name="lookup", description="Look something up",
                    input_schema={"type": "object", "properties": {"q": {"type": "string"}}})
    response = model.complete(system="", messages=[{"role": "user", "content": "go"}], tools=[tool])
    assert response.text == "Let me check."
    assert response.tool_calls == (ToolCall(id="toolu_1", name="lookup", arguments={"q": "cash flow"}),)
    assert response.stop_reason == "tool_use"
    request = client.messages.requests[0]
    assert request["max_tokens"] == 500
    assert "system" not in request      # an empty system prompt is left out
    assert request["tools"] == [{"name": "lookup", "description": "Look something up",
                                 "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}}]


def test_history_with_tool_results_is_translated():
    client = FakeClient(api_response([text_block("done")]))
    model = AnthropicModel("some-model", client=client)
    model.complete(system="", messages=[
        {"role": "user", "content": "add these"},
        {"role": "assistant", "content": "On it.", "tool_calls": [
            {"id": "a", "name": "sum", "arguments": {"x": 1}},
            {"id": "b", "name": "sum", "arguments": {"x": 2}}]},
        {"role": "tool", "tool_call_id": "a", "content": "1"},
        {"role": "tool", "tool_call_id": "b", "content": "2"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c", "name": "sum", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c", "content": "3"},
        {"role": "assistant", "content": "The total is 3."},
        {"role": "user", "content": "thanks"},
    ])
    assert client.messages.requests[0]["messages"] == [
        {"role": "user", "content": "add these"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "On it."},
            {"type": "tool_use", "id": "a", "name": "sum", "input": {"x": 1}},
            {"type": "tool_use", "id": "b", "name": "sum", "input": {"x": 2}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": "1"},
            {"type": "tool_result", "tool_use_id": "b", "content": "2"}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "c", "name": "sum", "input": {}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "c", "content": "3"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "The total is 3."}]},
        {"role": "user", "content": "thanks"},
    ]


def test_stop_reasons():
    for api, neutral in [("end_turn", "end"), ("tool_use", "tool_use"), ("max_tokens", "max_tokens"),
                         ("stop_sequence", "other"), ("refusal", "other")]:
        model = AnthropicModel("m", client=FakeClient(api_response([text_block("x")], stop_reason=api)))
        assert model.complete(system="", messages=[]).stop_reason == neutral
