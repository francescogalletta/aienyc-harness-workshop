"""SPEC 2.4: the step line, the marks and the one step that needs the person, worked out by the core."""
import pytest

from harness.core.state import finish, show_value, step_line, step_marks


def step(**fields) -> dict:
    return {"id": "s1", "number": 1, "name": "A step", "kind": "calculation", "open_questions": [], **fields}


def built(**fields) -> dict:
    return {"status": "built", "examples": 4, "tests": 6, "passing": 6, "examples_passing": 4,
            "plan_check": None, "example_list": [], "disagreement": [], **fields}


def checked(n: int) -> list[dict]:
    return [{"n": k, "checked_by": "second_pass"} for k in range(1, n + 1)]


@pytest.mark.parametrize("value, shown", [
    ("43000.00", "43,000.00"),
    (1234567, "1,234,567"),
    ("-1234.5", "-1,234.5"),
    ("12.30", "12.30"),
    ("2026-10-10", "2026-10-10"),
    ("short text", "short text"),
    ("a much longer piece of text than fits", "a much longer pie…"),
    (["a", "b", "c"], "3 values"),
    ({"x": "1", "y": "2"}, "2 values"),
])
def test_how_a_result_is_written_on_the_step_line(value, shown):
    assert show_value(value) == shown


def test_needs_you_comes_first_and_names_the_call_when_a_decision_is_open():
    line = step_line(step(needs_you=True, calls={"open": "d4", "records": []}, build=built()))
    assert line == {"text": "Needs you · your call", "kind": "strong"}
    line = step_line(step(needs_you=True, build=built(status="not_built")))
    assert line == {"text": "Needs you · not built", "kind": "strong"}


def test_building_then_the_last_answer_then_built():
    assert step_line(step(build=built(status="building"))) == {"text": "Building", "kind": None}
    run = {"in_last_answer": True, "output": "43000.00"}
    assert step_line(step(build=built(), last_run=run)) == {"text": "→ 43,000.00", "kind": "result"}
    shown = step_line(step(build=built(), last_run=run, unconfirmed=[{"id": "a1", "text": "x"}]))
    assert shown == {"text": "→ 43,000.00 ◌", "kind": "result"}
    old_run = {"in_last_answer": False, "output": "1"}
    assert step_line(step(build=built(), last_run=old_run)) == {"text": "4 examples · 6/6", "kind": "tested"}


def test_a_built_step_is_tested_only_when_every_test_and_example_passes():
    assert step_line(step(build=built(passing=5))) == {"text": "4 examples · 5/6", "kind": None}
    assert step_line(step(build=built(examples_passing=3)))["kind"] is None


def test_stale_not_built_decided_and_nothing():
    assert step_line(step(build=built(status="stale"))) == {"text": "Stale · rebuild", "kind": None}
    assert step_line(step(build=built(status="not_built"))) == {"text": "Not built", "kind": None}
    decided = step(kind="your_call", calls={"open": None, "records": [{"decision": "d1"}]})
    assert step_line(decided) == {"text": "Decided", "kind": None}
    assert step_line(step()) is None
    assert step_line(step(build=built(status="none"))) is None


def test_marks_come_in_order_each_only_when_it_applies():
    full = step(open_questions=[{"text": "q1"}, {"text": "q2"}],
                build=built(plan_check={"departures": ["one way"], "confirmed": False}),
                challenges=["c1", "c2", "c3"], unconfirmed=[{"id": "a1", "text": "x"}])
    marks = step_marks(full)
    assert [(mark["symbol"], mark["count"]) for mark in marks] == [("●", 2), ("plan check", None), ("▲", 3),
                                                                   ("◌", None)]
    assert all(isinstance(mark["title"], str) and mark["title"] for mark in marks)
    assert step_marks(step()) == []
    confirmed = step(build=built(plan_check={"departures": ["one way"], "confirmed": True}))
    assert step_marks(confirmed) == []
    assert step_marks(step(build=built(plan_check={"departures": [], "confirmed": False}))) == []


def test_the_open_decision_wins_needs_you_and_only_one_step_has_it():
    steps = [step(id="s1", build=built(status="not_built", disagreement=[{"n": 1}])),
             step(id="s2", kind="your_call", calls={"open": "d1", "records": []})]
    finish({"steps": steps})
    assert [s["needs_you"] for s in steps] == [False, True]
    assert steps[1]["line"]["text"] == "Needs you · your call"


def test_with_no_decision_the_first_stuck_step_needs_you():
    steps = [step(id="s1", build=built()),
             step(id="s2", build=built(status="not_built", example_list=checked(2))),       # not stuck
             step(id="s3", build=built(status="not_built", example_list=checked(1))),       # too few checked
             step(id="s4", build=built(status="not_built", disagreement=[{"n": 2}]))]
    finish({"steps": steps})
    assert [s["needs_you"] for s in steps] == [False, False, True, False]
    assert [s["line"]["text"] for s in steps] == ["4 examples · 6/6", "Not built", "Needs you · not built",
                                                  "Not built"]


def test_a_layer_may_set_needs_you_and_the_core_keeps_at_most_one():
    steps = [step(id="s1", needs_you=True), step(id="s2", needs_you=True)]
    finish({"steps": steps})
    assert [s["needs_you"] for s in steps] == [True, False]
