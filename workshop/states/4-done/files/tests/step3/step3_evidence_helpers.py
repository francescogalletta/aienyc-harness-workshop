"""Shared by the evidence tests (SPEC 7.3 to 7.5): the JSON shapes worked out from the SPEC and from the database
file itself, never from the code under test."""
import json

import step3_helpers as s3
from step3_helpers import h

PROCESS_KEYS = ["id", "label", "in_brief", "name", "kind", "module"]
MODULE_ROW_KEYS = ["name", "steps", "fingerprint", "registered_at", "file_status", "last_test"]
TEST_RUN_KEYS = ["id", "ts", "reason", "passed", "fingerprint"]
EVENT_KEYS = ["id", "ts", "session_id", "kind", "actor", "payload"]
CONVERSATION_ROW_KEYS = ["session_id", "started", "ended", "first_message", "messages", "replies", "withheld",
                         "corrections", "runs", "replay"]
SESSION_ROW_KEYS = ["session_id", "started", "ended", "events", "first_kind"]
RUN_ROW_KEYS = ["id", "ts", "session_id", "module", "output"]
SUMMARY_KEYS = ["interview", "database", "brief", "process", "modules", "conversations", "runs", "sessions", "kinds"]
CONVERSATION_KEYS = ["session_id", "today", "replay", "events"]
CONVERSATION_EVENT_KEYS = ["id", "ts", "kind", "actor", "payload", "numbers"]
RUN_KEYS = ["id", "ts", "session_id", "module", "fingerprint", "inputs", "assumptions", "expected", "output",
            "test_run", "registered_now"]
MODULE_KEYS = ["name", "fingerprint", "registered_at", "session_id", "spec", "plan", "steps", "file_status", "files",
               "examples", "adopted", "registered_test", "last_test", "runs", "history"]
TRACE_KEYS = ["text", "start", "end", "source", "run_id"]
FILES = ("spec.json", "golden.json", "module.py", "tests.py")

NO_MODULE = "There is no registered module called '{name}'."
SURPLUS, MONTHS, YEARLY = "monthly_surplus", "months_to_goal", "yearly_cost"


def shown_test_run(row):
    return {"id": row["id"], "ts": row["ts"], "reason": row["reason"], "passed": bool(row["passed"]),
            "fingerprint": row["fingerprint"]}


def shown_test_run_with_report(row):
    return {**shown_test_run(row), "report": json.loads(row["report"])}


def event_of(row):
    return {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "kind": row["kind"],
            "actor": row["actor"], "payload": json.loads(row["payload"])}


def events_where(world, where="1", params=(), newest_first=False):
    rows = world.sql(f"SELECT * FROM events WHERE {where} ORDER BY id {'DESC' if newest_first else 'ASC'}", params)
    return [event_of(row) for row in rows]


def row_of_test_run(world, run_id):
    return world.sql("SELECT * FROM test_runs WHERE id = ?", (run_id,))[0]


def last_test_row(world, module):
    return world.sql("SELECT * FROM test_runs WHERE module = ? ORDER BY id DESC LIMIT 1", (module,))[0]


def module_row(world, name):
    return world.sql("SELECT * FROM modules WHERE name = ?", (name,))[0]


def steps_of(world, name):
    """The step references of a registered module, in step id order."""
    ids = [r["step_id"] for r in world.sql("SELECT step_id FROM step_modules WHERE module = ? ORDER BY step_id", (name,))]
    return [s3.step_ref(step_id, not step_id.startswith("added_")) for step_id in ids]


def traced_numbers(text, expected):
    return s3.traced(text, expected)


def post_test(api, module, **options):
    return api.post("/api/work/test", {"module": module}, **options)


def add_session(conn, session, *entries):
    """Record events in a new session of the database, through the public function.

    Each entry is (kind, payload) or (kind, payload, actor). Returns the ids, in order.
    """
    ids = []
    for entry in entries:
        kind, payload, *rest = entry
        ids.append(s3.record_payload(conn, session, kind, payload, rest[0] if rest else "harness"))
    return ids
