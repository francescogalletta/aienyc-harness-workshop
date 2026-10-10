"""The step helper (SPEC 4.7): the person clicks a calculation step and says something about it.

One model call with `step_helper.md` and the tool `respond` says what they meant: correct an example,
confirm an example (or the plan check), explain, keep a note about their real situation, or rebuild the
step. The harness checks the call before it does anything: an example that exists, an answer that fits the
output type and its shape, and every number of an answer or an explanation backed by the person's words or
what the helper was shown. A call that fails a check gets `HELPER_UNCLEAR` and nothing changes.

What other layers call: `wants(core, step_id)` (layer 3 leaves exactly these messages to this route).
"""
import json
from pathlib import Path

from ..model import ToolSpec
from .builder import build_step, confirm_departures, format_sections, plan_of, record_confirmation
from .notes import add_note
from .provenance import unbacked
from .registry import find_step, get_build, step_status
from .values import from_json

HELPER_UNCLEAR = ("I could not tell what to change. Say which example and the right answer, with every number "
                  "written out.")
NOTE_KEPT = "I have kept that about {name}. It is used when the calculation runs with your real figures."
EXAMPLE_CONFIRMED = "Example {n} of {name} is confirmed by you."
EXAMPLE_CORRECTED = "Example {n} of {name} now has your answer. I am checking the code against it."
DEPARTURES_CONFIRMED = "The differences between {name} and the plan are confirmed."
REBUILDING = "I have kept that and I am building {name} again."
STEP_BUILT = "{name} is built and tested."
STEP_NOT_BUILT = "{name} is not built: {reason}. Click it to see why."
THINKING = "reading what you said"
CHECKING_CODE = "checking the code against your answer"

ACTIONS = ("correct", "confirm", "explain", "note", "rebuild")
RESPOND = ToolSpec(
    name="respond",
    description=("Say what the person meant: correct an example's answer, confirm an example or the plan check, "
                 "explain, keep a note about their situation, or rebuild the step. Call it exactly once."),
    input_schema={"type": "object", "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "example": {"type": "integer"},
        "answer": {},
        "message": {"type": "string"}}, "required": ["action"]})


def _departures(record: dict) -> bool:
    return bool(record.get("departures")) and not record.get("departures_confirmed")


def wants(core, step_id: str) -> bool:
    """Whether a message about this step belongs to the helper rather than to the analyst (SPEC 4.7): the
    step is not built, has an example the two passes disagreed on, or has departures not confirmed.
    `core` is the Session (or anything with `conn` and `config`)."""
    brief = plan_of(core.config)
    if find_step(core.conn, brief, step_id) is None:
        return False
    record = get_build(core.conn, step_id) or {}
    return (step_status(core.conn, brief, step_id)[0] == "not_built"
            or any(not each.get("checked_by") for each in record.get("examples", []))
            or _departures(record))


def route(core, message: dict):
    """In phase `accepted`, every message with a calculation step attached is the helper's."""
    from ..grounding.layer import phase_of

    step_id = message.get("step")
    if not step_id or phase_of(core) != "accepted":
        return None
    if find_step(core.conn, plan_of(core.config), step_id) is None:
        return None
    return handle


def handle(work, message: dict) -> None:
    """One helper turn, a main-lane job."""
    step_id = message["step"]
    brief = plan_of(work.config)
    step = find_step(work.conn, brief, step_id)
    if step is None:
        return
    record = get_build(work.conn, step_id) or {}
    work.progress(THINKING, step=step_id, what="helper")
    sections = {"step": step, "spec": record.get("spec"),
                "departures": {"list": record.get("departures", []),
                               "confirmed": bool(record.get("departures_confirmed"))},
                "examples": record.get("examples", []), "disagreement": record.get("disagreement", []),
                "reason": record.get("reason", ""), "message": message["text"]}
    system = Path(__file__).with_name("step_helper.md").read_text(encoding="utf-8")
    response = work.model.complete(system=system, messages=[{"role": "user", "content": format_sections(sections)}],
                                  tools=[RESPOND])
    call = next((each for each in response.tool_calls if each.name == "respond"), None)
    arguments = call.arguments if call is not None and isinstance(call.arguments, dict) else {}
    action = arguments.get("action")
    outcome = _apply(work, step, record, message, arguments) if action in ACTIONS else False
    work.record("build.helper", {"step": step_id, "action": action, "example": arguments.get("example"),
                                 "accepted": outcome}, "agent")
    if not outcome:
        work.post(HELPER_UNCLEAR, who="harness", step=step_id)


handle.what = "helper"


def _apply(work, step: dict, record: dict, message: dict, arguments: dict) -> bool:
    """Do what the checked call says. False when a check failed (nothing changed)."""
    step_id, name, action = step["id"], step["name"], arguments["action"]
    post = lambda text, who="harness": work.post(text, who=who, step=step_id)      # noqa: E731
    session_id = work.conversation
    examples = {each.get("n"): each for each in record.get("examples", [])}
    n = arguments.get("example")
    if action == "explain":
        text = arguments.get("message")
        if not isinstance(text, str) or not text.strip():
            return False
        shown = [message["text"], step, record.get("spec"), record.get("departures"), record.get("examples"),
                 record.get("disagreement"), record.get("reason")]
        if unbacked(text, shown):
            return False
        post(text.strip(), "assistant")
        return True
    if action == "note":
        add_note(work.conn, step_id=step_id, text=message["text"], session_id=session_id)
        post(NOTE_KEPT.format(name=name))
        return True
    if action == "rebuild":
        add_note(work.conn, step_id=step_id, text=message["text"], session_id=session_id)
        post(REBUILDING.format(name=name))
        _report(work, step, build_step(work, step_id))
        return True
    if action == "confirm" and n == 0:
        try:
            confirm_departures(work.conn, step_id, session_id=session_id)
        except ValueError:
            return False
        post(DEPARTURES_CONFIRMED.format(name=name))
        return True
    example = examples.get(n) if isinstance(n, int) and not isinstance(n, bool) else None
    if example is None:
        return False
    if action == "confirm":
        answer = None
    else:                                           # correct
        answer = arguments.get("answer")
        if answer is None or not _answer_fits(record, example, answer, message["text"]):
            return False
    try:
        result = record_confirmation(work.conn, step_id, n, answer=answer, session_id=session_id)
    except ValueError:
        return False
    corrected = answer is not None
    post((EXAMPLE_CORRECTED if corrected else EXAMPLE_CONFIRMED).format(n=n, name=name))
    if result["rebuild"]:
        rebuild_code(work, step_id)
    return True


def _answer_fits(record: dict, example: dict, answer, words: str) -> bool:
    """The answer has the output type and the shape of `expected`, and every number in it is in the
    person's message or in the example (its inputs, its answer, the other pass's answer)."""
    spec = record.get("spec")
    if not spec:
        return False
    try:
        from_json(answer, spec["output"]["type"])
    except ValueError:
        return False
    if not _same_shape(example.get("expected"), answer):
        return False
    shown = [words, example.get("inputs"), example.get("expected"), example.get("second_pass")]
    return not unbacked(json.dumps(answer, ensure_ascii=False), shown)


def _same_shape(expected, answer) -> bool:
    if isinstance(expected, dict):
        return (isinstance(answer, dict) and expected.keys() == answer.keys()
                and all(_same_shape(expected[key], answer[key]) for key in expected))
    if isinstance(expected, list):
        return (isinstance(answer, list) and len(expected) == len(answer)
                and all(_same_shape(left, right) for left, right in zip(expected, answer)))
    return not isinstance(answer, (dict, list))


def _report(work, step: dict, result: dict) -> None:
    if result["outcome"] == "not_built":
        work.post(STEP_NOT_BUILT.format(name=step["name"], reason=result["reason"]), who="harness",
                  step=step["id"])
    else:
        work.post(STEP_BUILT.format(name=step["name"]), who="harness", step=step["id"])


def rebuild_code(work, step_id: str) -> dict:
    """Build a step again from its stored spec and its examples as they now stand (no model call when the
    code already passes) and say how it ended. A main-lane job, or a step of one."""
    step = find_step(work.conn, plan_of(work.config), step_id)
    if step is None:
        raise ValueError(f"the plan has no calculation step '{step_id}'")
    work.progress(CHECKING_CODE, step=step_id)
    result = build_step(work, step_id, code_only=True)
    _report(work, step, result)
    return result
