"""SPEC 6.4 and 6.5: `check_scenario`, each expectation evaluated against what a session recorded."""
import json

import pytest

import step3_helpers as s3
from step3_helpers import h, record

SESSION = h.SESSION
INCOME = {"income": "5000", "spending": "3000"}


@pytest.fixture
def modules(conn):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


def run(gate, conn, inputs=None, module="monthly_surplus", session=SESSION):
    inputs = INCOME if inputs is None else inputs
    return gate.call(conn, module, inputs, assumptions=[], expected="about 2000", session_id=session)


def reply(conn, text, session=SESSION):
    record(conn, session, "ask.reply", "agent", text=text)


def scenario(kind="ask", **expect):
    return {"name": "upfront", "kind": kind, "lines": ["x"], "expect": expect}


def check(replay, conn, results=None, session=SESSION, **expect):
    return replay.check_scenario(conn, session, scenario(**expect), results)


def build_check(replay, conn, results, **expect):
    return replay.check_scenario(conn, SESSION, scenario("build", **expect), results)


# ---- the shape -------------------------------------------------------------------------------------------------

def test_a_check_has_what_passed_and_seen(replay, conn, modules, gate):
    run(gate, conn)
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus"}])
    assert list(found) == ["what", "passed", "seen"]
    assert found["passed"] is True and isinstance(found["what"], str) and isinstance(found["seen"], str)


def test_checking_records_nothing(replay, conn, modules, gate):
    run(gate, conn)
    before = len(h.events(conn))
    check(replay, conn, runs=[{"module": "monthly_surplus"}], shown=["2,000"], max_withheld=0)
    assert len(h.events(conn)) == before


def test_one_check_per_expectation_in_the_order_runs_shown_not_shown_withheld_corrections_steps(replay, conn, modules, gate):
    run(gate, conn)
    reply(conn, "You have 2,000.")
    expect = {"max_corrections": 1, "steps": {"s3": "kept", "s1": "built"}, "max_withheld": 1, "not_shown": ["9,999", "8,888"],
              "shown": ["2,000", "5,000"], "runs": [{"module": "months_to_goal"}, {"module": "monthly_surplus"}]}
    results = [{"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""},
               {"step": "s3", "outcome": "kept", "module": "months_to_goal", "reason": ""}]
    found = check(replay, conn, results, **expect)
    assert [c["what"] for c in found] == [
        "ran months_to_goal", "ran monthly_surplus", "shows 2,000", "shows 5,000", "does not show 9,999",
        "does not show 8,888", "at most 1 replies withheld", "at most 1 corrections", "step s3 kept", "step s1 built"]


# ---- runs ---------------------------------------------------------------------------------------------------------------

def test_a_run_of_the_module_in_the_session(replay, conn, modules, gate):
    ran = run(gate, conn)
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus"}])
    assert found == {"what": "ran monthly_surplus", "passed": True,
                     "seen": f'run {ran["run_id"]}: {{"income": "5000", "spending": "3000"}}'}


def test_no_run_of_the_module(replay, conn, modules, gate):
    run(gate, conn)
    [found] = check(replay, conn, runs=[{"module": "months_to_goal"}])
    assert found == {"what": "ran months_to_goal", "passed": False, "seen": "no run of months_to_goal"}


def test_with_inputs_the_what_shows_them_as_json(replay, conn, modules, gate):
    run(gate, conn)
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus", "inputs": {"income": "5000"}}])
    assert found["what"] == 'ran monthly_surplus with {"income": "5000"}' and found["passed"] is True


def test_the_what_keeps_non_ascii_text_as_it_is(replay, conn, modules, gate):
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus", "inputs": {"note": "café"}}])
    assert found["what"] == 'ran monthly_surplus with {"note": "café"}'


def test_every_run_of_the_module_is_seen_by_id_joined_by_semicolons(replay, conn, modules, gate):
    first = run(gate, conn)
    other = run(gate, conn, module="months_to_goal", inputs={"target": "1000", "monthly_saving": "250"})
    second = run(gate, conn, {"income": "6000", "spending": "4000"})
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus"}])
    assert found["seen"] == (f'run {first["run_id"]}: {{"income": "5000", "spending": "3000"}}; '
                             f'run {second["run_id"]}: {{"income": "6000", "spending": "4000"}}')
    assert f'run {other["run_id"]}:' not in found["seen"]


def test_some_run_must_have_each_listed_input(replay, conn, modules, gate):
    run(gate, conn)
    run(gate, conn, {"income": "6000", "spending": "4000"})
    found = check(replay, conn, runs=[{"module": "monthly_surplus", "inputs": {"income": "6000"}},
                                      {"module": "monthly_surplus", "inputs": {"income": "7000"}},
                                      {"module": "monthly_surplus", "inputs": {"income": "5000", "spending": "4000"}}])
    assert [c["passed"] for c in found] == [True, False, False]           # the keys must come from one run
    assert all(c["seen"].count("run ") == 2 for c in found)


def test_inputs_are_compared_with_same(replay, conn, modules, gate):
    run(gate, conn)
    found = check(replay, conn, runs=[{"module": "monthly_surplus", "inputs": {"income": "5000.00"}},
                                      {"module": "monthly_surplus", "inputs": {"income": 5000}},
                                      {"module": "monthly_surplus", "inputs": {"income": "5000.004"}},
                                      {"module": "monthly_surplus", "inputs": {"income": "5000.01"}},
                                      {"module": "monthly_surplus", "inputs": {"income": "4999.99"}}])
    assert [c["passed"] for c in found] == [True, True, True, False, False]


def test_keys_that_are_not_listed_are_not_compared(replay, conn, modules, gate):
    run(gate, conn)
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus", "inputs": {"spending": "3000"}}])
    assert found["passed"] is True


def test_a_listed_key_the_run_does_not_have_fails(replay, conn, modules, gate):
    run(gate, conn)
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus", "inputs": {"rent": "1"}}])
    assert found["passed"] is False and found["seen"].startswith("run ")


def test_text_is_compared_exactly(replay, conn, modules, gate):
    h.install(conn, h.yearly_files("added_1"), "added_1")
    run(gate, conn, {"monthly": "250"}, module="yearly_cost")
    found = check(replay, conn, runs=[{"module": "yearly_cost", "inputs": {"monthly": "250"}},
                                      {"module": "yearly_cost", "inputs": {"monthly": "250.0"}},
                                      {"module": "yearly_cost", "inputs": {"monthly": "250.01"}}])
    assert [c["passed"] for c in found] == [True, True, False]


def test_runs_of_another_session_do_not_count(replay, conn, modules, gate):
    run(gate, conn, session="somebody-else")
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus"}])
    assert found["passed"] is False and found["seen"] == "no run of monthly_surplus"
    [found] = check(replay, conn, session="somebody-else", runs=[{"module": "monthly_surplus"}])
    assert found["passed"] is True


def test_a_refused_call_is_not_a_run(replay, conn, modules, gate):
    with pytest.raises(gate.Refused):
        gate.call(conn, "monthly_surplus", {"income": "x"}, assumptions=[], expected="y", session_id=SESSION)
    [found] = check(replay, conn, runs=[{"module": "monthly_surplus"}])
    assert found["passed"] is False


# ---- shown and not_shown ----------------------------------------------------------------------------------------------------------

def test_a_number_is_seen_in_the_first_reply_that_backs_it(replay, conn):
    reply(conn, "Nothing yet.")
    reply(conn, "You have 2,000 left.")
    reply(conn, "Still 2,000 left, or 3,500.")
    found = check(replay, conn, shown=["2,000", "3,500"])
    assert found == [{"what": "shows 2,000", "passed": True, "seen": "in reply 2 of 3"},
                     {"what": "shows 3,500", "passed": True, "seen": "in reply 3 of 3"}]


def test_a_number_that_no_reply_backs(replay, conn):
    reply(conn, "You have 2,000 left.")
    reply(conn, "Nothing else.")
    [found] = check(replay, conn, shown=["9,999"])
    assert found == {"what": "shows 9,999", "passed": False, "seen": "in none of 2 replies"}


def test_not_shown_passes_when_no_reply_shows_it_and_fails_when_one_does(replay, conn):
    reply(conn, "You have 2,000 left.")
    found = check(replay, conn, not_shown=["9,999", "2,000"])
    assert found == [{"what": "does not show 9,999", "passed": True, "seen": "in none of 1 replies"},
                     {"what": "does not show 2,000", "passed": False, "seen": "in reply 1 of 1"}]


def test_with_no_reply_at_all(replay, conn):
    found = check(replay, conn, shown=["2,000"], not_shown=["2,000"])
    assert found == [{"what": "shows 2,000", "passed": False, "seen": "in none of 0 replies"},
                     {"what": "does not show 2,000", "passed": True, "seen": "in none of 0 replies"}]


@pytest.mark.parametrize("written, replied, seen", [
    ("4,583", "That is 4,583.33 a month.", True),
    ("4,583.33", "That is 4,583 a month.", False),
    ("4,583.33", "That is 4,583.333 a month.", True),
    ("4.6k", "That is 4,583.33 a month.", True),
    ("4,600", "That is 4,583.33 a month.", False),
    ("50%", "A rate of 0.5 applies.", True),
    ("0.5", "A rate of 50% applies.", True),
    ("$2,000", "You keep 2000 a month.", True),
    ("2,000", "You keep €2,000.00 a month.", True),
    ("2,000", "You keep 2,001 a month.", False),
    ("1,250.5", "You keep 1,250.50 a month.", True)])
def test_a_number_is_seen_at_the_precision_it_is_written_in_the_scenario(replay, conn, written, replied, seen):
    reply(conn, replied)
    [found] = check(replay, conn, shown=[written])
    assert found["passed"] is seen
    assert found["seen"] == ("in reply 1 of 1" if seen else "in none of 1 replies")


def test_only_replies_shown_to_the_person_count(replay, conn):
    reply(conn, "You have 2,000 left.")
    record(conn, SESSION, "ask.withheld", "harness", numbers=["7,777"], text="It is 7,777.")
    record(conn, SESSION, "ask.correction", "harness", reason="reply", numbers=["6,666"], text="It is 6,666.")
    record(conn, SESSION, "ask.module_requested", "agent", arguments={}, request="The assistant asks 5,555.")
    record(conn, SESSION, "ask.message", "person", text="I have 4,444.")
    found = check(replay, conn, shown=["7,777", "6,666", "5,555", "4,444"], not_shown=["7,777", "6,666", "5,555", "4,444"])
    assert [c["passed"] for c in found] == [False] * 4 + [True] * 4
    assert {c["seen"] for c in found} == {"in none of 1 replies"}


def test_replies_of_another_session_do_not_count(replay, conn):
    reply(conn, "You have 2,000 left.", session="somebody-else")
    reply(conn, "Nothing.")
    [found] = check(replay, conn, shown=["2,000"])
    assert found == {"what": "shows 2,000", "passed": False, "seen": "in none of 1 replies"}


# ---- the limits ----------------------------------------------------------------------------------------------------------------------------

def withheld(conn, session=SESSION):
    record(conn, session, "ask.withheld", "harness", numbers=["1,234"], text="It is 1,234.")


def corrected(conn, reason="reply", session=SESSION):
    record(conn, session, "ask.correction", "harness", reason=reason, numbers=["1,234"], text="It is 1,234.")


@pytest.mark.parametrize("count, limit, passed", [(0, 0, True), (1, 0, False), (1, 1, True), (2, 1, False), (3, 5, True)])
def test_max_withheld(replay, conn, count, limit, passed):
    for _ in range(count):
        withheld(conn)
    [found] = check(replay, conn, max_withheld=limit)
    assert found == {"what": f"at most {limit} replies withheld", "passed": passed, "seen": f"{count} withheld"}


@pytest.mark.parametrize("count, limit, passed", [(0, 0, True), (1, 0, False), (1, 1, True), (3, 2, False), (2, 2, True)])
def test_max_corrections(replay, conn, count, limit, passed):
    for index in range(count):
        corrected(conn, ["reply", "run_module", "save_input", "request_module"][index % 4])
    [found] = check(replay, conn, max_corrections=limit)
    assert found == {"what": f"at most {limit} corrections", "passed": passed, "seen": f"{count} corrections"}


def test_corrections_of_every_reason_count_and_the_other_session_does_not(replay, conn):
    for reason in ("reply", "run_module", "save_input", "request_module"):
        corrected(conn, reason)
    corrected(conn, session="somebody-else")
    withheld(conn, session="somebody-else")
    found = check(replay, conn, max_withheld=0, max_corrections=3)
    assert found == [{"what": "at most 0 replies withheld", "passed": True, "seen": "0 withheld"},
                     {"what": "at most 3 corrections", "passed": False, "seen": "4 corrections"}]


# ---- steps ----------------------------------------------------------------------------------------------------------------------------------

def result_of(step, outcome, module="monthly_surplus", reason=""):
    return {"step": step, "outcome": outcome, "module": module if outcome != "not_built" else None, "reason": reason}


def test_a_step_with_the_outcome_expected(replay, conn):
    results = [result_of("s1", "built"), result_of("s3", "kept", "months_to_goal")]
    found = build_check(replay, conn, results, steps={"s1": "built", "s3": "kept"})
    assert found == [{"what": "step s1 built", "passed": True, "seen": "built"},
                     {"what": "step s3 kept", "passed": True, "seen": "kept"}]


def test_a_step_with_another_outcome(replay, conn):
    [found] = build_check(replay, conn, [result_of("s1", "reused")], steps={"s1": "built"})
    assert found == {"what": "step s1 built", "passed": False, "seen": "reused"}


def test_a_step_not_built_shows_its_reason(replay, conn):
    results = [result_of("s1", "not_built", reason=h.REASON_SPEC)]
    found = build_check(replay, conn, results, steps={"s1": "not_built", "s3": "built"})
    assert found[0] == {"what": "step s1 not_built", "passed": True, "seen": "not_built (no acceptable spec after 3 attempts)"}
    assert found[1] == {"what": "step s3 built", "passed": False, "seen": "not handled"}


def test_a_step_that_was_not_handled(replay, conn):
    [found] = build_check(replay, conn, [result_of("s1", "not_built", reason=h.REASON_STOPPED)], steps={"s3": "kept"})
    assert found == {"what": "step s3 kept", "passed": False, "seen": "not handled"}


def test_an_added_step_is_shown_with_its_label(replay, conn):
    results = [result_of("added_1", "built", "yearly_cost")]
    [found] = build_check(replay, conn, results, steps={"added_1": "built"})
    assert found == {"what": "step added_1 (not in the brief) built", "passed": True, "seen": "built"}


def test_the_steps_come_in_the_order_of_the_object(replay, conn):
    results = [result_of("s1", "built"), result_of("s3", "built", "months_to_goal")]
    found = build_check(replay, conn, results, steps={"s3": "built", "s1": "built"})
    assert [c["what"] for c in found] == ["step s3 built", "step s1 built"]
