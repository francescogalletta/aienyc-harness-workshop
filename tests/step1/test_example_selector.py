"""SPEC 4.8: `HARNESS_EXAMPLE` changes the defaults, `main()` checks the name before any command, and example mode
works on a copy of the example's brief under my/var/examples/<name>/, made once."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

UNKNOWN_EXAMPLE = "There is no example called '{name}'. The examples are: {names}."
EXAMPLE_COPIED = ("Copied the example '{name}' to {folder}. What you change there stays there; "
                  "delete that folder to start the example again.")
SETTINGS = ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE", "HARNESS_SCRIPT",
            "HARNESS_MODEL", "HARNESS_RESEARCHER", "HARNESS_REFERENCE")


def run(cwd, args, name="nope"):
    """Run the harness with `cwd` as the working folder, with an example selected and no path settings."""
    settings = {key: value for key, value in os.environ.items() if key not in SETTINGS}
    settings.update({"PYTHONPATH": str(ROOT), "HARNESS_MODEL_PROVIDER": "scripted", "HARNESS_EXAMPLE": name})
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=cwd, input="", capture_output=True,
                          text=True, env=settings, timeout=120)


def files(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture
def cwd(tmp_path):
    """A working folder with two examples that hold a brief, a folder that is not an example, and a plain file."""
    folder = tmp_path / "cwd"
    for name in ("wedding", "moving"):
        (folder / "examples" / name / "brief").mkdir(parents=True)
        (folder / "examples" / name / "brief" / "domain_brief.json").write_text("{}", encoding="utf-8")
    (folder / "examples" / "moving" / "data").mkdir()
    (folder / "examples" / "moving" / "data" / "bank.csv").write_text("x", encoding="utf-8")
    (folder / "examples" / "notes.txt").write_text("not an example", encoding="utf-8")
    return folder


# ---- the configuration --------------------------------------------------------------------------------


def test_an_example_changes_the_database_and_the_brief_defaults(monkeypatch):
    from harness.config import load_config
    for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    config = load_config()
    assert config.example == "moving"
    assert config.db_path == Path("my/var/examples/moving/harness.db")
    assert config.brief_dir == Path("my/var/examples/moving/brief")
    monkeypatch.setenv("HARNESS_BRIEF_DIR", "elsewhere")                    # a variable set explicitly still wins
    assert load_config().brief_dir == Path("elsewhere")


# ---- main() checks the name once, before any command -------------------------------------------------------------

def test_an_unknown_example_is_refused_with_the_known_names(cwd):
    result = run(cwd, ["events"])
    assert result.returncode == 1
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="moving, wedding")
    assert result.stdout == "" and "Traceback" not in result.stderr
    assert not (cwd / "my").exists()                                  # nothing ran


# ---- the copy --------------------------------------------------------------------------------------------

def test_the_first_command_copies_the_brief_says_so_and_keeps_its_database_under_var(cwd):
    result = run(cwd, ["events"], name="moving")
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == EXAMPLE_COPIED.format(name="moving", folder="my/var/examples/moving")
    copy = cwd / "my" / "var" / "examples" / "moving"
    assert files(copy / "brief") == files(cwd / "examples" / "moving" / "brief") and files(copy / "brief")
    assert not (copy / "data").exists()                               # the data is read where it is
    assert (copy / "harness.db").is_file() and not (cwd / "my" / "var" / "harness.db").exists()


def test_a_copy_that_exists_is_kept_as_it_is_and_nothing_is_said(cwd):
    run(cwd, ["events"], name="moving")
    brief = cwd / "my" / "var" / "examples" / "moving" / "brief" / "domain_brief.json"
    brief.write_text("changed by the person", encoding="utf-8")
    (cwd / "examples" / "moving" / "brief" / "domain_brief.json").write_text("changed in the example", encoding="utf-8")
    again = run(cwd, ["events"], name="moving")
    assert again.returncode == 0 and again.stderr == ""
    assert brief.read_text(encoding="utf-8") == "changed by the person"
