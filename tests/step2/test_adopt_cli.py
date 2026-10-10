"""SPEC 5.10: `python -m harness adopt`, run as a person would run it."""
import os
import sqlite3

import pytest

import step2_adopt_helpers as s3
import step2_helpers as h
from step2_adopt_helpers import (ADOPT_INTRO, ALL_ADOPTED, REASON_TESTS, SOME_NOT_ADOPTED, listing, typed)


def database():
    return sqlite3.connect(os.environ["HARNESS_DB"])


def adopt_cli(answers=()):
    return h.run_cli(["adopt"], typed(*answers))


@pytest.fixture
def brief_saved(save_confirmed_brief):
    return save_confirmed_brief()


@pytest.fixture
def folders(modules_dir):
    s3.surplus_folder(modules_dir)
    s3.months_folder(modules_dir)


# ---- the brief ------------------------------------------------------------------------------------------


# ---- nothing to adopt ---------------------------------------------------------------------------------------


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
