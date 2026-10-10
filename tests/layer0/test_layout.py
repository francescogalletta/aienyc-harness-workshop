"""SPEC 1 (rules 7, 9, 10 and 11): what the tree of the harness keeps to."""
import ast
import importlib
import re
import subprocess
from pathlib import Path

import pytest

from harness.config import load_config
from harness.layers import PACKAGES

ROOT = Path(__file__).resolve().parents[2]
WORKSHOP = "work" + "shop"            # in two pieces, so that this file does not name the folder itself
EXAMPLE = "wed" + "ding"


def source_files(folder, suffixes=(".py", ".md", ".sql", ".json", ".html")):
    return [path for path in (ROOT / folder).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in suffixes]


def test_the_harness_imports_nothing_from_the_teaching_folder():
    pattern = re.compile(rf"^\s*(import|from)\s+{WORKSHOP}\b", re.MULTILINE)
    offenders = [str(path.relative_to(ROOT)) for path in source_files("harness")
                 if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == []


@pytest.mark.parametrize("folder", ["harness", "tests"])
def test_nothing_in_the_harness_or_the_tests_names_the_teaching_folder(folder):
    pattern = re.compile(rf"(?<![-\w]){WORKSHOP}[/\\]", re.IGNORECASE)
    offenders = [str(path.relative_to(ROOT)) for path in source_files(folder)
                 if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == []


def test_nothing_under_the_harness_names_an_example_domain():
    offenders = [str(path.relative_to(ROOT)) for path in source_files("harness")
                 if EXAMPLE in path.read_text(encoding="utf-8").lower()]
    assert offenders == []


def test_the_default_places_the_harness_writes_are_under_my(monkeypatch):
    for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    config = load_config()
    for path in (config.db_path, config.brief_dir, config.modules_dir):
        assert path.parts[0] == "my"


def test_git_ignores_my_var():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    assert subprocess.run(["git", "check-ignore", "-q", "my/var/harness.db"], cwd=ROOT).returncode == 0


def test_there_is_no_migration_history():
    assert not (ROOT / "harness" / "migrations").exists()
    assert (ROOT / "harness" / "schema.sql").is_file()


def modules():
    return sorted(".".join(path.relative_to(ROOT).with_suffix("").parts) for path in source_files("harness", (".py",))
                  if path.name != "__main__.py" and path.name != "runner.py")   # runner.py runs on its own


@pytest.mark.parametrize("name", modules())
def test_every_module_of_the_harness_imports(name):
    importlib.import_module(name)


def imported_packages(path: Path) -> set[str]:
    """The harness packages a file imports, as top-level names under harness ('calc', 'core', ...)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = path.relative_to(ROOT / "harness").parts[:-1]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package[:len(package) - node.level + 1])
                target = base + (node.module.split(".") if node.module else [])
            elif node.module and node.module.startswith("harness."):
                target = node.module.split(".")[1:]
            else:
                continue
            if target:
                found.add(target[0])
            else:
                found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[1] for alias in node.names
                         if alias.name.startswith("harness."))
    return found


def test_a_layer_imports_no_layer_above_it():
    layer_of = {name.split(".")[1]: number for number, name in enumerate(PACKAGES, start=1)}
    offenders = []
    for package, number in layer_of.items():
        folder = ROOT / "harness" / package
        for path in folder.rglob("*.py") if folder.is_dir() else []:
            above = {name for name in imported_packages(path) if layer_of.get(name, 0) > number}
            if above:
                offenders.append(f"{path.relative_to(ROOT)} imports {sorted(above)}")
    assert offenders == []


def test_the_base_imports_no_layer():
    layers = {name.split(".")[1] for name in PACKAGES}
    offenders = [str(path.relative_to(ROOT)) for path in source_files("harness", (".py",))
                 if path.parent.name not in layers and imported_packages(path) & layers]
    assert offenders == []
