"""SPEC 5.7: `build_step`, the whole pipeline for one step, and `build`, which calls it for each step of the process."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (NO_STEP, REASON_CODE, REASON_SKIPPED, REASON_STOPPED, STEP_HEADER, built, events, months_script,
                           only_step, payloads, propose_examples, propose_spec, respond, reuse_module, rows, sections,
                           surplus_script, write_module, yearly_script)

S1 = {"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}
S3 = {"step": "s3", "outcome": "built", "module": "months_to_goal", "reason": ""}
ADDED = {"step": "added_1", "outcome": "built", "module": "yearly_cost", "reason": ""}


def stopped(step):
    return {"step": step, "outcome": "not_built", "module": None, "reason": REASON_STOPPED}


# ---- calling build_step ----------------------------------------------------------------------

def test_build_step_takes_keyword_arguments_only(builder, conn, brief):
    person = h.Person()
    with pytest.raises(TypeError):
        builder.build_step(h.TracingModel([], person), conn, brief, brief["process"][0], person.ask)


def test_say_defaults_to_print_and_rebuild_to_none(builder, conn, brief, capsys):
    h.install_surplus(conn, "s1")
    person = h.Person()
    result = builder.build_step(model=h.TracingModel([], person), conn=conn, brief=brief, step=brief["process"][0],
                                ask=person.ask, session_id=h.SESSION)
    assert result == {"step": "s1", "outcome": "kept", "module": "monthly_surplus", "reason": ""}
    assert capsys.readouterr().out == STEP_HEADER.format(id="s1", name="Work out the monthly surplus") + "\n"


def test_a_built_step_returns_its_result(build_one):
    result, model, _ = build_one(surplus_script(), built())
    assert result == S1 and len(model.calls) == 3


def test_the_result_has_the_four_keys(build_one):
    result, _, _ = build_one(surplus_script(), built())
    assert sorted(result) == ["module", "outcome", "reason", "step"]


def test_only_the_given_step_is_handled(build_one, conn):
    result, model, person = build_one(surplus_script(), built())          # the brief also has s3
    assert result == S1
    assert [t for t in person.told if t.startswith("Step ")] == ["Step s1: Work out the monthly surplus"]
    assert [r["name"] for r in rows(conn, "modules")] == ["monthly_surplus"]


def test_the_step_starts_with_its_header(build_one):
    _, _, person = build_one(surplus_script(), built())
    assert person.log[0] == ("say", STEP_HEADER.format(id="s1", name="Work out the monthly surplus"))


def test_a_step_with_an_unchanged_module_is_kept_and_no_model_is_called(build_one, conn):
    h.install_surplus(conn, "s1")
    result, model, person = build_one([])
    assert result == {"step": "s1", "outcome": "kept", "module": "monthly_surplus", "reason": ""}
    assert model.calls == [] and person.asked == []


def test_a_reused_module_is_a_result_too(build_one, conn):
    h.install_surplus(conn, "old_step")
    result, model, _ = build_one([reuse_module("monthly_surplus")])
    assert result == {"step": "s1", "outcome": "reused", "module": "monthly_surplus", "reason": ""}
    assert len(model.calls) == 1


def test_the_meta_of_a_brief_is_dropped(build_one, brief):
    meta = {"status": "confirmed", "written_at": "WRITTEN-AT-MARKER"}
    _, model, _ = build_one(surplus_script(), built(), brief={**brief, "meta": meta})
    assert "WRITTEN-AT-MARKER" not in json.dumps(model.calls[0]["messages"])


def test_rebuild_rebuilds_that_module_for_the_step(build_one, conn, registry):
    h.install_surplus(conn, "s1")
    result, model, _ = build_one(surplus_script(), built(), rebuild="monthly_surplus")
    assert result == S1
    assert [t.name for t in model.calls[0]["tools"]] == ["propose_spec"]
    assert registry.file_status(conn, "monthly_surplus") == "unchanged"


def test_a_module_whose_files_changed_is_rebuilt_without_being_asked(build_one, conn, modules_dir):
    h.install_surplus(conn, "s1")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    result, model, _ = build_one(surplus_script(), built())
    assert result == S1 and [t.name for t in model.calls[0]["tools"]] == ["propose_spec"]


# ---- /quit is caught by build_step -------------------------------------------------------------

STOPS = [
    ([propose_spec()], ["/quit"]),
    ([propose_spec(), propose_examples()], ["yes", "/quit"]),
    ([propose_spec(), propose_examples(), respond("correct", answer="2000")], ["yes", "it should be 2000", "/quit"]),
]
STOP_IDS = ["at the plan check", "at an example", "at a transcribed answer"]


@pytest.mark.parametrize("script, answers", STOPS, ids=STOP_IDS)
def test_quit_ends_the_step_as_not_built_and_does_not_raise(build_one, conn, registry, script, answers):
    result, _, _ = build_one(script, answers)
    assert result == stopped("s1")
    assert registry.list_modules(conn) == [] and registry.step_map(conn) == {}


@pytest.mark.parametrize("script, answers", STOPS, ids=STOP_IDS)
def test_a_stopped_step_is_recorded_before_build_step_returns(build_one, conn, script, answers):
    build_one(script, answers)
    assert events(conn, "calc.step_not_built") == [("calc.step_not_built", "harness", {
        "step": "s1", "reason": REASON_STOPPED})]


def test_every_not_built_result_is_recorded(build_one, conn):
    result, _, _ = build_one([propose_spec()], ["/skip"])
    assert result["reason"] == REASON_SKIPPED
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_SKIPPED}]


def test_a_built_step_records_no_not_built_event(build_one, conn):
    build_one(surplus_script(), built())
    assert events(conn, "calc.step_not_built") == []


def test_a_model_call_that_raises_leaves_build_step(build_one, conn):
    from harness.model import ScriptExhausted

    with pytest.raises(ScriptExhausted):
        build_one([propose_spec()], ["yes"])                              # the example writer has no reply


def test_notes_saved_in_a_stopped_step_stay(build_one, conn):
    result, _, _ = build_one([propose_spec(), propose_spec(h.revised_spec())], ["I have a list of costs", "/quit"])
    assert result == stopped("s1")
    assert [r["text"] for r in rows(conn, "notes")] == ["I have a list of costs"]


# ---- an added step is a step like any other ----------------------------------------------------

def test_an_added_step_is_built_with_its_label_and_reason(build_one, conn, brief):
    step = h.add_new_step(conn)
    result, model, person = build_one(yearly_script(), built(), step=step)
    assert result == ADDED
    assert person.log[0] == ("say", STEP_HEADER.format(id="added_1 (not in the brief)", name=step["name"]))
    first = model.calls[0]["messages"][0]["content"]
    assert first == sections(("step", step), ("brief", brief), ("registered modules", []), ("notes", []))
    assert json.loads(first.split("[step]\n")[1].split("\n\n[brief]")[0])["reason"] == h.NEW_TEXTS["why"]


def test_a_module_built_for_an_added_step_is_mapped_to_it(build_one, conn, registry, modules_dir):
    step = h.add_new_step(conn)
    build_one(yearly_script(), built(), step=step)
    assert registry.step_map(conn) == {"added_1": "yearly_cost"}
    assert (modules_dir / "yearly_cost" / "spec.json").read_text(encoding="utf-8") == h.dump(
        h.saved_spec(h.yearly_spec(), "added_1"))


def test_the_brief_sent_to_the_spec_writer_has_no_added_steps(build_one, conn):
    step = h.add_new_step(conn)
    h.add_new_step(conn, name="a second one")
    _, model, _ = build_one(yearly_script(), built(), step=step)
    section = model.calls[0]["messages"][0]["content"].split("[brief]\n")[1].split("\n\n[registered modules]")[0]
    assert json.loads(section) == h.make_brief() and "a second one" not in section


# ---- build: the steps of the process ----------------------------------------------------------

def test_build_handles_the_brief_steps_and_then_the_added_steps(build, conn):
    step = h.add_new_step(conn)
    script = surplus_script() + months_script() + yearly_script()
    results, model, person = build(script, built(3))
    assert results == [S1, S3, ADDED] and len(model.calls) == 9
    assert [t for t in person.told if t.startswith("Step ")] == [
        "Step s1: Work out the monthly surplus", "Step s3: Work out the months to reach the target",
        f"Step added_1 (not in the brief): {step['name']}"]


def test_added_steps_come_in_the_order_they_were_added(build, conn):
    h.add_new_step(conn, name="first one")
    h.add_new_step(conn, name="second one")
    h.install_surplus(conn, "s1")
    second = [propose_spec(h.yearly_spec(name="second_cost")), propose_examples(h.yearly_examples()),
              write_module(h.YEARLY_PY, h.YEARLY_TESTS)]
    results, _, person = build(yearly_script() + second, built(2), brief=only_step("s1"))
    assert [(r["step"], r["outcome"]) for r in results] == [("s1", "kept"), ("added_1", "built"), ("added_2", "built")]
    assert [t for t in person.told if t.startswith("Step ")] == [
        "Step s1: Work out the monthly surplus", "Step added_1 (not in the brief): first one",
        "Step added_2 (not in the brief): second one"]


def test_an_added_step_with_a_working_module_is_kept(build, conn):
    h.add_new_step(conn)
    h.install_yearly(conn)
    results, model, person = build([], brief=h.make_brief(process=[]))
    assert results == [{"step": "added_1", "outcome": "kept", "module": "yearly_cost", "reason": ""}]
    assert model.calls == []
    assert person.told == ["Step added_1 (not in the brief): " + h.NEW_TEXTS["works_out"]]


def test_an_added_step_whose_module_changed_is_rebuilt(build, conn, modules_dir):
    h.add_new_step(conn)
    h.install_yearly(conn)
    (modules_dir / "yearly_cost" / "module.py").write_text("# edited\n" + h.YEARLY_PY, encoding="utf-8")
    results, model, _ = build(yearly_script(), built(), brief=h.make_brief(process=[]))
    assert results == [ADDED] and [t.name for t in model.calls[0]["tools"]] == ["propose_spec"]


def test_a_brief_with_only_a_judgment_step_still_builds_the_added_step(build, conn):
    h.add_new_step(conn)
    results, _, _ = build(yearly_script(), built(), brief=h.make_brief(process=[h.make_brief()["process"][1]]))
    assert results == [ADDED]


def test_a_failed_added_step_does_not_stop_the_build_and_stays(build, conn, added):
    h.add_new_step(conn)
    bad = propose_spec(name="Bad Name")
    results, _, _ = build([bad, bad, bad], brief=h.make_brief(process=[]))
    assert results[0]["outcome"] == "not_built"
    assert [s["id"] for s in added.list_added_steps(conn)] == ["added_1"]


def test_rebuild_of_a_module_built_for_an_added_step(build, conn):
    h.add_new_step(conn)
    h.install_yearly(conn)
    results, model, person = build(yearly_script(), built(), rebuild="yearly_cost")
    assert results == [ADDED]
    assert person.told[0] == f"Step added_1 (not in the brief): {h.NEW_TEXTS['works_out']}"


def test_rebuild_of_a_module_whose_added_step_is_not_in_the_process(build, conn):
    h.install_yearly(conn, "added_9")
    with pytest.raises(ValueError) as error:
        build([], rebuild="yearly_cost")
    assert str(error.value) == NO_STEP.format(step="added_9", name="yearly_cost")


# ---- build stops its list on REASON_STOPPED ------------------------------------------------------

def test_a_stopped_step_ends_the_list_and_the_added_steps_after_it_are_not_handled(build, conn):
    h.add_new_step(conn)
    results, model, person = build(surplus_script()[:1] + months_script(), ["/quit"])
    assert results == [stopped("s1")] and len(model.calls) == 1
    assert not any(t.startswith("Step s3") or t.startswith("Step added_1") for t in person.told)


def test_a_stop_in_a_later_step_keeps_the_results_before_it(build, conn):
    h.add_new_step(conn)
    results, model, person = build(surplus_script() + months_script()[:1], [*built(), "/quit"])
    assert results == [S1, stopped("s3")]
    assert not any(t.startswith("Step added_1") for t in person.told)


def test_a_step_that_fails_for_another_reason_does_not_end_the_list(build, conn):
    wrong = write_module(h.WRONG_SURPLUS_PY, h.WRONG_SURPLUS_TESTS)
    script = [propose_spec(), propose_examples(), wrong, wrong, wrong, *months_script()]
    results, _, _ = build(script, built(2))
    assert [r["reason"] for r in results] == [REASON_CODE, ""] and results[1] == S3


# ---- build calls build_step ------------------------------------------------------------------

def test_build_calls_build_step_for_each_calculation_step_with_no_rebuild(builder, build, monkeypatch, conn):
    h.add_new_step(conn)
    calls, real = [], builder.build_step

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(builder, "build_step", spy)
    build(surplus_script() + months_script() + yearly_script(), built(3))
    assert [c["step"]["id"] for c in calls] == ["s1", "s3", "added_1"]
    assert all(c.get("rebuild") is None for c in calls)


def test_build_with_rebuild_calls_build_step_once_with_the_name(builder, build, monkeypatch, conn):
    h.install_surplus(conn, "s1")
    calls, real = [], builder.build_step

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(builder, "build_step", spy)
    build(surplus_script(), built(), rebuild="monthly_surplus")
    assert [(c["step"]["id"], c["rebuild"]) for c in calls] == [("s1", "monthly_surplus")]
