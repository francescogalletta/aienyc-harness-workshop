"""The plan state document (ARCHITECTURE.md section 3) and the step-line rule (SPEC 2.4).

`start()` makes the top level the core owns; layers add their keys in order;
`finish()` then works out `needs_you`, `line` and `marks` for every step. The
page and the terminal show these as they come.
"""
import json
import re
from decimal import ROUND_HALF_UP, Decimal

PRODUCT = "Financial Advisor Harness"
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEXT_LENGTH = 18
KEY_VALUE_LENGTH = 24      # a key value with its name may run a little longer
MARK_TITLES = {
    "●": "open questions",
    "plan check": "the built calculation departs from the plan",
    "▲": "open challenges",
    "◌": "rests on something unconfirmed",
}


def start(*, version: int, layers: list[int], error, lanes: dict, activity: list, waiting, chat: list) -> dict:
    """The top level of the state document, before any layer has contributed."""
    return {
        "version": version,
        "layers": layers,
        "product": PRODUCT,
        "phase": "empty",
        "error": error,
        "lanes": lanes,
        "activity": activity,
        "waiting": waiting,
        "goal": None,
        "context": None,
        "inputs": {},
        "steps": [],
        "edges": [],
        "chat": chat,
    }


def finish(state: dict) -> dict:
    """Work out `needs_you`, `line` and `marks` on every step, after every layer has contributed."""
    steps = state.get("steps", [])
    _needs_you(steps)
    for step in steps:
        step["line"] = step_line(step)
        step["marks"] = step_marks(step)
    return state


def _needs_you(steps: list[dict]) -> None:
    """At most one step needs the person: the step of the open decision; with none, the first
    calculation step that is not built with a disagreement or too few checked examples."""
    chosen = next((step for step in steps if (step.get("calls") or {}).get("open")), None)
    if chosen is None:
        chosen = next((step for step in steps if step.get("needs_you")), None)
    if chosen is None:
        chosen = next((step for step in steps if _stuck(step.get("build"))), None)
    for step in steps:
        step["needs_you"] = step is chosen


def _stuck(build) -> bool:
    if not build or build.get("status") != "not_built":
        return False
    checked = [each for each in build.get("example_list") or [] if each.get("checked_by")]
    return bool(build.get("disagreement")) or len(checked) < 2


def step_line(step: dict) -> dict | None:
    """The first rule of SPEC 2.4 that applies."""
    build = step.get("build") or {}
    last_run = step.get("last_run") or {}
    if step.get("needs_you"):
        why = "your call" if (step.get("calls") or {}).get("open") else "not built"
        return {"text": f"Needs you · {why}", "kind": "strong"}
    if build.get("status") == "building":
        return {"text": "Building", "kind": None}
    if last_run.get("in_last_answer"):
        output = ((step.get("build") or {}).get("spec") or {}).get("output")
        text = "→ " + show_value(last_run.get("output"), output)
        if step.get("unconfirmed"):
            text += " ◌"
        return {"text": text, "kind": "result"}
    if build.get("status") == "built":
        examples, tests = build.get("examples", 0), build.get("tests", 0)
        passing, examples_passing = build.get("passing", 0), build.get("examples_passing", 0)
        tested = passing == tests and examples_passing == examples
        return {"text": f"{examples} examples · {passing}/{tests}", "kind": "tested" if tested else None}
    if build.get("status") == "stale":
        return {"text": "Stale · rebuild", "kind": None}
    if build.get("status") == "not_built":
        return {"text": "Not built", "kind": None}
    if (step.get("calls") or {}).get("records"):
        return {"text": "Decided", "kind": None}
    return None


def step_marks(step: dict) -> list[dict]:
    """The marks of SPEC 2.4, in order, each only when it applies."""
    marks = []
    questions = step.get("open_questions") or []
    if questions:
        marks.append({"symbol": "●", "count": len(questions), "title": MARK_TITLES["●"]})
    plan_check = (step.get("build") or {}).get("plan_check")
    if plan_check and plan_check.get("departures") and not plan_check.get("confirmed"):
        marks.append({"symbol": "plan check", "count": None, "title": MARK_TITLES["plan check"]})
    challenges = step.get("challenges") or []
    if challenges:
        marks.append({"symbol": "▲", "count": len(challenges), "title": MARK_TITLES["▲"]})
    if step.get("unconfirmed"):
        marks.append({"symbol": "◌", "count": None, "title": MARK_TITLES["◌"]})
    return marks


def show_value(value, output: dict | None = None) -> str:
    """A run's output on the step line (SPEC 2.4): a number as `show_number` writes it, a date as given, text cut
    to 18 characters; an object or a list as its key value with the key's name when the output's description
    makes one obvious (`key_value`), else `{n} values`."""
    if isinstance(value, (list, dict)):
        found = key_value(value, (output or {}).get("description") or "")
        return found if found is not None else count(value)
    text = show_scalar(value)
    return text if len(text) <= TEXT_LENGTH else text[:TEXT_LENGTH - 1] + "…"


# --- How values are shown (SPEC 2.4): one place, used for the step line, the pop-up's runs and examples,
# and the numbers of a decision. Modules compute exactly; this only writes a value for the eye. ---

def _decimal(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str) and NUMBER.match(value.strip()):
        return Decimal(value.strip())
    return None


def show_number(number, key: str = "") -> str:
    """Thousands separators and at most two decimals, the trailing zeros of a whole amount dropped; up to four
    decimals (trailing zeros dropped) for a value below 1. A whole number under a key naming a year is written
    without separators."""
    number = Decimal(number) if not isinstance(number, Decimal) else number
    if number != 0 and abs(number) < 1:
        text = format(number.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f").rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text
    rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral():
        whole = int(rounded)
        return str(whole) if "year" in key.lower() else f"{whole:,}"
    return f"{rounded:,.2f}"


def show_scalar(value, key: str = "") -> str:
    """One value as it is shown: yes or no, a number by `show_number`, a date or text as given, a list or an
    object as `{n} values`."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "nothing"
    if isinstance(value, (list, dict)):
        return count(value)
    number = _decimal(value)
    if number is not None:
        return show_number(number, key)
    return str(value)


def count(value) -> str:
    """`{n} values` (`1 value`) for a list or an object."""
    return "1 value" if len(value) == 1 else f"{len(value)} values"


def key_name(key) -> str:
    return str(key).replace("_", " ")


def _numeric_keys(rows: list[dict]) -> list[str]:
    keys = [key for key in rows[0] if all(isinstance(row, dict) for row in rows)]
    return [key for key in keys if all(_decimal(row.get(key)) is not None for row in rows)]


def key_value(value, description: str) -> str | None:
    """The key value of an object, or of the last row of a list of objects, written `name value` (`last name
    value` for a list), when one is obvious: the only numeric key the output's description names, else the only
    numeric key there is. None when none is obvious."""
    if isinstance(value, dict):
        rows, prefix = [value], ""
    elif isinstance(value, list) and value and all(isinstance(row, dict) and row for row in value):
        rows, prefix = value, "last "
    else:
        return None
    if not rows or not rows[0]:
        return None
    numeric = _numeric_keys(rows)
    words = " ".join(description.casefold().replace("_", " ").split())
    named = [key for key in numeric if re.search(r"\b" + re.escape(key_name(key).casefold()) + r"\b", words)]
    chosen = named if len(named) == 1 else numeric if len(numeric) == 1 else []
    if len(chosen) != 1:
        return None
    key = chosen[0]
    shown = show_scalar(rows[-1][key], key)
    name = prefix + key_name(key)
    room = KEY_VALUE_LENGTH - len(shown) - 1
    if len(name) > room:
        name = name[:max(1, room - 1)] + "…"
    return f"{name} {shown}"


def display(value) -> dict:
    """A value as the pop-up shows it: `text` always (a short form), and `rows` ([name, text] for an object, or
    [index, text] for a list of single values) or `columns` and `table` (a list of objects, one row each)."""
    if isinstance(value, dict):
        return {"text": count(value),
                "rows": [[key_name(key), show_scalar(each, str(key))] for key, each in value.items()]}
    if isinstance(value, list):
        if value and all(isinstance(row, dict) for row in value):
            columns = []
            for row in value:
                columns += [key for key in row if key not in columns]
            return {"text": count(value), "columns": [key_name(key) for key in columns],
                    "table": [[show_scalar(row[key], key) if key in row else "" for key in columns] for row in value]}
        return {"text": count(value),
                "rows": [[str(n), show_scalar(each)] for n, each in enumerate(value, start=1)]}
    return {"text": show_scalar(value)}


def display_inputs(inputs) -> list:
    """A run's or an example's inputs for the pop-up: [name, Display] in their order."""
    if not isinstance(inputs, dict):
        return []
    return [[key_name(key), display(each) if isinstance(each, (list, dict)) else {"text": show_scalar(each, str(key))}]
            for key, each in inputs.items()]


LONG_DECIMAL = re.compile(r"(?<![\w.,])(-?)(\d{1,3}(?:,\d{3})+|\d+)\.(\d+)(?![\w.]|,\d)")


def tidy_numbers(text: str) -> str:
    """Numbers written with more decimals than `show_number` keeps, written as it writes them; every other
    number as it was. For text the harness shows from a model, such as a decision."""
    def tidy(match) -> str:
        sign, whole, decimals = match.groups()
        number = Decimal(sign + whole.replace(",", "") + "." + decimals)
        keeps = 4 if abs(number) < 1 else 2
        return show_number(number) if len(decimals) > keeps else match.group()
    return LONG_DECIMAL.sub(tidy, text)
