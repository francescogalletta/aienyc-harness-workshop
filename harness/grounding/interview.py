"""The grounding interview (SPEC 4.4).

The model asks, the person answers, and the harness keeps the conversation
honest: one question at a time, real lookups for standard terms, a brief
that passes its checks, and the person's own confirmation before anything
is saved. Everything said is recorded in the database.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import db
from ..model import ToolSpec
from .brief import BRIEF_SCHEMA, save_brief, summarise_brief, validate_brief
from .research import MAX_QUERY_LENGTH

INSTRUCTIONS = Path(__file__).with_name("interviewer.md")

LOOK_UP = ToolSpec(
    name="look_up",
    description=("Look up the standard definition of one finance term or method. Send only the term, "
                 "a few words. Returns its standard name, a short definition and sources."),
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})

WRITE_BRIEF = ToolSpec(
    name="write_brief",
    description=("Submit the finished brief. The harness checks it and asks the person to confirm. "
                 "The arguments are the brief itself."),
    input_schema=BRIEF_SCHEMA)

TOOLS = (LOOK_UP, WRITE_BRIEF)

ONE_QUESTION = ("[harness] That reply held more than one question. Ask one question at a time: "
                "send only the most important one now.")
WRAP_UP = ("[harness] The person wants to finish now. Call write_brief with what you have, "
           "and list what is still unresolved under open_questions.")
LIMIT_REACHED = ("[harness] You have reached the question limit. Call write_brief now, "
                 "and list what is still unresolved under open_questions.")
EMPTY_REPLY = "[harness] Your reply was empty. Ask your next question, or call write_brief."
CONFIRM = "Is this right? Type yes to accept it, or say what should change."
YES = {"yes", "y", "yes.", "ok", "okay", "si", "sí"}
MAX_REJECTIONS = 3


class Quit(Exception):
    """The person asked to stop for now."""


def new_state(session_id: str, opening: str) -> dict:
    return {"session_id": session_id, "messages": [{"role": "user", "content": opening}],
            "lookups": [], "questions": 0, "rejections": 0}


def run_interview(*, model, researcher, ask, conn, state: dict, brief_dir,
                  state_path=None, max_questions: int = 12, say=print) -> dict | None:
    """Run the interview until a brief is saved, or the person stops.

    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    Returns the saved brief's details, or None if the person stopped early.
    """
    system = INSTRUCTIONS.read_text(encoding="utf-8").replace("{max_questions}", str(max_questions))
    session_id, messages = state["session_id"], state["messages"]
    corrected = False       # has this turn already been sent back for asking two questions?

    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload=payload)

    def save_state():
        if state_path is not None:
            Path(state_path).parent.mkdir(parents=True, exist_ok=True)
            Path(state_path).write_text(json.dumps(state, indent=2), encoding="utf-8")

    def hear(question: str) -> str:
        answer = ask(question).strip()
        if answer == "/quit":
            raise Quit
        return answer

    try:
        while True:
            save_state()
            last = messages[-1]
            waiting_for_person = last["role"] == "assistant" and not last.get("tool_calls")

            if waiting_for_person:
                answer = hear(last["content"])
                state["questions"] += 1
                record("grounding.answer", "person", {"text": answer})
                if answer == "/wrap":
                    answer = WRAP_UP
                elif state["questions"] >= max_questions:
                    answer += "\n\n" + LIMIT_REACHED
                messages.append({"role": "user", "content": answer})
                continue

            say("  (thinking)")
            response = model.complete(system=system, messages=messages, tools=TOOLS)

            if response.tool_calls:
                # Text sent alongside a tool call is not shown: the person
                # only sees a message they can answer.
                results, saved = [], None
                looked_up = _look_up_all([call for call in response.tool_calls if call.name == "look_up"],
                                         researcher, state, record, say)
                for call in response.tool_calls:
                    if call.name == "look_up":
                        results.append(looked_up[call.id])
                    elif call.name == "write_brief" and saved is None:
                        result, saved = _write_brief(call, state, record, hear, say, brief_dir)
                        results.append(result)
                    else:
                        results.append({"role": "tool", "tool_call_id": call.id, "is_error": True,
                                        "content": f"There is no tool called {call.name} here."})
                # Add the call and its results together, so a saved state is never half a turn.
                messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in response.tool_calls]})
                messages.extend(results)
                if saved is not None:
                    if state_path is not None:
                        Path(state_path).unlink(missing_ok=True)
                    return saved
                continue

            text = response.text.strip()
            if not text:
                messages.append({"role": "user", "content": EMPTY_REPLY})
                continue
            if text.count("?") > 1 and not corrected:
                corrected = True
                record("grounding.correction", "harness", {"reason": "more than one question", "text": text})
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": ONE_QUESTION})
                continue
            corrected = False
            record("grounding.question", "agent", {"text": text})
            messages.append({"role": "assistant", "content": text})
    except Quit:
        save_state()
        return None


def _look_up_all(calls, researcher, state, record, say) -> dict:
    """Run the lookups of one turn side by side. Returns {call id: tool result}."""
    results, wanted = {}, []
    for call in calls:
        query = str(call.arguments.get("query", "")).strip()
        if not query or len(query) > MAX_QUERY_LENGTH:
            results[call.id] = {
                "role": "tool", "tool_call_id": call.id, "is_error": True,
                "content": f"Send only the term to look up, at most {MAX_QUERY_LENGTH} characters."}
        else:
            say(f"  (looking up: {query})")
            wanted.append((call, query))

    def look_up(query):
        try:
            return researcher.look_up(query).as_dict()
        except Exception as error:
            return {"query": query, "error": " ".join(str(error).split())}

    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(look_up, [query for _call, query in wanted]))

    for (call, query), lookup in zip(wanted, found):     # recorded in the order they were asked
        record("grounding.lookup", "agent", lookup)
        if "error" in lookup:
            results[call.id] = {"role": "tool", "tool_call_id": call.id, "is_error": True,
                                "content": f"The lookup failed: {lookup['error']}"}
        else:
            state["lookups"].append(lookup)
            results[call.id] = {"role": "tool", "tool_call_id": call.id, "content": json.dumps(lookup)}
    return results


def _write_brief(call, state, record, hear, say, brief_dir):
    """Check a proposed brief, then ask the person. Returns (tool result, saved details or None)."""
    brief = call.arguments
    meta = {"session_id": state["session_id"], "lookups": state["lookups"]}
    errors = validate_brief(brief, state["lookups"])

    if errors:
        state["rejections"] += 1
        record("grounding.brief_rejected", "harness", {"errors": errors})
        if state["rejections"] >= MAX_REJECTIONS:
            # Stop going round in circles: keep what there is, clearly marked as a draft.
            paths = save_brief(brief if isinstance(brief, dict) else {}, brief_dir,
                               {**meta, "status": "draft", "errors": errors})
            say("The brief still does not pass the checks, so it was saved as a draft.")
            return _saved(call, state, record, paths, "draft")
        problems = "\n".join(f"- {error}" for error in errors)
        return ({"role": "tool", "tool_call_id": call.id, "is_error": True,
                 "content": f"The brief was not accepted. Fix these and submit it again:\n{problems}"}, None)

    say(summarise_brief(brief))
    answer = hear(CONFIRM)
    if answer.lower() in YES:
        paths = save_brief(brief, brief_dir, {**meta, "status": "confirmed"})
        return _saved(call, state, record, paths, "confirmed")
    record("grounding.brief_changes", "person", {"text": answer})
    return ({"role": "tool", "tool_call_id": call.id,
             "content": f"The person did not confirm the brief. They said: {answer}"}, None)


def _saved(call, state, record, paths, status):
    details = {"status": status, "json": str(paths[0]), "page": str(paths[1])}
    record("grounding.brief_written", "harness", details)
    return {"role": "tool", "tool_call_id": call.id, "content": f"Saved as {status}."}, details
