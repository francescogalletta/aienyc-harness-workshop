"""SPEC 8.4: a request_module writes a decision of kind build, just after ask.module_outcome."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import decision_block, h

REPLY = h.say_text("Understood.")
ACCEPT3 = h.accepts(3)
NEW_SCRIPT = [h.request_module("new"), *h.yearly_script(), h.say_text("Built.")]
NEW_ANSWERS = ["yes", "yes", *ACCEPT3, "/quit"]


def build_decisions(conn):
    return [d for d in s4.decision_rows(conn) if d["kind"] == "build"]


def around_the_outcome(conn):
    kinds = s4.conversation_kinds(conn)
    at = kinds.index("ask.module_outcome")
    return kinds[at:at + 2]


# ---- a request that is declined -------------------------------------------------------------------------------------

@pytest.mark.parametrize("case, target, block, step_id, fixture", [
    ("step", "s1", h.STEP_BLOCK, "s1", "months_only"),
    ("new", None, h.NEW_BLOCK, None, "installed"),
    ("replace", "monthly_surplus", h.REPLACE_BLOCK, "s1", "installed")])
def test_a_declined_request_writes_a_build_decision_of_no(request, talk, conn, case, target, block, step_id, fixture):
    request.getfixturevalue(fixture)
    talk([h.request_module(case, target), REPLY], ["not now, thanks", "/quit"])
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["session_id"], row["step_id"], row["question"]) == ("build", h.SESSION, step_id, block)
    assert json.loads(row["options"]) == [] and json.loads(row["runs"]) == []
    assert (row["choice"], row["words"]) == ("no", "not now, thanks")


def test_the_words_are_the_answer_to_the_request_question_stripped(talk, months_only, conn):
    talk([h.request_module("step", "s1"), REPLY], ["  no  ", "/quit"])
    assert build_decisions(conn)[0]["words"] == "no"


def test_an_empty_answer_writes_nothing_and_the_answer_after_it_is_recorded(talk, months_only, conn):
    talk([h.request_module("step", "s1"), REPLY], ["", "no", "/quit"])
    assert [d["words"] for d in build_decisions(conn)] == ["no"]


def test_the_outcome_event_is_followed_by_the_decision_event_even_when_declined(talk, months_only, conn):
    talk([h.request_module("step", "s1"), REPLY], ["no", "/quit"])
    kinds = s4.conversation_kinds(conn)
    assert kinds[:6] == ["ask.message", "ask.module_requested", "ask.module_decision", "ask.module_outcome",
                         "ask.decision", "ask.reply"]


def test_the_decision_event_is_that_of_the_record(talk, months_only, conn):
    talk([h.request_module("step", "s1"), REPLY], ["no", "/quit"])
    [(_, actor, payload)] = h.events(conn, "ask.decision")
    assert actor == "person" and payload == {"id": 1, "kind": "build", "step": "s1", "question": h.STEP_BLOCK,
                                             "options": [], "choice": "no", "words": "no", "runs": []}


# ---- a request that is accepted ---------------------------------------------------------------------------------------

def test_a_built_step_writes_a_yes_for_its_step(talk, months_only, conn):
    script = [h.request_module("step", "s1"), *h.surplus_script(), h.say_text("Built.")]
    talk(script, ["yes", "yes", *ACCEPT3, "/quit"])
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["step_id"], row["choice"], row["words"], row["question"]) == (
        "build", "s1", "yes", "yes", h.STEP_BLOCK)


def test_the_decision_comes_after_the_whole_build(talk, months_only, conn):
    script = [h.request_module("step", "s1"), *h.surplus_script(), h.say_text("Built.")]
    talk(script, ["yes", "yes", *ACCEPT3, "/quit"])
    kinds = s4.conversation_kinds(conn)
    assert kinds.index("calc.module_registered") < kinds.index("ask.module_outcome") < kinds.index("ask.decision")
    assert kinds[kinds.index("ask.module_outcome") + 1] == "ask.decision"
    assert kinds.index("ask.module_decision") < kinds.index("calc.spec_proposed")


def test_a_new_request_that_is_accepted_names_the_added_step(talk, installed, conn):
    talk(NEW_SCRIPT, NEW_ANSWERS, question=h.YEARLY_QUESTION)
    [row] = build_decisions(conn)
    assert (row["step_id"], row["choice"], row["words"], row["question"]) == ("added_1", "yes", "yes", h.NEW_BLOCK)
    assert around_the_outcome(conn) == ["ask.module_outcome", "ask.decision"]


def test_a_new_request_that_is_declined_has_no_step(talk, installed, conn):
    talk([h.request_module("new"), REPLY], ["no", "/quit"])
    assert build_decisions(conn)[0]["step_id"] is None
    assert h.rows(conn, "added_steps") == []


def test_a_new_request_the_person_accepts_keeps_its_decision_when_the_build_does_not_end_in_a_module(talk, installed, conn):
    talk([h.request_module("new"), h.propose_spec(h.yearly_spec()), REPLY], ["yes", "/quit", "/quit"])
    [row] = build_decisions(conn)
    assert (row["step_id"], row["choice"]) == ("added_1", "yes")
    assert around_the_outcome(conn) == ["ask.module_outcome", "ask.decision"]


def test_a_new_request_that_ends_in_a_reused_module_is_a_yes_for_its_step(talk, installed, conn):
    talk([h.request_module("new"), h.reuse_module("monthly_surplus"), REPLY], ["yes", "/quit"])
    [row] = build_decisions(conn)
    assert (row["step_id"], row["choice"]) == ("added_1", "yes")


def test_a_replace_request_names_the_step_of_the_module(talk, installed, conn):
    script = [h.request_module("replace"), h.propose_spec(h.revised_spec()), REPLY]
    talk(script, ["yes", "/skip", "/quit"])
    [row] = build_decisions(conn)
    assert (row["step_id"], row["choice"], row["question"]) == ("s1", "yes", h.REPLACE_BLOCK)


def test_a_replace_request_of_a_module_for_another_step_names_that_step(talk, installed, conn):
    talk([h.request_module("replace", "months_to_goal"), REPLY], ["no", "/quit"])
    assert build_decisions(conn)[0]["step_id"] == "s3"


def test_a_step_request_for_an_added_step_names_it(talk, installed, conn):
    h.add_new_step(conn, session_id="earlier")
    talk([h.request_module("step", "added_1", **h.NEW_TEXTS), REPLY], ["no", "/quit"])
    [row] = build_decisions(conn)
    first = h.REQUEST_STEP.format(step="added_1 (not in the brief)", name=h.NEW_TEXTS["works_out"])
    assert row["step_id"] == "added_1" and row["question"] == h.request_block(first, h.NEW_TEXTS)


@pytest.mark.parametrize("answer", ["yes", "Yes, please", "ok!", "/accept now", "sí"])
def test_a_lenient_yes_is_a_yes_and_the_words_are_the_answer(talk, installed, conn, answer):
    talk([h.request_module("new"), h.reuse_module("monthly_surplus"), REPLY], [answer, "/quit"])
    [row] = build_decisions(conn)
    assert row["choice"] == "yes" and row["words"] == answer


@pytest.mark.parametrize("answer", ["no", "yeah", "later", "/skip", "yes?", "maybe"])
def test_any_other_answer_is_a_no(talk, installed, conn, answer):
    talk([h.request_module("new"), REPLY], [answer, "/quit"])
    [row] = build_decisions(conn)
    assert row["choice"] == "no" and row["words"] == answer


def test_the_choice_agrees_with_the_event_ask_module_decision(talk, installed, conn):
    for n, answer in enumerate(["no", "yes use those"], 1):
        script = [h.request_module("new", why=f"you asked about case {n}"), h.reuse_module("monthly_surplus"), REPLY]
        talk(script, [answer, "/quit"], session_id=f"chat-{n}")
    decisions = [p["decision"] for p in h.payloads(conn, "ask.module_decision")]
    assert decisions == ["declined", "accepted"]
    assert [d["choice"] for d in build_decisions(conn)] == ["no", "yes"]


# ---- requests that write nothing ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("request_", [
    h.request_module("bogus"), h.request_module("step", "s9"), h.request_module("step", "s2"),
    h.request_module("new", works_out="  "), h.request_module("replace", "ghost")])
def test_a_request_refused_by_a_check_was_never_shown_and_writes_no_decision(talk, installed, conn, request_):
    model, person = talk([request_, REPLY])
    assert h.tool_message(model, 1)["is_error"] is True
    assert s4.decision_rows(conn) == [] and h.events(conn, "ask.decision") == []
    assert h.events(conn, "ask.request_refused") != []


def test_a_step_that_already_has_a_module_is_refused_and_writes_none(talk, installed, conn):
    talk([h.request_module("step", "s1"), REPLY])
    assert s4.decision_rows(conn) == []


def test_a_request_with_an_unbacked_number_writes_no_decision(talk, installed, conn):
    talk([h.request_module("new", why="the fee of 4,321 is due"), REPLY])
    assert s4.decision_rows(conn) == [] and h.events(conn, "ask.correction") != []


def test_too_many_requests_write_one_decision_for_each_shown_request(talk, installed, conn):
    script = [h.request_module("new", works_out="first thing"), h.request_module("new", works_out="second thing"),
              h.request_module("new", works_out="third thing"), REPLY]
    talk(script, ["no", "no", "/quit"])
    assert [d["choice"] for d in build_decisions(conn)] == ["no", "no"]


# ---- the decisions command and the sources ---------------------------------------------------------------------------------------

def test_the_decisions_command_shows_a_build_decision_for_an_added_step(talk, installed, conn):
    talk(NEW_SCRIPT, NEW_ANSWERS, question=h.YEARLY_QUESTION)
    [decision] = s4.decisions_of(conn)
    lines = h.run_cli(["decisions"]).stdout.splitlines()
    assert lines[0] == f"{decision['id']}  {decision['ts']}  build  step: added_1 (not in the brief)  chose: yes  runs: -"
    assert lines[-1] == "  in their words: yes"


def test_the_words_of_the_answer_to_a_request_back_the_numbers_of_a_later_block(talk, installed, conn):
    script = [h.request_module("new"), s4.ask_decision(question="Should it be 3,333 a month?"), REPLY]
    model, person = talk(script, ["no, I would rather pay 3,333", "1", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"])["outcome"] == "decided"
    assert h.events(conn, "ask.correction") == []


def test_the_words_of_the_answer_back_a_later_reply(talk, installed, conn):
    model, person = talk([h.request_module("new"), h.say_text("You said 3,333.")], ["no, I would rather pay 3,333", "/quit"])
    assert s4.asked_of(person)[-1] == "You said 3,333." and h.events(conn, "ask.correction") == []
    assert h.events(conn, "ask.withheld") == []
