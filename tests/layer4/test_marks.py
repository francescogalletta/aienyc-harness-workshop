"""SPEC 6.1: run and mark. A run on something unconfirmed goes ahead and carries a mark; one action confirms,
another corrects."""
from harness.needs_you import marks
from layer4_helpers import act, assistant, events, notices, problems, refused, reply, run, say, step_of

ASSUMED = "Amount B stays at 20."


def total_with_assumption(open_session, *more):
    session = open_session([run("total", {"a": 10, "b": 20}, [ASSUMED]), reply("The total is 30, if B stays at 20."),
                            *more])
    return session, say(session, "A is 10 and B is 20, what is the total?")


def test_a_run_on_an_unconfirmed_assumption_goes_ahead_and_marks_the_step(open_session):
    session, state = total_with_assumption(open_session)
    assert state["waiting"] is None and state["lanes"]["main"] == "idle"
    answer = assistant(state)[-1]
    assert answer["kind"] == "text" and "30" in answer["text"]                  # nothing stopped for it
    step = step_of(state, "c1")
    assert [each["text"] for each in step["unconfirmed"]] == [ASSUMED]
    assert [mark["symbol"] for mark in step["marks"]] == ["◌"]
    assert step["line"] == {"text": "→ 30 ◌", "kind": "result"}
    assert step_of(state, "c2")["unconfirmed"] == [] and step_of(state, "c2")["marks"] == []
    assert problems(state, strict=True) == []


def test_the_answer_carries_a_notice_naming_the_assumptions_and_the_steps(open_session):
    session, state = total_with_assumption(open_session)
    (message,) = notices(state)
    assert message["id"] == assistant(state)[-1]["id"]
    notice = message["notice"]
    assert notice["status"] == "open" and notice["steps"] == ["c1"]
    assert [each["text"] for each in notice["assumptions"]] == [ASSUMED]
    assert notice["assumptions"][0]["id"] == step_of(state, "c1")["unconfirmed"][0]["id"]


def test_a_run_with_no_assumption_has_no_mark_and_no_notice(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}), reply("The total is 30.")])
    state = say(session, "A is 10 and B is 20, what is the total?")
    assert notices(state) == [] and step_of(state, "c1")["unconfirmed"] == []
    assert step_of(state, "c1")["marks"] == []


def test_the_same_sentence_is_one_assumption_however_it_is_written(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}, [ASSUMED, "amount  b stays at 20.", ASSUMED]),
                            run("double", {"total": 30}, ["AMOUNT B STAYS AT 20."]),
                            reply("The total is 30 and twice that is 60.")])
    state = say(session, "A is 10 and B is 20, what is twice the total?")
    (message,) = notices(state)
    assert len(message["notice"]["assumptions"]) == 1 and message["notice"]["steps"] == ["c1", "c2"]
    rows = session.conn.execute("SELECT key, status FROM assumptions").fetchall()
    assert [(row["key"], row["status"]) for row in rows] == [("amount b stays at 20.", "unconfirmed")]
    assert marks.key_of("  Amount   B stays at 20. ") == "amount b stays at 20."


def test_the_notice_names_only_the_steps_whose_runs_rested_on_something(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}), run("double", {"total": 30}, ["Twice is what is meant."]),
                            reply("The total is 30 and twice that is 60.")])
    state = say(session, "A is 10 and B is 20, what is twice the total?")
    assert notices(state)[0]["notice"]["steps"] == ["c2"]
    assert step_of(state, "c1")["marks"] == [] and [m["symbol"] for m in step_of(state, "c2")["marks"]] == ["◌"]


def test_confirming_clears_the_marks_and_the_notice(open_session):
    session, state = total_with_assumption(open_session)
    message = notices(state)[0]["id"]
    state = act(session, "confirm_assumptions", message=message)
    assert step_of(state, "c1")["unconfirmed"] == [] and step_of(state, "c1")["marks"] == []
    assert step_of(state, "c1")["line"]["text"] == "→ 30"
    assert notices(state)[0]["notice"]["status"] == "confirmed"
    assert [row["status"] for row in session.conn.execute("SELECT status FROM assumptions")] == ["confirmed"]
    assert events(session, "you.assumptions_confirmed")[0]["message"] == message


def test_a_confirmation_that_is_not_allowed_is_refused(open_session):
    session, state = total_with_assumption(open_session)
    message = notices(state)[0]["id"]
    assert refused(session, "confirm_assumptions", message="m999")
    assert refused(session, "confirm_assumptions", message=state["chat"][0]["id"])       # no notice there
    act(session, "confirm_assumptions", message=message)
    assert refused(session, "confirm_assumptions", message=message)                      # already confirmed
    try:
        session.act("confirm_assumptions", {})
    except ValueError:
        pass
    else:
        raise AssertionError("a missing message is a bad action")


def test_confirming_one_answer_clears_the_same_sentence_under_another(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}, [ASSUMED]), reply("The total is 30."),
                            run("double", {"total": 30}, [ASSUMED, "Twice is what is meant."]), reply("Twice is 60.")])
    say(session, "A is 10 and B is 20, what is the total?")
    state = say(session, "And twice that?")
    first, second = notices(state)
    assert [each["text"] for each in second["notice"]["assumptions"]] == [ASSUMED, "Twice is what is meant."]
    state = act(session, "confirm_assumptions", message=first["id"])
    assert step_of(state, "c1")["marks"] == []
    assert [each["text"] for each in step_of(state, "c2")["unconfirmed"]] == ["Twice is what is meant."]
    assert [m["notice"]["status"] for m in notices(state)] == ["confirmed", "open"]


def test_a_confirmed_assumption_is_not_marked_when_it_is_used_again(open_session):
    session, state = total_with_assumption(open_session, run("total", {"a": 10, "b": 20}, [ASSUMED]),
                                           reply("Still 30."))
    act(session, "confirm_assumptions", message=notices(state)[0]["id"])
    state = say(session, "Again please")
    assert len(notices(state)) == 1 and step_of(state, "c1")["unconfirmed"] == []


def test_saying_it_is_not_right_corrects_it_and_runs_the_steps_again(open_session):
    session, state = total_with_assumption(open_session, run("total", {"a": 10, "b": 25}),
                                           reply("With B at 25 the total is 35."))
    message = notices(state)[0]["id"]
    state = say(session, "B is 25 in fact", notice=message)
    row = session.conn.execute("SELECT status, words FROM assumptions").fetchone()
    assert (row["status"], row["words"]) == ("corrected", "B is 25 in fact")
    assert notices(state)[0]["notice"]["status"] == "changed"
    told = session.script.calls[2]["messages"][-1]["content"]
    assert told.startswith("[harness]") and ASSUMED in told and "B is 25 in fact" in told
    assert step_of(state, "c1")["unconfirmed"] == [] and step_of(state, "c1")["line"]["text"] == "→ 35"
    assert events(session, "you.assumptions_corrected")[0]["words"] == "B is 25 in fact"
    assert [m["who"] for m in state["chat"]][-2:] == ["you", "assistant"]


def test_correcting_an_answer_leaves_what_the_person_already_confirmed_alone(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}, [ASSUMED]), reply("The total is 30."),
                            run("double", {"total": 30}, [ASSUMED, "Twice is what is meant."]), reply("Twice is 60."),
                            reply("Noted.")])
    say(session, "A is 10 and B is 20, what is the total?")
    state = say(session, "And twice that?")
    first, second = notices(state)
    act(session, "confirm_assumptions", message=first["id"])
    state = say(session, "Twice was not what I meant", notice=second["id"])
    assert {row["text"]: row["status"] for row in session.conn.execute("SELECT text, status FROM assumptions")} == {
        ASSUMED: "confirmed", "Twice is what is meant.": "corrected"}
    told = session.script.calls[-1]["messages"][-1]["content"]
    assert "Twice is what is meant." in told and ASSUMED not in told


def test_until_it_is_run_again_a_corrected_step_still_counts_as_unconfirmed(open_session):
    session, state = total_with_assumption(open_session, reply("I will leave it."))
    state = say(session, "B is 25 in fact", notice=notices(state)[0]["id"])
    assert [each["text"] for each in step_of(state, "c1")["unconfirmed"]] == [ASSUMED]


def test_a_corrected_assumption_used_again_counts_as_unconfirmed(open_session):
    session, state = total_with_assumption(open_session, reply("Noted."), run("total", {"a": 10, "b": 20}, [ASSUMED]),
                                           reply("30 again."))
    say(session, "B is 25 in fact", notice=notices(state)[0]["id"])
    state = say(session, "Run it again with B at 20")
    assert [m["notice"]["status"] for m in notices(state)] == ["changed", "open"]
    assert [each["text"] for each in step_of(state, "c1")["unconfirmed"]] == [ASSUMED]


def test_a_message_that_points_at_no_notice_is_an_ordinary_message(open_session):
    session = open_session([reply("Hello")])
    state = say(session, "Hello", notice="m999")
    assert [m["text"] for m in assistant(state)] == ["Hello"]
    assert not events(session, "you.assumptions_corrected")


def test_the_analyst_is_told_each_assumption_with_its_status_and_words(open_session):
    session, state = total_with_assumption(open_session, reply("Noted."), reply("Fine."))
    say(session, "B is 25 in fact", notice=notices(state)[0]["id"])
    say(session, "Anything else?")
    known = session.script.calls[-1]["system"].split("## What you know")[1]
    assert "[assumptions]" in known and ASSUMED in known and '"corrected"' in known and "B is 25 in fact" in known
