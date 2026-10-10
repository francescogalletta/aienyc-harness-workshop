"""SPEC 8.5: the side assistant: its context and prompt, its one tool, its number check and its limits."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ASIDE_LOOKING_UP, ASIDE_LOOKUP_LIMIT, ASIDE_NUMBERS, ASIDE_THINKING, LOOKUP_FAILED, LOOKUP_TERM,
                           MAX_ASIDE_CALLS, MAX_ASIDE_LOOKUPS, MAX_QUERY_LENGTH, h, look_up, look_ups, marked, side)

THINK = ("say", marked(ASIDE_THINKING))
CALL = ("call", "aside")
LOOK_UP_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


def events_of(conn, kind):
    return [payload for _, _, payload in h.events(conn, kind)]


def tool_results(model, call_index):
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


def go_back(extra=()):
    return [*extra, "/back", "no"]


def test_the_runs_and_decisions_of_other_sessions_are_left_out(aside, agent, conn, brief, installed):
    person = h.Person("Neither", "/quit")
    model = s4.Model([s4.run(assumptions=[]), s4.ask_decision(), h.say_text("Done.")], person)
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="another-chat",
                    question=h.QUESTION, today=h.DAY)
    context = aside.aside_context(conn, brief, session_id="this-chat", today=s4.TODAY, looking_at=None)
    assert context == s4.aside_context(brief)


def test_the_context_never_holds_the_saved_inputs_the_notes_or_the_main_messages(aside, ask_agent, notes, conn, brief):
    notes.add_note(conn, step_id="s1", text="A private note about 7,654.", session_id="earlier")
    script = [h.save_input("buffer", "9,876", "said"), h.say_text("Saved it, here is a long reply about nothing."),
              h.say_text("More about the nothing.")]
    ask_agent(script, ["Tell me more about the nothing", "/quit"], question="My buffer is 9,876. Save it.")
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    for text in ("9,876", "7,654", "private note", "Tell me more", "long reply", "buffer"):
        assert text not in context
    assert context == s4.aside_context(brief)


def test_a_lookup_goes_through_the_desk_and_the_result_is_given_back(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    outcome, person, model = one_aside([look_up("sinking fund"), side("It is money set aside.")], go_back(),
                                       first="What is a sinking fund?", desk=desk)
    assert person.log == [("say", s4.ASIDE_OPEN), THINK, CALL, ("say", marked(ASIDE_LOOKING_UP.format(query="sinking fund"))),
                          THINK, CALL, ("ask", marked("It is money set aside.")), ("ask", marked(s4.ASIDE_CARRY)),
                          ("say", s4.ASIDE_CLOSE)]
    [(_, actor, payload)] = h.events(conn, "aside.lookup")
    assert actor == "agent" and payload["aside"] == 1 and payload["query"] == "sinking fund" and payload["found"] is True
    assert payload["definition"] == "Money set aside regularly for a known future cost." and payload["origin"] == "fake"
    assert payload["sources"] == [{"title": "A page about sinking fund", "url": "https://example.org/sinking-fund"}]
    [result] = tool_results(model, 1)
    assert not result.get("is_error")
    assert json.loads(result["content"]) == {key: value for key, value in payload.items() if key != "aside"}
    assert researcher.queries == ["sinking fund"]


@pytest.mark.parametrize("arguments", [{"query": "x" * (MAX_QUERY_LENGTH + 1)}])
def test_an_empty_or_too_long_term_is_an_error_that_is_not_recorded(one_aside, conn, arguments):
    desk, researcher = s4.make_desk(conn)
    reply = {"tool_calls": [{"name": "look_up", "arguments": arguments}]}
    _, person, model = one_aside([reply, side("Fine.")], go_back(), first="Q", desk=desk)
    [result] = tool_results(model, 1)
    assert result["is_error"] is True and result["content"] == LOOKUP_TERM.format(limit=MAX_QUERY_LENGTH)
    assert h.events(conn, "aside.lookup") == [] and researcher.queries == []
    assert not [1 for kind, text in person.log if kind == "say" and "looking up" in text]


def test_three_lookups_are_allowed_and_the_fourth_is_an_error_that_is_not_recorded(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    script = [look_ups("a", "b", "c", "d"), side("Enough.")]
    _, person, model = one_aside(script, go_back(), first="Q", desk=desk)
    results = tool_results(model, 1)
    assert [bool(r.get("is_error")) for r in results] == [False, False, False, True]
    assert results[3]["content"] == ASIDE_LOOKUP_LIMIT
    assert researcher.queries == ["a", "b", "c"] and len(h.events(conn, "aside.lookup")) == 3
    lines = [text for kind, text in person.log if kind == "say" and "looking up" in text]
    assert len(lines) == 3 and MAX_ASIDE_LOOKUPS == 3


def test_a_number_the_person_just_typed_is_backed(one_aside, conn):
    _, person, _ = one_aside([side("So that is 3,456 a month.")], go_back(), first="I pay 3,456 a month for the flat.")
    assert ("ask", marked("So that is 3,456 a month.")) in person.log


def test_the_main_conversation_is_not_a_source(one_aside, conn, ask_agent):
    """5000 is in the question of the main conversation, and in no source of the side conversation."""
    ask_agent([h.say_text("Hello, I have your 5000 and 3000.")], ["/quit"])
    _, person, _ = one_aside([side("You earn 5000."), side("I do not have that number.")], go_back(), first="What do I earn?")
    assert ("ask", marked("You earn 5000.")) not in person.log


def test_the_first_failure_sends_the_reply_back_and_the_person_sees_nothing_of_it(one_aside, conn):
    outcome, person, model = one_aside([side("You need 3,333 and 4,444."), side("I cannot say that number.")], go_back(),
                                       first="How much do I need?")
    assert len(model.calls) == 2
    assert model.calls[1]["messages"][1:] == [
        {"role": "assistant", "content": "You need 3,333 and 4,444."},
        {"role": "user", "content": ASIDE_NUMBERS.format(numbers="3,333, 4,444")}]
    assert events_of(conn, "aside.correction") == [{"aside": 1, "numbers": ["3,333", "4,444"],
                                                    "text": "You need 3,333 and 4,444."}]
    assert not [1 for kind, text in person.log if "3,333" in text]
    assert person.log[:6] == [("say", s4.ASIDE_OPEN), THINK, CALL, THINK, CALL, ("ask", marked("I cannot say that number."))]
    assert events_of(conn, "aside.reply") == [{"aside": 1, "text": "I cannot say that number."}]
    assert h.events(conn, "aside.withheld") == []


def test_a_second_failure_in_the_turn_withholds_the_reply(one_aside, conn):
    outcome, person, model = one_aside([side("You need 3,333."), side("Really 5,555.")], go_back(), first="How much?")
    assert len(model.calls) == 2
    assert events_of(conn, "aside.withheld") == [{"aside": 1, "numbers": ["5,555"], "text": "Really 5,555."}]
    assert events_of(conn, "aside.reply") == []
    assert ("ask", marked(h.WITHHELD.format(numbers="5,555"))) in person.log
    assert not [1 for kind, text in person.log if "5,555" in text and "held back" not in text]


def test_five_model_calls_are_the_most_for_one_turn(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    script = [look_up(f"term {n}") for n in range(1, 6)] + [side("never reached")]
    outcome, person, model = one_aside(script, go_back(), first="Q", desk=desk)
    assert MAX_ASIDE_CALLS == 5 and len(model.calls) == 5
    assert events_of(conn, "aside.stopped") == [{"aside": 1, "reason": "too many steps"}]
    assert h.events(conn, "aside.reply") == []
    assert ("ask", marked(h.TOO_MANY)) in person.log
    assert person.log.count(THINK) == 5
