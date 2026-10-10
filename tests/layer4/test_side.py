"""SPEC 6.4: side threads. A sub-agent with its own context answers on the side lane, in any phase, while the
main lane works or waits; it changes nothing, and neither sees the other's conversation."""
import json
import threading

import pytest

from harness.config import load_config
from harness.core import BadAction, Session
from harness.model import ScriptedModel
from harness.terminal import Terminal
from layer4_helpers import (SETTLE, act, ask, assistant, call, events, problems, refused, reply, run, say,
                            step_of, until)

SIDE_START = "You help one person understand"
OPTIONS = ["Keep it at 30", "Raise it"]


class Held(ScriptedModel):
    """A scripted model that can be made to wait inside a call."""

    def __init__(self, script, hold=None):
        super().__init__(script)
        self.hold, self.entered = hold, threading.Event()

    def complete(self, **options):
        self.entered.set()
        if self.hold is not None:
            assert self.hold.wait(SETTLE)
        return super().complete(**options)


class Routed:
    """One model for the session: the side assistant's calls go to `side`, every other to `main`."""

    def __init__(self, main, side):
        self.main, self.side = main, side

    def complete(self, *, system, messages, tools=()):
        target = self.side if system.startswith(SIDE_START) else self.main
        return target.complete(system=system, messages=messages, tools=tools)


@pytest.fixture
def routed(world):
    opened = []

    def make(main=(), side_script=(), *, hold_main=None, hold_side=None):
        model = Routed(Held(main, hold_main), Held(side_script, hold_side))
        session = Session(load_config(), model_factory=lambda: model)
        session.models = model
        session.memory["today"] = "2026-10-10"
        opened.append(session)
        session.settle(SETTLE)
        return session

    yield make
    for session in opened:
        session.close()


def threads(state):
    return state["threads"]


def open_thread(session, text="What is this?", step=None):
    payload = {"text": text, **({"step": step} if step else {})}
    applied, why = session.act("side", payload)
    assert applied, why
    return session.settle(SETTLE)


def test_a_side_thread_is_answered_and_follows_the_last_main_message(routed):
    session = routed(main=[reply("Ask me about the plan.")], side_script=[reply("It adds the two amounts.")])
    state = say(session, "hello")
    last = state["chat"][-1]["id"]
    state = open_thread(session, "What does this step do?", step="c1")
    (thread,) = threads(state)
    assert (thread["kind"], thread["step"], thread["title"], thread["after"], thread["status"]) == (
        "side", "c1", "Total", last, "open")
    assert [(m["who"], m["text"]) for m in thread["messages"]] == [
        ("you", "What does this step do?"), ("assistant", "It adds the two amounts.")]
    assert all(m["sources"] == [] for m in thread["messages"]) and thread["challenge"] is None
    assert state["activity"] == [] and state["lanes"]["side"] == "idle"
    assert [m["id"] for m in state["chat"]][-1] == last                 # nothing was added to the main chat
    assert problems(state, strict=True) == []
    assert [e["thread"] for e in events(session, "you.side_opened")] == [thread["id"]]
    assert events(session, "you.side_message") and events(session, "you.side_reply")


def test_a_thread_without_a_step_is_titled_by_its_first_words_and_stays_where_it_began(routed):
    session = routed(main=[reply("One."), reply("Two.")], side_script=[reply("A short answer.")])
    state = say(session, "first")
    first = state["chat"][-1]["id"]
    state = open_thread(session, "What is a sinking fund and why would anybody use one at all?")
    assert 0 < len(threads(state)[0]["title"]) <= 45 and threads(state)[0]["step"] is None
    state = say(session, "second")
    assert threads(state)[0]["after"] == first and state["chat"][-1]["id"] != first


def test_a_reply_in_the_thread_is_a_new_answer_with_the_thread_as_its_whole_conversation(routed):
    session = routed(side_script=[reply("First answer."), reply("Second answer.")])
    state = open_thread(session, "First question")
    thread = threads(state)[0]["id"]
    state = act(session, "side", text="Second question", thread=thread)
    assert [m["who"] for m in threads(state)[0]["messages"]] == ["you", "assistant", "you", "assistant"]
    sent = session.models.side.calls[-1]["messages"]
    assert [(m["role"], m["content"]) for m in sent] == [
        ("user", "First question"), ("assistant", "First answer."), ("user", "Second question")]


def test_a_thread_takes_six_messages_and_bad_requests_are_refused(routed):
    session = routed(side_script=[reply(f"Answer {n}.") for n in "abcdef"])
    thread = threads(open_thread(session, "one"))[0]["id"]
    for n in range(5):
        act(session, "side", text=f"more {n}", thread=thread)
    assert "limit" in refused(session, "side", text="one too many", thread=thread)
    assert "no such" in refused(session, "side", text="hello", thread="t99").lower()
    for payload in ({"text": " "}, {"text": "x", "step": "zz"}, {"text": "x", "thread": "nonsense"}, {"text": 5}):
        with pytest.raises(BadAction):
            session.act("side", payload)


def test_a_side_thread_works_before_there_is_a_plan(tmp_path):
    model = ScriptedModel([reply("A running balance is the amount left after each payment.")])
    session = Session(load_config(), model_factory=lambda: model)
    try:
        state = open_thread(session, "What is a running balance?")
        assert state["phase"] == "empty" and threads(state)[0]["messages"][-1]["who"] == "assistant"
        assert threads(state)[0]["after"] is None and problems(state) == []
    finally:
        session.close()


def test_the_main_lane_keeps_waiting_for_the_person_while_a_side_thread_is_answered(routed):
    session = routed(main=[run("total", {"a": 10, "b": 20}), ask("j1", "Is 30 enough?", OPTIONS, runs=[1]),
                           reply("Noted.")],
                     side_script=[reply("A judgment step is yours to decide.")])
    state = say(session, "A is 10 and B is 20. Is the total enough?")
    assert state["lanes"]["main"] == "waiting"
    state = open_thread(session, "What is a judgment step?", step="j1")
    assert state["waiting"]["kind"] == "decision" and state["lanes"]["main"] == "waiting"
    assert threads(state)[0]["messages"][-1]["text"] == "A judgment step is yours to decide."
    decision = next(m for m in state["chat"] if m["kind"] == "decision")["decision"]
    assert decision["status"] == "open"                                  # the thread decided nothing
    assert problems(state, strict=True) == []
    state = act(session, "choose", decision=decision["id"], option=1)
    assert state["lanes"]["main"] == "idle" and assistant(state)[-1]["text"] == "Noted."


def test_a_thread_is_answered_while_the_main_lane_is_busy_and_activity_names_it(routed):
    hold_main, hold_side = threading.Event(), threading.Event()
    session = routed(main=[reply("Main answer.")], side_script=[reply("Side answer.")],
                     hold_main=hold_main, hold_side=hold_side)
    session.act("say", {"text": "a question"})
    assert session.models.main.entered.wait(SETTLE)
    assert session.state()["lanes"]["main"] == "working"
    session.act("side", {"text": "a side question"})
    assert session.models.side.entered.wait(SETTLE)
    state = session.state()
    (entry,) = [e for e in state["activity"] if e["lane"] == "side"]
    assert entry["thread"] == threads(state)[0]["id"] and entry["what"] == "side"
    assert state["lanes"]["main"] == "working" and state["lanes"]["side"] == "working"
    assert problems(state) == []
    hold_side.set()
    state = until(session, lambda s: s["lanes"]["side"] == "idle")
    assert state["lanes"]["main"] == "working" and threads(state)[0]["messages"][-1]["text"] == "Side answer."
    hold_main.set()
    state = session.settle(SETTLE)
    assert assistant(state)[-1]["text"] == "Main answer."
    assert threads(state)[0]["after"] == state["chat"][0]["id"]          # it began after the person's message


def test_neither_conversation_sees_the_other(routed):
    session = routed(main=[reply("Main one."), reply("Main two.")],
                     side_script=[reply("The side answer, not for the analyst.")])
    say(session, "My first main question")
    open_thread(session, "A purple elephant question")
    say(session, "My second main question")
    main_text = json.dumps([c["messages"] for c in session.models.main.calls]) + \
        "".join(c["system"] for c in session.models.main.calls)
    assert "purple elephant" not in main_text and "not for the analyst" not in main_text
    sent = session.models.side.calls[0]
    assert [m["content"] for m in sent["messages"]] == ["A purple elephant question"]
    assert "Main one." in sent["system"] and "My first main question" in sent["system"]      # last chat lines, as text
    assert sent["tools"][0].name == "look_up" and len(sent["tools"]) == 1


def test_what_is_said_in_a_thread_is_not_a_source_for_the_main_analyst(routed):
    session = routed(main=[reply("Your budget is 777."), reply("I could not confirm that figure.")],
                     side_script=[reply("Noted that you said so.")])
    open_thread(session, "My budget is 777, what does that mean?")
    say(session, "What is my budget?")
    assert events(session, "ask.correction")[0]["numbers"] == ["777"]


def test_the_side_assistant_cannot_change_anything(routed):
    session = routed(side_script=[call("run_module", module="total", inputs={"a": "10", "b": "20"}, assumptions=[],
                                       expected="30"),
                                  call("save_input", name="x", value="1", note=""),
                                  reply("I cannot run that here; ask in the main chat.")])
    before = session.state()
    state = open_thread(session, "Please work out the total", step="c1")
    assert threads(state)[0]["messages"][-1]["who"] == "assistant"
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 0
    assert session.conn.execute("SELECT COUNT(*) FROM inputs").fetchone()[0] == 0
    assert [m["is_error"] for m in session.models.side.calls[-1]["messages"] if m["role"] == "tool"] == [True, True]
    assert step_of(state, "c1")["last_run"] is None and state["steps"] == before["steps"]


def test_it_is_given_the_plan_and_the_attached_step_in_detail_but_never_the_code(routed):
    session = routed(side_script=[reply("It adds two amounts.")])
    open_thread(session, "Explain this", step="c1")
    system = session.models.side.calls[0]["system"]
    assert "Know the total" in system and "Is it enough?" in system             # the plan: goal, steps
    assert "checked_by" in system and "worked out by hand" in system              # the step's examples
    assert "def calculate" not in system and "module_py" not in system


def test_a_reply_may_use_numbers_it_was_given_or_the_person_wrote(routed):
    session = routed(side_script=[reply("Its first example adds 10 and 20 to make 30, and you said 12 months.")])
    state = open_thread(session, "I have 12 months. What do its examples show?", step="c1")
    assert threads(state)[0]["messages"][-1]["text"].startswith("Its first example")
    assert not events(session, "you.side_withheld")


def test_a_number_from_nowhere_is_sent_back_once_and_then_withheld(routed):
    session = routed(side_script=[reply("That comes to 4,321 in total."), reply("It is still 4,321."),
                                  reply("A clean answer.")])
    state = open_thread(session, "How much is it?")
    last = threads(state)[0]["messages"][-1]
    assert last["who"] == "assistant" and "That comes to" not in last["text"] and "still" not in last["text"]
    assert len(session.models.side.calls) == 2
    assert "4,321" in session.models.side.calls[1]["messages"][-1]["content"]
    (withheld,) = events(session, "you.side_withheld")
    assert withheld["numbers"] == ["4,321"]
    state = act(session, "side", text="Try again", thread=threads(state)[0]["id"])
    sent = session.models.side.calls[-1]["messages"]
    assert [m["role"] for m in sent] == ["user"]                           # the two questions, as one turn
    assert "held back" not in json.dumps(sent)                             # the notice is not its own reply
    assert threads(state)[0]["messages"][-1]["text"] == "A clean answer."


def test_a_lookup_sends_only_the_term_and_the_reply_names_its_source(routed):
    sent = []

    class Spy:
        def look_up_general(self, query):
            sent.append(query)
            return {"query": query, "status": "found", "name": "Sinking fund", "origin": "spy", "planned": False,
                    "definition": "Money set aside for a known future cost.",
                    "sources": [{"title": "Sinking fund (Wikipedia)", "url": "https://example.org/sf"}],
                    "cached": False}

    session = routed(side_script=[call("look_up", query="sinking fund"),
                                  reply("A sinking fund is money set aside for a known future cost.")])
    session.desk_factory = lambda conn: Spy()
    state = open_thread(session, "what is a sinking fund?")
    last = threads(state)[0]["messages"][-1]
    assert sent == ["sinking fund"]
    assert last["sources"] == [{"title": "Sinking fund (Wikipedia)", "url": "https://example.org/sf"}]
    assert events(session, "you.side_lookup")[0]["query"] == "sinking fund"
    assert problems(state, strict=True) == []


def test_the_real_desk_refuses_a_query_with_a_digit_and_at_most_three_lookups_are_made(routed):
    session = routed(side_script=[call("look_up", query="my 4500 savings"), call("look_up", query="sinking fund"),
                                  call("look_up", query="emergency fund"), call("look_up", query="inflation"),
                                  reply("I could not check all of those.")])
    state = open_thread(session, "what are these?")
    results = [m for m in session.models.side.calls[-1]["messages"] if m["role"] == "tool"]
    assert [bool(m.get("is_error")) for m in results] == [True, False, False, True]
    assert "refused" in results[0]["content"] and "No more lookups" in results[3]["content"]
    assert len(events(session, "you.side_lookup")) == 3
    assert len(threads(state)[0]["messages"][-1]["sources"]) == 2          # only the two that were found


def test_a_review_thread_can_be_replied_in_and_the_reviewers_words_are_in_the_challenge(routed):
    from harness.core import add_thread
    session = routed(side_script=[reply("It asks whether the plan is too tight.")])
    thread = add_thread(session.conn, session.conversation, kind="review", title="A challenge", step="c1")
    session.post("Is the plan too tight?", who="reviewer", thread=thread)
    state = act(session, "side", text="What does that mean?", thread=thread)
    found = next(t for t in threads(state) if t["id"] == thread)
    assert [m["who"] for m in found["messages"]] == ["reviewer", "you", "assistant"]
    sent = session.models.side.calls[0]["messages"]
    assert [(m["role"], m["content"]) for m in sent] == [("user", "What does that mean?")]


def test_the_terminal_opens_replies_and_attaches_threads(routed):
    session = routed(side_script=[reply("It adds."), reply("Still adds.")])
    lines, out = iter(["/side @c1 what does it do", "/reply and then", "/quit"]), []
    Terminal(session, read=lambda _prompt: next(lines), write=out.append, wait=0.05).run(
        stop=lambda s: s["threads"] and len(s["threads"][0]["messages"]) >= 4)
    assert any("side | assistant: Still adds." in line for line in out)
    assert threads(session.state())[0]["step"] == "c1"


def test_the_side_threads_expectation_counts_answered_threads(routed):
    from harness.needs_you.layer import LAYER
    expect = LAYER.expects["side_threads"]
    assert expect.validate(2) is None and expect.validate(-1) and expect.validate("1")
    session = routed(side_script=[reply("An answer.")])
    context = session
    assert not expect.check(1, context)["passed"]
    open_thread(session, "a question")
    assert expect.check(1, context)["passed"] and not expect.check(2, context)["passed"]
