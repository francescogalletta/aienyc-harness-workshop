"""Calls that are the person's (SPEC 6.2): the only real stops.

`ask_decision` posts the question with its options in the chat and waits in the core's waiting slot with
`{"kind": "decision", ...}`. The person picks an option (`choose`) or answers in their own words (`say`); the
analyst gets the choice back as the tool result. The record is a `decisions` row; the state shows it on the
step the decision names.
"""
import json
import re

from .. import db
from ..answers.agent import Turn, reply_figures, tool_result
from ..calc.added import process_steps
from ..calc.builder import plan_of
from ..core import BadAction, NotNow, number_of
from ..core.state import tidy_numbers
from ..model import ToolSpec

SOMETHING_ELSE = "something else"
MAX_DECISIONS = 2
ACCEPT_WORDS = {"yes", "y", "yes.", "ok", "okay", "si", "sí", "/accept"}
NUMBERED = re.compile(r"(?:option\s+)?([1-9])[.)]?", re.IGNORECASE)

ASK_DECISION = ToolSpec(
    name="ask_decision",
    description=("Put a call only the person can make to them: a step of kind judgment, or a choice between ways "
                 "forward that depends on what they want. Give the step it belongs to (`step`, required), the "
                 "question, two to four options in plain words, the option you would suggest (`suggested`, a number "
                 "from 1, optional) with one sentence why, and the run ids of the results it rests on (`runs`). The "
                 "person answers, and you get their choice or their own words."),
    input_schema={"type": "object", "properties": {
        "step": {"type": "string"}, "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "suggested": {"type": "integer"}, "why": {"type": "string"},
        "runs": {"type": "array", "items": {"type": "integer"}}},
        "required": ["step", "question", "options", "runs"]})

TOO_MANY_DECISIONS = ("No more decisions can be put to the person until their next message. Tell the person "
                      "plainly what is still to decide.")
NO_QUESTION = "Say the question in plain words."
BAD_OPTIONS = "Give two to four different options, each in plain words."
NO_STEP = "There is no step {step} in the process. Give the step the decision belongs to."
BAD_SUGGESTED = "suggested must be the number of one of the options, or left out."
NO_WHY = "Say in one sentence why you suggest it."
BAD_RUNS = "runs must be a list of run ids. It may be empty."
UNKNOWN_RUNS = "These runs are not in this conversation: {runs}."
INPUTS_UNBACKED = ("These numbers did not come from the person, the plan, a saved input or a module result: "
                   "{numbers}. Ask the person, or run the module that produces them.")
NO_DECISION = "There is no open decision {decision}."
NOT_WAITING = "That decision is not the one waiting for an answer."
BAD_OPTION = "option must be the number of one of the options."


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def row_view(row) -> dict:
    """A `decisions` row as the Decision of the state document."""
    status = "open" if row["status"] == "open" else "answered"
    return {"id": f"d{row['id']}", "step": row["step_id"], "question": row["question"],
            "options": json.loads(row["options"]), "suggested": row["suggested"], "why": row["why"],
            "status": status, "choice": row["choice"]}


def record_view(row) -> dict:
    return {"decision": f"d{row['id']}", "question": row["question"], "options": json.loads(row["options"]),
            "choice": row["choice"], "words": row["words"], "ts": row["ts"]}


def get_row(conn, decision_id: str):
    try:
        return conn.execute("SELECT * FROM decisions WHERE id = ?", (number_of(decision_id, "d"),)).fetchone()
    except ValueError:
        return None


def rows_of(conn, conversation: str) -> list:
    return conn.execute("SELECT * FROM decisions WHERE conversation = ? ORDER BY id", (conversation,)).fetchall()


def drop_unanswered(conn) -> None:
    """Hook `loaded`: a decision still open when a process starts was asked by a process that is gone."""
    conn.execute("UPDATE decisions SET status = 'dropped' WHERE status = 'open'")
    conn.commit()


def read_choice(answer: str, options: list[str], suggested: int | None) -> str:
    """The person's words as a choice: an option's number or words, `yes` for the suggestion, else `something else`."""
    said = one_line(answer)
    found = NUMBERED.fullmatch(said)
    if found and int(found.group(1)) <= len(options):
        return found.group(1)
    for number, option in enumerate(options, start=1):
        if said.casefold() == one_line(option).casefold():
            return str(number)
    if suggested is not None and said.casefold() in ACCEPT_WORDS:
        return str(suggested)
    return SOMETHING_ELSE


# --- The tool ---

def tools(turn: Turn) -> list:
    return [(ASK_DECISION, ask_decision)]


def run_ids(value) -> list[int] | None:
    """Run ids as the model may write them (`4`, `"4"` or `"r4"`), or None when it is not a list of them."""
    if not isinstance(value, list):
        return None
    found = []
    for each in value:
        if isinstance(each, bool):
            return None
        if isinstance(each, str) and re.fullmatch(r"r?\d+", each.strip()):
            each = int(each.strip().lstrip("r"))
        if not isinstance(each, int):
            return None
        found.append(each)
    return found


def ask_decision(turn: Turn, call) -> dict:
    arguments, conn, work = call.arguments, turn.conn, turn.work

    def refuse(error: str) -> dict:
        turn.record("you.decision_refused", {"error": error, "arguments": arguments})
        return tool_result(call, error, True)

    if turn.extra.get("decisions_asked", 0) >= MAX_DECISIONS:
        return refuse(TOO_MANY_DECISIONS)
    question, options = arguments.get("question"), arguments.get("options")
    if not isinstance(question, str) or not question.strip():
        return refuse(NO_QUESTION)
    if (not isinstance(options, list) or not 2 <= len(options) <= 4
            or not all(isinstance(each, str) and each.strip() for each in options)
            or len({one_line(each).casefold() for each in options}) != len(options)):
        return refuse(BAD_OPTIONS)
    brief = plan_of(work.config)
    step_id = arguments.get("step")
    steps = {each["id"] for each in process_steps(conn, brief)} if brief else set()
    if not isinstance(step_id, str) or step_id not in steps:
        return refuse(NO_STEP.format(step=json.dumps(step_id)))
    suggested, why = arguments.get("suggested"), arguments.get("why")
    if suggested is not None and (not isinstance(suggested, int) or isinstance(suggested, bool)
                                  or not 1 <= suggested <= len(options)):
        return refuse(BAD_SUGGESTED)
    if suggested is not None and (not isinstance(why, str) or not why.strip()):
        return refuse(NO_WHY)
    runs = run_ids(arguments.get("runs"))
    if runs is None:
        return refuse(BAD_RUNS)
    known = {row["id"] for row in conn.execute("SELECT id FROM calc_runs WHERE session_id = ?", (turn.conversation,))}
    unknown = list(dict.fromkeys(each for each in runs if each not in known))
    if unknown:
        return refuse(UNKNOWN_RUNS.format(runs=", ".join(str(each) for each in unknown)))
    why = one_line(why) if suggested is not None else ""
    shown = "\n".join([question, *options, why])
    numbers = turn.unbacked(shown)
    if numbers:
        turn.corrections += 1
        turn.record("ask.correction", {"reason": "ask_decision", "numbers": numbers, "text": json.dumps(arguments)})
        return tool_result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)

    options = [tidy_numbers(one_line(each)) for each in options]     # shown as the harness writes numbers (SPEC 2.4)
    question, why = tidy_numbers(one_line(question)), tidy_numbers(why)
    turn.extra["decisions_asked"] = turn.extra.get("decisions_asked", 0) + 1
    cursor = conn.execute(
        "INSERT INTO decisions (ts, conversation, step_id, question, options, suggested, why, runs)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (db.now(), turn.conversation, step_id, question, json.dumps(options), suggested, why, json.dumps(runs)))
    conn.commit()
    decision_id = f"d{cursor.lastrowid}"
    shape = {"id": decision_id, "step": step_id, "question": question, "options": options, "suggested": suggested,
             "why": why, "status": "open", "choice": None}
    message = work.post(question, who="assistant", kind="decision", step=step_id,
                        data={"decision": shape, "figures": reply_figures(turn, question)})
    conn.execute("UPDATE decisions SET message = ? WHERE id = ?", (message, cursor.lastrowid))
    conn.commit()
    turn.record("you.decision_asked", {"decision": decision_id, "step": step_id, "question": question,
                                       "options": options, "suggested": suggested, "why": why, "runs": runs}, "agent")

    answer = work.wait("decision", decision=decision_id, step=step_id)
    if "choice" in answer:                                   # `choose`: the option's number
        choice = str(answer["choice"])
        words = options[int(choice) - 1]
    else:                                                    # the person's own words
        words = one_line(answer.get("text", ""))
        choice = read_choice(words, options, suggested)
    conn.execute("UPDATE decisions SET choice = ?, words = ?, status = 'answered' WHERE id = ?",
                 (choice, words, cursor.lastrowid))
    conn.commit()
    work.session.update_message(message, {"decision": {**shape, "status": "answered", "choice": choice}})
    turn.record("you.decision", {"decision": decision_id, "step": step_id, "choice": choice, "words": words,
                                 "runs": runs}, "person")
    decided = {row["step_id"] for row in rows_of(conn, turn.conversation) if row["status"] == "answered"}
    result = {"outcome": "decided", "decision": decision_id, "choice": choice,
              "option": None if choice == SOMETHING_ELSE else options[int(choice) - 1], "said": words,
              "judgment_steps": [{"id": each["id"], "name": each["name"], "decided": each["id"] in decided}
                                 for each in process_steps(conn, brief) if each.get("kind") == "judgment"]}
    return tool_result(call, json.dumps(result))


# --- The action ---

def choose(core, payload: dict) -> None:
    """`choose {decision, option}`: the option's text is posted as the person's message, then the wait is answered."""
    decision, option = payload.get("decision"), payload.get("option")
    if isinstance(option, str) and option.isdigit():
        option = int(option)
    if not isinstance(decision, str) or not isinstance(option, int) or isinstance(option, bool):
        raise BadAction("decision must be a decision id and option an option number")
    waiting = core.waiting
    if waiting is None or waiting.get("kind") != "decision" or waiting.get("decision") != decision:
        raise NotNow(NOT_WAITING)
    row = get_row(core.conn, decision)
    if row is None or row["status"] != "open":
        raise NotNow(NO_DECISION.format(decision=decision))
    options = json.loads(row["options"])
    if not 1 <= option <= len(options):
        raise BadAction(BAD_OPTION)
    core.post(options[option - 1], who="you", step=row["step_id"])
    core.answer({"choice": option, "decision": decision})
