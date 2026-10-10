"""SPEC 4.6: module folders on disk are adopted on load, without asking."""
import json
import shutil
from pathlib import Path

from harness.calc import builder, gate, registry
from harness.grounding.brief import step_fingerprint
from layer2_helpers import SETTLE, TOTAL_CODE, TOTAL_EXAMPLES, TOTAL_SPEC, events, step_of, write_plan

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def seeded(monkeypatch, tmp_path, name="wedding"):
    """A copy of a seeded example's plan and modules, as example mode makes one."""
    for part in ("brief", "modules"):
        shutil.copytree(EXAMPLES / name / part, tmp_path / name / part)
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / name / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / name / "modules"))
    return json.loads((tmp_path / name / "brief" / "domain_brief.json").read_text())


def test_the_seeded_modules_are_adopted_on_load_and_run_through_the_gate(monkeypatch, tmp_path, open_session):
    brief = seeded(monkeypatch, tmp_path)
    session = open_session([])
    state = session.state()
    calculation = [step for step in state["steps"] if step["kind"] == "calculation"]
    assert [step["id"] for step in calculation] == ["s1", "s2", "s3", "s5", "s6", "added_1"]
    assert all(step["build"]["status"] == "built" and step["line"]["kind"] == "tested" for step in calculation)
    assert step_of(state, "added_1")["in_plan"] is False
    assert all(each["checked_by"] == "second_pass" for each in step_of(state, "s1")["build"]["example_list"])
    adopted = events(session, "build.adopted")
    assert len(adopted) == 6 and {each["outcome"] for each in adopted} == {"adopted"}
    module = registry.get_module(session.conn, "monthly_surplus")
    assert module["step_fingerprint"] == step_fingerprint(brief, "s3")
    golden = json.loads((tmp_path / "wedding" / "modules" / "monthly_surplus" / "golden.json").read_text())[0]
    run = gate.call(session.conn, "monthly_surplus", golden["inputs"], assumptions=[], expected="a number",
                    session_id="t")
    assert run["output"] == golden["expected"]

    again = open_session([])                               # nothing left to adopt the next time
    assert again.state()["lanes"]["main"] == "idle" and len(events(again, "build.adopted")) == 6


def test_a_folder_whose_tests_fail_here_leaves_its_step_not_built(monkeypatch, tmp_path, open_session, build):
    seeded(monkeypatch, tmp_path, "moving")
    broken = tmp_path / "moving" / "modules" / "move_upfront_cost" / "module.py"
    broken.write_text(broken.read_text() + "\n\ndef calculate(**anything):\n    return '0'\n")
    session = open_session([])
    found = step_of(session.state(), "m1")["build"]
    assert (found["status"], found["reason"]) == ("not_built", builder.REASON_TESTS)
    assert registry.get_module(session.conn, "move_upfront_cost") is None
    assert step_of(session.state(), "m2")["build"]["status"] == "built"
    build(session)                                         # the model has nothing to say: m1 stays not built
    assert events(session, "build.finished")[-1]["steps"] == {"m1": "not_built", "m2": "kept", "m3": "kept"}


def test_folders_are_adopted_when_a_plan_is_accepted(tmp_path, open_session):
    folder = tmp_path / "modules" / "total"
    folder.mkdir(parents=True)
    (folder / "spec.json").write_text(json.dumps({**TOTAL_SPEC, "step_id": "c1"}))
    (folder / "golden.json").write_text(json.dumps([{**each, "checked_by": "second_pass"} for each in TOTAL_EXAMPLES]))
    (folder / "module.py").write_text(TOTAL_CODE[0])
    (folder / "tests.py").write_text(TOTAL_CODE[1])
    session = open_session([])
    assert registry.get_module(session.conn, "total") is None          # no plan yet: nothing to adopt
    write_plan(tmp_path / "brief")
    session.queue("main", lambda work: work.hook("plan_accepted", work), what="interview")
    state = session.settle(SETTLE)
    assert step_of(state, "c1")["build"]["status"] == "built" and step_of(state, "c2")["build"]["status"] == "none"
