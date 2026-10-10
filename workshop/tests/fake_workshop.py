"""A small fake workshop for the workshop's own tests: three steps, a handful of files, built in a temporary folder
with the same functions the tool uses to store a state. Nothing here reads the real manifest or states."""
import json
from pathlib import Path

from workshop import states

SPEC = "# Contract\n\n| Section | Status |\n| --- | --- |\n{rows}\n\n{sections}"


def spec(n):
    sections = "".join(f"## {k}. Section {k}\n\ntext\n\n" for k in range(1, n + 2))
    return SPEC.format(rows="| 1. One | Fixed |", sections=sections)


FINISHED = {                                    # the end of step 2
    "SPEC.md": spec(2),
    "harness/a.py": "A = 2\n",
    "harness/b.py": "B = 1\n",
    "harness/c.py": "C = 2\n",
    "harness/s.py": "S = 'done'\n",
    "harness/note.md": "a note\n",
    "tests/data/test_fix.py": "def test_fix():\n    assert True\n",
    "tests/step0/test_a.py": "from harness import a\n\n\ndef test_a():\n    assert a.A >= 0  # revised in step 2\n",
    "tests/step1/test_b.py": "from harness import b\n\n\ndef test_b():\n    assert b.B == 1\n",
    "tests/step2/test_c.py": "from harness import c, s\n\n\ndef test_c():\n    assert c.C == 2\n",
}
END1 = {**FINISHED, "SPEC.md": spec(1), "harness/a.py": "A = 1\n",
        "tests/step0/test_a.py": "from harness import a\n\n\ndef test_a():\n    assert a.A >= 0\n"}
for gone in ("harness/c.py", "harness/s.py", "tests/step2/test_c.py"):
    del END1[gone]
END0 = {**END1, "SPEC.md": spec(0), "harness/a.py": "A = 0\n"}
for gone in ("harness/b.py", "harness/note.md", "tests/step1/test_b.py"):
    del END0[gone]
START_S = "S = 'start'\n"

MANIFEST = {
    "format": 1,
    "roots": ["SPEC.md", "harness/", "tests/"],
    "always": ["tests/data/"],
    "steps": [
        {"step": 0, "name": "zero", "prompt": "workshop/prompts/p0.md", "tests": "tests/step0/",
         "built": ["harness/a.py"], "start": [], "changed": [],
         "given": ["SPEC.md", "tests/step0/", "tests/data/"], "red_at_start": {}},
        {"step": 1, "name": "one", "prompt": "workshop/prompts/p1.md", "tests": "tests/step1/",
         "built": ["harness/b.py"], "start": [], "changed": ["harness/a.py"],
         "given": ["SPEC.md", "tests/step1/", "harness/note.md"], "red_at_start": {}},
        {"step": 2, "name": "two", "prompt": "workshop/prompts/p2.md", "tests": "tests/step2/",
         "built": ["harness/c.py"], "start": ["harness/s.py"], "changed": ["harness/a.py"],
         "given": ["SPEC.md", "tests/step2/", "tests/step0/test_a.py"], "red_at_start": {}},
    ],
}
PROMPTS = {"p0": "Build harness/a.py.\n", "p1": "Build harness/b.py.\n", "p2": "Build harness/c.py and harness/s.py.\n"}
PYPROJECT = '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\n'


def write_tree(folder, tree):
    for path, text in tree.items():
        file = Path(folder) / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")


def make_workshop(root):
    """Write manifest, prompts and states under root/workshop, and a pyproject.toml. Returns the root."""
    root = Path(root)
    base = root / "workshop"
    (base / "prompts").mkdir(parents=True)
    (base / "manifest.json").write_text(states.dump_json(MANIFEST), encoding="utf-8")
    for name, text in PROMPTS.items():
        (base / "prompts" / f"{name}.md").write_text(text, encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    store = base / "states"
    for p, text in FINISHED.items():
        (store / "finished" / p).parent.mkdir(parents=True, exist_ok=True)
        (store / "finished" / p).write_text(text, encoding="utf-8")
    finished = {p: t.encode() for p, t in FINISHED.items()}
    for n, tree in ((0, END0), (1, END1)):
        states.write_overlay(store, n, {p: t.encode() for p, t in tree.items()}, finished)
    (store / "2-build" / "files" / "harness").mkdir(parents=True)
    (store / "2-build" / "files" / "harness" / "s.py").write_text(START_S, encoding="utf-8")
    return root


def put_state(root, name):
    """Make the working tree at root exactly the state `name`, with the tool's own functions."""
    data = states.load(root)
    states.apply(data, data.state_map(name), data.all_paths(), root)
    return data


def tree_of(root):
    data = states.load(root)
    return states.read_tree(root, data.roots())


def manifest_change(root, change):
    path = Path(root) / "workshop" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(states.dump_json(manifest), encoding="utf-8")
