"""Shared by the step 2 tests: a small brief, two example modules, script builders and a recording person.

The example is a savings goal. Step s1 works out the monthly surplus, s2 is a judgment, s3 works out
how many months it takes to reach a target. The strings below are copied from SPEC 5.6, 5.7 and 5.9
on purpose: the tests check the harness against the contract, not against its own constants.
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALC = ROOT / "harness" / "calc"
SESSION = "test-session"

# ---- fixed strings (SPEC 5.6, 5.7, 5.9, 5.10) -------------------------------------------------

NOT_REGISTERED = "There is no registered module called '{name}'."
FILES_CHANGED = ("The files of '{name}' are not the ones that passed their tests. "
                 "Rebuild it with: python -m harness build --rebuild {name}")
NO_EXPECTATION = ("Before running '{name}', give the assumptions (a list of sentences, which may be empty) "
                  "and say what you expect the result to be.")
BAD_INPUTS = "The inputs do not fit '{name}': {problems}"
TESTS_FAIL = "The tests of '{name}' do not pass right now, so it will not run."
RUN_FAILED = "'{name}' stopped with an error: {error}"

NO_BRIEF = "There is no brief yet. Write one with: python -m harness ground"
DRAFT_BRIEF = "The brief is still a draft. Confirm it first with: python -m harness ground"
STEP_HEADER = "Step {id}: {name}"
USE_TOOL = "[harness] Reply only by calling {tools}."
ONE_CALL = "Only one tool call is handled per reply. This one was ignored."
SPEC_REJECTED = "The spec was not accepted. Fix these and propose it again:"
NAME_TAKEN = "a module called '{name}' already exists: reuse it, or choose another name"
CANNOT_REUSE = "There is no registered module called '{name}' with unchanged files. Propose a spec instead."
EXAMPLES_REJECTED = "The examples were not accepted. Fix these and propose them again:"
EXAMPLES_INTRO = "Check these worked examples for {name}: {description} Your answers become the check its code must pass."
CONFIRM_EXAMPLE = ("Type /accept if the answer is right, type the right answer, or type /skip to leave this "
                   "example out. /quit stops the build.")
NOT_A_VALUE = "That could not be read as {kind}. Type /accept, the right answer, or /skip."
CODE_REJECTED = "The code was not accepted. Fix these and write both files again:"
RUNNING_TESTS = "  (running the tests)"
TESTS_FAILED = "The code was run and did not pass. Fix it and write both files again:"
EXAMPLE_FAILED = "Example {index} failed. Its inputs were: {inputs}"
EXAMPLES_DISAGREE = ("The code and these worked examples disagree. One of them is wrong. Check each by hand: "
                     "if the example was wrong, run the build again and type the right answer.")
DISAGREEMENT = "  With {inputs} you confirmed {expected}, and the code gives {got}."
REASON_SPEC = "no acceptable spec after 3 attempts"
REASON_EXAMPLES = "no acceptable examples after 3 attempts"
REASON_CONFIRMED = "fewer than 2 examples were confirmed"
REASON_CODE = "the code did not pass after 3 attempts"
REASON_STOPPED = "stopped by the person"
KIND_WORDS = {"number": "a number", "integer": "a whole number", "date": "a date (YYYY-MM-DD)",
              "boolean": "yes or no", "text": "text", "list": "a JSON list", "object": "a JSON object"}

OPENING = "What would you like to work out?"
NUMBERS_CORRECTION = ("[harness] Your reply was not shown. These numbers did not come from a module result in this "
                      "conversation, a saved input, the brief or the person's own words: {numbers}. Do not work "
                      "numbers out yourself: run a module, or leave the number out. Then reply again.")
WITHHELD = "(The answer was held back, because it contained numbers that no tested module produced: {numbers}.)"
WITHHELD_NOTE = ("[harness] Your last reply was not shown to the person, because it contained numbers that no "
                 "module produced: {numbers}.")
INPUTS_UNBACKED = ("These numbers did not come from the person, the brief, a saved input or a module result: "
                   "{numbers}. Ask the person, or run the module that produces them.")
EMPTY_REPLY = "[harness] Your reply was empty. Ask the person for what you need, or give your answer."
TOO_MANY = "(The harness stopped working on this, because it took too many steps. Try asking in a simpler way.)"
BAD_NAME = "The name must be in snake_case, such as monthly_income."
EMPTY_VALUE = "The value is empty."
SAVED = "Saved."

ALL_BUILT = "Every calculation step has a tested module."
SOME_MISSING = ("Some calculation steps have no tested module yet. "
                "Run python -m harness build again to carry on.")

# ---- the tool input schemas of SPEC 5.7 and 5.9, without the prose a schema may add -------------

_TEXT = {"type": "string"}
_TYPE = {"type": "string", "enum": ["number", "integer", "date", "text", "boolean", "list", "object"]}
SPEC_SCHEMA = {"type": "object", "properties": {
    "name": _TEXT, "description": _TEXT, "method": _TEXT, "formula": _TEXT,
    "inputs": {"type": "array", "items": {"type": "object", "properties": {
        "name": _TEXT, "type": _TYPE, "description": _TEXT}, "required": ["name", "type", "description"]}},
    "output": {"type": "object", "properties": {"type": _TYPE, "description": _TEXT},
               "required": ["type", "description"]}},
    "required": ["name", "description", "method", "formula", "inputs", "output"]}
REUSE_SCHEMA = {"type": "object", "properties": {"module": _TEXT, "reason": _TEXT},
                "required": ["module", "reason"]}
EXAMPLES_SCHEMA = {"type": "object", "properties": {"examples": {"type": "array", "items": {
    "type": "object", "properties": {"inputs": {"type": "object"}, "expected": {}, "working": _TEXT},
    "required": ["inputs", "expected", "working"]}}}, "required": ["examples"]}
CODE_SCHEMA = {"type": "object", "properties": {"module_py": _TEXT, "tests_py": _TEXT},
               "required": ["module_py", "tests_py"]}
RUN_MODULE_SCHEMA = {"type": "object", "properties": {
    "module": {"type": "string"}, "inputs": {"type": "object"},
    "assumptions": {"type": "array", "items": {"type": "string"}}, "expected": {"type": "string"}},
    "required": ["module", "inputs", "assumptions", "expected"]}
SAVE_INPUT_SCHEMA = {"type": "object", "properties": {
    "name": {"type": "string"}, "value": {"type": "string"}, "note": {"type": "string"}},
    "required": ["name", "value", "note"]}


def without_descriptions(schema):
    """A schema with the prose `description` of each node removed (the contract lets a schema add them)."""
    if isinstance(schema, list):
        return [without_descriptions(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key == "description" and isinstance(value, str):
            continue
        if key == "properties" and isinstance(value, dict):
            result[key] = {name: without_descriptions(sub) for name, sub in value.items()}
        else:
            result[key] = without_descriptions(value)
    return result


# ---- the brief ---------------------------------------------------------------------------------

GOAL = "Build an emergency fund without touching long-term savings."
PARTICULAR = "Rent is fixed at 1,150 a month"


def make_brief(**changes):
    """A confirmed brief, as `load_brief` returns it: two calculation steps and one judgment."""
    brief = {
        "goal": GOAL,
        "mode": "ongoing",
        "scope": {"in": ["Monthly income and spending"], "out": ["Investing"]},
        "glossary": [{"term": "Emergency fund", "definition": "Money kept aside for surprises."}],
        "particulars": [{"what": PARTICULAR, "handling": "Count it as spending"}],
        "inputs": [{"name": "Monthly income", "description": "What comes in each month"},
                   {"name": "Monthly spending", "description": "What goes out each month"},
                   {"name": "Savings target", "description": "How much the fund should hold"}],
        "process": [
            {"id": "s1", "name": "Work out the monthly surplus", "kind": "calculation",
             "method": "arithmetic", "formula": "surplus = income - spending",
             "needs": ["Monthly income", "Monthly spending"], "produces": "Surplus per month"},
            {"id": "s2", "name": "Decide how much to set aside", "kind": "judgment",
             "needs": ["s1"], "produces": "Amount set aside each month"},
            {"id": "s3", "name": "Work out the months to reach the target", "kind": "calculation",
             "method": "arithmetic", "formula": "months = target / monthly saving, rounded up",
             "needs": ["s2", "Savings target"], "produces": "Months to the target"},
        ],
        "definition_of_done": ["I know how many months the fund takes."],
        "open_questions": [],
    }
    brief.update(changes)
    return brief


def only_step(step_id, brief=None):
    """The brief with a single calculation step kept (and the judgment step dropped)."""
    brief = brief or make_brief()
    return {**brief, "process": [step for step in brief["process"] if step["id"] == step_id]}


# ---- two example modules ----------------------------------------------------------------------

def surplus_spec(**changes):
    """What the model sends to `propose_spec` for step s1."""
    spec = {
        "name": "monthly_surplus",
        "description": "The money left over each month after spending.",
        "method": "arithmetic",
        "formula": "surplus = income - spending",
        "inputs": [{"name": "income", "type": "number", "description": "Money in each month."},
                   {"name": "spending", "type": "number", "description": "Money out each month."}],
        "output": {"type": "number", "description": "The surplus per month."},
    }
    spec.update(changes)
    return spec


def months_spec(**changes):
    """What the model sends to `propose_spec` for step s3."""
    spec = {
        "name": "months_to_goal",
        "description": "The whole months needed to save a target amount.",
        "method": "arithmetic",
        "formula": "months = target / monthly_saving, rounded up",
        "inputs": [{"name": "target", "type": "number", "description": "The amount to reach."},
                   {"name": "monthly_saving", "type": "number", "description": "Amount saved each month."}],
        "output": {"type": "integer", "description": "The number of months."},
    }
    spec.update(changes)
    return spec


def saved_spec(spec, step_id):
    """The spec as it is written to spec.json: the seven keys, in order."""
    return {"name": spec["name"], "description": spec["description"], "step_id": step_id,
            "method": spec["method"], "formula": spec["formula"],
            "inputs": spec["inputs"], "output": spec["output"]}


def surplus_examples():
    return [
        {"inputs": {"income": "5123.45", "spending": "3100.10"}, "expected": "2023.35",
         "working": "5123.45 less 3100.10 leaves 2023.35"},
        {"inputs": {"income": "4000", "spending": "4500"}, "expected": "-500",
         "working": "4000 less 4500 is a shortfall of 500"},
        {"inputs": {"income": "3000", "spending": "3000"}, "expected": "0",
         "working": "equal amounts leave nothing"},
    ]


def months_examples():
    return [
        {"inputs": {"target": "12000", "monthly_saving": "1000"}, "expected": "12", "working": "12000 over 1000"},
        {"inputs": {"target": "10000", "monthly_saving": "300"}, "expected": "34", "working": "33.3 rounded up"},
        {"inputs": {"target": "500", "monthly_saving": "500"}, "expected": "1", "working": "one month covers it"},
    ]


SURPLUS_PY = """\
def calculate(income, spending):
    return income - spending
"""

SURPLUS_TESTS = """\
from decimal import Decimal

from module import calculate


def test_a_surplus():
    assert calculate(Decimal("5000"), Decimal("3000")) == Decimal("2000")


def test_a_shortfall():
    assert calculate(Decimal("100"), Decimal("250")) == Decimal("-150")
"""

WRONG_SURPLUS_PY = """\
def calculate(income, spending):
    return income + spending
"""

# Passes its own tests, but its tests agree with the wrong answer: only the worked examples can catch it.
WRONG_SURPLUS_TESTS = """\
from decimal import Decimal

from module import calculate


def test_adds():
    assert calculate(Decimal("1"), Decimal("1")) == Decimal("2")
"""

RAISING_SURPLUS_PY = """\
def calculate(income, spending):
    if spending > income:
        raise ValueError("spending is above income")
    return income - spending
"""

RAISING_SURPLUS_TESTS = """\
from decimal import Decimal

from module import calculate


def test_a_surplus():
    assert calculate(Decimal("5000"), Decimal("3000")) == Decimal("2000")
"""

MONTHS_PY = """\
import math


def calculate(target, monthly_saving):
    if monthly_saving <= 0:
        raise ValueError("monthly_saving must be above zero")
    return math.ceil(target / monthly_saving)
"""

MONTHS_TESTS = """\
from decimal import Decimal

from module import calculate


def test_exact_months():
    assert calculate(Decimal("1000"), Decimal("250")) == 4


def test_part_months_round_up():
    assert calculate(Decimal("1000"), Decimal("300")) == 4
"""

# Right for every input except a saving of exactly 1, where it never finishes.
SLOW_MONTHS_PY = """\
import math


def calculate(target, monthly_saving):
    if monthly_saving == 1:
        for _ in range(10 ** 12):
            pass
    return math.ceil(target / monthly_saving)
"""


def golden_of(examples, decisions=None):
    """golden.json as the builder writes it: the confirmed examples, each with its decision."""
    decisions = decisions or ["accepted"] * len(examples)
    return [{"inputs": e["inputs"], "expected": e["expected"], "working": e["working"], "decision": d}
            for e, d in zip(examples, decisions)]


# ---- module folders ----------------------------------------------------------------------------

def dump(value):
    """How spec.json and golden.json are written (SPEC 5.4)."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def surplus_files(step_id="s1", module_py=SURPLUS_PY, tests_py=SURPLUS_TESTS):
    return {"spec.json": dump(saved_spec(surplus_spec(), step_id)),
            "golden.json": dump(golden_of(surplus_examples())),
            "module.py": module_py, "tests.py": tests_py}


def months_files(step_id="s3", module_py=MONTHS_PY, tests_py=MONTHS_TESTS):
    return {"spec.json": dump(saved_spec(months_spec(), step_id)),
            "golden.json": dump(golden_of(months_examples())),
            "module.py": module_py, "tests.py": tests_py}


def write_files(folder, files):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def expected_fingerprint(folder):
    """The fingerprint of SPEC 5.4, worked out here and not by the harness."""
    digest = hashlib.sha256()
    for name in ("spec.json", "golden.json", "module.py", "tests.py"):
        data = (Path(folder) / name).read_bytes()
        digest.update(f"{name}\n{len(data)}\n".encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


def add_test_run(conn, module, fingerprint, *, passed=True, reason="build"):
    """Insert a test_runs row directly, so registry tests do not depend on the gate."""
    cursor = conn.execute(
        "INSERT INTO test_runs (ts, module, fingerprint, reason, passed, report) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), module, fingerprint, reason, int(passed),
         json.dumps({"tests": [], "golden": [], "passed": passed})))
    conn.commit()
    return cursor.lastrowid


def insert_registered(conn, folder, step_id):
    """Put a module in the registry without any of `register`'s checks (for a module that must misbehave)."""
    folder = Path(folder)
    spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    fingerprint = expected_fingerprint(folder)
    run_id = add_test_run(conn, spec["name"], fingerprint)
    conn.execute("INSERT INTO modules (name, fingerprint, spec, test_run_id, registered_at, session_id)"
                 " VALUES (?, ?, ?, ?, ?, ?)",
                 (spec["name"], fingerprint, json.dumps(spec), run_id, datetime.now(timezone.utc).isoformat(), SESSION))
    conn.execute("INSERT INTO step_modules (step_id, module) VALUES (?, ?)", (step_id, spec["name"]))
    conn.commit()


def install(conn, files, step_id, session_id=SESSION):
    """Write a module's files into the modules folder, test them and register them, as a good build would."""
    from harness.calc import gate, registry

    name = json.loads(files["spec.json"])["name"]
    folder = write_files(registry.module_dir(name), files)
    run = gate.run_tests(conn, name, reason="build", session_id=session_id)
    assert run["passed"], run["report"]
    registry.register(conn, name, step_id=step_id, test_run_id=run["test_run_id"], session_id=session_id)
    conn.commit()
    return folder


def install_surplus(conn, step_id="s1"):
    return install(conn, surplus_files(step_id), step_id)


def install_months(conn, step_id="s3"):
    return install(conn, months_files(step_id), step_id)


def snapshot(folder):
    """Every regular file of a folder and its bytes."""
    return {p.name: p.read_bytes() for p in sorted(Path(folder).iterdir()) if p.is_file()}


# ---- the scripted model ------------------------------------------------------------------------

def tool(name, arguments):
    return {"tool_calls": [{"name": name, "arguments": arguments}]}


def tools(*calls, text=""):
    """One reply that holds several tool calls, each given as (name, arguments)."""
    return {"text": text, "tool_calls": [{"name": n, "arguments": a} for n, a in calls]}


def propose_spec(spec=None, **changes):
    return tool("propose_spec", {**(spec or surplus_spec()), **changes})


def reuse_module(module, reason="It does the same job."):
    return tool("reuse_module", {"module": module, "reason": reason})


def propose_examples(examples=None):
    return tool("propose_examples", {"examples": examples if examples is not None else surplus_examples()})


def write_module(module_py=SURPLUS_PY, tests_py=SURPLUS_TESTS):
    return tool("write_module", {"module_py": module_py, "tests_py": tests_py})


def surplus_script():
    """The three replies that build monthly_surplus at the first try of every phase."""
    return [propose_spec(), propose_examples(), write_module()]


def months_script():
    return [propose_spec(months_spec()), propose_examples(months_examples()),
            write_module(MONTHS_PY, MONTHS_TESTS)]


def say_text(text):
    return {"text": text}


def run_module(module="monthly_surplus", inputs=None, assumptions=(), expected="about the usual amount"):
    inputs = inputs if inputs is not None else {"income": "5000", "spending": "3000"}
    return tool("run_module", {"module": module, "inputs": inputs,
                               "assumptions": list(assumptions), "expected": expected})


def save_input(name="monthly_income", value="5000", note="said by the person"):
    return tool("save_input", {"name": name, "value": value, "note": note})


# ---- the person --------------------------------------------------------------------------------

class Person:
    """Answers `ask` from a list, and keeps everything shown, in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.log = []                       # ("ask" | "say", text)

    def ask(self, text):
        self.log.append(("ask", text))
        assert self.answers, f"the harness asked again with no answer left: {text!r}"
        return self.answers.pop(0)

    def say(self, text=""):
        self.log.append(("say", text))

    @property
    def asked(self):
        return [text for kind, text in self.log if kind == "ask"]

    @property
    def told(self):
        return [text for kind, text in self.log if kind == "say"]


def accepts(count):
    return ["/accept"] * count


# ---- reading what was recorded ------------------------------------------------------------------

def events(conn, kind=None):
    """(kind, actor, payload) of the events, oldest first."""
    from harness import db
    return [(r["kind"], r["actor"], json.loads(r["payload"])) for r in db.list_events(conn, kind=kind)]


def payloads(conn, kind):
    return [payload for _, _, payload in events(conn, kind)]


def kinds(conn, prefix=""):
    return [kind for kind, _, _ in events(conn) if kind.startswith(prefix)]


def rows(conn, table):
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]


# ---- the format of a user message (SPEC 5.7) ---------------------------------------------------

def sections(*pairs):
    """A user message made of (title, value) sections: `[title]`, then the value, one blank line between."""
    parts = []
    for title, value in pairs:
        text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
        parts.append(f"[{title}]\n{text}")
    return "\n\n".join(parts)


def prompt_text(name):
    return (CALC / name).read_text(encoding="utf-8")


def phase_calls(model, system_file):
    """The calls the scripted model received with the given instructions file as the system prompt."""
    text = prompt_text(system_file).strip()
    return [call for call in model.calls if call["system"].strip() == text]


# ---- the command line --------------------------------------------------------------------------

def run_cli(args, typed=""):
    """Run `python -m harness ...` in the repository with the test environment (set by conftest)."""
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=ROOT, input=typed,
                          capture_output=True, text=True)
