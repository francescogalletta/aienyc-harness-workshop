"""Adopting module folders that are already on disk (SPEC 5.13).

The person accepts worked examples someone else checked, as a whole. Then each
module's tests and examples run here, and `register` re-checks everything.
Nothing here calls a model.
"""
import json
import re

from .. import db
from ..config import load_config
from .added import ADDED_PREFIX, add_step, list_added_steps, process_steps, step_label
from .builder import ACCEPT_WORDS
from .gate import run_tests
from .registry import FILES, MIN_CONFIRMED, file_status, get_module, register, step_map, validate_spec

ADOPT_INTRO = ("These module folders are not registered here. Their worked examples were checked by hand, "
               "but not by you:")
ADOPT_QUESTION = ("Adopting a module means trusting worked examples you did not check yourself. Its tests and "
                  "examples run first, and it is registered only if they pass. Type yes to adopt them. "
                  "Anything else adopts nothing.")
ADOPT_MISSING = "missing files: {files}"
ADOPT_BAD_SPEC = "spec.json is not a valid spec for this folder"
ADOPT_BAD_EXAMPLES = "golden.json does not hold at least 2 worked examples"
ADOPT_NO_STEP = "the process has no calculation step '{step}'"
ADOPT_STEP_TAKEN = "step {step} already has the module '{other}'"
REASON_DECLINED = "you did not accept the worked examples"
REASON_TESTS = "its tests or worked examples do not pass here"
ADOPTED_STEP = "Re-created from the module '{module}' when it was adopted."

ADDED_STEP = re.compile(r"^added_[1-9][0-9]*$")
_UNREADABLE = object()


def candidates(conn) -> list[str]:
    """Module folders that are not registered, or whose registered files changed or are gone (SPEC 5.13)."""
    folder = load_config().modules_dir
    if not folder.is_dir():
        return []
    names = [path.name for path in folder.iterdir()
             if path.is_dir() and not path.name.startswith(("_", "."))
             and not (get_module(conn, path.name) and file_status(conn, path.name) == "unchanged")]
    return sorted(names)


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _UNREADABLE


def adopt(*, conn, brief, ask, say=print, session_id, how="asked") -> list[dict]:
    """Register the candidate module folders that pass, after the person's yes. Returns one result each."""
    folder = load_config().modules_dir
    results = {}            # module name -> result
    adoptable = []          # (name, step id, golden), in name order
    claimed = {}            # step id -> the earlier adoptable candidate that has it
    steps = {step["id"]: step for step in process_steps(conn, brief)}
    mapped = step_map(conn)

    def refuse(name, step, reason):
        db.record_event(conn, session_id=session_id, kind="calc.adopt_refused", actor="harness",
                        payload={"module": name, "step": step, "reason": reason})
        say(f"{name}: not adopted ({reason})")
        results[name] = {"module": name, "step": step, "outcome": "not_adopted", "reason": reason}

    # 1. Check each candidate, in name order.
    for name in candidates(conn):
        path = folder / name
        spec = _read_json(path / "spec.json")
        step = spec.get("step_id") if isinstance(spec, dict) else None
        step = step if isinstance(step, str) and step else None

        absent = [file for file in FILES if not (path / file).is_file()]
        if absent:
            refuse(name, step, ADOPT_MISSING.format(files=", ".join(absent)))
            continue
        if spec is _UNREADABLE or validate_spec(spec) or spec["name"] != name:
            refuse(name, step, ADOPT_BAD_SPEC)
            continue
        golden = _read_json(path / "golden.json")
        if (not isinstance(golden, list) or len(golden) < MIN_CONFIRMED
                or not all(isinstance(entry, dict) for entry in golden)):
            refuse(name, step, ADOPT_BAD_EXAMPLES)
            continue
        if not ((step in steps and steps[step].get("kind") == "calculation") or ADDED_STEP.match(step)):
            refuse(name, step, ADOPT_NO_STEP.format(step=step))
            continue
        other = mapped.get(step)
        if other is not None and other != name and file_status(conn, other) == "unchanged":
            refuse(name, step, ADOPT_STEP_TAKEN.format(step=step_label(step), other=other))
            continue
        if step in claimed:
            refuse(name, step, ADOPT_STEP_TAKEN.format(step=step_label(step), other=claimed[step]))
            continue
        claimed[step] = name
        adoptable.append((name, step, golden))

    # 2. Ask once.
    if adoptable:
        names = [name for name, _, _ in adoptable]
        if how == "asked":
            say(ADOPT_INTRO)
            for name, step, golden in adoptable:
                decisions = ", ".join(entry["decision"] if isinstance(entry.get("decision"), str) else "?"
                                      for entry in golden)
                say(f"  {name} for step {step_label(step)}: {len(golden)} worked examples ({decisions})")
            while True:
                answer = ask(ADOPT_QUESTION).strip()
                if answer:
                    break
            accepted = answer.lower() in ACCEPT_WORDS       # strict: no leniency here (SPEC 5.13)
            db.record_event(conn, session_id=session_id, kind="calc.adopt_decision", actor="person",
                            payload={"modules": names, "decision": "accepted" if accepted else "declined",
                                     "text": answer, "how": "asked"})
        else:
            accepted = True
            db.record_event(conn, session_id=session_id, kind="calc.adopt_decision", actor="harness",
                            payload={"modules": names, "decision": "accepted", "text": "", "how": "replay"})

        if not accepted:
            for name, step, _ in adoptable:
                say(f"{name}: not adopted ({REASON_DECLINED})")
                results[name] = {"module": name, "step": step, "outcome": "not_adopted",
                                 "reason": REASON_DECLINED}
        else:
            # 3. Adopt each, in name order.
            for name, step, _ in adoptable:
                _adopt_one(conn, name, step, session_id, how, results, refuse, say)

    return [results[name] for name in sorted(results)]


def _adopt_one(conn, name, step, session_id, how, results, refuse, say) -> None:
    run = run_tests(conn, name, reason="adopt", session_id=session_id)
    if not run["passed"]:
        return refuse(name, step, REASON_TESTS)
    try:
        fingerprint = register(conn, name, step_id=step, test_run_id=run["test_run_id"], session_id=session_id)
    except ValueError as error:
        return refuse(name, step, str(error))
    if step.startswith(ADDED_PREFIX) and step not in {each["id"] for each in list_added_steps(conn)}:
        spec = get_module(conn, name)["spec"]       # re-create the step, so the process stays whole
        add_step(conn, name=spec["description"], formula=spec["formula"],
                 needs=", ".join(item["name"].replace("_", " ") for item in spec["inputs"]),
                 produces=spec["output"]["description"], reason=ADOPTED_STEP.format(module=name),
                 session_id=session_id, step_id=step)
    db.record_event(conn, session_id=session_id, kind="calc.module_adopted", actor="harness",
                    payload={"module": name, "step": step, "fingerprint": fingerprint,
                             "test_run_id": run["test_run_id"], "how": how})
    say(f"{name} -> {step_label(step)} (adopted)")
    results[name] = {"module": name, "step": step, "outcome": "adopted", "reason": ""}
