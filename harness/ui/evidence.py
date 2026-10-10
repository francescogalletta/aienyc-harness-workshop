"""Reading the evidence (SPEC 7.3, 7.4, 8.9 and 9.9).

Seven functions, each taking an open connection. Six only read; `test_now` makes
one fresh, recorded test run. Each returns exactly the JSON body of its
endpoint, or None for not found. No model writes any of it.
"""
import json

from ..calc.added import list_added_steps, step_label
from ..calc.builder import plan_words
from ..calc.findings import list_findings
from ..calc.gate import run_tests
from ..calc.provenance import trace
from ..calc.registry import FILES, file_status, get_module, list_modules, module_dir, step_map
from ..config import load_config


# --- Small readers ---------------------------------------------------------------

def _brief() -> dict | None:
    """The brief in the brief folder, whatever its status, without `meta`; None when there is none."""
    try:
        brief = json.loads((load_config().brief_dir / "domain_brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {key: value for key, value in brief.items() if key != "meta"} if isinstance(brief, dict) else None


def _meta_status() -> str | None:
    try:
        meta = json.loads((load_config().brief_dir / "domain_brief.json").read_text(encoding="utf-8")).get("meta")
    except (OSError, ValueError, AttributeError):
        return None
    status = meta.get("status") if isinstance(meta, dict) else None
    return status if isinstance(status, str) else None


def _brief_steps(brief) -> list[dict]:
    steps = brief.get("process") if brief else None
    return [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []


def _reference(step_id: str, in_brief: set) -> dict:
    return {"id": step_id, "label": step_label(step_id), "in_brief": step_id in in_brief}


def _test_run(row, report: bool = False) -> dict | None:
    if row is None:
        return None
    run = {"id": row["id"], "ts": row["ts"], "reason": row["reason"], "passed": bool(row["passed"]),
           "fingerprint": row["fingerprint"]}
    if report:
        run["report"] = json.loads(row["report"])
    return run


def _event(row) -> dict:
    return {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "kind": row["kind"],
            "actor": row["actor"], "payload": json.loads(row["payload"])}


def _replay(conn, session_id: str) -> dict | None:
    row = conn.execute("SELECT payload FROM events WHERE session_id = ? AND kind = 'replay.scenario'"
                       " ORDER BY id LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    return {"example": payload.get("example"), "scenario": payload.get("scenario")}


def _count(conn, session_id: str, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ? AND kind = ?",
                        (session_id, kind)).fetchone()[0]


# --- summary ---------------------------------------------------------------------

def summary(conn, *, interview: bool) -> dict:
    """What the page needs to start (SPEC 7.4)."""
    brief = _brief()
    in_brief = {step.get("id") for step in _brief_steps(brief)}
    mapped = step_map(conn)
    process = []
    for step in [*_brief_steps(brief), *list_added_steps(conn)]:
        reference = _reference(step.get("id"), in_brief)
        process.append({**reference, "name": step.get("name"), "kind": step.get("kind"),
                        "module": mapped.get(step.get("id"))})

    modules = []
    for module in list_modules(conn):
        last = conn.execute("SELECT * FROM test_runs WHERE module = ? ORDER BY id DESC LIMIT 1",
                            (module["name"],)).fetchone()
        modules.append({"name": module["name"], "steps": [_reference(step, in_brief) for step in module["steps"]],
                        "fingerprint": module["fingerprint"], "registered_at": module["registered_at"],
                        "file_status": file_status(conn, module["name"]), "last_test": _test_run(last)})

    sessions = []
    for row in conn.execute("SELECT session_id, MIN(id) AS first_id, MAX(id) AS last_id, COUNT(*) AS n"
                            " FROM events GROUP BY session_id ORDER BY first_id DESC"):
        first = conn.execute("SELECT ts, kind FROM events WHERE id = ?", (row["first_id"],)).fetchone()
        last = conn.execute("SELECT ts FROM events WHERE id = ?", (row["last_id"],)).fetchone()
        sessions.append({"session_id": row["session_id"], "started": first["ts"], "ended": last["ts"],
                         "events": row["n"], "first_kind": first["kind"]})

    conversations = []
    asked = {row["session_id"] for row in conn.execute(
        "SELECT DISTINCT session_id FROM events WHERE kind = 'ask.message'")}
    for session in sessions:
        sid = session["session_id"]
        if sid not in asked:
            continue
        first = conn.execute("SELECT payload FROM events WHERE session_id = ? AND kind = 'ask.message'"
                             " ORDER BY id LIMIT 1", (sid,)).fetchone()
        conversations.append({
            "session_id": sid, "started": session["started"], "ended": session["ended"],
            "first_message": json.loads(first["payload"]).get("text"),
            "messages": _count(conn, sid, "ask.message"), "replies": _count(conn, sid, "ask.reply"),
            "withheld": _count(conn, sid, "ask.withheld"), "corrections": _count(conn, sid, "ask.correction"),
            "runs": conn.execute("SELECT COUNT(*) FROM calc_runs WHERE session_id = ?", (sid,)).fetchone()[0],
            "replay": _replay(conn, sid)})

    runs = [{"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "module": row["module"],
             "output": json.loads(row["output"])}
            for row in conn.execute("SELECT * FROM calc_runs ORDER BY id DESC")]
    kinds = [row["kind"] for row in conn.execute("SELECT DISTINCT kind FROM events ORDER BY kind")]
    loaded = {row["id"] for row in conn.execute("SELECT id FROM imports")}
    imports = [{**payload, "loaded_now": payload.get("id") in loaded}
               for payload in (json.loads(row["payload"]) for row in conn.execute(
                   "SELECT payload FROM events WHERE kind = 'data.imported' ORDER BY id DESC"))]
    summaries = []
    for row in conn.execute("SELECT * FROM data_summaries ORDER BY id DESC"):
        inputs = json.loads(row["inputs"])
        summaries.append({"id": row["id"], "ts": row["ts"], "session_id": row["session_id"],
                          "measure": inputs.get("measure"), "account": inputs.get("account"),
                          "value": json.loads(row["output"]).get("value")})
    return {"interview": interview, "database": str(load_config().db_path),
            "brief": {"goal": brief.get("goal"), "status": _meta_status()} if brief else None,
            "process": process, "modules": modules, "conversations": conversations, "runs": runs,
            "sessions": sessions, "kinds": kinds, "imports": imports, "summaries": summaries,
            "findings": list(reversed(list_findings(conn)))}


# --- conversation ----------------------------------------------------------------

def _traced_field(kind: str, payload: dict):
    """The text of an event whose numbers are traced, or None for the other events (SPEC 7.4)."""
    if kind in ("ask.reply", "ask.withheld") or (kind == "ask.correction" and payload.get("reason") == "reply"):
        field = payload.get("text")
    elif kind == "ask.module_requested":
        field = payload.get("request")
    elif kind in ("ask.gate", "ask.decision_asked"):
        field = payload.get("block")
    else:
        return None
    return field if isinstance(field, str) else None


def conversation(conn, session_id: str) -> dict | None:
    """One conversation as it happened, with the numbers of its replies traced (SPEC 7.4)."""
    rows = conn.execute("SELECT * FROM events WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    events = [_event(row) for row in rows]
    if not any(event["kind"] == "ask.message" for event in events):
        return None
    started = next((event for event in events if event["kind"] == "ask.started"), None)
    today = started["payload"].get("today") if started else None
    if not isinstance(today, str):
        today = events[0]["ts"][:10]
    brief = _brief()

    # Inputs and notes come from any session; runs and the person's words from this one (SPEC 7.3).
    elsewhere = [_event(row) for row in conn.execute(
        "SELECT * FROM events WHERE kind IN ('ask.input_saved', 'calc.note_saved') ORDER BY id")]
    shown = []
    for event in events:
        before = event["id"]
        field = _traced_field(event["kind"], event["payload"])
        numbers = None
        if field is not None:
            sources = [("run", each["payload"].get("run_id"),
                        {"inputs": each["payload"].get("inputs"), "output": each["payload"].get("output")})
                       for each in events if each["kind"] == "calc.run" and each["id"] < before]
            sources += [("data", each["payload"].get("id"), each["payload"].get("output")) for each in events
                        if each["kind"] == "data.summary" and each["id"] < before]
            sources += [("input", None, each["payload"].get("value")) for each in elsewhere
                        if each["kind"] == "ask.input_saved" and each["id"] < before]
            sources += [("note", None, each["payload"].get("text")) for each in elsewhere
                        if each["kind"] == "calc.note_saved" and each["id"] < before]
            if brief is not None:
                sources.append(("brief", None, brief))
            sources += [("person", None, each["payload"].get("text")) for each in events
                        if each["kind"] in ("ask.message", "ask.module_decision") and each["id"] < before]
            sources += [("person", None, each["payload"].get("words")) for each in events
                        if each["kind"] == "ask.decision" and each["id"] < before]
            sources += [("person", None, each["payload"].get("carried")) for each in events
                        if each["kind"] == "aside.closed" and isinstance(each["payload"].get("carried"), str)
                        and each["id"] < before]
            sources.append(("today", None, today))
            numbers = trace(field, sources)
        shown.append({"id": event["id"], "ts": event["ts"], "kind": event["kind"], "actor": event["actor"],
                      "payload": event["payload"], "numbers": numbers})
    return {"session_id": session_id, "today": today, "replay": _replay(conn, session_id), "events": shown}


# --- run -------------------------------------------------------------------------

def run(conn, run_id: int) -> dict | None:
    """One calculation run and the test run it relied on (SPEC 7.4)."""
    row = conn.execute("SELECT * FROM calc_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    test = conn.execute("SELECT * FROM test_runs WHERE id = ?", (row["test_run_id"],)).fetchone()
    module = get_module(conn, row["module"])
    return {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "module": row["module"],
            "fingerprint": row["fingerprint"], "inputs": json.loads(row["inputs"]),
            "assumptions": json.loads(row["assumptions"]), "expected": row["expected"],
            "output": json.loads(row["output"]), "test_run": _test_run(test),
            "registered_now": module is not None and module["fingerprint"] == row["fingerprint"]}


# --- module ----------------------------------------------------------------------

def _file_text(name: str, file: str) -> str | None:
    try:
        return (module_dir(name) / file).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def _examples(text: str | None):
    try:
        found = json.loads(text) if text is not None else None
    except ValueError:
        return None
    return found if isinstance(found, list) else None


def _about(payload: dict, name: str, step: str) -> bool:
    """Is an event of the build about this module or its step?"""
    shown = payload.get("step")
    modules = payload.get("modules")
    return (payload.get("module") == name or (step is not None and shown == step)
            or (step is not None and isinstance(shown, dict) and shown.get("id") == step)
            or (isinstance(modules, list) and name in modules))


def module(conn, name: str) -> dict | None:
    """One registered module: its files, examples, tests, runs and the build that made it (SPEC 7.4)."""
    registered = get_module(conn, name)
    if registered is None:
        return None
    row = conn.execute("SELECT session_id FROM modules WHERE name = ?", (name,)).fetchone()
    brief = _brief()
    in_brief = {step.get("id") for step in _brief_steps(brief)}
    files = {file: _file_text(name, file) for file in FILES}

    adopted = None
    for event in conn.execute("SELECT * FROM events WHERE kind = 'calc.module_adopted' ORDER BY id DESC"):
        payload = json.loads(event["payload"])
        if payload.get("module") == name and payload.get("fingerprint") == registered["fingerprint"]:
            adopted = {"ts": event["ts"], "how": payload.get("how"), "session_id": event["session_id"]}
            break

    registered_test = conn.execute("SELECT * FROM test_runs WHERE id = ?", (registered["test_run_id"],)).fetchone()
    last_test = conn.execute("SELECT * FROM test_runs WHERE module = ? ORDER BY id DESC LIMIT 1",
                             (name,)).fetchone()
    runs = [{"id": each["id"], "ts": each["ts"], "session_id": each["session_id"],
             "inputs": json.loads(each["inputs"]), "output": json.loads(each["output"])}
            for each in conn.execute("SELECT * FROM calc_runs WHERE module = ? ORDER BY id DESC", (name,))]

    history = []
    for event in conn.execute("SELECT * FROM events WHERE kind = 'calc.module_registered' ORDER BY id DESC"):
        payload = json.loads(event["payload"])
        if payload.get("module") != name:
            continue
        step = payload.get("step")
        history = [_event(each) for each in conn.execute(
            "SELECT * FROM events WHERE session_id = ? AND id <= ? ORDER BY id", (event["session_id"], event["id"]))
            if _about(json.loads(each["payload"]), name, step)]
        break

    return {"name": name, "fingerprint": registered["fingerprint"], "registered_at": registered["registered_at"],
            "session_id": row["session_id"], "spec": registered["spec"], "plan": plan_words(registered["spec"]),
            "steps": [_reference(step, in_brief) for step in registered["steps"]],
            "file_status": file_status(conn, name), "files": files, "examples": _examples(files["golden.json"]),
            "adopted": adopted, "registered_test": _test_run(registered_test),
            "last_test": _test_run(last_test, report=True), "runs": runs, "history": history}


# --- data summary ----------------------------------------------------------------

def data_summary(conn, summary_id: int) -> dict | None:
    """One data summary, and the findings that rest on it (SPEC 7.4, step 5)."""
    row = conn.execute("SELECT * FROM data_summaries WHERE id = ?", (summary_id,)).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "inputs": json.loads(row["inputs"]),
            "output": json.loads(row["output"]), "imports": json.loads(row["imports"]),
            "findings": [each["id"] for each in list_findings(conn) if each["summary"] == summary_id]}


# --- events ----------------------------------------------------------------------

def events_page(conn, *, kind=None, session=None, before=None, limit=200) -> dict:
    """The raw event log, newest first (SPEC 7.4). `kind` ending in `.` is a prefix."""
    where, values = [], []
    if kind:
        if kind.endswith("."):
            where.append("substr(kind, 1, ?) = ?")
            values += [len(kind), kind]
        else:
            where.append("kind = ?")
            values.append(kind)
    if session:
        where.append("session_id = ?")
        values.append(session)
    if before is not None:
        where.append("id < ?")
        values.append(before)
    sql = "SELECT * FROM events" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    rows = conn.execute(sql, [*values, limit + 1]).fetchall()
    return {"events": [_event(row) for row in rows[:limit]], "more": len(rows) > limit}


# --- test now --------------------------------------------------------------------

def test_now(conn, name: str, *, session_id: str) -> dict | None:
    """Run the tests of a registered module now, and record the run (SPEC 7.4). The one write."""
    if get_module(conn, name) is None:
        return None
    made = run_tests(conn, name, reason="status", session_id=session_id)
    row = conn.execute("SELECT * FROM test_runs WHERE id = ?", (made["test_run_id"],)).fetchone()
    return {"module": name, "file_status": file_status(conn, name), "test_run": _test_run(row, report=True)}
