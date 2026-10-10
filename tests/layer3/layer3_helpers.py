"""Helpers for the layer 3 tests: a small confirmed plan with two built modules, and scripted analyst turns."""
import copy
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "layer0"))      # state_shape, the state validator

from harness import db, replay  # noqa: E402
from harness.model import ScriptedModel  # noqa: E402

PROPOSED = {"kind": "proposed"}
SETTLE = 20


def item(text):
    return {"text": text, "origin": PROPOSED}


def small_plan() -> dict:
    """A confirmed plan: c1 and c2 are calculations with modules, c3 a calculation without one, j1 a judgment."""
    step = {"method": "arithmetic", "cadence": "", "origin": PROPOSED}
    return {
        "goal": item("Know the total"), "mode": "one_off",
        "scope": {"in": [item("Two amounts")], "out": [item("Taxes")]}, "glossary": [],
        "particulars": [{"what": "Amounts are in euros", "handling": "Say so", "step": "c1", "origin": PROPOSED}],
        "inputs": [{"name": "Amount A", "description": "the first", "origin": PROPOSED},
                   {"name": "Amount B", "description": "the second", "origin": PROPOSED}],
        "process": [
            {"id": "c1", "name": "Total", "kind": "calculation", "formula": "a + b", "needs": ["Amount A", "Amount B"],
             "produces": "total", **step},
            {"id": "c2", "name": "Double", "kind": "calculation", "formula": "total x 2", "needs": ["c1"],
             "produces": "double", **step},
            {"id": "c3", "name": "Tax", "kind": "calculation", "formula": "double x rate", "needs": ["c2"],
             "produces": "tax", **step},
            {"id": "j1", "name": "Is it enough?", "kind": "judgment", "method": "", "formula": "",
             "needs": ["c3"], "produces": "a decision", "cadence": "", "origin": PROPOSED}],
        "definition_of_done": [item("I know the total")], "open_questions": [],
        "meta": {"status": "confirmed", "written_at": "2026-10-10T00:00:00+00:00", "session_id": "x",
                 "lookups": [], "revisions": []},
    }


def number(name):
    return {"name": name, "type": "number", "description": f"the {name}"}


def module_files(name, step, spec_inputs, code, tests, examples, formula):
    spec = {"name": name, "description": formula, "step_id": step, "method": "arithmetic", "formula": formula,
            "inputs": spec_inputs, "output": {"type": "number", "description": f"the {name}"}}
    golden = [{**each, "checked_by": "second_pass"} for each in examples]
    return {"spec.json": json.dumps(spec), "golden.json": json.dumps(golden), "module.py": code, "tests.py": tests}


def example(inputs, expected):
    return {"inputs": {key: str(value) for key, value in inputs.items()}, "expected": str(expected),
            "working": f"worked out by hand: {expected}"}


TEST_HEAD = "from decimal import Decimal\nfrom module import calculate\n\n\n"
MODULES = {
    "total": module_files(
        "total", "c1", [number("a"), number("b")], "def calculate(a, b):\n    return a + b\n",
        TEST_HEAD + "def test_adds():\n    assert calculate(a=Decimal('1'), b=Decimal('2')) == Decimal('3')\n",
        [example({"a": 10, "b": 20}, 30), example({"a": 0, "b": 50}, 50), example({"a": 100, "b": 250}, 350)],
        "a + b"),
    "double": module_files(
        "double", "c2", [number("total")], "def calculate(total):\n    return total * 2\n",
        TEST_HEAD + "def test_doubles():\n    assert calculate(total=Decimal('4')) == Decimal('8')\n",
        [example({"total": 15}, 30), example({"total": 0}, 0), example({"total": 250}, 500)], "total x 2"),
}


def write_world(tmp_path, plan=None) -> dict:
    """Write the plan and the module folders; a session adopts the folders when it opens."""
    brief = tmp_path / "brief"
    brief.mkdir(parents=True, exist_ok=True)
    (brief / "domain_brief.json").write_text(json.dumps(plan or small_plan()), encoding="utf-8")
    for name, files in MODULES.items():
        folder = tmp_path / "modules" / name
        folder.mkdir(parents=True, exist_ok=True)
        for file, text in files.items():
            (folder / file).write_text(text, encoding="utf-8")
    return copy.deepcopy(plan or small_plan())


# --- Scripted turns ---

def call(tool, **arguments):
    return {"tool_calls": [{"name": tool, "arguments": arguments}]}


def run(module, inputs, assumptions=(), expected="about the sum"):
    return call("run_module", module=module, inputs={key: str(value) for key, value in inputs.items()},
                assumptions=list(assumptions), expected=expected)


def save(name, value, note="said by the person"):
    return call("save_input", name=name, value=str(value), note=note)


def reply(text):
    return {"text": text}


def say(session, text, step=None):
    applied, why = session.act("say", {"text": text, "step": step})
    assert applied, why
    return session.settle(SETTLE)


def events(session, kind):
    return [json.loads(row["payload"]) for row in db.list_events(session.conn, kind=kind)]


def assistant(state):
    """The assistant and harness messages of the chat."""
    return [message for message in state["chat"] if message["who"] != "you"]


def step_of(state, step_id):
    return next(step for step in state["steps"] if step["id"] == step_id)


# --- Replay: a scripted person on the small world ---

ASK = "what is 10 plus 20?"
TOTAL = [run("total", {"a": 10, "b": 20}), reply("The total is 30.")]
REFERENCE = Path(__file__).resolve().parents[2] / "reference" / "terms.json"


def point_replay_at(monkeypatch, tmp_path):
    """Replay's scratch folders and the researcher go to the test's own place."""
    monkeypatch.setattr(replay, "REPLAY_DIR", tmp_path / "replay")
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_REFERENCE", str(REFERENCE))


def world_folder(tmp_path):
    """A small example folder: c1, c2 with modules, c3 without, j1 a judgment."""
    folder = tmp_path / "ex"
    write_world(folder)
    return folder


def scenario(layer=4, **more):
    found = {"name": "s", "layer": layer, "kind": "ask", "lines": [ASK],
             "expect": {"runs": [{"module": "total", "inputs": {"a": "10", "b": "20"}}]}}
    found.update(more)
    return found


def play(found, example, script=(), **options):
    model = ScriptedModel(list(script))
    options.setdefault("write", lambda text: None)
    result = replay.run_scenario(found, example_dir=example, model_factory=lambda: model, **options)
    result["model"] = model
    return result
