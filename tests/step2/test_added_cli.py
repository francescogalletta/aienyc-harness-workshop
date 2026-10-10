"""SPEC 5.10: `build`, `modules` and `ask` with added steps, reserved ids and requests made in a conversation."""
import os
import sqlite3

import pytest

import step2_helpers as h
from step2_helpers import (ALL_BUILT, DRAFT_BRIEF, NEW_BLOCK, NEW_TEXTS, NO_STEP, REASON_SPEC, RESERVED_ID, SOME_MISSING,
                           built, make_brief, propose_spec, run_cli, say_text, yearly_script)

ADDED_LABEL = "added_1 (not in the brief)"
ADDED_HEADER = "Step added_1 (not in the brief): the cost over a whole year"
NO_CALCULATION_STEPS = "The brief has no calculation steps."


def typed(*answers):
    return "".join(answer + "\n" for answer in answers)


def database():
    return sqlite3.connect(os.environ["HARNESS_DB"])


@pytest.fixture
def brief_saved(save_confirmed_brief):
    return save_confirmed_brief(make_brief())


@pytest.fixture
def with_added_step(conn, brief_saved):
    """Both brief steps have a module, and the process has an added step with none."""
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    return h.add_new_step(conn)


# ---- build -------------------------------------------------------------------------------------

def test_build_builds_an_added_step_after_the_brief_steps(with_added_step, write_script):
    write_script(yearly_script())
    result = run_cli(["build"], typed(*built()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-4:] == [
        "s1 -> monthly_surplus (already built)", "s3 -> months_to_goal (already built)",
        f"{ADDED_LABEL} -> yearly_cost (built)", ALL_BUILT]
    assert ADDED_HEADER in result.stdout


def test_build_again_finds_the_added_step_already_built(with_added_step, write_script):
    write_script(yearly_script())
    run_cli(["build"], typed(*built()))
    write_script([])
    result = run_cli(["build"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-2:] == [f"{ADDED_LABEL} -> yearly_cost (already built)", ALL_BUILT]


def test_build_rebuilds_an_added_step_whose_module_changed(with_added_step, write_script, modules_dir):
    write_script(yearly_script())
    run_cli(["build"], typed(*built()))
    path = modules_dir / "yearly_cost" / "module.py"
    path.write_text("# edited\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    write_script(yearly_script())
    result = run_cli(["build"], typed(*built()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-2:] == [f"{ADDED_LABEL} -> yearly_cost (built)", ALL_BUILT]


def test_build_reports_an_added_step_that_could_not_be_built(with_added_step, write_script):
    bad = propose_spec(name="Bad Name")
    write_script([bad, bad, bad])
    result = run_cli(["build"])
    assert result.returncode == 1
    assert result.stdout.splitlines()[-2:] == [f"{ADDED_LABEL}: not built ({REASON_SPEC})", SOME_MISSING]


def test_a_brief_with_no_calculation_step_still_builds_an_added_step(save_confirmed_brief, conn, write_script):
    save_confirmed_brief(make_brief(process=[make_brief()["process"][1]]))
    h.add_new_step(conn)
    write_script(yearly_script())
    result = run_cli(["build"], typed(*built()))
    assert result.returncode == 0, result.stderr
    assert NO_CALCULATION_STEPS not in result.stdout
    assert result.stdout.splitlines()[-2:] == [f"{ADDED_LABEL} -> yearly_cost (built)", ALL_BUILT]


def test_rebuild_of_a_module_built_for_an_added_step(with_added_step, write_script, conn):
    h.install_yearly(conn)
    write_script(yearly_script())
    result = run_cli(["build", "--rebuild", "yearly_cost"], typed(*built()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == f"{ADDED_LABEL} -> yearly_cost (built)"
    assert ALL_BUILT not in result.stdout and SOME_MISSING not in result.stdout


def test_rebuild_of_a_module_whose_step_is_not_in_the_process(brief_saved, conn, write_script):
    h.install_surplus(conn, "old_step")
    write_script([])
    result = run_cli(["build", "--rebuild", "monthly_surplus"])
    assert result.returncode == 1 and result.stdout == ""
    assert NO_STEP.format(step="old_step", name="monthly_surplus") in result.stderr
    assert "Traceback" not in result.stderr


def test_build_refuses_a_brief_with_a_reserved_step_id(save_confirmed_brief, write_script):
    steps = [{**make_brief()["process"][0], "id": "added_1"}]
    save_confirmed_brief(make_brief(process=steps))
    write_script([])
    result = run_cli(["build"])
    assert result.returncode == 1 and result.stdout == ""
    assert RESERVED_ID.format(id="added_1") in result.stderr


# ---- modules -----------------------------------------------------------------------------------

def test_modules_marks_an_added_step_as_not_in_the_brief(conn):
    folder = h.install_yearly(conn)
    h.add_new_step(conn)
    result = run_cli(["modules"])
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [
        f"yearly_cost  steps: {ADDED_LABEL}  files: unchanged  tests: passed  "
        f"fingerprint: {h.expected_fingerprint(folder)[:12]}"]


def test_modules_marks_only_the_added_ids_of_a_module_with_several_steps(conn):
    h.install_surplus(conn, "s1")
    conn.execute("INSERT INTO step_modules (step_id, module) VALUES ('added_1', 'monthly_surplus')")
    conn.commit()
    [line] = run_cli(["modules"]).stdout.splitlines()
    steps = line.split("  steps: ")[1].split("  files: ")[0]
    assert sorted(steps.split(", ")) == sorted(["s1", ADDED_LABEL])


# ---- ask ---------------------------------------------------------------------------------------

@pytest.fixture
def ready(conn, brief_saved):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


def test_ask_refuses_a_brief_with_a_reserved_step_id_like_a_draft_one(save_confirmed_brief, conn, write_script):
    h.install_surplus(conn, "s1")
    steps = [{**make_brief()["process"][0], "id": "added_2"}]
    save_confirmed_brief(make_brief(process=steps))
    write_script([])
    result = run_cli(["ask", "Hi"])
    assert result.returncode == 1 and result.stdout == ""
    assert RESERVED_ID.format(id="added_2") in result.stderr
    assert DRAFT_BRIEF not in result.stderr


def test_a_build_asked_for_in_a_conversation_runs_in_the_terminal_and_prints_no_result_lines(ready, write_script):
    script = [h.no_findings(), h.request_module("new"), *yearly_script(), h.run_module("yearly_cost", {"monthly": "250"}),
              say_text("It comes to 3,000 a year.")]             # (step 5) the verifier checks the figures in the question first
    write_script(script)
    words = h.YEARLY_QUESTION.split()
    result = run_cli(["ask", *words], typed("yes", "yes", "/accept", "/accept", "/accept", "/quit"))
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "Ask about your plan. Type /quit to stop."
    assert NEW_BLOCK in result.stdout and ADDED_HEADER in result.stdout
    assert "It comes to 3,000 a year." in result.stdout
    assert "(built)" not in result.stdout and " -> " not in result.stdout
    assert ALL_BUILT not in result.stdout and SOME_MISSING not in result.stdout
    assert database().execute("SELECT id, name, session_id FROM added_steps").fetchall()[0][:2] == (1, NEW_TEXTS["works_out"])
    assert database().execute("SELECT module FROM step_modules WHERE step_id = 'added_1'").fetchall() == [("yearly_cost",)]


def test_the_build_inside_a_conversation_has_the_session_of_the_conversation(ready, write_script):
    write_script([h.request_module("new"), *yearly_script(), say_text("Done.")])
    run_cli(["ask", "Hi"], typed("yes", "yes", "/accept", "/accept", "/accept", "/quit"))
    sessions = {r[0] for r in database().execute(
        "SELECT session_id FROM events WHERE session_id != ?", (h.SESSION,))}      # not the fixtures' own session
    assert len(sessions) == 1
    kinds = {r[0] for r in database().execute("SELECT kind FROM events WHERE session_id != ?", (h.SESSION,))}
    assert {"ask.module_outcome", "calc.step_added", "calc.module_registered"} <= kinds
