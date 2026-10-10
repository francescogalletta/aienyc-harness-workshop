"""The plan state document (ARCHITECTURE.md section 3) and the step-line rule (SPEC 2.4).

`start()` makes the top level the core owns; layers add their keys in order;
`finish()` then works out `needs_you`, `line` and `marks` for every step. The
page and the terminal show these as they come.
"""
import json
import re
from decimal import Decimal

PRODUCT = "Financial Advisor Harness"
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEXT_LENGTH = 18
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
        text = "→ " + show_value(last_run.get("output"))
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


def show_value(value) -> str:
    """A run's output on the step line: numbers with thousands separators and their decimals as
    given, dates as given, text cut to 18 characters, a list or an object as `{n} values`."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, Decimal)):
        value = str(value)
    if isinstance(value, (list, dict)):
        return f"{len(value)} values"
    if value is None:
        return "nothing"
    text = str(value) if isinstance(value, str) else json.dumps(value)
    if NUMBER.match(text):
        return group_thousands(text)
    if DATE.match(text):
        return text
    return text if len(text) <= TEXT_LENGTH else text[:TEXT_LENGTH - 1] + "…"


def group_thousands(text: str) -> str:
    """'-1234567.50' -> '-1,234,567.50'; the decimals stay as written."""
    sign = "-" if text.startswith("-") else ""
    whole, dot, decimals = text.lstrip("-").partition(".")
    return f"{sign}{int(whole):,}{dot}{decimals}"
