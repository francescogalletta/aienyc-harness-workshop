"""Helpers for the layer 1 tests: a small valid brief, and scripted model turns."""
import copy
from pathlib import Path

PROPOSED = {"kind": "proposed"}
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SETTLE = 10


def item(text, origin=None):
    return {"text": text, "origin": origin or PROPOSED}


def small_brief(**changes) -> dict:
    """A valid brief of two steps and one input; `changes` replace top-level keys."""
    brief = {
        "goal": item("Have enough saved for the move", {"kind": "person", "quote": "save for a move"}),
        "mode": "one_off",
        "scope": {"in": [item("The cost of the move")], "out": [item("Choosing the new home")]},
        "glossary": [{"term": "Sinking fund", "definition": "Money set aside for a known cost.",
                      "person_says": "the pot", "source": "https://example.test/sinking-fund"}],
        "particulars": [
            {"what": "Rent is paid twice for a month", "handling": "Count it as a cost of the move",
             "step": "a1", "origin": PROPOSED},
            {"what": "Figures are in euros", "handling": "Say so in every answer", "step": None, "origin": PROPOSED}],
        "inputs": [{"name": "Van hire", "description": "The quoted price", "origin": PROPOSED}],
        "process": [
            {"id": "a1", "name": "Move cost", "kind": "calculation", "method": "Sinking fund",
             "formula": "van hire + rent", "needs": ["Van hire"], "produces": "total", "cadence": "once",
             "origin": {"kind": "looked_up", "source": "https://example.test/sinking-fund"}},
            {"id": "a2", "name": "Keep the date?", "kind": "judgment", "method": "", "formula": "",
             "needs": ["a1"], "produces": "a decision", "cadence": "", "origin": PROPOSED}],
        "definition_of_done": [item("I know how much to put aside")],
        "open_questions": [{"text": "Is the date fixed?", "step": "a2", "origin": PROPOSED},
                           {"text": "Is there a second van?", "step": None, "origin": PROPOSED}],
    }
    brief.update(copy.deepcopy(changes))
    return brief


def write_brief(brief=None, **changes):
    """A model turn that submits a brief."""
    return {"tool_calls": [{"name": "write_brief", "arguments": brief or small_brief(**changes)}]}


def asks(text):
    """A model turn that asks the person a question."""
    return {"text": text}


def looks_up(*terms):
    return {"tool_calls": [{"name": "look_up", "arguments": {"query": term}} for term in terms]}


PLAN = {"tool_calls": [{"name": "plan_research", "arguments": {"terms": ["sinking fund"]}}]}


def say(session, text, step=None):
    session.act("say", {"text": text, "step": step})
    return session.settle(SETTLE)
