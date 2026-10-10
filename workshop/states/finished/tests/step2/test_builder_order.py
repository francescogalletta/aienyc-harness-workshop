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


