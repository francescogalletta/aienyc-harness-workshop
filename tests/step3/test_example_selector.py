"""SPEC 6.2: `HARNESS_EXAMPLE` changes three defaults, and `main()` checks the name before any command."""
import sqlite3
from pathlib import Path

import pytest

import step3_helpers as s3
from step3_helpers import UNKNOWN_EXAMPLE, h, make_example, run_in, typed

DEFAULTED = ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")


@pytest.fixture
def plain(monkeypatch):
    """No harness path setting at all, so that the defaults show."""
    for name in (*DEFAULTED, "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)


# ---- the configuration --------------------------------------------------------------------------------

def test_the_examples_folder_is_a_relative_path():
    from harness.config import EXAMPLES_DIR
    assert EXAMPLES_DIR == Path("examples") and not EXAMPLES_DIR.is_absolute()


def test_without_an_example_the_defaults_are_the_old_ones(plain):
    from harness.config import load_config
    config = load_config()
    assert config.example is None
    assert (config.db_path, config.brief_dir, config.modules_dir) == (
        Path("var/harness.db"), Path("brief"), Path("modules"))


def test_an_example_changes_the_three_defaults(plain, monkeypatch):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    config = load_config()
    assert config.example == "moving"
    assert config.db_path == Path("var/examples/moving/harness.db")
    assert config.brief_dir == Path("examples/moving/brief")
    assert config.modules_dir == Path("examples/moving/modules")
    assert isinstance(config.db_path, Path) and isinstance(config.brief_dir, Path)


@pytest.mark.parametrize("setting, field, value", [
    ("HARNESS_DB", "db_path", "elsewhere.db"),
    ("HARNESS_BRIEF_DIR", "brief_dir", "elsewhere_brief"),
    ("HARNESS_MODULES_DIR", "modules_dir", "elsewhere_modules")])
def test_a_variable_set_explicitly_still_wins_and_only_for_its_own_field(plain, monkeypatch, setting, field, value):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    monkeypatch.setenv(setting, value)
    config = load_config()
    assert getattr(config, field) == Path(value)
    expected = {"db_path": Path("var/examples/moving/harness.db"), "brief_dir": Path("examples/moving/brief"),
                "modules_dir": Path("examples/moving/modules")}
    for other, default in expected.items():
        if other != field:
            assert getattr(config, other) == default


def test_all_three_explicit_variables_win_together(plain, monkeypatch, tmp_path):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    for name, folder in zip(DEFAULTED, ("a.db", "b", "c")):
        monkeypatch.setenv(name, str(tmp_path / folder))
    config = load_config()
    assert (config.db_path, config.brief_dir, config.modules_dir) == (tmp_path / "a.db", tmp_path / "b", tmp_path / "c")
    assert config.example == "moving"


@pytest.mark.parametrize("setting", DEFAULTED)
def test_an_empty_variable_counts_as_unset(plain, monkeypatch, setting):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    monkeypatch.setenv(setting, "")
    config = load_config()
    assert config.db_path == Path("var/examples/moving/harness.db") and config.modules_dir == Path("examples/moving/modules")
    assert config.brief_dir == Path("examples/moving/brief")


def test_an_empty_example_counts_as_unset(plain, monkeypatch):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "")
    config = load_config()
    assert config.example is None and config.db_path == Path("var/harness.db")


@pytest.mark.parametrize("name", ["no such example", "Bad-Name", "../up", "9lives"])
def test_load_config_does_not_check_the_name(plain, monkeypatch, name):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", name)
    config = load_config()
    assert config.example == name
    assert config.brief_dir == Path("examples") / name / "brief"


def test_the_example_is_read_on_every_call(plain, monkeypatch):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "one")
    assert load_config().modules_dir == Path("examples/one/modules")
    monkeypatch.setenv("HARNESS_EXAMPLE", "two")
    assert load_config().modules_dir == Path("examples/two/modules")
    monkeypatch.delenv("HARNESS_EXAMPLE")
    assert load_config().modules_dir == Path("modules")


def test_other_settings_are_not_touched_by_an_example(plain, monkeypatch):
    from harness.config import load_config
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.delenv("HARNESS_SCRIPT", raising=False)
    config = load_config()
    assert (config.model_provider, config.model_name, config.script_path) == ("scripted", "claude-sonnet-5-5", None)
    assert config.reference_path == Path("reference/terms.json")


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
    assert not (cwd / "var").exists()                                 # nothing ran


@pytest.mark.parametrize("args", [["check"], ["events"], ["modules"], ["adopt"], ["build"], ["ask", "Hi"],
                                  ["ground"], ["replay", "moving"]])
def test_every_command_is_checked(cwd, args):
    result = selected(cwd, args)
    assert result.returncode == 1 and result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="moving, wedding")
    assert result.stdout == ""


@pytest.mark.parametrize("args", [["ui", "--port", "0", "--no-browser"], ["work", "--port", "0", "--no-browser"]])
def test_the_servers_are_checked_before_they_start(cwd, args):
    result = selected(cwd, args, timeout=60)
    assert result.returncode == 1 and result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="moving, wedding")


def test_the_names_are_the_folders_of_the_examples_folder_sorted(cwd):
    (cwd / "examples" / "alpha").mkdir()
    result = selected(cwd, ["events"])
    assert result.stderr.strip().endswith("The examples are: alpha, moving, wedding.")


def test_a_name_with_no_folder_is_refused_even_when_a_file_has_that_name(cwd):
    (cwd / "examples" / "plainfile").write_text("not a folder", encoding="utf-8")
    result = selected(cwd, ["events"], name="plainfile")
    assert result.returncode == 1
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="plainfile", names="moving, wedding")


def test_a_name_that_does_not_fit_the_pattern_is_refused_even_when_the_folder_exists(cwd):
    (cwd / "examples" / "Bad-Name").mkdir()
    result = selected(cwd, ["events"], name="Bad-Name")
    assert result.returncode == 1
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="Bad-Name", names="Bad-Name, moving, wedding")


def test_no_examples_folder_gives_none(tmp_path):
    folder = tmp_path / "bare"
    folder.mkdir()
    result = selected(folder, ["events"])
    assert result.returncode == 1
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="(none)")
    assert result.stderr.strip().endswith("The examples are: (none).")


def test_an_empty_examples_folder_gives_none(tmp_path):
    (tmp_path / "bare" / "examples").mkdir(parents=True)
    result = selected(tmp_path / "bare", ["events"])
    assert result.stderr.strip().endswith("The examples are: (none).")


def test_a_known_example_runs_the_command_and_keeps_its_database_under_var(cwd):
    result = selected(cwd, ["events"], name="moving")
    assert result.returncode == 0, result.stderr
    assert (cwd / "var" / "examples" / "moving" / "harness.db").is_file()
    assert not (cwd / "var" / "harness.db").exists()


def test_an_empty_example_name_means_no_example(cwd):
    result = selected(cwd, ["events"], name="")
    assert result.returncode == 0, result.stderr
    assert (cwd / "var" / "harness.db").is_file()


def test_an_explicit_database_wins_over_the_example(cwd, tmp_path):
    result = selected(cwd, ["events"], name="moving", HARNESS_DB=tmp_path / "mine.db")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "mine.db").is_file() and not (cwd / "var").exists()


# ---- playing with an example --------------------------------------------------------------------------------------

def test_adopt_then_ask_play_with_the_example_and_keep_the_database(tmp_path, write_script):
    cwd = tmp_path / "play"
    folder = make_example(cwd / "examples", "savings")
    before = {p.relative_to(folder): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}

    adopted = selected(cwd, ["adopt"], name="savings", typed_text=typed("yes"))
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    assert adopted.stdout.splitlines()[-1] == s3.ALL_ADOPTED
    database = cwd / "var" / "examples" / "savings" / "harness.db"
    assert database.is_file()

    again = selected(cwd, ["adopt"], name="savings")                   # the database is kept between runs
    assert again.returncode == 0 and again.stdout.strip() == s3.NOTHING_TO_ADOPT

    listed = selected(cwd, ["modules"], name="savings")
    assert listed.returncode == 0, listed.stdout
    assert [line.split("  ")[0] for line in listed.stdout.splitlines()] == ["monthly_surplus", "months_to_goal"]

    write_script(s3.ask_script())
    asked = selected(cwd, ["ask", *s3.ASK_QUESTION.split()], name="savings", typed_text=typed("/quit"))
    assert asked.returncode == 0, asked.stderr
    assert "You have 2,000 left each month." in asked.stdout
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT module FROM calc_runs").fetchall() == [("monthly_surplus",)]
    connection.close()

    after = {p.relative_to(folder): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}
    assert after == before                                              # files are not copied, and none were written
