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


# ---- say and ask pass through -------------------------------------------------------------------------------------

def test_say_and_ask_go_to_the_given_functions(side_talk):
    asides, person, _ = side_talk([], ["yes"])
    asides.say("Hello")
    assert asides.ask(QUESTION) == "yes"
    assert person.log == [("say", "Hello"), ("ask", QUESTION)]


def test_an_ordinary_answer_is_returned_as_it_was_given_not_stripped(side_talk):
    asides, _, _ = side_talk([], ["  yes please \n"])
    assert asides.ask(QUESTION) == "  yes please \n"


def test_an_empty_text_is_said_like_any_other(side_talk):
    asides, person, _ = side_talk([], [])
    asides.say("")
    assert person.log == [("say", "")]


@pytest.mark.parametrize("answer", ["/asides", "/asidex", "/aside?", "/aside:why", "aside", "/Aside-this", "please /aside",
                                    "/back", "/ASIDES what", "//aside"])
def test_what_is_not_the_command_is_an_ordinary_answer(side_talk, answer):
    asides, person, model = side_talk([], [answer])
    assert asides.ask(QUESTION) == answer
    assert model.calls == [] and person.log == [("ask", QUESTION)]


@pytest.mark.parametrize("answer, first", [
    ("/aside What is a sinking fund?", "What is a sinking fund?"), ("/ASIDE what", "what"), ("/Aside   what  ", "what"),
    ("  /aside what", "what"), ("/aside\twhat", "what"), ("/aside\nwhat is this\n", "what is this"),
    ("/aside what\nand this", "what\nand this")])
def test_the_command_opens_a_side_conversation_with_the_rest_as_its_first_message(side_talk, conn, answer, first):
    asides, person, model = side_talk([side("Reply.")], [answer, "/back", "no", "yes"])
    assert asides.ask(QUESTION) == "yes"
    [opened] = events_of(conn, "aside.opened")
    assert opened["first"] == first and opened["aside"] == 1
    assert [p["text"] for p in events_of(conn, "aside.message")][0] == first


@pytest.mark.parametrize("answer", ["/aside", "/ASIDE", "  /aside  ", "/aside\n"])
def test_the_command_alone_asks_what_to_talk_through(side_talk, conn, answer):
    asides, person, _ = side_talk([side("Reply.")], [answer, "What is it?", "/back", "no", "yes"])
    assert asides.ask(QUESTION) == "yes"
    assert ("ask", marked(ASIDE_FIRST)) in person.log
    [opened] = events_of(conn, "aside.opened")
    assert opened["first"] == ""
    assert [p["text"] for p in events_of(conn, "aside.message")] == ["What is it?"]


# ---- the side conversation and the same question again ---------------------------------------------------------------

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


def test_progress_lines_are_not_part_of_what_the_person_was_looking_at(side_talk, conn):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.say("  (running monthly_surplus)")
    asides.say("The block")
    asides.say("  (thinking)")
    asides.ask(QUESTION)
    assert events_of(conn, "aside.opened")[0]["looking_at"] == "The block"
    assert person.log[-2] == ("say", "The block")


def test_only_progress_lines_means_nothing_was_looked_at(side_talk, conn):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.say("  (thinking)")
    asides.ask(QUESTION)
    assert events_of(conn, "aside.opened")[0]["looking_at"] is None
    assert person.log[-1] == ("ask", QUESTION) and person.log[-2] == ("say", ASIDE_CLOSE)


def test_with_nothing_shown_nothing_is_shown_again(side_talk, conn):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.ask(QUESTION)
    assert events_of(conn, "aside.opened")[0]["looking_at"] is None
    assert person.log == [("ask", QUESTION), *one_side_conversation(), ("ask", QUESTION)]


def test_a_text_that_starts_with_two_spaces_and_a_parenthesis_is_progress_but_not_other_indents(side_talk, conn):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.say("  (a progress line)")
    asides.say("  indented, not progress")
    asides.say(" (one space)")
    asides.ask(QUESTION)
    assert events_of(conn, "aside.opened")[0]["looking_at"] == "  indented, not progress\n (one space)"


def test_what_was_shown_is_forgotten_once_the_person_answers(side_talk, conn):
    asides, person, _ = side_talk([side("It is a thing.")], ["go on", "/aside What is it?", "/back", "no", "yes"])
    asides.say("The first block")
    assert asides.ask("First question?") == "go on"
    asides.say("The second block")
    asides.ask("Second question?")
    assert events_of(conn, "aside.opened")[0]["looking_at"] == "The second block"


def test_it_is_the_same_for_each_side_conversation_at_one_question(side_talk, conn):
    script = [side("First reply."), side("Second reply.")]
    answers = ["/aside one", "/back", "no", "/aside two", "/back", "no", "yes"]
    asides, person, _ = side_talk(script, answers)
    asides.say("The block")
    assert asides.ask(QUESTION) == "yes"
    opened = events_of(conn, "aside.opened")
    assert [(o["aside"], o["first"], o["looking_at"]) for o in opened] == [(1, "one", "The block"), (2, "two", "The block")]
    assert person.log.count(("say", "The block")) == 3 and person.log.count(("ask", QUESTION)) == 3


def test_the_block_is_shown_again_with_the_given_say_not_kept_as_shown_since_the_last_answer(side_talk, conn):
    script = [side("First reply."), side("Second reply.")]
    asides, person, _ = side_talk(script, ["/aside one", "/back", "no", "/aside two", "/back", "no", "yes"])
    asides.say("The block")
    asides.ask(QUESTION)
    assert [o["looking_at"] for o in events_of(conn, "aside.opened")] == ["The block", "The block"]


def test_side_conversations_are_numbered_from_1_in_the_order_opened(side_talk, conn):
    script = [side("First reply."), side("Second reply.")]
    asides, _, _ = side_talk(script, ["/aside one", "/back", "no", "go on", "/aside two", "/back", "no", "yes"])
    asides.ask("Q1?")
    asides.ask("Q2?")
    assert [p["aside"] for p in events_of(conn, "aside.opened")] == [1, 2]
    assert [p["aside"] for p in events_of(conn, "aside.closed")] == [1, 2]


def test_the_numbers_start_again_in_each_session(side_talk, conn):
    script = [side("A."), side("B.")]
    first, _, _ = side_talk(script[:1], ["/aside one", "/back", "no", "yes"], session_id="chat-one")
    first.ask(QUESTION)
    second, _, _ = side_talk(script[1:], ["/aside two", "/back", "no", "yes"], session_id="chat-two")
    second.ask(QUESTION)
    assert [p["aside"] for p in events_of(conn, "aside.opened")] == [1, 1]


def test_a_side_conversation_that_ends_in_quit_answers_the_question_with_quit(side_talk):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/quit"])
    asides.say("The block")
    assert asides.ask(QUESTION) == "/quit"
    assert person.log.count(("ask", QUESTION)) == 1 and person.log[-1] == ("say", ASIDE_CLOSE)
    assert person.log.count(("say", "The block")) == 1


def test_quit_at_the_carry_question_answers_the_open_question_with_quit(side_talk):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "/quit"])
    assert asides.ask(QUESTION) == "/quit"
    assert asides.carried == []


def test_a_side_conversation_ended_by_the_turn_limit_goes_back_to_the_question(side_talk):
    script = [side(f"Reply {n}.") for n in range(1, 7)]
    answers = ["/aside one", *["more"] * 5, "no", "yes"]
    asides, person, _ = side_talk(script, answers)
    assert asides.ask(QUESTION) == "yes"
    assert person.log.count(("ask", QUESTION)) == 2


# ---- carrying back --------------------------------------------------------------------------------------------------------

def test_nothing_carried_at_first(side_talk):
    asides, _, _ = side_talk([], [])
    assert asides.carried == [] and asides.take_carried() == []


def test_a_carried_text_is_kept_as_typed_and_given_once(side_talk):
    asides, person, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "  Rent is 1,100 now.  ", "yes"])
    asides.ask(QUESTION)
    assert asides.carried == ["Rent is 1,100 now."]
    assert asides.take_carried() == ["Rent is 1,100 now."]
    assert asides.take_carried() == [] and asides.carried == ["Rent is 1,100 now."]


def test_carried_texts_come_oldest_first_and_only_the_new_ones(side_talk):
    script = [side("A."), side("B."), side("C.")]
    answers = ["/aside one", "/back", "First thing.", "go", "/aside two", "/back", "Second thing.", "/aside three", "/back",
               "Third thing.", "yes"]
    asides, _, _ = side_talk(script, answers)
    asides.ask("Q1?")
    assert asides.take_carried() == ["First thing."]
    asides.ask("Q2?")
    assert asides.carried == ["First thing.", "Second thing.", "Third thing."]
    assert asides.take_carried() == ["Second thing.", "Third thing."]


@pytest.mark.parametrize("typed", ["", "   ", "no", "No", "N", "nothing", "NOTHING", "no.", "/skip", "/back", "/anything"])
def test_a_text_that_is_nothing_is_not_carried(side_talk, typed):
    asides, _, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", typed, "yes"])
    asides.ask(QUESTION)
    assert asides.carried == [] and asides.take_carried() == []


@pytest.mark.parametrize("typed", ["nope", "no thanks", "not much", "none", "Yes", "n o", "Use 1,500 for rent"])
def test_anything_else_is_carried(side_talk, typed):
    asides, _, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", typed, "yes"])
    asides.ask(QUESTION)
    assert asides.carried == [typed]


def test_the_side_conversation_that_ended_with_the_limit_can_carry_too(side_talk):
    script = [side(f"Reply {n}.") for n in range(1, 7)]
    asides, _, _ = side_talk(script, ["/aside one", *["more"] * 5, "Carry this.", "yes"])
    asides.ask(QUESTION)
    assert asides.carried == ["Carry this."]


def test_the_side_assistant_replies_are_not_carried(side_talk):
    asides, _, _ = side_talk([side("A reply nobody asked to pass on.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.ask(QUESTION)
    assert asides.carried == []


# ---- nothing is recorded as a message of the conversation, nothing counts -----------------------------------------------

def test_the_aside_answer_is_never_an_ask_message(side_talk, conn):
    asides, _, _ = side_talk([side("It is a thing.")], ["/aside What is it?", "/back", "no", "yes"])
    asides.ask(QUESTION)
    assert h.events(conn, "ask.message") == []
    assert [k for k in h.kinds(conn) if k.startswith("ask.")] == []
