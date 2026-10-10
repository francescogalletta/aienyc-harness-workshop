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


# ---- the answer ---------------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["yes"])
def test_an_accept_word_accepts_whatever_its_case(chat, both, conn, word):
    chat([request_module("new"), reuse_module("monthly_surplus"), REPLY], [word, "/quit"])
    [(_, actor, decision)] = events(conn, "ask.module_decision")
    assert actor == "person" and decision == {"decision": "accepted", "text": word.strip()}


@pytest.mark.parametrize("answer", ["no"])
def test_any_other_answer_declines(chat, both, conn, answer):
    model, person = declined(chat, request_module("new"), [answer, "/quit"])
    assert len(model.calls) == 2 and person.asked == [REQUEST_QUESTION, "Understood."]
    assert events(conn, "ask.module_decision") == [("ask.module_decision", "person", {
        "decision": "declined", "text": answer})]
    assert rows(conn, "added_steps") == []


