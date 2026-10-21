"""Proposals and joins (SPEC 6.6, ARCHITECTURE.md 12.3 to 12.5).

On a side branch the side assistant may propose one change the person asked for, through `propose_change`. The
harness checks it with no model: the words are the person's in this branch, the target is something the last answer
took (or the plan), and a new value is one the person wrote here. A proposal that passes is stored `pending` with
its impact (12.4). The person says yes (`accept_proposal`) or no (`decline_proposal`), or closes the branch
(`close_branch`). On yes the main lane joins it: the value is saved, the runs of the last answer it reaches run again
through the gate (no model), the join notice is posted with chips, and the trunk node is recorded with the branch.
"""
import json

from ..answers.agent import saved_inputs, step_of_module, store_input, tell_analyst, tool_result
from ..answers.rerun import _as_written, _pairs, _token, impact, last_answer_runs, old_values, rerun
from ..core import BadAction, NotNow, number_of, set_outcome
from ..core.state import show_scalar
from ..db import now
from ..model import ToolSpec
from . import marks

PROPOSE_CHANGE = ToolSpec(
    name="propose_change",
    description=("Propose a change the person asked for in this branch. The harness checks it and shows it to them "
                 "with Yes and No; it changes nothing by itself. kind `value`: `input` is the value's name as the "
                 "last answer's runs give it (such as guest_count), `value` the new value in plain form (digits, "
                 "YYYY-MM-DD, or text), taken from the person's words here; when the person changes several "
                 "values at once, give them all in `changes` (one {input, value} each) instead of `input` and "
                 "`value`, so they are proposed, accepted and run again together. kind `plan`: `step` is the step "
                 "it is about, or empty for the whole plan. `words`: the person's words in this branch it rests "
                 "on, copied exactly."),
    input_schema={"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["value", "plan"]}, "input": {"type": "string"},
        "value": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "object", "properties": {
            "input": {"type": "string"}, "value": {"type": "string"}}, "required": ["input", "value"]}},
        "step": {"type": "string"}, "words": {"type": "string"}},
        "required": ["kind", "words"]})

PROPOSED = ("Proposed: {text}. It touches {steps}. The person sees it with Yes and No in this thread, with what it "
            "changes and re-runs: do not repeat that. Say only, in a few words, that it waits for their yes. Do not "
            "say it is done.")
NOT_THEIR_WORDS = "Those are not words the person wrote in this thread. Copy them exactly from their message."
UNKNOWN_INPUT = ("Nothing in the last answer takes {input}. The values it took are: {inputs}. Propose one of them, or "
                 "tell the person to say it in the main chat.")
VALUE_UNBACKED = ("The new value must be in the person's words in this thread, and {numbers} is not. Ask them for the "
                  "figure itself. Do not work it out.")
AMBIGUOUS = "The last answer used several values for {input}: {values}. Ask the person which one they mean."
SAME = "{input} is already {value}."
UNKNOWN_STEP = "There is no step {step} in the plan."
ONE_PER_REPLY = "One proposal per reply."
JOINED = "Decided on a branch: {what}. Run again: {steps}."
JOINED_NOTHING = "Decided on a branch: {what}. Nothing in the last answer used it."
NOT_RUN_AGAIN = " Not run again: {steps} ({reason})."
JOIN_NOTE = ("[harness] On a branch the person changed {what}, in their words: \"{words}\". The "
             "harness saved it and ran again: {runs}. These are now the current results; do not run them again "
             "unless the person asks.")
IS = "{label} is {new} (was {old})"              # one change in JOINED
FROM_TO = "{label} from {old} to {new}"          # one change in JOIN_NOTE
NODE_TEXT = "{label}: {new} (was {old})"         # one change in a node's text; several joined by "; "
WAS = "{new} (was {old})"
ANSWER_FIRST = "Answer the question that is waiting first."
NOT_PENDING = "That proposal is not waiting for a yes or a no."
NOT_OPEN = "That branch is not open."
JOINING = "joining the branch"
EMPTY_VALUE = "an empty value"
PLAN_TEXT_LENGTH = 80


def one_line(text) -> str:
    return " ".join(str(text).split())


def spaced(text) -> str:
    return one_line(text).casefold()


# --- Words the harness writes ---

def step_words(numbers: list) -> str:
    """`step 1`, `steps 1 and 2`, `steps 1, 2 and 5` (a calculation with no plan step is named as it is)."""
    numbers = [str(each) for each in numbers]
    if not numbers:
        return "no step"
    if len(numbers) == 1:
        return f"step {numbers[0]}"
    return "steps " + ", ".join(numbers[:-1]) + " and " + numbers[-1]


def numbers_of(state: dict, steps: list[str]) -> list:
    by_id = {step["id"]: step["number"] for step in state["steps"]}
    return [by_id.get(step, step) for step in steps]


def label_of(state: dict, key: str) -> str:
    """The plan input's name when `in:<key>` is one, else the key in words with a capital."""
    found = state["inputs"].get(f"in:{key}")
    if found:
        return found["name"]
    text = key.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def value_changes(change: dict) -> list[dict]:
    """The changes of a value proposal or node: its bundle (`changes`), else the one it names."""
    if change.get("changes"):
        return list(change["changes"])
    return [{key: change.get(key) for key in ("input", "label", "from", "to")}]


def with_first(changes: list[dict]) -> dict:
    """A value change: the first of the bundle as `input`, `label`, `from`, `to`, and `changes` when several."""
    found = {"kind": "value", **{key: changes[0][key] for key in ("input", "label", "from", "to")}}
    if len(changes) > 1:
        found["changes"] = [dict(each) for each in changes]
    return found


def each_change(template: str, changes: list[dict], joint: str) -> str:
    return joint.join(template.format(label=each["label"], new=each["to"],
                                      old=each["from"] if each["from"] is not None else "none")
                      for each in changes)


def proposal_text(change: dict, state: dict) -> str:
    if change["kind"] == "value":
        return "; ".join(f"{each['label']}: {each['from'] if each['from'] is not None else 'none'} → {each['to']}"
                         for each in value_changes(change))
    step = next((each for each in state["steps"] if each["id"] == change.get("step")), None)
    text = (f"Plan, step {step['number']} {step['name']}: " if step else "Plan: ") + one_line(change["words"])
    return text if len(text) <= PLAN_TEXT_LENGTH else text[:PLAN_TEXT_LENGTH - 1] + "…"


def touches(found: dict, state: dict) -> str:
    text = step_words(numbers_of(state, found["steps"])) if found["steps"] else "no step of the last answer"
    if found["downstream"]:
        text += f" (and {', '.join(str(each) for each in numbers_of(state, found['downstream']))} further down)"
    return text


# --- Storage ---

def _output(conn, run) -> tuple[bool, object]:
    try:
        row = conn.execute("SELECT output FROM calc_runs WHERE id = ?", (number_of(run, "r"),)).fetchone()
    except (TypeError, ValueError):
        row = None
    return (True, json.loads(row["output"])) if row is not None else (False, None)


def _what_changed(conn, old_run, new_run, shown: str) -> str:
    """A re-run's result as what changed in it: the last leaf that differs, `new (was old)`, as the step line
    writes a value; `shown` when nothing can be compared or nothing differs."""
    (had_old, old), (had_new, new) = _output(conn, old_run), _output(conn, new_run)
    if not (had_old and had_new):
        return shown
    differ = [(was, now_) for was, now_ in _pairs(old, new) if _token(was) != _token(now_)]
    if not differ:
        return shown
    was, now_ = differ[-1]
    return WAS.format(new=show_scalar(now_), old=show_scalar(was))


def notice_chips(conn, node: dict, chips: list[dict]) -> list[dict]:
    """A join notice's chips (ARCHITECTURE.md 12.7): the decision first, then the value that changed, `new (was
    old)`, then one result per re-run, as what changed in it. The re-runs' other inputs and assumptions are the
    old answer's, and stay with it."""
    change = node.get("change") or {}
    olds = {each["input"]: each["from"] for each in value_changes(change) if each.get("input")}
    back = {new: was for was, new in (change.get("runs") or {}).items()}
    kept, valued = [], set()
    for chip in chips:
        subject = chip.get("subject") or {}
        if chip.get("kind") == "value" and subject.get("key") in olds and subject.get("key") not in valued:
            valued.add(subject["key"])
            old = olds[subject["key"]]
            kept.append({**chip, "text": WAS.format(new=chip["text"], old=show_scalar(old))
                         if old is not None else chip["text"]})
        elif chip.get("kind") == "result":
            kept.append({**chip, "text": _what_changed(conn, back.get(subject.get("run")), subject.get("run"),
                                                       chip["text"])})
    return [{"kind": "decision", "label": "Decided", "text": node["text"], "status": None,
             "subject": {"kind": "decision", "node": node["id"]}}, *kept]


def proposal_row(conn, proposal_id: str, conversation: str):
    try:
        wanted = number_of(proposal_id, "p")
    except ValueError:
        raise BadAction(f"not a proposal id: {proposal_id!r}") from None
    return conn.execute("SELECT * FROM proposals WHERE id = ? AND conversation = ?", (wanted, conversation)).fetchone()


def proposal_view(row, state: dict) -> dict:
    """A `proposals` row as the Proposal of the state document (ARCHITECTURE.md 3.5)."""
    change = json.loads(row["change"])
    return {"id": f"p{row['id']}", "status": row["status"], "change": change, "words": row["words"],
            "text": proposal_text(change, state), "impact": json.loads(row["impact"]),
            "node": f"n{row['node']}" if row["node"] is not None else None, "reason": row["reason"]}


def newest_proposals(conn, conversation: str) -> dict[str, object]:
    """{thread id: its newest proposal row}."""
    found = {}
    for row in conn.execute("SELECT * FROM proposals WHERE conversation = ? ORDER BY id", (conversation,)):
        found[f"t{row['thread']}"] = row
    return found


def has_pending(conn, thread: str) -> bool:
    return conn.execute("SELECT 1 FROM proposals WHERE thread = ? AND status = 'pending'",
                        (number_of(thread, "t"),)).fetchone() is not None


# --- propose_change: the checks (SPEC 6.6) ---

def _last_answer_inputs(conn, conversation: str) -> list[str]:
    ids = last_answer_runs(conn, conversation)
    keys = []
    if ids:
        for row in conn.execute(f"SELECT inputs FROM calc_runs WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id",
                                tuple(ids)):
            inputs = json.loads(row["inputs"])
            keys += [key for key in (inputs if isinstance(inputs, dict) else {}) if key not in keys]
    return keys


def _run_inputs(conn, run: str | None) -> dict:
    try:
        row = conn.execute("SELECT inputs FROM calc_runs WHERE id = ?", (number_of(run, "r"),)).fetchone()
    except ValueError:
        return {}
    inputs = json.loads(row["inputs"]) if row else {}
    return inputs if isinstance(inputs, dict) else {}


def old_value(conn, conversation: str, subject: dict, key: str) -> tuple[str | None, list[str]]:
    """The value being replaced (12.3, point 4), and the values found when they are several (ambiguous)."""
    kind = subject.get("kind")
    if kind == "value" and subject.get("key") == key:
        return subject.get("value"), []
    if kind in ("result", "assumption"):
        inputs = _run_inputs(conn, subject.get("run"))
        if key in inputs:
            return _as_written(inputs[key]), []
    saved = saved_inputs(conn).get(key)
    if saved is not None:
        return _as_written(saved["value"]), []
    values = old_values(conn, conversation, key)
    if len(values) > 1:
        return None, values
    return (values[0] if values else None), []


def value_unbacked(value: str, texts: list[str]) -> list[str]:
    """The numbers and dates of `value` that are not in the person's words (`texts`), read with number words and
    dates written in words. Every number counts here, small ones too: the new value is the point of the proposal."""
    from ..calc.provenance import _read

    sources = marks.given_texts(texts)
    known = [item["value"] for source in sources for item in _read(source) if not item["parts"]]
    dates = set().union(*(marks.dates_in(source) for source in sources)) if sources else set()
    missing = []
    for item in _read(value):
        if item["parts"]:
            backed = item["written"] in dates
        else:
            backed = any(abs(each - item["value"]) <= item["precision"] / 2 for each in known)
        if not backed and item["written"] not in missing:
            missing.append(item["written"])
    return missing


def check(conn, conversation: str, state: dict, thread: dict, arguments: dict, person: list[str]) -> tuple:
    """(reason, error text, change) for a refused proposal, or (None, None, change) for one that passes."""
    kind = arguments.get("kind")
    words = arguments.get("words")
    items = arguments.get("changes") if isinstance(arguments.get("changes"), list) and arguments.get("changes") \
        else [{"input": arguments.get("input"), "value": arguments.get("value")}]
    pairs = []
    for item in items:
        raw_input = str((item or {}).get("input") or "").strip() if isinstance(item, dict) else ""
        pairs.append((raw_input[len("in:"):] if raw_input.startswith("in:") else raw_input,
                      one_line((item or {}).get("value") or "") if isinstance(item, dict) else ""))
    key, value = pairs[0]
    step = str(arguments.get("step") or "").strip() or None
    shown = {"kind": kind, "input": key, "value": value, "step": step, "words": words}
    if len(pairs) > 1:
        shown["changes"] = [{"input": each_key, "value": each_value} for each_key, each_value in pairs]
    if not isinstance(words, str) or len(spaced(words)) < 3 or not any(spaced(words) in spaced(text)
                                                                        for text in person):
        return "not_their_words", NOT_THEIR_WORDS, shown
    words = one_line(words)
    if kind == "plan":
        if step is not None and step not in {each["id"] for each in state["steps"]}:
            return "unknown_step", UNKNOWN_STEP.format(step=step), shown
        return None, None, {"kind": "plan", "step": step, "words": words}
    subject = thread["subject"]
    taken = _last_answer_inputs(conn, conversation)
    own = [subject.get("key")] if subject.get("kind") == "value" else \
        [subject["input"][len("in:"):]] if subject.get("kind") == "input" else []
    if kind != "value":
        return "unknown_input", UNKNOWN_INPUT.format(input=key or "that", inputs=", ".join(taken) or "none"), shown
    changes = []
    for key, value in pairs:
        if not key or key not in [*taken, *own] or key in {each["input"] for each in changes}:
            return "unknown_input", UNKNOWN_INPUT.format(input=key or "that", inputs=", ".join(taken) or "none"), shown
        missing = value_unbacked(value, person) if value else [EMPTY_VALUE]
        if missing:
            return "value_unbacked", VALUE_UNBACKED.format(numbers=", ".join(missing)), shown
        old, several = old_value(conn, conversation, subject, key)
        if several:
            return "ambiguous", AMBIGUOUS.format(input=key, values=", ".join(several)), shown
        if old is not None and _token(old) == _token(value):
            return "same", SAME.format(input=key, value=old), shown
        changes.append({"input": key, "label": label_of(state, key), "from": old, "to": value})
    return None, None, with_first(changes)


def plan_impact(state: dict, step: str | None) -> dict:
    start = [step] if step else []
    reached, todo = set(start), list(start)
    while todo:
        here = todo.pop()
        for edge in state["edges"]:
            if edge["from"] == here and edge["to"] not in reached:
                reached.add(edge["to"])
                todo.append(edge["to"])
    return {"inputs": [], "runs": [], "steps": start,
            "downstream": [each["id"] for each in state["steps"] if each["id"] in reached and each["id"] not in start]}


def propose(work, thread: dict, call, state: dict, person: list[str], made: list) -> dict:
    """The `propose_change` tool of the side assistant. `made` holds the proposals of this reply."""
    conn, conversation = work.conn, work.conversation

    def refuse(reason, error, change):
        work.record("you.proposal_refused", {"thread": thread["id"], "reason": reason, "change": change}, "agent")
        return tool_result(call, error, True)

    reason, error, change = check(conn, conversation, state, thread, call.arguments, person)
    if reason is None and made:
        reason, error = "one_per_reply", ONE_PER_REPLY
    if reason is not None:
        return refuse(reason, error, change)
    if change["kind"] == "value":
        found = impact(conn, state, changes=[{"key": each["input"], "old": each["from"]}
                                             for each in value_changes(change)], conversation=conversation)
    else:
        found = plan_impact(state, change["step"])
    conn.execute("UPDATE proposals SET status = 'replaced' WHERE thread = ? AND status = 'pending'",
                 (number_of(thread["id"], "t"),))
    cursor = conn.execute(
        "INSERT INTO proposals (ts, conversation, thread, kind, change, words, impact, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (now(), conversation, number_of(thread["id"], "t"), change["kind"], json.dumps(change),
         one_line(call.arguments.get("words")), json.dumps(found)))
    conn.commit()
    proposal = f"p{cursor.lastrowid}"
    made.append(proposal)
    work.record("you.proposed", {"thread": thread["id"], "proposal": proposal, "change": change, "impact": found},
                "agent")
    work.changed()
    return tool_result(call, PROPOSED.format(text=proposal_text(change, state), steps=touches(found, state)))


# --- Branch deaths (12.5) ---

def dies(conn, thread: dict) -> bool:
    """A side branch of the person's that is open, whose last message is the side assistant's, with no pending
    proposal: one that dies when the person moves on."""
    return (thread["kind"] == "side" and thread["origin"] == "you" and thread["outcome"] == "open"
            and bool(thread["messages"]) and thread["messages"][-1]["who"] == "assistant"
            and not has_pending(conn, thread["id"]))


def kill(core, thread: str, reason: str) -> None:
    """Make a branch dead and record why (`closed`, `declined`, `moved_on`, `new_branch`)."""
    set_outcome(core.conn, thread, "dead")
    core.record("you.branch_dead", {"thread": thread, "reason": reason}, "person" if reason != "moved_on" else
                "harness")
    core.changed()


def moved_on(work, turn) -> None:
    """Hook `turn_finished`: the analyst finished answering a main-chat message sent after a branch's last message;
    such a branch dies when it waits on nothing (12.5)."""
    from ..core import list_threads

    message = (turn.message or {}).get("id")
    try:
        asked = number_of(message, "m")
    except ValueError:
        return
    conn = work.conn
    for thread in list_threads(conn, work.conversation):
        if not dies(conn, thread):
            continue
        last = conn.execute("SELECT MAX(id) FROM messages WHERE thread = ?", (number_of(thread["id"], "t"),)).fetchone()[0]
        if last is not None and asked > last:
            kill(work, thread["id"], "moved_on")


# --- The actions ---

def _thread_row(conn, thread: str, conversation: str):
    return conn.execute("SELECT * FROM threads WHERE id = ? AND conversation = ?",
                        (number_of(thread, "t"), conversation)).fetchone()


def accept_proposal(core, payload: dict) -> None:
    """`accept_proposal {proposal}`: status `accepted`; the join is queued on the main lane."""
    proposal = payload.get("proposal")
    if not isinstance(proposal, str):
        raise BadAction("proposal must be a proposal id")
    row = proposal_row(core.conn, proposal, core.conversation)
    if row is None or row["status"] != "pending":
        raise NotNow(NOT_PENDING)
    waiting = core.waiting
    if waiting is not None and waiting.get("kind") == "decision":
        raise NotNow(ANSWER_FIRST)
    core.conn.execute("UPDATE proposals SET status = 'accepted' WHERE id = ?", (row["id"],))
    core.conn.commit()
    thread = f"t{row['thread']}"
    core.record("you.proposal_accepted", {"thread": thread, "proposal": proposal}, "person")
    steps = json.loads(row["impact"]).get("steps") or [None]
    core.queue("main", lambda work: join(work, proposal), what="join", step=steps[0], text=JOINING)


def decline_proposal(core, payload: dict) -> None:
    """`decline_proposal {proposal}`: status `declined`; the branch is dead (a joined one stays joined)."""
    proposal = payload.get("proposal")
    if not isinstance(proposal, str):
        raise BadAction("proposal must be a proposal id")
    row = proposal_row(core.conn, proposal, core.conversation)
    if row is None or row["status"] != "pending":
        raise NotNow(NOT_PENDING)
    core.conn.execute("UPDATE proposals SET status = 'declined' WHERE id = ?", (row["id"],))
    core.conn.commit()
    thread = f"t{row['thread']}"
    core.record("you.proposal_declined", {"thread": thread, "proposal": proposal}, "person")
    if _thread_row(core.conn, thread, core.conversation)["outcome"] == "open":
        kill(core, thread, "declined")


def close_branch(core, payload: dict) -> None:
    """`close_branch {thread}`: a side branch that is open becomes dead; a pending proposal in it is declined."""
    thread = payload.get("thread")
    if not isinstance(thread, str):
        raise BadAction("thread must be a thread id")
    try:
        number_of(thread, "t")
    except ValueError:
        raise BadAction(f"not a thread id: {thread!r}") from None
    row = _thread_row(core.conn, thread, core.conversation)
    if row is None or row["kind"] != "side" or row["outcome"] != "open":
        raise NotNow(NOT_OPEN)
    for pending in core.conn.execute("SELECT id FROM proposals WHERE thread = ? AND status = 'pending'",
                                     (row["id"],)).fetchall():
        core.conn.execute("UPDATE proposals SET status = 'declined' WHERE id = ?", (pending["id"],))
        core.conn.commit()
        core.record("you.proposal_declined", {"thread": thread, "proposal": f"p{pending['id']}"}, "person")
    kill(core, thread, "closed")


# --- The join (12.3), a main-lane job ---

def _fail(work, row, reason: str) -> None:
    work.conn.execute("UPDATE proposals SET status = 'failed', reason = ? WHERE id = ?", (reason, row["id"]))
    work.conn.commit()
    work.post(f"The change was not made: {reason}", who="harness", thread=f"t{row['thread']}")


def join(work, proposal: str) -> None:
    row = proposal_row(work.conn, proposal, work.conversation)
    if row is None or row["status"] != "accepted":
        return
    change = json.loads(row["change"])
    try:
        if change["kind"] == "plan":
            _join_plan(work, row, change)
        else:
            _join_value(work, row, change)
    except Exception as error:
        _fail(work, row, one_line(error) or type(error).__name__)
        raise


def _join_plan(work, row, change: dict) -> None:
    from ..grounding.revise import revise_plan

    thread = f"t{row['thread']}"
    result = revise_plan(work, words=change["words"], step=change.get("step"), by="person", branch=thread)
    if "error" in result:
        _fail(work, row, result["error"])
        return
    work.conn.execute("UPDATE proposals SET node = ? WHERE id = ?", (number_of(result["node"], "n"), row["id"]))
    work.conn.commit()
    work.record("you.joined", {"thread": thread, "proposal": f"p{row['id']}", "node": result["node"], "runs": {},
                               "failed": []}, "harness")
    work.changed()


def _join_value(work, row, change: dict) -> None:
    conn, conversation = work.conn, work.conversation
    thread = f"t{row['thread']}"
    changes = value_changes(change)
    subject = json.loads(conn.execute("SELECT subject FROM threads WHERE id = ?", (row["thread"],)).fetchone()[0])
    work.progress("saving the value" if len(changes) == 1 else "saving the values", what="join")
    for each in changes:
        store_input(conn, each["input"], each["to"], f"on a branch: {row['words']}", conversation)
    drop = []
    if subject.get("kind") == "assumption":
        drop = [subject.get("text") or ""]
        found = subject.get("assumption")
        if not found:
            linked = marks.link_run(conn, number_of(subject["run"], "r"), drop)
            found = linked[0]["id"] if linked else None
        if found:
            marks.set_status(conn, [found], marks.CORRECTED, row["words"])
    work.changed()
    result = rerun(work, changes=[{"key": each["input"], "old": each["from"], "new": each["to"],
                                   "label": each["label"]} for each in changes], drop=drop)

    state = work.session.state()
    step_ids = {step["id"] for step in state["steps"]}
    new_runs = [number_of(each, "r") for each in result["replaced"].values()]
    modules = {each["id"]: each["module"] for each in conn.execute(
        f"SELECT id, module FROM calc_runs WHERE id IN ({','.join('?' * len(new_runs))})", tuple(new_runs))} \
        if new_runs else {}
    steps, loose = [], []                 # the plan steps run again; modules run again with no step in the state
    for run in new_runs:
        step = step_of_module(conn, modules[run], step_ids)
        if step:
            steps += [step] if step not in steps else []
        elif modules[run] not in loose:
            loose.append(modules[run])
    what = each_change(IS, changes, " and ")
    if result["replaced"] or result["failed"]:
        text = JOINED.format(what=what, steps=step_words([*numbers_of(state, steps), *loose]))
    else:
        text = JOINED_NOTHING.format(what=what)
    reasons = {}
    for each in result["failed"]:
        reasons.setdefault(each["reason"], []).append(each["step"] or "a calculation not in the plan")
    for reason, failed_steps in reasons.items():
        text += NOT_RUN_AGAIN.format(steps=step_words(numbers_of(state, list(dict.fromkeys(failed_steps)))),
                                     reason=reason)
    message = work.post(text, who="harness", kind="text",
                        data={"_runs": result["runs"], "_chip_runs": new_runs, "figures": []})
    failed = [{"run": each["run"], "step": each["step"] or "", "reason": each["reason"]} for each in result["failed"]]
    node = work.decide(who="you", kind="value", text=each_change(NODE_TEXT, changes, "; "),
                       change={**{key: value for key, value in with_first(changes).items() if key != "kind"},
                               "runs": result["replaced"], "failed": failed},
                       touched={"inputs": [f"in:{each['input']}" for each in changes
                                           if f"in:{each['input']}" in state["inputs"]], "steps": steps},
                       branch=thread)
    work.session.update_message(message, {"_node": node})
    conn.execute("UPDATE proposals SET node = ? WHERE id = ?", (number_of(node, "n"), row["id"]))
    conn.commit()
    work.record("you.joined", {"thread": thread, "proposal": f"p{row['id']}", "node": node,
                               "runs": result["replaced"], "failed": failed}, "harness")
    outputs = [conn.execute("SELECT module, output FROM calc_runs WHERE id = ?", (run,)).fetchone() for run in new_runs]
    runs = "; ".join(f"{each['module']} gives {each['output']}" for each in outputs) or "nothing"
    tell_analyst(work, JOIN_NOTE.format(what=each_change(FROM_TO, changes, ", "), words=row["words"], runs=runs))
    work.changed()
