"""SPEC 5.1: an analyst turn on the main lane: what the model is told, its calls, and what ends a turn."""
from pathlib import Path

from harness.answers.agent import tool_result
from harness.answers.layer import LAYER as ANSWERS, route
from harness.calc.layer import LAYER as CALC
from harness.grounding.layer import LAYER as GROUNDING
from harness.layers import BASE, Layer
from harness.model import ToolSpec
from layer3_helpers import SETTLE, assistant, call, events, reply, run, save, say

ANALYST = Path(__file__).resolve().parents[2] / "harness" / "answers" / "analyst.md"


def test_a_message_after_the_plan_is_accepted_is_one_analyst_turn(open_session):
    session = open_session([reply("What is amount A?")])
    state = say(session, "How much is the total?")
    assert [message["who"] for message in state["chat"]] == ["you", "assistant"]
    assert state["chat"][1]["text"] == "What is amount A?" and state["chat"][1]["kind"] == "text"
    assert state["lanes"]["main"] == "idle" and state["activity"] == []
    assert [each["text"] for each in events(session, "ask.message")] == ["How much is the total?"]


def test_the_model_is_given_the_prompt_the_context_and_the_tools(open_session):
    session = open_session([reply("Hello")])
    say(session, "How much is the total?")
    first = session.script.calls[0]
    assert ANALYST.read_text(encoding="utf-8").strip() in first["system"]
    known = first["system"].split("## What you know")[1]
    for section in ("today", "goal", "particulars", "process", "modules", "saved inputs", "notes"):
        assert f"[{section}]" in known
    assert "2026-10-10" in known and '"id": "c3"' in known
    assert {spec.name for spec in first["tools"]} >= {"run_module", "save_input", "change_plan"}


def test_a_step_with_no_module_is_shown_as_having_none(open_session):
    session = open_session([reply("Hello")])
    say(session, "Hello")
    process = session.script.calls[0]["system"].split("[process]")[1].split("[modules]")[0]
    assert '"module": null' in process and '"build": "none"' in process


def test_a_message_about_a_step_says_so_to_the_model(open_session):
    session = open_session([reply("Hello")])
    say(session, "What does this do?", step="c1")
    assert session.script.calls[0]["messages"][-1]["content"].startswith("[harness] About step c1 (Total):")


def test_the_step_helper_keeps_the_messages_it_wants(open_session, monkeypatch):
    session = open_session([])
    message = {"id": "m1", "text": "x", "step": "c1", "notice": None}
    assert route(session, message) is not None
    from harness.calc import helper
    monkeypatch.setattr(helper, "wants", lambda core, step: True)
    assert route(session, message) is None
    assert route(session, {**message, "step": None}) is not None


def test_the_model_keeps_the_conversation_for_the_life_of_the_session(open_session):
    session = open_session([reply("One?"), reply("Two?")])
    say(session, "first")
    say(session, "second")
    roles = [message["role"] for message in session.script.calls[1]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_a_new_process_starts_fresh_but_the_prompt_holds_what_was_saved_and_run(open_session):
    first = open_session([save("amount_a", 100), run("total", {"a": 100, "b": 50}), reply("It is 150.")])
    say(first, "Amount A is 100 and B is 50")
    second = open_session([reply("Anything else?")])
    state = say(second, "Hello again")
    call_ = second.script.calls[0]
    assert len(call_["messages"]) == 1                               # no memory of the first process
    assert '"amount_a"' in call_["system"] and "earlier runs in this conversation" in call_["system"]
    assert state["chat"][0]["text"] == "Amount A is 100 and B is 50"      # the chat is the same conversation


def test_an_empty_reply_is_asked_for_again(open_session):
    session = open_session([reply(""), reply("Fine")])
    state = say(session, "Hello")
    assert [message["text"] for message in assistant(state)] == ["Fine"]
    assert session.script.calls[1]["messages"][-1]["content"].startswith("[harness]")


def test_a_turn_stops_after_ten_model_calls(open_session):
    session = open_session([call("nothing_here")] * 10)
    state = say(session, "Hello")
    assert len(session.script.calls) == 10
    assert [(message["who"], message["kind"]) for message in assistant(state)] == [("harness", "text")]
    assert events(session, "ask.stopped") and not events(session, "ask.reply")


def test_a_failed_model_call_sets_the_error_and_leaves_no_half_turn(open_session):
    session = open_session([])
    state = say(session, "Hello")
    assert state["error"] and events(session, "core.job_failed")
    session.script.script.append(reply("Back again"))
    state = say(session, "Hello again")
    assert [message["role"] for message in session.script.calls[-1]["messages"]] == ["user"]
    assert [message["text"] for message in assistant(state)] == ["Back again"]


def test_the_tools_prompt_context_and_hook_of_a_later_layer_join_the_turn(open_session, tmp_path):
    extra = tmp_path / "extra.md"
    extra.write_text("Extra rules for the analyst.", encoding="utf-8")
    finished, pinged = [], []

    def ping(turn, call_):
        pinged.append(call_.arguments)
        return tool_result(call_, "pong")

    later = Layer(number=4, name="later", prompt=extra, context=lambda conn: {"later section": "xyz"},
                  tools=lambda turn: [(ToolSpec("ping", "pings", {"type": "object", "properties": {}}), ping)],
                  hooks={"turn_finished": lambda work, turn: finished.append(turn)})
    session = open_session([call("ping", n="x"), run("total", {"a": 1, "b": 2}), reply("Done.")],
                           layers=[BASE, GROUNDING, CALC, ANSWERS, later])
    state = say(session, "Go")
    first = session.script.calls[0]
    assert {spec.name for spec in first["tools"]} >= {"ping", "run_module"}
    assert first["system"].index("Extra rules") > first["system"].index("never") and "[later section]" in first["system"]
    assert pinged == [{"n": "x"}]
    turn = finished[0]
    assert turn.runs == [1] and turn.reply == assistant(state)[-1]["id"] and turn.withheld is False
