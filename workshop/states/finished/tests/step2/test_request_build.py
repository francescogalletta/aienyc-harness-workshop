"""SPEC 5.9: a request the person accepts builds one step, inside the conversation, with the builder of 5.7."""
import json

import pytest

import step2_helpers as h
from harness.model import ScriptExhausted
from step2_helpers import (NEW_BLOCK, NEW_TEXTS, QUESTION, REASON_SKIPPED, REASON_STOPPED, REPLACE_BLOCK, REQUEST_QUESTION,
                           SESSION, STEP_BLOCK, YEARLY_QUESTION, agent_calls, events, kinds, payloads, propose_examples,
                           propose_spec, request_module, reuse_module, rows, run_module, say_text,
                           saved_spec, sections, surplus_script, tool_message, tools, user_messages, write_module,
                           yearly_script)

ACCEPT3 = ["/accept"] * 3
PLAN = ("To work this out: surplus = income - spending\nI will need from you:\n"
        "  - income (a number): Money in each month.\n  - spending (a number): Money out each month.\n"
        "It gives back: The surplus per month.")
EXAMPLES = [
    "Example 1 of 3\n  income: 5123.45\n  spending: 3100.10\n  Working: 5123.45 less 3100.10 leaves 2023.35\n"
    "  Proposed answer: 2023.35",
    "Example 2 of 3\n  income: 4000\n  spending: 4500\n  Working: 4000 less 4500 is a shortfall of 500\n"
    "  Proposed answer: -500",
    "Example 3 of 3\n  income: 3000\n  spending: 3000\n  Working: 3000 less 3000 leaves 0\n  Proposed answer: 0"]
THINKING = [("say", "  (thinking)"), ("call", "analyst")]
BUILD_EVENTS = ["calc.spec_proposed", "calc.plan_decision", "calc.examples_proposed", "calc.golden_decision",
                "calc.golden_decision", "calc.golden_decision", "calc.code_written", "calc.tests_run",
                "calc.module_registered"]
COSTS = [{"name": "rent", "amount": "1000"}, {"name": "food", "amount": "500"}]
COSTS_QUESTION = "I earn 5000 and pay rent 1000 and food 500 a month. What is left?"


def result_of(model, call_index):
    return json.loads(tool_message(model, call_index)["content"])


def request_events(conn):
    """The kinds recorded from the request to its outcome."""
    names = kinds(conn)
    return names[names.index("ask.module_requested"):names.index("ask.module_outcome") + 1]


# ---- case step ---------------------------------------------------------------------------------

STEP_SCRIPT = [request_module("step", "s1"), *surplus_script(), run_module(), say_text("monthly_surplus gives 2,000.")]
STEP_ANSWERS = ["yes", "yes", *ACCEPT3, "/quit"]


def test_a_step_with_no_module_is_built_in_the_conversation_and_then_run(months_only, chat, conn, registry):
    model, person = chat(STEP_SCRIPT, STEP_ANSWERS)
    assert model.roles() == ["analyst", "spec_writer", "example_writer", "module_writer", "analyst", "analyst"]
    assert registry.step_map(conn) == {"s1": "monthly_surplus", "s3": "months_to_goal"}
    [run] = rows(conn, "calc_runs")
    assert run["module"] == "monthly_surplus" and run["session_id"] == SESSION
    assert person.asked[-1] == "monthly_surplus gives 2,000."
    assert result_of(model, 4) == {"outcome": "built", "step": "s1", "module": "monthly_surplus",
                                   "spec": saved_spec(h.surplus_spec(), "s1")}
    assert not tool_message(model, 4).get("is_error")


# ---- case new ----------------------------------------------------------------------------------

NEW_SCRIPT = [request_module("new"), *yearly_script(),
              run_module("yearly_cost", {"monthly": "250"}, expected="about 3,000"),
              say_text("Over a year it comes to 3,000.")]


def test_a_new_need_adds_a_step_and_builds_it_and_the_agent_runs_the_module_at_once(both, chat, conn, registry):
    model, person = chat(NEW_SCRIPT, STEP_ANSWERS, question=YEARLY_QUESTION)
    assert model.roles() == ["analyst", "spec_writer", "example_writer", "module_writer", "analyst", "analyst"]
    [step] = rows(conn, "added_steps")
    assert (step["id"], step["session_id"], step["name"], step["formula"], step["needs"], step["produces"],
            step["reason"]) == (1, SESSION, NEW_TEXTS["works_out"], NEW_TEXTS["formula"], NEW_TEXTS["from_what"],
                                NEW_TEXTS["gives"], NEW_TEXTS["why"])
    assert registry.step_map(conn)["added_1"] == "yearly_cost"
    assert result_of(model, 4) == {"outcome": "built", "step": "added_1", "module": "yearly_cost",
                                   "spec": saved_spec(h.yearly_spec(), "added_1")}
    [run] = rows(conn, "calc_runs")
    assert (run["module"], json.loads(run["output"])) == ("yearly_cost", "3000")
    assert person.asked[-1] == "Over a year it comes to 3,000."


# ---- case replace ------------------------------------------------------------------------------

REPLACE_SCRIPT = [
    request_module("replace"), propose_spec(h.revised_spec()), propose_examples(h.revised_examples()),
    write_module(h.REVISED_PY, h.REVISED_TESTS),
    run_module("monthly_surplus", {"income": "5000", "costs": COSTS}, expected="about 3,500"),
    say_text("Left each month: 3,500.")]


def test_a_replace_request_keeps_the_block_as_a_note_and_rebuilds_the_module(both, chat, conn, registry, modules_dir):
    before = registry.get_module(conn, "monthly_surplus")
    model, person = chat(REPLACE_SCRIPT, STEP_ANSWERS, question=COSTS_QUESTION)
    assert model.roles() == ["analyst", "spec_writer", "example_writer", "module_writer", "analyst", "analyst"]
    assert [(r["step_id"], r["session_id"], r["text"]) for r in rows(conn, "notes")] == [("s1", SESSION, REPLACE_BLOCK)]
    after = registry.get_module(conn, "monthly_surplus")
    assert after["fingerprint"] != before["fingerprint"] and after["steps"] == ["s1"]
    assert (modules_dir / "monthly_surplus" / "module.py").read_text(encoding="utf-8") == h.REVISED_PY
    assert result_of(model, 4) == {"outcome": "built", "step": "s1", "module": "monthly_surplus",
                                   "spec": saved_spec(h.revised_spec(), "s1")}
    assert json.loads(rows(conn, "calc_runs")[0]["output"]) == "3500" and person.asked[-1] == "Left each month: 3,500."


# ---- a build that does not end in a module -------------------------------------------------------

NOT_BUILT = [
    pytest.param("step", "s1", "months_only", propose_spec(), "s1", id="step"),
]


@pytest.mark.parametrize("case, target, fixture, spec_call, step_id", NOT_BUILT)
@pytest.mark.parametrize("typed, reason", [("/quit", REASON_STOPPED)])
def test_a_build_that_does_not_finish_is_an_outcome_and_the_conversation_goes_on(
        request, chat, conn, case, target, fixture, spec_call, step_id, typed, reason):
    request.getfixturevalue(fixture)
    model, person = chat([request_module(case, target), spec_call, say_text("Understood.")], ["yes", typed, "/quit"])
    assert result_of(model, 2) == {"outcome": "not_built", "step": step_id, "reason": reason}
    assert not tool_message(model, 2).get("is_error")
    assert person.asked == [REQUEST_QUESTION, h.PLAN_QUESTION, "Understood."]
    assert payloads(conn, "calc.step_not_built") == [{"step": step_id, "reason": reason}]
    assert payloads(conn, "ask.module_outcome") == [{"outcome": "not_built", "step": step_id, "reason": reason}]


# ---- the limits of a turn --------------------------------------------------------------------------

def test_the_model_calls_of_a_build_do_not_count_towards_max_calls(both, chat, conn):
    script = [request_module("new"), *yearly_script(), *[say_text("")] * 9]
    model, person = chat(script, ["yes", "yes", *ACCEPT3, "/quit"], question=YEARLY_QUESTION)
    assert len(agent_calls(model)) == 10 and len(model.calls) == 13
    assert person.asked[-1] == h.TOO_MANY
    assert events(conn, "ask.stopped") == [("ask.stopped", "harness", {"reason": "too many steps"})]


