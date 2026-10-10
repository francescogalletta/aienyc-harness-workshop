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

@pytest.mark.parametrize("name", [
    "REQUEST_STEP", "REQUEST_NEW", "REQUEST_REPLACE", "REQUEST_QUESTION", "TOO_MANY_REQUESTS", "BAD_CASE",
    "MISSING_WORDS", "NOT_A_STEP", "ALREADY_BUILT", "ACCEPT_WORDS", "NO_STEP", "NOT_REGISTERED"])
def test_the_fixed_strings(agent, name):
    assert getattr(agent, name) == getattr(h, name)


def test_the_limit(agent):
    assert agent.MAX_REQUESTS == MAX_REQUESTS == 2


def test_the_schema_is_the_one_of_the_spec(agent):
    assert h.without_descriptions(agent.REQUEST_MODULE_SCHEMA) == h.REQUEST_MODULE_SCHEMA


def test_the_tool_is_offered_last_with_that_schema(ask_agent):
    model, _ = ask_agent([say_text("Hello.")])
    names = [t.name for t in model.calls[0]["tools"]]
    assert names[-1] == "request_module"
    assert h.without_descriptions(model.calls[0]["tools"][-1].input_schema) == h.REQUEST_MODULE_SCHEMA


# ---- each check, in the stated order ---------------------------------------------------------

def test_too_many_requests_comes_first_even_when_the_third_call_is_otherwise_wrong(chat_):
    third = request_arguments("bogus")
    script = [tools(("request_module", request_arguments("new")), ("request_module", request_arguments("new")),
                    ("request_module", third)), SORRY]
    model, person = chat_(script, ["no", "no", "/quit"])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == TOO_MANY_REQUESTS
    assert events(chat_.conn, "ask.request_refused") == [("ask.request_refused", "harness", {
        "error": TOO_MANY_REQUESTS, "arguments": third})]
    assert person.asked == [h.REQUEST_QUESTION, h.REQUEST_QUESTION, SORRY["text"]]


@pytest.mark.parametrize("case", ["", "bogus", "Step", "STEP", 5, None])
def test_a_case_that_is_not_step_new_or_replace(chat_, case):
    arguments = {**request_arguments("step"), "case": case}
    refused_with(chat_, BAD_CASE, arguments)


def test_a_missing_case(chat_):
    refused_with(chat_, BAD_CASE, without(request_arguments("step"), "case"))


def test_the_case_is_checked_before_the_words(chat_):
    refused_with(chat_, BAD_CASE, request_arguments("bogus", why=""))


@pytest.mark.parametrize("changes, fields", [
    ({"why": ""}, "why"),
    ({"works_out": "   ", "why": ""}, "works_out, why"),
    ({"gives": "\n\t"}, "gives"),
    ({"from_what": 5, "formula": ["x"]}, "from_what, formula"),
    ({"formula": None, "from_what": None}, "from_what, formula"),
    ({"works_out": None, "from_what": None, "gives": None, "formula": None, "why": None},
     "works_out, from_what, gives, formula, why"),
])
def test_each_text_must_be_words_and_the_fields_are_named_in_schema_order(chat_, changes, fields):
    arguments = request_arguments("step")
    for key, value in changes.items():
        if value is None:
            arguments.pop(key)
        else:
            arguments[key] = value
    refused_with(chat_, MISSING_WORDS.format(fields=fields), arguments)


def test_the_words_are_checked_before_the_step(chat_):
    refused_with(chat_, MISSING_WORDS.format(fields="why"), request_arguments("step", target="ghost", why=""))


@pytest.mark.parametrize("target, shown", [
    ("ghost", "ghost"), ("s2", "s2"), ("monthly_surplus", "monthly_surplus"), ("added_1", "added_1"), ("", ""),
    (5, ""), (None, "")])
def test_a_step_request_needs_a_calculation_step_of_the_process(chat_, target, shown):
    arguments = {**request_arguments("step"), "target": target}
    if target is None:
        del arguments["target"]
    refused_with(chat_, NOT_A_STEP.format(target=shown), arguments)


@pytest.mark.parametrize("step_id, module", [("s1", "monthly_surplus"), ("s3", "months_to_goal")])
def test_a_step_with_a_working_module_is_already_built(chat_, step_id, module):
    refused_with(chat_, ALREADY_BUILT.format(target=step_id, module=module), request_arguments("step", step_id))


@pytest.mark.parametrize("damage", ["edit", "delete"])
def test_a_step_whose_module_has_changed_or_missing_files_may_be_requested(chat_, conn, modules_dir, damage):
    folder = modules_dir / "monthly_surplus"
    if damage == "edit":
        (folder / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    else:
        (folder / "tests.py").unlink()
    model, person = chat_([request_module("step", "s1"), SORRY], ["no", "/quit"])
    assert person.asked[0] == h.REQUEST_QUESTION and events(conn, "ask.request_refused") == []


def test_an_added_step_without_a_module_may_be_requested(chat_, conn):
    step = h.add_new_step(conn)
    model, person = chat_([request_module("step", "added_1", **h.NEW_TEXTS), SORRY], ["no", "/quit"])
    assert person.asked[0] == h.REQUEST_QUESTION and events(conn, "ask.correction") == []
    assert any(t.startswith(h.REQUEST_STEP.format(step="added_1 (not in the brief)", name=step["name"]))
               for t in person.told)


@pytest.mark.parametrize("target, name", [("ghost", "ghost"), ("", ""), (5, "")])
def test_a_replace_request_needs_a_registered_module(chat_, target, name):
    arguments = {**request_arguments("replace"), "target": target}
    refused_with(chat_, NOT_REGISTERED.format(name=name), arguments)


def test_a_replace_request_without_a_target(chat_):
    refused_with(chat_, NOT_REGISTERED.format(name=""), without(request_arguments("replace"), "target"))


def test_a_replace_request_needs_the_modules_step_to_be_in_the_process(chat_, conn):
    h.install_yearly(conn, "added_9")
    refused_with(chat_, NO_STEP.format(step="added_9", name="yearly_cost"), request_arguments("replace", "yearly_cost"))


def test_a_module_built_for_an_added_step_may_be_replaced(chat_, conn):
    h.add_new_step(conn)
    h.install_yearly(conn)
    model, person = chat_([request_module("replace", "yearly_cost"), SORRY], ["no", "/quit"])
    assert person.asked[0] == h.REQUEST_QUESTION and events(conn, "ask.request_refused") == []


def test_a_module_with_changed_files_may_be_replaced(chat_, conn, modules_dir):
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    model, person = chat_([request_module("replace"), SORRY], ["no", "/quit"])
    assert person.asked[0] == h.REQUEST_QUESTION


def test_the_registered_check_comes_before_the_number_check(chat_):
    refused_with(chat_, NOT_REGISTERED.format(name="ghost"), request_arguments("replace", "ghost", why="you pay 4321"))


def test_a_target_of_a_new_request_is_ignored(chat_, conn):
    model, person = chat_([request_module("new", "ghost 9999"), SORRY], ["no", "/quit"])
    assert person.asked[0] == h.REQUEST_QUESTION and events(conn, "ask.request_refused") == []
    assert payloads(conn, "ask.module_requested")[0]["arguments"]["target"] == "ghost 9999"


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


@pytest.mark.parametrize("where", ["works_out", "from_what", "gives", "formula", "why"])
def test_every_one_of_the_five_texts_is_read(chat_, conn, where):
    arguments = request_arguments("new", **{where: "something worth 4321"})
    model, _ = chat_([call(arguments), SORRY])
    assert tool_message(model, 1)["content"] == INPUTS_UNBACKED.format(numbers="4321")


def test_a_number_from_the_persons_question_is_backed(chat_, conn):
    model, person = chat_([request_module("new", why="you earn 5000"), SORRY], ["no", "/quit"])
    assert events(conn, "ask.correction") == [] and person.asked[0] == h.REQUEST_QUESTION


def test_a_number_from_the_brief_is_backed(chat_, conn):
    model, person = chat_([request_module("new", formula="1,150 for the rent plus the rest"), SORRY], ["no", "/quit"])
    assert events(conn, "ask.correction") == [] and person.asked[0] == h.REQUEST_QUESTION


def test_a_number_the_person_gave_in_an_earlier_answer_to_a_request_is_backed(chat_, conn):
    script = [tools(("request_module", request_arguments("new")),
                    ("request_module", request_arguments("new", why="you pay 777 for the van"))), SORRY]
    model, person = chat_(script, ["no, I only pay 777 for the van", "no", "/quit"])
    assert events(chat_.conn, "ask.correction") == []
    assert person.asked == [h.REQUEST_QUESTION, h.REQUEST_QUESTION, SORRY["text"]]


def test_a_step_id_in_the_block_is_not_read_as_a_number(chat, months_only, conn):
    model, person = chat([request_module("step", "s1", gives="the surplus of s1"), SORRY], ["no", "/quit"])
    assert events(conn, "ask.correction") == [] and person.asked[0] == h.REQUEST_QUESTION


# ---- MAX_REQUESTS ------------------------------------------------------------------------------

def test_a_declined_request_counts_towards_the_limit(chat_, conn):
    model, person = chat_([tools(*[("request_module", request_arguments("new"))] * 3), SORRY], ["no", "no", "/quit"])
    contents = [m["content"] for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert [json.loads(c)["outcome"] for c in contents[:2]] == ["declined", "declined"]
    assert contents[2] == TOO_MANY_REQUESTS
    assert len(events(conn, "ask.module_requested")) == 2


def test_an_accepted_request_counts_too(chat_, conn):
    script = [tools(*[("request_module", request_arguments("new"))] * 3), *yearly_script(), SORRY]
    answers = ["yes", "yes", "/accept", "/accept", "/accept", "no", "/quit"]
    model, person = chat_(script, answers)
    contents = [m["content"] for m in model.calls[-1]["messages"] if m["role"] == "tool"]
    assert [json.loads(c)["outcome"] for c in contents[:2]] == ["built", "declined"]
    assert contents[2] == TOO_MANY_REQUESTS


def test_refused_requests_do_not_count(chat_, conn):
    script = [tools(("request_module", request_arguments("bogus")), ("request_module", request_arguments("step", "ghost")),
                    ("request_module", request_arguments("new", why="you pay 4321")),
                    ("request_module", request_arguments("new")), ("request_module", request_arguments("new"))), SORRY]
    model, person = chat_(script, ["no", "no", "/quit"])
    contents = [m["content"] for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert contents[:3] == [BAD_CASE, NOT_A_STEP.format(target="ghost"), INPUTS_UNBACKED.format(numbers="4321")]
    assert [json.loads(c)["outcome"] for c in contents[3:]] == ["declined", "declined"]


def test_the_count_starts_again_at_each_person_message(chat_, conn):
    script = [tools(*[("request_module", request_arguments("new"))] * 2), say_text("Nothing yet."),
              request_module("new"), say_text("Still nothing.")]
    model, person = chat_(script, ["no", "no", "Try again", "no", "/quit"])
    assert len(events(conn, "ask.module_requested")) == 3 and events(conn, "ask.request_refused") == []
    assert person.asked.count(h.REQUEST_QUESTION) == 3
