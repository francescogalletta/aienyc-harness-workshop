"""The Codex adapter (SPEC 2.2).

It uses the OpenAI Codex command-line tool, signed in on this machine, as the
model. No API key is involved: each call runs `codex exec` once, with Codex's
shell, web search and the person's own configuration switched off, and reads
back one reply.

As with Claude Code, tool calling is done by agreement: the instructions list
the tools, and the reply must fit a JSON shape that holds text and tool calls.
Codex holds the reply to that shape strictly, which allows no free-form
object, so the arguments of each call come back as a JSON string.
"""
import json
import os
import subprocess
import tempfile
import uuid
from collections.abc import Sequence

from .claude_code_provider import PREAMBLE, render_conversation
from .interface import ModelResponse, ToolCall, ToolSpec

# Print one reply and exit, as a plain model: a read-only sandbox, no approvals,
# no shell, no web search, no AGENTS.md, none of the person's settings, nothing saved.
BASE_FLAGS = ["--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
              "--sandbox", "read-only",
              "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
              "-c", "features.shell_tool=false", "-c", "features.apps=false",
              "-c", "project_doc_max_bytes=0", "-c", 'history.persistence="none"']

TOOL_RULES = (
    "The program can carry out the actions listed below. They are not functions you can call "
    "directly. The only way to use one is to add an entry to `tool_calls` in your reply, with its "
    "name and, in `arguments`, a JSON object that fits its input schema, written as a string "
    '(for example "{\\"q\\": \\"budget\\"}"). The program then carries it out and shows you the '
    "result on the next turn. Never make up a result. Put what you want to say to the person in "
    "`text`; it may be empty when you add an action. When you need no action, leave `tool_calls` empty."
)


class CodexModel:
    def __init__(self, model_name: str | None, runner=None, command: str = "codex", timeout: float = 300):
        # HARNESS_MODEL defaults to a Claude model, which Codex cannot run: use Codex's own default.
        self.model_name = None if not model_name or model_name.startswith("claude") else model_name
        self.command = command
        self.timeout = timeout
        self.runner = runner or (lambda argv, stdin_text: run_command(argv, stdin_text, timeout))

    def complete(self, *, system: str, messages: list[dict],
                 tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        with tempfile.TemporaryDirectory() as folder:
            # The instructions replace Codex's own, and go in a file: they can be too long for a command line.
            instructions = os.path.join(folder, "instructions.txt")
            with open(instructions, "w", encoding="utf-8") as file:
                file.write(system_prompt(system, tools))
            argv = [self.command, "exec", *BASE_FLAGS, "--cd", folder,
                    "-c", f"model_instructions_file={json.dumps(instructions)}"]
            if self.model_name:
                argv += ["--model", self.model_name]
            if tools:
                schema = os.path.join(folder, "schema.json")
                with open(schema, "w", encoding="utf-8") as file:
                    json.dump(reply_schema(tools), file)
                argv += ["--output-schema", schema]
            argv.append("-")                # the conversation comes on standard input
            returncode, stdout, stderr = self.runner(argv, render_conversation(messages))

        text, usage = parse_output(returncode, stdout, stderr)
        tool_calls = ()
        if tools:
            try:
                structured = json.loads(text)
            except ValueError:
                structured = None
            if not isinstance(structured, dict):
                raise RuntimeError("Codex returned no structured reply")
            text = structured.get("text") or ""
            tool_calls = tuple(
                ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=call["name"],
                         arguments=tool_arguments(call.get("arguments")))
                for call in structured.get("tool_calls") or [])
        return ModelResponse(
            text=text, tool_calls=tool_calls,
            stop_reason="tool_use" if tool_calls else "end",
            usage={"input_tokens": usage.get("input_tokens") or 0,
                   "output_tokens": usage.get("output_tokens") or 0})


def run_command(argv: list[str], stdin_text: str, timeout: float) -> tuple[int, str, str]:
    """The default runner: run Codex once and hand back what it printed."""
    try:
        # Run from the system's temporary folder, so the model is told
        # nothing about the folder the harness lives in.
        done = subprocess.run(argv, input=stdin_text, capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout, cwd=tempfile.gettempdir())
    except FileNotFoundError:
        raise RuntimeError(f"Codex was not found (tried to run {argv[0]!r}). "
                           "Install it and sign in with `codex login`, or choose another provider.") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Codex gave no reply within {timeout:g} seconds") from None
    return done.returncode, done.stdout, done.stderr


def system_prompt(system: str, tools: Sequence[ToolSpec]) -> str:
    parts = [PREAMBLE]
    if system:
        parts.append(system)
    if tools:
        listing = [{"name": tool.name, "description": tool.description,
                    "input_schema": tool.input_schema} for tool in tools]
        parts.append(TOOL_RULES + "\n\n" + json.dumps(listing, indent=2))
    return "\n\n".join(parts)


def reply_schema(tools: Sequence[ToolSpec]) -> dict:
    """The shape every reply must fit when tools are on offer."""
    call = {"type": "object",
            "properties": {"name": {"type": "string", "enum": [tool.name for tool in tools]},
                           "arguments": {"type": "string",
                                         "description": "The arguments: a JSON object, written as a string."}},
            "required": ["name", "arguments"], "additionalProperties": False}
    return {"type": "object",
            "properties": {"text": {"type": "string"},
                           "tool_calls": {"type": "array", "items": call}},
            "required": ["text", "tool_calls"], "additionalProperties": False}


def tool_arguments(written) -> dict:
    """The arguments of one tool call, read back from their JSON string."""
    if not written:
        return {}
    try:
        arguments = json.loads(written)
    except (TypeError, ValueError):
        arguments = None
    if not isinstance(arguments, dict):
        detail = " ".join(str(written).split())[:100]
        raise RuntimeError(f"Codex returned tool arguments that are not a JSON object: {detail}")
    return arguments


def parse_output(returncode: int, stdout: str, stderr: str) -> tuple[str, dict]:
    """Read the reply and token usage from Codex's JSON events, or raise with the reason it gave."""
    events = []
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    replies = [event["item"].get("text") or "" for event in events
               if event.get("type") == "item.completed" and isinstance(event.get("item"), dict)
               and event["item"].get("type") == "agent_message"]
    finished = [event for event in events if event.get("type") == "turn.completed"]
    if returncode == 0 and finished and replies:
        usage = finished[-1].get("usage") or {}
        return replies[-1], usage
    # A run that did not finish: the reason is in its error events, else in what it printed.
    reasons = [(event.get("error") or {}).get("message") if event.get("type") == "turn.failed"
               else event.get("message") for event in events if event.get("type") in ("turn.failed", "error")]
    reasons = [str(reason) for reason in reasons if reason]
    if reasons:
        raise RuntimeError(f"Codex reported an error: {' '.join(reasons[-1].split())[:300]}")
    detail = " ".join((stderr or stdout or "no output").split())[:300]
    raise RuntimeError(f"Codex did not return a reply (exit {returncode}): {detail}")
