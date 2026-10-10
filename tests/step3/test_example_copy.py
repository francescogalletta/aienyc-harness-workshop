"""SPEC 6.2, "The copy": example mode works on a copy under my/var/examples/<name>/, made once by main()."""
import shutil

import pytest

import step3_helpers as s3
from step3_helpers import UNKNOWN_EXAMPLE, make_example, run_in

EXAMPLE_COPIED = ("Copied the example '{name}' to {folder}. What you change there stays there; "
                  "delete that folder to start the example again.")
PLAIN = {"HARNESS_EXAMPLE": "savings", "HARNESS_DB": None, "HARNESS_BRIEF_DIR": None, "HARNESS_MODULES_DIR": None}


@pytest.fixture
def cwd(tmp_path):
    """A working folder with the example `savings` (brief, two modules, scenarios and a data folder)."""
    folder = tmp_path / "cwd"
    example = make_example(folder / "examples", "savings")
    (example / "data").mkdir()
    (example / "data" / "bank.csv").write_text("x", encoding="utf-8")
    return folder


def files(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def command(cwd, *args, **env):
    return run_in(cwd, list(args), **{**PLAIN, **env})


def test_the_first_command_copies_the_brief_and_the_modules_and_says_so(cwd):
    result = command(cwd, "events")
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == EXAMPLE_COPIED.format(name="savings", folder="my/var/examples/savings")
    copy = cwd / "my" / "var" / "examples" / "savings"
    example = cwd / "examples" / "savings"
    assert files(copy / "brief") == files(example / "brief") and files(copy / "modules") == files(example / "modules")
    assert files(copy / "modules")                                     # there are module files to copy


def test_the_data_and_the_scenarios_are_not_copied(cwd):
    command(cwd, "events")
    copy = cwd / "my" / "var" / "examples" / "savings"
    assert not (copy / "data").exists() and not (copy / "scenarios").exists()


def test_the_example_itself_is_left_alone(cwd):
    before = files(cwd / "examples")
    command(cwd, "events")
    command(cwd, "modules")
    assert files(cwd / "examples") == before


def test_a_copy_that_exists_is_kept_as_it_is_and_nothing_is_said(cwd):
    command(cwd, "events")
    brief = cwd / "my" / "var" / "examples" / "savings" / "brief" / "domain_brief.json"
    brief.write_text("changed by the person", encoding="utf-8")
    (cwd / "examples" / "savings" / "brief" / "domain_brief.json").write_text("changed in the example", encoding="utf-8")
    again = command(cwd, "events")
    assert again.returncode == 0 and again.stderr == ""
    assert brief.read_text(encoding="utf-8") == "changed by the person"


def test_only_the_part_that_is_missing_is_copied(cwd):
    command(cwd, "events")
    copy = cwd / "my" / "var" / "examples" / "savings"
    shutil.rmtree(copy / "modules")
    (copy / "brief" / "domain_brief.json").write_text("mine", encoding="utf-8")
    again = command(cwd, "events")
    assert again.stderr.strip() == EXAMPLE_COPIED.format(name="savings", folder="my/var/examples/savings")
    assert (copy / "modules").is_dir() and (copy / "brief" / "domain_brief.json").read_text(encoding="utf-8") == "mine"


def test_pycache_folders_are_left_out(cwd):
    cache = cwd / "examples" / "savings" / "modules" / "monthly_surplus" / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-312.pyc").write_bytes(b"x")
    command(cwd, "events")
    copy = cwd / "my" / "var" / "examples" / "savings" / "modules"
    assert (copy / "monthly_surplus" / "module.py").is_file()
    assert not list(copy.rglob("__pycache__"))


def test_a_part_the_example_does_not_have_is_not_made(cwd):
    shutil.rmtree(cwd / "examples" / "savings" / "modules")
    command(cwd, "events")
    copy = cwd / "my" / "var" / "examples" / "savings"
    assert (copy / "brief").is_dir() and not (copy / "modules").exists()


def test_it_is_made_whatever_the_three_variables_say(cwd, tmp_path):
    result = command(cwd, "events", HARNESS_DB=tmp_path / "mine.db", HARNESS_BRIEF_DIR=tmp_path / "b",
                     HARNESS_MODULES_DIR=tmp_path / "m")
    assert result.returncode == 0, result.stderr
    assert (cwd / "my" / "var" / "examples" / "savings" / "brief").is_dir()
    assert (cwd / "my" / "var" / "examples" / "savings" / "modules").is_dir()


def test_an_unknown_example_makes_no_copy(cwd):
    result = command(cwd, "events", HARNESS_EXAMPLE="nope")
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="savings")
    assert not (cwd / "my").exists()


def test_adopt_registers_the_copy_and_builds_nothing_into_the_example(cwd):
    before = files(cwd / "examples")
    result = run_in(cwd, ["adopt"], s3.typed("yes"), **PLAIN)
    assert result.returncode == 0, result.stdout + result.stderr
    assert files(cwd / "examples") == before
    assert (cwd / "my" / "var" / "examples" / "savings" / "harness.db").is_file()
