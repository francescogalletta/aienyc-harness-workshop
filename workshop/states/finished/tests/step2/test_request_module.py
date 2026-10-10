"""SPEC 5.9: `request_module`, the tool and the checks that come before the person is asked anything."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (ALREADY_BUILT, BAD_CASE, INPUTS_UNBACKED, MAX_REQUESTS, MISSING_WORDS, NO_STEP,
                           NOT_A_STEP, NOT_REGISTERED, TOO_MANY_REQUESTS, events, payloads, request_arguments,
                           request_module, say_text, tool, tool_message, tools, yearly_script)

SORRY = say_text("Sorry, I cannot say.")


def call(arguments):
    return tool("request_module", arguments)


def without(arguments, *keys):
    return {k: v for k, v in arguments.items() if k not in keys}


def refused_with(chat, error, arguments):
    """Run one request that must be refused. Check the error result, the event and that the person saw nothing."""
    model, person = chat([call(arguments), SORRY])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == error
    assert events(chat.conn, "ask.request_refused") == [("ask.request_refused", "harness", {
        "error": error, "arguments": arguments})]
    assert events(chat.conn, "ask.module_requested") == [] and events(chat.conn, "ask.module_decision") == []
    assert events(chat.conn, "ask.module_outcome") == [] and events(chat.conn, "ask.correction") == []
    assert person.asked == [SORRY["text"]] and not [t for t in person.told if t.startswith("The assistant asks")]
    assert len(model.calls) == 2
    return model, person


@pytest.fixture
def chat_(chat, installed, conn):
    """`chat` with both example modules registered and the connection within reach."""
    chat.conn = conn
    return chat


# ---- the tool and its strings ----------------------------------------------------------------


# ---- each check, in the stated order ---------------------------------------------------------


@pytest.mark.parametrize("case", ["bogus"])
def test_a_case_that_is_not_step_new_or_replace(chat_, case):
    arguments = {**request_arguments("step"), "case": case}
    refused_with(chat_, BAD_CASE, arguments)


@pytest.mark.parametrize("target, shown", [
    ("ghost", "ghost")])
def test_a_step_request_needs_a_calculation_step_of_the_process(chat_, target, shown):
    arguments = {**request_arguments("step"), "target": target}
    if target is None:
        del arguments["target"]
    refused_with(chat_, NOT_A_STEP.format(target=shown), arguments)


@pytest.mark.parametrize("step_id, module", [("s1", "monthly_surplus")])
def test_a_step_with_a_working_module_is_already_built(chat_, step_id, module):
    refused_with(chat_, ALREADY_BUILT.format(target=step_id, module=module), request_arguments("step", step_id))


@pytest.mark.parametrize("target, name", [("ghost", "ghost")])
def test_a_replace_request_needs_a_registered_module(chat_, target, name):
    arguments = {**request_arguments("replace"), "target": target}
    refused_with(chat_, NOT_REGISTERED.format(name=name), arguments)


# ---- the number check ----------------------------------------------------------------------------

def test_numbers_that_nothing_gave_are_refused_and_not_shown(chat_, conn):
    arguments = request_arguments("new", works_out="the cost with an extra 4321", why="you pay 8,765.50 more")
    model, person = chat_([call(arguments), SORRY])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == INPUTS_UNBACKED.format(numbers="4321, 8,765.50")
    assert events(conn, "ask.correction") == [("ask.correction", "harness", {
        "reason": "request_module", "numbers": ["4321", "8,765.50"], "text": json.dumps(arguments)})]
    assert events(conn, "ask.request_refused") == [] and events(conn, "ask.module_requested") == []
    assert person.asked == [SORRY["text"]] and person.told == ["  (thinking)"] * 2


# ---- MAX_REQUESTS ------------------------------------------------------------------------------

def test_a_declined_request_counts_towards_the_limit(chat_, conn):
    model, person = chat_([tools(*[("request_module", request_arguments("new"))] * 3), SORRY], ["no", "no", "/quit"])
    contents = [m["content"] for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert [json.loads(c)["outcome"] for c in contents[:2]] == ["declined", "declined"]
    assert contents[2] == TOO_MANY_REQUESTS
    assert len(events(conn, "ask.module_requested")) == 2


