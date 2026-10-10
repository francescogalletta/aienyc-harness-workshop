"""SPEC 6.5: `run_scenario` runs one scenario in a scratch folder, with the scripted model."""
import hashlib
import json
import os
from pathlib import Path

import pytest

import step3_helpers as s3
from step3_helpers import ROOT, ask_script, h
from harness.model import ScriptedModel

SCENARIO_KEYS = ["scenario", "passed", "checks", "error", "folder"]


@pytest.fixture(autouse=True)
def scratch(replay_scratch):
    """Every test here runs from the repository root and has what it leaves in my/var/replay taken away."""
    return replay_scratch


def run(replay, example, scenario=None, *, script=None, keep=False, model=None, name=None):
    folder = example(scenarios={}) if callable(example) else example
    scenario = scenario or s3.ask_scenario()
    model = model or ScriptedModel(script if script is not None else ask_script())
    return replay.run_scenario(scenario, example_dir=folder, model=model, keep=keep)


def kept_events(result, **options):
    return s3.stored_events(Path(result["folder"]) / "harness.db", **options)


def tree(folder):
    """{relative path: digest} of every file under a folder."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*")) if p.is_file()}


# ---- the result ------------------------------------------------------------------------------------------------------

def test_a_scenario_that_goes_well_passes(replay, example):
    result = run(replay, example)
    assert result["scenario"] == "upfront" and result["passed"] is True and result["error"] is None
    assert result["folder"] is None
    assert len(result["checks"]) == 4 and all(check["passed"] for check in result["checks"])


def test_the_result_holds_these_keys(replay, example):
    assert sorted(run(replay, example)) == sorted(SCENARIO_KEYS)


def test_the_checks_are_those_of_check_scenario_over_the_session(replay, example, monkeypatch):
    from harness import db
    scenario = s3.ask_scenario()
    result = run(replay, example, scenario, keep=True)
    session = kept_events(result)[0]["session_id"]
    monkeypatch.setenv("HARNESS_DB", str(Path(result["folder"]) / "harness.db"))
    conn = db.connect()
    try:
        assert replay.check_scenario(conn, session, scenario) == result["checks"]
    finally:
        conn.close()


def test_the_checks_come_in_the_order_of_the_expectations(replay, example):
    result = run(replay, example)
    assert [c["what"] for c in result["checks"]] == [
        'ran monthly_surplus with {"income": "5000"}', "shows 2,000", "at most 0 replies withheld",
        "at most 0 corrections"]
    assert result["checks"][1] == {"what": "shows 2,000", "passed": True, "seen": "in reply 1 of 1"}


def test_a_check_that_fails_fails_the_scenario_but_is_not_an_error(replay, example):
    scenario = s3.ask_scenario(expect={"shown": ["9,999"]})
    result = run(replay, example, scenario)
    assert result["passed"] is False and result["error"] is None
    assert result["checks"] == [{"what": "shows 9,999", "passed": False, "seen": "in none of 1 replies"}]


def test_one_failing_check_among_passing_ones_fails_it(replay, example):
    scenario = s3.ask_scenario(expect={"shown": ["2,000", "9,999"], "max_withheld": 0})
    result = run(replay, example, scenario)
    assert [c["passed"] for c in result["checks"]] == [True, False, True] and result["passed"] is False


def test_the_run_prints_nothing(replay, example, capsys):
    run(replay, example)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_the_example_is_left_as_it_was(replay, example):
    folder = example(scenarios={})
    before = tree(folder)
    run(replay, folder, keep=True)
    assert tree(folder) == before


# ---- the scratch folder -----------------------------------------------------------------------------------------------

def test_the_folder_is_made_in_var_replay_of_the_working_folder(replay, example, scratch):
    result = run(replay, example, keep=True)
    folder = Path(result["folder"])
    assert folder.is_dir() and folder.resolve().parent == (ROOT / "my" / "var" / "replay").resolve()
    assert folder.name.startswith("savings-upfront-") and len(folder.name) > len("savings-upfront-")
    assert folder in set(scratch.iterdir()) or folder.resolve() in {p.resolve() for p in scratch.iterdir()}


def test_var_replay_is_made_when_it_is_not_there(replay, example, scratch):
    if scratch.exists():
        pytest.skip("my/var/replay is already there, so nothing shows whether it would be made")
    result = run(replay, example, keep=True)
    assert scratch.is_dir() and Path(result["folder"]).parent.resolve() == scratch.resolve()


def test_the_folder_is_taken_away_without_keep(replay, example, scratch):
    before = set(scratch.iterdir()) if scratch.exists() else set()
    run(replay, example)
    assert (set(scratch.iterdir()) if scratch.exists() else set()) == before


def test_keep_keeps_the_folder_with_the_brief_the_modules_and_the_database(replay, example):
    result = run(replay, example, keep=True)
    folder = Path(result["folder"])
    assert sorted(p.name for p in folder.iterdir()) == ["brief", "harness.db", "modules"]
    assert sorted(p.name for p in (folder / "modules").iterdir()) == ["monthly_surplus", "months_to_goal"]
    assert sorted(p.name for p in (folder / "brief").iterdir()) == ["domain_brief.json", "domain_brief.md"]


def test_the_brief_is_a_copy_of_the_one_of_the_example(replay, example):
    folder = example(scenarios={})
    result = run(replay, folder, keep=True)
    for name in ("domain_brief.json", "domain_brief.md"):
        assert (Path(result["folder"]) / "brief" / name).read_bytes() == (folder / "brief" / name).read_bytes()


def test_the_modules_are_copies_of_those_of_the_example(replay, example):
    folder = example(scenarios={})
    result = run(replay, folder, keep=True)
    assert tree(Path(result["folder"]) / "modules") == tree(folder / "modules")


def test_without_leaves_out_the_modules_of_those_steps(replay, example):
    scenario = s3.ask_scenario(without=["s1"], expect={"max_withheld": 0})
    result = run(replay, example, scenario, keep=True)
    assert sorted(p.name for p in (Path(result["folder"]) / "modules").iterdir()) == ["months_to_goal"]


def test_without_goes_by_the_step_of_the_spec_not_the_folder_name(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "folder_a": s3.renamed_files(h.surplus_files("s1"), "monthly_surplus"),
        "folder_b": s3.renamed_files(h.months_files("s3"), "months_to_goal")}, scenarios={})
    scenario = s3.ask_scenario(without=["s3"], expect={"max_withheld": 0})
    result = run(replay, folder, scenario, keep=True)
    assert sorted(p.name for p in (Path(result["folder"]) / "modules").iterdir()) == ["folder_a"]


def test_folders_that_start_with_an_underscore_are_not_copied(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "monthly_surplus": h.surplus_files("s1"), "months_to_goal": h.months_files("s3"),
        "_draft": s3.renamed_files(h.surplus_files("s1"), "draft_surplus")}, scenarios={})
    result = run(replay, folder, keep=True)
    assert sorted(p.name for p in (Path(result["folder"]) / "modules").iterdir()) == ["monthly_surplus", "months_to_goal"]
    assert result["error"] is None


def test_each_run_has_a_folder_of_its_own(replay, example):
    folder = example(scenarios={})
    first = run(replay, folder, keep=True)
    second = run(replay, folder, keep=True)
    assert first["folder"] != second["folder"] and Path(first["folder"]).is_dir() and Path(second["folder"]).is_dir()
    sessions = {kept_events(first)[0]["session_id"], kept_events(second)[0]["session_id"]}
    assert len(sessions) == 2


def test_the_name_of_the_folder_holds_the_example_and_the_scenario(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "moving_out", scenarios={})
    result = run(replay, folder, s3.ask_scenario("first_look"), keep=True)
    assert Path(result["folder"]).name.startswith("moving_out-first_look-")


# ---- the environment --------------------------------------------------------------------------------------------------

class Spy(ScriptedModel):
    """Notes the three settings and the working database while the model is asked."""

    def complete(self, **kwargs):
        self.seen = {name: os.environ.get(name) for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")}
        return super().complete(**kwargs)


def test_the_harness_is_pointed_at_the_folder_while_it_runs(replay, example):
    model = Spy(ask_script())
    result = run(replay, example, keep=True, model=model)
    folder = Path(result["folder"]).resolve()
    assert {name: Path(value).resolve() for name, value in model.seen.items()} == {
        "HARNESS_DB": folder / "harness.db", "HARNESS_BRIEF_DIR": folder / "brief",
        "HARNESS_MODULES_DIR": folder / "modules"}


def test_the_earlier_values_are_put_back(replay, example, monkeypatch):
    before = {name: os.environ[name] for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")}
    run(replay, example)
    assert {name: os.environ.get(name) for name in before} == before


def test_variables_that_were_unset_are_unset_again(replay, example, monkeypatch):
    for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR"):
        monkeypatch.delenv(name)
    run(replay, example)
    assert all(name not in os.environ for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR"))


def test_the_values_are_put_back_when_the_run_fails(replay, example):
    before = {name: os.environ[name] for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")}
    result = run(replay, example, script=[])
    assert result["error"] is not None
    assert {name: os.environ.get(name) for name in before} == before


def test_the_database_of_the_caller_is_not_touched(replay, example, tmp_path):
    run(replay, example)
    assert not (tmp_path / "var" / "harness.db").exists()


# ---- the session --------------------------------------------------------------------------------------------------------

def test_every_event_carries_one_new_session_id(replay, example):
    result = run(replay, example, keep=True)
    events = kept_events(result)
    assert len({e["session_id"] for e in events}) == 1 and events[0]["session_id"]


def test_the_session_starts_with_the_scenario_event(replay, example):
    scenario = s3.ask_scenario()
    result = run(replay, example, scenario, keep=True)
    first = kept_events(result)[0]
    assert first["kind"] == "replay.scenario" and first["actor"] == "harness"
    assert first["payload"] == {"example": "savings", "scenario": "upfront", "kind": "ask", "lines": scenario["lines"],
                                "expect": scenario["expect"], "without": []}
    assert list(first["payload"]) == ["example", "scenario", "kind", "lines", "expect", "without"]


def test_the_scenario_event_holds_without_when_it_is_given(replay, example):
    scenario = s3.ask_scenario(without=["s3"])
    result = run(replay, example, scenario, keep=True)
    assert kept_events(result, kind="replay.scenario")[0]["payload"]["without"] == ["s3"]


def test_the_session_ends_with_the_checked_event(replay, example):
    result = run(replay, example, keep=True)
    last = kept_events(result)[-1]
    assert last["kind"] == "replay.checked" and last["actor"] == "harness"
    assert last["payload"] == {"scenario": "upfront", "passed": True, "error": None, "checks": result["checks"]}
    assert list(last["payload"]) == ["scenario", "passed", "error", "checks"]


def test_the_checked_event_says_when_a_check_failed(replay, example):
    result = run(replay, example, s3.ask_scenario(expect={"shown": ["9,999"]}), keep=True)
    payload = kept_events(result, kind="replay.checked")[0]["payload"]
    assert payload["passed"] is False and payload["checks"] == result["checks"]


def test_one_scenario_event_and_one_checked_event(replay, example):
    result = run(replay, example, keep=True)
    kinds = [e["kind"] for e in kept_events(result)]
    assert kinds.count("replay.scenario") == 1 and kinds.count("replay.checked") == 1


def test_the_order_is_scenario_adopt_ask_checked(replay, example):
    result = run(replay, example, keep=True)
    kinds = [e["kind"] for e in kept_events(result)]
    assert kinds[0] == "replay.scenario" and kinds[-1] == "replay.checked"
    position = {kind: kinds.index(kind) for kind in ("calc.adopt_decision", "calc.module_adopted", "ask.started",
                                                      "ask.message", "ask.reply")}
    assert (position["calc.adopt_decision"] < position["calc.module_adopted"] < position["ask.started"]
            < position["ask.message"] < position["ask.reply"] < len(kinds) - 1)


def test_the_modules_are_adopted_silently_with_how_replay(replay, example):
    result = run(replay, example, keep=True)
    [decision] = kept_events(result, kind="calc.adopt_decision")
    assert decision["actor"] == "harness"
    assert decision["payload"] == {"modules": ["monthly_surplus", "months_to_goal"], "decision": "accepted", "text": "",
                                   "how": "replay"}
    adopted = kept_events(result, kind="calc.module_adopted")
    assert [(e["payload"]["module"], e["payload"]["step"], e["payload"]["how"]) for e in adopted] == [
        ("monthly_surplus", "s1", "replay"), ("months_to_goal", "s3", "replay")]
    runs = {r["id"]: r["reason"] for r in s3.sql(Path(result["folder"]) / "harness.db", "SELECT id, reason FROM test_runs")}
    assert [runs[e["payload"]["test_run_id"]] for e in adopted] == ["adopt", "adopt"]


def test_the_lines_are_not_used_up_by_the_adoption(replay, example):
    model = ScriptedModel(ask_script())
    run(replay, example, model=model)
    assert s3.ASK_QUESTION in json.dumps(model.calls[0]["messages"])


def test_the_first_line_answers_the_opening_question(replay, example):
    result = run(replay, example, keep=True)
    started = kept_events(result, kind="ask.started")
    messages = kept_events(result, kind="ask.message")
    assert len(started) == 1
    assert messages[0]["actor"] == "person" and messages[0]["payload"] == {"text": s3.ASK_QUESTION}


def test_the_lines_are_typed_in_order_and_then_it_quits(replay, example):
    lines = ["First question?", "A second one?"]
    scenario = s3.ask_scenario(lines=lines, expect={"max_withheld": 0})
    script = [h.say_text("One."), h.say_text("Two.")]
    result = run(replay, example, scenario, script=script, keep=True)
    assert [e["payload"]["text"] for e in kept_events(result, kind="ask.message")] == lines
    assert [e["payload"]["text"] for e in kept_events(result, kind="ask.reply")] == ["One.", "Two."]
    assert result["error"] is None and result["passed"] is True


def test_when_the_lines_run_out_the_conversation_ends_the_normal_way(replay, example):
    result = run(replay, example, s3.ask_scenario(lines=["Hello?"], expect={"max_withheld": 0}), script=[h.say_text("Hi.")])
    assert result["error"] is None and result["passed"] is True


def test_the_date_of_the_scenario_is_the_date_of_the_conversation(replay, example):
    model = ScriptedModel(ask_script())
    result = run(replay, example, s3.ask_scenario(today="2029-12-31"), model=model, keep=True)
    assert "[today]\n2029-12-31" in model.calls[0]["system"]
    assert kept_events(result, kind="ask.started")[0]["payload"] == {"today": "2029-12-31"}


def test_without_a_date_the_real_date_is_used(replay, example):
    from datetime import date
    before = date.today().isoformat()
    result = run(replay, example, s3.ask_scenario(today=None), keep=True)
    after = date.today().isoformat()
    assert kept_events(result, kind="ask.started")[0]["payload"]["today"] in {before, after}


def test_a_module_that_is_left_out_is_not_there_to_run(replay, example):
    scenario = s3.ask_scenario(without=["s1"], expect={"runs": [{"module": "monthly_surplus"}]})
    script = [h.run_module(), h.say_text("It is not there.")]
    result = run(replay, example, scenario, script=script, keep=True)
    assert result["passed"] is False and result["error"] is None
    assert result["checks"] == [{"what": "ran monthly_surplus", "passed": False, "seen": "no run of monthly_surplus"}]
    assert kept_events(result, kind="calc.module_adopted")[0]["payload"]["module"] == "months_to_goal"


# ---- a build scenario ------------------------------------------------------------------------------------------------

def test_a_build_scenario_builds_the_steps_that_are_left_out(replay, example):
    scenario = s3.build_scenario("rebuild_one")
    result = run(replay, example, scenario, script=h.surplus_script(), keep=True)
    assert result["error"] is None and result["passed"] is True
    assert [(c["what"], c["seen"]) for c in result["checks"]] == [
        (f"step {h.label('s1')} built", "built"), (f"step {h.label('s3')} kept", "kept")]
    modules = [p.name for p in (Path(result["folder"]) / "modules").iterdir() if not p.name.startswith("_")]
    assert sorted(modules) == ["monthly_surplus", "months_to_goal"]


def test_a_build_scenario_does_not_ask_for_the_opening_question(replay, example):
    person_events = kept_events(run(replay, example, s3.build_scenario(), script=h.surplus_script(), keep=True),
                                kind="ask.started")
    assert person_events == []


def test_a_build_session_holds_scenario_adopt_build_checked(replay, example):
    result = run(replay, example, s3.build_scenario(), script=h.surplus_script(), keep=True)
    kinds = [e["kind"] for e in kept_events(result)]
    assert kinds[0] == "replay.scenario" and kinds[-1] == "replay.checked"
    assert max(i for i, k in enumerate(kinds) if k == "calc.module_adopted") < kinds.index("calc.spec_proposed")


def test_lines_that_run_out_in_a_build_stop_it_the_normal_way(replay, example):
    scenario = s3.build_scenario(lines=["yes"], expect={"steps": {"s1": "not_built"}})
    result = run(replay, example, scenario, script=h.surplus_script())
    assert result["error"] is None
    [check] = result["checks"]
    assert check["what"] == f"step {h.label('s1')} not_built" and check["passed"] is True
    assert check["seen"].startswith("not_built (") and check["seen"].endswith(")")


def test_a_build_scenario_with_nothing_left_out_keeps_every_step(replay, example):
    scenario = s3.build_scenario(without=None, expect={"steps": {"s1": "kept", "s3": "kept"}}, lines=["/quit"])
    result = run(replay, example, scenario, script=[])
    assert result["error"] is None and result["passed"] is True


# ---- errors --------------------------------------------------------------------------------------------------------------

def test_a_module_that_is_not_adopted_is_an_error(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "monthly_surplus": {**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY},
        "months_to_goal": h.months_files("s3")})
    result = run(replay, folder, keep=True)
    assert result["error"] == f"monthly_surplus was not adopted: {s3.REASON_TESTS}"
    assert result["passed"] is False and result["checks"] == []


def test_the_first_module_that_was_not_adopted_is_the_one_named(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "monthly_surplus": {**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY},
        "months_to_goal": {**h.months_files("s3"), "module.py": "def calculate(target, monthly_saving):\n    return 0\n"}})
    result = run(replay, folder)
    assert result["error"] == f"monthly_surplus was not adopted: {s3.REASON_TESTS}"


def test_a_module_that_is_refused_for_another_reason_names_that_reason(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "monthly_surplus": h.surplus_files("s1"),
        "months_to_goal": h.months_files("s9")})
    result = run(replay, folder)
    assert result["error"] == f"months_to_goal was not adopted: {s3.ADOPT_NO_STEP.format(step='s9')}"


def test_nothing_is_asked_of_the_model_when_a_module_is_not_adopted(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "monthly_surplus": {**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY},
        "months_to_goal": h.months_files("s3")})
    model = ScriptedModel(ask_script())
    run(replay, folder, model=model)
    assert model.calls == []


def test_the_session_of_a_failed_adoption_has_the_scenario_the_refusal_and_the_checked_event(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", modules={
        "monthly_surplus": {**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY},
        "months_to_goal": h.months_files("s3")})
    result = run(replay, folder, keep=True)
    kinds = [e["kind"] for e in kept_events(result)]
    assert kinds[0] == "replay.scenario" and kinds[-1] == "replay.checked" and "ask.started" not in kinds
    checked = kept_events(result, kind="replay.checked")[0]["payload"]
    assert checked == {"scenario": "upfront", "passed": False, "error": result["error"], "checks": []}


def test_an_exception_in_the_run_is_the_error(replay, example):
    result = run(replay, example, script=[])                             # the script is used up at the first call
    assert result["passed"] is False and result["checks"] == []
    assert result["error"].startswith("ScriptExhausted: ") and "\n" not in result["error"]


def test_an_exception_message_is_made_one_line(replay, example):
    class Breaking(ScriptedModel):
        def complete(self, **kwargs):
            raise RuntimeError("first line\nsecond line")

    result = run(replay, example, model=Breaking([]))
    assert result["error"].startswith("RuntimeError: first line") and "\n" not in result["error"]
    assert "second line" in result["error"]


def test_the_checked_event_holds_the_error(replay, example):
    result = run(replay, example, script=[], keep=True)
    [checked] = kept_events(result, kind="replay.checked")
    assert checked["payload"] == {"scenario": "upfront", "passed": False, "error": result["error"], "checks": []}


def test_the_folder_is_still_taken_away_after_an_exception(replay, example, scratch):
    before = set(scratch.iterdir()) if scratch.exists() else set()
    run(replay, example, script=[])
    assert (set(scratch.iterdir()) if scratch.exists() else set()) == before


def test_the_folder_is_kept_after_an_exception_when_asked(replay, example):
    result = run(replay, example, script=[], keep=True)
    assert result["folder"] is not None and Path(result["folder"], "harness.db").exists()


def test_a_scenario_that_cannot_pass_is_not_an_exception(replay, example):
    result = run(replay, example, s3.ask_scenario(expect={"max_corrections": 0}), script=[h.say_text("Hello.")])
    assert result["error"] is None and result["passed"] is True
