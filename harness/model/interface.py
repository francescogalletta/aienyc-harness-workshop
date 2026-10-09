"""The neutral model interface every provider adapter speaks (SPEC 3.2)."""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict          # JSON Schema for the arguments


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelResponse:
    text: str                           # "" if the model said nothing
    tool_calls: tuple[ToolCall, ...]    # () if it called no tools
    stop_reason: str                    # "end" | "tool_use" | "max_tokens" | "other"
    usage: dict                         # {"input_tokens": int, "output_tokens": int}


class Model(Protocol):
    def complete(self, *, system: str, messages: list[dict],
                 tools: Sequence[ToolSpec] = ()) -> ModelResponse: ...
