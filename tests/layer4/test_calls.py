"""SPEC 6.2: calls that are the person's. The question arrives in the chat with options, the core's waiting slot
holds the conversation, the person picks an option or answers in their own words, and the record is the step's."""
import json

import pytest

from harness.needs_you import calls
from layer4_helpers import act, ask, assistant, events, problems, refused, reply, run, say, step_of

QUESTION = "Is 30 enough?"
OPTIONS = ["Keep it at 30", "Raise it", "Look at it again later"]


def asking(open_session, *after, **more):
    """A session that has run `total` and put the decision to the person; returns it with the waiting state."""
    session = open_session([run("total", {"a": 10, "b": 20}), ask("j1", QUESTION, OPTIONS, runs=[1], **more), *after])
    return session, say(session, "A is 10 and B is 20. Is the total enough?")


def test_a_decision_stops_the_conversation_and_marks_the_step_that_needs_the_person(open_session):
    session, state = asking(open_session, reply("Noted."), suggested=2, why="It leaves room.")
    assert state["lanes"]["main"] == "waiting"
    (message,) = [each for each in state["chat"] if each["kind"] == "decision"]
    decision = message["decision"]
    assert state["waiting"] == {"kind": "decision", "decision": decision["id"], "step": "j1"}
    assert message["text"] == QUESTION == decision["question"] and message["step"] == "j1"
    assert (decision["options"], decision["suggested"], decision["status"], decision["choice"]) == (
        OPTIONS, 2, "open", None)
    step = step_of(state, "j1")
    assert step["needs_you"] and step["line"] == {"text": "Needs you · your call", "kind": "strong"}
    assert step["calls"] == {"open": decision["id"], "records": []}
    assert [each["id"] for each in state["steps"] if each["needs_you"]] == ["j1"]
    assert problems(state, strict=True) == []
    assert events(session, "you.decision_asked")[0]["runs"] == [1]


def test_choosing_posts_the_option_as_the_persons_message_and_answers_the_decision(open_session):
    session, state = asking(open_session, reply("Then we keep 30."), suggested=1, why="Simple.")
    decision = next(each for each in state["chat"] if each["kind"] == "decision")["decision"]["id"]
    state = act(session, "choose", decision=decision, option=1)
    posted = state["chat"][-2]
    assert (posted["who"], posted["text"], posted["step"]) == ("you", OPTIONS[0], "j1")
    assert assistant(state)[-1]["text"] == "Then we keep 30."          # the analyst got the choice and went on
    told = json.loads(session.script.calls[2]["messages"][-1]["content"])
    assert (told["outcome"], told["choice"], told["option"]) == ("decided", "1", OPTIONS[0])
    assert told["judgment_steps"] == [{"id": "j1", "name": "Is it enough?", "decided": True}]
    assert state["waiting"] is None and state["lanes"]["main"] == "idle"
    step = step_of(state, "j1")
    assert not step["needs_you"] and step["calls"]["open"] is None
    (record,) = step["calls"]["records"]
    assert (record["decision"], record["question"], record["options"], record["choice"], record["words"]) == (
        decision, QUESTION, OPTIONS, "1", OPTIONS[0])
    assert step["line"] == {"text": "Decided", "kind": None}
    message = next(each for each in state["chat"] if each["kind"] == "decision")
    assert (message["decision"]["status"], message["decision"]["choice"]) == ("answered", "1")
    assert events(session, "you.decision")[0]["choice"] == "1"
    assert problems(state, strict=True) == []


def test_the_person_can_answer_in_their_own_words(open_session):
    session, state = asking(open_session, reply("Then 45 it is."))
    state = say(session, "Neither, I want to try 45")
    told = json.loads(session.script.calls[2]["messages"][-1]["content"])
    assert (told["choice"], told["option"], told["said"]) == ("something else", None, "Neither, I want to try 45")
    (record,) = step_of(state, "j1")["calls"]["records"]
    assert (record["choice"], record["words"]) == ("something else", "Neither, I want to try 45")
    assert assistant(state)[-1]["text"] == "Then 45 it is."        # their 45 is a source: the reply was not held back


@pytest.mark.parametrize("words, choice", [("2", "2"), ("option 3.", "3"), ("raise it", "2"), ("yes", "1"),
                                           ("maybe", "something else")])
def test_an_option_is_read_from_a_number_its_words_or_yes_for_the_suggestion(open_session, words, choice):
    session, state = asking(open_session, reply("Noted."), suggested=1, why="Simple.")
    say(session, words)
    assert json.loads(session.script.calls[2]["messages"][-1]["content"])["choice"] == choice


def test_choose_is_refused_when_that_decision_is_not_the_one_waiting(open_session):
    session = open_session([reply("Hello")])
    say(session, "Hello")
    assert refused(session, "choose", decision="d1", option=1)               # nothing waits
    session, state = asking(open_session, reply("Noted."))
    decision = state["waiting"]["decision"]
    assert refused(session, "choose", decision="d99", option=1)
    for bad in ({"decision": decision}, {"decision": decision, "option": "x"}, {"decision": decision, "option": 9}):
        with pytest.raises(ValueError):
            session.act("choose", bad)
    assert session.state()["waiting"]["decision"] == decision               # still waiting
    act(session, "choose", decision=decision, option=2)
    assert refused(session, "choose", decision=decision, option=2)            # answered once


def test_a_decision_that_does_not_meet_the_checks_is_sent_back_and_never_asked(open_session):
    bad = [ask("zz", QUESTION, OPTIONS), ask("j1", " ", OPTIONS), ask("j1", QUESTION, ["Only one"]),
           ask("j1", QUESTION, ["Same", "same"]), ask("j1", QUESTION, OPTIONS, suggested=4, why="x"),
           ask("j1", QUESTION, OPTIONS, suggested=1), ask("j1", QUESTION, OPTIONS, runs=[7]),
           ask("j1", "Is 31 enough?", OPTIONS, runs=[1]), ask("j1", QUESTION, OPTIONS)]
    bad[-1]["tool_calls"][0]["arguments"]["runs"] = "none"
    session = open_session([run("total", {"a": 10, "b": 20}), *bad, reply("I could not ask.")])
    state = say(session, "A is 10 and B is 20. Is it enough?")
    assert state["waiting"] is None and not [m for m in state["chat"] if m["kind"] == "decision"]
    assert len(events(session, "you.decision_refused")) == len(bad) - 1       # the unbacked 31 is a correction
    assert events(session, "ask.correction")[0]["reason"] == "ask_decision"
    assert session.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_at_most_two_decisions_are_put_to_the_person_for_one_message(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}),
                            ask("j1", QUESTION, OPTIONS, runs=[1]), ask("j1", "Is it still enough?", OPTIONS, runs=[1]),
                            ask("j1", "And now?", OPTIONS, runs=[1]), reply("Enough questions.")])
    state = say(session, "A is 10 and B is 20")
    state = act(session, "choose", decision=state["waiting"]["decision"], option=1)
    state = act(session, "choose", decision=state["waiting"]["decision"], option=2)
    assert state["waiting"] is None and assistant(state)[-1]["text"] == "Enough questions."
    assert len(events(session, "you.decision_asked")) == 2 and len(events(session, "you.decision_refused")) == 1


def test_a_number_in_the_question_leads_to_the_step_that_produced_it(open_session):
    session, state = asking(open_session, reply("Noted."))
    message = next(each for each in state["chat"] if each["kind"] == "decision")
    (figure,) = message["figures"]
    assert (figure["text"], figure["step"], figure["run"]) == ("30", "c1", "r1")
    assert message["text"][figure["start"]:figure["end"]] == "30"


def test_calls_belong_to_the_your_call_steps_and_to_any_step_a_decision_named(open_session):
    session, state = asking(open_session, reply("Noted."))
    assert step_of(state, "j1")["calls"] == {"open": state["waiting"]["decision"], "records": []}
    assert step_of(state, "c1")["calls"] is None and step_of(state, "c3")["calls"] is None
    say(session, "1")
    session2 = open_session([run("total", {"a": 10, "b": 20}), ask("c1", "Is the sum right?", ["Yes", "No"], runs=[1]),
                             reply("Noted.")])
    state = say(session2, "A is 10 and B is 20")
    assert step_of(state, "c1")["calls"]["open"] == state["waiting"]["decision"] and step_of(state, "c1")["needs_you"]
    assert step_of(state, "j1")["calls"]["open"] is None and not step_of(state, "j1")["needs_you"]


def test_a_decision_asked_by_a_process_that_is_gone_is_not_open_any_more(open_session):
    session, state = asking(open_session)
    session.close()
    again = open_session([])
    state = again.state()
    message = next(each for each in state["chat"] if each["kind"] == "decision")
    assert (message["decision"]["status"], message["decision"]["choice"]) == ("answered", None)
    assert state["waiting"] is None and not any(step["needs_you"] for step in state["steps"])
    assert step_of(state, "j1")["calls"] == {"open": None, "records": []}


def test_what_the_person_decided_is_told_to_the_analyst_so_it_is_not_asked_again(open_session):
    session, state = asking(open_session, reply("Noted."), reply("As you decided."))
    say(session, "2")
    say(session, "Anything else?")
    known = session.script.calls[-1]["system"].split("## What you know")[1]
    assert "[decisions]" in known and QUESTION in known and '"choice": "2"' in known
    assert "[decisions]" in session.script.calls[0]["system"]
    assert calls.read_choice("2", OPTIONS, None) == "2"


def test_the_decisions_expectation_counts_what_was_decided_on_a_step(open_session):
    from harness.needs_you.layer import LAYER
    session, state = asking(open_session, reply("Noted."))
    say(session, "2")
    expect = LAYER.expects["decisions"]
    assert expect.validate([{"step": "j1", "choice": "2", "count": 1}]) is None
    assert expect.validate([{"step": 1}]) and expect.validate("j1")
    assert expect.check([{"step": "j1", "choice": "2"}], session)["passed"]
    assert not expect.check([{"step": "j1", "choice": "1"}], session)["passed"]
    assert not expect.check([{"step": "j1", "count": 2}], session)["passed"]


def test_a_decision_shows_longer_decimals_as_the_harness_writes_numbers(open_session):
    session = open_session([run("total", {"a": "1000", "b": "888.888888888"}),
                            ask("j1", "Save 1888.888888888 a month?", ["Yes, 1888.888888888", "No"], runs=[1],
                                suggested=1, why="It leaves 1888.888888888 spare."), reply("Noted.")])
    state = say(session, "A is 1000 and B is 888.888888888. Should I save it?")
    (message,) = [each for each in state["chat"] if each["kind"] == "decision"]
    decision = message["decision"]
    assert message["text"] == decision["question"] == "Save 1,888.89 a month?"
    assert decision["options"] == ["Yes, 1,888.89", "No"] and decision["why"] == "It leaves 1,888.89 spare."
    (figure,) = [each for each in message["figures"] if each["text"] == "1,888.89"]
    assert (figure["step"], figure["run"]) == ("c1", "r1")
    assert problems(state, strict=True) == []
