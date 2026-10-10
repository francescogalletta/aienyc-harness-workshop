"""A small made-up project in a temporary folder: six steps, one package per layer, one test per step."""
import subprocess
from pathlib import Path

import pytest

from workshop import __main__ as cli
from workshop import tree

PACKAGES = ["grounding", "calc", "answers", "needs_you", "review"]


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def make_project(root):
    write(root, "harness/__init__.py", "")
    write(root, "harness/base.py", "BASE = 1\n")
    write(root, "tests/layer0/test_0.py", "def test_0():\n    import harness.base\n")
    steps = [{"step": 0, "principle": "the core", "package": None, "built": [], "given": [],
              "tests": "tests/layer0/", "run": "check"}]
    for k, pkg in enumerate(PACKAGES, start=1):
        for name in ("__init__.py", "layer.py", "work.py"):
            write(root, f"harness/{pkg}/{name}", f"X = {k}\n")
        write(root, f"harness/{pkg}/prompt.md", f"prompt {k}\n")
        write(root, f"tests/layer{k}/test_{k}.py", f"def test_{k}():\n    import harness.{pkg}.work\n")
        steps.append({"step": k, "principle": f"p{k}", "package": f"harness/{pkg}/",
                      "built": [f"harness/{pkg}/{n}" for n in ("__init__.py", "layer.py", "work.py")],
                      "given": [f"harness/{pkg}/prompt.md"], "tests": f"tests/layer{k}/", "run": "run"})
    return {"format": 2, "reference": None, "core": ["harness/__init__.py", "harness/base.py"], "steps": steps}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """(root, manifest) of the made-up project, a git checkout with everything committed."""
    root = tmp_path / "copy"
    manifest = make_project(root)
    write(root, "workshop/README.md", "guide\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "finished")
    monkeypatch.setattr(tree, "ROOT", root)
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.delenv("HARNESS_LAYERS", raising=False)
    return root, manifest
