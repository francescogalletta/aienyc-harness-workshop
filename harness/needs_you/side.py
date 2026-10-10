"""Side threads (SPEC 6.4): the person asks something on the side, in a thread inside the chat, at any time
and in any phase. A sub-agent with its own context answers on the side lane, so the main lane goes on
working (or waiting) meanwhile. It explains and explores; it cannot run, save, build, decide or change
anything, and nothing passes back: the main analyst never sees a thread, and a thread never sees the main
analyst's messages (only the last ten lines of the chat, as text).

Its reply is number-checked against what it was given, the thread's own messages and its lookups. A lookup
sends only a general term out, through the research desk.
"""
import json
from pathlib import Path

from ..answers.agent import tool_result
from ..calc.builder import format_sections
from ..calc.provenance import unbacked
from ..core import BadAction, NotNow, add_thread, list_messages, list_threads, number_of
from ..grounding.research import as_lookup, default_desk
from ..model import ToolSpec

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


def title_of(text: str, step_name: str | None) -> str:
    """The step's name, or the first words of the text, cut to 45 characters."""
    title = one_line(step_name or text)
    return title if len(title) <= TITLE_LENGTH else title[:TITLE_LENGTH - 1].rstrip() + "…"


# --- The action ---

def side(core, payload: dict) -> None:
    """`side {text, step?, thread?}`: start a side thread, or reply in one (side or review)."""
    text, step, thread = payload.get("text"), payload.get("step"), payload.get("thread")
    if not isinstance(text, str) or not text.strip():
        raise BadAction("text must be a non-empty string")
    if step is not None and not isinstance(step, str):
        raise BadAction("step must be a string or null")
    if thread is not None and not isinstance(thread, str):
        raise BadAction("thread must be a string or null")
    text, conn = text.strip(), core.conn
    if thread is None:
        name = None
        if step:
            found = next((each for each in core.state()["steps"] if each["id"] == step), None)
            if found is None:
                raise BadAction(f"there is no step {step!r}")
            name = found["name"]
        thread = add_thread(conn, core.conversation, kind="side", title=title_of(text, name), step=step or None)
        core.record("you.side_opened", {"thread": thread, "step": step or None, "title": title_of(text, name)},
                    "person")
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


def sections_of(state: dict, thread: dict) -> dict:
    recent = [{"who": each["who"], "text": each["text"]} for each in state["chat"][-RECENT_CHAT:]]
    challenge = thread.get("challenge") if thread["kind"] == "review" else None
    return {"plan": plan_section(state), "step": step_section(state, thread["step"]), "recent chat": recent,
            "challenge": ({"concern": challenge["concern"], "proposal": challenge["proposal"],
                           "kind": challenge["kind"], "status": challenge["status"]} if challenge else None)}


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
    sections = sections_of(state, next((each for each in state["threads"] if each["id"] == thread_id), thread))
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
        response = work.model.complete(system=system, messages=messages, tools=[LOOK_UP])
        if response.tool_calls:
            results = []
            for call in response.tool_calls:
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
