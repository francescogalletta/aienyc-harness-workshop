"""Helpers for the layer 2 tests: a small confirmed plan, and scripted model turns for a build."""
import copy
import json
from pathlib import Path

PROPOSED = {"kind": "proposed"}
SETTLE = 20


def item(text):
    return {"text": text, "origin": PROPOSED}


def small_plan(**changes) -> dict:
    """A confirmed plan of two calculation steps (c2 needs c1) and a judgment."""
    brief = {
        "goal": item("Know the total"), "mode": "one_off",
        "scope": {"in": [item("Two amounts")], "out": [item("Taxes")]},
        "glossary": [],
        "particulars": [{"what": "Amounts are in euros", "handling": "Say so", "step": "c1", "origin": PROPOSED}],
        "inputs": [{"name": "Amount A", "description": "the first", "origin": PROPOSED},
                   {"name": "Amount B", "description": "the second", "origin": PROPOSED}],
        "process": [
            {"id": "c1", "name": "Total", "kind": "calculation", "method": "arithmetic", "formula": "a + b",
             "needs": ["Amount A", "Amount B"], "produces": "total", "cadence": "", "origin": PROPOSED},
            {"id": "c2", "name": "Double", "kind": "calculation", "method": "arithmetic", "formula": "total x 2",
             "needs": ["c1"], "produces": "double", "cadence": "", "origin": PROPOSED},
            {"id": "j1", "name": "Is it enough?", "kind": "judgment", "method": "", "formula": "",
             "needs": ["c2"], "produces": "a decision", "cadence": "", "origin": PROPOSED}],
        "definition_of_done": [item("I know the total")],
        "open_questions": [],
        "meta": {"status": "confirmed", "written_at": "2026-10-10T00:00:00+00:00", "session_id": "x",
                 "lookups": [], "revisions": []},
    }
    brief.update(copy.deepcopy(changes))
    return brief


def write_plan(folder, brief=None) -> dict:
    brief = brief or small_plan()
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / "domain_brief.json").write_text(json.dumps(brief), encoding="utf-8")
    return brief


# --- The two calculations, as a model would write them ---

def number(name):
    return {"name": name, "type": "number", "description": f"the {name}"}


TOTAL_SPEC = {"name": "total", "description": "adds two amounts", "method": "arithmetic", "formula": "a + b",
              "inputs": [number("a"), number("b")], "output": {"type": "number", "description": "the total"}}
DOUBLE_SPEC = {"name": "double", "description": "doubles the total", "method": "arithmetic",
               "formula": "total x 2", "inputs": [number("total")],
               "output": {"type": "number", "description": "twice the total"}}
TOTAL_CODE = ("def calculate(a, b):\n    return a + b\n",
              "from decimal import Decimal\nfrom module import calculate\n\n\ndef test_adds():\n"
              "    assert calculate(a=Decimal('1'), b=Decimal('2')) == Decimal('3')\n")
WRONG_TOTAL_CODE = ("def calculate(a, b):\n    return a + b + 1\n",
                    "from decimal import Decimal\nfrom module import calculate\n\n\ndef test_runs():\n"
                    "    assert calculate(a=Decimal('1'), b=Decimal('1')) > 0\n")
DOUBLE_CODE = ("def calculate(total):\n    return total * 2\n",
               "from decimal import Decimal\nfrom module import calculate\n\n\ndef test_doubles():\n"
               "    assert calculate(total=Decimal('4')) == Decimal('8')\n")


def total_example(a, b, answer=None):
    answer = str(a + b) if answer is None else answer
    return {"inputs": {"a": str(a), "b": str(b)}, "expected": answer, "working": f"{a} + {b} = {answer}"}


def double_example(total):
    return {"inputs": {"total": str(total)}, "expected": str(total * 2), "working": f"{total} x 2 = {total * 2}"}


TOTAL_EXAMPLES = [total_example(10, 20), total_example(0, 50), total_example(100, 250)]
DOUBLE_EXAMPLES = [double_example(15), double_example(0), double_example(250)]


# --- Scripted turns ---

def call(tool, **arguments):
    return {"tool_calls": [{"name": tool, "arguments": arguments}]}


def spec_turn(spec, departures=()):
    return call("propose_spec", **spec, departures=list(departures))


def examples_turn(examples):
    return call("propose_examples", examples=examples)


def checker_turn(examples, start=1, answers=None):
    """The second pass: its own working and answer for each example; `answers` {n: answer} differ on purpose."""
    found = []
    for n, example in enumerate(examples, start=start):
        answer = (answers or {}).get(n, example["expected"])
        found.append({"n": n, "answer": answer, "working": f"{example['working']}; so {answer}"})
    return call("answer_examples", answers=found)


def code_turn(code):
    return call("write_module", module_py=code[0], tests_py=code[1])


def total_turns(departures=()):
    return [spec_turn(TOTAL_SPEC, departures), examples_turn(TOTAL_EXAMPLES), checker_turn(TOTAL_EXAMPLES),
            code_turn(TOTAL_CODE)]


def double_turns():
    return [spec_turn(DOUBLE_SPEC), examples_turn(DOUBLE_EXAMPLES), checker_turn(DOUBLE_EXAMPLES),
            code_turn(DOUBLE_CODE)]


def events(session, kind):
    from harness import db
    return [json.loads(row["payload"]) for row in db.list_events(session.conn, kind=kind)]


def step_of(state, step_id):
    return next(step for step in state["steps"] if step["id"] == step_id)
