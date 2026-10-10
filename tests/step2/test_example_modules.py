"""SPEC 4.8 and 5.13: in example mode the modules folder is a copy of the example's, and `adopt` registers it."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import step2_adopt_helpers as a
import step2_helpers as h
from harness.grounding import save_brief

ROOT = h.ROOT
SETTINGS = ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE", "HARNESS_SCRIPT")


def run(cwd, args, typed_text=""):
    env = {key: value for key, value in os.environ.items() if key not in SETTINGS}
    env.update({"PYTHONPATH": str(ROOT), "HARNESS_EXAMPLE": "savings"})
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=cwd, input=typed_text, capture_output=True,
                          text=True, env=env, timeout=180)


def files(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_the_modules_default_follows_the_example(monkeypatch):
    from harness.config import load_config
    for name in ("HARNESS_MODULES_DIR", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_EXAMPLE", "moving")
    assert load_config().modules_dir == Path("my/var/examples/moving/modules")


def test_adopt_in_example_mode_registers_a_copy_of_the_example_s_modules(tmp_path):
    cwd = tmp_path / "cwd"
    example = cwd / "examples" / "savings"
    save_brief(h.make_brief(), example / "brief", {"status": "confirmed", "session_id": "s", "lookups": []})
    a.surplus_folder(example / "modules")
    a.months_folder(example / "modules")
    before = files(example)
    result = run(cwd, ["adopt"], a.typed("yes"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == a.ALL_ADOPTED
    copy = cwd / "my" / "var" / "examples" / "savings"
    assert files(copy / "modules") == files(example / "modules") and files(copy / "modules")
    names = [row[0] for row in sqlite3.connect(copy / "harness.db").execute("SELECT name FROM modules ORDER BY name")]
    assert names == ["monthly_surplus", "months_to_goal"]
    assert files(example) == before                                   # the example itself is never written
