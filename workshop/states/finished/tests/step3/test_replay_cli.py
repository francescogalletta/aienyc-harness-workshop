"""SPEC 6.7: `python -m harness replay EXAMPLE [SCENARIO] [--keep]`, run as a program in a folder with `examples/`."""

import pytest

import step3_helpers as s3
from step3_helpers import REPLAY_DONE, ask_script, h, run_in

SURPLUS_RUN = '{"income": "5000", "spending": "3000"}'
PASSING = [
    "Scenario upfront (ask)",
    f'  PASS  ran monthly_surplus with {{"income": "5000"}} (seen: run 1: {SURPLUS_RUN})',
    "  PASS  shows 2,000 (seen: in reply 1 of 1)",
    "  PASS  at most 0 replies withheld (seen: 0 withheld)",
    "  PASS  at most 0 corrections (seen: 0 corrections)",
]


@pytest.fixture
def replay_cli(tmp_path, write_script):
    """Run `replay` in the test's folder (where `examples/` is) with the given scripted model."""
    def run(*args, script=None, typed_text=""):
        write_script(ask_script() if script is None else script)
        return run_in(tmp_path, ["replay", *args], typed_text)
    return run


def lines(result):
    return result.stdout.splitlines()


def done(passed, total):
    return REPLAY_DONE.format(passed=passed, total=total)


# ---- the printed lines and the exit code ----------------------------------------------------------------------------

def test_a_passing_scenario_prints_its_checks_and_the_total(example, replay_cli):
    example()
    result = replay_cli("savings")
    assert lines(result) == [*PASSING, done(1, 1)] and result.returncode == 0 and result.stderr == ""


def test_a_module_that_is_not_adopted_is_an_error_line(example, replay_cli):
    example(modules={"monthly_surplus": {**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY},
                     "months_to_goal": h.months_files("s3")})
    result = replay_cli("savings")
    assert lines(result) == ["Scenario upfront (ask)", f"  ERROR  monthly_surplus was not adopted: {s3.REASON_TESTS}",
                             done(0, 1)]
    assert result.returncode == 1


def test_a_build_scenario_is_run_as_a_build(example, replay_cli):
    example(scenarios={"rebuild_one": s3.build_scenario("rebuild_one")})
    result = replay_cli("savings", script=h.surplus_script())
    assert lines(result) == ["Scenario rebuild_one (build)", f"  PASS  step {h.label('s1')} built (seen: built)",
                             f"  PASS  step {h.label('s3')} kept (seen: kept)", done(1, 1)]
    assert result.returncode == 0


# ---- --keep -------------------------------------------------------------------------------------------------------------


# ---- what is refused ----------------------------------------------------------------------------------------------------
