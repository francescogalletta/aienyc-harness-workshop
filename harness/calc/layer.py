"""Layer 2, build and tested calculations (SPEC 4).

Adoption of module folders on load and when a plan is accepted, the actions `build`, `confirm_example`,
`confirm_plan_check` and `run_tests`, the step helper (`route`, `helper.py`), the `build` key on every
step (set on calculation steps once the plan is accepted, with added steps drawn after the plan's), the
`build` command and the `steps` expectation of replay.
"""
from pathlib import Path

from .. import db
from ..core import BadAction, NotNow
from ..layers import Command, Expect, Layer
from .adopt import adopt_folders, candidates
from .added import list_added_steps
from .builder import (building_step, confirm_departures, plan_of, record_confirmation,
                      run_step_tests, start_build)
from .helper import rebuild_code, route
from .registry import build_view, find_step, get_build, module_for_step

ADOPTING = "checking the module folders"
TESTING = "running the tests"
NO_STEP = "The plan has no calculation step '{step}'."
NO_EXAMPLE = "Step '{step}' has no example {n}."
ALREADY_YOURS = "Example {n} is already confirmed by you."
BEING_BUILT = "That step is being built right now."
NO_DEPARTURES = "That step has nothing to confirm."
NO_MODULE = "That step has no registered module to test."
OUTCOMES = ("built", "reused", "kept", "not_built")


def contribute(view, state: dict) -> None:
    """The `build` key of every step: null before the plan is accepted and on steps that are not
    calculations, else the whole Build (ARCHITECTURE.md 3.3). Added steps follow the plan's, `in_plan` false."""
    accepted = state.get("phase") == "accepted"
    brief = plan_of(view.config) if accepted else None
    building = building_step(view.memory)
    if accepted:
        for added in list_added_steps(view.conn):
            state["steps"].append({
                "id": added["id"], "number": len(state["steps"]) + 1, "name": added["name"], "kind": "calculation",
                "in_plan": False, "method": added["method"], "formula": added["formula"],
                "produces": added["produces"], "cadence": "", "needs": [], "inputs": [],
                "origin": {"kind": "proposed"}, "particulars": [], "open_questions": []})
    for step in state["steps"]:
        step["build"] = (build_view(view.conn, brief, step["id"], building=step["id"] == building)
                         if accepted and step.get("kind") == "calculation" else None)


# --- Hooks ---

def _adopt(work) -> None:
    brief = plan_of(work.config)
    if brief is not None:
        adopt_folders(work.conn, brief, session_id=work.conversation)


def loaded(core) -> None:
    """Adopt module folders on disk (SPEC 4.6), as a main-lane job, when there is a plan and anything to adopt."""
    brief = plan_of(core.config)
    if brief is not None and candidates(core.conn, brief):
        core.queue("main", _adopt, what="tests", text=ADOPTING)


def plan_accepted(work) -> None:
    _adopt(work)


# --- Actions ---

def _step_id(payload: dict) -> str:
    step = payload.get("step")
    if not isinstance(step, str) or not step:
        raise BadAction("step must be a step id")
    return step


def _calculation(core, payload: dict) -> str:
    step_id = _step_id(payload)
    if find_step(core.conn, plan_of(core.config), step_id) is None:
        raise NotNow(NO_STEP.format(step=step_id))
    return step_id


def build(core, payload: dict) -> None:
    start_build(core)


def confirm_example(core, payload: dict) -> None:
    """The person says an example is right as it stands. A left-out example, or one the module was not
    tested on, queues a rebuild of the code alone."""
    n = payload.get("n")
    if not isinstance(n, int) or isinstance(n, bool):
        raise BadAction("n must be a whole number")
    step_id = _calculation(core, payload)
    example = next((each for each in (get_build(core.conn, step_id) or {}).get("examples", [])
                    if each.get("n") == n), None)
    if example is None:
        raise NotNow(NO_EXAMPLE.format(step=step_id, n=n))
    if example.get("checked_by") == "you":
        raise NotNow(ALREADY_YOURS.format(n=n))
    if building_step(core.memory) == step_id:
        raise NotNow(BEING_BUILT)
    result = record_confirmation(core.conn, step_id, n, session_id=core.conversation)
    if result["rebuild"]:
        core.queue("main", lambda work: rebuild_code(work, step_id), what="build", step=step_id,
                   text="checking the code against your confirmation")


def confirm_plan_check(core, payload: dict) -> None:
    step_id = _calculation(core, payload)
    record = get_build(core.conn, step_id) or {}
    if not record.get("departures") or record.get("departures_confirmed"):
        raise NotNow(NO_DEPARTURES)
    confirm_departures(core.conn, step_id, session_id=core.conversation)


def run_tests(core, payload: dict) -> None:
    step_id = _calculation(core, payload)
    if not module_for_step(core.conn, step_id) and not (get_build(core.conn, step_id) or {}).get("module"):
        raise NotNow(NO_MODULE)

    def run(work):
        try:
            run_step_tests(work.conn, step_id, session_id=work.conversation)
        except ValueError:                      # the module went away since the action
            pass

    core.queue("main", run, what="tests", step=step_id, text=TESTING, key=f"tests:{step_id}")


# --- The `build` command ---

def run_build_command(session, *, write=print) -> int:
    """Press Build in the terminal: build every calculation step, print what happens and one line per step.
    0 when every calculation step is built, else 1."""
    from ..terminal import Terminal

    terminal = Terminal(session, write=write)
    state = session.state()
    if state["phase"] != "accepted":
        write("There is no accepted plan to build yet. Run `python -m harness ground` first.")
        return 1
    applied, reason = session.act("build", {})
    if not applied:
        write(reason)
        return 1
    while True:
        state = session.settle(0.5)
        terminal.show(state)
        if all(lane == "idle" for lane in state["lanes"].values()):
            break
    steps = [step for step in state["steps"] if step.get("build")]
    for step in steps:
        found = step["build"]
        write(f"{step['id']}  {step['name']}: {found['status']}"
              + (f" ({found['examples']} examples, {found['passing']}/{found['tests']} tests)"
                 if found["status"] == "built" else f" ({found['reason']})" if found["reason"] else ""))
    return 0 if steps and all(step["build"]["status"] == "built" for step in steps) else 1


def build_command(args) -> int:
    from ..config import load_config
    from ..core import Session

    session = Session(load_config())
    try:
        return run_build_command(session)
    finally:
        session.close()


# --- Replay expectation `steps` ---

def _validate_steps(value) -> str | None:
    if (not isinstance(value, dict) or not value
            or not all(isinstance(key, str) and outcome in OUTCOMES for key, outcome in value.items())):
        return f"steps must map step ids to one of {', '.join(OUTCOMES)}"
    return None


def _check_steps(value: dict, session) -> dict:
    """`session` is the replay's Session. Compared with `steps` of the latest `build.finished` event."""
    import json

    rows = db.list_events(session.conn, kind="build.finished")
    seen = json.loads(rows[-1]["payload"])["steps"] if rows else {}
    return {"what": "steps", "passed": all(seen.get(step) == outcome for step, outcome in value.items()),
            "seen": seen}


LAYER = Layer(
    number=2, name="build", schema=Path(__file__).with_name("schema.sql"),
    contribute=contribute,
    actions={"build": build, "confirm_example": confirm_example, "confirm_plan_check": confirm_plan_check,
             "run_tests": run_tests},
    route=route,
    hooks={"loaded": loaded, "plan_accepted": plan_accepted},
    commands={"build": Command(help="build and test the calculation modules of the accepted plan", run=build_command)},
    expects={"steps": Expect(validate=_validate_steps, check=_check_steps)},
)
