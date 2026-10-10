"""SPEC 8.5: one side conversation (`run_aside`): the banners, the turns, `/back`, `/quit`, the carry question and
the limits. Everything the person sees is marked, except the two banners."""
import pytest

import step4_helpers as s4
from step4_helpers import (ASIDE_CARRY, ASIDE_CLOSE, ASIDE_FIRST, ASIDE_LIMIT, ASIDE_NESTED, ASIDE_OPEN, ASIDE_THINKING,
                           MAX_ASIDE_TURNS, h, marked, side)

THINK = ("say", marked(ASIDE_THINKING))
CALL = ("call", "aside")


def events_of(conn, kind):
    return [payload for _, _, payload in h.events(conn, kind)]


def replies(count):
    return [side(f"Reply {n}.") for n in range(1, count + 1)]


def test_a_side_conversation_of_one_turn_shows_exactly_this(one_aside):
    outcome, person, _ = one_aside([side("It is a thing.")], ["/back", "no"], first="What is it?")
    assert outcome == ("back", None)
    assert person.log == [("say", ASIDE_OPEN), THINK, CALL, ("ask", marked("It is a thing.")), ("ask", marked(ASIDE_CARRY)),
                          ("say", ASIDE_CLOSE)]


@pytest.mark.parametrize("typed", ["/aside what about this?"])
def test_the_command_inside_a_side_conversation_is_refused_and_the_same_text_asked_again(one_aside, conn, typed):
    outcome, person, model = one_aside(replies(1), [typed, "/back", "no"], first="What?")
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks == [marked("Reply 1.")] * 2 + [marked(ASIDE_CARRY)]
    assert person.log.count(("say", marked(ASIDE_NESTED))) == 1
    assert len(model.calls) == 1 and [p["text"] for p in events_of(conn, "aside.message")] == ["What?"]
    assert len(events_of(conn, "aside.opened")) == 1 and outcome == ("back", None)


@pytest.mark.parametrize("typed", ["/quit"])
def test_quit_in_any_case_ends_it_at_once_with_nothing_carried_and_no_carry_question(one_aside, typed):
    outcome, person, _ = one_aside(replies(1), [typed], first="What?")
    assert outcome == ("quit", None)
    assert ("ask", marked(ASIDE_CARRY)) not in person.log and person.log[-1] == ("say", ASIDE_CLOSE)


def test_what_the_person_types_at_the_carry_question_is_carried_as_typed_once_stripped(one_aside, conn):
    outcome, person, _ = one_aside(replies(1), ["/back", "   Rent is 1,100 now,\n  not 1,150.  "], first="What?")
    assert outcome == ("back", "Rent is 1,100 now,\n  not 1,150.")
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 1, "how": "back",
                                                "carried": "Rent is 1,100 now,\n  not 1,150."}]


def test_the_sixth_turn_shows_its_reply_and_the_limit_without_asking_for_another_message(one_aside, conn):
    answers = ["two", "three", "four", "five", "six", "carry this"]
    outcome, person, model = one_aside(replies(6), answers, first="one")
    assert outcome == ("limit", "carry this") and len(model.calls) == 6
    assert person.log[-4:] == [("say", marked("Reply 6.")), ("say", marked(ASIDE_LIMIT.format(limit=6))),
                               ("ask", marked(ASIDE_CARRY)), ("say", ASIDE_CLOSE)]
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks == [marked(f"Reply {n}.") for n in range(1, 6)] + [marked(ASIDE_CARRY)]
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 6, "how": "limit", "carried": "carry this"}]
