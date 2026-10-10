"""SPEC 6.4 and 6.5: `check_scenario`, each expectation evaluated against what a session recorded."""

import pytest

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


@pytest.mark.parametrize("written, replied, seen", [
    ("4,600", "That is 4,583.33 a month.", False)])
def test_a_number_is_seen_at_the_precision_it_is_written_in_the_scenario(replay, conn, written, replied, seen):
    reply(conn, replied)
    [found] = check(replay, conn, shown=[written])
    assert found["passed"] is seen
    assert found["seen"] == ("in reply 1 of 1" if seen else "in none of 1 replies")


# ---- the limits ----------------------------------------------------------------------------------------------------------------------------

def withheld(conn, session=SESSION):
    record(conn, session, "ask.withheld", "harness", numbers=["1,234"], text="It is 1,234.")


def corrected(conn, reason="reply", session=SESSION):
    record(conn, session, "ask.correction", "harness", reason=reason, numbers=["1,234"], text="It is 1,234.")


@pytest.mark.parametrize("count, limit, passed", [(1, 1, True), (2, 1, False)])
def test_max_withheld(replay, conn, count, limit, passed):
    for _ in range(count):
        withheld(conn)
    [found] = check(replay, conn, max_withheld=limit)
    assert found == {"what": f"at most {limit} replies withheld", "passed": passed, "seen": f"{count} withheld"}


@pytest.mark.parametrize("count, limit, passed", [(3, 2, False)])
def test_max_corrections(replay, conn, count, limit, passed):
    for index in range(count):
        corrected(conn, ["reply", "run_module", "save_input", "request_module"][index % 4])
    [found] = check(replay, conn, max_corrections=limit)
    assert found == {"what": f"at most {limit} corrections", "passed": passed, "seen": f"{count} corrections"}


# ---- steps ----------------------------------------------------------------------------------------------------------------------------------

def result_of(step, outcome, module="monthly_surplus", reason=""):
    return {"step": step, "outcome": outcome, "module": module if outcome != "not_built" else None, "reason": reason}


def test_a_step_with_the_outcome_expected(replay, conn):
    results = [result_of("s1", "built"), result_of("s3", "kept", "months_to_goal")]
    found = build_check(replay, conn, results, steps={"s1": "built", "s3": "kept"})
    assert found == [{"what": "step s1 built", "passed": True, "seen": "built"},
                     {"what": "step s3 kept", "passed": True, "seen": "kept"}]
