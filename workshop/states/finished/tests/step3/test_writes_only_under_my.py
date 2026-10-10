"""SPEC 1, rule 8: with its default settings the harness writes only under my/, whatever the command."""
import json

import pytest

import step3_helpers as s3
from step3_helpers import ROOT, make_example, run_in, typed

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


def test_replay_writes_only_under_my(work, script):
    before = tree(work)
    result = cli(work, script(s3.ask_script()), ["replay", "savings", "--keep"])
    assert result.returncode == 0, result.stdout + result.stderr
    only_under_my(work, before)
    assert any(name.startswith("my/var/replay/savings-upfront-") for name in tree(work))
