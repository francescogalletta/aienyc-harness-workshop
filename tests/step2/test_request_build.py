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


def test_everything_shown_and_asked_in_order(months_only, chat):
    _, person = chat(STEP_SCRIPT, STEP_ANSWERS)
    assert person.log == [
        *THINKING, ("say", STEP_BLOCK), ("ask", REQUEST_QUESTION),
        ("say", "Step s1: Work out the monthly surplus"),
        ("say", h.WRITING_SPEC.format(attempt=1)), ("call", "spec_writer"), ("say", PLAN), ("ask", h.PLAN_QUESTION),
        ("say", h.WRITING_EXAMPLES.format(attempt=1)), ("call", "example_writer"), ("say", h.EXAMPLES_INTRO),
        ("say", EXAMPLES[0]), ("ask", h.CONFIRM_EXAMPLE), ("say", EXAMPLES[1]), ("ask", h.CONFIRM_EXAMPLE),
        ("say", EXAMPLES[2]), ("ask", h.CONFIRM_EXAMPLE),
        ("say", h.WRITING_CODE.format(attempt=1)), ("call", "module_writer"), ("say", h.RUNNING_TESTS),
        *THINKING, ("say", "  (running monthly_surplus)"), *THINKING, ("ask", "monthly_surplus gives 2,000.")]


def test_the_answers_in_the_build_are_not_messages_of_the_conversation(months_only, chat, conn):
    model, _ = chat(STEP_SCRIPT, STEP_ANSWERS)
    assert payloads(conn, "ask.message") == [{"text": QUESTION}]
    assert user_messages(model, 5) == [QUESTION]
    assert [m["role"] for m in model.calls[5]["messages"]] == ["user", "assistant", "tool", "assistant", "tool"]


def test_the_events_of_a_request_for_a_step(months_only, chat, conn):
    chat(STEP_SCRIPT, STEP_ANSWERS)
    assert request_events(conn) == ["ask.module_requested", "ask.module_decision", *BUILD_EVENTS, "ask.module_outcome"]
    assert payloads(conn, "ask.module_decision") == [{"decision": "accepted", "text": "yes"}]
    [(_, actor, outcome)] = events(conn, "ask.module_outcome")
    assert actor == "harness" and outcome == {"outcome": "built", "step": "s1", "module": "monthly_surplus",
                                              "spec": saved_spec(h.surplus_spec(), "s1")}


def test_every_event_of_the_request_carries_the_session_id(months_only, chat, conn):
    chat(STEP_SCRIPT, STEP_ANSWERS)
    assert {r["session_id"] for r in conn.execute("SELECT session_id FROM events")} == {SESSION}


def test_a_step_whose_module_changed_is_rebuilt_without_reuse(both, chat, conn, modules_dir):
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    script = [request_module("step", "s1"), *surplus_script(), say_text("Done.")]
    model, _ = chat(script, ["yes", "yes", *ACCEPT3, "/quit"])
    spec_call = model.calls[1]
    assert [t.name for t in spec_call["tools"]] == ["propose_spec"]
    assert spec_call["messages"][0]["content"].endswith("[current spec]\n" + json.dumps(
        saved_spec(h.surplus_spec(), "s1"), indent=2, ensure_ascii=False))
    assert result_of(model, 4)["outcome"] == "built"
    assert h.expected_fingerprint(modules_dir / "monthly_surplus") == rows(conn, "modules")[0]["fingerprint"]


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


def test_the_header_of_the_build_marks_the_step_as_not_in_the_brief(both, chat):
    _, person = chat(NEW_SCRIPT, STEP_ANSWERS, question=YEARLY_QUESTION)
    assert ("say", "Step added_1 (not in the brief): the cost over a whole year") in person.log
    assert person.log.index(("say", NEW_BLOCK)) < person.log.index(
        ("say", "Step added_1 (not in the brief): the cost over a whole year"))


def test_the_spec_writer_gets_the_added_step_with_its_reason(both, chat, conn, brief):
    model, _ = chat(NEW_SCRIPT, STEP_ANSWERS, question=YEARLY_QUESTION)
    step = h.added_step(1)
    assert model.calls[1]["messages"][0]["content"] == sections(
        ("step", step), ("brief", brief),
        ("registered modules", [saved_spec(h.surplus_spec(), "s1"), saved_spec(h.months_spec(), "s3")]),
        ("notes", []))


def test_the_events_of_a_new_request(both, chat, conn):
    chat(NEW_SCRIPT, STEP_ANSWERS, question=YEARLY_QUESTION)
    assert request_events(conn) == ["ask.module_requested", "ask.module_decision", "calc.step_added", *BUILD_EVENTS,
                                    "ask.module_outcome"]
    [(_, actor, payload)] = events(conn, "calc.step_added")
    assert actor == "harness" and payload == {"step": h.added_step(1)}


def test_the_context_of_the_session_is_not_remade_but_the_next_sessions_has_the_step_and_the_module(both, chat, conn):
    model, _ = chat(NEW_SCRIPT, STEP_ANSWERS, question=YEARLY_QUESTION)
    assert len({call["system"] for call in agent_calls(model)}) == 1
    assert "yearly_cost" not in model.calls[0]["system"] and "added_1" not in model.calls[0]["system"]

    model, _ = chat([say_text("Hello again.")], question="Hi", session_id="next-session")
    brief = h.make_brief()
    context = sections(
        ("today", "2026-03-14"), ("goal", brief["goal"]), ("particulars", brief["particulars"]),
        ("process", brief["process"]), ("added steps (not in the brief)", [h.added_step(1)]),
        ("modules", {"monthly_surplus": {"steps": ["s1"], "spec": saved_spec(h.surplus_spec(), "s1")},
                     "months_to_goal": {"steps": ["s3"], "spec": saved_spec(h.months_spec(), "s3")},
                     "yearly_cost": {"steps": ["added_1"], "spec": saved_spec(h.yearly_spec(), "added_1")}}),
        ("saved inputs", {}), ("notes", []))
    assert model.calls[0]["system"].strip() == h.prompt_text("analyst.md").replace("{context}", context).strip()


def test_the_added_steps_in_the_context_are_those_of_every_session(both, chat, conn):
    h.add_new_step(conn, session_id="earlier", name="first one")
    h.add_new_step(conn, session_id="earlier too", name="second one")
    model, _ = chat([say_text("Hello.")])
    section = model.calls[0]["system"].split("[added steps (not in the brief)]\n")[1].split("\n\n[modules]")[0]
    assert [s["name"] for s in json.loads(section)] == ["first one", "second one"]


def test_the_step_stays_when_the_build_does_not_end_in_a_module_and_can_be_requested_later(both, chat, conn, registry):
    model, _ = chat([request_module("new"), propose_spec(h.yearly_spec()), say_text("Not now.")], ["yes", "/quit", "/quit"])
    assert result_of(model, 2) == {"outcome": "not_built", "step": "added_1", "reason": REASON_STOPPED}
    assert [r["id"] for r in rows(conn, "added_steps")] == [1] and registry.step_map(conn).get("added_1") is None

    script = [request_module("step", "added_1", **NEW_TEXTS), *yearly_script(), say_text("Built.")]
    model, person = chat(script, ["yes", "yes", *ACCEPT3, "/quit"], session_id="later")
    first = h.REQUEST_STEP.format(step="added_1 (not in the brief)", name=NEW_TEXTS["works_out"])
    assert person.told[1] == h.request_block(first, NEW_TEXTS)
    assert result_of(model, 4)["step"] == "added_1" and registry.step_map(conn)["added_1"] == "yearly_cost"
    assert len(rows(conn, "added_steps")) == 1


def test_a_new_request_may_end_in_a_reused_module(both, chat, conn, registry):
    model, person = chat([request_module("new"), reuse_module("monthly_surplus"), say_text("Reused.")], ["yes", "/quit"])
    assert model.roles() == ["analyst", "spec_writer", "analyst"] and person.asked == [REQUEST_QUESTION, "Reused."]
    assert result_of(model, 2) == {"outcome": "reused", "step": "added_1", "module": "monthly_surplus",
                                   "spec": saved_spec(h.surplus_spec(), "s1")}
    assert registry.step_map(conn)["added_1"] == "monthly_surplus"
    assert payloads(conn, "calc.module_reused")[0]["step"] == "added_1"
    assert request_events(conn) == ["ask.module_requested", "ask.module_decision", "calc.step_added",
                                    "calc.module_reused", "ask.module_outcome"]


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


def test_the_spec_writer_of_a_replacement_sees_the_note_and_the_current_spec_and_is_not_offered_reuse(both, chat, brief):
    model, _ = chat(REPLACE_SCRIPT, STEP_ANSWERS, question=COSTS_QUESTION)
    assert [t.name for t in model.calls[1]["tools"]] == ["propose_spec"]
    assert model.calls[1]["messages"][0]["content"] == sections(
        ("step", brief["process"][0]), ("brief", brief), ("registered modules", [saved_spec(h.months_spec(), "s3")]),
        ("notes", [{"step": "s1", "text": REPLACE_BLOCK}]), ("current spec", saved_spec(h.surplus_spec(), "s1")))


def test_the_events_of_a_replace_request(both, chat, conn):
    chat(REPLACE_SCRIPT, STEP_ANSWERS, question=COSTS_QUESTION)
    assert request_events(conn) == ["ask.module_requested", "ask.module_decision", "calc.note_saved", *BUILD_EVENTS,
                                    "ask.module_outcome"]
    assert events(conn, "calc.note_saved") == [("calc.note_saved", "person", {"id": 1, "step": "s1", "text": REPLACE_BLOCK})]


def test_a_failed_replacement_leaves_the_module_as_it_was_and_the_note_stays(both, chat, conn, registry, modules_dir):
    files, module = h.snapshot(modules_dir / "monthly_surplus"), registry.get_module(conn, "monthly_surplus")
    model, _ = chat([request_module("replace"), propose_spec(h.revised_spec()), say_text("Left as it was.")],
                    ["yes", "/skip", "/quit"])
    assert result_of(model, 2) == {"outcome": "not_built", "step": "s1", "reason": REASON_SKIPPED}
    assert h.snapshot(modules_dir / "monthly_surplus") == files and registry.get_module(conn, "monthly_surplus") == module
    assert [r["text"] for r in rows(conn, "notes")] == [REPLACE_BLOCK]


# ---- a build that does not end in a module -------------------------------------------------------

NOT_BUILT = [
    pytest.param("step", "s1", "months_only", propose_spec(), "s1", id="step"),
    pytest.param("new", None, "both", propose_spec(h.yearly_spec()), "added_1", id="new"),
    pytest.param("replace", "monthly_surplus", "both", propose_spec(), "s1", id="replace"),
]


@pytest.mark.parametrize("case, target, fixture, spec_call, step_id", NOT_BUILT)
@pytest.mark.parametrize("typed, reason", [("/quit", REASON_STOPPED), ("/skip", REASON_SKIPPED)])
def test_a_build_that_does_not_finish_is_an_outcome_and_the_conversation_goes_on(
        request, chat, conn, case, target, fixture, spec_call, step_id, typed, reason):
    request.getfixturevalue(fixture)
    model, person = chat([request_module(case, target), spec_call, say_text("Understood.")], ["yes", typed, "/quit"])
    assert result_of(model, 2) == {"outcome": "not_built", "step": step_id, "reason": reason}
    assert not tool_message(model, 2).get("is_error")
    assert person.asked == [REQUEST_QUESTION, h.PLAN_QUESTION, "Understood."]
    assert payloads(conn, "calc.step_not_built") == [{"step": step_id, "reason": reason}]
    assert payloads(conn, "ask.module_outcome") == [{"outcome": "not_built", "step": step_id, "reason": reason}]


def test_the_json_of_each_result_lists_its_keys_in_the_order_of_the_spec(both, chat):
    model, _ = chat([request_module("new"), reuse_module("monthly_surplus"), request_module("new"),
                     say_text("Done.")], ["yes", "no", "/quit"])
    contents = [m["content"] for m in model.calls[-1]["messages"] if m["role"] == "tool"]
    spec = saved_spec(h.surplus_spec(), "s1")
    assert contents[0] == json.dumps({"outcome": "reused", "step": "added_1", "module": "monthly_surplus", "spec": spec})
    assert contents[1] == json.dumps({"outcome": "declined", "said": "no"})


def test_the_json_of_a_not_built_result_lists_its_keys_in_the_order_of_the_spec(months_only, chat):
    model, _ = chat([request_module("step", "s1"), propose_spec(), say_text("Done.")], ["yes", "/quit", "/quit"])
    assert tool_message(model, 2)["content"] == json.dumps({"outcome": "not_built", "step": "s1", "reason": REASON_STOPPED})


def test_the_json_of_a_built_result_lists_its_keys_in_the_order_of_the_spec(months_only, chat):
    model, _ = chat(STEP_SCRIPT, STEP_ANSWERS)
    assert tool_message(model, 4)["content"] == json.dumps({
        "outcome": "built", "step": "s1", "module": "monthly_surplus", "spec": saved_spec(h.surplus_spec(), "s1")})


# ---- the limits of a turn --------------------------------------------------------------------------

def test_the_model_calls_of_a_build_do_not_count_towards_max_calls(both, chat, conn):
    script = [request_module("new"), *yearly_script(), *[say_text("")] * 9]
    model, person = chat(script, ["yes", "yes", *ACCEPT3, "/quit"], question=YEARLY_QUESTION)
    assert len(agent_calls(model)) == 10 and len(model.calls) == 13
    assert person.asked[-1] == h.TOO_MANY
    assert events(conn, "ask.stopped") == [("ask.stopped", "harness", {"reason": "too many steps"})]


def test_a_model_call_of_the_build_that_raises_leaves_run_agent(both, chat, registry, conn):
    with pytest.raises(ScriptExhausted):
        chat([request_module("new"), propose_spec(h.yearly_spec())], ["yes", "yes"])
    assert [m["name"] for m in registry.list_modules(conn)] == ["monthly_surplus", "months_to_goal"]


def test_a_build_runs_before_the_next_call_of_the_same_reply_is_handled(both, chat, conn):
    reply = tools(("request_module", h.request_arguments("new")), ("save_input", {
        "name": "monthly_income", "value": "5000", "note": "said by the person"}))
    model, _ = chat([reply, *yearly_script(), say_text("Both done.")], ["yes", "yes", *ACCEPT3, "/quit"])
    assert model.roles() == ["analyst", "spec_writer", "example_writer", "module_writer", "analyst"]
    names = kinds(conn)
    assert names.index("ask.module_outcome") < names.index("ask.input_saved")
    results = [m for m in model.calls[-1]["messages"] if m["role"] == "tool"]
    assert [json.loads(results[0]["content"])["outcome"], results[1]["content"]] == ["built", h.SAVED]


def test_a_note_kept_during_the_build_backs_the_next_reply_at_once(months_only, chat, conn):
    script = [request_module("step", "s1"), propose_spec(), propose_spec(h.revised_spec()),
              propose_examples(h.revised_examples()), write_module(h.REVISED_PY, h.REVISED_TESTS),
              say_text("You have 6,543 in costs.")]
    answers = ["yes", "I have 6543 in costs", "yes", *ACCEPT3, "/quit"]
    model, person = chat(script, answers)
    assert [r["text"] for r in rows(conn, "notes")] == ["I have 6543 in costs"]
    assert person.asked[-1] == "You have 6,543 in costs." and events(conn, "ask.correction") == []
    assert payloads(conn, "ask.message") == [{"text": QUESTION}]
