"""SPEC 7.2 and 7.8: `run_agent` records `ask.started` when it starts, before anything is asked."""
import json
from datetime import date

from harness.model import ScriptedModel
from step3_helpers import h


def converse(agent, conn, brief, script, answers, *, question=h.QUESTION, session_id="the-session", **options):
    person = h.Person(*answers)
    agent.run_agent(model=ScriptedModel(script), conn=conn, brief=brief, ask=person.ask, say=person.say,
                    session_id=session_id, question=question, **options)
    return person


def session_events(conn, session_id="the-session"):
    return [(r["id"], r["kind"], r["actor"], r["payload"]) for r in conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY id", (session_id,))]


def test_the_first_event_of_the_session_is_ask_started(agent, conn, brief):
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"], today=date(2026, 3, 14))
    first = session_events(conn)[0]
    assert first[1:3] == ("ask.started", "harness")
    assert json.loads(first[3]) == {"today": "2026-03-14"}
