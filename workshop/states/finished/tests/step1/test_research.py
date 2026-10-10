"""SPEC 4.2 and 4.6: looking up standard definitions, and who looks them up."""
import json

import pytest

from harness.config import load_config
from harness.grounding import (ChainResearcher, Lookup, ReferenceResearcher, WikipediaResearcher,
                               get_researcher)
from harness.grounding.claude_code_research import ClaudeCodeResearcher
from harness.grounding.research import RESEARCHERS

from step1_helpers import SOURCE


def test_reference_researcher_matches_terms_and_aliases(reference_file):
    researcher = ReferenceResearcher(reference_file)
    found = researcher.look_up("Cash-Flow  FORECAST")
    assert isinstance(found, Lookup) and found.found
    assert found.query == "Cash-Flow  FORECAST" and found.name == "cash flow forecast"
    assert found.definition.startswith("A plan of the money")
    assert found.sources == ({"title": "Example: cash flow forecast", "url": SOURCE},)
    assert found.origin == "reference"
    assert researcher.look_up("cash_flow projection").name == "cash flow forecast"
    assert researcher.look_up("balance").name == "account balance"


def test_reference_researcher_says_when_it_does_not_know(reference_file):
    missing = ReferenceResearcher(reference_file).look_up("quantum budgeting")
    assert missing == Lookup(query="quantum budgeting", found=False, origin="reference")
    assert missing.as_dict() == {"query": "quantum budgeting", "found": False, "name": "",
                                 "definition": "", "sources": [], "origin": "reference"}
    assert Lookup("x", False).origin == ""                    # the last field, empty unless set


def test_the_repository_ships_a_usable_reference_file():
    from pathlib import Path
    entries = json.loads((Path(__file__).resolve().parents[2] / "reference" / "terms.json").read_text())
    assert len(entries) >= 10
    for entry in entries:
        assert entry["term"] and entry["definition"] and isinstance(entry["aliases"], list)
        assert entry["sources"] and all(s["url"].startswith("https://") and s["title"] for s in entry["sources"])


def test_the_default_researcher_is_the_file_first_then_wikipedia(monkeypatch, reference_file):
    monkeypatch.delenv("HARNESS_RESEARCHER")                  # the tests' own default is `reference`
    monkeypatch.setenv("HARNESS_REFERENCE", str(reference_file))
    assert load_config().researcher == "auto"
    researcher = get_researcher()
    assert isinstance(researcher, ChainResearcher)
    first, second = researcher.researchers
    assert isinstance(first, ReferenceResearcher) and isinstance(second, WikipediaResearcher)
    assert researcher.look_up("cash forecast").origin == "reference"     # found in the file: no request made


def test_get_researcher_reads_the_configured_name(reference_file, monkeypatch):
    monkeypatch.setenv("HARNESS_REFERENCE", str(reference_file))
    researcher = get_researcher()
    assert isinstance(researcher, ReferenceResearcher)
    assert researcher.look_up("cash forecast").found
    assert isinstance(get_researcher("wikipedia"), WikipediaResearcher)


def test_get_researcher_by_name_and_unknown(monkeypatch):
    monkeypatch.setenv("HARNESS_RESEARCHER", "claude_code")
    monkeypatch.setenv("HARNESS_MODEL", "configured-name")
    researcher = get_researcher()
    assert isinstance(researcher, ClaudeCodeResearcher) and researcher.model_name == "configured-name"
    assert set(RESEARCHERS) == {"auto", "claude_code", "reference", "wikipedia"}
    with pytest.raises(ValueError, match="auto, claude_code, reference, wikipedia"):
        get_researcher("town-crier")


class FakeRunner:
    def __init__(self, structured=None, **fields):
        self.reply = {"type": "result", "is_error": False, "result": "", "structured_output": structured,
                      **fields}
        self.returncode = 1 if fields.get("is_error") else 0
        self.calls = []

    def __call__(self, argv, stdin_text):
        flags = dict(zip(argv, argv[1:]))
        with open(flags["--system-prompt-file"], encoding="utf-8") as file:
            system = file.read()
        self.calls.append({"argv": argv, "flags": flags, "stdin": stdin_text, "system": system})
        return self.returncode, json.dumps(self.reply), ""


def test_claude_code_researcher_sends_only_the_term_to_the_web():
    """Ground rule 6: the model that reads web pages is told the term and nothing else."""
    from pathlib import Path
    import harness.grounding.research as research_module
    runner = FakeRunner({"found": True, "name": "Budget variance",
                         "definition": "The difference between budget and actual.",
                         "sources": [{"title": "A page", "url": "https://example.org/variance"},
                                     {"title": "No address"}]})
    lookup = ClaudeCodeResearcher("some-model", runner=runner).look_up("budget variance")
    assert lookup == Lookup(query="budget variance", found=True, name="Budget variance",
                            definition="The difference between budget and actual.",
                            sources=({"title": "A page", "url": "https://example.org/variance"},),
                            origin="claude_code")

    call = runner.calls[0]
    assert call["stdin"] == "budget variance"
    instructions = Path(research_module.__file__).with_name("researcher.md").read_text(encoding="utf-8")
    assert call["system"] == instructions
    argv, flags = call["argv"], call["flags"]
    assert argv[0] == "claude" and argv[1] == "-p"
    assert flags["--tools"] == "WebSearch" and flags["--allowedTools"] == "WebSearch"
    assert flags["--disallowedTools"] == "mcp__*"
    assert flags["--model"] == "some-model" and flags["--output-format"] == "json"
    for flag in ("--safe-mode", "--strict-mcp-config", "--no-chrome", "--disable-slash-commands",
                 "--no-session-persistence"):
        assert flag in argv, flag
    assert "--bare" not in argv
    schema = json.loads(flags["--json-schema"])
    assert schema["required"] == ["found", "name", "definition", "sources"]


def test_claude_code_researcher_needs_sources_to_count_as_found():
    no_sources = FakeRunner({"found": True, "name": "Something", "definition": "Words.", "sources": []})
    lookup = ClaudeCodeResearcher("m", runner=no_sources).look_up("something")
    assert lookup.found is False and lookup.sources == ()
    not_found = FakeRunner({"found": False, "name": "", "definition": "", "sources": []})
    missing = ClaudeCodeResearcher("m", runner=not_found).look_up("zzz")
    assert missing.found is False and missing.origin == "claude_code"


def test_claude_code_researcher_errors():
    with pytest.raises(RuntimeError, match="structured"):
        ClaudeCodeResearcher("m", runner=FakeRunner(None)).look_up("x")
    with pytest.raises(RuntimeError, match="not logged in"):
        ClaudeCodeResearcher("m", runner=FakeRunner(None, is_error=True, result="not logged in")).look_up("x")
