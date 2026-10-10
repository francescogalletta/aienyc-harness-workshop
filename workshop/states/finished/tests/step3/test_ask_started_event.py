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


def test_the_payload_is_the_date_of_the_conversation_and_nothing_else(agent, conn, brief):
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"], today=date(2031, 1, 5))
    assert h.events(conn, "ask.started") == [("ask.started", "harness", {"today": "2031-01-05"})]
    assert list(h.payloads(conn, "ask.started")[0]) == ["today"]


def test_it_comes_before_the_first_message_of_the_person(agent, conn, brief):
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"], today=h.DAY)
    kinds = [kind for _, kind, _, _ in session_events(conn)]
    assert kinds.index("ask.started") == 0 and kinds.index("ask.started") < kinds.index("ask.message")


def test_it_is_recorded_before_the_opening_question_is_asked(agent, conn, brief):
    seen = []

    def ask(text):
        seen.append([kind for _, kind, _, _ in session_events(conn)])
        return "/quit"

    agent.run_agent(model=ScriptedModel([]), conn=conn, brief=brief, ask=ask, say=lambda text="": None,
                    session_id="the-session", question="", today=h.DAY)
    assert seen == [["ask.started"]]


def test_a_session_that_ends_at_once_holds_only_that_event(agent, conn, brief):
    person = converse(agent, conn, brief, [], ["/quit"], question="", today=h.DAY)
    assert person.asked == [h.OPENING]
    assert [kind for _, kind, _, _ in session_events(conn)] == ["ask.started"]


def test_it_is_recorded_before_the_first_model_call(agent, conn, brief):
    class Spy(ScriptedModel):
        def complete(self, **kwargs):
            Spy.kinds_at_call = [kind for _, kind, _, _ in session_events(conn)]
            return super().complete(**kwargs)

    person = h.Person("/quit")
    agent.run_agent(model=Spy([h.say_text("Hello.")]), conn=conn, brief=brief, ask=person.ask, say=person.say,
                    session_id="the-session", question=h.QUESTION, today=h.DAY)
    assert Spy.kinds_at_call[0] == "ask.started"


def test_the_default_date_is_the_real_date(agent, conn, brief):
    before = date.today()
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"])
    after = date.today()
    [(_, _, payload)] = h.events(conn, "ask.started")
    assert payload["today"] in {before.isoformat(), after.isoformat()}


def test_the_date_is_the_one_the_conversation_uses(agent, conn, brief):
    model = ScriptedModel([h.say_text("Hello.")])
    person = h.Person("/quit")
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="the-session",
                    question=h.QUESTION, today=date(2029, 12, 31))
    assert "[today]\n2029-12-31" in model.calls[0]["system"]
    assert h.payloads(conn, "ask.started") == [{"today": "2029-12-31"}]


def test_each_run_records_its_own_event_under_its_own_session(agent, conn, brief):
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"], session_id="one", today=date(2026, 3, 14))
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"], session_id="two", today=date(2026, 4, 2))
    rows = conn.execute("SELECT session_id, payload FROM events WHERE kind = 'ask.started' ORDER BY id").fetchall()
    assert [(r["session_id"], json.loads(r["payload"])) for r in rows] == [
        ("one", {"today": "2026-03-14"}), ("two", {"today": "2026-04-02"})]


def test_it_is_not_a_message_nor_a_reply(agent, conn, brief):
    converse(agent, conn, brief, [h.say_text("Hello.")], ["/quit"], today=h.DAY)
    assert h.payloads(conn, "ask.message") == [{"text": h.QUESTION}]
    assert len(h.payloads(conn, "ask.reply")) == 1 and len(h.payloads(conn, "ask.started")) == 1
