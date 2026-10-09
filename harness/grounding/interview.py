"""The grounding interview (SPEC 4.4 and 4.6).

The model asks, the person answers, and the harness keeps the conversation
honest: one question at a time, real lookups for standard terms, a brief
that passes its checks, and the person's own confirmation before anything
is saved. Everything said is recorded in the database.

Lookups go through a research desk (SPEC 4.6): the terms the request
depends on are read up on before the first question, and no term is looked
up twice.
"""
import json
from pathlib import Path

from .. import db
from ..model import ToolSpec
from .brief import BRIEF_SCHEMA, save_brief, summarise_brief, validate_brief
from .research import MAX_QUERY_LENGTH, as_lookup, plan_research, term_key

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
CONFIRM = "Type /accept to accept this brief, or say what should change."
ACCEPT = {"/accept", "yes", "y", "yes.", "ok", "okay", "si", "sí"}
NOT_CONFIRMED = "The person did not confirm the brief. They said: "
MAX_REJECTIONS = 3

MAX_LOOKUPS = 12        # different terms the interviewer may look up, not counting the plan
LOOKUP_LIMIT = "The lookup limit for this interview is used up. Carry on with what you have."
NOT_FOUND_NOTE = "No source found. Try the usual standard name once, or leave this term without a source."


class Quit(Exception):
    """The person asked to stop for now."""


def new_state(session_id: str, opening: str) -> dict:
    """Everything needed to carry on later.

    `research` holds every research entry in the order first asked,
    `lookups` the found ones as lookup dicts (what `validate_brief` reads),
    and `proposed` the brief awaiting the person's confirmation, else None.
    """
    return {"session_id": session_id, "messages": [{"role": "user", "content": opening}],
            "lookups": [], "research": [], "proposed": None, "questions": 0, "rejections": 0}


def run_interview(*, model, researcher, ask, conn, state: dict, brief_dir,
                  state_path=None, max_questions: int = 12, say=print, plan: bool = True) -> dict | None:
    """Run the interview until a brief is saved, or the person stops.

    `researcher` is a `ResearchDesk`.
    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    `plan` reads up on the terms the opening statement depends on, before the first question.
    Returns the saved brief's details, or None if the person stopped early.

    Another thread may read `state` while this runs (the web page does), so
    research entries are added or replaced whole, never changed in place.
    """
    system = INSTRUCTIONS.read_text(encoding="utf-8").replace("{max_questions}", str(max_questions))
    state.setdefault("research", [])        # a state saved before these keys existed
    state.setdefault("proposed", None)
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
        if plan and len(messages) == 1 and not state["research"]:
            _plan(model, researcher, state, record, say)

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


def _plan(model, desk, state, record, say) -> None:
    """Read up on the opening statement's terms, and tell the interviewer which are ready."""
    entries = plan_research(model, desk, state["messages"][0]["content"], say)
    record("grounding.research_plan", "agent", {"terms": [entry["query"] for entry in entries]})
    if not entries:
        return
    state["research"].extend(entries)
    state["lookups"].extend(as_lookup(entry) for entry in entries if entry["status"] == "found")
    ready = [entry["query"] for entry in entries if entry["status"] == "found"]
    missing = [entry["query"] for entry in entries if entry["status"] != "found"]
    line = "[harness]"
    if ready:
        line += f" Already read up on, ready for look_up: {', '.join(ready)}."
    if missing:
        line += f" No source found for: {', '.join(missing)}."
    state["messages"][0]["content"] += "\n\n" + line


def _earlier(state, query: str) -> dict | None:
    """The research entry that already answers this query: the same term, or a found entry's name."""
    key = term_key(query)
    for entry in state["research"]:
        if key == term_key(entry["query"]) or (entry["status"] == "found" and key == term_key(entry["name"])):
            return entry
    return None


def _look_up_all(calls, desk, state, record, say) -> dict:
    """Run the lookups of one turn side by side. Returns {call id: tool result}.

    A term is looked up once in an interview. Asking again gets the earlier
    answer back without a lookup, and after MAX_LOOKUPS terms no new one is run.
    """
    def error(call, text):
        return {"role": "tool", "tool_call_id": call.id, "is_error": True, "content": text}

    results, new, repeats = {}, {}, []      # new: {term key: (first call to ask, query)}
    used = sum(1 for entry in state["research"] if not entry["planned"])
    for call in calls:
        query = str(call.arguments.get("query", "")).strip()
        if not query or len(query) > MAX_QUERY_LENGTH:
            results[call.id] = error(call, f"Send only the term to look up, at most {MAX_QUERY_LENGTH} characters.")
        elif _earlier(state, query) or term_key(query) in new:
            repeats.append((call, query))
        elif used + len(new) >= MAX_LOOKUPS:
            results[call.id] = error(call, LOOKUP_LIMIT)
        else:
            say(f"  (looking up: {query})")
            new[term_key(query)] = (call, query)

    entries = desk.look_up_many([query for _call, query in new.values()])
    for (call, _query), entry in zip(new.values(), entries):       # recorded in the order they were asked
        state["research"].append(entry)
        if entry["status"] == "failed":
            record("grounding.lookup", "agent", {"query": entry["query"], "error": entry["error"]})
            results[call.id] = error(call, f"The lookup failed: {entry['error']}")
            continue
        lookup = as_lookup(entry)
        record("grounding.lookup", "agent", lookup)
        if entry["status"] == "found":
            state["lookups"].append(lookup)
        else:
            lookup = {**lookup, "note": NOT_FOUND_NOTE}
        results[call.id] = {"role": "tool", "tool_call_id": call.id, "content": json.dumps(lookup)}

    for call, query in repeats:         # answered from what is known: nothing said, nothing recorded
        entry = _earlier(state, query)
        if entry["status"] == "found":
            results[call.id] = {"role": "tool", "tool_call_id": call.id,
                                "content": json.dumps({**as_lookup(entry), "repeat": True})}
        else:
            results[call.id] = error(
                call, f'No source was found for "{query}" earlier. Do not look it up again.')
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

    state["proposed"] = brief       # while the person decides, anyone showing the state can show the brief
    try:
        say(summarise_brief(brief))
        answer = hear(CONFIRM)
        if answer.lower() in ACCEPT:
            paths = save_brief(brief, brief_dir, {**meta, "status": "confirmed"})
            return _saved(call, state, record, paths, "confirmed")
    finally:
        state["proposed"] = None
    record("grounding.brief_changes", "person", {"text": answer})
    return ({"role": "tool", "tool_call_id": call.id, "content": NOT_CONFIRMED + answer}, None)


def _saved(call, state, record, paths, status):
    details = {"status": status, "json": str(paths[0]), "page": str(paths[1])}
    record("grounding.brief_written", "harness", details)
    return {"role": "tool", "tool_call_id": call.id, "content": f"Saved as {status}."}, details
