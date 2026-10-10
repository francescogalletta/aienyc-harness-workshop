"""SPEC 5.7: progress lines, and the exact order of what is said, asked and sent to the model."""
import step2_helpers as h
from step2_helpers import (CONFIRM_EXAMPLE, EXAMPLES_INTRO, PLAN_QUESTION, READING_REPLY, RUNNING_TESTS, STEP_HEADER,
                           WRITING_CODE, WRITING_EXAMPLES, WRITING_SPEC, built, only_step, propose_examples,
                           propose_spec, respond, reuse_module, say_text, surplus_script, write_module)

HEADER = STEP_HEADER.format(id="s1", name="Work out the monthly surplus")
PLAN = ("To work this out: surplus = income - spending\nI will need from you:\n"
        "  - income (a number): Money in each month.\n  - spending (a number): Money out each month.\n"
        "It gives back: The surplus per month.")
BLOCKS = [
    "Example 1 of 3\n  income: 5123.45\n  spending: 3100.10\n  Working: 5123.45 less 3100.10 leaves 2023.35\n"
    "  Proposed answer: 2023.35",
    "Example 2 of 3\n  income: 4000\n  spending: 4500\n  Working: 4000 less 4500 is a shortfall of 500\n"
    "  Proposed answer: -500",
    "Example 3 of 3\n  income: 3000\n  spending: 3000\n  Working: 3000 less 3000 leaves 0\n  Proposed answer: 0"]
WRONG = write_module(h.WRONG_SURPLUS_PY, h.WRONG_SURPLUS_TESTS)


def say(text):
    return ("say", text)


def ask(text):
    return ("ask", text)


def call(role):
    return ("call", role)


def test_everything_shown_and_every_model_call_of_a_step_built_at_the_first_try(build):
    results, _, person = build(surplus_script(), built(), brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    assert person.log == [
        say(HEADER), say(WRITING_SPEC.format(attempt=1)), call("spec_writer"), say(PLAN), ask(PLAN_QUESTION),
        say(WRITING_EXAMPLES.format(attempt=1)), call("example_writer"), say(EXAMPLES_INTRO),
        say(BLOCKS[0]), ask(CONFIRM_EXAMPLE), say(BLOCKS[1]), ask(CONFIRM_EXAMPLE), say(BLOCKS[2]), ask(CONFIRM_EXAMPLE),
        say(WRITING_CODE.format(attempt=1)), call("module_writer"), say(RUNNING_TESTS)]


def test_a_skip_or_a_value_read_directly_adds_no_model_call(build):
    results, model, _ = build(surplus_script(), ["yes", "2023.35", "/skip", "/accept"], brief=only_step("s1"))
    assert results[0]["outcome"] == "built" and model.roles() == ["spec_writer", "example_writer", "module_writer"]


def test_a_reused_step_takes_one_call_and_no_answer(build, conn):
    h.install_surplus(conn, step_id="old_step")
    _, model, person = build([reuse_module("monthly_surplus")], brief=only_step("s1"))
    assert person.log[:3] == [say(HEADER), say(WRITING_SPEC.format(attempt=1)), call("spec_writer")]
    assert model.roles() == ["spec_writer"] and person.asked == []


def test_a_kept_step_says_only_its_header(build, conn):
    h.install_surplus(conn, step_id="s1")
    _, model, person = build([], brief=only_step("s1"))
    assert person.log[0] == say(HEADER) and model.calls == [] and person.asked == []


def test_each_free_text_reply_adds_one_helper_call_as_soon_as_it_is_typed(build):
    explain = respond("explain", message="It is made up.")
    script = [propose_spec(), propose_examples(), explain, explain, write_module()]
    answers = ["yes", "why?", "/accept", "what?", "/accept", "/accept"]
    results, model, person = build(script, answers, brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    assert model.roles() == ["spec_writer", "example_writer", "example_helper", "example_helper", "module_writer"]
    log = person.log
    for position in [i for i, entry in enumerate(log) if entry == call("example_helper")]:
        assert log[position - 2:position] == [ask(CONFIRM_EXAMPLE), say(READING_REPLY)]
        assert log[position + 1:position + 3] == [say("It is made up."), ask(CONFIRM_EXAMPLE)]


def test_the_plan_is_asked_before_the_examples_are_written(build):
    _, _, person = build(surplus_script(), built(), brief=only_step("s1"))
    assert person.log.index(ask(PLAN_QUESTION)) < person.log.index(call("example_writer"))


def test_a_progress_line_comes_just_before_each_call_and_counts_the_attempts(build):
    script = [say_text("no tool"), propose_spec(), say_text("no tool"), propose_examples(), WRONG, write_module()]
    results, model, person = build(script, built(), brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    log = person.log
    before = [log[i - 1] for i, entry in enumerate(log) if entry[0] == "call"]
    assert before == [say(WRITING_SPEC.format(attempt=1)), say(WRITING_SPEC.format(attempt=2)),
                      say(WRITING_EXAMPLES.format(attempt=1)), say(WRITING_EXAMPLES.format(attempt=2)),
                      say(WRITING_CODE.format(attempt=1)), say(WRITING_CODE.format(attempt=2))]


def test_the_attempts_are_counted_to_three_in_each_phase(build):
    bad_spec = propose_spec(name="Bad Name")
    script = [bad_spec, bad_spec, propose_spec(), propose_examples([]), propose_examples([]), propose_examples(),
              WRONG, WRONG, write_module()]
    _, _, person = build(script, built(), brief=only_step("s1"))
    lines = [t for t in person.told if t.startswith("  (writing")]
    assert lines == [WRITING_SPEC.format(attempt=n) for n in (1, 2, 3)] + [
        WRITING_EXAMPLES.format(attempt=n) for n in (1, 2, 3)] + [WRITING_CODE.format(attempt=n) for n in (1, 2, 3)]
