"""Layer 1, the plan (SPEC 3): the interview on the core, the plan as a state document, its actions,
routing before there is a plan, resuming, and the `ground` command.

The interview state lives in `core.memory["plan"]` while there is an interview (the state document draws
from it) and in `grounding_state.json` beside the database so a later process can resume. Once the plan is
accepted the confirmed brief in `brief_dir` is the plan.
"""
import json
import re
from pathlib import Path

from ..core import BadAction, NotNow, list_messages
from ..layers import Command, Layer
from .brief import draw, load_brief, summarise_brief
from .interview import PLAN_ACCEPTED, new_state, run_interview
from .research import default_desk

STATE_FILE = "grounding_state.json"
ALREADY = "A plan has already been started."
NOT_WAITING_PLAN = "No plan is waiting to be accepted."
NOT_WAITING_ANSWER = "The interview is not waiting for an answer."
INTRO = "Tell me what you want help with, in your own words. Type /quit to stop."
PLAN_HINT = "Type /accept to accept this plan, or say what is wrong with it."
PREPARED = "This is a prepared plan: {goal}. Ask a question about it, or click a step to see what it does."


def state_path(config) -> Path:
    return Path(config.db_path).parent / STATE_FILE


def phase_of(core) -> str:
    """empty, interview, proposed or accepted."""
    plan = core.memory.get("plan")
    if plan is not None:
        return "proposed" if plan.get("shown") else "interview"
    return "accepted" if _saved(core.memory, core.config) is not None else "empty"


def _saved(memory: dict, config) -> dict | None:
    """The confirmed brief on disk, read again only when the file changed."""
    path = Path(config.brief_dir) / "domain_brief.json"
    try:
        stat = path.stat()
    except OSError:
        memory.pop("plan_file", None)
        return None
    stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = memory.get("plan_file")
    if cached is None or cached[0] != stamp:
        cached = memory["plan_file"] = (stamp, load_brief(path.parent))
    return cached[1]


def contribute(view, state: dict) -> None:
    plan = view.memory.get("plan")
    if plan is not None:
        brief, lookups = plan.get("shown"), plan["lookups"]
        state["phase"] = "proposed" if brief else "interview"
    else:
        brief = _saved(view.memory, view.config)
        lookups = (brief or {}).get("meta", {}).get("lookups") or []
        state["phase"] = "accepted" if brief else "empty"
    if brief:
        state.update(draw(brief, lookups))


# --- Actions ---

def _begin(core, text: str, own: str | None = None) -> dict:
    """Make the interview state for an opening statement, in a new conversation when the current one has
    anything else in it. `own` is the id of the person's message that is already posted, if it is."""
    if core.memory.get("plan") is not None or phase_of(core) != "empty":
        raise NotNow(ALREADY)
    others = [message for message in list_messages(core.conn, core.conversation) if message["id"] != own]
    if others:
        core.new_conversation()
        own = None
    if own is None:
        core.post(text, who="you")
    state = core.memory["plan"] = new_state(core.conversation, text)
    return state


def _run(work, state: dict, answer: dict | None = None) -> None:
    """The interview job: runs until the plan is accepted, then finishes the acceptance."""
    config = work.config
    path = state_path(config)
    run_interview(work, state, desk=work.desk() or default_desk(config, work.conn), brief_dir=config.brief_dir,
                  state_path=path, answer=answer)
    work.session.memory["plan"] = None
    path.unlink(missing_ok=True)
    work.post(PLAN_ACCEPTED, who="harness")
    work.hook("plan_accepted", work)


def start(core, payload: dict) -> None:
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise BadAction("text must be a non-empty string")
    state = _begin(core, text.strip())
    core.queue("main", lambda work: _run(work, state), what="interview", text="reading your request")


def accept_plan(core, payload: dict) -> None:
    if (core.waiting or {}).get("kind") != "plan":
        raise NotNow(NOT_WAITING_PLAN)
    core.answer({"accept": True})


def wrap(core, payload: dict) -> None:
    if (core.waiting or {}).get("kind") != "message" or core.memory.get("plan") is None:
        raise NotNow(NOT_WAITING_ANSWER)
    core.answer({"wrap": True})


def route(core, message: dict):
    """Before there is a plan, a message starts the interview. While there is an interview, no job is
    running (a running one would have taken the message), so the message resumes it."""
    state = core.memory.get("plan")
    if state is not None:
        def resume(work, message):
            _run(work, state, {"text": message["text"], "step": message.get("step")})
        resume.what = "interview"
        return resume
    if phase_of(core) != "empty":
        return None

    def begin(work, message):
        _run(work, _begin(work.session, message["text"], message["id"]))
    begin.what = "interview"
    return begin


def loaded(core) -> None:
    """Resume an interview a former process left unfinished; open a seeded example's empty chat with a word."""
    _resume(core)
    _introduce(core)


def _introduce(core) -> None:
    """In example mode, an accepted plan with an empty chat gets one harness message: a prepared plan, what it
    covers (the first sentence of its goal), and what the person can do."""
    if not core.config.example or core.memory.get("plan") is not None:
        return
    brief = _saved(core.memory, core.config)
    if brief is None or list_messages(core.conn, core.conversation):
        return
    core.post(PREPARED.format(goal=first_sentence((brief.get("goal") or {}).get("text", ""))), who="harness")


def first_sentence(text: str) -> str:
    """The first sentence of a text, without its full stop, its first letter small unless it starts a name."""
    words = " ".join(str(text).split())
    found = re.split(r"(?<=[.!?])\s", words, maxsplit=1)[0].rstrip(".!? ")
    return found[0].lower() + found[1:] if len(found) > 1 and found[0].isupper() and found[1].islower() else found


def _resume(core) -> None:
    path = state_path(core.config)
    if not path.exists():
        return
    if _saved(core.memory, core.config) is not None:        # accepted after all: the file is a leftover
        path.unlink(missing_ok=True)
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        state["messages"], state["lookups"], state["research"], state["words"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    core.memory["plan"] = state
    core.queue("main", lambda work: _run(work, state), what="interview", text="picking up where we left off")


# --- The `ground` command ---

def run_ground(session, *, read=input, write=print) -> int:
    """Drive the interview in the terminal until the plan is accepted. 0 when it was, else 1."""
    from ..terminal import Terminal

    if session.state()["phase"] == "accepted":
        write("The plan is already accepted.")
        return 0
    shown = None

    def reading(prompt):
        nonlocal shown
        plan = session.memory.get("plan") or {}
        if plan.get("proposed") is not None and plan["proposed"] is not shown:
            shown = plan["proposed"]
            write(summarise_brief(shown))
            write(PLAN_HINT)
        return read(prompt)

    def done(state) -> bool:
        return state["phase"] == "accepted" and state["lanes"]["main"] == "idle"

    write(INTRO)
    final = Terminal(session, read=reading, write=write).run(stop=done)
    return 0 if done(final) else 1


def ground(args) -> int:
    from ..config import load_config
    from ..core import Session

    session = Session(load_config())
    try:
        return run_ground(session)
    finally:
        session.close()


LAYER = Layer(
    number=1, name="the plan", schema=Path(__file__).with_name("schema.sql"),
    contribute=contribute,
    actions={"start": start, "accept_plan": accept_plan, "wrap": wrap},
    route=route,
    hooks={"loaded": loaded},
    commands={"ground": Command(help="agree the plan in an interview, in the terminal", run=ground)},
)
