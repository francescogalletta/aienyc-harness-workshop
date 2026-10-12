"""Branches (SPEC 6.4): the person opens a branch beside the chat on one subject of the plan (a value, a result,
an assumption, a step, an input, a decision or the whole plan), at any time and in any phase. A sub-agent with its
own context answers on the side lane, so the main lane goes on working (or waiting) meanwhile. It explains and
explores; it cannot run, save, build or decide anything. Once the plan is accepted it may propose a change the
person asked for (`propose_change`, `join.py`); the harness applies it only on the person's yes.

Its reply is number-checked against what it was given, the thread's own messages and its lookups. A lookup
sends only a general term out, through the research desk.
"""
import json
import sqlite3
from pathlib import Path

from ..answers.agent import step_of_module, tool_result
from ..answers.rerun import last_answer_runs
from ..calc.builder import format_sections
from ..calc.provenance import unbacked
from ..core import BadAction, NotNow, add_thread, list_messages, list_threads, number_of, set_outcome
from ..grounding.research import as_lookup, default_desk
from ..model import ToolSpec
from . import join

PROMPT = Path(__file__).with_name("side.md")
TITLE_LENGTH = 45
MAX_PERSON_MESSAGES = 6
MAX_LOOKUPS = 3
MAX_CALLS = 8
RECENT_CHAT = 10

LOOK_UP = ToolSpec(
    name="look_up",
    description=("Look up the standard meaning of a finance term or practice that the plan's glossary does not "
                 "explain. Send only a short general term or question, a few words, never anything about the "
                 "person. Returns a definition and its sources."),
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})

THREAD_FULL = "This side thread has reached its limit of {limit} messages. Start a new one."
NO_THREAD = "There is no such side thread."
NUMBERS_CORRECTION = ("[harness] Your reply was not shown. These numbers were not in what you were given, in the "
                      "person's messages here or in a lookup result: {numbers}. Do no arithmetic. Leave them out, "
                      "or say the main chat can work it out with a tested calculation. Then reply again.")
WITHHELD = ("(The answer was held back, because it held numbers that nothing here gave: {numbers}. "
            "The main chat works numbers out with tested calculations.)")
EMPTY_REPLY = "[harness] Your reply was empty. Answer the person, or ask them one question."
LOOKUP_LIMIT = "No more lookups are allowed in this thread. Answer with what you have, and say so."
LOOKUP_REFUSED = "The lookup was refused: {error}. Send a short general term only."
NOT_FOUND = ("No source was found for that. Say so plainly; do not give a definition from memory as if it were "
             "sourced.")
NO_SUCH_TOOL = "There is no tool called {name} here."
STOPPED = "(The harness stopped working on this, because it took too many steps. Try asking in a simpler way.)"


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def title_of(text: str) -> str:
    """The first words of the text, cut to 45 characters: what the branch is about, in the words that opened it
    (the branch's first line names its subject)."""
    title = one_line(text)
    return title if len(title) <= TITLE_LENGTH else title[:TITLE_LENGTH - 1].rstrip() + "…"


# --- The action ---

SUBJECT_KEYS = {"plan": (), "step": ("step",), "input": ("input", "step"),
                "value": ("run", "key", "value", "input", "step"), "result": ("run", "step", "value"),
                "assumption": ("run", "step", "text", "assumption"), "decision": ("node",)}


def _run_inputs(conn, conversation: str, run) -> dict | None:
    """The inputs of a run of this conversation, or None when there is no such run."""
    try:
        row = conn.execute("SELECT inputs FROM calc_runs WHERE id = ? AND session_id = ?",
                           (number_of(run, "r"), conversation)).fetchone()
    except (ValueError, sqlite3.Error):
        return None
    if row is None:
        return None
    inputs = json.loads(row["inputs"])
    return inputs if isinstance(inputs, dict) else {}


def check_subject(core, subject, state: dict) -> dict:
    """A Subject of ARCHITECTURE.md 3.5 whose ids exist (a run of this conversation, a plan step or input, an
    assumption, a node), with only its own keys. Anything else is a BadAction."""
    if not isinstance(subject, dict) or subject.get("kind") not in SUBJECT_KEYS:
        raise BadAction("subject must be an object with a known kind")
    kind = subject["kind"]
    found = {"kind": kind, **{key: subject.get(key) for key in SUBJECT_KEYS[kind]}}
    for key in SUBJECT_KEYS[kind]:
        if found[key] is not None and not isinstance(found[key], str):
            raise BadAction(f"subject {key} must be a string or null")
    steps = {step["id"] for step in state["steps"]}
    conn = core.conn

    def need(condition: bool, what: str) -> None:
        if not condition:
            raise BadAction(f"subject: {what}")

    if kind == "step":
        need(found["step"] in steps, f"there is no step {found['step']!r}")
    if kind in ("input", "value", "result", "assumption") and found.get("step") is not None:
        need(found["step"] in steps, f"there is no step {found['step']!r}")
    if kind == "input":
        need(found["input"] in state["inputs"], f"there is no input {found['input']!r}")
    if kind == "value" and found["input"] is not None:
        need(found["input"] in state["inputs"], f"there is no input {found['input']!r}")
    if kind in ("value", "result", "assumption"):
        inputs = _run_inputs(conn, core.conversation, found["run"])
        need(inputs is not None, f"there is no run {found['run']!r} in this conversation")
        if kind == "value":
            need(bool(found["key"]) and found["key"] in inputs, f"the run takes no {found['key']!r}")
            need(found["value"] is not None, "a value needs its value")
        if kind == "result":
            need(found["value"] is not None, "a result needs its value")
        if kind == "assumption":
            need(bool((found["text"] or "").strip()), "an assumption needs its sentence")
            if found["assumption"] is not None:
                try:
                    known = conn.execute("SELECT 1 FROM assumptions WHERE id = ?",
                                         (number_of(found["assumption"], "a"),)).fetchone()
                except ValueError:
                    known = None
                need(known is not None, f"there is no assumption {found['assumption']!r}")
    if kind == "decision":
        try:
            known = conn.execute("SELECT 1 FROM trunk WHERE id = ? AND conversation = ?",
                                 (number_of(found["node"], "n"), core.conversation)).fetchone()
        except ValueError:
            known = None
        need(known is not None, f"there is no decision {found['node']!r}")
    return found


def side(core, payload: dict) -> None:
    """`side {text, step?, thread?, subject?}`: open a branch on a subject (SPEC 6.4), or say something in one (side
    or review). Opening one makes the person's other side branches that wait on nothing dead (12.5); a message
    in a dead side branch opens it again."""
    text, step, thread = payload.get("text"), payload.get("step"), payload.get("thread")
    subject = payload.get("subject")
    if not isinstance(text, str) or not text.strip():
        raise BadAction("text must be a non-empty string")
    if step is not None and not isinstance(step, str):
        raise BadAction("step must be a string or null")
    if thread is not None and not isinstance(thread, str):
        raise BadAction("thread must be a string or null")
    text, conn = text.strip(), core.conn
    if thread is None:
        state = core.state()
        if subject is not None:
            subject = check_subject(core, subject, state)
            step = subject.get("step")
        elif step:
            if step not in {each["id"] for each in state["steps"]}:
                raise BadAction(f"there is no step {step!r}")
            subject = {"kind": "step", "step": step}
        else:
            subject = {"kind": "plan"}
        for other in list_threads(conn, core.conversation):
            if join.dies(conn, other):
                join.kill(core, other["id"], "new_branch")
        thread = add_thread(conn, core.conversation, kind="side", title=title_of(text), step=step or None,
                            origin="you", subject=subject)
        core.record("you.side_opened", {"thread": thread, "step": step or None, "title": title_of(text),
                                        "subject": subject}, "person")
    else:
        try:
            wanted = number_of(thread, "t")
        except ValueError:
            raise BadAction(f"not a thread id: {thread!r}") from None
        row = conn.execute("SELECT * FROM threads WHERE id = ? AND conversation = ?",
                           (wanted, core.conversation)).fetchone()
        if row is None:
            raise NotNow(NO_THREAD)
        said = conn.execute("SELECT COUNT(*) FROM messages WHERE thread = ? AND who = 'you'", (wanted,)).fetchone()[0]
        if said >= MAX_PERSON_MESSAGES:
            raise NotNow(THREAD_FULL.format(limit=MAX_PERSON_MESSAGES))
        step = row["step"]
        if row["kind"] == "side" and row["outcome"] == "dead":
            set_outcome(conn, thread, "open")
            core.record("you.branch_reopened", {"thread": thread}, "person")
    message = core.post(text, who="you", thread=thread)
    core.record("you.side_message", {"thread": thread, "message": message, "text": text}, "person")
    upto = number_of(message, "m")
    core.queue("side", lambda work: reply(work, thread, upto), what="side", step=step or None,
               text="answering", thread=thread)


# --- What the side assistant is given (SPEC 6.4: "it sees") ---

def texts(items) -> list[str]:
    return [one_line(each["text"]) for each in items or []]


def plan_section(state: dict) -> dict:
    context = state.get("context") or {}
    goal = state.get("goal") or {}
    steps = [{"id": step["id"], "number": step["number"], "name": step["name"], "kind": step["kind"],
              "in_plan": step["in_plan"], "method": step["method"], "formula": step["formula"],
              "needs": step["needs"], "produces": step["produces"],
              "particulars": [{"what": each["text"], "handling": each.get("handling", "")}
                              for each in step["particulars"]],
              "open_questions": texts(step["open_questions"])}
             for step in state["steps"]]
    inputs = [{"name": each["name"], "description": each["description"], "value": each.get("value")}
              for each in state["inputs"].values()]
    return {"phase": state["phase"], "goal": goal.get("text", ""),
            "in scope": texts(context.get("scope_in")), "out of scope": texts(context.get("scope_out")),
            "assumptions": [{"what": each["text"], "handling": each.get("handling", "")}
                            for each in context.get("assumptions", [])],
            "definition of done": texts(context.get("done")),
            "open questions": texts(context.get("open_questions")),
            "glossary": [{"term": each["term"], "definition": each["definition"]}
                         for each in context.get("glossary", [])],
            "inputs": inputs, "steps": steps}


def step_section(state: dict, step_id: str | None) -> dict | None:
    """The attached step in detail: its spec in plain words, examples and who checked them, last run,
    unconfirmed assumptions, decisions and challenges. Never the code."""
    step = next((each for each in state["steps"] if each["id"] == step_id), None) if step_id else None
    if step is None:
        return None
    build = step.get("build") or {}
    found = {"id": step["id"], "name": step["name"], "kind": step["kind"], "in_plan": step["in_plan"],
             "formula": step["formula"], "needs": step["needs"], "produces": step["produces"]}
    if build:
        found["build"] = {"status": build["status"], "reason": build["reason"],
                          "spec": build.get("spec"), "plan_check": build.get("plan_check"),
                          "examples": [{"n": each["n"], "inputs": each["inputs"], "expected": each["expected"],
                                        "working": each["working"], "checked_by": each["checked_by"],
                                        "second_pass": each["second_pass"]} for each in build["example_list"]],
                          "disagreement": [{key: value for key, value in each.items() if key != "shown"}
                                           for each in build["disagreement"]]}
    run = step.get("last_run")
    if run:
        found["last run"] = {"inputs": run["inputs"], "output": run["output"], "assumptions": run["assumptions"]}
    if step.get("unconfirmed"):
        found["unconfirmed"] = [each["text"] for each in step["unconfirmed"]]
    if step.get("calls"):
        found["decisions"] = [{"question": each["question"], "options": each["options"], "choice": each["choice"],
                               "words": each["words"]} for each in step["calls"]["records"]]
    challenges = [thread["challenge"] for thread in state.get("threads", [])
                  if thread.get("challenge") and thread["challenge"]["step"] == step["id"]]
    if challenges:
        found["challenges"] = [{"concern": each["concern"], "proposal": each["proposal"], "status": each["status"]}
                               for each in challenges]
    return found


def run_section(conn, run: str | None, state: dict) -> dict | None:
    """A run as the side assistant reads it: its module, step, inputs and output."""
    try:
        row = conn.execute("SELECT * FROM calc_runs WHERE id = ?", (number_of(run, "r"),)).fetchone()
    except ValueError:
        return None
    if row is None:
        return None
    step = step_of_module(conn, row["module"], {each["id"] for each in state["steps"]})
    return {"run": f"r{row['id']}", "module": row["module"], "step": step,
            "inputs": json.loads(row["inputs"]), "output": json.loads(row["output"])}


def subject_section(conn, conversation: str, state: dict, subject: dict) -> dict:
    """The branch's subject with what it points at (SPEC 6.4)."""
    kind = subject.get("kind")
    found = dict(subject)
    steps = {each["id"]: each for each in state["steps"]}
    if subject.get("step") in steps:
        found["step name"] = steps[subject["step"]]["name"]
    if kind == "plan":
        found["about"] = "the whole plan"
    if subject.get("input") in state["inputs"]:
        entry = state["inputs"][subject["input"]]
        found["input name"] = entry["name"]
        found["saved value"] = entry.get("value")
    if subject.get("run"):
        found["the run"] = run_section(conn, subject["run"], state)
    if kind == "assumption":
        row = conn.execute("SELECT status, words FROM assumptions WHERE key = ?",
                           (" ".join(str(subject.get("text") or "").split()).casefold(),)).fetchone()
        if row is not None:
            found["status"] = row["status"]
            if row["words"]:
                found["their words"] = row["words"]
    if kind == "decision":
        node = next((each for each in state["history"]["trunk"] if each["id"] == subject.get("node")), None)
        if node is not None:
            found["decided"] = {"who": node["who"], "kind": node["kind"], "text": node["text"],
                                "change": node["change"]}
    return found


def last_answer_section(conn, conversation: str, state: dict) -> list[dict]:
    """Each run of the main chat's last answer: module, step, inputs, output."""
    found = (run_section(conn, f"r{run}", state) for run in last_answer_runs(conn, conversation))
    return [each for each in found if each is not None]


def sections_of(state: dict, thread: dict, conn=None, conversation: str = "") -> dict:
    recent = [{"who": each["who"], "text": each["text"]} for each in state["chat"][-RECENT_CHAT:]]
    challenge = thread.get("challenge") if thread["kind"] == "review" else None
    found = {"plan": plan_section(state), "step": step_section(state, thread["step"]), "recent chat": recent,
             "challenge": ({"concern": challenge["concern"], "proposal": challenge["proposal"],
                            "kind": challenge["kind"], "status": challenge["status"]} if challenge else None)}
    if conn is not None:
        found["subject"] = subject_section(conn, conversation, state, thread.get("subject") or {"kind": "plan"})
        found["last answer"] = last_answer_section(conn, conversation, state) if state["phase"] == "accepted" else []
    return found


def system_prompt(sections: dict) -> str:
    return PROMPT.read_text(encoding="utf-8").replace("{context}", format_sections(sections))


def model_messages(rows: list[dict], upto: int, kind: str) -> list[dict]:
    """The thread as the model reads it: the person's words and its own earlier replies up to the message it
    answers (a reviewer's words are in `challenge`; a withheld notice is not a reply it gave)."""
    messages = []
    for row in rows:
        if int(row["id"][1:]) > upto or row["kind"] == "withheld" or row["who"] == "reviewer":
            continue
        role = "user" if row["who"] == "you" else "assistant"
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + row["text"]
        else:
            messages.append({"role": role, "content": row["text"]})
    return messages


# --- A reply ---

def lookups_so_far(conn, conversation: str, thread: str) -> int:
    from .. import db
    return sum(1 for row in db.list_events(conn, session_id=conversation, kind="you.side_lookup")
               if json.loads(row["payload"]).get("thread") == thread)


def reply(work, thread_id: str, upto: int) -> None:
    """The side lane job: one reply to the person's message `upto` in the thread."""
    conn, conversation = work.conn, work.conversation
    thread = next((each for each in list_threads(conn, conversation) if each["id"] == thread_id), None)
    if thread is None:
        return
    work.progress("reading the plan", thread=thread_id)
    state = work.session.state()
    thread = next((each for each in state["threads"] if each["id"] == thread_id), thread)
    sections = sections_of(state, thread, conn, conversation)
    proposing = thread["kind"] == "side" and state["phase"] == "accepted"
    tools = [LOOK_UP, join.PROPOSE_CHANGE] if proposing else [LOOK_UP]
    person = [row["text"] for row in list_messages(conn, conversation, thread_id)
              if row["who"] == "you" and int(row["id"][1:]) <= upto]
    made = []
    system = system_prompt(sections)
    rows = list_messages(conn, conversation, thread_id)
    messages = model_messages(rows, upto, thread["kind"])
    thread_words = [row["text"] for row in rows if row["kind"] != "withheld" and int(row["id"][1:]) <= upto]
    found, shown, used = [], [], lookups_so_far(conn, conversation, thread_id)
    desk, corrected = None, False

    def numbers_of(text: str) -> list[str]:
        return unbacked(text, [sections, thread_words, found])

    def finish(text: str, kind: str = "text") -> None:
        data = {"sources": shown} if shown and kind == "text" else {}
        message = work.post(text, who="assistant", kind=kind, thread=thread_id, data=data)
        if kind == "text":
            work.record("you.side_reply", {"thread": thread_id, "message": message, "text": text,
                                           "sources": shown}, "agent")

    for _ in range(MAX_CALLS):
        work.progress("thinking", thread=thread_id)
        response = work.model.complete(system=system, messages=messages, tools=tools)
        if response.tool_calls:
            results = []
            for call in response.tool_calls:
                if call.name == "propose_change" and proposing:
                    result = join.propose(work, thread, call, state, person, made)
                    found.append(result["content"])
                    results.append(result)
                    continue
                if call.name != "look_up":
                    results.append(tool_result(call, NO_SUCH_TOOL.format(name=call.name), True))
                    continue
                if used >= MAX_LOOKUPS:
                    results.append(tool_result(call, LOOKUP_LIMIT, True))
                    continue
                used += 1
                query = str(call.arguments.get("query", "")).strip()
                work.progress("looking up: " + query, thread=thread_id)
                desk = desk or work.desk() or default_desk(work.config, conn)
                entry = desk.look_up_general(query)
                work.record("you.side_lookup", {"thread": thread_id, "query": query, "status": entry["status"]},
                            "agent")
                if entry["status"] == "failed":
                    results.append(tool_result(call, LOOKUP_REFUSED.format(error=entry["error"]), True))
                elif entry["status"] == "not_found":
                    results.append(tool_result(call, json.dumps({"found": False, "note": NOT_FOUND})))
                else:
                    lookup = as_lookup(entry)
                    found.append(lookup)
                    shown.extend(each for each in lookup["sources"] if each not in shown)
                    results.append(tool_result(call, json.dumps(
                        {key: lookup[key] for key in ("query", "found", "name", "definition", "sources")})))
            messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
            messages.extend(results)
            continue
        text = response.text.strip()
        if not text:
            messages.append({"role": "user", "content": EMPTY_REPLY})
            continue
        numbers = numbers_of(text)
        if numbers and not corrected:
            corrected = True
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": NUMBERS_CORRECTION.format(numbers=", ".join(numbers))})
            continue
        if numbers:
            work.record("you.side_withheld", {"thread": thread_id, "numbers": numbers, "text": text}, "agent")
            finish(WITHHELD.format(numbers=", ".join(numbers)), "withheld")
        else:
            finish(text)
        return
    finish(STOPPED, "withheld")
