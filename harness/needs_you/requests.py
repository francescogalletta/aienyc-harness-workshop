"""Missing calculations (SPEC 6.3): the analyst asks for a module to be built and it is built at once, without
asking the person. They are told in the chat; a calculation the plan has no step for appears as an added step,
"not in the plan".
"""
import json
import time

from ..answers.agent import Turn, tool_result
from ..calc.added import add_step, process_steps
from ..calc.builder import build_step, plan_of
from ..calc.notes import add_note
from ..calc.registry import get_module, step_status
from ..model import ToolSpec

MAX_REQUESTS = 2
NAME_LENGTH = 60
CASES = ("step", "new", "replace")

BUILT_NOT_IN_PLAN = "A calculation that is not in the plan was needed: {name}. It is built and tested."
BUILT_STEP = "Step {number} {name} is built and tested."
BUILDING = "Building {name}, which this answer needs. It is written and tested first, so it can take a minute."
NOT_BUILT_STEP = "Step {number} {name} could not be built. Click it to see why."

REQUEST_MODULE = ToolSpec(
    name="request_module",
    description=("Ask for one module to be built, when no module can do what is needed. `case` is step (a "
                 "calculation step of the process has no working module, or must be built again; `target` is its "
                 "id), new (the process has no step for it; leave `target` empty; give a short `name` for the "
                 "step) or replace (a module does not fit what the person has; `target` is its name). Say in plain "
                 "words what must be worked out, from what, giving what, how, and why it is needed now. It is built "
                 "at once and the person is told; you do not write or see code."),
    input_schema={"type": "object", "properties": {
        "case": {"type": "string", "enum": list(CASES)}, "target": {"type": "string"}, "name": {"type": "string"},
        "works_out": {"type": "string"}, "from_what": {"type": "string"}, "gives": {"type": "string"},
        "formula": {"type": "string"}, "why": {"type": "string"}},
        "required": ["case", "works_out", "from_what", "gives", "formula", "why"]})

TOO_MANY_REQUESTS = ("No more builds can be asked for until the person's next message. Tell the person plainly "
                     "what cannot be answered yet.")
BAD_CASE = "case must be step, new or replace."
MISSING_WORDS = "Say in plain words: {fields}."
NOT_A_STEP = "There is no calculation step '{target}' in the process."
ALREADY_BUILT = ("Step '{target}' already has the module '{module}', built and not stale. Run it, or ask to "
                 "replace it if it does not fit.")
NOT_REGISTERED = "There is no registered module called '{name}'."
NO_STEP = "The module '{name}' carries out step {step}, which the process no longer has."
INPUTS_UNBACKED = ("These numbers did not come from the person, the plan, a saved input or a module result: "
                   "{numbers}. Ask the person, or run the module that produces them.")
BUILD_FAILED = "The build stopped with an error: {error}"


def tools(turn: Turn) -> list:
    return [(REQUEST_MODULE, request_module)]


def short_name(arguments: dict, works_out: str) -> str:
    name = " ".join(str(arguments.get("name") or "").split())
    if name:
        return name[:NAME_LENGTH]
    text = " ".join(works_out.split())
    return text if len(text) <= NAME_LENGTH else text[:NAME_LENGTH].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def number_of_step(conn, brief, step_id: str) -> int:
    ids = [each["id"] for each in process_steps(conn, brief)]
    return ids.index(step_id) + 1 if step_id in ids else len(ids)


def request_module(turn: Turn, call) -> dict:
    arguments, conn, work = call.arguments, turn.conn, turn.work

    def refuse(error: str) -> dict:
        turn.record("you.request_refused", {"error": error, "arguments": arguments})
        return tool_result(call, error, True)

    case, target = arguments.get("case"), arguments.get("target")
    target = target.strip() if isinstance(target, str) else ""
    if turn.extra.get("requests", 0) >= MAX_REQUESTS:
        return refuse(TOO_MANY_REQUESTS)
    if case not in CASES:
        return refuse(BAD_CASE)
    fields = ("works_out", "from_what", "gives", "formula", "why")
    missing = [key for key in fields if not isinstance(arguments.get(key), str) or not arguments[key].strip()]
    if missing:
        return refuse(MISSING_WORDS.format(fields=", ".join(missing)))
    works_out, from_what, gives, formula, why = (" ".join(arguments[key].split()) for key in fields)
    brief = plan_of(work.config)
    steps = {each["id"]: each for each in process_steps(conn, brief)} if brief else {}
    rebuild, registered = None, None
    if case == "step":
        if target not in steps or steps[target].get("kind") != "calculation":
            return refuse(NOT_A_STEP.format(target=target))
        status, _ = step_status(conn, brief, target)
        if status == "built":
            from ..calc.registry import module_for_step
            return refuse(ALREADY_BUILT.format(target=target, module=module_for_step(conn, target)))
    elif case == "replace":
        registered = get_module(conn, target)
        if registered is None:
            return refuse(NOT_REGISTERED.format(name=target))
        if registered["spec"].get("step_id") not in steps:
            return refuse(NO_STEP.format(name=target, step=registered["spec"].get("step_id")))
    block = "\n".join([works_out, from_what, gives, formula, why])
    numbers = turn.unbacked(block)
    if numbers:
        turn.corrections += 1
        turn.record("ask.correction", {"reason": "request_module", "numbers": numbers, "text": json.dumps(arguments)})
        return tool_result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)

    turn.extra["requests"] = turn.extra.get("requests", 0) + 1       # counts whatever the outcome
    if case == "new":
        step = add_step(conn, name=short_name(arguments, works_out), formula=formula, needs=from_what,
                        produces=gives, reason=why, session_id=turn.conversation)
    elif case == "replace":
        step = steps[registered["spec"]["step_id"]]
        add_note(conn, step_id=step["id"], text=block, session_id=turn.conversation)
        rebuild = target
    else:
        step = steps[target]
    work.changed()
    work.post(BUILDING.format(name=step["name"]), who="harness", step=step["id"])        # at once, not after the build
    started = time.monotonic()
    try:
        built = build_step(work, step, rebuild=rebuild)
    except Exception as error:                       # the build itself broke: the analyst is told, the step stays unbuilt
        built = {"step": step["id"], "outcome": "not_built", "module": None, "reason": BUILD_FAILED.format(error=error)}
    seconds = round(time.monotonic() - started, 1)
    work.progress("working out the answer", what="answer")
    if built["outcome"] == "not_built":
        result = {"outcome": "not_built", "step": built["step"], "reason": built["reason"]}
        told = NOT_BUILT_STEP
    else:
        result = {"outcome": built["outcome"], "step": built["step"], "module": built["module"],
                  "spec": get_module(conn, built["module"])["spec"]}
        told = BUILT_NOT_IN_PLAN if case == "new" else BUILT_STEP
    work.post(told.format(number=number_of_step(conn, brief, step["id"]), name=step["name"]),
              who="harness", step=step["id"])
    turn.record("you.module_requested", {"case": case, "target": target, "step": step["id"], "arguments": arguments,
                                         "outcome": result["outcome"], "seconds": seconds}, "agent")
    return tool_result(call, json.dumps(result))
