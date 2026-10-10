"""SPEC 6.2: `HARNESS_EXAMPLE` changes three defaults, and `main()` checks the name before any command."""
from pathlib import Path

import pytest

from step3_helpers import UNKNOWN_EXAMPLE, run_in

DEFAULTED = ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")


@pytest.fixture
def plain(monkeypatch):
    """No harness path setting at all, so that the defaults show."""
    for name in (*DEFAULTED, "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)


# ---- the configuration --------------------------------------------------------------------------------


def test_an_example_changes_the_three_defaults(plain, monkeypatch):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    config = load_config()
    assert config.example == "moving"
    assert config.db_path == Path("my/var/examples/moving/harness.db")
    assert config.brief_dir == Path("my/var/examples/moving/brief")
    assert config.modules_dir == Path("my/var/examples/moving/modules")
    assert isinstance(config.db_path, Path) and isinstance(config.brief_dir, Path)


# ---- main() checks the name once, before any command -------------------------------------------------------------

@pytest.fixture
def cwd(tmp_path):
    """A working folder with an examples folder that holds two real folders and a plain file."""
    folder = tmp_path / "cwd"
    (folder / "examples" / "wedding").mkdir(parents=True)
    (folder / "examples" / "moving").mkdir()
    (folder / "examples" / "notes.txt").write_text("not an example", encoding="utf-8")
    return folder


def selected(cwd, args, name="nope", typed_text="", timeout=180, **env):
    settings = {"HARNESS_EXAMPLE": name, "HARNESS_DB": None, "HARNESS_BRIEF_DIR": None, "HARNESS_MODULES_DIR": None}
    return run_in(cwd, args, typed_text, timeout=timeout, **{**settings, **env})


def test_an_unknown_example_is_refused_with_the_known_names(cwd):
    result = selected(cwd, ["events"])
    assert result.returncode == 1
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="moving, wedding")
    assert result.stderr.strip() == "There is no example called 'nope'. The examples are: moving, wedding."
    assert result.stdout == "" and "Traceback" not in result.stderr
    assert not (cwd / "my").exists()                                  # nothing ran


def test_a_known_example_runs_the_command_and_keeps_its_database_under_var(cwd):
    result = selected(cwd, ["events"], name="moving")
    assert result.returncode == 0, result.stderr
    assert (cwd / "my" / "var" / "examples" / "moving" / "harness.db").is_file()
    assert not (cwd / "my" / "var" / "harness.db").exists()


# ---- playing with an example --------------------------------------------------------------------------------------
