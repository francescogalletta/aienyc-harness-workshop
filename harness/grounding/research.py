"""Looking up standard definitions (SPEC 4.2).

The interviewer never reads the web itself. It hands a short term to a
researcher, and gets back a definition and its sources. The researcher is
told the term and nothing else about the person.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import load_config

MAX_QUERY_LENGTH = 100


@dataclass(frozen=True)
class Lookup:
    query: str
    found: bool
    name: str = ""
    definition: str = ""
    sources: tuple[dict, ...] = ()      # each {"title": ..., "url": ...}

    def as_dict(self) -> dict:
        return {"query": self.query, "found": self.found, "name": self.name,
                "definition": self.definition, "sources": list(self.sources)}


class Researcher(Protocol):
    def look_up(self, query: str) -> Lookup: ...


class ReferenceResearcher:
    """Answers from a saved file of terms. Works offline, and always the same."""

    def __init__(self, path):
        self.path = Path(path)

    def look_up(self, query: str) -> Lookup:
        wanted = _plain(query)
        for entry in json.loads(self.path.read_text(encoding="utf-8")):
            names = [entry["term"], *entry.get("aliases", [])]
            if wanted in {_plain(name) for name in names}:
                return Lookup(query=query, found=True, name=entry["term"],
                              definition=entry["definition"], sources=tuple(entry["sources"]))
        return Lookup(query=query, found=False)


def _plain(text: str) -> str:
    """Lower case, with any run of spaces, hyphens or underscores as one space."""
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


def _reference(config):
    return ReferenceResearcher(config.reference_path)


def _claude_code(config):
    from .claude_code_research import ClaudeCodeResearcher      # imported only when asked for
    return ClaudeCodeResearcher(config.model_name)


# name -> function that takes the Config and returns a Researcher
RESEARCHERS = {
    "reference": _reference,
    "claude_code": _claude_code,
}


def get_researcher(name: str | None = None) -> Researcher:
    """Return the researcher called `name`, or the configured one."""
    config = load_config()
    name = name or config.researcher
    if name not in RESEARCHERS:
        known = ", ".join(sorted(RESEARCHERS))
        raise ValueError(f"unknown researcher: {name!r} (known: {known})")
    return RESEARCHERS[name](config)
