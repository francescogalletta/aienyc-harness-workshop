"""SPEC 5.7: the builder, from the brief to a registered module. The model is scripted, the person is a list of answers."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (DRAFT_BRIEF, NAME_TAKEN, NO_BRIEF, ONE_CALL, PLAN_QUESTION, REASON_SPEC, SPEC_REJECTED,
                           STEP_HEADER, USE_TOOL, built, events, make_brief, months_script, months_spec, only_step,
                           payloads, propose_examples, propose_spec, rows, say_text, saved_spec, sections,
                           surplus_examples, surplus_script, surplus_spec, tools, write_module)

S1 = {"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}
S3 = {"step": "s3", "outcome": "built", "module": "months_to_goal", "reason": ""}


def bullets(content, header):
    """The lines after a fixed first line, which must be `- ` bullets."""
    lines = [line for line in content.splitlines() if line.strip()]
    assert lines[0] == header
    assert lines[1:] and all(line.startswith("- ") for line in lines[1:]), lines
    return [line[2:] for line in lines[1:]]


def tool_messages(model, call_index):
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


# ---- the fixed strings and schemas -----------------------------------------------------------

FIXED_STRINGS = [
    "NO_BRIEF", "DRAFT_BRIEF", "STEP_HEADER", "WRITING_SPEC", "WRITING_EXAMPLES", "WRITING_CODE", "READING_REPLY",
    "USE_TOOL", "ONE_CALL", "SPEC_REJECTED", "NAME_TAKEN", "CANNOT_REUSE", "PLAN_QUESTION", "PLAN_FEEDBACK",
    "PLAN_KEPT", "EXAMPLES_REJECTED", "EXAMPLES_INTRO", "CONFIRM_EXAMPLE", "CONFIRM_ANSWER", "NOTE_KEPT",
    "NOT_UNDERSTOOD", "CODE_REJECTED", "RUNNING_TESTS", "TESTS_FAILED", "EXAMPLE_FAILED", "EXAMPLES_DISAGREE",
    "DISAGREEMENT", "REASON_SPEC", "REASON_SKIPPED", "REASON_EXAMPLES", "REASON_CONFIRMED", "REASON_CODE",
    "REASON_STOPPED", "ACCEPT_WORDS", "KIND_WORDS"]


@pytest.mark.parametrize("name", FIXED_STRINGS)
def test_the_fixed_strings(builder, name):
    assert getattr(builder, name) == getattr(h, name)


def test_not_a_value_is_gone(builder):
    assert not hasattr(builder, "NOT_A_VALUE")


def test_the_limits(builder):
    assert (builder.MAX_ATTEMPTS, builder.MIN_EXAMPLES, builder.MAX_PLAN_ROUNDS, builder.MIN_CONFIRMED) == (3, 3, 2, 2)


def test_min_confirmed_is_the_registrys(builder, registry):
    assert builder.MIN_CONFIRMED is registry.MIN_CONFIRMED


@pytest.mark.parametrize("name", ["SPEC_SCHEMA", "REUSE_SCHEMA", "EXAMPLES_SCHEMA", "RESPOND_SCHEMA", "CODE_SCHEMA"])
def test_the_tool_schemas(builder, name):
    assert h.without_descriptions(getattr(builder, name)) == getattr(h, name)


# ---- load_brief ------------------------------------------------------------------------------

def test_load_brief_returns_the_brief_without_meta(builder, tmp_path, save_confirmed_brief):
    save_confirmed_brief(make_brief())
    assert builder.load_brief(tmp_path / "brief") == make_brief()


def test_load_brief_without_a_file(builder, tmp_path):
    with pytest.raises(ValueError) as error:
        builder.load_brief(tmp_path / "brief")
    assert str(error.value) == NO_BRIEF


def test_load_brief_refuses_a_draft(builder, tmp_path, save_confirmed_brief):
    save_confirmed_brief(make_brief(), status="draft")
    with pytest.raises(ValueError) as error:
        builder.load_brief(tmp_path / "brief")
    assert str(error.value) == DRAFT_BRIEF


# ---- a step built at the first try -----------------------------------------------------------

def test_a_step_built_at_the_first_try_takes_exactly_three_model_calls(build):
    results, model, _ = build(surplus_script(), built(), brief=only_step("s1"))
    assert results == [S1]
    assert len(model.calls) == 3


def test_each_phase_is_a_conversation_of_its_own(build):
    _, model, _ = build(surplus_script(), built(), brief=only_step("s1"))
    spec_call, examples_call, code_call = model.calls
    for call, prompt, names, schemas in [
            (spec_call, "spec_writer.md", ["propose_spec", "reuse_module"], [h.SPEC_SCHEMA, h.REUSE_SCHEMA]),
            (examples_call, "example_writer.md", ["propose_examples"], [h.EXAMPLES_SCHEMA]),
            (code_call, "module_writer.md", ["write_module"], [h.CODE_SCHEMA])]:
        assert call["system"].strip() == h.prompt_text(prompt).strip()
        assert [t.name for t in call["tools"]] == names
        assert [h.without_descriptions(t.input_schema) for t in call["tools"]] == schemas
        assert [m["role"] for m in call["messages"]] == ["user"]


def test_the_user_messages_are_made_of_sections(build):
    brief = only_step("s1")
    _, model, _ = build(surplus_script(), built(), brief=brief)
    step = brief["process"][0]
    accepted = saved_spec(surplus_spec(), "s1")
    assert model.calls[0]["messages"][0]["content"] == sections(
        ("step", step), ("brief", brief), ("registered modules", []), ("notes", []))
    assert model.calls[1]["messages"][0]["content"] == sections(("spec", accepted), ("step", step))
    assert model.calls[2]["messages"][0]["content"] == sections(("spec", accepted))


def test_the_meta_of_a_brief_is_not_sent(build):
    brief = {**only_step("s1"), "meta": {"status": "confirmed", "written_at": "WRITTEN-AT-MARKER"}}
    _, model, _ = build(surplus_script(), built(), brief=brief)
    assert "WRITTEN-AT-MARKER" not in json.dumps(model.calls[0]["messages"])


def test_the_files_of_a_built_module(build, conn, modules_dir):
    build(surplus_script(), built(), brief=only_step("s1"))
    folder = modules_dir / "monthly_surplus"
    assert sorted(p.name for p in folder.iterdir() if p.is_file()) == ["golden.json", "module.py", "spec.json", "tests.py"]
    assert (folder / "module.py").read_text(encoding="utf-8") == h.SURPLUS_PY
    assert (folder / "tests.py").read_text(encoding="utf-8") == h.SURPLUS_TESTS
    assert (folder / "spec.json").read_text(encoding="utf-8") == h.dump(saved_spec(surplus_spec(), "s1"))
    assert (folder / "golden.json").read_text(encoding="utf-8") == h.dump(h.golden_of(surplus_examples()))
    assert not (modules_dir / "_build" / "monthly_surplus").exists()          # moved, not copied


def test_a_built_module_is_registered_on_the_run_that_passed(build, conn, registry, modules_dir):
    build(surplus_script(), built(), brief=only_step("s1"))
    module = registry.get_module(conn, "monthly_surplus")
    assert module["fingerprint"] == h.expected_fingerprint(modules_dir / "monthly_surplus")
    assert module["spec"] == saved_spec(surplus_spec(), "s1") and module["steps"] == ["s1"]
    [run] = rows(conn, "test_runs")
    assert run["id"] == module["test_run_id"] and run["reason"] == "build" and run["passed"] == 1
    assert run["fingerprint"] == module["fingerprint"]
    assert registry.step_map(conn) == {"s1": "monthly_surplus"}


def test_what_the_person_is_told(build):
    _, _, person = build(surplus_script(), built(), brief=only_step("s1"))
    told = person.told
    first = ("Example 1 of 3\n  income: 5123.45\n  spending: 3100.10\n"
             "  Working: 5123.45 less 3100.10 leaves 2023.35\n  Proposed answer: 2023.35")
    assert told[0] == STEP_HEADER.format(id="s1", name="Work out the monthly surplus")
    assert first in told
    second = next(t for t in told if t.startswith("Example 2 of 3\n"))
    third = next(t for t in told if t.startswith("Example 3 of 3\n"))
    marks = [h.EXAMPLES_INTRO, first, second, third, h.RUNNING_TESTS]
    order = [told.index(text) for text in marks]
    assert order == sorted(order)


def test_every_example_is_shown_and_then_asked_about(build):
    _, _, person = build(surplus_script(), built(), brief=only_step("s1"))
    shown = [i for i, (kind, text) in enumerate(person.log) if kind == "say" and text.startswith("Example ")]
    asks = [i for i, (kind, text) in enumerate(person.log) if kind == "ask" and text == h.CONFIRM_EXAMPLE]
    assert len(asks) == 3
    assert all(shown[k] < asks[k] < (shown[k + 1] if k < 2 else 10 ** 6) for k in range(3))


def test_values_are_shown_in_plain_words_and_not_as_json(build):
    spec = surplus_spec(name="schedule_total", inputs=[
        {"name": "payments", "type": "list", "description": "d"}, {"name": "paid", "type": "boolean", "description": "d"},
        {"name": "label", "type": "text", "description": "d"}, {"name": "count", "type": "integer", "description": "d"}],
        output={"type": "list", "description": "d"})
    examples = [{"inputs": {"payments": [{"date": "2026-01-01", "amount": "10"}], "paid": True, "label": "é\"x", "count": 3},
                 "expected": ["1", "2"], "working": "1, then 2"}] * 3
    _, _, person = build([propose_spec(spec), propose_examples(examples)], ["yes", "/quit"], brief=only_step("s1"))
    assert (
        'Example 1 of 3\n  payments:\n    1. date: 2026-01-01\n       amount: 10\n  paid: yes\n  label: é"x\n'
        '  count: 3\n  Working: 1, then 2\n  Proposed answer:\n    1. 1\n    2. 2') in person.told


def test_input_names_are_shown_with_spaces(build):
    spec = surplus_spec(name="two_words", inputs=[
        {"name": "income_per_month", "type": "number", "description": "d"},
        {"name": "other_spending", "type": "number", "description": "d"}])
    examples = [{"inputs": {"income_per_month": "5", "other_spending": "3"}, "expected": "2", "working": "5 - 3 = 2"}] * 3
    _, _, person = build([propose_spec(spec), propose_examples(examples)], ["yes", "/quit"], brief=only_step("s1"))
    assert "Example 1 of 3\n  income per month: 5\n  other spending: 3\n  Working: 5 - 3 = 2\n  Proposed answer: 2" in person.told


def test_the_plan_is_shown_in_plain_words_and_then_asked_about(build):
    _, _, person = build(surplus_script(), built(), brief=only_step("s1"))
    plan = ("To work this out: surplus = income - spending\nI will need from you:\n"
            "  - income (a number): Money in each month.\n  - spending (a number): Money out each month.\n"
            "It gives back: The surplus per month.")
    told_at = person.log.index(("say", plan))
    assert person.log[told_at + 1] == ("ask", PLAN_QUESTION)


# ---- the events of a build -------------------------------------------------------------------

def test_the_events_of_a_build_in_order(build, conn):
    build(surplus_script(), built(), brief=only_step("s1"))
    assert h.kinds(conn, "calc.") == ["calc.spec_proposed", "calc.plan_decision", "calc.examples_proposed",
                                      "calc.golden_decision", "calc.golden_decision", "calc.golden_decision",
                                      "calc.code_written", "calc.tests_run", "calc.module_registered"]


def test_the_actors_and_payloads_of_a_build(build, conn, modules_dir):
    build(surplus_script(), built(), brief=only_step("s1"))
    by_kind = {kind: (actor, payload) for kind, actor, payload in events(conn) if kind != "calc.golden_decision"}
    assert by_kind["calc.plan_decision"] == ("person", {"step": "s1", "round": 1, "decision": "accepted", "text": "yes"})
    fingerprint = h.expected_fingerprint(modules_dir / "monthly_surplus")
    assert by_kind["calc.spec_proposed"] == ("agent", {"step": "s1", "spec": saved_spec(surplus_spec(), "s1")})
    assert by_kind["calc.examples_proposed"] == ("agent", {"module": "monthly_surplus", "examples": surplus_examples()})
    assert by_kind["calc.code_written"] == ("agent", {"module": "monthly_surplus", "attempt": 1,
                                                      "module_py": h.SURPLUS_PY, "tests_py": h.SURPLUS_TESTS})
    run_id = rows(conn, "test_runs")[0]["id"]
    assert by_kind["calc.tests_run"] == ("harness", {"module": "monthly_surplus", "test_run_id": run_id,
                                                     "reason": "build", "passed": True, "fingerprint": fingerprint})
    assert by_kind["calc.module_registered"] == ("harness", {"module": "monthly_surplus", "step": "s1",
                                                             "fingerprint": fingerprint, "test_run_id": run_id})


def test_every_event_carries_the_session_id(build, conn):
    build(surplus_script(), built(), brief=only_step("s1"))
    assert {r["session_id"] for r in conn.execute("SELECT session_id FROM events")} == {h.SESSION}


# ---- which steps -----------------------------------------------------------------------------

def test_calculation_steps_are_built_in_brief_order_and_other_steps_are_left_alone(build, conn):
    results, model, person = build(surplus_script() + months_script(), built(2))
    assert results == [S1, S3]
    assert len(model.calls) == 6
    assert [t for t in person.told if t.startswith("Step ")] == [
        "Step s1: Work out the monthly surplus", "Step s3: Work out the months to reach the target"]


def test_a_brief_with_no_calculation_step_does_nothing(build):
    brief = make_brief(process=[make_brief()["process"][1]])
    results, model, person = build([], brief=brief)
    assert results == [] and model.calls == [] and person.log == []


# ---- phase 1: the spec -----------------------------------------------------------------------

@pytest.mark.parametrize("phase, tool_names", [
    (0, "propose_spec or reuse_module"), (1, "propose_examples"), (2, "write_module")])
def test_a_reply_without_a_tool_call_is_sent_back_and_counts_as_an_attempt(build, phase, tool_names):
    script = surplus_script()
    script.insert(phase, say_text("I think this is fine."))
    results, model, _ = build(script, built(), brief=only_step("s1"))
    retry = model.calls[phase + 1]["messages"]
    assert retry[-2]["role"] == "assistant" and retry[-2]["content"] == "I think this is fine."
    assert retry[-1] == {"role": "user", "content": USE_TOOL.format(tools=tool_names)}
    assert results == [S1] and len(model.calls) == 4


def test_only_the_first_tool_call_of_a_reply_is_handled(build):
    bad = {**surplus_spec(), "name": "Bad Name"}
    script = [tools(("propose_spec", bad), ("propose_spec", surplus_spec())), *surplus_script()]
    results, model, _ = build(script, built(), brief=only_step("s1"))
    first, second = tool_messages(model, 1)
    assert first["is_error"] and second["is_error"] and second["content"] == ONE_CALL
    assistant = model.calls[1]["messages"][1]
    assert [first["tool_call_id"], second["tool_call_id"]] == [c["id"] for c in assistant["tool_calls"]]
    assert results == [S1]


def test_a_tool_the_phase_does_not_offer_is_an_error(build):
    script = [tools(("write_module", {"module_py": "", "tests_py": ""})), *surplus_script()]
    _, model, _ = build(script, built(), brief=only_step("s1"))
    [result] = tool_messages(model, 1)
    assert result["is_error"] and result["content"] == "There is no tool called write_module here."


def test_a_spec_that_fails_validate_spec_comes_back_as_bullets(build, conn):
    script = [propose_spec(name="Bad Name"), *surplus_script()]
    results, model, _ = build(script, built(), brief=only_step("s1"))
    [result] = tool_messages(model, 1)
    assert result["is_error"] is True
    [problem] = bullets(result["content"], SPEC_REJECTED)
    assert "name" in problem
    assert events(conn, "calc.spec_rejected") == [("calc.spec_rejected", "harness", {"step": "s1", "errors": [problem]})]
    assert results == [S1]


def test_the_assistant_message_and_the_tool_result_are_added_together(build):
    script = [propose_spec(name="Bad Name"), *surplus_script()]
    _, model, _ = build(script, built(), brief=only_step("s1"))
    messages = model.calls[1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert messages[1]["tool_calls"][0]["name"] == "propose_spec"
    assert messages[1]["tool_calls"][0]["arguments"]["name"] == "Bad Name"
    assert messages[2]["tool_call_id"] == messages[1]["tool_calls"][0]["id"]


def test_the_harness_drops_unknown_keys_and_sets_the_step_id(build, modules_dir):
    spec = surplus_spec(colour="red", step_id="s99")
    spec["inputs"] = [{**i, "unit": "eur"} for i in spec["inputs"]]
    spec["output"] = {**spec["output"], "scale": 2}
    results, _, _ = build([propose_spec(spec), propose_examples(), write_module()], built(), brief=only_step("s1"))
    assert results == [S1]
    written = (modules_dir / "monthly_surplus" / "spec.json").read_text(encoding="utf-8")
    assert written == h.dump(saved_spec(surplus_spec(), "s1"))


def test_a_new_module_may_not_take_the_name_of_a_registered_one(build, conn):
    h.install_surplus(conn, step_id="old_step")
    script = [propose_spec(), propose_spec(name="savings_gap"), propose_examples(), write_module()]
    results, model, _ = build(script, built(), brief=only_step("s1"))
    [result] = tool_messages(model, 1)
    assert NAME_TAKEN.format(name="monthly_surplus") in bullets(result["content"], SPEC_REJECTED)
    assert results[0]["module"] == "savings_gap"


def test_three_refused_specs_end_the_step_and_the_next_step_goes_ahead(build, conn):
    bad = propose_spec(name="Bad Name")
    script = [bad, say_text("no tool"), bad, *months_script()]
    results, model, person = build(script, built())
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_SPEC}, S3]
    assert len(model.calls) == 3 + 3
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_SPEC}]
    assert events(conn, "calc.step_not_built")[0][1] == "harness"
    assert "Step s3: Work out the months to reach the target" in person.told


def test_the_third_attempt_may_succeed(build):
    bad = propose_spec(name="Bad Name")
    results, model, _ = build([bad, bad, *surplus_script()], built(), brief=only_step("s1"))
    assert results == [S1] and len(model.calls) == 5


def test_a_step_that_is_not_built_leaves_nothing_behind(build, conn, modules_dir):
    bad = propose_spec(name="Bad Name")
    build([bad, bad, bad], brief=only_step("s1"))
    assert rows(conn, "modules") == [] and rows(conn, "step_modules") == []
    assert not (modules_dir / "monthly_surplus").exists()


def test_a_model_call_that_raises_leaves_the_exception_and_keeps_what_was_registered(build, conn, registry):
    from harness.model import ScriptExhausted

    with pytest.raises(ScriptExhausted):
        build(surplus_script() + [propose_spec(months_spec())], built() + ["yes"])      # s3 runs out of script
    assert [m["name"] for m in registry.list_modules(conn)] == ["monthly_surplus"]


def test_only_modules_with_unchanged_files_are_shown_to_the_spec_writer(build, conn, modules_dir):
    h.install_surplus(conn, step_id="old_step")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# changed\n", encoding="utf-8")
    h.install_months(conn, step_id="other_step")
    script = [propose_spec(months_spec(name="another_one")), propose_examples(h.months_examples()),
              write_module(h.MONTHS_PY, h.MONTHS_TESTS)]
    _, model, _ = build(script, built(), brief=only_step("s3"))
    section = model.calls[0]["messages"][0]["content"].split("[registered modules]\n")[1]
    assert "months_to_goal" in section and "monthly_surplus" not in section
