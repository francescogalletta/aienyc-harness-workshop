"""ARCHITECTURE.md 4.1 to 4.3 and SPEC 2.3: the session, the lanes, the waiting slot, routing and layers."""
import json
import threading

import pytest

from harness import db
from harness.config import load_config
from harness.core import NO_ROUTE, BadAction, NotNow, Session, add_thread, list_threads
from harness.layers import BASE
from layer0_helpers import SETTLE, fake_layer, routes_all

TOP_LEVEL = {"version", "layers", "product", "phase", "error", "lanes", "activity", "waiting", "goal",
             "context", "inputs", "steps", "edges", "chat"}


def events(session, kind) -> list[dict]:
    return [json.loads(row["payload"]) for row in db.list_events(session.conn, kind=kind)]


def texts(state) -> list[tuple[str, str]]:
    return [(message["who"], message["text"]) for message in state["chat"]]


def replier(text="a reply"):
    def handle(work, message):
        work.post(text)
    return handle


# --- Creation and the state document ---

def test_a_new_database_gets_a_conversation_that_the_next_session_keeps(open_session):
    first = open_session()
    conversation = first.conversation
    stored = first.conn.execute("SELECT value FROM meta WHERE key = 'conversation'").fetchone()["value"]
    assert stored == conversation
    first.close()
    assert open_session().conversation == conversation


def test_the_state_document_has_the_top_level_of_the_contract(open_session):
    state = open_session().state()
    assert TOP_LEVEL <= set(state)
    assert state["layers"] == [0]
    assert state["product"] == "Financial Advisor Harness"
    assert state["phase"] == "empty"
    assert state["error"] is None and state["waiting"] is None and state["goal"] is None
    assert state["context"] is None
    assert state["lanes"] == {"main": "idle", "side": "idle", "review": "idle"}
    assert (state["activity"], state["inputs"], state["steps"], state["edges"], state["chat"]) == ([], {}, [], [], [])
    assert isinstance(state["version"], int)
    json.dumps(state)           # it goes to the page as it is


def test_discovery_is_used_when_no_layers_are_given(monkeypatch):
    monkeypatch.setenv("HARNESS_LAYERS", "0")
    session = Session(load_config())
    try:
        assert session.state()["layers"] == [0]
    finally:
        session.close()


def test_the_enabled_layers_schemas_are_applied(open_session, tmp_path):
    schema = tmp_path / "fake.sql"
    schema.write_text("CREATE TABLE IF NOT EXISTS fake_rows (id INTEGER PRIMARY KEY);", encoding="utf-8")
    session = open_session(fake_layer(1, schema=schema))
    names = {row["name"] for row in session.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"events", "meta", "messages", "threads", "fake_rows"} <= names


def test_layers_contribute_in_order_and_the_core_finishes_their_steps(open_session):
    seen = []

    def first(view, state):
        seen.append(("first", view.conversation))
        state["phase"] = "accepted"
        state["steps"].append({"id": "s1", "number": 1, "name": "One", "kind": "calculation",
                               "open_questions": [{"text": "q"}]})

    def second(view, state):
        seen.append(("second", state["phase"]))
        state["steps"][0]["build"] = {"status": "stale"}

    session = open_session(fake_layer(1, contribute=first), fake_layer(2, contribute=second))
    state = session.state()
    assert seen == [("first", session.conversation), ("second", "accepted")]
    assert state["layers"] == [0, 1, 2]
    assert state["steps"][0]["line"] == {"text": "Stale · rebuild", "kind": None}
    assert [mark["symbol"] for mark in state["steps"][0]["marks"]] == ["●"]
    assert state["steps"][0]["needs_you"] is False


def test_the_version_goes_up_on_a_change_and_not_otherwise(open_session):
    session = open_session()
    first = session.state()["version"]
    assert session.state()["version"] == first
    session.act("say", {"text": "hello"})
    assert session.settle(SETTLE)["version"] > first


# --- Saying something ---

def test_with_no_route_the_harness_says_nothing_can_answer(open_session):
    session = open_session()
    assert session.act("say", {"text": "  hello  "}) == (True, "")
    state = session.settle(SETTLE)
    assert texts(state) == [("you", "hello"), ("harness", NO_ROUTE)]
    assert state["chat"][0]["queued"] is False and state["chat"][0]["kind"] == "text"
    assert [each["who"] for each in events(session, "core.message")] == ["you", "harness"]
    assert events(session, "core.action")[0]["action"] == "say"


def test_the_highest_layer_that_routes_gets_the_message_on_the_main_lane(open_session):
    lanes = []

    def lower(work, message):
        work.post("from the lower layer")

    def higher(work, message):
        lanes.append(work.lane)
        work.post(f"from the higher layer about {message['step']}")

    session = open_session(fake_layer(1, route=routes_all(lower)),
                           fake_layer(2, route=lambda core, message: higher if message["step"] else None))
    session.act("say", {"text": "about a step", "step": "s3"})
    session.settle(SETTLE)
    session.act("say", {"text": "about nothing"})
    state = session.settle(SETTLE)
    assert [text for who, text in texts(state) if who == "assistant"] == [
        "from the higher layer about s3", "from the lower layer"]
    assert lanes == ["main"]
    assert state["chat"][0]["step"] == "s3"


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "   "}, {"text": 5}, {"text": "x", "step": 3},
                                     {"text": "x", "notice": ["m1"]}])
def test_a_say_with_a_bad_payload_is_refused_as_bad(open_session, payload):
    session = open_session()
    with pytest.raises(BadAction):
        session.act("say", payload)
    assert session.state()["chat"] == []


def test_an_unknown_action_is_bad_and_a_layer_action_runs(open_session):
    calls = []
    session = open_session(fake_layer(1, actions={"poke": lambda core, payload: calls.append(payload)}))
    with pytest.raises(BadAction):
        session.act("nothing_like_this", {})
    with pytest.raises(BadAction):
        session.act("poke", ["not", "an", "object"])
    assert session.act("poke", {"x": 1}) == (True, "")
    assert calls == [{"x": 1}]


def test_an_action_refused_now_gives_the_reason_and_records_nothing(open_session):
    def refuse(core, payload):
        raise NotNow("not while the moon is up")

    session = open_session(fake_layer(1, actions={"poke": refuse}))
    assert session.act("poke", {}) == (False, "not while the moon is up")
    assert events(session, "core.action") == []


def test_two_layers_cannot_register_the_same_action(open_session):
    action = {"poke": lambda core, payload: None}
    with pytest.raises(ValueError):
        open_session(fake_layer(1, actions=action), fake_layer(2, actions=action))


# --- Jobs, failures and activity ---

def test_a_job_that_raises_sets_one_line_of_error_and_the_lane_goes_on(open_session):
    def broken(work, message):
        raise RuntimeError("the thing\nbroke")

    session = open_session(fake_layer(1, route=lambda core, message: broken if message["text"] == "break"
                                      else replier("fine")))
    session.act("say", {"text": "break"})
    state = session.settle(SETTLE)
    assert state["error"] and "\n" not in state["error"]
    assert state["lanes"]["main"] == "idle"
    failed = events(session, "core.job_failed")
    assert len(failed) == 1 and {"lane", "what", "error"} <= set(failed[0])
    session.act("say", {"text": "again"})              # the next action clears the error
    state = session.settle(SETTLE)
    assert state["error"] is None
    assert ("assistant", "fine") in texts(state)


def test_activity_shows_what_runs_and_its_progress_then_empties(open_session):
    go_on, reported = threading.Event(), threading.Event()

    def slow(work, message):
        work.progress("writing the code, attempt 2", step="s4")
        reported.set()
        go_on.wait(SETTLE)

    slow.what = "build"
    session = open_session(fake_layer(1, route=routes_all(slow)))
    session.act("say", {"text": "go"})
    assert reported.wait(SETTLE)
    state = session.state()
    assert state["lanes"]["main"] == "working"
    [entry] = state["activity"]
    assert (entry["lane"], entry["what"], entry["step"], entry["text"]) == (
        "main", "build", "s4", "writing the code, attempt 2")
    assert entry["since"]
    go_on.set()
    state = session.settle(SETTLE)
    assert state["activity"] == [] and state["lanes"]["main"] == "idle"


def test_lanes_run_at_the_same_time_and_settle_waits_for_all(open_session):
    main_started, side_done, release = threading.Event(), threading.Event(), threading.Event()
    done = []

    def on_main(work):
        main_started.set()
        release.wait(SETTLE)
        done.append("main")

    def on_side(work):
        done.append(work.lane)
        side_done.set()

    session = open_session()
    session.queue("main", on_main, what="build")
    assert main_started.wait(SETTLE)
    session.queue("side", on_side, what="side")
    assert side_done.wait(SETTLE)           # the side lane did not wait for the main lane
    assert done == ["side"]
    assert session.state()["lanes"]["main"] == "working"
    release.set()
    state = session.settle(SETTLE)
    assert done == ["side", "main"]
    assert set(state["lanes"].values()) == {"idle"}


def test_a_job_queued_with_a_key_is_not_queued_twice_while_it_waits(open_session):
    started, release = threading.Event(), threading.Event()
    runs = []

    def blocker(work):
        started.set()
        release.wait(SETTLE)

    session = open_session()
    session.queue("review", blocker, what="review")
    assert started.wait(SETTLE)
    assert session.queue("review", lambda work: runs.append(1), what="review", key="pass") is True
    assert session.queue("review", lambda work: runs.append(2), what="review", key="pass") is False
    release.set()
    session.settle(SETTLE)
    assert runs == [1]


def test_the_model_is_made_once_and_shared_by_jobs(open_session):
    made = []

    def factory():
        made.append(1)
        return object()

    models = []
    session = open_session(fake_layer(1, route=routes_all(lambda work, message: models.append(work.model))),
                           model_factory=factory)
    session.act("say", {"text": "one"})
    session.settle(SETTLE)
    session.act("say", {"text": "two"})
    session.settle(SETTLE)
    assert len(made) == 1 and models[0] is models[1]


# --- The waiting slot ---

def asker(kind="message", **data):
    """A handler that waits on the person once and posts what came back."""
    def handle(work, message):
        answer = work.wait(kind, **data)
        work.post(json.dumps({key: answer.get(key) for key in ("text", "step", "notice", "action")}))
    return handle


def test_a_waiting_job_takes_the_next_message_as_its_answer(open_session):
    routed = []

    def route(core, message):
        routed.append(message["text"])
        return asker()

    session = open_session(fake_layer(1, route=route))
    session.act("say", {"text": "start"})
    state = session.settle(SETTLE)
    assert state["waiting"] == {"kind": "message"}
    assert state["lanes"]["main"] == "waiting"
    session.act("say", {"text": "my answer", "step": "s2", "notice": "m9"})
    state = session.settle(SETTLE)
    assert json.loads(state["chat"][-1]["text"]) == {"text": "my answer", "step": "s2", "notice": "m9",
                                                     "action": None}
    assert routed == ["start"]                  # the answer was not routed
    assert state["waiting"] is None and state["lanes"]["main"] == "idle"


def test_an_action_answers_the_waiting_slot_and_is_refused_when_nothing_waits(open_session):
    def accept(core, payload):
        if (core.waiting or {}).get("kind") != "plan":
            raise NotNow("no plan waits")
        core.answer({"action": "accept"})

    session = open_session(fake_layer(1, route=routes_all(asker("plan")), actions={"accept": accept}))
    assert session.act("accept", {}) == (False, "no plan waits")
    session.act("say", {"text": "propose"})
    assert session.settle(SETTLE)["waiting"] == {"kind": "plan"}
    assert session.act("accept", {}) == (True, "")
    state = session.settle(SETTLE)
    assert json.loads(state["chat"][-1]["text"])["action"] == "accept"
    with pytest.raises(NotNow):
        session.answer({"action": "late"})


def test_waiting_data_is_shown_in_the_state(open_session):
    session = open_session(fake_layer(1, route=routes_all(asker("decision", decision="d4", step="s7"))))
    session.act("say", {"text": "go"})
    assert session.settle(SETTLE)["waiting"] == {"kind": "decision", "decision": "d4", "step": "s7"}


def test_a_message_typed_while_the_main_lane_works_is_queued_then_routed(open_session):
    started, release = threading.Event(), threading.Event()

    def slow(work, message):
        started.set()
        release.wait(SETTLE)
        work.post(f"done with {message['text']}")

    session = open_session(fake_layer(1, route=routes_all(slow)))
    session.act("say", {"text": "first"})
    assert started.wait(SETTLE)
    session.act("say", {"text": "second"})
    state = session.state()
    second = next(message for message in state["chat"] if message["text"] == "second")
    assert second["queued"] is True
    release.set()
    state = session.settle(SETTLE)
    assert [text for who, text in texts(state) if who == "assistant"] == ["done with first", "done with second"]
    assert all(message["queued"] is False for message in state["chat"])


def test_a_message_queued_while_a_job_works_answers_its_wait_at_once(open_session):
    started, release = threading.Event(), threading.Event()

    def works_then_asks(work, message):
        started.set()
        release.wait(SETTLE)
        answer = work.wait("message")
        work.post(f"heard {answer['text']}")

    session = open_session(fake_layer(1, route=routes_all(works_then_asks)))
    session.act("say", {"text": "start"})
    assert started.wait(SETTLE)
    session.act("say", {"text": "typed early"})
    release.set()
    state = session.settle(SETTLE)
    assert texts(state)[-1] == ("assistant", "heard typed early")
    assert state["waiting"] is None


def test_closing_ends_a_job_that_waits_without_an_error(open_session):
    session = open_session(fake_layer(1, route=routes_all(asker())))
    session.act("say", {"text": "go"})
    session.settle(SETTLE)
    session.close()
    assert session.state()["error"] is None
    assert events(session, "core.job_failed") == []


# --- Hooks, conversations, messages and threads ---

def test_hooks_run_in_layer_order_and_loaded_runs_on_creation(open_session):
    calls = []
    session = open_session(
        fake_layer(1, hooks={"loaded": lambda core: calls.append(("loaded", 1, core)),
                             "step_built": lambda work, step: calls.append(("built", 1, step))}),
        fake_layer(2, hooks={"loaded": lambda core: calls.append(("loaded", 2, core))}))
    assert calls == [("loaded", 1, session), ("loaded", 2, session)]
    session.queue("main", lambda work: work.hook("step_built", work, "s2"), what="build")
    session.settle(SETTLE)
    assert calls[-1] == ("built", 1, "s2")


def test_a_loaded_hook_that_fails_is_reported_as_the_error(open_session):
    def broken(core):
        raise RuntimeError("cannot resume")

    session = open_session(fake_layer(1, hooks={"loaded": broken}))
    assert "cannot resume" in session.state()["error"]
    assert events(session, "core.job_failed")[0]["what"] == "loaded"


def test_a_new_conversation_starts_an_empty_chat(open_session):
    session = open_session()
    session.act("say", {"text": "hello"})
    session.settle(SETTLE)
    before = session.conversation
    after = session.new_conversation()
    assert after != before
    assert session.state()["chat"] == []
    assert session.conn.execute("SELECT value FROM meta WHERE key = 'conversation'").fetchone()["value"] == after


def test_message_data_shows_in_the_chat_and_can_be_updated(open_session):
    session = open_session()
    message = session.post("here", kind="notice", step="s1", data={"notice": {"status": "open"}, "_inner": 1})
    session.update_message(message, {"notice": {"status": "confirmed"}})
    [shown] = session.state()["chat"]
    assert shown["id"] == message and shown["kind"] == "notice" and shown["step"] == "s1"
    assert shown["notice"] == {"status": "confirmed"}
    assert "_inner" not in shown


def test_thread_messages_stay_out_of_the_main_chat(open_session):
    session = open_session()
    thread = add_thread(session.conn, session.conversation, kind="side", title="About step 1", step="s1")
    session.post("a side question", who="you", thread=thread)
    session.post("a side answer", thread=thread, data={"sources": []})
    assert session.state()["chat"] == []
    [found] = list_threads(session.conn, session.conversation)
    assert (found["id"], found["kind"], found["step"], found["status"]) == (thread, "side", "s1", "open")
    assert [(m["who"], m["text"]) for m in found["messages"]] == [("you", "a side question"),
                                                                 ("assistant", "a side answer")]
    assert found["messages"][1]["sources"] == []


def test_a_session_on_the_base_alone_uses_the_base_layer_object():
    session = Session(load_config(), layers=[BASE])
    try:
        assert session.layers == [BASE]
    finally:
        session.close()
