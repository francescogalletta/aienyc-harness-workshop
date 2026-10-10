"""The Claude adapter (SPEC 3.4). The only file that may import the provider SDK."""
from collections.abc import Sequence

from .interface import ModelResponse, ToolCall, ToolSpec

STOP_REASONS = {"end_turn": "end", "tool_use": "tool_use", "max_tokens": "max_tokens"}


class AnthropicModel:
    def __init__(self, model_name: str, client=None, max_tokens: int = 4096):
        if client is None:
            import anthropic    # only here, and only when no client is handed in
            client = anthropic.Anthropic()
        self.model_name = model_name
        self.client = client
        self.max_tokens = max_tokens

    def complete(self, *, system: str, messages: list[dict],
                 tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        request = {"model": self.model_name, "max_tokens": self.max_tokens,
                   "messages": _to_api_messages(messages)}
        if system:
            request["system"] = system
        if tools:
            request["tools"] = [{"name": tool.name, "description": tool.description,
                                 "input_schema": tool.input_schema} for tool in tools]
        response = self.client.messages.create(**request)

        blocks = response.content
        return ModelResponse(
            text="".join(block.text for block in blocks if block.type == "text"),
            tool_calls=tuple(ToolCall(id=block.id, name=block.name, arguments=block.input)
                             for block in blocks if block.type == "tool_use"),
            stop_reason=STOP_REASONS.get(response.stop_reason, "other"),
            usage={"input_tokens": response.usage.input_tokens,
                   "output_tokens": response.usage.output_tokens},
        )


def _to_api_messages(messages: list[dict]) -> list[dict]:
    """Translate neutral messages into the shape the Claude API expects."""
    out = []
    for message in messages:
        role = message["role"]
        if role == "user":
            out.append({"role": "user", "content": message["content"]})
        elif role == "assistant":
            blocks = []
            if message["content"]:
                blocks.append({"type": "text", "text": message["content"]})
            for call in message.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": call["id"], "name": call["name"],
                               "input": call["arguments"]})
            if blocks:      # the API rejects an empty message, so leave it out
                out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": message["tool_call_id"],
                     "content": message["content"]}
            if message.get("is_error"):
                block["is_error"] = True
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)    # consecutive results share one user message
            else:
                out.append({"role": "user", "content": [block]})
        else:
            raise ValueError(f"unknown message role: {role!r}")
    return out
