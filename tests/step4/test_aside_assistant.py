"""SPEC 8.5: the side assistant: its context and prompt, its one tool, its number check and its limits."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ASIDE_LOOKING_UP, ASIDE_LOOKUP_LIMIT, ASIDE_NUMBERS, ASIDE_THINKING, LOOKUP_FAILED, LOOKUP_TERM,
                           MAX_ASIDE_CALLS, MAX_ASIDE_LOOKUPS, MAX_QUERY_LENGTH, h, look_up, look_ups, marked, side)

THINK = ("say", marked(ASIDE_THINKING))
CALL = ("call", "aside")
LOOK_UP_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


def events_of(conn, kind):
    return [payload for _, _, payload in h.events(conn, kind)]


def tool_results(model, call_index):
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


def go_back(extra=()):
    return [*extra, "/back", "no"]


# ---- the context ----------------------------------------------------------------------------------------------------------------

def test_the_context_of_a_side_conversation_with_nothing_yet(aside, conn, brief, installed):
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    assert context == s4.aside_context(brief)


def test_the_context_holds_what_the_person_was_looking_at(aside, conn, brief, installed):
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at="The block\nof two lines")
    assert context == s4.aside_context(brief, looking_at="The block\nof two lines")
    assert context.endswith("[looking at]\nThe block\nof two lines")


def test_looking_at_is_null_when_there_was_nothing(aside, conn, brief, installed):
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    assert context.endswith("[looking at]\nnull")


def test_the_nine_sections_in_order(aside, conn, brief, installed):
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today="2031-02-03", looking_at=None)
    titles = [line for line in context.split("\n") if line.startswith("[") and line.endswith("]") and not line.startswith("[ ")]
    top = [t for t in titles if t in ("[today]", "[goal]", "[glossary]", "[particulars]", "[process]", "[plans]",
                                      "[runs in this conversation]", "[decisions in this conversation]", "[looking at]")]
    assert top == ["[today]", "[goal]", "[glossary]", "[particulars]", "[process]", "[plans]",
                   "[runs in this conversation]", "[decisions in this conversation]", "[looking at]"]
    assert context.startswith("[today]\n2031-02-03\n\n[goal]\n" + brief["goal"])


def test_the_plans_are_those_of_the_registered_modules_by_name_with_labelled_steps(aside, conn, brief, installed):
    h.install_yearly(conn, "added_1")
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    plans = {**s4.PLANS, "yearly_cost": {"steps": ["added_1 (not in the brief)"], "plan": s4.s3.plan_text(h.yearly_spec())}}
    assert context == s4.aside_context(brief, plans=plans)


def test_with_no_modules_the_plans_are_empty(aside, conn, brief):
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    assert context == s4.aside_context(brief, plans={})


def test_the_runs_and_decisions_of_this_conversation_are_in_the_context(aside, ask_agent, conn, brief):
    script = [s4.run(assumptions=[]), s4.ask_decision(step="s2", runs=[1]), h.say_text("Done.")]
    ask_agent(script, ["Neither", "/quit"])
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    [decision] = s4.decisions_of(conn)
    kept = {key: decision[key] for key in ["id", "kind", "step", "question", "options", "choice", "words", "runs"]}
    assert context == s4.aside_context(
        brief, runs=[{"run": 1, "module": "monthly_surplus", "inputs": {"income": "5000", "spending": "3000"},
                      "output": "2000"}], decisions=[kept])
    assert "\"ts\"" not in context and "session_id" not in context


def test_the_runs_and_decisions_of_other_sessions_are_left_out(aside, agent, conn, brief, installed):
    person = h.Person("Neither", "/quit")
    model = s4.Model([s4.run(assumptions=[]), s4.ask_decision(), h.say_text("Done.")], person)
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="another-chat",
                    question=h.QUESTION, today=h.DAY)
    context = aside.aside_context(conn, brief, session_id="this-chat", today=s4.TODAY, looking_at=None)
    assert context == s4.aside_context(brief)


def test_the_context_never_holds_the_saved_inputs_the_notes_or_the_main_messages(aside, ask_agent, notes, conn, brief):
    notes.add_note(conn, step_id="s1", text="A private note about 7,654.", session_id="earlier")
    script = [h.save_input("buffer", "9,876", "said"), h.say_text("Saved it, here is a long reply about nothing."),
              h.say_text("More about the nothing.")]
    ask_agent(script, ["Tell me more about the nothing", "/quit"], question="My buffer is 9,876. Save it.")
    context = aside.aside_context(conn, brief, session_id=h.SESSION, today=s4.TODAY, looking_at=None)
    for text in ("9,876", "7,654", "private note", "Tell me more", "long reply", "buffer"):
        assert text not in context
    assert context == s4.aside_context(brief)


# ---- the call to the model ----------------------------------------------------------------------------------------------------

def test_the_system_prompt_is_aside_md_with_the_context(one_aside, conn, brief, installed):
    _, _, model = one_aside([side("Fine.")], go_back(), first="What is it?", looking_at="The block")
    call = model.calls[0]
    context = s4.aside_context(brief, looking_at="The block")
    assert call["system"].strip() == s4.aside_system(context).strip()
    assert "{context}" not in call["system"]


def test_the_side_assistant_has_its_own_prompt(one_aside, installed):
    _, _, model = one_aside([side("Fine.")], go_back(), first="What is it?")
    assert model.calls[0]["system"].strip() != h.prompt_text("analyst.md").strip()
    assert s4.role_of(model.calls[0]["system"]) == "aside"


def test_the_one_tool_is_look_up(one_aside):
    _, _, model = one_aside([side("Fine.")], go_back(), first="What is it?")
    [tool] = model.calls[0]["tools"]
    assert tool.name == "look_up" and h.without_descriptions(tool.input_schema) == LOOK_UP_SCHEMA


def test_the_context_is_made_once_when_it_opens(one_aside, conn, brief, installed):
    _, _, model = one_aside([side("One."), side("Two.")], go_back(["Second."]), first="First.")
    assert model.calls[0]["system"] == model.calls[1]["system"]


# ---- lookups --------------------------------------------------------------------------------------------------------------------

def test_a_lookup_goes_through_the_desk_and_the_result_is_given_back(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    outcome, person, model = one_aside([look_up("sinking fund"), side("It is money set aside.")], go_back(),
                                       first="What is a sinking fund?", desk=desk)
    assert person.log == [("say", s4.ASIDE_OPEN), THINK, CALL, ("say", marked(ASIDE_LOOKING_UP.format(query="sinking fund"))),
                          THINK, CALL, ("ask", marked("It is money set aside.")), ("ask", marked(s4.ASIDE_CARRY)),
                          ("say", s4.ASIDE_CLOSE)]
    [(_, actor, payload)] = h.events(conn, "aside.lookup")
    assert actor == "agent" and payload["aside"] == 1 and payload["query"] == "sinking fund" and payload["found"] is True
    assert set(payload) == {"aside", "query", "found", "name", "definition", "sources", "origin"}
    assert payload["definition"] == "Money set aside regularly for a known future cost." and payload["origin"] == "fake"
    assert payload["sources"] == [{"title": "A page about sinking fund", "url": "https://example.org/sinking-fund"}]
    [result] = tool_results(model, 1)
    assert not result.get("is_error")
    assert json.loads(result["content"]) == {key: value for key, value in payload.items() if key != "aside"}
    assert researcher.queries == ["sinking fund"]


def test_the_assistant_message_and_the_results_are_added_together(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    _, _, model = one_aside([look_ups("sinking fund", "emergency fund"), side("Both are savings.")], go_back(),
                            first="What are they?", desk=desk)
    roles = [m["role"] for m in model.calls[1]["messages"]]
    assert roles == ["user", "assistant", "tool", "tool"]
    first, second = tool_results(model, 1)
    assert json.loads(first["content"])["query"] == "sinking fund" and json.loads(second["content"])["query"] == "emergency fund"


def test_the_calls_of_one_reply_are_handled_in_order_each_with_its_line(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    _, person, _ = one_aside([look_ups("emergency fund", "sinking fund"), side("Both.")], go_back(), first="Q", desk=desk)
    lines = [text for kind, text in person.log if kind == "say" and "looking up" in text]
    assert lines == [marked(ASIDE_LOOKING_UP.format(query="emergency fund")), marked(ASIDE_LOOKING_UP.format(query="sinking fund"))]
    assert researcher.queries == ["emergency fund", "sinking fund"]


def test_the_query_is_stripped_and_only_the_query_reaches_the_researcher(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    one_aside([look_up("  sinking fund \n"), side("Fine.")], go_back(), first="My wedding costs 20,000, what is a sinking fund?",
              desk=desk)
    assert researcher.queries == ["sinking fund"]
    assert events_of(conn, "aside.lookup")[0]["query"] == "sinking fund"


def test_a_term_nobody_knows_is_not_an_error_and_is_recorded_as_not_found(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    _, _, model = one_aside([look_up("quantum budgeting"), side("I could not find it.")], go_back(), first="Q", desk=desk)
    [result] = tool_results(model, 1)
    assert not result.get("is_error") and json.loads(result["content"])["found"] is False
    assert events_of(conn, "aside.lookup")[0]["found"] is False


def test_a_failed_lookup_is_an_error_result_and_records_the_error(one_aside, conn):
    desk, researcher = s4.make_desk(conn, s4.FakeResearcher(failing=["sinking fund"]))
    _, _, model = one_aside([look_up("sinking fund"), side("It failed.")], go_back(), first="Q", desk=desk)
    [event] = events_of(conn, "aside.lookup")
    assert set(event) == {"aside", "query", "error"}
    assert event["aside"] == 1 and event["query"] == "sinking fund" and "the researcher is down" in event["error"]
    [result] = tool_results(model, 1)
    assert result["is_error"] is True and result["content"] == LOOKUP_FAILED.format(error=event["error"])


@pytest.mark.parametrize("arguments", [{"query": ""}, {"query": "   "}, {}, {"query": "x" * (MAX_QUERY_LENGTH + 1)},
                                       {"query": " " + "x" * (MAX_QUERY_LENGTH + 1)}])
def test_an_empty_or_too_long_term_is_an_error_that_is_not_recorded(one_aside, conn, arguments):
    desk, researcher = s4.make_desk(conn)
    reply = {"tool_calls": [{"name": "look_up", "arguments": arguments}]}
    _, person, model = one_aside([reply, side("Fine.")], go_back(), first="Q", desk=desk)
    [result] = tool_results(model, 1)
    assert result["is_error"] is True and result["content"] == LOOKUP_TERM.format(limit=MAX_QUERY_LENGTH)
    assert h.events(conn, "aside.lookup") == [] and researcher.queries == []
    assert not [1 for kind, text in person.log if kind == "say" and "looking up" in text]


def test_a_term_of_exactly_the_longest_length_is_looked_up(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    one_aside([look_up("x" * MAX_QUERY_LENGTH), side("Fine.")], go_back(), first="Q", desk=desk)
    assert researcher.queries == ["x" * MAX_QUERY_LENGTH]


def test_three_lookups_are_allowed_and_the_fourth_is_an_error_that_is_not_recorded(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    script = [look_ups("a", "b", "c", "d"), side("Enough.")]
    _, person, model = one_aside(script, go_back(), first="Q", desk=desk)
    results = tool_results(model, 1)
    assert [bool(r.get("is_error")) for r in results] == [False, False, False, True]
    assert results[3]["content"] == ASIDE_LOOKUP_LIMIT
    assert researcher.queries == ["a", "b", "c"] and len(h.events(conn, "aside.lookup")) == 3
    lines = [text for kind, text in person.log if kind == "say" and "looking up" in text]
    assert len(lines) == 3 and MAX_ASIDE_LOOKUPS == 3


def test_the_limit_is_for_the_whole_side_conversation_not_for_a_turn(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    script = [look_ups("a", "b"), side("One."), look_ups("c", "d"), side("Two.")]
    _, _, model = one_aside(script, go_back(["Again."]), first="Q", desk=desk)
    results = tool_results(model, 3)[-2:]
    assert [bool(r.get("is_error")) for r in results] == [False, True]
    assert researcher.queries == ["a", "b", "c"]


def test_a_new_side_conversation_has_three_lookups_of_its_own(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    one_aside([look_ups("a", "b", "c"), side("One.")], go_back(), first="Q", desk=desk)
    _, _, model = one_aside([look_ups("d", "e", "f"), side("Two.")], go_back(), first="Q", desk=desk, aside_number=2)
    assert not any(r.get("is_error") for r in tool_results(model, 1))
    assert researcher.queries == ["a", "b", "c", "d", "e", "f"]


def test_a_bad_term_is_checked_before_the_limit(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    _, _, model = one_aside([look_ups("a", "b", "c", ""), side("Fine.")], go_back(), first="Q", desk=desk)
    assert tool_results(model, 1)[3]["content"] == LOOKUP_TERM.format(limit=MAX_QUERY_LENGTH)


def test_a_bad_term_does_not_count_as_a_lookup(one_aside, conn):
    desk, researcher = s4.make_desk(conn)
    _, _, model = one_aside([look_ups("", "x" * 101, "a", "b", "c"), side("Fine.")], go_back(), first="Q", desk=desk)
    assert [bool(r.get("is_error")) for r in tool_results(model, 1)] == [True, True, False, False, False]


@pytest.mark.parametrize("name, arguments", [
    ("run_module", {"module": "monthly_surplus", "inputs": {"income": "5000", "spending": "3000"}, "assumptions": [],
                    "expected": "2000"}),
    ("save_input", {"name": "buffer", "value": "5000", "note": "n"}),
    ("request_module", h.request_arguments("new")),
    ("ask_decision", s4.ask_decision_arguments()),
    ("write_brief", {})])
def test_no_other_tool_exists_and_nothing_is_written(one_aside, conn, installed, name, arguments):
    before = {t: len(h.rows(conn, t)) for t in ("decisions", "inputs", "notes", "calc_runs", "added_steps", "modules")}
    _, person, model = one_aside([h.tool(name, arguments), side("Fine.")], go_back(), first="Q")
    [result] = tool_results(model, 1)
    assert result["is_error"] is True and result["content"] == f"There is no tool called {name} here."
    assert {t: len(h.rows(conn, t)) for t in before} == before
    assert h.events(conn, "ask.decision_asked") == [] and h.events(conn, "ask.gate") == []


def test_without_a_desk_one_is_made_from_the_configured_researcher(one_aside, conn, tmp_path, monkeypatch):
    reference = tmp_path / "terms.json"
    reference.write_text(json.dumps([{"term": "sinking fund", "aliases": [], "definition": "Money set aside for a known cost.",
                                      "sources": [{"title": "A page", "url": "https://example.org/a"}]}]), encoding="utf-8")
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_REFERENCE", str(reference))
    _, _, model = one_aside([look_up("sinking fund"), side("It is money set aside.")], go_back(), first="Q")
    [event] = events_of(conn, "aside.lookup")
    assert event["found"] is True and event["origin"] == "reference" and event["definition"] == "Money set aside for a known cost."
    assert json.loads(tool_results(model, 1)[0]["content"])["name"] == event["name"]


# ---- the number check ---------------------------------------------------------------------------------------------------------

def test_a_number_in_the_context_is_backed(one_aside, conn):
    outcome, person, model = one_aside([side("Your rent is fixed at 1,150 a month.")], go_back(), first="What is my rent?")
    assert ("ask", marked("Your rent is fixed at 1,150 a month.")) in person.log
    assert h.events(conn, "aside.correction") == [] and len(model.calls) == 1


def test_a_number_the_person_just_typed_is_backed(one_aside, conn):
    _, person, _ = one_aside([side("So that is 3,456 a month.")], go_back(), first="I pay 3,456 a month for the flat.")
    assert ("ask", marked("So that is 3,456 a month.")) in person.log


def test_a_number_typed_in_a_later_message_is_backed_in_later_replies(one_aside, conn):
    _, person, _ = one_aside([side("Fine."), side("Then 3,456 it is.")], go_back(["It is 3,456 a month."]), first="Hello")
    assert ("ask", marked("Then 3,456 it is.")) in person.log


def test_what_was_looked_at_is_part_of_the_context_and_backs_numbers(one_aside, conn):
    _, person, _ = one_aside([side("The block says 2,468.")], go_back(), first="What does it say?",
                             looking_at="Taking as given: a surplus of 2,468 each month.")
    assert ("ask", marked("The block says 2,468.")) in person.log


def test_a_lookup_result_backs_the_numbers_it_holds(one_aside, conn):
    desk, _ = s4.make_desk(conn, s4.FakeResearcher({"sinking fund": "Typically 4.5% of the cost is set aside each year."}))
    _, person, model = one_aside([look_up("sinking fund"), side("Often 4.5% a year.")], go_back(), first="What is it?", desk=desk)
    assert ("ask", marked("Often 4.5% a year.")) in person.log and h.events(conn, "aside.correction") == []


def test_the_same_number_without_the_lookup_is_not_backed(one_aside, conn):
    _, person, _ = one_aside([side("Often 4.5% a year."), side("It varies.")], go_back(), first="What is a sinking fund?")
    assert ("ask", marked("Often 4.5% a year.")) not in person.log
    assert events_of(conn, "aside.correction")[0]["numbers"] == ["4.5%"]


def test_the_main_conversation_is_not_a_source(one_aside, conn, ask_agent):
    """5000 is in the question of the main conversation, and in no source of the side conversation."""
    ask_agent([h.say_text("Hello, I have your 5000 and 3000.")], ["/quit"])
    _, person, _ = one_aside([side("You earn 5000."), side("I do not have that number.")], go_back(), first="What do I earn?")
    assert ("ask", marked("You earn 5000.")) not in person.log


def test_a_number_typed_in_another_side_conversation_is_not_a_source(one_aside, conn):
    one_aside([side("Fine.")], go_back(), first="My bonus is 7,777.")
    _, person, _ = one_aside([side("Your bonus is 7,777."), side("I do not have that.")], go_back(), first="What is my bonus?",
                             aside_number=2)
    assert ("ask", marked("Your bonus is 7,777.")) not in person.log


def test_a_text_carried_by_another_side_conversation_is_not_a_source(one_aside, conn):
    outcome, _, _ = one_aside([side("Fine.")], ["/back", "My bonus is 7,777."], first="Hello")
    assert outcome == ("back", "My bonus is 7,777.")
    _, person, _ = one_aside([side("Your bonus is 7,777."), side("I do not have that.")], go_back(), first="What is my bonus?",
                             aside_number=2)
    assert ("ask", marked("Your bonus is 7,777.")) not in person.log


def test_small_whole_numbers_are_not_checked(one_aside):
    _, person, _ = one_aside([side("There are 3 steps and 12 months in a year.")], go_back(), first="Q")
    assert ("ask", marked("There are 3 steps and 12 months in a year.")) in person.log


def test_the_first_failure_sends_the_reply_back_and_the_person_sees_nothing_of_it(one_aside, conn):
    outcome, person, model = one_aside([side("You need 3,333 and 4,444."), side("I cannot say that number.")], go_back(),
                                       first="How much do I need?")
    assert len(model.calls) == 2
    assert model.calls[1]["messages"][1:] == [
        {"role": "assistant", "content": "You need 3,333 and 4,444."},
        {"role": "user", "content": ASIDE_NUMBERS.format(numbers="3,333, 4,444")}]
    assert events_of(conn, "aside.correction") == [{"aside": 1, "numbers": ["3,333", "4,444"],
                                                    "text": "You need 3,333 and 4,444."}]
    assert not [1 for kind, text in person.log if "3,333" in text]
    assert person.log[:6] == [("say", s4.ASIDE_OPEN), THINK, CALL, THINK, CALL, ("ask", marked("I cannot say that number."))]
    assert events_of(conn, "aside.reply") == [{"aside": 1, "text": "I cannot say that number."}]
    assert h.events(conn, "aside.withheld") == []


def test_a_second_failure_in_the_turn_withholds_the_reply(one_aside, conn):
    outcome, person, model = one_aside([side("You need 3,333."), side("Really 5,555.")], go_back(), first="How much?")
    assert len(model.calls) == 2
    assert events_of(conn, "aside.withheld") == [{"aside": 1, "numbers": ["5,555"], "text": "Really 5,555."}]
    assert events_of(conn, "aside.reply") == []
    assert ("ask", marked(h.WITHHELD.format(numbers="5,555"))) in person.log
    assert not [1 for kind, text in person.log if "5,555" in text and "held back" not in text]


def test_the_next_message_after_a_withheld_reply_carries_the_note(one_aside, conn):
    script = [side("You need 3,333."), side("Really 5,555."), side("I do not know.")]
    _, _, model = one_aside(script, go_back(["And now?"]), first="How much?")
    last = model.calls[2]["messages"][-1]
    assert last == {"role": "user", "content": "And now?\n\n" + h.WITHHELD_NOTE.format(numbers="5,555")}
    assert model.calls[2]["messages"][-2] == {"role": "assistant", "content": "Really 5,555."}


def test_the_note_is_for_the_one_message_after_the_withheld_reply_only(one_aside, conn):
    script = [side("You need 3,333."), side("Really 5,555."), side("I do not know."), side("Fine.")]
    _, _, model = one_aside(script, go_back(["And now?", "Thanks."]), first="How much?")
    assert model.calls[3]["messages"][-1] == {"role": "user", "content": "Thanks."}


def test_each_turn_starts_the_check_again(one_aside, conn):
    script = [side("You need 3,333."), side("I do not know."), side("It is 4,444."), side("No idea.")]
    _, person, model = one_aside(script, go_back(["And then?"]), first="How much?")
    assert len(events_of(conn, "aside.correction")) == 2 and h.events(conn, "aside.withheld") == []
    assert [p["text"] for p in events_of(conn, "aside.reply")] == ["I do not know.", "No idea."]


def test_the_numbers_are_each_once_in_the_order_of_the_text(one_aside, conn):
    one_aside([side("3,333 then 4,444 then 3,333 again."), side("No.")], go_back(), first="Q")
    assert events_of(conn, "aside.correction")[0]["numbers"] == ["3,333", "4,444"]


def test_a_corrected_reply_that_passes_is_the_reply(one_aside, conn):
    _, person, _ = one_aside([side("You need 3,333."), side("It depends on your plan.")], go_back(), first="Q")
    assert ("ask", marked("It depends on your plan.")) in person.log


# ---- empty replies, calls per turn -----------------------------------------------------------------------------------------------

def test_an_empty_reply_adds_the_empty_reply_message_and_the_model_is_called_again(one_aside, conn):
    _, person, model = one_aside([side(""), side("Sorry, here is my answer.")], go_back(), first="Q")
    assert model.calls[1]["messages"][-1] == {"role": "user", "content": h.EMPTY_REPLY}
    assert ("ask", marked("Sorry, here is my answer.")) in person.log
    assert events_of(conn, "aside.reply") == [{"aside": 1, "text": "Sorry, here is my answer."}]


def test_five_model_calls_are_the_most_for_one_turn(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    script = [look_up(f"term {n}") for n in range(1, 6)] + [side("never reached")]
    outcome, person, model = one_aside(script, go_back(), first="Q", desk=desk)
    assert MAX_ASIDE_CALLS == 5 and len(model.calls) == 5
    assert events_of(conn, "aside.stopped") == [{"aside": 1, "reason": "too many steps"}]
    assert h.events(conn, "aside.reply") == []
    assert ("ask", marked(h.TOO_MANY)) in person.log
    assert person.log.count(THINK) == 5


def test_the_turn_that_stopped_is_a_turn_and_the_next_turn_has_five_calls_again(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    script = [look_up(f"term {n}") for n in range(1, 6)] + [side("A real reply.")]
    outcome, person, model = one_aside(script, go_back(["Try again."]), first="Q", desk=desk)
    assert len(model.calls) == 6 and events_of(conn, "aside.closed")[0]["turns"] == 2
    assert model.calls[5]["messages"][-1] == {"role": "user", "content": "Try again."}
    assert events_of(conn, "aside.reply") == [{"aside": 1, "text": "A real reply."}]


def test_four_calls_and_a_reply_are_within_the_limit(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    script = [look_up(f"term {n}") for n in range(1, 5)] + [side("A real reply.")]
    _, person, model = one_aside(script, go_back(), first="Q", desk=desk)
    assert len(model.calls) == 5 and h.events(conn, "aside.stopped") == []
    assert events_of(conn, "aside.reply") == [{"aside": 1, "text": "A real reply."}]


def test_a_correction_uses_one_of_the_calls_of_the_turn(one_aside, conn):
    desk, _ = s4.make_desk(conn)
    script = [look_up("a"), look_up("b"), look_up("c"), side("You need 3,333."), side("Still 4,444."), side("never reached")]
    _, person, model = one_aside(script, go_back(), first="Q", desk=desk)
    assert len(model.calls) == 5 and len(h.events(conn, "aside.withheld")) == 1


def test_the_side_calls_do_not_count_for_the_main_conversation(ask_agent, conn):
    script = [s4.run_pair(s4.run(assumptions=[]), s4.run(assumptions=[])), h.say_text("Done."), side("A thing.")]
    model, person = ask_agent(script, ["/aside what is this?", "/back", "no", "/quit"])
    assert len(model.of("analyst")) == 2


def test_the_given_prompts_hold_the_context_placeholder_once():
    assert h.prompt_text("aside.md").count("{context}") == 1
    assert h.prompt_text("analyst.md").count("{context}") == 1
