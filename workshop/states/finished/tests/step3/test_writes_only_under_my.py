"""SPEC 1, rule 8: with its default settings the harness writes only under my/, whatever the command."""
import json
import shutil
import sqlite3

import pytest

import step3_helpers as s3
from step3_helpers import ROOT, h, make_example, run_in, save_the_brief, typed

NO_SETTINGS = {"HARNESS_DB": None, "HARNESS_BRIEF_DIR": None, "HARNESS_MODULES_DIR": None, "HARNESS_EXAMPLE": None,
               "HARNESS_RESEARCHER": "reference", "HARNESS_REFERENCE": ROOT / "reference" / "terms.json"}


@pytest.fixture
def work(tmp_path):
    """A working folder with one seeded example, as a person's copy of the repository would have."""
    folder = tmp_path / "work"
    make_example(folder / "examples", "savings")
    return folder


@pytest.fixture
def script(tmp_path):
    """Write the scripted model's replies; the file is outside the working folder."""
    def write(entries):
        (tmp_path / "model.json").write_text(json.dumps(entries), encoding="utf-8")
        return tmp_path / "model.json"
    return write


def tree(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def cli(work, script_file, args, answers=()):
    return run_in(work, args, typed(*answers), HARNESS_MODEL_PROVIDER="scripted", HARNESS_SCRIPT=script_file,
                  **NO_SETTINGS)


def only_under_my(work, before):
    after = tree(work)
    changed = {name for name in after if before.get(name) != after[name]} | (set(before) - set(after))
    assert changed and all(name.startswith("my/") for name in changed), sorted(changed)


def test_build_writes_only_under_my(work, script):
    save_the_brief(work / "my" / "brief")
    before = tree(work)
    result = cli(work, script([*h.surplus_script(), *h.months_script()]), ["build"], [*s3.BUILD_LINES, *s3.BUILD_LINES])
    assert result.returncode == 0, result.stdout + result.stderr
    only_under_my(work, before)
    assert (work / "my" / "modules" / "monthly_surplus" / "module.py").is_file()
    assert (work / "my" / "var" / "harness.db").is_file()


def test_adopt_and_ask_write_only_under_my(work, script):
    save_the_brief(work / "my" / "brief")
    h.write_files(work / "my" / "modules" / "monthly_surplus", h.surplus_files("s1"))
    before = tree(work)
    adopted = cli(work, script([]), ["adopt"], ["yes"])
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    only_under_my(work, before)
    before = tree(work)
    asked = cli(work, script([h.no_findings(), *s3.ask_script()]), ["ask", *s3.ASK_QUESTION.split()], ["/quit"])
    assert asked.returncode == 0, asked.stdout + asked.stderr
    assert "You have 2,000 left each month." in asked.stdout
    only_under_my(work, before)


def test_replay_writes_only_under_my(work, script):
    before = tree(work)
    result = cli(work, script(s3.ask_script()), ["replay", "savings", "--keep"])
    assert result.returncode == 0, result.stdout + result.stderr
    only_under_my(work, before)
    assert any(name.startswith("my/var/replay/savings-upfront-") for name in tree(work))


def test_replay_without_keep_leaves_nothing_but_the_folder_it_made(work, script):
    before = tree(work)
    cli(work, script(s3.ask_script()), ["replay", "savings"])
    after = tree(work)
    assert all(name.startswith("my/") for name in set(after) ^ set(before))


def test_example_mode_writes_only_under_my(work, script):
    before = tree(work)
    result = run_in(work, ["adopt"], typed("yes"), **{**NO_SETTINGS, "HARNESS_EXAMPLE": "savings",
                                                      "HARNESS_MODEL_PROVIDER": "scripted",
                                                      "HARNESS_SCRIPT": script([])})
    assert result.returncode == 0, result.stdout + result.stderr
    only_under_my(work, before)
    assert tree(work / "examples") == {k.removeprefix("examples/"): v for k, v in before.items()
                                       if k.startswith("examples/")}


def test_the_interview_keeps_its_state_under_my_var(work, script):
    before = tree(work)
    result = cli(work, script([]), ["ground"], ["I want to stay on top of my money."])
    assert result.returncode == 1
    only_under_my(work, before)
    assert (work / "my" / "var" / "grounding_state.json").is_file()
    assert sqlite3.connect(work / "my" / "var" / "harness.db").execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 1
