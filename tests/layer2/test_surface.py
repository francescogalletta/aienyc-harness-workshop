"""SPEC 4.7 and 4.8: the layer 2 surface: the state it contributes, its actions, the step helper, the
`build` command and the `steps` expectation."""
from pathlib import Path

import pytest
from state_shape import problems

from harness.calc import builder, helper
from harness.calc.added import add_step
from harness.calc.layer import LAYER, run_build_command
from harness.calc.notes import list_notes
from harness.core import NO_ROUTE, BadAction
from harness.model import ScriptedModel
from layer2_helpers import (SETTLE, TOTAL_CODE, TOTAL_EXAMPLES, TOTAL_SPEC, WRONG_TOTAL_CODE, call, checker_turn,
                            code_turn, double_turns, events, examples_turn, respond_turn, small_plan, spec_turn,
                            step_of, total_turns, write_plan)

HELPER_PROMPT = Path(helper.__file__).with_name("step_helper.md").read_text(encoding="utf-8")


def plain(items):
    """Disagreements without how the pop-up shows them."""
    return [{key: value for key, value in each.items() if key != "shown"} for each in items]


def built(open_session, build, *, departures=(), left_out=False, extra=()):
    """A session whose two steps are built. `left_out`: the second pass disagrees with total's example 3,
    so it is left out. `extra` are the model turns that follow the build."""
    first = total_turns(departures)
    if left_out:
        first[2] = checker_turn(TOTAL_EXAMPLES, answers={3: "349"})
    session = open_session(first + double_turns() + list(extra))
    build(session)
    return session


def say(session, text, step="c1"):
    applied, reason = session.act("say", {"text": text, "step": step})
    assert applied, reason
    return session.settle(SETTLE)


def harness_lines(state):
    return [message["text"] for message in state["chat"] if message["who"] == "harness"]


def checked_by(state, step_id="c1"):
    return [each["checked_by"] for each in step_of(state, step_id)["build"]["example_list"]]


# --- The state a build leaves ---

def test_the_state_keeps_its_shape_before_during_and_after_a_build(tmp_path, plan, open_session):
    class Watching:
        def __init__(self):
            self.inner, self.seen, self.session = ScriptedModel(total_turns() + double_turns()), [], None

        def complete(self, **request):
            self.seen.append(self.session.state())
            return self.inner.complete(**request)

    model = Watching()
    session = open_session(model=model)
    model.session = session
    before = session.state()
    assert [step["build"]["status"] for step in before["steps"] if step["build"]] == ["none", "none"]
    assert step_of(before, "j1")["build"] is None and problems(before, strict=True) == []
    applied, _ = session.act("build", {})
    assert applied
    after = session.settle(SETTLE)
    for state in [*model.seen, after]:
        assert problems(state, strict=True) == []
    assert {step_of(seen, entry["step"])["build"]["status"] for seen in model.seen
            for entry in seen["activity"] if entry["what"] == "build"} == {"building"}
    changed = small_plan()                                  # stale: the plan moved under a built step
    changed["process"][0]["formula"] = "a plus b"
    write_plan(tmp_path / "brief", changed)
    stale = session.state()
    assert step_of(stale, "c1")["build"]["status"] == "stale" and problems(stale, strict=True) == []


def test_a_step_that_is_not_built_shows_why_what_disagreed_and_the_code(plan, open_session, build):
    script = [spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES), checker_turn(TOTAL_EXAMPLES),
              *[code_turn(WRONG_TOTAL_CODE)] * 3, *double_turns()]
    state = build(open_session(script))
    step = step_of(state, "c1")
    assert problems(state, strict=True) == []
    assert step["needs_you"] and step["line"]["kind"] == "strong"
    assert step["build"]["disagreement"] and step["build"]["code"]["tests_py"]
    assert [each["checked_by"] for each in step["build"]["example_list"]] == ["second_pass"] * 3
    assert step_of(state, "c2")["needs_you"] is False


def test_the_popup_detail_names_who_checked_each_example_and_the_departures(plan, open_session, build):
    session = built(open_session, build, departures=["Takes a list of costs"], left_out=True)
    state = session.state()
    found = step_of(state, "c1")["build"]
    assert problems(state, strict=True) == []
    assert checked_by(state) == ["second_pass", "second_pass", None]
    assert found["example_list"][2]["second_pass"] == "349" and found["examples"] == 2
    assert found["spec"]["formula"] == "a + b" and found["tested_at"] and found["code"]["module_py"]
    assert found["plan_check"] == {"departures": ["Takes a list of costs"], "confirmed": False}
    assert "plan check" in [mark["symbol"] for mark in step_of(state, "c1")["marks"]]
    assert found["example_list"][2]["shown"] == {"inputs": [["a", {"text": "100"}], ["b", {"text": "250"}]],
                                                 "expected": {"text": "350"}, "second_pass": {"text": "349"}}


def test_a_step_added_in_a_conversation_is_drawn_last_and_not_in_the_plan(plan, open_session):
    session = open_session([])
    add_step(session.conn, name="Cost per head", formula="total / 2", needs="total", produces="cost per head",
             reason="asked for", session_id="t")
    state = session.state()
    last = state["steps"][-1]
    assert (last["id"], last["in_plan"], last["kind"]) == ("added_1", False, "calculation")
    assert last["build"]["status"] == "none" and problems(state, strict=True) == []


# --- The actions ---

def test_confirming_a_left_out_example_records_it_and_checks_the_code_without_the_model(plan, open_session, build):
    session = built(open_session, build, left_out=True)
    calls = len(session.script.calls)
    assert session.act("confirm_example", {"step": "c1", "n": 3})[0]
    state = session.settle(SETTLE)
    assert checked_by(state) == ["second_pass", "second_pass", "you"]
    assert step_of(state, "c1")["build"]["examples"] == 3 and step_of(state, "c1")["build"]["status"] == "built"
    assert len(session.script.calls) == calls and state["error"] is None
    assert events(session, "build.example_confirmed")[0]["n"] == 3
    assert events(session, "build.tests_run")[-1]["reason"] == "build"


def test_confirm_example_is_refused_when_it_is_already_yours_or_does_not_exist(plan, open_session, build):
    session = built(open_session, build)
    assert session.act("confirm_example", {"step": "c1", "n": 1})[0]
    session.settle(SETTLE)
    assert checked_by(session.state()) == ["you", "second_pass", "second_pass"]
    refused, reason = session.act("confirm_example", {"step": "c1", "n": 1})
    assert not refused and reason
    assert not session.act("confirm_example", {"step": "c1", "n": 9})[0]
    assert not session.act("confirm_example", {"step": "j1", "n": 1})[0]
    assert not session.act("confirm_example", {"step": "nothing", "n": 1})[0]
    with pytest.raises(BadAction):
        session.act("confirm_example", {"step": "c1"})
    with pytest.raises(BadAction):
        session.act("confirm_example", {"n": 1})


def test_confirming_the_plan_check_clears_its_mark_once(plan, open_session, build):
    session = built(open_session, build, departures=["Takes a list of costs"])
    assert session.act("confirm_plan_check", {"step": "c1"})[0]
    state = session.state()
    assert step_of(state, "c1")["build"]["plan_check"]["confirmed"] and step_of(state, "c1")["marks"] == []
    assert not session.act("confirm_plan_check", {"step": "c1"})[0]
    assert not session.act("confirm_plan_check", {"step": "c2"})[0]              # no departures there
    assert events(session, "build.departures_confirmed")[0]["step"] == "c1"


def test_run_tests_queues_a_test_run_for_a_step_with_a_module(plan, open_session, build):
    session = built(open_session, build)
    runs = len(events(session, "build.tests_run"))
    assert session.act("run_tests", {"step": "c2"})[0]
    state = session.settle(SETTLE)
    assert len(events(session, "build.tests_run")) == runs + 1
    assert events(session, "build.tests_run")[-1]["reason"] == "status"
    assert step_of(state, "c2")["build"]["tested_at"]
    assert not session.act("run_tests", {"step": "j1"})[0]


def test_run_tests_is_refused_for_a_step_with_no_module(plan, open_session):
    session = open_session([])
    refused, reason = session.act("run_tests", {"step": "c1"})
    assert not refused and reason


# --- Who gets a message about a step ---

def test_a_message_with_a_calculation_step_goes_to_the_helper_and_others_are_not_routed(plan, open_session, build):
    seen = []

    class Watching:
        def __init__(self):
            self.inner = ScriptedModel(total_turns() + double_turns() + [respond_turn("explain", message="It adds.")])
            self.session = None

        def complete(self, **request):
            seen.append([entry["what"] for entry in self.session.state()["activity"]])
            return self.inner.complete(**request)

    model = Watching()
    session = open_session(model=model)
    model.session = session
    build(session)
    state = say(session, "what does this do?")
    assert seen[-1] == ["helper"]
    sent = model.inner.calls[-1]
    assert sent["system"] == HELPER_PROMPT and [tool.name for tool in sent["tools"]] == ["respond"]
    asked = sent["messages"][0]["content"]
    assert "what does this do?" in asked and "[spec]" in asked and "[examples]" in asked
    assert any(message["who"] == "assistant" and message["step"] == "c1" for message in state["chat"])
    for text, step in (("hello", None), ("is this enough?", "j1"), ("what is this?", "nothing")):
        before = len(model.inner.calls)
        state = say(session, text, step)
        assert harness_lines(state)[-1] == NO_ROUTE and len(model.inner.calls) == before


def test_wants_is_true_for_not_built_left_out_and_unconfirmed_steps_only(plan, open_session, build):
    session = built(open_session, build, departures=["Takes a list of costs"], left_out=True)
    assert helper.wants(session, "c1")                                  # left out and departures
    session.act("confirm_plan_check", {"step": "c1"})
    assert helper.wants(session, "c1")                                  # still the left-out example
    session.act("confirm_example", {"step": "c1", "n": 3})
    session.settle(SETTLE)
    assert not helper.wants(session, "c1") and not helper.wants(session, "c2")
    assert not helper.wants(session, "j1") and not helper.wants(session, "nothing")


def test_a_step_that_is_not_built_is_the_helpers(plan, open_session):
    stuck = open_session([])
    assert helper.wants(stuck, "c1") is False                           # nothing built yet: status none
    stuck.conn.execute("INSERT INTO build_steps (step_id, status, module, spec, departures, departures_confirmed,"
                       " examples, disagreement, reason, step_fingerprint, ts)"
                       " VALUES ('c1', 'not_built', NULL, NULL, '[]', 0, '[]', '[]', 'no', '', 'x')")
    stuck.conn.commit()
    assert helper.wants(stuck, "c1")


# --- The helper's five actions ---

def test_correct_stores_the_answer_and_checks_the_code_against_it(plan, open_session, build):
    session = built(open_session, build, left_out=True,
                    extra=[respond_turn("correct", example=3, answer="350")])
    calls = len(session.script.calls)
    state = say(session, "Example 3 is 350")
    assert len(session.script.calls) == calls + 1                       # the helper's only
    assert checked_by(state)[2] == "you" and step_of(state, "c1")["build"]["examples"] == 3
    assert step_of(state, "c1")["build"]["status"] == "built"
    assert session.conn.execute("SELECT answer FROM example_confirmations").fetchone()[0] == '"350"'
    assert harness_lines(state)[-1] == helper.STEP_BUILT.format(name="Total")
    assert events(session, "build.helper")[0] == {"step": "c1", "action": "correct", "example": 3,
                                                  "accepted": True}


def test_the_other_passs_answer_may_be_taken_and_a_failing_correction_leaves_the_step_not_built(
        plan, open_session, build):
    session = built(open_session, build, left_out=True,
                    extra=[respond_turn("correct", example=3, answer="349"), *[code_turn(TOTAL_CODE)] * 3])
    state = say(session, "the second answer is right")                  # 349 is in no word of theirs
    found = step_of(state, "c1")["build"]
    assert (found["status"], found["reason"]) == ("not_built", builder.REASON_CODE)
    assert plain(found["disagreement"]) == [{"n": 3, "expected": "349", "code_gives": "350"}]
    assert found["example_list"][2]["checked_by"] == "you" and step_of(state, "c1")["needs_you"]
    assert harness_lines(state)[-1] == helper.STEP_NOT_BUILT.format(name="Total", reason=builder.REASON_CODE)
    assert problems(state, strict=True) == []


def test_a_call_that_fails_a_check_changes_nothing_and_gets_the_unclear_reply(plan, open_session, build):
    turns = [
        respond_turn("correct", example=1, answer="31"),                # 31 is in neither the words nor the example
        respond_turn("correct", example=1, answer=["30"]),              # not a number
        respond_turn("correct", example=9, answer="30"),                # no such example
        respond_turn("correct", example=1),                             # no answer
        respond_turn("confirm", example=9),
        respond_turn("confirm", example=0),                             # nothing departs from the plan
        respond_turn("explain", message="It adds 77 and 78."),          # numbers nobody gave
        respond_turn("explain"),
        {"text": "I think you mean the first one."},                    # no call at all
        call("something_else", action="note"),
    ]
    session = built(open_session, build, extra=turns)
    before = session.state()["steps"]
    for number in range(len(turns)):
        state = say(session, "make it right")
        assert harness_lines(state).count(helper.HELPER_UNCLEAR) == number + 1
    assert state["steps"] == before and session.conn.execute(
        "SELECT COUNT(*) FROM example_confirmations").fetchone()[0] == 0
    assert list_notes(session.conn) == [] and [each["accepted"] for each in events(session, "build.helper")] == [
        False] * len(turns)


def test_confirm_marks_an_example_or_the_departures_as_the_persons(plan, open_session, build):
    session = built(open_session, build, departures=["Takes a list of costs"], left_out=True,
                    extra=[respond_turn("confirm", example=0), respond_turn("confirm", example=3)])
    state = say(session, "that difference from the plan is fine")
    assert step_of(state, "c1")["build"]["plan_check"]["confirmed"] and step_of(state, "c1")["marks"] == []
    state = say(session, "example 3 is right")
    assert checked_by(state) == ["second_pass", "second_pass", "you"]
    assert step_of(state, "c1")["build"]["examples"] == 3 and harness_lines(state)[-1]


def test_explain_answers_in_the_chat_without_changing_the_step(plan, open_session, build):
    session = built(open_session, build, extra=[respond_turn(
        "explain", message="Example 1 adds 10 and 20 to get 30. It is made up, only to check the arithmetic.")])
    before = step_of(session.state(), "c1")["build"]
    state = say(session, "why is the first example 30?")
    reply = state["chat"][-1]
    assert (reply["who"], reply["step"], reply["kind"]) == ("assistant", "c1", "text")
    assert step_of(state, "c1")["build"] == before and problems(state, strict=True) == []


def test_note_keeps_the_persons_words_and_builds_nothing(plan, open_session, build):
    words = "We have 5,000 saved already, and we add 400 a month."
    session = built(open_session, build, extra=[respond_turn("note")])
    calls = len(session.script.calls)
    state = say(session, words)
    assert [note["text"] for note in list_notes(session.conn)] == [words]
    assert events(session, "build.note")[0]["step"] == "c1"
    assert len(session.script.calls) == calls + 1 and step_of(state, "c1")["build"]["status"] == "built"
    assert harness_lines(state)[-1] == helper.NOTE_KEPT.format(name="Total")


def test_rebuild_keeps_the_words_as_a_note_and_builds_the_step_again(plan, open_session, build):
    again = [spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES), checker_turn(TOTAL_EXAMPLES),
             code_turn(TOTAL_CODE)]
    session = built(open_session, build, extra=[respond_turn("rebuild"), *again])
    words = "It should also take the fees."
    state = say(session, words)
    spec_call = session.script.calls[9]                                  # after the build and the helper
    assert words in spec_call["messages"][0]["content"] and "[current spec]" in spec_call["messages"][0]["content"]
    assert [note["text"] for note in list_notes(session.conn)] == [words]
    assert step_of(state, "c1")["build"]["status"] == "built" and state["error"] is None
    assert events(session, "build.started")[-1] == {"step": "c1", "code_only": False, "rebuild": None}
    assert harness_lines(state)[-1] == helper.STEP_BUILT.format(name="Total")


# --- The terminal command and the replay expectation ---

def test_the_build_command_builds_prints_a_line_per_step_and_exits_by_the_result(plan, open_session):
    session = open_session(total_turns() + double_turns())
    lines = []
    assert run_build_command(session, write=lines.append) == 0
    assert [line.split(":")[0] for line in lines if "built" in line and ":" in line][-2:] == ["c1  Total",
                                                                                            "c2  Double"]
    assert any(builder.BUILD_DONE.format(built=2, total=2) in line for line in lines)


def test_the_build_command_exits_1_while_a_step_is_not_built(plan, open_session):
    lines = []
    stuck = open_session([spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES), checker_turn(TOTAL_EXAMPLES),
                          *[code_turn(WRONG_TOTAL_CODE)] * 3, *double_turns()])
    assert run_build_command(stuck, write=lines.append) == 1
    assert any("c1" in line and "not_built" in line for line in lines)


def test_the_build_command_stops_without_an_accepted_plan(open_session):
    lines = []
    assert run_build_command(open_session([]), write=lines.append) == 1 and lines


def test_the_steps_expectation_compares_with_the_latest_build(plan, open_session, build):
    expect = LAYER.expects["steps"]
    session = built(open_session, build)
    assert expect.validate({"c1": "built", "c2": "kept"}) is None
    assert expect.validate({"c1": "fine"}) and expect.validate([]) and expect.validate({})
    assert expect.check({"c1": "built", "c2": "built"}, session)["passed"]
    result = expect.check({"c1": "not_built"}, session)
    assert not result["passed"] and result["seen"] == {"c1": "built", "c2": "built"}
