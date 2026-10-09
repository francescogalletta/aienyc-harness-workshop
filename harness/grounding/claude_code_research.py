"""Web lookups through the person's own signed-in Claude Code (SPEC 4.2).

Each lookup runs Claude Code once, with web search as its only tool. It is
sent the term and nothing else, so nothing the person said reaches the web.
"""
import json
import os
import tempfile
from pathlib import Path

from ..model.claude_code_provider import parse_output, run_command
from .research import Lookup

FLAGS = ["-p", "--safe-mode", "--tools", "WebSearch", "--allowedTools", "WebSearch",
         "--disallowedTools", "mcp__*", "--strict-mcp-config", "--no-chrome",
         "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"]

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "name": {"type": "string"},
        "definition": {"type": "string"},
        "sources": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
            "required": ["title", "url"]}},
    },
    "required": ["found", "name", "definition", "sources"],
}

INSTRUCTIONS = Path(__file__).with_name("researcher.md")


class ClaudeCodeResearcher:
    def __init__(self, model_name: str, runner=None, command: str = "claude", timeout: float = 300):
        self.model_name = model_name
        self.command = command
        self.timeout = timeout
        self.runner = runner or (lambda argv, stdin_text: run_command(argv, stdin_text, timeout))

    def look_up(self, query: str) -> Lookup:
        with tempfile.TemporaryDirectory() as folder:
            prompt_file = os.path.join(folder, "system.txt")
            with open(prompt_file, "w", encoding="utf-8") as file:
                file.write(INSTRUCTIONS.read_text(encoding="utf-8"))
            argv = [self.command, *FLAGS, "--model", self.model_name,
                    "--system-prompt-file", prompt_file,
                    "--json-schema", json.dumps(REPLY_SCHEMA)]
            returncode, stdout, stderr = self.runner(argv, query)

        reply = parse_output(returncode, stdout, stderr).get("structured_output")
        if not isinstance(reply, dict):
            raise RuntimeError("Claude Code returned no structured reply")
        sources = tuple({"title": str(source.get("title", "")), "url": str(source["url"])}
                        for source in reply.get("sources") or [] if source.get("url"))
        found = bool(reply.get("found")) and bool(sources)
        return Lookup(query=query, found=found, name=reply.get("name") or "",
                      definition=reply.get("definition") or "", sources=sources if found else ())
