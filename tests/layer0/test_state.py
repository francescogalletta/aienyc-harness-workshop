"""SPEC 2.4: the step line, the marks and the one step that needs the person, worked out by the core."""
import pytest

from decimal import Decimal

from harness.core.state import (display, display_inputs, finish, show_number, show_scalar, show_value, step_line,
                                step_marks, tidy_numbers)


def step(**fields) -> dict:
    return {"id": "s1", "number": 1, "name": "A step", "kind": "calculation", "open_questions": [], **fields}


def built(**fields) -> dict:
    return {"status": "built", "examples": 4, "tests": 6, "passing": 6, "examples_passing": 4,
            "plan_check": None, "example_list": [], "disagreement": [], **fields}


def checked(n: int) -> list[dict]:
    return [{"n": k, "checked_by": "second_pass"} for k in range(1, n + 1)]


@pytest.mark.parametrize("value, shown", [
    ("43000.00", "43,000"),
    (1234567, "1,234,567"),
    ("-1234.5", "-1,234.50"),
    ("12.30", "12.30"),
    ("1888.888888888888888888888889", "1,888.89"),
    ("0.30952380952380952", "0.3095"),
    ("0.5", "0.5"),
    ("2026-10-10", "2026-10-10"),
    ("short text", "short text"),
    ("a much longer piece of text than fits", "a much longer pie…"),
    (["a", "b", "c"], "3 values"),
    ({"x": "1", "y": "2"}, "2 values"),
    (["a"], "1 value"),
])
def test_how_a_result_is_written_on_the_step_line(value, shown):
    assert show_value(value) == shown


def test_an_object_or_a_list_of_rows_shows_its_key_value_when_one_is_obvious():
    rows = [{"month": "2027-01", "balance": "1300"}, {"month": "2028-03", "balance": "29400.004"}]
    assert show_value(rows) == "last balance 29,400"                  # the only numeric key
    named = {"description": "The gap to the target: shortfall, and the target and balance it compares."}
    found = {"name": "x", "shortfall": "5600", "target": "40000", "balance": "34400"}
    assert show_value(found, {"description": "Each has a shortfall."}) == "shortfall 5,600"
    assert show_value(found, named) == "4 values"                       # three keys named: none is obvious
    assert show_value([{"x": "1", "y": "2"}], {"description": "a list"}) == "1 value"
    assert show_value({"rate": "0.30952"}) == "rate 0.3095"


def test_how_a_value_is_written_for_the_eye():
    assert [show_number(Decimal(each)) for each in ("1300.00", "1888.885", "-2.5", "0.123456", "0", "1999999.999")] \
        == ["1,300", "1,888.89", "-2.50", "0.1235", "0", "2,000,000"]
    assert show_number(Decimal("2027"), "year") == "2027" and show_number(Decimal("2027")) == "2,027"
    assert show_scalar(True) == "yes" and show_scalar("2027-05-13") == "2027-05-13" and show_scalar(None) == "nothing"
    assert display("43000.00") == {"text": "43,000"}
    assert display({"payment_1_amount": "18500", "payment_1_due_date": "2027-05-13"}) == {
        "text": "2 values", "rows": [["payment 1 amount", "18,500"], ["payment 1 due date", "2027-05-13"]]}
    assert display([{"name": "first", "amount": "6000"}, {"name": "second", "left": "0.5"}]) == {
        "text": "2 values", "columns": ["name", "amount", "left"],
        "table": [["first", "6,000", ""], ["second", "", "0.5"]]}
    assert display(["1", "2.345"]) == {"text": "2 values", "rows": [["1", "1"], ["2", "2.35"]]}
    assert display_inputs({"guest_count": "150", "costs": [{"amount": "5000"}]}) == [
        ["guest count", {"text": "150"}], ["costs", {"text": "1 value", "columns": ["amount"], "table": [["5,000"]]}]]


def test_longer_decimals_in_text_are_rewritten_and_nothing_else():
    text = "Save 1888.888888888888888888888889 a month, rate 0.30952380952, 1,234.5 and 12.25, on 2027-05-13."
    assert tidy_numbers(text) == "Save 1,888.89 a month, rate 0.3095, 1,234.5 and 12.25, on 2027-05-13."


def test_needs_you_comes_first_and_names_the_call_when_a_decision_is_open():
    line = step_line(step(needs_you=True, calls={"open": "d4", "records": []}, build=built()))
    assert line == {"text": "Needs you · your call", "kind": "strong"}
    line = step_line(step(needs_you=True, build=built(status="not_built")))
    assert line == {"text": "Needs you · not built", "kind": "strong"}


def test_building_then_the_last_answer_then_built():
    assert step_line(step(build=built(status="building"))) == {"text": "Building", "kind": None}
    run = {"in_last_answer": True, "output": "43000.00"}
    assert step_line(step(build=built(), last_run=run)) == {"text": "→ 43,000", "kind": "result"}
    shown = step_line(step(build=built(), last_run=run, unconfirmed=[{"id": "a1", "text": "x"}]))
    assert shown == {"text": "→ 43,000 ◌", "kind": "result"}
    rows = {"in_last_answer": True, "output": [{"name": "a", "shortfall": "0"}, {"name": "b", "shortfall": "5250"}]}
    spec = {"spec": {"output": {"type": "list", "description": "each has name and shortfall"}}}
    assert step_line(step(build=built(**spec), last_run=rows))["text"] == "→ last shortfall 5,250"
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
