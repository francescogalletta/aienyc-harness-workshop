"""SPEC 5.10: `python -m harness build`, `modules` and `ask`, run as a person would run them."""
import os
import sqlite3

import pytest

import step2_helpers as h
from step2_helpers import (ALL_BUILT, CONFIRM_EXAMPLE, DRAFT_BRIEF, NO_BRIEF, NOT_REGISTERED, OPENING, REASON_SPEC,
                           REASON_STOPPED, SOME_MISSING, accepts, make_brief, months_script, only_step,
                           propose_examples, propose_spec, reuse_module, run_cli, say_text, surplus_script)

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
    result = run_cli(["build"], typed(*accepts(6)))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-3:] == [*BUILD_LINES, ALL_BUILT]
    assert module_names() == ["monthly_surplus", "months_to_goal"]


def test_build_asks_the_way_the_interview_does(brief_saved, write_script):
    write_script(surplus_script() + months_script())
    result = run_cli(["build"], typed(*accepts(6)))
    assert f"\n{CONFIRM_EXAMPLE}\n\n> " in result.stdout
    assert "Step s1: Work out the monthly surplus" in result.stdout


def test_build_again_finds_everything_already_built(brief_saved, write_script):
    write_script(surplus_script() + months_script())
    run_cli(["build"], typed(*accepts(6)))
    write_script([])                                             # no model call is needed now
    result = run_cli(["build"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-3:] == ["s1 -> monthly_surplus (already built)",
                                               "s3 -> months_to_goal (already built)", ALL_BUILT]


def test_build_says_when_a_module_is_reused(save_confirmed_brief, write_script, conn):
    save_confirmed_brief(only_step("s1"))
    h.install_surplus(conn, step_id="old_step")
    write_script([reuse_module("monthly_surplus")])
    result = run_cli(["build"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-2:] == ["s1 -> monthly_surplus (reused)", ALL_BUILT]


def test_build_reports_a_step_that_could_not_be_built_and_goes_on(brief_saved, write_script):
    bad = propose_spec(name="Bad Name")
    write_script([bad, bad, bad, *months_script()])
    result = run_cli(["build"], typed(*accepts(3)))
    assert result.returncode == 1
    assert result.stdout.splitlines()[-3:] == [f"s1: not built ({REASON_SPEC})", BUILD_LINES[1], SOME_MISSING]


def test_end_of_input_stops_the_build(brief_saved, write_script):
    write_script([propose_spec(), propose_examples()])
    result = run_cli(["build"], "")
    assert result.returncode == 1
    assert result.stdout.splitlines()[-2:] == [f"s1: not built ({REASON_STOPPED})", SOME_MISSING]
    assert module_names() == []


def test_a_brief_with_no_calculation_steps(save_confirmed_brief, write_script):
    save_confirmed_brief(make_brief(process=[make_brief()["process"][1]]))
    write_script([])
    result = run_cli(["build"])
    assert result.returncode == 0
    assert result.stdout.splitlines()[-1] == "The brief has no calculation steps."
    assert ALL_BUILT not in result.stdout and SOME_MISSING not in result.stdout


def test_build_without_a_brief(write_script):
    write_script([])
    result = run_cli(["build"])
    assert result.returncode == 1 and NO_BRIEF in result.stderr and "Traceback" not in result.stderr


def test_build_with_a_draft_brief(save_confirmed_brief, write_script):
    save_confirmed_brief(make_brief(), status="draft")
    write_script([])
    result = run_cli(["build"])
    assert result.returncode == 1 and DRAFT_BRIEF in result.stderr


def test_build_of_an_unknown_module(brief_saved, write_script):
    write_script([])
    result = run_cli(["build", "--rebuild", "ghost"])
    assert result.returncode == 1 and NOT_REGISTERED.format(name="ghost") in result.stderr
    assert "Traceback" not in result.stderr


def test_a_build_that_fails_stops_cleanly(brief_saved, write_script):
    write_script([])                                              # the first model call runs out of script
    result = run_cli(["build"])
    assert result.returncode == 1
    assert "build stopped: ScriptExhausted: " in result.stderr
    assert "Traceback" not in result.stderr and "\n" not in result.stderr.strip().split("build stopped: ")[-1]


def test_rebuild_of_one_module(brief_saved, write_script, conn):
    h.install_surplus(conn, step_id="s1")
    write_script(surplus_script())
    result = run_cli(["build", "--rebuild", "monthly_surplus"], typed(*accepts(3)))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "s1 -> monthly_surplus (built)"
    assert ALL_BUILT not in result.stdout and SOME_MISSING not in result.stdout


def test_a_rebuild_that_fails_exits_1(brief_saved, write_script, conn):
    h.install_surplus(conn, step_id="s1")
    write_script([propose_spec(description="")] * 3)
    result = run_cli(["build", "--rebuild", "monthly_surplus"])
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1] == f"s1: not built ({REASON_SPEC})"
    assert ALL_BUILT not in result.stdout and SOME_MISSING not in result.stdout


def test_each_command_makes_a_new_session_and_migrates_first(brief_saved, write_script):
    write_script(surplus_script() + months_script())
    run_cli(["build"], typed(*accepts(6)))
    write_script(surplus_script())
    run_cli(["build", "--rebuild", "monthly_surplus"], typed(*accepts(3)))
    sessions = [r[0] for r in database().execute("SELECT DISTINCT session_id FROM events WHERE kind LIKE 'calc.%'")]
    assert len(sessions) == 2


# ---- modules ---------------------------------------------------------------------------------

def test_modules_with_nothing_registered():
    result = run_cli(["modules"])
    assert result.returncode == 0 and result.stdout.strip() == NO_MODULES


def test_modules_lists_each_with_a_fresh_test_run(conn):
    surplus, months = h.install_surplus(conn, "s1"), h.install_months(conn, "s3")
    result = run_cli(["modules"])
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [
        f"monthly_surplus  steps: s1  files: unchanged  tests: passed  fingerprint: {h.expected_fingerprint(surplus)[:12]}",
        f"months_to_goal  steps: s3  files: unchanged  tests: passed  fingerprint: {h.expected_fingerprint(months)[:12]}"]
    status = database().execute("SELECT module, passed FROM test_runs WHERE reason = 'status' ORDER BY id").fetchall()
    assert status == [("monthly_surplus", 1), ("months_to_goal", 1)]


def test_modules_shows_every_step_of_a_module_or_a_dash(conn):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    conn.execute("INSERT INTO step_modules (step_id, module) VALUES ('s9', 'monthly_surplus')")
    conn.execute("DELETE FROM step_modules WHERE module = 'months_to_goal'")
    conn.commit()
    lines = run_cli(["modules"]).stdout.splitlines()
    assert lines[0].startswith("monthly_surplus  steps: s1, s9  files: ")
    assert lines[1].startswith("months_to_goal  steps: -  files: ")


def test_modules_with_a_changed_file_asks_for_a_rebuild(conn, modules_dir):
    folder = h.install_surplus(conn, "s1")
    registered = h.expected_fingerprint(folder)
    (folder / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")       # still correct
    result = run_cli(["modules"])
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f"monthly_surplus  steps: s1  files: changed  tests: passed  fingerprint: {registered[:12]}", REBUILD_HINT]


def test_modules_with_failing_tests(conn):
    folder = h.install_surplus(conn, "s1")
    (folder / "module.py").write_text(h.WRONG_SURPLUS_PY, encoding="utf-8")
    result = run_cli(["modules"])
    assert result.returncode == 1
    assert "files: changed  tests: failed" in result.stdout and result.stdout.splitlines()[-1] == REBUILD_HINT
    assert database().execute("SELECT passed FROM test_runs WHERE reason = 'status'").fetchall() == [(0,)]


def test_modules_with_a_missing_file(conn):
    folder = h.install_surplus(conn, "s1")
    (folder / "tests.py").unlink()
    result = run_cli(["modules"])
    assert result.returncode == 1
    assert "files: missing  tests: failed" in result.stdout and result.stdout.splitlines()[-1] == REBUILD_HINT


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


def test_ask_joins_the_words_of_the_question(ready, write_script):
    write_script([h.run_module(), say_text("monthly_surplus gives 2,000.")])
    result = run_cli(["ask", "I", "earn", "5000", "and", "spend", "3000."], typed("/quit"))
    assert result.returncode == 0, result.stderr
    assert "monthly_surplus gives 2,000." in result.stdout
    assert database().execute("SELECT module, output FROM calc_runs").fetchall() == [("monthly_surplus", '"2000"')]


def test_ask_without_a_question_asks_for_one(ready, write_script):
    write_script([])
    result = run_cli(["ask"], "")                                 # the end of input counts as /quit
    assert result.returncode == 0, result.stderr
    assert OPENING in result.stdout


def test_ask_makes_a_session_of_its_own(ready, write_script):
    write_script([say_text("Hello."), say_text("Hello again.")])
    run_cli(["ask", "Hi"], typed("Again", "/quit"))
    sessions = {r[0] for r in database().execute("SELECT session_id FROM events WHERE kind LIKE 'ask.%'")}
    assert len(sessions) == 1


def test_ask_without_a_brief(write_script):
    write_script([])
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1 and NO_BRIEF in result.stderr


def test_ask_with_a_draft_brief(save_confirmed_brief, write_script):
    save_confirmed_brief(make_brief(), status="draft")
    write_script([])
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1 and DRAFT_BRIEF in result.stderr
    assert result.stdout == ""                                    # the greeting comes after the checks


def test_ask_with_no_module_built_yet(brief_saved, write_script):
    write_script([])
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1 and NO_BUILT_MODULES in result.stderr
    assert result.stdout == ""


def test_ask_that_fails_stops_cleanly(ready, write_script):
    write_script([])                                              # the first model call runs out of script
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1
    assert "ask stopped: ScriptExhausted: " in result.stderr and "Traceback" not in result.stderr
