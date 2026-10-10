"""SPEC 8.3: what the person is shown for a judgment, how the answer is read, what is recorded and what the agent gets."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (DECISION_QUESTION, DECISION_QUESTION_SUGGESTED, ask_decision, decision_block, h)

OK = "Done."
OPTIONS = ["Keep the date", "Move the date", "Ask the landlord"]
BOTH = [DECISION_QUESTION, DECISION_QUESTION_SUGGESTED]
S2 = {"id": "s2", "name": "Decide how much to set aside"}


def decide(ask_agent, answer, *, options=OPTIONS, extra=("/quit",), **changes):
    """One decision answered with `answer`. Returns (result dict, model, person)."""
    model, person = ask_agent([ask_decision(options=options, **changes), h.say_text(OK)], [answer, *extra])
    return json.loads(h.tool_message(model, 1)["content"]), model, person


def log_without_progress(person):
    return s4.quiet(person)


def position(person, entry):
    return person.log.index(entry)


# ---- what is shown ---------------------------------------------------------------------------------------------------

def test_the_block_is_said_and_then_the_question_is_asked(ask_agent):
    _, _, person = decide(ask_agent, "1")
    block = decision_block("Should the date stay or move?", OPTIONS)
    k = position(person, ("say", block))
    assert person.log[k + 1] == ("ask", DECISION_QUESTION)


def test_with_a_recommendation_the_question_offers_yes(ask_agent):
    _, _, person = decide(ask_agent, "1", recommendation=2, why="It leaves room.")
    block = decision_block("Should the date stay or move?", OPTIONS, 2, "It leaves room.")
    k = position(person, ("say", block))
    assert person.log[k + 1] == ("ask", DECISION_QUESTION_SUGGESTED)


def test_the_block_names_the_step_when_there_is_one(ask_agent):
    _, _, person = decide(ask_agent, "1", step="s2", recommendation=1, why="Safest.")
    assert ("say", decision_block("Should the date stay or move?", OPTIONS, 1, "Safest.", S2)) in person.log


def test_a_step_given_as_an_empty_string_is_no_step(ask_agent):
    _, _, person = decide(ask_agent, "1", step="")
    assert ("say", decision_block("Should the date stay or move?", OPTIONS)) in person.log


def test_a_step_of_the_process_that_is_not_a_judgment_is_named_too(ask_agent):
    _, _, person = decide(ask_agent, "1", step="s1")
    step = {"id": "s1", "name": "Work out the monthly surplus"}
    assert ("say", decision_block("Should the date stay or move?", OPTIONS, step=step)) in person.log


def test_an_added_step_is_named_with_its_label(ask_agent, conn):
    h.add_new_step(conn, session_id="earlier")
    _, _, person = decide(ask_agent, "1", step="added_1")
    step = {"id": "added_1", "name": h.NEW_TEXTS["works_out"]}
    assert ("say", decision_block("Should the date stay or move?", OPTIONS, step=step)) in person.log


def test_every_text_is_shown_as_one_line_and_the_arguments_are_kept_as_sent(ask_agent, conn):
    arguments = s4.ask_decision_arguments(question="  Should the\ndate   stay?  ", options=["Keep\n the date ", " Move\tit"],
                                          recommendation=2, why="  It   is\nsafer. ")
    model, person = ask_agent([h.tools(("ask_decision", arguments)), h.say_text(OK)], ["1", "/quit"])
    block = ("Only you can decide this:\n  Should the date stay?\n    1. Keep the date\n    2. Move it\n"
             "  The assistant suggests 2: It is safer.")
    assert ("say", block) in person.log
    [(kind, actor, payload)] = h.events(conn, "ask.decision_asked")
    assert (kind, actor) == ("ask.decision_asked", "agent")
    assert list(payload) == ["arguments", "block"] and payload == {"arguments": arguments, "block": block}


def test_nothing_is_said_or_asked_for_a_decision_before_the_checks_pass(ask_agent):
    _, _, person = decide(ask_agent, "1")
    assert [text for kind, text in person.log if kind == "ask"] == [DECISION_QUESTION, OK]


def test_a_decision_is_one_block_one_question(ask_agent):
    _, _, person = decide(ask_agent, "1")
    assert len([1 for kind, text in person.log if kind == "say" and text.startswith("Only you can decide")]) == 1
    assert len([1 for kind, text in person.log if kind == "ask" and text in BOTH]) == 1


# ---- reading the answer ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer, choice", [
    ("1", "1"), ("2", "2"), ("3", "3"), ("2.", "2"), ("3)", "3"), ("option 2", "2"), ("Option 3.", "3"),
    ("keep the date", "1"), ("MOVE THE DATE", "2"), ("  Ask   the\nlandlord ", "3")])
def test_a_number_or_the_text_of_an_option_picks_it(ask_agent, conn, answer, choice):
    result, _, _ = decide(ask_agent, answer)
    assert result["choice"] == choice and result["option"] == OPTIONS[int(choice) - 1]
    assert s4.decision_rows(conn)[0]["choice"] == choice


@pytest.mark.parametrize("answer", ["4", "option 5", "0", "Neither", "I would wait a week", "2 and 3", "yes please",
                                    "keep the date, please", "/quit"])
def test_anything_else_is_something_else_with_the_persons_words(ask_agent, conn, answer):
    result, _, _ = decide(ask_agent, answer)
    assert result["choice"] == "something else" and result["option"] is None and result["said"] == answer
    [row] = s4.decision_rows(conn)
    assert row["choice"] == "something else" and row["words"] == answer


@pytest.mark.parametrize("answer", sorted(h.ACCEPT_WORDS) + ["YES", "Yes."])
def test_an_accept_word_takes_the_suggestion(ask_agent, answer):
    result, _, _ = decide(ask_agent, answer, recommendation=3, why="Cheapest.")
    assert result["choice"] == "3" and result["option"] == "Ask the landlord" and result["said"] == answer


def test_yes_without_a_suggestion_is_something_else(ask_agent):
    result, _, _ = decide(ask_agent, "yes")
    assert result["choice"] == "something else" and result["option"] is None


def test_a_number_beats_the_suggestion(ask_agent):
    result, _, _ = decide(ask_agent, "1", recommendation=3, why="Cheapest.")
    assert result["choice"] == "1"


def test_the_answer_is_stripped(ask_agent, conn):
    result, _, _ = decide(ask_agent, "  2  ")
    assert result["said"] == "2" and s4.decision_rows(conn)[0]["words"] == "2"


def test_an_empty_answer_asks_again_with_the_same_text_and_records_nothing(ask_agent, conn):
    model, person = ask_agent([ask_decision(options=OPTIONS, recommendation=1, why="Simplest."), h.say_text(OK)],
                              ["", "   ", "2", "/quit"])
    asks = [text for kind, text in person.log if kind == "ask"]
    assert asks[:3] == [DECISION_QUESTION_SUGGESTED] * 3
    assert len(s4.decision_rows(conn)) == 1 and s4.decision_rows(conn)[0]["words"] == "2"
    assert len(h.events(conn, "ask.decision")) == 1 and len(h.events(conn, "ask.decision_asked")) == 1


def test_an_empty_answer_is_not_a_person_message_of_the_conversation(ask_agent, conn):
    ask_agent([ask_decision(), h.say_text(OK)], ["", "1", "/quit"])
    assert [p["text"] for _, _, p in h.events(conn, "ask.message")][0] == h.QUESTION
    assert len(h.events(conn, "ask.decision")) == 1


def test_the_answer_to_a_decision_is_not_a_person_message(ask_agent, conn):
    ask_agent([ask_decision(), h.say_text(OK)], ["Put 3,333 aside", "/quit"])
    texts = [p["text"] for _, _, p in h.events(conn, "ask.message")]
    assert "Put 3,333 aside" not in texts


# ---- the result ------------------------------------------------------------------------------------------------------

def test_the_result_is_not_an_error_and_is_exactly_this_json(ask_agent, conn):
    model, _ = ask_agent([ask_decision(options=OPTIONS), h.say_text(OK)], ["2", "/quit"])
    message = h.tool_message(model, 1)
    assert not message.get("is_error")
    expected = {"outcome": "decided", "decision": 1, "choice": "2", "option": "Move the date", "said": "2",
                "judgment_steps": [{"id": "s2", "name": "Decide how much to set aside", "decided": False}]}
    assert message["content"] == json.dumps(expected)


def test_something_else_has_a_null_option(ask_agent):
    model, _ = ask_agent([ask_decision(options=OPTIONS), h.say_text(OK)], ["Neither", "/quit"])
    expected = {"outcome": "decided", "decision": 1, "choice": "something else", "option": None, "said": "Neither",
                "judgment_steps": [{"id": "s2", "name": "Decide how much to set aside", "decided": False}]}
    assert h.tool_message(model, 1)["content"] == json.dumps(expected)


def test_the_option_is_given_as_one_line(ask_agent):
    result, _, _ = decide(ask_agent, "2", options=["Keep it", "  Move   the\ndate "])
    assert result["option"] == "Move the date"


def test_the_decision_in_the_result_is_the_id_of_the_record(ask_agent, conn):
    script = [ask_decision(question="First?"), ask_decision(question="Second?"), h.say_text(OK)]
    model, _ = ask_agent(script, ["1", "2", "/quit"])
    assert json.loads(h.tool_message(model, 1)["content"])["decision"] == 1
    assert json.loads(h.tool_message(model, 2)["content"])["decision"] == 2


def test_the_decision_id_follows_the_decisions_of_other_kinds(ask_agent, conn):
    model, _ = ask_agent([s4.run(), ask_decision(), h.say_text(OK)], ["yes", "1", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"])["decision"] == 2


def judgment_brief(*, extra=()):
    brief = h.make_brief()
    brief["process"] = [*brief["process"],
                        {"id": "s4", "name": "Decide on a date", "kind": "judgment", "needs": ["s3"], "produces": "A date"},
                        {"id": "s5", "name": "Work out the cost", "kind": "calculation", "method": "arithmetic",
                         "formula": "cost = 1", "needs": ["s4"], "produces": "A cost"}]
    return brief


def steps_of(model, call_index):
    return json.loads(h.tool_message(model, call_index)["content"])["judgment_steps"]


def test_the_judgment_steps_are_every_judgment_of_the_process_in_process_order(ask_agent):
    model, _ = ask_agent([ask_decision(), h.say_text(OK)], ["1", "/quit"], brief=judgment_brief())
    assert steps_of(model, 1) == [{"id": "s2", "name": "Decide how much to set aside", "decided": False},
                                  {"id": "s4", "name": "Decide on a date", "decided": False}]
    assert list(steps_of(model, 1)[0]) == ["id", "name", "decided"]


def test_a_step_is_decided_once_the_session_has_a_judgment_for_it_whatever_the_choice(ask_agent):
    script = [ask_decision(step="s4", question="Which date?"), ask_decision(step="s2", question="How much?"),
              h.say_text(OK)]
    model, _ = ask_agent(script, ["Neither", "2", "/quit"], brief=judgment_brief())
    assert [s["decided"] for s in steps_of(model, 1)] == [False, True]
    assert [s["decided"] for s in steps_of(model, 2)] == [True, True]


def test_a_decision_without_a_step_decides_no_step(ask_agent):
    model, _ = ask_agent([ask_decision(), h.say_text(OK)], ["1", "/quit"], brief=judgment_brief())
    assert [s["decided"] for s in steps_of(model, 1)] == [False, False]


def test_a_decision_for_a_step_that_is_not_a_judgment_is_not_listed(ask_agent):
    model, _ = ask_agent([ask_decision(step="s1"), h.say_text(OK)], ["1", "/quit"], brief=judgment_brief())
    assert [s["id"] for s in steps_of(model, 1)] == ["s2", "s4"] and [s["decided"] for s in steps_of(model, 1)] == [False, False]


def test_a_decision_of_another_session_does_not_decide_a_step(agent, conn, brief, installed):
    for session, expected in (("earlier-chat", [False]), ("this-chat", [True])):
        person = h.Person("1", "/quit")
        model = s4.Model([ask_decision(step="s2"), h.say_text(OK)], person)
        agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=session,
                        question=h.QUESTION, today=h.DAY)
        assert [s["decided"] for s in steps_of(model, 1)] == [True]
    person = h.Person("1", "/quit")
    model = s4.Model([ask_decision(), h.say_text(OK)], person)
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="third-chat",
                    question=h.QUESTION, today=h.DAY)
    assert [s["decided"] for s in steps_of(model, 1)] == [False]


def test_a_judgment_decision_of_a_build_or_a_gate_does_not_decide_a_step(ask_agent):
    model, _ = ask_agent([s4.run(), ask_decision(), h.say_text(OK)], ["yes", "1", "/quit"])
    assert steps_of(model, 2) == [{"id": "s2", "name": "Decide how much to set aside", "decided": False}]


def test_the_result_has_the_answer_as_the_person_wrote_it_stripped(ask_agent):
    result, _, _ = decide(ask_agent, "  Neither,   I will think\nabout it  ")
    assert result["said"] == "Neither,   I will think\nabout it"


# ---- the record ------------------------------------------------------------------------------------------------------

def test_the_record_of_a_judgment(ask_agent, conn):
    script = [s4.run(assumptions=[]), ask_decision(step="s2", options=[" Keep  the date ", "Move\nthe date"], runs=[1],
                                                   recommendation=2, why="Safer."), h.say_text(OK)]
    ask_agent(script, ["1", "/quit"])
    [row] = s4.decision_rows(conn)
    block = decision_block("Should the date stay or move?", ["Keep the date", "Move the date"], 2, "Safer.", S2)
    assert (row["session_id"], row["kind"], row["step_id"], row["question"]) == (h.SESSION, "judgment", "s2", block)
    assert json.loads(row["options"]) == ["Keep the date", "Move the date"]
    assert (row["choice"], row["words"], json.loads(row["runs"])) == ("1", "1", [1])


@pytest.mark.parametrize("step", [s4.DROP, None, ""])
def test_no_step_is_a_null_step(ask_agent, conn, step):
    ask_agent([ask_decision(step=step), h.say_text(OK)], ["1", "/quit"])
    assert s4.decision_rows(conn)[0]["step_id"] is None


def test_the_options_of_the_record_are_those_shown_one_line_each(ask_agent, conn):
    ask_agent([ask_decision(options=["A   one", "B\ntwo", "C"]), h.say_text(OK)], ["1", "/quit"])
    assert json.loads(s4.decision_rows(conn)[0]["options"]) == ["A one", "B two", "C"]


def test_the_record_of_something_else_has_the_words_as_typed(ask_agent, conn):
    ask_agent([ask_decision(), h.say_text(OK)], ["  Neither, I will ask my landlord  ", "/quit"])
    [row] = s4.decision_rows(conn)
    assert row["choice"] == "something else" and row["words"] == "Neither, I will ask my landlord"


def test_events_in_order_asked_then_the_decision_then_the_reply(ask_agent, conn):
    ask_agent([ask_decision(), h.say_text(OK)], ["1", "/quit"])
    kinds = s4.conversation_kinds(conn)
    assert kinds[:4] == ["ask.message", "ask.decision_asked", "ask.decision", "ask.reply"]


def test_the_event_of_the_decision_is_the_record_without_ts_and_session(ask_agent, conn):
    ask_agent([ask_decision(step="s2"), h.say_text(OK)], ["2", "/quit"])
    [(kind, actor, payload)] = h.events(conn, "ask.decision")
    assert (kind, actor) == ("ask.decision", "person")
    [decision] = s4.decisions_of(conn)
    assert payload == {key: decision[key] for key in ["id", "kind", "step", "question", "options", "choice", "words", "runs"]}
    assert payload["step"] == "s2" and payload["id"] == 1


def test_the_decision_is_listed_for_the_session(ask_agent, conn):
    ask_agent([ask_decision(), h.say_text(OK)], ["1", "/quit"])
    assert [d["kind"] for d in s4.decisions_of(conn, h.SESSION)] == ["judgment"]
    assert s4.decisions_of(conn, "somebody-else") == []


def test_the_decision_command_shows_it(ask_agent, conn):
    ask_agent([ask_decision(step="s2"), h.say_text(OK)], ["2", "/quit"])
    lines = h.run_cli(["decisions"]).stdout.splitlines()
    [decision] = s4.decisions_of(conn)
    assert lines[0] == (f"{decision['id']}  {decision['ts']}  judgment  step: s2  chose: 2. Move the date  runs: -")


# ---- what the person sees of a decision and the reply after it -----------------------------------------------------------

def test_the_agent_goes_on_with_the_result_and_the_reply_is_shown_as_usual(ask_agent):
    model, person = ask_agent([ask_decision(), h.say_text("Then we keep the date.")], ["1", "/quit"])
    assert len(model.of("analyst")) == 2
    assert s4.asked_of(person)[-1] == "Then we keep the date."


def test_a_decision_is_not_a_model_call(ask_agent):
    model, person = ask_agent([ask_decision(), h.say_text(OK)], ["1", "/quit"])
    assert model.roles() == ["analyst", "analyst"]


def test_a_reply_with_a_decision_and_a_run_handles_them_in_order(ask_agent, conn):
    script = [s4.run_pair(ask_decision(), s4.run(assumptions=[])), h.say_text(OK)]
    model, person = ask_agent(script, ["2", "/quit"])
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(messages[0]["content"])["outcome"] == "decided"
    assert json.loads(messages[1]["content"])["output"] == "2000"
    kinds = s4.conversation_kinds(conn)
    assert kinds.index("ask.decision") < kinds.index("calc.run")


def test_the_person_answers_there_and_then_before_the_next_call_of_the_reply(ask_agent):
    script = [s4.run_pair(s4.run(assumptions=[]), ask_decision(), s4.run(assumptions=[])), h.say_text(OK)]
    _, person = ask_agent(script, ["1", "/quit"])
    told = [text for kind, text in person.log if kind == "say"]
    first = told.index("  (running monthly_surplus)")
    block = next(i for i, text in enumerate(told) if text.startswith("Only you can decide"))
    second = len(told) - 1 - told[::-1].index("  (running monthly_surplus)")
    assert first < block < second
