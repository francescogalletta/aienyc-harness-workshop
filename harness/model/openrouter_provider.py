"""The OpenRouter adapter: its OpenAI-style chat API over plain HTTP, standard library only."""
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Sequence

from .interface import ModelResponse, ToolCall, ToolSpec

URL = "https://openrouter.ai/api/v1/chat/completions"
NO_KEY = "The 'openrouter' provider needs OPENROUTER_API_KEY to be set."
STOP_REASONS = {"stop": "end", "tool_calls": "tool_use", "length": "max_tokens"}


def openrouter_model_id(name: str) -> str:
    """`claude-sonnet-5-5` becomes `anthropic/claude-sonnet-5.5`; a name with a `/` is kept."""
    if "/" in name:
        return name
    return "anthropic/" + re.sub(r"-(\d+)-(\d+)$", r"-\1.\2", name)


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise RuntimeError(f"OpenRouter returned {error.code}: {detail}") from None


class OpenRouterModel:
    def __init__(self, model_name: str, api_key: str | None = None, post=None,
                 max_tokens: int = 4096, timeout: float = 300):
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(NO_KEY)
        self.model_name = openrouter_model_id(model_name)
        self.api_key = api_key
        self.post = post or _post       # a test hands in a fake, so no network is used
        self.max_tokens = max_tokens
        self.timeout = timeout

    def complete(self, *, system: str, messages: list[dict],
                 tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        body = {"model": self.model_name, "max_tokens": self.max_tokens,
                "messages": _to_api_messages(system, messages)}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": tool.name, "description": tool.description,
                "parameters": tool.input_schema}} for tool in tools]
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        response = self.post(URL, body, headers, self.timeout)
        if "error" in response:
            raise RuntimeError(f"OpenRouter error: {response['error'].get('message', response['error'])}")

        choice = response["choices"][0]
        message = choice["message"]
        usage = response.get("usage") or {}
        return ModelResponse(
            text=message.get("content") or "",
            tool_calls=tuple(ToolCall(id=call["id"], name=call["function"]["name"],
                                      arguments=json.loads(call["function"].get("arguments") or "{}"))
                             for call in message.get("tool_calls") or []),
            stop_reason=STOP_REASONS.get(choice.get("finish_reason"), "other"),
            usage={"input_tokens": usage.get("prompt_tokens", 0),
                   "output_tokens": usage.get("completion_tokens", 0)},
        )


def _to_api_messages(system: str, messages: list[dict]) -> list[dict]:
    """Translate neutral messages into the OpenAI-style shape OpenRouter expects."""
    out = [{"role": "system", "content": system}] if system else []
    for message in messages:
        role = message["role"]
        if role == "user":
            out.append({"role": "user", "content": message["content"]})
        elif role == "assistant":
            calls = [{"id": call["id"], "type": "function",
                      "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}}
                     for call in message.get("tool_calls") or []]
            if not message["content"] and not calls:
                continue        # an empty message is left out, as in the Claude adapter
            entry = {"role": "assistant", "content": message["content"] or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
        elif role == "tool":
            content = message["content"]
            if message.get("is_error"):
                content = f"Error: {content}"     # the API has no error flag on a tool result
            out.append({"role": "tool", "tool_call_id": message["tool_call_id"], "content": content})
        else:
            raise ValueError(f"unknown message role: {role!r}")
    return out
