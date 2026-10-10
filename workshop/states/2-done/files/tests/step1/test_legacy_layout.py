"""SPEC 4.5, "An older copy": brief/ or modules/ at the top and nothing in my/ gives LEGACY_LAYOUT and exit 1."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

LEGACY_COMMANDS = ("ground", "ui", "build", "modules", "ask", "adopt", "work")
LEGACY_LAYOUT = ("This copy has brief/ or modules/ at the top, but the harness now keeps them in my/. "
                 "Move each one you have: mkdir -p my && git mv brief my/brief && git mv modules my/modules "
                 "(plain mv if they are not committed). Then run the command again.")
AVAILABLE = ('ground', 'ui', 'build', 'modules', 'ask')           # the commands of LEGACY_COMMANDS that this step has
PROBE = "modules"                           # one of them, to see whether the check lets a command through
SETTINGS = ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE", "HARNESS_SCRIPT",
            "HARNESS_MODEL", "HARNESS_RESEARCHER", "HARNESS_REFERENCE")


def run(cwd, args, **env):
    """Run the harness with `cwd` as the working folder and none of the path settings unless `env` gives them."""
    settings = {key: value for key, value in os.environ.items() if key not in SETTINGS}
    settings.update({"PYTHONPATH": str(ROOT), "HARNESS_MODEL_PROVIDER": "scripted"})
    settings.update({key: str(value) for key, value in env.items()})
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=cwd, input="", capture_output=True,
                          text=True, env=settings, timeout=120)


def everything(folder):
    return sorted(str(path.relative_to(folder)) for path in Path(folder).rglob("*") if "__pycache__" not in path.parts)


@pytest.fixture
def old_copy(tmp_path):
    """A working folder as an older copy left it: brief/ and modules/ at the top, nothing else."""
    (tmp_path / "brief").mkdir()
    (tmp_path / "brief" / "domain_brief.json").write_text("{}", encoding="utf-8")
    (tmp_path / "modules").mkdir()
    return tmp_path


def test_the_commands_and_the_message_are_those_of_the_spec():
    sys.path.insert(0, str(ROOT))
    from harness import __main__ as main
    assert main.LEGACY_COMMANDS == LEGACY_COMMANDS
    assert main.LEGACY_LAYOUT == LEGACY_LAYOUT


@pytest.mark.parametrize("command", AVAILABLE)
def test_every_command_that_needs_them_prints_the_message_and_stops(old_copy, command):
    before = everything(old_copy)
    result = run(old_copy, [command])
    assert result.returncode == 1
    assert result.stderr.strip() == LEGACY_LAYOUT and result.stdout == ""
    assert everything(old_copy) == before                  # no database opened, nothing moved or made


@pytest.mark.parametrize("folder", ["brief", "modules"])
def test_either_folder_alone_is_enough(tmp_path, folder):
    (tmp_path / folder).mkdir()
    result = run(tmp_path, [PROBE])
    assert result.returncode == 1 and result.stderr.strip() == LEGACY_LAYOUT


@pytest.mark.parametrize("args", [["check"], ["events"]])
def test_check_and_events_never_make_the_check(old_copy, args):
    result = run(old_copy, args)
    assert LEGACY_LAYOUT not in result.stderr and LEGACY_LAYOUT not in result.stdout


@pytest.mark.parametrize("args", [["decisions"], ["replay", "nope"], ["data", "list"]])
def test_commands_that_are_not_in_the_list_do_not_make_it(old_copy, args):
    result = run(old_copy, args)
    assert LEGACY_LAYOUT not in result.stderr and LEGACY_LAYOUT not in result.stdout


def test_the_arguments_are_parsed_first(old_copy):
    result = run(old_copy, ["build", "--no-such-option"])
    assert result.returncode == 2 and LEGACY_LAYOUT not in result.stderr


@pytest.mark.parametrize("present", ["my/brief", "my/modules"])
def test_either_folder_in_my_means_it_is_not_an_older_copy(old_copy, present):
    (old_copy / present).mkdir(parents=True)
    result = run(old_copy, [PROBE])
    assert result.returncode == 0, result.stderr
    assert LEGACY_LAYOUT not in result.stderr


@pytest.mark.parametrize("setting", ["HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR"])
def test_a_folder_variable_means_it_is_not_an_older_copy(old_copy, setting):
    result = run(old_copy, [PROBE], **{setting: old_copy / "elsewhere"})
    assert result.returncode == 0, result.stderr
    assert LEGACY_LAYOUT not in result.stderr


def test_an_example_means_it_is_not_an_older_copy(old_copy):
    (old_copy / "examples" / "demo").mkdir(parents=True)
    result = run(old_copy, [PROBE], HARNESS_EXAMPLE="demo")
    assert result.returncode == 0, result.stderr
    assert LEGACY_LAYOUT not in result.stderr


@pytest.mark.parametrize("setting", ["HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE"])
def test_an_empty_variable_counts_as_unset(old_copy, setting):
    result = run(old_copy, [PROBE], **{setting: ""})
    assert result.returncode == 1 and result.stderr.strip() == LEGACY_LAYOUT


def test_a_file_called_brief_is_not_a_folder(tmp_path):
    (tmp_path / "brief").write_text("not a folder", encoding="utf-8")
    result = run(tmp_path, [PROBE])
    assert result.returncode == 0, result.stderr
    assert LEGACY_LAYOUT not in result.stderr


def test_nothing_at_the_top_is_a_fresh_start(tmp_path):
    result = run(tmp_path, [PROBE])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "my" / "var" / "harness.db").is_file()
