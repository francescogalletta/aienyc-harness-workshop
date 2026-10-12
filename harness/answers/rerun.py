"""The re-run engine (SPEC 5.4, ARCHITECTURE.md 12.4): when the person changes a value, which runs of the last
answer used it, directly or through an earlier run's result, and running them again through the gate.

No model is called. A run is reached by value lineage: a run of the last answer whose top-level input `key` holds
the old value is direct; a later run is reached when a value in its inputs (at any depth, inside lists and
objects too) equals a value an earlier re-run changed. Values compare as the number check reads them: the same
number however it is written ("36,100", "36100.00", 36100), else the same text. `impact` is the same walk without
running, for a proposal; `rerun` does it, for a join. Neither posts anything.
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


# --- Impact: the walk without running ---

def _current_conversation(conn) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'conversation'").fetchone()
    return row["value"] if row else None


def impact(conn, state: dict, *, key: str, old: str | None, conversation: str | None = None) -> dict:
    """What changing `key` from `old` would run again (12.4): the direct runs of the last answer, then each run
    holding a value an earlier listed run produced; their steps; and the steps the plan's edges reach from them
    that the last answer did not run (touched, not run). For a value no run used, those are the plan input's
    steps and what they reach. `state` needs only `inputs`, `steps` and `edges`; `conversation` defaults to the
    current one."""
    conversation = conversation or _current_conversation(conn)
    listed, numbers, dates = [], set(), set()
    for row in _rows(conn, conversation) if conversation else []:
        inputs = json.loads(row["inputs"])
        if _direct(inputs, key, old) or _holds(inputs, numbers, dates):
            listed.append(row)
            made_numbers, made_dates = _products(row)
            numbers |= made_numbers
            dates |= made_dates

    plan_steps = [step["id"] for step in state.get("steps", [])]
    steps = list(dict.fromkeys(step for step in (_step_of(conn, row["module"]) for row in listed)
                               if step in plan_steps))
    input_id = f"in:{key}"
    inputs = [input_id] if input_id in state.get("inputs", {}) else []
    start = steps if listed else list(state.get("inputs", {}).get(input_id, {}).get("steps", []))
    reached, todo = set(start), list(start)
    while todo:
        here = todo.pop()
        for edge in state.get("edges", []):
            if edge.get("from") == here and edge.get("to") not in reached:
                reached.add(edge["to"])
                todo.append(edge["to"])
    downstream = [step for step in plan_steps if step in reached and step not in steps]
    return {"inputs": inputs, "runs": [f"r{row['id']}" for row in listed], "steps": steps,
            "downstream": downstream}


# --- The re-run ---

class _Changes:
    """The old values earlier re-runs changed, leaf by leaf: {old: {new token: new value}}. A value one leaf
    changed and another kept, or changed to two different values, is ambiguous."""

    def __init__(self):
        self.seen: dict = {}

    def add(self, old_output, new_output) -> None:
        for old, new in _pairs(old_output, new_output):
            self.seen.setdefault(_token(old), {})[_token(new)] = new

    def find(self, value) -> tuple[bool, object]:
        """(changed, the new value or AMBIGUOUS) for a leaf of a later run's inputs."""
        token = _token(value)
        news = self.seen.get(token)
        if not news or set(news) == {token}:
            return False, None
        if len(news) > 1:
            return True, AMBIGUOUS
        return True, next(iter(news.values()))

    def replace(self, value) -> tuple[object, bool]:
        """The value with each changed leaf replaced, written as it was; and whether it took an ambiguous one."""
        if isinstance(value, dict):
            pairs = [(key, *self.replace(item)) for key, item in value.items()]
            return {key: item for key, item, _ in pairs}, any(flag for _, _, flag in pairs)
        if isinstance(value, list):
            pairs = [self.replace(item) for item in value]
            return [item for item, _ in pairs], any(flag for _, flag in pairs)
        changed, new = self.find(value)
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


def rerun(work, *, key: str, old: str | None, new: str, label: str, drop=()) -> dict:
    """Run again, through the gate, the runs of the last answer the change of `key` from `old` to `new` reaches
    (12.4), oldest first, each with the values earlier re-runs changed. Returns {"replaced": {"r3": "r9"},
    "failed": [{"run": "r5", "step": "s5" | None, "reason": str}], "runs": [the new last answer, oldest first]}.
    `drop` are assumption sentences to leave out (a branch's assumption subject). Posts nothing."""
    conn, conversation = work.conn, work.conversation
    rows = _rows(conn, conversation)
    numbers = _step_numbers(work)
    expected = RERUN_EXPECTED.format(label=label, new=new, old="none" if old is None else old)
    dropped = {" ".join(sentence.split()) for sentence in drop}
    changes, broken_numbers, broken_dates = _Changes(), set(), set()
    replaced, failed, kept = {}, [], []

    def fail(row, step, reason):
        failed.append({"run": f"r{row['id']}", "step": step, "reason": reason})
        made_numbers, made_dates = _products(row)
        broken_numbers.update(made_numbers)
        broken_dates.update(made_dates)
        kept.append(row["id"])

    for row in rows:
        inputs = json.loads(row["inputs"])
        step = _step_of(conn, row["module"])
        if _holds(inputs, broken_numbers, broken_dates):
            fail(row, step, UPSTREAM_FAILED)
            continue
        direct = _direct(inputs, key, old)
        others = {name: value for name, value in inputs.items() if name != key} if direct else inputs
        fresh, ambiguous = changes.replace(others)
        if direct:
            was = inputs[key]
            fresh = {name: (_written_as(was, new) if not isinstance(was, (list, dict)) else new) if name == key
                     else fresh[name] for name in inputs}
        if ambiguous:
            fail(row, step, AMBIGUOUS)
            continue
        if fresh == inputs:
            kept.append(row["id"])
            continue
        assumptions = [sentence for sentence in json.loads(row["assumptions"])
                       if " ".join(sentence.split()) not in dropped and _keeps(sentence, key, old)]
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
        changes.add(json.loads(row["output"]), result["output"])

    runs = sorted(kept + [int(each[1:]) for each in replaced.values()])
    return {"replaced": replaced, "failed": failed, "runs": runs}
