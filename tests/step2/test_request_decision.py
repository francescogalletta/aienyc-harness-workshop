"""SPEC 5.9: what the person is shown for a request, and what their answer does."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (ACCEPT_WORDS, NEW_BLOCK, REPLACE_BLOCK, REQUEST_QUESTION, STEP_BLOCK, events, payloads,
                           request_arguments, request_module, reuse_module, rows, say_text, tool_message)

REPLY = say_text("Understood.")


def declined(chat, request, answers=("no", "/quit")):
    return chat([request, REPLY], list(answers))


# ---- the request block, byte for byte ------------------------------------------------------------

def test_a_step_request_is_shown_as_its_block(chat, months_only):
    _, person = declined(chat, request_module("step", "s1"))
    assert person.told[1] == STEP_BLOCK == (
        "The assistant asks to build a module for step s1: Work out the monthly surplus.\n"
        "  To work out: the money left over each month\n"
        "  From: what comes in and what goes out each month\n"
        "  Giving: the surplus per month\n"
        "  How: what comes in minus what goes out\n"
        "  Why now: you asked what is left each month")


def test_a_new_request_is_shown_as_its_block(chat, both):
    _, person = declined(chat, request_module("new"))
    assert person.told[1] == NEW_BLOCK == (
        "The assistant asks to build a calculation that is not in the brief.\n"
        "  To work out: the cost over a whole year\n"
        "  From: the cost for one month\n"
        "  Giving: the total for a year\n"
        "  How: the monthly cost times twelve\n"
        "  Why now: you asked about a whole year")


def test_a_replace_request_is_shown_as_its_block(chat, both):
    _, person = declined(chat, request_module("replace", "monthly_surplus"))
    assert person.told[1] == REPLACE_BLOCK == (
        "The assistant asks to rebuild the module monthly_surplus, so that it takes what you have.\n"
        "  To work out: the money left over each month\n"
        "  From: a list of costs, each with a name and an amount\n"
        "  Giving: the surplus per month\n"
        "  How: what comes in minus the sum of the costs\n"
        "  Why now: you have a list of costs, not one total")


def test_a_step_request_for_an_added_step_shows_it_as_not_in_the_brief(chat, both, conn):
    step = h.add_new_step(conn)
    _, person = declined(chat, request_module("step", "added_1", **h.NEW_TEXTS))
    first = h.REQUEST_STEP.format(step="added_1 (not in the brief)", name=step["name"])
    assert person.told[1] == h.request_block(first, h.NEW_TEXTS)
    assert person.told[1].splitlines()[0] == (
        "The assistant asks to build a module for step added_1 (not in the brief): the cost over a whole year.")


def test_the_five_texts_are_used_stripped(chat, both):
    padded = {key: f"  {value}\n" for key, value in h.NEW_TEXTS.items()}
    _, person = declined(chat, request_module("new", **padded))
    assert person.told[1] == NEW_BLOCK


def test_the_block_is_said_and_then_the_question_is_asked(chat, both):
    _, person = declined(chat, request_module("new"))
    at = person.log.index(("say", NEW_BLOCK))
    assert person.log[at + 1] == ("ask", REQUEST_QUESTION)
    assert person.log[at - 2:at] == [("say", "  (thinking)"), ("call", "analyst")]


def test_nothing_is_said_after_the_question_when_the_person_declines(chat, both):
    _, person = declined(chat, request_module("new"))
    at = person.log.index(("ask", REQUEST_QUESTION))
    assert person.log[at + 1:at + 3] == [("say", "  (thinking)"), ("call", "analyst")]


def test_the_request_is_recorded_with_the_arguments_as_sent_and_the_block_shown(chat, both, conn):
    padded = request_arguments("new", why="  you asked about a whole year \n")
    chat([h.tool("request_module", padded), REPLY], ["no", "/quit"])
    assert events(conn, "ask.module_requested") == [("ask.module_requested", "agent", {
        "arguments": padded, "request": NEW_BLOCK})]


# ---- the answer ---------------------------------------------------------------------------------

def test_an_empty_answer_asks_again_with_the_same_question_and_records_nothing(chat, both, conn):
    _, person = declined(chat, request_module("new"), ["", "   ", "no", "/quit"])
    assert person.asked == [REQUEST_QUESTION] * 3 + ["Understood."]
    assert len(events(conn, "ask.module_decision")) == 1 and len(events(conn, "ask.module_requested")) == 1


def test_the_block_is_not_shown_again_when_the_question_is_asked_again(chat, both):
    _, person = declined(chat, request_module("new"), ["", "no", "/quit"])
    assert person.told.count(NEW_BLOCK) == 1


@pytest.mark.parametrize("word", sorted(ACCEPT_WORDS) + ["YES", "Okay", "  Yes.  ", "Sí", "\n/accept\n"])
def test_an_accept_word_accepts_whatever_its_case(chat, both, conn, word):
    chat([request_module("new"), reuse_module("monthly_surplus"), REPLY], [word, "/quit"])
    [(_, actor, decision)] = events(conn, "ask.module_decision")
    assert actor == "person" and decision == {"decision": "accepted", "text": word.strip()}


@pytest.mark.parametrize("answer", ["no", "not now", "yeah", "/skip", "n", "later", "yes?", "sure", "maybe yes",
                                    "nope, yes", "yes-ish", "yesplease", "y_es"])
def test_any_other_answer_declines(chat, both, conn, answer):
    model, person = declined(chat, request_module("new"), [answer, "/quit"])
    assert len(model.calls) == 2 and person.asked == [REQUEST_QUESTION, "Understood."]
    assert events(conn, "ask.module_decision") == [("ask.module_decision", "person", {
        "decision": "declined", "text": answer})]
    assert rows(conn, "added_steps") == []


# SPEC 6.6: at this question only, an answer accepts when its first word is an accept word, once the characters
# . , ! ; : are taken off the end of that word.
@pytest.mark.parametrize("answer", ["yes please", "Yes, please", "ok!", "/accept now", "yes use those", "YES.",
                                    "Okay; go on", "sí, claro", "y: now", "yes...", "yes,,", "  yes   please  ",
                                    "\tyes\tplease", "Y! go", "/accept."])
def test_a_first_word_that_is_an_accept_word_accepts(chat, both, conn, answer):
    model, person = chat([request_module("new"), reuse_module("monthly_surplus"), REPLY], [answer, "/quit"])
    assert events(conn, "ask.module_decision") == [("ask.module_decision", "person", {
        "decision": "accepted", "text": answer.strip()})]
    assert [r["name"] for r in rows(conn, "added_steps")] == [h.NEW_TEXTS["works_out"]]       # the build started
    assert model.roles()[:2] == ["analyst", "spec_writer"]


def test_a_lenient_yes_to_a_request_is_not_a_message_of_the_person(chat, both, conn):
    chat([request_module("new"), reuse_module("monthly_surplus"), REPLY], ["yes use those", "/quit"])
    assert payloads(conn, "ask.message") == [{"text": h.QUESTION}]


@pytest.mark.parametrize("answer, accepted", [
    ("yes", True), ("Yes", True), ("YES.", True), ("y", True), ("ok", True), ("okay", True), ("si", True),
    ("sí", True), ("/accept", True), ("/ACCEPT", True), ("yes please", True), ("Yes, please", True), ("ok!", True),
    ("/accept now", True), ("yes use those", True), ("y; ok", True), ("yes!!", True), ("yes.,", True),
    ("sí:", True), ("  yes please", True), ("yes\nplease", True), ("\t/accept\tnow", True),
    ("yeah", False), ("no", False), ("not now", False), ("later", False), ("", False), ("   ", False),
    ("yes?", False), ("ok?", False), ("!yes", False), (".yes", False), ("noyes", False), ("yes-please", False),
    ("no, yes", False), ("please yes", False), ("/skip", False), ("/quit", False), ("yess", False)])
def test_says_yes(agent, answer, accepted):
    assert agent.says_yes(answer) is accepted


def test_says_yes_does_not_change_the_accept_words(agent):
    from harness.calc import builder
    assert builder.ACCEPT_WORDS == ACCEPT_WORDS
    for word in ACCEPT_WORDS:
        assert agent.says_yes(word) and agent.says_yes(word.upper())


# SPEC 6.6: nowhere else is the answer lenient. A plan answered "yes please" is feedback, an example answered
# "yes please" is free text for the example helper.
def test_the_plan_check_stays_strict(build_one, conn):
    result, model, person = build_one([h.propose_spec(), h.propose_spec(h.revised_spec())], ["yes please", "/quit"])
    assert payloads(conn, "calc.plan_decision")[0] == {"step": "s1", "round": 1, "decision": "feedback", "text": "yes please"}
    assert result["outcome"] == "not_built"


def test_a_worked_example_stays_strict(build_one, conn):
    script = [h.propose_spec(), h.propose_examples(), h.respond("skip")]
    result, model, person = build_one(script, ["yes", "yes please", "/quit"])
    assert payloads(conn, "calc.example_reply") == [{"module": "monthly_surplus", "index": 1, "text": "yes please"}]
    assert payloads(conn, "calc.golden_decision")[0]["decision"] == "skipped"


def test_the_answer_is_stripped_before_it_is_recorded_and_returned(chat, both, conn):
    model, _ = declined(chat, request_module("new"), ["  not now \n", "/quit"])
    assert payloads(conn, "ask.module_decision") == [{"decision": "declined", "text": "not now"}]
    assert json.loads(tool_message(model, 1)["content"]) == {"outcome": "declined", "said": "not now"}


def test_quit_declines_and_the_conversation_goes_on(chat, both, conn):
    script = [request_module("new"), REPLY, say_text("Of course.")]
    model, person = chat(script, [" /quit ", "Anything else?", "/quit"])
    assert person.asked == [REQUEST_QUESTION, "Understood.", "Of course."] and len(model.calls) == 3
    assert payloads(conn, "ask.module_decision") == [{"decision": "declined", "text": "/quit"}]
    assert tool_message(model, 1)["content"] == json.dumps({"outcome": "declined", "said": "/quit"})
    assert payloads(conn, "ask.message")[-1] == {"text": "Anything else?"}


def test_the_answer_to_the_question_is_not_a_message_of_the_person(chat, both, conn):
    declined(chat, request_module("new"), ["no thanks", "/quit"])
    assert payloads(conn, "ask.message") == [{"text": h.QUESTION}]


def test_a_decline_is_an_outcome_and_not_an_error(chat, both):
    model, _ = declined(chat, request_module("new"))
    result = tool_message(model, 1)
    assert not result.get("is_error")
    assert result["content"] == json.dumps({"outcome": "declined", "said": "no"})
    assert result["tool_call_id"] == model.calls[1]["messages"][1]["tool_calls"][0]["id"]


def test_a_decline_builds_nothing_and_adds_nothing(chat, both, conn):
    model, person = declined(chat, request_module("new"))
    assert model.roles() == ["analyst", "analyst"]
    assert rows(conn, "added_steps") == [] and rows(conn, "notes") == []
    assert not [t for t in person.told if t.startswith("Step ")]


def test_the_events_of_a_declined_request(chat, both, conn):
    declined(chat, request_module("new"))
    mine = [(k, a, p) for k, a, p in events(conn) if k.startswith("ask.module")]
    assert mine == [
        ("ask.module_requested", "agent", {"arguments": request_arguments("new"), "request": NEW_BLOCK}),
        ("ask.module_decision", "person", {"decision": "declined", "text": "no"}),
        ("ask.module_outcome", "harness", {"outcome": "declined", "said": "no"})]
