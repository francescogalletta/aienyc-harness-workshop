"""SPEC 6.2, "The copy": example mode works on a copy under my/var/examples/<name>/, made once by main()."""

import pytest

from step3_helpers import make_example, run_in

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


def test_a_copy_that_exists_is_kept_as_it_is_and_nothing_is_said(cwd):
    command(cwd, "events")
    brief = cwd / "my" / "var" / "examples" / "savings" / "brief" / "domain_brief.json"
    brief.write_text("changed by the person", encoding="utf-8")
    (cwd / "examples" / "savings" / "brief" / "domain_brief.json").write_text("changed in the example", encoding="utf-8")
    again = command(cwd, "events")
    assert again.returncode == 0 and again.stderr == ""
    assert brief.read_text(encoding="utf-8") == "changed by the person"
