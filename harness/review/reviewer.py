"""The reviewer (SPEC 7): a sub-agent on the review lane that looks at how the problem is being thought about
and raises challenges, each on one step and each a thread in the chat.

A pass is its own conversation with the model: `reviewer.md` as the system prompt and one user message made of
sections (the plan, the built specs, assumptions, decisions, saved inputs, last runs, earlier challenges, the
person's replies in review threads). It does not see the analyst's conversation, the code of any module, or the
main chat. The harness keeps a challenge only after the checks of SPEC 7.2, ranks the kept ones, caps them, and
opens a thread for each. Nothing here waits for the person or touches the main lane.
"""
import json
import re
import time
from pathlib import Path

from .. import db
from ..answers.agent import saved_inputs, today_of, without_meta
from ..calc.added import process_steps
from ..calc.builder import format_sections, plan_of
from ..calc.provenance import unbacked
from ..calc.registry import get_build, get_module, module_for_step, step_status
from ..core import add_thread, list_threads
from ..grounding.research import default_desk
from ..model import ToolSpec

PROMPT = Path(__file__).with_name("reviewer.md")

MAX_CALLS = 8               # model calls in one pass
MAX_LOOKUPS = 4             # lookups in one pass
MAX_PER_PASS = 3            # challenges kept from one pass
MAX_OPEN = 5                # with this many open, a pass keeps none
TITLE_LENGTH = 45
LAST_RUNS = 8
KINDS = ("challenge", "question")
CHANGES = ("plan", "assumption", "input", "build_step", "replace_step", "none")
IMPACTS = ("high", "medium", "low")

LOOK_UP = ToolSpec(
    name="look_up",
    description=("Look up a short general question or term, such as 'sinking fund'. Only the words you give leave "
                 "this machine, so put nothing about the person in them: no figure, no date, no name. A query "
                 "with a digit in it is refused. At most four lookups in a pass."),
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
REPORT = ToolSpec(
    name="report",
    description=("End the pass with the challenges to raise (an empty list when nothing is weak enough). Call it "
                 "exactly once."),
    input_schema={"type": "object", "properties": {"challenges": {"type": "array", "items": {
        "type": "object", "properties": {
            "step": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)},
            "title": {"type": "string"}, "concern": {"type": "string"}, "proposal": {"type": "string"},
            "change": {"type": "string", "enum": list(CHANGES)},
            "impact": {"type": "string", "enum": list(IMPACTS)},
            "sources": {"type": "array", "items": {"type": "string"}}},
        "required": ["step", "kind", "title", "concern", "proposal", "change", "impact", "sources"]}}},
        "required": ["challenges"]})

CLOSING = ("[harness] Look at this plan and report with one call to `report`. You may look up general questions "
           "first.")
NO_REPORT = "[harness] Your pass ends with one call to `report`; call it now, with an empty list if nothing is weak."
TOO_MANY_LOOKUPS = "No more lookups in this pass."
ONE_REPORT = "Only one report counts in a pass."
BAD_REPORT = "`challenges` must be a list of objects. Report again."
NOT_FOUND = "Nothing was found for that."
LOOKUP_FAILED = "The lookup gave nothing: {error}"
URL = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)

# why a challenge was dropped (the `reason` of `review.dropped`)
NOT_A_STEP, BAD_TITLE, BAD_VALUE = "unknown_step", "bad_title", "bad_value"
BAD_QUESTION, NO_PROPOSAL, UNFETCHED = "bad_question", "no_proposal", "source_not_fetched"
UNBACKED, REPEAT, OVER_CAP, TOO_MANY_OPEN = "number_unbacked", "repeat", "over_cap", "too_many_open"


def one_line(text) -> str:
    return " ".join(str(text).split())


def same(text) -> str:
    """Titles compared case-folded with runs of white space as one space (SPEC 3.1)."""
    return one_line(text).casefold()


# --- What the reviewer is given ---

def step_number(conn, brief, step_id: str) -> tuple[int, str] | None:
    """(number, name) of a step of the process, or None."""
    for number, step in enumerate(process_steps(conn, brief), start=1):
        if step["id"] == step_id:
            return number, step["name"]
    return None


def plan_section(conn, brief: dict) -> dict:
    plan = without_meta(brief)
    steps = []
    for number, step in enumerate(process_steps(conn, brief), start=1):
        shown = {"id": step["id"], "number": number, "name": step["name"], "kind": step["kind"]}
        for key in ("method", "formula", "needs", "produces", "cadence", "origin", "reason"):
            if step.get(key):
                shown[key] = step[key]
        if step["id"].startswith("added_"):
            shown["in the plan"] = False
        steps.append(shown)
    shown = {"goal": plan.get("goal"), "mode": plan.get("mode"), "scope": plan.get("scope"),
             "particulars": plan.get("particulars", []), "inputs": plan.get("inputs", []),
             "steps": steps, "definition of done": plan.get("definition_of_done", []),
             "open questions": plan.get("open_questions", []),
             "glossary": [{key: entry.get(key) for key in ("term", "definition", "person_says")}
                          for entry in plan.get("glossary", [])]}
    return shown


def specs_section(conn, brief: dict) -> list[dict]:
    """The built specs, in words: formula, inputs, output, departures. Never code."""
    found = []
    for step in process_steps(conn, brief):
        if step["kind"] != "calculation":
            continue
        status, reason = step_status(conn, brief, step["id"])
        record = get_build(conn, step["id"]) or {}
        module = module_for_step(conn, step["id"])
        spec = record.get("spec") or ((get_module(conn, module) or {}).get("spec") if module else None)
        entry = {"step": step["id"], "status": status}
        if reason:
            entry["reason"] = reason
        if spec:
            entry["spec"] = {key: spec.get(key) for key in ("formula", "inputs", "output")}
        if record.get("departures"):
            entry["departures from the plan"] = record["departures"]
        found.append(entry)
    return found


def assumptions_section(conn, conversation: str, step_ids: set[str]) -> list[dict]:
    from ..answers.agent import step_of_module
    found = {}
    for row in conn.execute(
            "SELECT a.id, a.text, a.status, a.words, c.module FROM assumptions a"
            " JOIN run_assumptions r ON r.assumption_id = a.id JOIN calc_runs c ON c.id = r.run_id"
            " WHERE c.session_id = ? ORDER BY a.id", (conversation,)):
        entry = found.setdefault(row["id"], {"assumption": row["text"], "status": row["status"], "steps": []})
        if row["words"]:
            entry["their words"] = row["words"]
        step = step_of_module(conn, row["module"], step_ids)
        if step and step not in entry["steps"]:
            entry["steps"].append(step)
    return list(found.values())


def decisions_section(conn, conversation: str) -> list[dict]:
    return [{"step": row["step_id"], "question": row["question"], "options": json.loads(row["options"]),
             "choice": row["choice"], "words": row["words"]}
            for row in conn.execute("SELECT * FROM decisions WHERE conversation = ? AND status = 'answered'"
                                    " ORDER BY id", (conversation,))]


def runs_section(conn, conversation: str, step_ids: set[str]) -> list[dict]:
    from ..answers.agent import step_of_module
    rows = conn.execute("SELECT * FROM calc_runs WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                        (conversation, LAST_RUNS)).fetchall()
    return [{"step": step_of_module(conn, row["module"], step_ids), "module": row["module"],
             "inputs": json.loads(row["inputs"]), "assumptions": json.loads(row["assumptions"]),
             "output": json.loads(row["output"])} for row in reversed(rows)]


def challenge_rows(conn, conversation: str) -> list:
    return conn.execute("SELECT * FROM challenges WHERE conversation = ? ORDER BY id", (conversation,)).fetchall()


def challenges_section(conn, conversation: str) -> list[dict]:
    return [{"step": row["step_id"], "title": row["title"], "kind": row["kind"], "status": row["status"]}
            for row in challenge_rows(conn, conversation)]


def replies_section(conn, conversation: str) -> list[dict]:
    """What the person said in review threads: each thread with its challenge, so an answer has its question."""
    by_thread = {row["thread_id"]: row for row in challenge_rows(conn, conversation)}
    found = []
    for thread in list_threads(conn, conversation):
        row = by_thread.get(thread["id"])
        words = [message["text"] for message in thread["messages"] if message["who"] == "you"]
        if thread["kind"] == "review" and row is not None and words:
            found.append({"step": row["step_id"], "title": row["title"], "kind": row["kind"],
                          "concern": row["concern"], "their replies": words})
    return found


def user_message(conn, config, conversation: str, memory: dict, brief: dict) -> str:
    step_ids = {step["id"] for step in process_steps(conn, brief)}
    sections = {
        "today": today_of(memory).isoformat(),
        "plan": plan_section(conn, brief),
        "built specs": specs_section(conn, brief),
        "assumptions": assumptions_section(conn, conversation, step_ids),
        "decisions": decisions_section(conn, conversation),
        "saved inputs": saved_inputs(conn),
        "last runs": runs_section(conn, conversation, step_ids),
        "earlier challenges": challenges_section(conn, conversation),
        "the person's replies in review threads": replies_section(conn, conversation),
    }
    return format_sections(sections) + "\n\n" + CLOSING


# --- Looking things up ---

class Lookups:
    """The pass's lookups through the research desk. Only a general question goes out (the desk refuses a digit)."""

    def __init__(self, work, desk, pass_no: int):
        self.work, self.desk, self.pass_no = work, desk, pass_no
        self.asked = 0
        self.fetched: dict[str, str] = {}       # url -> title, of every source a lookup of this pass returned
        self.texts: list[str] = []              # what came back, a source of the number check

    def __call__(self, call) -> tuple[str, bool]:
        if self.asked >= MAX_LOOKUPS:
            return TOO_MANY_LOOKUPS, True
        query = call.arguments.get("query")
        query = one_line(query) if isinstance(query, str) else ""
        self.asked += 1
        self.work.progress(f"looking up: {query}"[:80], what="review")
        try:
            entry = self.desk.look_up_general(query)
        except Exception as error:
            entry = {"status": "failed", "error": one_line(error) or type(error).__name__, "sources": [],
                     "name": "", "definition": "", "origin": ""}
        sources = [{"title": source["title"], "url": source["url"]} for source in entry.get("sources") or []]
        self.work.record("review.lookup", {"pass": self.pass_no, "query": query, "status": entry["status"],
                                           "sources": sources, "origin": entry.get("origin", ""),
                                           "error": entry.get("error", "")}, "agent")
        if entry["status"] == "found":
            self.fetched.update({source["url"]: source["title"] for source in sources})
            self.texts += [entry["name"], entry["definition"]]
            return json.dumps({"name": entry["name"], "definition": entry["definition"], "sources": sources}), False
        if entry["status"] == "failed":
            return LOOKUP_FAILED.format(error=entry.get("error", "")), True
        return NOT_FOUND, False


# --- The checks of SPEC 7.2 ---

def check(raw, *, step_ids: set[str], seen: set[tuple[str, str]], lookups: Lookups, sources: list) -> tuple[dict | None, str]:
    """A challenge as the harness keeps it, or (None, the reason it is dropped)."""
    if not isinstance(raw, dict):
        return None, BAD_VALUE
    step, title = raw.get("step"), raw.get("title")
    kind, change, impact = raw.get("kind"), raw.get("change"), raw.get("impact")
    concern, proposal, cited = raw.get("concern"), raw.get("proposal"), raw.get("sources", [])
    if not isinstance(step, str) or step not in step_ids:
        return None, NOT_A_STEP
    if not isinstance(title, str) or not 1 <= len(one_line(title)) <= TITLE_LENGTH:
        return None, BAD_TITLE
    if kind not in KINDS or change not in CHANGES or impact not in IMPACTS \
            or not isinstance(concern, str) or not one_line(concern) or not isinstance(proposal, str) \
            or not isinstance(cited, list) or not all(isinstance(each, str) for each in cited):
        return None, BAD_VALUE
    if kind == "question" and (one_line(proposal) or change != "none"):
        return None, BAD_QUESTION
    if kind == "challenge" and not one_line(proposal):
        return None, NO_PROPOSAL
    text = f"{concern} {proposal}"
    if any(url not in lookups.fetched for url in cited) \
            or any(url not in lookups.fetched for url in URL.findall(text)) \
            or (not cited and "wikipedia" in text.casefold()):
        return None, UNFETCHED                  # outside information needs a source the harness fetched
    if unbacked(f"{title} {concern} {proposal}", sources):
        return None, UNBACKED
    if (step, same(title)) in seen:
        return None, REPEAT
    seen.add((step, same(title)))
    return {"step": step, "kind": kind, "title": one_line(title), "concern": one_line(concern),
            "proposal": one_line(proposal), "change": change, "impact": impact,
            "sources": [{"title": lookups.fetched[url], "url": url} for url in dict.fromkeys(cited)]}, ""


def keep(conn, conversation: str, report: list, *, step_ids: set[str], lookups: Lookups, sources: list):
    """Check, rank and cap a report. Returns (kept in order, [(challenge or raw, reason)] dropped)."""
    seen = {(row["step_id"], same(row["title"])) for row in challenge_rows(conn, conversation)}
    passed, dropped = [], []
    for raw in report:
        found, reason = check(raw, step_ids=step_ids, seen=seen, lookups=lookups, sources=sources)
        if found is None:
            dropped.append((raw, reason))
        else:
            passed.append(found)
    passed.sort(key=lambda each: IMPACTS.index(each["impact"]))          # stable: the reviewer's order inside a level
    room = 0 if MAX_OPEN <= open_count(conn, conversation) else min(MAX_PER_PASS, MAX_OPEN - open_count(conn, conversation))
    dropped += [(each, TOO_MANY_OPEN if room == 0 else OVER_CAP) for each in passed[room:]]
    return passed[:room], dropped


def open_count(conn, conversation: str) -> int:
    return sum(1 for row in challenge_rows(conn, conversation) if row["status"] == "open")


# --- A pass ---

def thread_text(challenge: dict) -> str:
    return challenge["concern"] + (f"\n\nProposed: {challenge['proposal']}" if challenge["proposal"] else "")


def open_thread(work, conversation: str, pass_no: int, rank: int, challenge: dict) -> str:
    """Store one kept challenge and open its review thread. Returns the challenge id, 'c<n>'."""
    thread = add_thread(work.conn, conversation, kind="review", step=challenge["step"], title=challenge["title"])
    cursor = work.conn.execute(
        "INSERT INTO challenges (ts, conversation, pass, step_id, kind, title, concern, proposal, change, impact,"
        " rank, sources, status, thread_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
        (db.now(), conversation, pass_no, challenge["step"], challenge["kind"], challenge["title"],
         challenge["concern"], challenge["proposal"], challenge["change"], challenge["impact"], rank,
         json.dumps(challenge["sources"]), thread))
    work.conn.commit()
    work.post(thread_text(challenge), who="reviewer", thread=thread, data={"sources": challenge["sources"]})
    return f"c{cursor.lastrowid}"


def run_pass(work, trigger: str) -> None:
    """One reviewer pass (a review-lane job)."""
    brief = plan_of(work.config)
    if brief is None:
        return
    conn, conversation, memory = work.conn, work.conversation, work.session.memory
    started = time.monotonic()
    pass_no = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM review_passes").fetchone()[0]
    mark = conn.execute("SELECT COALESCE(MAX(id), 0) FROM assumptions").fetchone()[0]     # this pass sees them all
    work.record("review.started", {"pass": pass_no, "trigger": trigger})
    work.progress("looking at how the plan is thought about", what="review")

    message = user_message(conn, work.config, conversation, memory, brief)
    step_ids = {step["id"] for step in process_steps(conn, brief)}
    lookups = Lookups(work, work.desk() or default_desk(work.config, conn), pass_no)
    messages = [{"role": "user", "content": message}]
    report, reminded = None, False
    for _ in range(MAX_CALLS):
        response = work.model.complete(system=PROMPT.read_text(encoding="utf-8"), messages=messages,
                                       tools=[LOOK_UP, REPORT])
        if not response.tool_calls:
            if reminded:
                break
            reminded = True
            messages += [{"role": "assistant", "content": response.text}, {"role": "user", "content": NO_REPORT}]
            continue
        results, reports = [], []
        for call in sorted(response.tool_calls, key=lambda each: each.name == "report"):     # lookups first
            if call.name == "look_up":
                content, failed = lookups(call)
            elif call.name == "report":
                found = call.arguments.get("challenges")
                if reports:
                    content, failed = ONE_REPORT, True
                elif not isinstance(found, list):
                    content, failed = BAD_REPORT, True
                else:
                    reports.append(found)
                    content, failed = "Received.", False
            else:
                content, failed = f"There is no tool called {call.name} here.", True
            results.append({"role": "tool", "tool_call_id": call.id, "content": content,
                            **({"is_error": True} if failed else {})})
        messages.append({"role": "assistant", "content": response.text, "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
        messages.extend(results)
        if reports:
            report = reports[0]
            break

    kept, dropped = [], []
    if report is not None:
        sources = [message, *lookups.texts]
        kept, dropped = keep(conn, conversation, report, step_ids=step_ids, lookups=lookups, sources=sources)
    for rank, challenge in enumerate(kept, start=1):
        challenge_id = open_thread(work, conversation, pass_no, rank, challenge)
        work.record("review.kept", {"pass": pass_no, "challenge": challenge_id, "step": challenge["step"],
                                    "kind": challenge["kind"], "title": challenge["title"],
                                    "change": challenge["change"], "impact": challenge["impact"], "rank": rank,
                                    "sources": [source["url"] for source in challenge["sources"]]}, "agent")
        work.changed()
    for raw, reason in dropped:
        shown = raw if isinstance(raw, dict) else {}
        work.record("review.dropped", {"pass": pass_no, "step": shown.get("step"), "title": shown.get("title"),
                                       "reason": reason}, "agent")
    seconds = round(time.monotonic() - started, 1)
    conn.execute('INSERT INTO review_passes (id, ts, conversation, "trigger", lookups, kept, dropped, seconds,'
                 " assumption_mark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (pass_no, db.now(), conversation, trigger, lookups.asked, len(kept), len(dropped), seconds, mark))
    conn.commit()
    work.record("review.finished", {"pass": pass_no, "trigger": trigger, "lookups": lookups.asked,
                                    "kept": len(kept), "dropped": len(dropped), "reported": report is not None,
                                    "seconds": seconds})
    work.changed()


def queue_pass(queue, trigger: str) -> bool:
    """Ask for a pass on the review lane (`queue` is a Work or a Session). A pass asked for while another waits
    in the queue is the same pass; one asked for while one runs is the one more that follows it."""
    return queue.queue("review", lambda work: run_pass(work, trigger), what="review", key="review",
                       text="looking at how the plan is thought about")


def new_assumptions(conn, run_ids) -> list[int]:
    """Ids of the assumptions of these runs that no pass has seen: stored after the last pass began."""
    mark = conn.execute("SELECT COALESCE(MAX(assumption_mark), 0) FROM review_passes").fetchone()[0]
    found = []
    for run_id in run_ids:
        found += [row[0] for row in conn.execute(
            "SELECT assumption_id FROM run_assumptions WHERE run_id = ? AND assumption_id > ?", (run_id, mark))]
    return found
