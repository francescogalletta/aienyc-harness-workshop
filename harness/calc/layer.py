"""Layer 2, build and tested calculations (SPEC 4).

Package A2a wired the engine: adoption of module folders on load and when a plan is accepted, the
`build` action (the unattended build), and the `build` key on calculation steps with added steps drawn
after the plan's. Package A2b adds the step helper (`route`), the actions `confirm_example`,
`confirm_plan_check` and `run_tests`, the `build` command and replay expectations.
"""
from pathlib import Path

from ..layers import Layer
from .adopt import adopt_folders, candidates
from .added import list_added_steps
from .builder import building_step, plan_of, start_build
from .registry import build_view

ADOPTING = "checking the module folders"


def contribute(view, state: dict) -> None:
    """`build` on every step (null but on calculation steps), and the added steps after the plan's."""
    if state.get("phase") != "accepted":
        return
    brief = plan_of(view.config)
    building = building_step(view.memory)
    for added in list_added_steps(view.conn):
        state["steps"].append({
            "id": added["id"], "number": len(state["steps"]) + 1, "name": added["name"], "kind": "calculation",
            "in_plan": False, "method": added["method"], "formula": added["formula"],
            "produces": added["produces"], "cadence": "", "needs": [], "inputs": [],
            "origin": {"kind": "proposed"}, "particulars": [], "open_questions": []})
    for step in state["steps"]:
        step["build"] = (build_view(view.conn, brief, step["id"], building=step["id"] == building)
                         if step.get("kind") == "calculation" else None)


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


def build(core, payload: dict) -> None:
    start_build(core)


LAYER = Layer(
    number=2, name="build", schema=Path(__file__).with_name("schema.sql"),
    contribute=contribute,
    actions={"build": build},
    hooks={"loaded": loaded, "plan_accepted": plan_accepted},
)
