"""SPEC 8.5: the `Asides` object that wraps `ask` and `say`, and the numbering and carrying of side conversations."""
import pytest

import step4_helpers as s4
from step4_helpers import ASIDE_CARRY, ASIDE_CLOSE, ASIDE_FIRST, ASIDE_OPEN, ASIDE_THINKING, h, marked, side

QUESTION = "Go ahead on these?"
THINK = ("say", marked(ASIDE_THINKING))


def one_side_conversation(reply="It is a thing.", carry="no"):
    """What the person is shown for a side conversation of one turn that carries `carry` back."""
    return [("say", ASIDE_OPEN), THINK, ("call", "aside"), ("ask", marked(reply)), ("ask", marked(ASIDE_CARRY)),
            ("say", ASIDE_CLOSE)]


def events_of(conn, kind):
    return [payload for _, _, payload in h.events(conn, kind)]


@pytest.mark.parametrize("answer, first", [("/aside What is a sinking fund?", "What is a sinking fund?")])
def test_the_command_opens_a_side_conversation_with_the_rest_as_its_first_message(side_talk, conn, answer, first):
    asides, person, model = side_talk([side("Reply.")], [answer, "/back", "no", "yes"])
    assert asides.ask(QUESTION) == "yes"
    [opened] = events_of(conn, "aside.opened")
    assert opened["first"] == first and opened["aside"] == 1
    assert [p["text"] for p in events_of(conn, "aside.message")][0] == first


def test_after_the_side_conversation_the_same_question_is_asked_again(side_talk):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    assert asides.ask(QUESTION) == "yes"
    assert person.log == [("ask", QUESTION), *one_side_conversation(), ("ask", QUESTION)]


def test_what_was_shown_since_the_last_answer_is_shown_again_before_the_question(side_talk):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.say("The block")
    asides.say("  more of it")
    asides.ask(QUESTION)
    assert person.log == [("say", "The block"), ("say", "  more of it"), ("ask", QUESTION), *one_side_conversation(),
                          ("say", "The block\n  more of it"), ("ask", QUESTION)]


def test_a_carried_text_is_kept_as_typed_and_given_once(side_talk):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "  Rent is 1,100 now.  ", "yes"])
    asides.ask(QUESTION)
    assert asides.carried == ["Rent is 1,100 now."]
    assert asides.take_carried() == ["Rent is 1,100 now."]
    assert asides.take_carried() == [] and asides.carried == ["Rent is 1,100 now."]


@pytest.mark.parametrize("typed", ["no"])
def test_a_text_that_is_nothing_is_not_carried(side_talk, typed):
    asides, _, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", typed, "yes"])
    asides.ask(QUESTION)
    assert asides.carried == [] and asides.take_carried() == []
