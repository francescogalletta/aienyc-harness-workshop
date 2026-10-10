"""Shared by the step 2 tests of `adopt` (SPEC 5.13): its fixed strings, module folders on disk and a recording person.

The fixed strings are copied from the SPEC on purpose: the tests check the harness against the contract, not against
its own constants. The step 3 helpers import this file.
"""
import json
from pathlib import Path

import step2_helpers as h
from step2_helpers import Person

# ---- fixed strings (SPEC 5.13) ---------------------------------------------------------------------------

ADOPT_INTRO = "These module folders are not registered here. Their worked examples were checked by hand, but not by you:"
ADOPT_QUESTION = ("Adopting a module means trusting worked examples you did not check yourself. Its tests and "
                  "examples run first, and it is registered only if they pass. Type yes to adopt them. Anything "
                  "else adopts nothing.")
ADOPT_MISSING = "missing files: {files}"
ADOPT_BAD_SPEC = "spec.json is not a valid spec for this folder"
ADOPT_BAD_EXAMPLES = "golden.json does not hold at least 2 worked examples"
ADOPT_NO_STEP = "the process has no calculation step '{step}'"
ADOPT_STEP_TAKEN = "step {step} already has the module '{other}'"
REASON_DECLINED = "you did not accept the worked examples"
REASON_TESTS = "its tests or worked examples do not pass here"
ADOPTED_STEP = "Re-created from the module '{module}' when it was adopted."
UNADOPTED = ("The modules folder has modules that are not registered here: {names}. Adopt them first with: "
             "python -m harness adopt")
NOTHING_TO_ADOPT = "Every module folder is already registered."
ALL_ADOPTED = "Every module folder is registered now."
SOME_NOT_ADOPTED = ("Some module folders are not registered. Fix them, or rebuild their steps with: "
                    "python -m harness build")


def typed(*answers):
    return "".join(answer + "\n" for answer in answers)


def dump(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


# ---- module folders on disk ---------------------------------------------------------------------------------

def put_module(modules_dir, files):
    """Write a module folder (named after its spec) into the modules folder. Returns the folder."""
    name = json.loads(files["spec.json"])["name"]
    return h.write_files(Path(modules_dir) / name, files)


def surplus_folder(modules_dir, step_id="s1", **options):
    return put_module(modules_dir, h.surplus_files(step_id, **options))


def months_folder(modules_dir, step_id="s3", **options):
    return put_module(modules_dir, h.months_files(step_id, **options))


def yearly_folder(modules_dir, step_id="added_1"):
    return put_module(modules_dir, h.yearly_files(step_id))


def renamed_files(files, name, step_id=None):
    """The same module under another name (and, when given, for another step)."""
    spec = json.loads(files["spec.json"])
    spec["name"] = name
    if step_id is not None:
        spec["step_id"] = step_id
    return {**files, "spec.json": dump(spec)}


def with_spec(files, **changes):
    spec = json.loads(files["spec.json"])
    spec.update(changes)
    return {**files, "spec.json": dump(spec)}


# ---- running adopt -----------------------------------------------------------------------------------------

def run_adopt(conn, brief, *answers, how="asked", session_id=h.SESSION, **options):
    """Call `adopt` with a recording person. Returns (results, person)."""
    import importlib
    adopt = importlib.import_module("harness.calc.adopt")
    person = Person(*answers)
    results = adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=session_id,
                          how=how, **options)
    return results, person


def adopted_line(name, step_id):
    return f"{name} -> {h.label(step_id)} (adopted)"


def refused_line(name, reason):
    return f"{name}: not adopted ({reason})"


def listing(name, step_id, n=3, decisions=None):
    decisions = decisions or ["accepted"] * n
    return f"  {name} for step {h.label(step_id)}: {n} worked examples ({', '.join(decisions)})"


def result(name, step, outcome="adopted", reason=""):
    return {"module": name, "step": step, "outcome": outcome, "reason": reason}
