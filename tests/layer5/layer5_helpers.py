"""Helpers for the layer 5 tests: layer 4's small plan and scripted turns, a model that keeps the analyst's script
apart from the reviewer's, a fake researcher, and scripted reviewer reports."""
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "layer4"))      # layer4_helpers and below

from layer4_helpers import (SETTLE, act, assistant, ask, call, chat_of, events, notices, problems,  # noqa: E402,F401
                            refused, reply, run, say, small_plan, step_of, until, write_world)

from harness.grounding.research import Lookup  # noqa: E402
from harness.model import ScriptedModel  # noqa: E402

SOURCE = {"title": "Sinking fund (Wikipedia)", "url": "https://en.wikipedia.org/wiki/Sinking_fund"}


class SplitModel:
    """One model for the session: calls with the reviewer's tools go to `reviewer`, the others to `analyst`.
    `gate`, if set, is an Event the reviewer waits for before each answer (`entered` is set when it arrives)."""

    def __init__(self, analyst=(), reviewer=()):
        self.analyst, self.reviewer = ScriptedModel(list(analyst)), ScriptedModel(list(reviewer))
        self.gate, self.entered = None, threading.Event()

    def complete(self, *, system, messages, tools=()):
        if {tool.name for tool in tools} == {"look_up", "report"}:
            self.entered.set()
            if self.gate is not None:
                self.gate.wait(10)
            return self.reviewer.complete(system=system, messages=messages, tools=tools)
        return self.analyst.complete(system=system, messages=messages, tools=tools)


class FakeResearcher:
    """Answers from a dict of query -> Lookup fields; a query it does not know is not found; `broken` raises."""

    def __init__(self, known=None, broken=False):
        self.known, self.broken, self.asked = known or {}, broken, []

    def look_up(self, query):
        self.asked.append(query)
        if self.broken:
            raise RuntimeError("unreachable")
        found = self.known.get(query)
        if found is None:
            return Lookup(query=query, found=False, origin="fake")
        return Lookup(query=query, found=True, name=found["name"], definition=found["definition"],
                      sources=(found.get("source", SOURCE),), origin="fake")


SINKING = {"sinking fund": {"name": "Sinking fund",
                            "definition": "Money set aside on a schedule to pay a known cost later."}}


def challenge(step="c1", title="Amount B may not hold", kind="challenge", concern="B is taken as fixed.",
              proposal="Ask whether B can change.", change="input", impact="medium", sources=()):
    return {"step": step, "kind": kind, "title": title, "concern": concern, "proposal": proposal,
            "change": change, "impact": impact, "sources": list(sources)}


def question(step="c1", title="Is B before tax?", concern="Is amount B before tax?"):
    return challenge(step=step, title=title, kind="question", concern=concern, proposal="", change="none")


def report(*challenges):
    return call("report", challenges=list(challenges))


def look_up(query):
    return call("look_up", query=query)


def threads_of(state, kind="review"):
    return [thread for thread in state["threads"] if thread["kind"] == kind]


def open_challenges(state):
    return [thread["challenge"] for thread in threads_of(state) if thread["challenge"]["status"] == "open"]


def pass_now(session, trigger="tests"):
    """Ask for a pass directly (automatic passes may be off) and wait for it."""
    from harness.review import reviewer
    reviewer.queue_pass(session, trigger)
    return session.settle(SETTLE)


def reviewer_input(session, n=0):
    """The text the reviewer was given in its n-th model call of the session."""
    return session.model_double.reviewer.calls[n]["messages"][0]["content"]
