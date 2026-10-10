"""SPEC 5.10: `python -m harness build`, `modules` and `ask`, run as a person would run them."""
import os
import sqlite3

import pytest

import step2_helpers as h
from step2_helpers import (ALL_BUILT, CONFIRM_EXAMPLE, DRAFT_BRIEF, NO_BRIEF, NOT_REGISTERED, OPENING, PLAN_QUESTION, REASON_SPEC,
                           REASON_STOPPED, SOME_MISSING, built, make_brief, months_script, only_step,
                           propose_spec, reuse_module, run_cli, say_text, surplus_script)

NO_MODULES = "No modules are registered yet. Build them with: python -m harness build"
REBUILD_HINT = "Rebuild a module with: python -m harness build --rebuild NAME"
NO_BUILT_MODULES = "No modules are built yet. Build them first with: python -m harness build"
BUILD_LINES = ["s1 -> monthly_surplus (built)", "s3 -> months_to_goal (built)"]


def typed(*answers):
    return "".join(answer + "\n" for answer in answers)


def database():
    return sqlite3.connect(os.environ["HARNESS_DB"])


def module_names():
    return [r[0] for r in database().execute("SELECT name FROM modules ORDER BY name")]


@pytest.fixture
def brief_saved(save_confirmed_brief):
    return save_confirmed_brief(make_brief())


# ---- build -----------------------------------------------------------------------------------

def test_build_builds_every_calculation_step(brief_saved, write_script):
    write_script(surplus_script() + months_script())
    result = run_cli(["build"], typed(*built(2)))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-3:] == [*BUILD_LINES, ALL_BUILT]
    assert module_names() == ["monthly_surplus", "months_to_goal"]


def test_build_reports_a_step_that_could_not_be_built_and_goes_on(brief_saved, write_script):
    bad = propose_spec(name="Bad Name")
    write_script([bad, bad, bad, *months_script()])
    result = run_cli(["build"], typed(*built()))
    assert result.returncode == 1
    assert result.stdout.splitlines()[-3:] == [f"s1: not built ({REASON_SPEC})", BUILD_LINES[1], SOME_MISSING]


# ---- modules ---------------------------------------------------------------------------------


def test_modules_lists_each_with_a_fresh_test_run(conn):
    surplus, months = h.install_surplus(conn, "s1"), h.install_months(conn, "s3")
    result = run_cli(["modules"])
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [
        f"monthly_surplus  steps: s1  files: unchanged  tests: passed  fingerprint: {h.expected_fingerprint(surplus)[:12]}",
        f"months_to_goal  steps: s3  files: unchanged  tests: passed  fingerprint: {h.expected_fingerprint(months)[:12]}"]
    status = database().execute("SELECT module, passed FROM test_runs WHERE reason = 'status' ORDER BY id").fetchall()
    assert status == [("monthly_surplus", 1), ("months_to_goal", 1)]


# ---- ask -------------------------------------------------------------------------------------

@pytest.fixture
def ready(conn, brief_saved):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


def test_ask_prints_what_it_is_and_shows_the_reply(ready, write_script):
    write_script([say_text("It depends on your plan.")])
    result = run_cli(["ask", "What", "is", "left?"], typed("/quit"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "Ask about your plan. Type /quit to stop."
    assert "\nIt depends on your plan.\n\n> " in result.stdout


def test_ask_without_a_brief(write_script):
    write_script([])
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1 and NO_BRIEF in result.stderr


def test_ask_with_no_module_built_yet(brief_saved, write_script):
    write_script([])
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1 and NO_BUILT_MODULES in result.stderr
    assert result.stdout == ""


