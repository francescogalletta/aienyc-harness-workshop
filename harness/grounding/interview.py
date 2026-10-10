"""The interview on the core (SPEC 3.2).

The model asks, the person answers, and the harness keeps the conversation honest: one question at a
time, real lookups for standard terms, a brief that passes its checks, and the person's own acceptance
before anything is saved. It runs as one main-lane job: its questions are posted as assistant messages
and it waits with `work.wait("message")`; a valid brief is proposed as a plan and it waits with
`work.wait("plan")`.

The interview state (`new_state`) is a plain dict. The layer keeps it in `core.memory["plan"]` for the
state document to draw, and on disk (`grounding_state.json`) so a later process can resume.
"""
import copy
import json
from pathlib import Path

from ..model import ToolSpec
from .brief import BRIEF_SCHEMA, describe_changes, save_brief, validate_brief
from .research import MAX_QUERY_LENGTH, as_lookup, plan_research, term_key

INSTRUCTIONS = Path(__file__).with_name("interviewer.md")

LOOK_UP = ToolSpec(
    name="look_up",
    description=("Look up the standard definition of one finance term or method. Send only the term, "
                 "a few words. Returns its standard name, a short definition and sources."),
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})

WRITE_BRIEF = ToolSpec(
    name="write_brief",
    description=("Submit the finished brief. The harness checks it and shows the person the plan. "
                 "The arguments are the brief itself."),
    input_schema=BRIEF_SCHEMA)

TOOLS = (LOOK_UP, WRITE_BRIEF)

PLAN_PROPOSED = "This is the plan as I understand it. Click a step to say what is wrong, or accept it."
PLAN_REVISED = "The plan is revised: {changes}. Click a step to say what is wrong, or accept it."
PLAN_ACCEPTED = "The plan is accepted."
DRAFT_SAVED = ("I could not make a plan that passes the harness checks, so I saved a draft at {path}. "
               "Tell me what to change, or type /wrap to try again with what we have.")

ONE_QUESTION = ("[harness] That reply held more than one question. Ask one question at a time: "
                "send only the most important one now.")
WRAP_UP = ("[harness] The person wants to finish now. Call write_brief with what you have, "
           "and list what is still unresolved under open_questions.")
LIMIT_REACHED = ("[harness] You have reached the question limit. Call write_brief now, "
                 "and list what is still unresolved under open_questions.")
EMPTY_REPLY = "[harness] Your reply was empty. Ask your next question, or call write_brief."
NOT_CONFIRMED = "The person did not accept the plan. They said: "
DRAFT_NOTE = ("The brief still fails the checks after {n} tries, so it was saved as a draft. Do not call "
              "write_brief again now: tell the person in one sentence what is blocking, and ask one question.")
HOLD = "The brief was not accepted, and the person has not answered since. Ask them one question instead."
MAX_REJECTIONS = 3
MAX_TURNS = 12          # model calls in a row without the person saying anything

MAX_LOOKUPS = 12        # different terms the interviewer may look up, not counting the plan
LOOKUP_LIMIT = "The lookup limit for this interview is used up. Carry on with what you have."
NOT_FOUND_NOTE = "No source found. Try the usual standard name once, or leave this term without a source."


def new_state(session_id: str, opening: str) -> dict:
    """Everything needed to carry on later.

    `research` holds every research entry in the order first asked, `lookups` the found ones as lookup
    dicts (what `validate_brief` reads), `words` what the person has written, `proposed` the brief
    awaiting acceptance (with `pending_call`, the write_brief call still without a result), and `shown`
    the latest brief proposed, which the plan keeps drawing while it is revised.
    """
    return {"session_id": session_id, "messages": [{"role": "user", "content": opening}], "words": [opening],
            "lookups": [], "research": [], "proposed": None, "shown": None, "pending_call": None,
            "questions": 0, "rejections": 0}


def about(text: str, step: str | None, brief: dict | None) -> str:
    """A person's words, with the step they are about put in front for the interviewer (SPEC 3.2)."""
    if not step:
        return text
    name = next((each["name"] for each in (brief or {}).get("process", []) if each.get("id") == step), None)
    head = f"[harness] About step {step} ({name}):" if name else f"[harness] About step {step}:"
    return f"{head}\n{text}"


def run_interview(work, state: dict, *, desk, brief_dir, state_path=None, answer: dict | None = None,
                  max_questions: int = 12) -> dict:
    """Run the interview until the plan is accepted. Returns the saved brief's details.

    `answer` is a message that arrived for an interview that was not waiting (its job failed, or the
    process restarted): it is taken as the answer to whatever the interview waits for next.
    """
    system = INSTRUCTIONS.read_text(encoding="utf-8").replace("{max_questions}", str(max_questions))
    messages = state["messages"]
    corrected = False       # has this turn already been sent back for asking two questions?
    turns = 0

    def save_state():
        if state_path is not None:
            Path(state_path).parent.mkdir(parents=True, exist_ok=True)
            Path(state_path).write_text(json.dumps(state, indent=2), encoding="utf-8")

    def hear(kind: str) -> dict:
        nonlocal answer
        got, answer = (answer if answer is not None else work.wait(kind)), None
        return got

    if len(messages) == 1 and not state["research"] and answer is None:
        _plan(work, desk, state)

    while True:
        save_state()

        if state["proposed"]:
            got = hear("plan")
            if got.get("accept"):
                meta = {"session_id": state["session_id"], "lookups": state["lookups"], "status": "confirmed"}
                paths = save_brief(state["proposed"], brief_dir, meta)
                work.record("plan.accepted", {"steps": len(state["proposed"]["process"]),
                                              "open_questions": len(state["proposed"]["open_questions"]),
                                              "json": str(paths[0])}, "person")
                return {"json": str(paths[0]), "page": str(paths[1])}
            text, step = got["text"], got.get("step")
            state["words"].append(text)
            work.record("plan.changes", {"text": text, "step": step}, "person")
            messages.append({"role": "tool", "tool_call_id": state["pending_call"],
                             "content": NOT_CONFIRMED + about(text, step, state["proposed"])})
            state["proposed"], state["pending_call"], state["rejections"] = None, None, 0
            work.changed()
            turns = 0
            continue

        last = messages[-1]
        if last["role"] == "assistant" and not last.get("tool_calls"):         # a question awaits the person
            got = hear("message")
            state["questions"] += 1
            state["rejections"], turns = 0, 0
            if got.get("wrap"):
                work.record("plan.answer", {"text": "/wrap", "step": None}, "person")
                content = WRAP_UP
            else:
                text, step = got["text"], got.get("step")
                state["words"].append(text)
                work.record("plan.answer", {"text": text, "step": step}, "person")
                content = about(text, step, state["shown"])
                if state["questions"] >= max_questions:
                    content += "\n\n" + LIMIT_REACHED
            messages.append({"role": "user", "content": content})
            continue

        if answer is not None:      # words for a turn the model still owes: they join the person's last message
            state["words"].append(answer["text"])
            last["content"] += "\n\n" + about(answer["text"], answer.get("step"), state["shown"])
            answer = None
            continue

        turns += 1
        if turns > MAX_TURNS:
            raise RuntimeError("the interviewer made too many calls in a row without asking the person")
        work.progress("thinking")
        response = work.model.complete(system=system, messages=messages, tools=TOOLS)

        if response.tool_calls:
            # Text sent alongside a tool call is not shown: the person only sees a message they can answer.
            looked_up = look_up_all([call for call in response.tool_calls if call.name == "look_up"],
                                     desk, state, work)
            results, proposal = [], None
            for call in response.tool_calls:
                if call.name == "look_up":
                    results.append(looked_up[call.id])
                elif call.name == "write_brief" and proposal is None:
                    result, proposal = _write_brief(call, state, work, brief_dir)
                    if result is not None:
                        results.append(result)
                else:
                    results.append({"role": "tool", "tool_call_id": call.id, "is_error": True,
                                    "content": f"There is no tool called {call.name} here, or one brief at a time."})
            # Add the call and its results together, so a saved state is never half a turn.
            messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
            messages.extend(results)
            if proposal is not None:
                before = state["shown"]
                state["proposed"] = state["shown"] = proposal
                state["pending_call"] = next(call.id for call in response.tool_calls if call.name == "write_brief")
                state["rejections"] = 0
                save_state()
                work.record("plan.proposed", {"steps": len(proposal["process"]),
                                              "open_questions": len(proposal["open_questions"])}, "agent")
                work.post(PLAN_REVISED.format(changes=describe_changes(before, proposal)) if before else PLAN_PROPOSED,
                          who="harness", kind="plan")
            continue

        text = response.text.strip()
        if not text:
            messages.append({"role": "user", "content": EMPTY_REPLY})
            continue
        if text.count("?") > 1 and not corrected:
            corrected = True
            work.record("plan.correction", {"reason": "more than one question", "text": text}, "harness")
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": ONE_QUESTION})
            continue
        corrected = False
        work.record("plan.question", {"text": text}, "agent")
        messages.append({"role": "assistant", "content": text})
        work.post(text)


def _plan(work, desk, state) -> None:
    """Read up on the opening statement's terms, and tell the interviewer which are ready."""
    entries = plan_research(work.model, desk, state["messages"][0]["content"],
                            lambda text: work.progress(text.strip(" ()")))
    work.record("plan.research_plan", {"terms": [entry["query"] for entry in entries]}, "agent")
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


def look_up_all(calls, desk, state, work) -> dict:
    """Run the lookups of one turn side by side. Returns {call id: tool result}.

    A term is looked up once in a conversation. Asking again gets the earlier answer back without a
    lookup, and after MAX_LOOKUPS terms no new one is run. `state` holds `research` and `lookups`.
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
            new[term_key(query)] = (call, query)
    if new:
        work.progress("looking up: " + ", ".join(query for _call, query in new.values()))

    entries = desk.look_up_many([query for _call, query in new.values()]) if new else []
    for (call, _query), entry in zip(new.values(), entries):       # recorded in the order they were asked
        state["research"].append(entry)
        if entry["status"] == "failed":
            work.record("plan.lookup", {"query": entry["query"], "error": entry["error"]}, "agent")
            results[call.id] = error(call, f"The lookup failed: {entry['error']}")
            continue
        lookup = as_lookup(entry)
        work.record("plan.lookup", lookup, "agent")
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


def _write_brief(call, state, work, brief_dir):
    """Check a proposed brief. Returns (tool result, None) when it is refused, else (None, the brief):
    its result waits for the person."""
    brief = copy.deepcopy(call.arguments)
    errors = validate_brief(brief, state["lookups"], state["words"])
    if not errors:
        return None, brief

    state["rejections"] += 1
    draft = state["rejections"] == MAX_REJECTIONS
    work.record("plan.brief_rejected", {"errors": errors, "draft": draft}, "harness")
    if state["rejections"] > MAX_REJECTIONS:
        return {"role": "tool", "tool_call_id": call.id, "is_error": True, "content": HOLD}, None
    if draft:
        # Stop going round in circles: keep what there is, clearly marked as a draft, and ask the person.
        meta = {"session_id": state["session_id"], "lookups": state["lookups"], "status": "draft", "errors": errors}
        try:
            paths = save_brief(brief if isinstance(brief, dict) else {}, brief_dir, meta)
        except (AttributeError, KeyError, TypeError):       # too broken to lay out as a page
            Path(brief_dir).mkdir(parents=True, exist_ok=True)
            paths = (Path(brief_dir) / "domain_brief.json",)
            paths[0].write_text(json.dumps({"brief": brief, "meta": meta}, indent=2), encoding="utf-8")
        work.post(DRAFT_SAVED.format(path=paths[0]), who="harness")
        return {"role": "tool", "tool_call_id": call.id, "is_error": True,
                "content": DRAFT_NOTE.format(n=MAX_REJECTIONS)}, None
    problems = "\n".join(f"- {error}" for error in errors)
    return ({"role": "tool", "tool_call_id": call.id, "is_error": True,
             "content": f"The brief was not accepted. Fix these and submit it again:\n{problems}"}, None)
