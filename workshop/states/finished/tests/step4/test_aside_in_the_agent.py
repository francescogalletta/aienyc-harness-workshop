"""SPEC 8.5 and 8.6: side conversations inside `run_agent`: at every kind of question, the order of model calls, what
crosses back, and what is recorded."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ASIDE_CARRIED, ASIDE_CARRY, ASIDE_CLOSE, ASIDE_OPEN, DECISION_QUESTION,
                           DECISION_QUESTION_SUGGESTED, GATE_QUESTION, h, marked, side)

OK = "Done."
A_THING = "A thing."
TO_ASIDE = ["/aside what does this mean?", "/back", "no"]            # opens one, goes back, carries nothing
GATE = s4.gate_block(s4.surplus_item())
SURPLUS_PLAN = ("To work this out: surplus = income - spending\nI will need from you:\n"
                "  - income (a number): Money in each month.\n  - spending (a number): Money out each month.\n"
                "It gives back: The surplus per month.")
EXAMPLES = [
    "Example 1 of 3\n  income: 5123.45\n  spending: 3100.10\n  Working: 5123.45 less 3100.10 leaves 2023.35\n"
    "  Proposed answer: 2023.35",
    "Example 2 of 3\n  income: 4000\n  spending: 4500\n  Working: 4000 less 4500 is a shortfall of 500\n"
    "  Proposed answer: -500",
    "Example 3 of 3\n  income: 3000\n  spending: 3000\n  Working: 3000 less 3000 leaves 0\n  Proposed answer: 0"]
STEP_HEADER = "Step s1: Work out the monthly surplus"


def events_of(conn, kind):
    return [payload for _, _, payload in h.events(conn, kind)]


def asks(person):
    return s4.asked_of(person)


def opened(conn):
    return events_of(conn, "aside.opened")


def agent_text(model):
    """Every message the agent's model was given, in one string (its system prompt tells about /aside)."""
    return json.dumps([c["messages"] for c in model.of("analyst")], default=str)


def sandwiched(person, question):
    """The asks of a question that was put twice, around one side conversation of one turn."""
    texts = asks(person)
    first = texts.index(question)
    return texts[first:first + 4]


# ---- the examples of 8.6 -----------------------------------------------------------------------------------------------

def test_an_aside_at_a_gate_then_yes_is_three_calls_and_the_carried_text_comes_last(ask_agent, conn):
    script = [s4.run(), side("Steady means it does not change."), h.say_text(OK)]
    answers = ["/aside What does steady mean?", "/back", "Rent is 1,100 now.", "yes", "/quit"]
    model, person = ask_agent(script, answers)
    assert model.roles() == ["analyst", "aside", "analyst"]
    messages = model.calls[2]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "user"]
    assert messages[2]["content"].startswith("{") and json.loads(messages[2]["content"])["output"] == "2000"
    assert messages[3] == {"role": "user", "content": ASIDE_CARRIED.format(text="Rent is 1,100 now.")}
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION]


def test_what_the_person_sees_around_the_aside_at_a_gate(ask_agent):
    script = [s4.run(), side("Steady means it does not change."), h.say_text(OK)]
    _, person = ask_agent(script, ["/aside What does steady mean?", "/back", "no", "yes", "/quit"])
    log = s4.quiet(person)
    k = log.index(("say", GATE))
    assert log[k:k + 11] == [
        ("say", GATE), ("ask", GATE_QUESTION), ("say", ASIDE_OPEN), ("say", marked("(thinking)")), ("call", "aside"),
        ("ask", marked("Steady means it does not change.")), ("ask", marked(ASIDE_CARRY)), ("say", ASIDE_CLOSE),
        ("say", GATE), ("ask", GATE_QUESTION), ("say", "  (running monthly_surplus)")]


def test_an_aside_with_one_lookup_is_four_calls(ask_agent, conn):
    desk, researcher = s4.make_desk(conn)
    script = [s4.run(), s4.look_up("sinking fund"), side("It is money set aside."), h.say_text(OK)]
    model, _ = ask_agent(script, ["/aside What is a sinking fund?", "/back", "no", "yes", "/quit"], desk=desk)
    assert model.roles() == ["analyst", "aside", "aside", "analyst"]
    assert researcher.queries == ["sinking fund"]


def test_an_aside_at_the_opening_question_is_the_side_call_and_then_the_agents(talk, conn):
    script = [side(A_THING), h.say_text("Hello.")]
    model, person = talk(script, ["/aside What is a sinking fund?", "/back", "no", h.QUESTION, "/quit"], question="")
    assert model.roles() == ["aside", "analyst"]
    assert asks(person) == [h.OPENING, marked(A_THING), marked(ASIDE_CARRY), h.OPENING, "Hello."]
    assert ("say", h.OPENING) not in person.log
    assert opened(conn) == [{"aside": 1, "first": "What is a sinking fund?", "looking_at": None}]
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION]
    assert model.calls[1]["messages"] == [{"role": "user", "content": h.QUESTION}]


def test_nothing_is_shown_again_after_an_aside_at_the_opening_question(talk):
    _, person = talk([side(A_THING), h.say_text("Hello.")], ["/aside what?", "/back", "no", h.QUESTION, "/quit"], question="")
    log = s4.quiet(person)
    close = log.index(("say", ASIDE_CLOSE))
    assert log[close + 1] == ("ask", h.OPENING)


def test_a_text_carried_at_the_opening_question_comes_after_the_first_message(talk, conn):
    script = [side(A_THING), h.say_text("Hello.")]
    model, _ = talk(script, ["/aside what?", "/back", "My rent is 1,150.", h.QUESTION, "/quit"], question="")
    assert model.calls[1]["messages"] == [{"role": "user", "content": h.QUESTION},
                                          {"role": "user", "content": ASIDE_CARRIED.format(text="My rent is 1,150.")}]


# ---- at every question ----------------------------------------------------------------------------------------------------------

def test_at_an_ordinary_reply_the_reply_is_asked_again_and_nothing_is_looked_at(talk, conn):
    model, person = talk([h.say_text("Here is what I found."), side(A_THING)], [*TO_ASIDE, "/quit"], question=h.QUESTION)
    assert asks(person) == ["Here is what I found.", marked(A_THING), marked(ASIDE_CARRY), "Here is what I found."]
    assert opened(conn)[0]["looking_at"] is None and len(model.of("analyst")) == 1
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION]


def test_the_aside_is_not_a_message_and_the_agent_never_hears_of_it(talk, conn):
    model, _ = talk([h.say_text("Here."), side(A_THING), h.say_text("Again.")], ["/aside what is that?", "/back", "no", "More", "/quit"])
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION, "More"]
    assert "/aside" not in agent_text(model) and "what is that" not in agent_text(model) and A_THING not in agent_text(model)


def test_at_a_withheld_reply(talk, conn):
    script = [h.say_text("You will have 8,888."), h.say_text("Really 8,888."), side(A_THING)]
    _, person = talk(script, [*TO_ASIDE, "/quit"])
    question = h.WITHHELD.format(numbers="8,888")
    assert sandwiched(person, question) == [question, marked(A_THING), marked(ASIDE_CARRY), question]
    assert opened(conn)[0]["looking_at"] is None


def test_at_the_too_many_steps_question(talk, conn):
    script = [h.save_input(f"item{n}", "5000", "n") for n in range(1, 11)] + [side(A_THING)]
    _, person = talk(script, [*TO_ASIDE, "/quit"])
    assert sandwiched(person, h.TOO_MANY) == [h.TOO_MANY, marked(A_THING), marked(ASIDE_CARRY), h.TOO_MANY]
    assert h.events(conn, "ask.stopped") != []


def test_at_a_gate_the_gate_block_is_what_the_person_was_looking_at(ask_agent, conn):
    _, person = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    assert opened(conn)[0]["looking_at"] == GATE
    assert sandwiched(person, GATE_QUESTION) == [GATE_QUESTION, marked(A_THING), marked(ASIDE_CARRY), GATE_QUESTION]


def test_at_a_decision_the_decision_block_is_what_the_person_was_looking_at(ask_agent, conn):
    block = s4.decision_block("Should the date stay or move?", ["Keep the date", "Move the date"])
    _, person = ask_agent([s4.ask_decision(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "2", "/quit"])
    assert opened(conn)[0]["looking_at"] == block
    assert sandwiched(person, DECISION_QUESTION) == [DECISION_QUESTION, marked(A_THING), marked(ASIDE_CARRY), DECISION_QUESTION]
    assert person.log.count(("say", block)) == 2


def test_at_a_decision_with_a_suggestion(ask_agent, conn):
    script = [s4.ask_decision(recommendation=1, why="Simplest."), side(A_THING), h.say_text(OK)]
    _, person = ask_agent(script, [*TO_ASIDE, "yes", "/quit"])
    assert sandwiched(person, DECISION_QUESTION_SUGGESTED)[0] == DECISION_QUESTION_SUGGESTED
    assert s4.decision_rows(conn)[0]["choice"] == "1"


def test_after_the_aside_the_block_is_shown_again_and_then_the_question(ask_agent):
    block = s4.decision_block("Should the date stay or move?", ["Keep the date", "Move the date"])
    _, person = ask_agent([s4.ask_decision(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "2", "/quit"])
    log = s4.quiet(person)
    close = log.index(("say", ASIDE_CLOSE))
    assert log[close + 1:close + 3] == [("say", block), ("ask", DECISION_QUESTION)]


def test_at_the_question_of_a_request_the_request_block_is_what_was_looked_at(talk, months_only, conn):
    script = [h.request_module("step", "s1"), side(A_THING), h.say_text("Understood.")]
    model, person = talk(script, [*TO_ASIDE, "no", "/quit"])
    assert model.roles() == ["analyst", "aside", "analyst"]
    assert opened(conn)[0]["looking_at"] == h.STEP_BLOCK
    assert sandwiched(person, h.REQUEST_QUESTION) == [h.REQUEST_QUESTION, marked(A_THING), marked(ASIDE_CARRY), h.REQUEST_QUESTION]
    assert s4.decision_rows(conn)[0]["words"] == "no" and s4.decision_rows(conn)[0]["kind"] == "build"


def build_script():
    return [h.request_module("step", "s1"), h.propose_spec(), h.propose_examples(), h.write_module(), h.say_text("Built.")]


def test_at_the_plan_check_of_a_build_the_header_and_the_plan_are_what_was_looked_at(talk, months_only, conn):
    script = [h.request_module("step", "s1"), h.propose_spec(), side(A_THING), h.propose_examples(), h.write_module(),
              h.say_text("Built.")]
    answers = ["yes", *TO_ASIDE, "yes", *h.accepts(3), "/quit"]
    model, person = talk(script, answers)
    assert model.roles() == ["analyst", "spec_writer", "aside", "example_writer", "module_writer", "analyst"]
    assert opened(conn)[0]["looking_at"] == STEP_HEADER + "\n" + SURPLUS_PLAN
    assert sandwiched(person, h.PLAN_QUESTION) == [h.PLAN_QUESTION, marked(A_THING), marked(ASIDE_CARRY), h.PLAN_QUESTION]


def test_the_events_of_the_aside_are_among_the_events_of_the_build(talk, months_only, conn):
    script = [h.request_module("step", "s1"), h.propose_spec(), side(A_THING), h.propose_examples(), h.write_module(),
              h.say_text("Built.")]
    talk(script, ["yes", *TO_ASIDE, "yes", *h.accepts(3), "/quit"])
    kinds = s4.conversation_kinds(conn)
    start = kinds.index("calc.spec_proposed")
    assert kinds[start:start + 8] == ["calc.spec_proposed", "aside.opened", "aside.message", "aside.reply", "aside.closed",
                                      "calc.plan_decision", "calc.examples_proposed", "calc.golden_decision"]


def test_at_an_example_of_a_build_the_example_block_is_what_was_looked_at(talk, months_only, conn):
    script = [h.request_module("step", "s1"), h.propose_spec(), h.propose_examples(), side(A_THING), h.write_module(),
              h.say_text("Built.")]
    answers = ["yes", "yes", "/accept", *TO_ASIDE, "/accept", "/accept", "/quit"]
    model, person = talk(script, answers)
    assert opened(conn)[0]["looking_at"] == EXAMPLES[1]
    assert sandwiched(person, h.CONFIRM_EXAMPLE)[:1] == [h.CONFIRM_EXAMPLE] and asks(person).count(h.CONFIRM_EXAMPLE) == 4
    assert model.roles() == ["analyst", "spec_writer", "example_writer", "aside", "module_writer", "analyst"]


def test_an_aside_in_a_build_does_not_change_what_the_build_does(talk, months_only, conn, registry):
    script = [h.request_module("step", "s1"), h.propose_spec(), side(A_THING), h.propose_examples(), h.write_module(),
              h.say_text("Built.")]
    model, _ = talk(script, ["yes", "/aside what?", "/back", "no", "yes", *h.accepts(3), "/quit"])
    assert registry.step_map(conn)["s1"] == "monthly_surplus"
    assert len(h.events(conn, "calc.golden_decision")) == 3 and h.events(conn, "ask.module_decision")[0][2]["decision"] == "accepted"


# ---- /quit -------------------------------------------------------------------------------------------------------------------------

def test_quit_in_an_aside_at_an_ordinary_question_ends_the_conversation(talk, conn):
    model, person = talk([h.say_text("Hello."), side(A_THING)], ["/aside what?", "/quit"])
    assert asks(person) == ["Hello.", marked(A_THING)] and len(model.of("analyst")) == 1
    assert events_of(conn, "aside.closed") == [{"aside": 1, "turns": 1, "how": "quit", "carried": None}]


def test_quit_in_an_aside_at_a_gate_is_a_no_with_the_words_quit(ask_agent, conn):
    model, person = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], ["/aside what?", "/quit", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"]) == {"outcome": "not_run", "said": "/quit"}
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["choice"], row["words"]) == ("assumptions", "no", "/quit")
    assert h.rows(conn, "calc_runs") == [] and asks(person)[-1] == OK


def test_quit_in_an_aside_at_a_decision_is_something_else_with_the_words_quit(ask_agent, conn):
    model, _ = ask_agent([s4.ask_decision(), side(A_THING), h.say_text(OK)], ["/aside what?", "/quit", "/quit"])
    result = json.loads(h.tool_message(model, 2)["content"])
    assert result["choice"] == "something else" and result["said"] == "/quit" and result["option"] is None
    assert s4.decision_rows(conn)[0]["words"] == "/quit"


def test_quit_in_an_aside_at_a_request_declines_it(talk, months_only, conn):
    model, _ = talk([h.request_module("step", "s1"), side(A_THING), h.say_text("Understood.")], ["/aside what?", "/quit", "/quit"])
    assert h.events(conn, "ask.module_decision")[0][2] == {"decision": "declined", "text": "/quit"}
    assert s4.decision_rows(conn)[0]["words"] == "/quit"


def test_quit_in_an_aside_at_the_opening_question_ends_the_session(talk, conn):
    model, person = talk([side(A_THING)], ["/aside what?", "/quit"], question="")
    assert model.roles() == ["aside"] and asks(person) == [h.OPENING, marked(A_THING)]
    assert h.events(conn, "ask.message") == []


def test_quit_at_the_carry_question_is_a_quit_of_the_open_question(ask_agent, conn):
    model, person = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], ["/aside what?", "/back", "/quit", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"]) == {"outcome": "not_run", "said": "/quit"}
    assert events_of(conn, "aside.closed")[0]["how"] == "quit"


# ---- what crosses back ---------------------------------------------------------------------------------------------------------------

def test_a_text_carried_at_a_decision_is_the_last_message_of_the_next_agent_call(ask_agent):
    script = [s4.ask_decision(), side(A_THING), h.say_text(OK)]
    model, _ = ask_agent(script, ["/aside what?", "/back", "Rent is 1,100 now.", "2", "/quit"])
    messages = model.calls[2]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "user"]
    assert messages[3]["content"] == ASIDE_CARRIED.format(text="Rent is 1,100 now.")


def test_a_text_carried_at_an_ordinary_reply_comes_after_the_next_message(talk, conn):
    script = [h.say_text("Hello."), side(A_THING), h.say_text("Right.")]
    model, _ = talk(script, ["/aside what?", "/back", "Rent is 1,100 now.", "Next question", "/quit"])
    assert [m["content"] for m in model.calls[2]["messages"] if m["role"] == "user"] == [
        h.QUESTION, "Next question", ASIDE_CARRIED.format(text="Rent is 1,100 now.")]
    assert [m["role"] for m in model.calls[2]["messages"]][-2:] == ["user", "user"]


def test_two_carried_texts_arrive_oldest_first_as_one_message_each(ask_agent):
    script = [s4.run(), side("One."), side("Two."), h.say_text(OK)]
    answers = ["/aside one", "/back", "First thing.", "/aside two", "/back", "Second thing.", "yes", "/quit"]
    model, _ = ask_agent(script, answers)
    assert [m["content"] for m in model.calls[3]["messages"][-2:]] == [
        ASIDE_CARRIED.format(text="First thing."), ASIDE_CARRIED.format(text="Second thing.")]


def test_a_carried_text_is_given_once(talk):
    script = [h.say_text("Hello."), side(A_THING), h.say_text("Right."), h.say_text("Fine.")]
    model, _ = talk(script, ["/aside what?", "/back", "Rent is 1,100 now.", "Next", "Again", "/quit"])
    carried = ASIDE_CARRIED.format(text="Rent is 1,100 now.")
    assert [m["content"] for m in model.calls[3]["messages"]].count(carried) == 1
    assert model.calls[3]["messages"][-1] == {"role": "user", "content": "Again"}


def test_nothing_carried_adds_no_message(ask_agent):
    model, _ = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    assert [m["role"] for m in model.calls[2]["messages"]] == ["user", "assistant", "tool"]


def test_a_text_that_was_carried_but_never_given_stays_in_the_event(talk, conn):
    model, _ = talk([h.say_text("Hello."), side(A_THING)], ["/aside what?", "/back", "Rent is 1,100 now.", "/quit"])
    assert len(model.of("analyst")) == 1
    assert events_of(conn, "aside.closed")[0]["carried"] == "Rent is 1,100 now."
    assert "Rent is 1,100 now." not in agent_text(model)


def test_the_replies_of_the_side_assistant_never_reach_the_agent(ask_agent):
    script = [s4.run(), side("A very particular side reply."), h.say_text(OK)]
    model, _ = ask_agent(script, ["/aside what?", "/back", "Only this.", "yes", "/quit"])
    assert "A very particular side reply." not in agent_text(model) and "what?" not in agent_text(model)


def test_the_carried_text_is_a_source_for_the_agents_number_check(ask_agent, conn):
    script = [s4.run(), side(A_THING), h.say_text("Your rent is 1,100 now.")]
    _, person = ask_agent(script, ["/aside what?", "/back", "Rent is 1,100 now.", "yes", "/quit"])
    assert asks(person)[-1] == "Your rent is 1,100 now." and h.events(conn, "ask.correction") == []


def test_without_the_carried_text_that_number_is_not_backed(ask_agent, conn):
    script = [s4.run(), side(A_THING), h.say_text("Your rent is 1,100 now."), h.say_text("I cannot say.")]
    _, person = ask_agent(script, [*TO_ASIDE, "yes", "/quit"])
    assert "Your rent is 1,100 now." not in asks(person) and len(h.events(conn, "ask.correction")) == 1


def test_the_carried_text_backs_a_later_decision_block(ask_agent, conn):
    script = [s4.run(), side(A_THING), s4.ask_decision(question="Keep rent at 1,100?"), h.say_text(OK)]
    model, _ = ask_agent(script, ["/aside what?", "/back", "Rent is 1,100 now.", "yes", "1", "/quit"])
    assert json.loads(h.tool_message(model, 3)["content"])["outcome"] == "decided"


def test_a_carried_text_is_not_a_person_message_and_does_not_start_the_counts_again(ask_agent, conn):
    script = [s4.ask_decision(question="First?"), s4.ask_decision(question="Second?"), side(A_THING),
              s4.ask_decision(question="Third?"), h.say_text(OK)]
    answers = ["1", "/aside what?", "/back", "Rent is 1,100 now.", "1", "/quit"]
    model, _ = ask_agent(script, answers)
    assert model.roles() == ["analyst", "analyst", "aside", "analyst", "analyst"]
    assert h.tool_message(model, 4)["content"] == s4.TOO_MANY_DECISIONS
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION]


def test_side_calls_do_not_count_towards_the_agents_ten(talk, conn):
    script = [h.save_input(f"item{n}", "5000", "n") for n in range(1, 10)] + [h.say_text("Last one."), side(A_THING),
                                                                              h.say_text("After.")]
    model, person = talk(script, ["/aside what?", "/back", "no", "More", "/quit"])
    assert h.events(conn, "ask.stopped") == [] and asks(person)[-1] == "After."


# ---- numbering and events ------------------------------------------------------------------------------------------------------------

def test_the_side_conversations_of_a_session_are_numbered_in_order(ask_agent, conn):
    script = [s4.run(), side("One."), side("Two."), h.say_text(OK)]
    ask_agent(script, ["/aside one", "/back", "no", "/aside two", "/back", "no", "yes", "/quit"])
    assert [o["aside"] for o in opened(conn)] == [1, 2]
    assert [o["first"] for o in opened(conn)] == ["one", "two"]


def test_two_asides_at_one_question_have_the_same_looking_at(ask_agent, conn):
    script = [s4.run(), side("One."), side("Two."), h.say_text(OK)]
    ask_agent(script, ["/aside one", "/back", "no", "/aside two", "/back", "no", "yes", "/quit"])
    assert [o["looking_at"] for o in opened(conn)] == [GATE, GATE]
    assert len(h.events(conn, "ask.gate")) == 1


def test_the_events_of_a_gate_with_an_aside_in_order(ask_agent, conn):
    script = [s4.run(), side(A_THING), h.say_text(OK)]
    ask_agent(script, [*TO_ASIDE, "yes", "/quit"])
    kinds = s4.conversation_kinds(conn)
    assert kinds[:7] == ["ask.message", "ask.gate", "aside.opened", "aside.message", "aside.reply", "aside.closed",
                         "ask.decision"]
    assert kinds.index("calc.run") > kinds.index("ask.decision") and kinds.index("ask.reply") > kinds.index("calc.run")


def test_the_events_of_a_decision_with_an_aside_in_order(ask_agent, conn):
    script = [s4.ask_decision(), side(A_THING), h.say_text(OK)]
    ask_agent(script, [*TO_ASIDE, "1", "/quit"])
    kinds = s4.conversation_kinds(conn)
    assert kinds[:7] == ["ask.message", "ask.decision_asked", "aside.opened", "aside.message", "aside.reply", "aside.closed",
                         "ask.decision"]


def test_the_events_of_a_request_with_an_aside_in_order(talk, months_only, conn):
    talk([h.request_module("step", "s1"), side(A_THING), h.say_text("Understood.")], [*TO_ASIDE, "no", "/quit"])
    kinds = s4.conversation_kinds(conn)
    assert kinds[:8] == ["ask.message", "ask.module_requested", "aside.opened", "aside.message", "aside.reply",
                         "aside.closed", "ask.module_decision", "ask.module_outcome"]


def test_every_aside_event_carries_the_session_and_its_number(ask_agent, conn):
    ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    rows = list(conn.execute("SELECT session_id, payload FROM events WHERE kind LIKE 'aside.%'"))
    assert rows and {r["session_id"] for r in rows} == {h.SESSION}
    assert {json.loads(r["payload"])["aside"] for r in rows} == {1}


def test_an_aside_writes_nothing_but_events(ask_agent, conn):
    ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    assert len(s4.decision_rows(conn)) == 1 and len(h.rows(conn, "calc_runs")) == 1
    assert h.rows(conn, "inputs") == [] and h.rows(conn, "notes") == []


def test_the_aside_gate_answer_is_not_the_answer_to_the_gate(ask_agent, conn):
    """The side conversation leaves the main conversation as it was: the gate still waits for its own answer."""
    ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["choice"], row["words"]) == ("assumptions", "yes", "yes")


def test_the_side_assistant_context_has_the_runs_and_decisions_so_far(ask_agent, conn, brief):
    script = [s4.run(assumptions=[]), s4.ask_decision(step="s2", runs=[1]), side(A_THING), h.say_text(OK)]
    model, _ = ask_agent(script, ["1", "/aside why?", "/back", "no", "/quit"])
    call = model.of("aside")[0]
    context = s4.aside_context(
        brief, runs=[{"run": 1, "module": "monthly_surplus", "inputs": {"income": "5000", "spending": "3000"}, "output": "2000"}],
        decisions=[{key: s4.decisions_of(conn)[0][key] for key in ["id", "kind", "step", "question", "options", "choice",
                                                                    "words", "runs"]}])
    assert call["system"].strip() == s4.aside_system(context).strip()


def test_the_aside_prompt_is_not_the_analysts(ask_agent):
    model, _ = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    assert model.of("aside")[0]["system"] != model.of("analyst")[0]["system"]
    assert s4.role_of(model.of("aside")[0]["system"]) == "aside"
