"""SPEC 6.7: `python -m harness adopt`, run as a person would run it."""
import os
import sqlite3

import pytest

import step3_helpers as s3
from step3_helpers import (ADOPT_INTRO, ADOPT_QUESTION, ALL_ADOPTED, NOTHING_TO_ADOPT, REASON_DECLINED, REASON_TESTS,
                           SOME_NOT_ADOPTED, ROOT, h, listing, run_in, typed)


def database():
    return sqlite3.connect(os.environ["HARNESS_DB"])


def adopt_cli(answers=(), **env):
    return run_in(ROOT, ["adopt"], typed(*answers), **env)


@pytest.fixture
def brief_saved(save_confirmed_brief):
    return save_confirmed_brief()


@pytest.fixture
def folders(modules_dir):
    s3.surplus_folder(modules_dir)
    s3.months_folder(modules_dir)


# ---- the brief ------------------------------------------------------------------------------------------

def test_without_a_brief(modules_dir):
    s3.surplus_folder(modules_dir)
    result = adopt_cli()
    assert result.returncode == 1 and h.NO_BRIEF in result.stderr and "Traceback" not in result.stderr
    assert result.stdout == ""


def test_without_a_brief_and_without_modules_it_still_needs_the_brief():
    result = adopt_cli()
    assert result.returncode == 1 and h.NO_BRIEF in result.stderr


def test_with_a_draft_brief(save_confirmed_brief, folders):
    save_confirmed_brief(status="draft")
    result = adopt_cli()
    assert result.returncode == 1 and h.DRAFT_BRIEF in result.stderr and result.stdout == ""


def test_with_a_reserved_step_id(save_confirmed_brief, folders):
    steps = [{**h.make_brief()["process"][0], "id": "added_1"}]
    save_confirmed_brief(h.make_brief(process=steps))
    result = adopt_cli()
    assert result.returncode == 1 and h.RESERVED_ID.format(id="added_1") in result.stderr and result.stdout == ""


# ---- nothing to adopt ---------------------------------------------------------------------------------------

def test_with_no_modules_folder(brief_saved):
    result = adopt_cli()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == NOTHING_TO_ADOPT == "Every module folder is already registered."


def test_with_every_folder_registered(brief_saved, conn):
    h.install_surplus(conn, "s1")
    result = adopt_cli()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == NOTHING_TO_ADOPT


def test_it_migrates_first(brief_saved):
    adopt_cli()
    names = [r[0] for r in database().execute("SELECT name FROM schema_migrations")]
    assert "0001_init.sql" in names and "0005_added_steps.sql" in names


# ---- adopting -----------------------------------------------------------------------------------------------------

def test_yes_adopts_every_folder_and_says_so(brief_saved, folders):
    result = adopt_cli(["yes"])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == ADOPT_INTRO
    assert lines[1:3] == [listing("monthly_surplus", "s1"), listing("months_to_goal", "s3")]
    assert "monthly_surplus -> s1 (adopted)" in result.stdout and "months_to_goal -> s3 (adopted)" in result.stdout
    assert lines[-1] == ALL_ADOPTED == "Every module folder is registered now."
    assert [r[0] for r in database().execute("SELECT name FROM modules ORDER BY name")] == [
        "monthly_surplus", "months_to_goal"]


def test_the_question_is_asked_the_way_build_asks(brief_saved, folders):
    result = adopt_cli(["yes"])
    assert f"\n{ADOPT_QUESTION}\n\n> " in result.stdout


def test_the_adopted_modules_are_listed_as_working_afterwards(brief_saved, folders):
    adopt_cli(["yes"])
    listed = h.run_cli(["modules"])
    assert listed.returncode == 0, listed.stdout
    assert "files: unchanged  tests: passed" in listed.stdout and len(listed.stdout.splitlines()) == 2


@pytest.mark.parametrize("answers", [["no"], ["/quit"], ["yes please"], []])
def test_anything_but_an_accept_word_adopts_nothing_and_exits_1(brief_saved, folders, answers):
    result = adopt_cli(answers)                       # no answer at all is the end of input, which counts as /quit
    assert result.returncode == 1, result.stdout
    lines = result.stdout.splitlines()
    assert lines[-1] == SOME_NOT_ADOPTED
    assert "monthly_surplus: not adopted (you did not accept the worked examples)" in result.stdout
    assert "months_to_goal: not adopted (you did not accept the worked examples)" in result.stdout
    assert database().execute("SELECT COUNT(*) FROM modules").fetchone() == (0,)
    assert database().execute("SELECT COUNT(*) FROM test_runs").fetchone() == (0,)


def test_one_folder_that_fails_gives_exit_1_and_the_others_are_adopted(brief_saved, modules_dir):
    s3.surplus_folder(modules_dir, module_py=h.WRONG_SURPLUS_PY)
    s3.months_folder(modules_dir)
    result = adopt_cli(["yes"])
    assert result.returncode == 1
    assert f"monthly_surplus: not adopted ({REASON_TESTS})" in result.stdout
    assert "months_to_goal -> s3 (adopted)" in result.stdout
    assert result.stdout.splitlines()[-1] == SOME_NOT_ADOPTED == (
        "Some module folders are not registered. Fix them, or rebuild their steps with: python -m harness build")
    assert [r[0] for r in database().execute("SELECT name FROM modules")] == ["months_to_goal"]


def test_a_folder_refused_by_a_check_gives_exit_1_without_a_question(brief_saved, modules_dir):
    h.write_files(modules_dir / "incomplete", {"module.py": "x = 1\n"})
    result = adopt_cli()
    assert result.returncode == 1
    assert "incomplete: not adopted (missing files: spec.json, golden.json, tests.py)" in result.stdout
    assert ADOPT_QUESTION not in result.stdout and result.stdout.splitlines()[-1] == SOME_NOT_ADOPTED


def test_no_model_is_used(brief_saved, folders):
    result = adopt_cli(["yes"], HARNESS_MODEL_PROVIDER="no_such_provider", HARNESS_SCRIPT=None)
    assert result.returncode == 0, result.stderr


def test_each_run_has_a_session_of_its_own(brief_saved, folders, modules_dir):
    adopt_cli(["yes"])
    sessions = {r[0] for r in database().execute("SELECT session_id FROM events")}
    assert len(sessions) == 1
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    adopt_cli(["yes"])
    sessions = {r[0] for r in database().execute("SELECT session_id FROM events")}
    assert len(sessions) == 2


def test_the_decision_is_the_persons_and_the_tests_are_adopt_runs(brief_saved, folders):
    adopt_cli(["yes"])
    kinds = database().execute("SELECT kind, actor FROM events ORDER BY id").fetchall()
    assert kinds[0] == ("calc.adopt_decision", "person")
    assert set(database().execute("SELECT reason FROM test_runs").fetchall()) == {("adopt",)}


def test_a_changed_module_is_adopted_again(brief_saved, folders, modules_dir):
    adopt_cli(["yes"])
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    result = adopt_cli(["yes"])
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines()[1] == listing("monthly_surplus", "s1")
    assert "months_to_goal" not in result.stdout


def test_an_added_step_comes_back_with_its_module(brief_saved, conn, modules_dir, write_script):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    s3.yearly_folder(modules_dir, "added_2")
    result = adopt_cli(["yes"])
    assert result.returncode == 0, result.stderr
    assert "yearly_cost -> added_2 (not in the brief) (adopted)" in result.stdout
    assert database().execute("SELECT id FROM added_steps").fetchall() == [(2,)]
    write_script([])                                        # no model call is needed now
    built = h.run_cli(["build"])
    assert built.returncode == 0, built.stderr
    assert "added_2 (not in the brief) -> yearly_cost (already built)" in built.stdout.splitlines()
