"""A stand-in model that replays prepared responses, for offline runs (SPEC 3.3)."""
import json
from collections.abc import Sequence
from pathlib import Path

from .interface import ModelResponse, ToolCall, ToolSpec


class ScriptExhausted(Exception):
    """The script has no response left to replay."""


class ScriptedModel:
    def __init__(self, script: list[dict]):
        self.script = list(script)
        self.calls: list[dict] = []     # what the harness sent, one entry per call
        self._next_entry = 0
        self._numbered_calls = 0        # tool calls given a call_N id so far

    @classmethod
    def from_file(cls, path) -> "ScriptedModel":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def complete(self, *, system: str, messages: list[dict],
                 tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        # Copies, so a caller that keeps extending its history does not rewrite ours.
        self.calls.append({"system": system, "messages": list(messages), "tools": tuple(tools)})
        if self._next_entry >= len(self.script):
            raise ScriptExhausted(f"the script has no response left (it holds {len(self.script)})")
        entry = self.script[self._next_entry]
        self._next_entry += 1

        tool_calls = tuple(self._tool_call(raw) for raw in entry.get("tool_calls", []))
        return ModelResponse(
            text=entry.get("text", ""),
            tool_calls=tool_calls,
            stop_reason=entry.get("stop_reason") or ("tool_use" if tool_calls else "end"),
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def _tool_call(self, raw: dict) -> ToolCall:
        call_id = raw.get("id")
        if call_id is None:
            self._numbered_calls += 1
            call_id = f"call_{self._numbered_calls}"
        return ToolCall(id=call_id, name=raw["name"], arguments=raw["arguments"])
