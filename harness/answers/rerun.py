"""The re-run engine (SPEC 5.4, ARCHITECTURE.md 12.4): when the person changes one value or a bundle of them,
which runs of the last answer used them, directly or through an earlier run's result, and running them again
through the gate.

No model is called. A run is reached by value lineage: a run of the last answer whose top-level input `key` holds
the old value is direct; a later run is reached when a value in its inputs (at any depth, inside lists and
objects too) equals a value an earlier re-run changed, and that re-run is of a step the plan's edges reach this
run's step from (a step not in the plan feeds, and is fed by, any step). Values compare as the number check
reads them: the same number however it is written ("36,100", "36100.00", 36100), else the same text. `impact`
is the same walk without running, for a proposal; `rerun` does it, for a join. Neither posts anything.
"""
import json
from decimal import Decimal, InvalidOperation

from ..calc import gate
from ..calc.added import process_steps
from ..calc.builder import plan_of
from ..calc.provenance import _produced, _read
from ..calc.registry import get_module
from .layer import latest_answer

RERUN_EXPECTED = "Run again by the harness: {label} is {new} (was {old})."
RUNNING_AGAIN = "running step {number} again"
AMBIGUOUS = "a value it took is ambiguous"
UPSTREAM_FAILED = "an earlier step could not run again"


# --- Values as the number check reads them ---

def _number(value) -> Decimal | None:
    """The number a leaf value is, written in any way the number check reads ("36,100", "$36,100", "36.1k",
    "36100.00", 36100), or None for a date, text, true/false, null, a list or an object."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    try:
        found = Decimal(text.replace(",", ""))
    except InvalidOperation:
        items = _read(text)
        if len(items) != 1 or items[0]["parts"] or items[0]["percent"] or items[0]["written"] != text:
            return None
        found = items[0]["value"]
    return found if found.is_finite() else None


def _token(value):
    """What a leaf value is compared by: its number, else its text, else itself. None for a list or object."""
    if isinstance(value, (list, dict)):
        return None
    number = _number(value)
    if number is not None:
        return ("number", number)
    if isinstance(value, str):
        return ("text", value.strip())
    return ("other", value)


def _leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def _pairs(old, new):
    """(old leaf, new leaf) of two outputs lined up by key path, a list by position. What does not line up
    (a key on one side only, a longer list, a leaf against a list or object) is left out."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in old:
            if key in new:
                yield from _pairs(old[key], new[key])
    elif isinstance(old, list) and isinstance(new, list):
        for old_item, new_item in zip(old, new):
            yield from _pairs(old_item, new_item)
    elif not isinstance(old, (list, dict)) and not isinstance(new, (list, dict)):
        yield old, new


def _plain(number: Decimal) -> str:
    """The shortest plain decimal: 43000, 18500, 0.4."""
    text = format(number.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def _written_as(was, new):
    """`new` written as the input `was` was written (12.4, point 3): text as the shortest plain decimal or the
    date or text as it is; a JSON number stays a number (whole when it was whole and still is)."""
    number = _number(new)
    if number is None:
        return new
    if isinstance(was, str):
        return _plain(number)
    if isinstance(was, int) and not isinstance(was, bool):
        return int(number) if number == number.to_integral_value() else float(number)
    if isinstance(was, float):
        return float(number)
    return new


# --- The last answer ---

def last_answer_runs(conn, conversation: str) -> list[int]:
    """The runs of the last answer (SPEC 5.2): those of its turn and those its figures name, oldest first."""
    return sorted(latest_answer(conn, conversation)[1])


def _rows(conn, conversation: str) -> list:
    """The `calc_runs` rows of the last answer, oldest first."""
    ids = last_answer_runs(conn, conversation)
    if not ids:
        return []
    return conn.execute(f"SELECT * FROM calc_runs WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id",
                        tuple(ids)).fetchall()


def _as_written(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def old_values(conn, conversation: str, key: str) -> list[str]:
    """The distinct values the top-level input `key` has among the runs of the last answer, as written, oldest
    first. Two writings of one number ("36100" and "36,100") count once, as first written."""
    found, seen = [], set()
    for row in _rows(conn, conversation):
        inputs = json.loads(row["inputs"])
        if not isinstance(inputs, dict) or key not in inputs:
            continue
        value = inputs[key]
        token = _token(value) if not isinstance(value, (list, dict)) else ("json", _as_written(value))
        if token not in seen:
            seen.add(token)
            found.append(_as_written(value))
    return found


def _direct(inputs, key: str, old) -> bool:
    """Whether a run's inputs have `key` at the top level with the old value (12.4, point 1); with no old value,
    whether they have `key` at all."""
    if not isinstance(inputs, dict) or key not in inputs:
        return False
    return old is None or _token(inputs[key]) == _token(old)


def _products(row) -> tuple[set, set]:
    """What a run produced, as `provenance._produced` reads it: numbers, and dates written whole."""
    numbers, dates = _produced(json.loads(row["output"]), json.loads(row["inputs"]))
    return set(numbers), set(dates)


def _holds(inputs, numbers: set, dates: set) -> bool:
    """Whether a value anywhere in the inputs is one of these numbers or dates."""
    for leaf in _leaves(inputs):
        number = _number(leaf)
        if number is not None and number in numbers:
            return True
        if isinstance(leaf, str) and leaf.strip() in dates:
            return True
    return False


def _step_of(conn, module: str) -> str | None:
    found = get_module(conn, module)
    return (found or {}).get("spec", {}).get("step_id") or None


# --- Changes and the plan's needs ---

def _changes_of(key, old, new=None, label=None, changes=None) -> list[dict]:
    """The bundle: `changes` as given ({key, old, new?, label?} each), else the one change of the keywords."""
    if changes is not None:
        return [dict(each) for each in changes]
    return [{"key": key, "old": old, "new": new, "label": label}]


def _ancestors(edges, steps) -> dict[str, set]:
    """For each step, the steps the edges reach it from, transitively."""
    parents: dict = {}
    for edge in edges:
        parents.setdefault(edge["to"], set()).add(edge["from"])
    found = {}
    for step in steps:
        seen, todo = set(), list(parents.get(step, ()))
        while todo:
            here = todo.pop()
            if here not in seen:
                seen.add(here)
                todo.extend(parents.get(here, ()))
        found[step] = seen
    return found


def _feeds(producer: str | None, consumer: str | None, ancestors: dict) -> bool:
    """Whether a run of step `producer` may have fed a run of step `consumer`: yes when either is not a step of
    the plan, else when the plan's edges reach `consumer` from `producer`."""
    if consumer not in ancestors or producer not in ancestors:
        return True
    return producer in ancestors[consumer]


def _plan_edges(brief: dict | None) -> tuple[list[dict], list[str]]:
    """The edges and step ids of a brief: each need that is a step id is an edge."""
    if not brief:
        return [], []
    steps = [step["id"] for step in brief["process"]]
    edges = [{"from": need, "to": step["id"]} for step in brief["process"] for need in step.get("needs", [])
             if need in steps]
    return edges, steps


# --- Impact: the walk without running ---

def _current_conversation(conn) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'conversation'").fetchone()
    return row["value"] if row else None


def impact(conn, state: dict, *, key: str | None = None, old: str | None = None, changes: list | None = None,
           conversation: str | None = None) -> dict:
    """What changing `key` from `old` (or each change of a bundle) would run again (12.4): the direct runs of
    the last answer, then each run holding a value an earlier listed run of a step its step needs produced;
    their steps; and the steps the plan's edges reach from them that the last answer did not run (touched, not
    run). For a value no run used, those are the plan input's steps and what they reach. `state` needs only
    `inputs`, `steps` and `edges`; `conversation` defaults to the current one."""
    conversation = conversation or _current_conversation(conn)
    wanted = _changes_of(key, old, changes=changes)
    plan_steps = [step["id"] for step in state.get("steps", []) if step.get("in_plan", True)]
    ancestors = _ancestors(state.get("edges", []), plan_steps)
    listed, made = [], []                       # made: (step, numbers, dates) of each listed run
    for row in _rows(conn, conversation) if conversation else []:
        inputs = json.loads(row["inputs"])
        step = _step_of(conn, row["module"])
        direct = any(_direct(inputs, each["key"], each["old"]) for each in wanted)
        fed = any(_holds(inputs, numbers, dates) for producer, numbers, dates in made
                  if _feeds(producer, step, ancestors))
        if direct or fed:
            listed.append(row)
            made.append((step, *_products(row)))

    all_steps = [step["id"] for step in state.get("steps", [])]
    steps = list(dict.fromkeys(step for step in (_step_of(conn, row["module"]) for row in listed)
                               if step in all_steps))
    inputs = [f"in:{each['key']}" for each in wanted if f"in:{each['key']}" in state.get("inputs", {})]
    start = steps if listed else list(dict.fromkeys(
        step for input_id in inputs for step in state.get("inputs", {}).get(input_id, {}).get("steps", [])))
    reached, todo = set(start), list(start)
    while todo:
        here = todo.pop()
        for edge in state.get("edges", []):
            if edge.get("from") == here and edge.get("to") not in reached:
                reached.add(edge["to"])
                todo.append(edge["to"])
    downstream = [step for step in all_steps if step in reached and step not in steps]
    return {"inputs": inputs, "runs": [f"r{row['id']}" for row in listed], "steps": steps,
            "downstream": downstream}


# --- The re-run ---

class _Changes:
    """The old values earlier re-runs changed, leaf by leaf, with the step that changed each:
    {old token: [(step, new value)]}. For a later run, only the re-runs of steps its step needs count (`_feeds`);
    a value they changed two different ways is ambiguous."""

    def __init__(self, ancestors: dict):
        self.seen: dict = {}
        self.ancestors = ancestors

    def add(self, old_output, new_output, step) -> None:
        for old, new in _pairs(old_output, new_output):
            self.seen.setdefault(_token(old), []).append((step, new))

    def find(self, value, consumer) -> tuple[bool, object]:
        """(changed, the new value or AMBIGUOUS) for a leaf of a later run's inputs, of step `consumer`."""
        token = _token(value)
        news = {}
        for producer, new in self.seen.get(token, ()):
            if _feeds(producer, consumer, self.ancestors):
                news[_token(new)] = new
        if not news or set(news) == {token}:
            return False, None
        if len(news) > 1:
            return True, AMBIGUOUS
        return True, next(iter(news.values()))

    def replace(self, value, consumer) -> tuple[object, bool]:
        """The value with each changed leaf replaced, written as it was; and whether it took an ambiguous one."""
        if isinstance(value, dict):
            pairs = [(key, *self.replace(item, consumer)) for key, item in value.items()]
            return {key: item for key, item, _ in pairs}, any(flag for _, _, flag in pairs)
        if isinstance(value, list):
            pairs = [self.replace(item, consumer) for item in value]
            return [item for item, _ in pairs], any(flag for _, flag in pairs)
        changed, new = self.find(value, consumer)
        if not changed:
            return value, False
        if new is AMBIGUOUS:
            return value, True
        return _written_as(value, new), False


def _words_of(key: str) -> str:
    return " ".join(key.replace("_", " ").casefold().split())


def _keeps(sentence: str, key: str, old) -> bool:
    """An assumption is kept unless it holds the old value or names `key` in words (12.4, point 4)."""
    spaced = " ".join(sentence.casefold().split())
    if _words_of(key) and _words_of(key) in spaced:
        return False
    if old is None:
        return True
    number = _number(old)
    if number is not None:
        return not any(not item["parts"] and item["value"] == number for item in _read(sentence))
    text = " ".join(str(old).casefold().split())
    return not text or text not in spaced


def _step_numbers(work) -> dict[str, int]:
    brief = plan_of(work.config)
    return {step["id"]: number for number, step in enumerate(process_steps(work.conn, brief), start=1)} \
        if brief else {}


def expected_text(changes: list[dict]) -> str:
    """What a re-run says it expects: one RERUN_EXPECTED sentence per change of the bundle."""
    return " ".join(RERUN_EXPECTED.format(label=each.get("label") or each["key"], new=each["new"],
                                          old="none" if each["old"] is None else each["old"]) for each in changes)


def rerun(work, *, key: str | None = None, old: str | None = None, new: str | None = None,
          label: str | None = None, changes: list | None = None, drop=()) -> dict:
    """Run again, through the gate, the runs of the last answer the change of `key` from `old` to `new` (or
    each change of the bundle `changes`, {key, old, new, label} each) reaches (12.4), oldest first, each with
    every value of the bundle set and the values earlier re-runs changed. Returns {"replaced": {"r3": "r9"},
    "failed": [{"run": "r5", "step": "s5" | None, "reason": str}], "runs": [the new last answer, oldest first]}.
    `drop` are assumption sentences to leave out (a branch's assumption subject). Posts nothing."""
    conn, conversation = work.conn, work.conversation
    wanted = _changes_of(key, old, new, label, changes)
    rows = _rows(conn, conversation)
    numbers = _step_numbers(work)
    edges, plan_steps = _plan_edges(plan_of(work.config))
    ancestors = _ancestors(edges, plan_steps)
    expected = expected_text(wanted)
    dropped = {" ".join(sentence.split()) for sentence in drop}
    changed, broken = _Changes(ancestors), []           # broken: (step, numbers, dates) of each failed run
    replaced, failed, kept = {}, [], []

    def fail(row, step, reason):
        failed.append({"run": f"r{row['id']}", "step": step, "reason": reason})
        broken.append((step, *_products(row)))
        kept.append(row["id"])

    for row in rows:
        inputs = json.loads(row["inputs"])
        step = _step_of(conn, row["module"])
        if any(_holds(inputs, made_numbers, made_dates) for producer, made_numbers, made_dates in broken
               if _feeds(producer, step, ancestors)):
            fail(row, step, UPSTREAM_FAILED)
            continue
        direct = {each["key"]: each for each in wanted if _direct(inputs, each["key"], each["old"])}
        others = {name: value for name, value in inputs.items() if name not in direct}
        fresh, ambiguous = changed.replace(others, step)
        for name, each in direct.items():
            was = inputs[name]
            fresh[name] = _written_as(was, each["new"]) if not isinstance(was, (list, dict)) else each["new"]
        fresh = {name: fresh[name] for name in inputs}
        if ambiguous:
            fail(row, step, AMBIGUOUS)
            continue
        if fresh == inputs:
            kept.append(row["id"])
            continue
        assumptions = [sentence for sentence in json.loads(row["assumptions"])
                       if " ".join(sentence.split()) not in dropped
                       and all(_keeps(sentence, each["key"], each["old"]) for each in wanted)]
        work.progress(RUNNING_AGAIN.format(number=numbers[step]) if step in numbers
                      else f"running {row['module']} again", step=step, what="join")
        try:
            result = gate.call(conn, row["module"], fresh, assumptions=assumptions, expected=expected,
                               session_id=conversation)
        except gate.Refused as refused:
            fail(row, step, str(refused))
            continue
        finally:
            work.changed()
        replaced[f"r{row['id']}"] = f"r{result['run_id']}"
        changed.add(json.loads(row["output"]), result["output"], step)

    runs = sorted(kept + [int(each[1:]) for each in replaced.values()])
    return {"replaced": replaced, "failed": failed, "runs": runs}
