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


# ---- the banners and the first message --------------------------------------------------------------------------------

def test_a_side_conversation_of_one_turn_shows_exactly_this(one_aside):
    outcome, person, _ = one_aside([side("It is a thing.")], ["/back", "no"], first="What is it?")
    assert outcome == ("back", None)
    assert person.log == [("say", ASIDE_OPEN), THINK, CALL, ("ask", marked("It is a thing.")), ("ask", marked(ASIDE_CARRY)),
                          ("say", ASIDE_CLOSE)]


def test_the_banners_are_not_marked_and_everything_else_is(one_aside):
    _, person, _ = one_aside([side("One.\nTwo.")], ["/back", "no"], first="What is it?")
    shown = [text for kind, text in person.log if kind != "call"]
    assert shown[0] == ASIDE_OPEN and shown[-1] == ASIDE_CLOSE
    for text in shown[1:-1]:
        assert all(line.startswith("aside | ") for line in text.split("\n")), text
    assert ("ask", "aside | One.\naside | Two.") in person.log


def test_a_banner_is_the_text_of_the_spec(one_aside):
    _, person, _ = one_aside([side("It is a thing.")], ["/back", "no"], first="What is it?")
    assert person.log[0][1].startswith("---- Side conversation. The main conversation waits")
    assert person.log[-1][1] == "---- Back to the main conversation. ----"


def test_two_turns(one_aside):
    outcome, person, _ = one_aside(replies(2), ["Why?", "/back", "no"], first="What?")
    assert outcome == ("back", None)
    assert person.log == [("say", ASIDE_OPEN), THINK, CALL, ("ask", marked("Reply 1.")), THINK, CALL,
                          ("ask", marked("Reply 2.")), ("ask", marked(ASIDE_CARRY)), ("say", ASIDE_CLOSE)]


def test_without_a_first_message_the_person_is_asked_for_it(one_aside):
    outcome, person, model = one_aside([side("It is a thing.")], ["What is it?", "/back", "no"], first="")
    assert person.log[:2] == [("say", ASIDE_OPEN), ("ask", marked(ASIDE_FIRST))]
    assert model.calls[0]["messages"] == [{"role": "user", "content": "What is it?"}]


def test_the_first_message_asked_for_is_read_like_any_other(one_aside):
    outcome, person, model = one_aside([side("It is a thing.")], ["", "   ", "/ASIDE what", "What is it?", "/back", "no"],
                                       first="")
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks[:3] == [marked(ASIDE_FIRST)] * 3
    assert ("say", marked(ASIDE_NESTED)) in person.log and asks[3] == marked(ASIDE_FIRST)
    assert model.calls[0]["messages"] == [{"role": "user", "content": "What is it?"}]


def test_back_as_the_first_message_goes_back_with_no_turn(one_aside, conn):
    outcome, person, model = one_aside([], ["/back", "no"], first="")
    assert outcome == ("back", None) and model.calls == []
    assert events_of(conn, "aside.message") == [] and events_of(conn, "aside.closed")[0]["turns"] == 0
    assert person.log == [("say", ASIDE_OPEN), ("ask", marked(ASIDE_FIRST)), ("ask", marked(ASIDE_CARRY)), ("say", ASIDE_CLOSE)]


def test_quit_as_the_first_message_ends_it_with_nothing_carried(one_aside, conn):
    outcome, person, model = one_aside([], ["/quit"], first="")
    assert outcome == ("quit", None) and model.calls == []
    assert person.log == [("say", ASIDE_OPEN), ("ask", marked(ASIDE_FIRST)), ("say", ASIDE_CLOSE)]
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 0, "how": "quit", "carried": None}]


def test_the_first_message_is_stripped(one_aside, conn):
    _, _, model = one_aside([side("Fine.")], ["/back", "no"], first="  What is it?  ")
    assert model.calls[0]["messages"][0]["content"] == "What is it?"
    assert events_of(conn, "aside.message") == [{"aside": 1, "text": "What is it?"}]


# ---- reading a message -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("typed", ["", "   ", "\n"])
def test_an_empty_message_asks_again_with_the_same_text_and_is_not_a_turn(one_aside, conn, typed):
    _, person, model = one_aside(replies(2), ["Why?", typed, "/back", "no"], first="What?")
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks == [marked("Reply 1."), marked("Reply 2."), marked("Reply 2."), marked(ASIDE_CARRY)]
    assert len(model.calls) == 2
    assert [p["text"] for p in events_of(conn, "aside.message")] == ["What?", "Why?"]


def test_an_empty_message_is_asked_again_with_the_same_text(one_aside):
    _, person, _ = one_aside(replies(1), ["", " ", "/back", "no"], first="What?")
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks == [marked("Reply 1.")] * 3 + [marked(ASIDE_CARRY)]


@pytest.mark.parametrize("typed", ["/aside", "/ASIDE", "/Aside what about this?", "  /aside  ", "/aside\nsomething"])
def test_the_command_inside_a_side_conversation_is_refused_and_the_same_text_asked_again(one_aside, conn, typed):
    outcome, person, model = one_aside(replies(1), [typed, "/back", "no"], first="What?")
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks == [marked("Reply 1.")] * 2 + [marked(ASIDE_CARRY)]
    assert person.log.count(("say", marked(ASIDE_NESTED))) == 1
    assert len(model.calls) == 1 and [p["text"] for p in events_of(conn, "aside.message")] == ["What?"]
    assert len(events_of(conn, "aside.opened")) == 1 and outcome == ("back", None)


def test_the_refusal_is_said_before_the_question_is_asked_again(one_aside):
    _, person, _ = one_aside(replies(1), ["/aside", "/back", "no"], first="What?")
    k = person.log.index(("say", marked(ASIDE_NESTED)))
    assert person.log[k - 1] == ("ask", marked("Reply 1.")) and person.log[k + 1] == ("ask", marked("Reply 1."))


@pytest.mark.parametrize("typed", ["/back", "/BACK", "  /Back  "])
def test_back_in_any_case_goes_back(one_aside, typed):
    outcome, _, _ = one_aside(replies(1), [typed, "no"], first="What?")
    assert outcome == ("back", None)


@pytest.mark.parametrize("typed", ["/quit", "/QUIT", "  /Quit "])
def test_quit_in_any_case_ends_it_at_once_with_nothing_carried_and_no_carry_question(one_aside, typed):
    outcome, person, _ = one_aside(replies(1), [typed], first="What?")
    assert outcome == ("quit", None)
    assert ("ask", marked(ASIDE_CARRY)) not in person.log and person.log[-1] == ("say", ASIDE_CLOSE)


@pytest.mark.parametrize("typed", ["/backwards", "/quitting", "/back now", "back", "quit"])
def test_other_words_are_the_next_message(one_aside, typed):
    outcome, person, model = one_aside(replies(2), [typed, "/back", "no"], first="What?")
    assert len(model.calls) == 2 and model.calls[1]["messages"][-1] == {"role": "user", "content": typed}


def test_the_message_is_stripped_before_it_is_used(one_aside, conn):
    _, _, model = one_aside(replies(2), ["   Why   now?  \n", "/back", "no"], first="What?")
    assert model.calls[1]["messages"][-1] == {"role": "user", "content": "Why   now?"}
    assert events_of(conn, "aside.message")[1] == {"aside": 1, "text": "Why   now?"}


# ---- carrying back -----------------------------------------------------------------------------------------------------------

def test_what_the_person_types_at_the_carry_question_is_carried_as_typed_once_stripped(one_aside, conn):
    outcome, person, _ = one_aside(replies(1), ["/back", "   Rent is 1,100 now,\n  not 1,150.  "], first="What?")
    assert outcome == ("back", "Rent is 1,100 now,\n  not 1,150.")
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 1, "how": "back",
                                                "carried": "Rent is 1,100 now,\n  not 1,150."}]


@pytest.mark.parametrize("typed", ["", "  ", "no", "NO", "N", "n", "Nothing", "no.", "No.", "/skip", "/back", "/other"])
def test_nothing_is_carried_for_an_empty_answer_a_nothing_word_or_a_command(one_aside, conn, typed):
    outcome, _, _ = one_aside(replies(1), ["/back", typed], first="What?")
    assert outcome == ("back", None)
    assert events_of(conn, "aside.closed")[0]["carried"] is None


@pytest.mark.parametrize("typed", ["no thanks", "nope", "Not now", "none", "yes", "n.", "no!"])
def test_any_other_text_is_carried(one_aside, typed):
    outcome, _, _ = one_aside(replies(1), ["/back", typed], first="What?")
    assert outcome == ("back", typed)


@pytest.mark.parametrize("typed", ["/quit", "/QUIT", " /Quit "])
def test_quit_at_the_carry_question_makes_it_a_quit_with_nothing_carried(one_aside, conn, typed):
    outcome, person, _ = one_aside(replies(1), ["/back", typed], first="What?")
    assert outcome == ("quit", None)
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 1, "how": "quit", "carried": None}]
    assert person.log[-1] == ("say", ASIDE_CLOSE)


def test_the_carry_question_is_asked_once_and_not_again_for_a_nothing(one_aside):
    _, person, _ = one_aside(replies(1), ["/back", "no"], first="What?")
    assert person.log.count(("ask", marked(ASIDE_CARRY))) == 1


# ---- the turn limit ----------------------------------------------------------------------------------------------------------

def test_the_limit_is_six_turns(one_aside):
    assert MAX_ASIDE_TURNS == 6


def test_the_sixth_turn_shows_its_reply_and_the_limit_without_asking_for_another_message(one_aside, conn):
    answers = ["two", "three", "four", "five", "six", "carry this"]
    outcome, person, model = one_aside(replies(6), answers, first="one")
    assert outcome == ("limit", "carry this") and len(model.calls) == 6
    assert person.log[-4:] == [("say", marked("Reply 6.")), ("say", marked(ASIDE_LIMIT.format(limit=6))),
                               ("ask", marked(ASIDE_CARRY)), ("say", ASIDE_CLOSE)]
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks == [marked(f"Reply {n}.") for n in range(1, 6)] + [marked(ASIDE_CARRY)]
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 6, "how": "limit", "carried": "carry this"}]


def test_the_limit_line_is_the_one_of_the_spec(one_aside):
    _, person, _ = one_aside(replies(6), ["b", "c", "d", "e", "f", "no"], first="a")
    assert ("say", "aside | That is as far as one side conversation goes: 6 messages.") in person.log


def test_quit_at_the_carry_question_after_the_limit(one_aside, conn):
    outcome, _, _ = one_aside(replies(6), ["b", "c", "d", "e", "f", "/quit"], first="a")
    assert outcome == ("quit", None)
    assert events_of(conn, "aside.closed")[0]["how"] == "quit"


def test_refused_and_empty_messages_are_not_turns(one_aside):
    answers = ["b", "", "/aside", "c", "d", "e", "f", "no"]
    outcome, person, model = one_aside(replies(6), answers, first="a")
    assert outcome == ("limit", None) and len(model.calls) == 6


def test_five_turns_are_not_the_limit(one_aside):
    outcome, person, model = one_aside(replies(5), ["b", "c", "d", "e", "/back", "no"], first="a")
    assert outcome == ("back", None) and ("say", marked(ASIDE_LIMIT.format(limit=6))) not in person.log


# ---- the messages the side assistant gets ---------------------------------------------------------------------------------------

def test_each_turn_adds_the_message_and_the_reply_and_only_those(one_aside):
    _, _, model = one_aside(replies(3), ["Second.", "Third.", "/back", "no"], first="First.")
    assert [call["messages"] for call in model.calls] == [
        [{"role": "user", "content": "First."}],
        [{"role": "user", "content": "First."}, {"role": "assistant", "content": "Reply 1."},
         {"role": "user", "content": "Second."}],
        [{"role": "user", "content": "First."}, {"role": "assistant", "content": "Reply 1."},
         {"role": "user", "content": "Second."}, {"role": "assistant", "content": "Reply 2."},
         {"role": "user", "content": "Third."}]]


def test_the_side_assistant_is_called_for_nothing_else(one_aside):
    _, _, model = one_aside(replies(2), ["Second.", "/back", "no"], first="First.")
    assert model.roles() == ["aside", "aside"]


# ---- events ---------------------------------------------------------------------------------------------------------------------

def test_the_events_of_a_side_conversation_in_order_with_their_actors_and_payloads(one_aside, conn):
    one_aside(replies(2), ["Second.", "/back", "no"], first="First.", looking_at="The block", aside_number=3)
    rows = [(kind, actor, payload) for kind, actor, payload in h.events(conn) if kind.startswith("aside.")]
    assert rows == [
        ("aside.opened", "person", {"aside": 3, "first": "First.", "looking_at": "The block"}),
        ("aside.message", "person", {"aside": 3, "text": "First."}),
        ("aside.reply", "agent", {"aside": 3, "text": "Reply 1."}),
        ("aside.message", "person", {"aside": 3, "text": "Second."}),
        ("aside.reply", "agent", {"aside": 3, "text": "Reply 2."}),
        ("aside.closed", "person", {"aside": 3, "turns": 2, "how": "back", "carried": None})]


def test_the_opened_event_has_null_looking_at_when_nothing_was_shown(one_aside, conn):
    one_aside(replies(1), ["/back", "no"], first="First.")
    assert events_of(conn, "aside.opened") == [{"aside": 1, "first": "First.", "looking_at": None}]


def test_the_opened_event_has_an_empty_first_when_none_was_typed(one_aside, conn):
    one_aside(replies(1), ["What?", "/back", "no"], first="")
    assert events_of(conn, "aside.opened")[0]["first"] == ""


def test_every_event_carries_the_session_id(one_aside, conn):
    one_aside(replies(1), ["/back", "no"], first="First.", session_id="chat-77")
    sessions = {r["session_id"] for r in conn.execute("SELECT session_id FROM events WHERE kind LIKE 'aside.%'")}
    assert sessions == {"chat-77"}


def test_the_reply_is_recorded_without_the_marks(one_aside, conn):
    one_aside([side("One.\nTwo.")], ["/back", "no"], first="First.")
    assert events_of(conn, "aside.reply") == [{"aside": 1, "text": "One.\nTwo."}]


def test_nothing_but_events_is_written(one_aside, conn):
    before = {t: len(h.rows(conn, t)) for t in ("decisions", "inputs", "notes", "calc_runs", "added_steps")}
    one_aside(replies(2), ["Second.", "/back", "I want to pass this on"], first="First.")
    assert {t: len(h.rows(conn, t)) for t in before} == before


def test_the_carried_text_is_in_the_closed_event_and_not_in_a_message_of_the_conversation(one_aside, conn):
    one_aside(replies(1), ["/back", "Pass this on"], first="First.")
    assert events_of(conn, "aside.closed")[0]["carried"] == "Pass this on"
    assert h.events(conn, "ask.message") == []
