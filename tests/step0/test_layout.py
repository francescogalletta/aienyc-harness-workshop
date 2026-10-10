"""SPEC 1 (rule 9) and 2: the layout. The harness never uses the teaching folder, and the fixtures are where the
layout says."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKSHOP = "work" + "shop"            # written in two pieces so that this file does not name the folder itself


def source_files(folder):
    return [path for path in (ROOT / folder).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".md", ".sql", ".json", ".html"}]


def test_the_harness_imports_nothing_from_the_teaching_folder():
    pattern = re.compile(rf"^\s*(import|from)\s+{WORKSHOP}\b", re.MULTILINE)
    offenders = [str(path.relative_to(ROOT)) for path in source_files("harness") if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == []


@pytest.mark.parametrize("folder", ["harness", "tests"])
def test_nothing_in_the_harness_or_the_tests_names_the_teaching_folder(folder):
    # The User-Agent of 4.2 has the word in it ("finance-harness-<word>/0.1"); that is not the folder.
    pattern = re.compile(rf"(?<![-\w]){WORKSHOP}[/\\]", re.IGNORECASE)
    offenders = [str(path.relative_to(ROOT)) for path in source_files(folder)
                 if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == []


def test_the_account_file_fixture_is_where_the_layout_says():
    fixture = ROOT / "tests" / "fixtures" / "accounts"
    assert (fixture / "generate.py").is_file() and (fixture / "FACILITATOR_KEY.md").is_file()
    assert (fixture / "example").is_dir()


def test_git_ignores_my_var():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(["git", "check-ignore", "-q", "my/var/harness.db"], cwd=ROOT)
    assert result.returncode == 0
