"""SPEC 4.3 to 4.5: the unattended build, the second pass, stale steps and the gate."""
import json
import threading

import pytest

from harness.calc import builder, gate, registry
from harness.calc.builder import build_step, confirm_departures, record_confirmation, run_step_tests
from harness.grounding.brief import step_fingerprint
from harness.model import ScriptedModel
from layer2_helpers import (SETTLE, TOTAL_CODE, TOTAL_EXAMPLES, TOTAL_SPEC, WRONG_TOTAL_CODE,
                            call, checker_turn, code_turn, double_turns, events, examples_turn, small_plan,
                            spec_turn, step_of, total_example, total_turns, write_plan)


def plain(items):
    """Disagreements without how the pop-up shows them."""
    return [{key: value for key, value in each.items() if key != "shown"} for each in items]


def harness_messages(state):
    return [message for message in state["chat"] if message["who"] == "harness"]


def run_job(session, job):
    session.queue("main", job, what="build")
    return session.settle(SETTLE)


def gate_call(session, name, inputs):
    return gate.call(session.conn, name, inputs, assumptions=[], expected="a number", session_id="t")


# --- The whole build ---

def test_the_build_runs_every_calculation_step_without_stopping(tmp_path, plan, open_session, build):
    session = open_session(total_turns() + double_turns())
    state = build(session)
    assert state["waiting"] is None and state["lanes"]["main"] == "idle" and state["error"] is None
    for step_id, name in (("c1", "total"), ("c2", "double")):
        step = step_of(state, step_id)
        found = step["build"]
        assert (found["status"], found["module"], found["reason"]) == ("built", name, "")
        assert (found["examples"], found["examples_passing"], found["tests"], found["passing"]) == (3, 3, 1, 1)
        assert step["line"]["kind"] == "tested" and found["tested_at"] and found["code"]["module_py"]
        assert [each["checked_by"] for each in found["example_list"]] == ["second_pass"] * 3
        golden = json.loads((tmp_path / "modules" / name / "golden.json").read_text())
        assert [each["checked_by"] for each in golden] == ["second_pass"] * 3
        assert registry.get_module(session.conn, name)["step_fingerprint"] == step_fingerprint(plan, step_id)
    assert step_of(state, "j1")["build"] is None
    assert events(session, "build.finished")[-1] == {"steps": {"c1": "built", "c2": "built"}}
    assert len(harness_messages(state)) == 1              # BUILD_DONE, and nothing needs the person
    assert gate_call(session, "double", {"total": "21"})["output"] == "42"


def test_progress_is_reported_through_activity_while_a_step_builds(plan, open_session, build):
    class Watching:
        def __init__(self):
            self.inner, self.seen, self.session = ScriptedModel(total_turns() + double_turns()), [], None

        def complete(self, **request):
            self.seen.append(self.session.state())
            return self.inner.complete(**request)

    model = Watching()
    session = open_session(model=model)
    model.session = session
    build(session)
    assert len(model.seen) == 8
    for seen in model.seen:
        (entry,) = [each for each in seen["activity"] if each["lane"] == "main"]
        assert entry["what"] == "build" and entry["step"] in ("c1", "c2") and entry["text"]
        step = step_of(seen, entry["step"])
        assert step["build"]["status"] == "building" and step["line"]["text"] == "Building"
    assert {each["activity"][0]["text"] for each in model.seen} >= {"writing the code, attempt 1",
                                                                     "second pass on 3 examples"}


def test_the_checker_and_the_code_writer_never_see_the_examples_answers(plan, open_session, build):
    session = open_session(total_turns() + double_turns())
    build(session)
    spec_call, writer_call, checker_call, code_call = session.script.calls[:4]
    assert [tool.name for tool in checker_call["tools"]] == ["answer_examples"]
    sent = json.dumps(checker_call["messages"])
    assert "10 + 20" not in sent and "expected" not in sent and "working" not in sent
    assert '\\"n\\": 3' in sent and "250" in sent                      # numbers and inputs only
    assert "Know the total" not in sent and "euros" not in sent        # nor the brief
    coded = json.dumps(code_call["messages"])
    assert "250" not in coded and "working" not in coded
    assert "departures" in spec_call["tools"][0].input_schema["required"]


def test_examples_the_second_pass_disputes_are_left_out_and_more_are_asked_for(plan, open_session, build):
    more = [total_example(1, 1), total_example(2, 2), total_example(3, 3)]
    script = [spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES),
              checker_turn(TOTAL_EXAMPLES, answers={1: "31", 2: "51"}),
              examples_turn(more), checker_turn(more, start=4), code_turn(TOTAL_CODE), *double_turns()]
    session = open_session(script)
    state = build(session)
    found = step_of(state, "c1")["build"]
    assert found["status"] == "built" and found["examples"] == 4
    assert [(each["n"], each["checked_by"], each["second_pass"]) for each in found["example_list"][:3]] == [
        (1, None, "31"), (2, None, "51"), (3, "second_pass", None)]
    assert session.script.calls[3]["messages"][-1]["content"].startswith("[harness]")
    left_out = events(session, "build.second_pass")[0]["left_out"]
    assert [(each["n"], each["answer"], each["why"]) for each in left_out] == [(1, "31", "a different answer"),
                                                                            (2, "51", "a different answer")]


def test_too_few_agreed_examples_leave_the_step_not_built_and_the_build_goes_on(plan, open_session, build):
    more = [total_example(1, 1), total_example(2, 2), total_example(3, 3)]
    script = [spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES),
              checker_turn(TOTAL_EXAMPLES, answers={1: "31", 2: "51"}),
              examples_turn(more), checker_turn(more, start=4, answers={4: "3", 5: "5", 6: "7"}), *double_turns()]
    session = open_session(script)
    state = build(session)
    step = step_of(state, "c1")
    assert step["build"]["status"] == "not_built"
    assert step["build"]["reason"] == builder.REASON_SECOND_PASS
    assert step["needs_you"] and step["line"] == {"text": "Needs you · not built", "kind": "strong"}
    assert len(step["build"]["example_list"]) == 6 and step["build"]["module"] is None
    assert step_of(state, "c2")["build"]["status"] == "built"
    assert events(session, "build.finished")[-1]["steps"] == {"c1": "not_built", "c2": "built"}
    assert events(session, "build.not_built")[0]["reason"] == builder.REASON_SECOND_PASS
    assert len(harness_messages(state)) == 2              # BUILD_DONE and BUILD_NEEDS_YOU


def test_code_that_disagrees_with_an_example_leaves_the_step_not_built(plan, open_session, build):
    script = [spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES), checker_turn(TOTAL_EXAMPLES),
              *[code_turn(WRONG_TOTAL_CODE)] * 3, *double_turns()]
    session = open_session(script)
    state = build(session)
    found = step_of(state, "c1")["build"]
    assert (found["status"], found["reason"]) == ("not_built", builder.REASON_CODE)
    assert plain(found["disagreement"]) == [{"n": 1, "expected": "30", "code_gives": "31"},
                                     {"n": 2, "expected": "50", "code_gives": "51"},
                                     {"n": 3, "expected": "350", "code_gives": "351"}]
    assert found["code"]["module_py"] == WRONG_TOTAL_CODE[0]
    feedback = [message["content"] for message in session.script.calls[5]["messages"] if message["role"] == "tool"]
    assert "Example 1 failed" in feedback[-1] and "30" not in feedback[-1] and "351" not in feedback[-1]
    assert registry.get_module(session.conn, "total") is None


def test_departures_put_a_plan_check_on_the_step_until_the_person_confirms_them(plan, open_session, build):
    session = open_session(total_turns(departures=["Takes a list of costs"]) + double_turns())
    state = build(session)
    assert step_of(state, "c1")["build"]["plan_check"] == {"departures": ["Takes a list of costs"],
                                                           "confirmed": False}
    assert [mark["symbol"] for mark in step_of(state, "c1")["marks"]] == ["plan check"]
    assert step_of(state, "c2")["build"]["plan_check"] is None
    confirm_departures(session.conn, "c1", session_id="t")
    state = session.state()
    assert step_of(state, "c1")["build"]["plan_check"]["confirmed"] and step_of(state, "c1")["marks"] == []
    assert events(session, "build.departures_confirmed")[0]["step"] == "c1"


def test_only_departures_in_substance_put_a_plan_check_on_the_step(plan, open_session, build):
    kinds = [{"kind": "made_exact", "text": "Takes the extra costs as a list"},
             {"kind": "input", "text": "Takes a date the plan does not name"}]
    session = open_session(total_turns(departures=kinds) + double_turns(departures=[
        {"kind": "made_exact", "text": "Rounds to the cent"}]))
    state = build(session)
    assert step_of(state, "c1")["build"]["plan_check"] == {"departures": ["Takes a date the plan does not name"],
                                                           "confirmed": False}
    assert step_of(state, "c2")["build"]["plan_check"] is None and step_of(state, "c2")["marks"] == []
    proposed = events(session, "build.spec_proposed")
    assert proposed[0]["made_exact"] == ["Takes the extra costs as a list"] and proposed[1]["departures"] == []


def test_a_departure_of_an_unknown_kind_sends_the_spec_back(plan, open_session, build):
    session = open_session(total_turns(departures=[{"kind": "style", "text": "Nicer"}]))
    build(session)
    assert any(builder.BAD_DEPARTURES in error for each in events(session, "build.spec_rejected")
               for error in each["errors"])


def test_a_step_may_reuse_a_registered_module(plan, open_session, build):
    session = open_session(total_turns() + [call("reuse_module", module="total", reason="same job")])
    state = build(session)
    assert step_of(state, "c2")["build"]["module"] == "total" and step_of(state, "c2")["build"]["status"] == "built"
    assert events(session, "build.finished")[-1]["steps"] == {"c1": "built", "c2": "reused"}


def test_no_acceptable_spec_or_failed_model_calls_end_not_built(plan, open_session, build):
    no_departures = {"tool_calls": [{"name": "propose_spec", "arguments": TOTAL_SPEC}]}
    session = open_session([no_departures, spec_turn({**TOTAL_SPEC, "name": "Not A Name"})])
    state = build(session)
    for step_id in ("c1", "c2"):
        assert step_of(state, step_id)["build"]["reason"] == builder.REASON_SPEC
    rejected = events(session, "build.spec_rejected")
    assert builder.BAD_DEPARTURES in rejected[0]["errors"] and len(rejected) == 2
    assert "ScriptExhausted" in events(session, "build.not_built")[0]["error"]
    assert state["error"] is None


def test_a_second_build_keeps_what_is_built_without_calling_the_model(plan, open_session, build):
    session = open_session(total_turns() + double_turns())
    build(session)
    calls = len(session.script.calls)
    build(session)
    assert len(session.script.calls) == calls
    assert events(session, "build.finished")[-1]["steps"] == {"c1": "kept", "c2": "kept"}


def test_build_is_refused_without_a_plan_and_while_one_runs(tmp_path, open_session):
    session = open_session([])
    assert session.act("build", {}) == (False, builder.NO_PLAN)
    write_plan(tmp_path / "brief")
    release = threading.Event()

    class Slow:
        def complete(self, **request):
            release.wait(SETTLE)
            raise RuntimeError("no model here")

    session = open_session(model=Slow())
    assert session.act("build", {})[0]
    assert session.act("build", {}) == (False, builder.ALREADY_BUILDING)
    release.set()
    session.settle(SETTLE)


# --- Stale, the gate, and the person's word ---

def test_a_changed_plan_makes_the_step_stale_and_the_gate_refuses_it_until_rebuilt(tmp_path, plan, open_session,
                                                                                 build):
    session = open_session(total_turns() + double_turns()
                           + [spec_turn({**TOTAL_SPEC, "name": "other", "formula": "a + b + c"}),
                              examples_turn(TOTAL_EXAMPLES), checker_turn(TOTAL_EXAMPLES), code_turn(TOTAL_CODE)])
    build(session)
    changed = small_plan()
    changed["process"][0]["formula"] = "a + b + c"
    write_plan(tmp_path / "brief", changed)
    state = session.state()
    assert step_of(state, "c1")["build"]["status"] == "stale"
    assert step_of(state, "c1")["build"]["reason"] == registry.STALE_PLAN
    assert step_of(state, "c1")["line"]["text"] == "Stale · rebuild"
    assert step_of(state, "c2")["build"]["status"] == "built"
    with pytest.raises(gate.Refused, match="changed in the plan"):
        gate_call(session, "total", {"a": "1", "b": "2"})
    state = build(session)
    assert events(session, "build.finished")[-1]["steps"] == {"c1": "built", "c2": "kept"}
    spec_call = session.script.calls[8]
    assert "[current spec]" in spec_call["messages"][0]["content"]
    assert [tool.name for tool in spec_call["tools"]] == ["propose_spec"]
    assert step_of(state, "c1")["build"]["module"] == "total"              # built again under its name
    assert gate_call(session, "total", {"a": "1", "b": "2"})["output"] == "3"


def test_changed_files_make_the_step_stale(tmp_path, plan, open_session, build):
    session = open_session(total_turns() + double_turns())
    build(session)
    (tmp_path / "modules" / "double" / "module.py").write_text("def calculate(total):\n    return total * 3\n")
    found = step_of(session.state(), "c2")["build"]
    assert (found["status"], found["reason"]) == ("stale", registry.STALE_FILES)
    with pytest.raises(gate.Refused, match="not the ones that passed"):
        gate_call(session, "double", {"total": "1"})


def test_a_corrected_example_rebuilds_the_code_and_a_disagreement_stops_the_gate(plan, open_session, build):
    session = open_session(total_turns() + double_turns() + [code_turn(TOTAL_CODE)] * 3)
    build(session)
    assert record_confirmation(session.conn, "c1", 1, answer="31", session_id="t") == {"rebuild": True}
    run_job(session, lambda work: build_step(work, "c1", code_only=True))
    found = step_of(session.state(), "c1")["build"]
    assert (found["status"], found["reason"]) == ("not_built", builder.REASON_CODE)
    assert plain(found["disagreement"]) == [{"n": 1, "expected": "31", "code_gives": "30"}]
    assert found["example_list"][0]["checked_by"] == "you" and found["module"] == "total"
    assert events(session, "build.example_corrected")[0] == {"step": "c1", "n": 1, "answer": "31"}
    with pytest.raises(gate.Refused, match="not built"):
        gate_call(session, "total", {"a": "1", "b": "2"})


def test_a_confirmed_left_out_example_joins_the_tests_and_survives_a_rebuild(tmp_path, plan, open_session, build):
    script = [spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES),
              checker_turn(TOTAL_EXAMPLES, answers={3: "349"}), code_turn(TOTAL_CODE), *double_turns(),
              spec_turn(TOTAL_SPEC), examples_turn(TOTAL_EXAMPLES[:2] + [total_example(5, 5)]),
              checker_turn(TOTAL_EXAMPLES[:2] + [total_example(5, 5)], start=2), code_turn(TOTAL_CODE)]
    session = open_session(script)
    build(session)
    assert step_of(session.state(), "c1")["build"]["examples"] == 2
    assert record_confirmation(session.conn, "c1", 1, session_id="t") == {"rebuild": False}
    assert record_confirmation(session.conn, "c1", 3, session_id="t") == {"rebuild": True}
    calls = len(session.script.calls)
    run_job(session, lambda work: build_step(work, "c1", code_only=True))
    assert len(session.script.calls) == calls                 # the code it has passes: no model call
    found = step_of(session.state(), "c1")["build"]
    assert found["status"] == "built" and found["examples"] == 3
    assert [each["checked_by"] for each in found["example_list"]] == ["you", "second_pass", "you"]
    golden = json.loads((tmp_path / "modules" / "total" / "golden.json").read_text())
    assert [each["checked_by"] for each in golden] == ["you", "second_pass", "you"]
    assert session.conn.execute("SELECT COUNT(*) FROM example_confirmations").fetchone()[0] == 2

    changed = small_plan()
    changed["process"][0]["formula"] = "a plus b"
    write_plan(tmp_path / "brief", changed)
    build(session)
    found = step_of(session.state(), "c1")["build"]
    assert found["status"] == "built"
    assert [(each["inputs"], each["checked_by"]) for each in found["example_list"][:2]] == [
        ({"a": "10", "b": "20"}, "you"), ({"a": "100", "b": "250"}, "you")]


def test_run_step_tests_runs_the_tests_of_a_steps_module(plan, open_session, build):
    session = open_session(total_turns() + double_turns())
    build(session)
    run = run_step_tests(session.conn, "c2", session_id="t")
    assert run["passed"]
    assert events(session, "build.tests_run")[-1]["reason"] == "status"
    with pytest.raises(ValueError):
        run_step_tests(session.conn, "j1", session_id="t")


def test_an_example_answer_must_fit_the_output_type(plan, open_session, build):
    session = open_session(total_turns() + double_turns())
    build(session)
    with pytest.raises(ValueError):
        record_confirmation(session.conn, "c1", 1, answer=["30"], session_id="t")
    with pytest.raises(ValueError):
        record_confirmation(session.conn, "c1", 9, session_id="t")

