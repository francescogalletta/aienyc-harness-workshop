"""SPEC 4.5, "An older copy": brief/ at the top and nothing in my/ gives LEGACY_LAYOUT and exit 1.
And SPEC 2: a command run in a fresh folder writes only under my/."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

LEGACY_LAYOUT = ("This copy has brief/ or modules/ at the top, but the harness now keeps them in my/. "
                 "Move each one you have: mkdir -p my && git mv brief my/brief && git mv modules my/modules "
                 "(plain mv if they are not committed). Then run the command again.")
SETTINGS = ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE", "HARNESS_SCRIPT",
            "HARNESS_MODEL", "HARNESS_RESEARCHER", "HARNESS_REFERENCE")


def test_the_brief_default_is_under_my(monkeypatch):
    """SPEC 2, 4.1: the brief defaults to a place under my/."""
    from harness.config import load_config
    for name in ("HARNESS_BRIEF_DIR", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    assert load_config().brief_dir == Path("my/brief")


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
    """A working folder as an older copy left it: brief/ at the top, nothing in my/."""
    (tmp_path / "brief").mkdir()
    (tmp_path / "brief" / "domain_brief.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_an_older_copy_gets_the_message_and_nothing_is_touched(old_copy):
    before = everything(old_copy)
    result = run(old_copy, ["ground"])
    assert result.returncode == 1
    assert result.stderr.strip() == LEGACY_LAYOUT and result.stdout == ""
    assert everything(old_copy) == before                  # no database opened, nothing moved or made


def test_check_and_events_still_work_in_an_older_copy(old_copy):
    for args in (["check"], ["events"]):
        result = run(old_copy, args)
        assert LEGACY_LAYOUT not in result.stderr and LEGACY_LAYOUT not in result.stdout


def test_a_copy_with_my_is_not_an_older_copy(old_copy):
    (old_copy / "my" / "brief").mkdir(parents=True)
    result = run(old_copy, ["ground", "--resume"])
    assert LEGACY_LAYOUT not in result.stderr


def test_a_fresh_folder_gets_its_files_only_under_my(tmp_path):
    result = run(tmp_path, ["check"])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "my" / "var" / "harness.db").is_file()
    assert [path.name for path in tmp_path.iterdir() if path.name != "__pycache__"] == ["my"]
