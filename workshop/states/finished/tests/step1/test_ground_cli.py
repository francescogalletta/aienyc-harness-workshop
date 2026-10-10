"""SPEC 4.5 and 4.6: `python -m harness ground` runs the interview in the terminal."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from step1_helpers import PLAN, make_brief

ROOT = Path(__file__).resolve().parents[2]


def run(args, env_extra, typed=""):
    env = {**os.environ, **env_extra}
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=ROOT, env=env, input=typed,
                          capture_output=True, text=True)


def environment(tmp_path, reference_file, script):
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script), encoding="utf-8")
    return {"HARNESS_DB": str(tmp_path / "var" / "harness.db"), "HARNESS_BRIEF_DIR": str(tmp_path / "brief"),
            "HARNESS_MODEL_PROVIDER": "scripted", "HARNESS_SCRIPT": str(script_path),
            "HARNESS_RESEARCHER": "reference", "HARNESS_REFERENCE": str(reference_file)}


def test_ground_from_start_to_saved_brief(tmp_path, reference_file):
    env = environment(tmp_path, reference_file, [
        PLAN,                                                     # the research plan comes first
        {"tool_calls": [{"name": "look_up", "arguments": {"query": "account balance"}}]},
        {"text": "Do you want a forecast, or today's balance?"},
        {"tool_calls": [{"name": "write_brief", "arguments": make_brief()}]},
    ])
    result = run(["ground"], env, typed="I want to stay on top of my money.\nA forecast.\n/accept\n")
    assert result.returncode == 0, result.stderr
    assert "(reading up on: cash flow forecast)" in result.stdout
    assert "(looking up: account balance)" in result.stdout
    assert "Type /accept to accept this brief" in result.stdout
    assert "What do you want this harness to help you with?" in result.stdout
    assert "Do you want a forecast, or today's balance?" in result.stdout
    assert "PROPOSED BRIEF" in result.stdout and "Brief saved (confirmed)" in result.stdout

    brief = json.loads((tmp_path / "brief" / "domain_brief.json").read_text(encoding="utf-8"))
    assert brief["meta"]["status"] == "confirmed"
    assert (tmp_path / "brief" / "domain_brief.md").exists()

    rows = sqlite3.connect(tmp_path / "var" / "harness.db").execute(
        "SELECT kind, actor, payload FROM events ORDER BY id").fetchall()
    assert rows[0][:2] == ("grounding.answer", "person")
    assert json.loads(rows[0][2]) == {"text": "I want to stay on top of my money."}
    assert rows[1][:2] == ("grounding.research_plan", "agent")
    assert json.loads(rows[1][2]) == {"terms": ["cash flow forecast"]}
    assert rows[-1][0] == "grounding.brief_written"

    # The desk remembered what it found, in the database.
    remembered = sqlite3.connect(tmp_path / "var" / "harness.db").execute(
        "SELECT key, origin FROM lookups ORDER BY key").fetchall()
    assert remembered == [("account balance", "reference"), ("cash flow forecast", "reference")]


def test_stopping_early_and_resuming(tmp_path, reference_file):
    env = environment(tmp_path, reference_file, [{"text": "nothing to plan"}, {"text": "First question?"}])
    stopped = run(["ground"], env, typed="I want help.\n")        # input ends before the first answer
    assert stopped.returncode == 0 and "--resume" in stopped.stdout
    assert (tmp_path / "var" / "grounding_state.json").exists()

    env = environment(tmp_path, reference_file, [
        {"tool_calls": [{"name": "look_up", "arguments": {"query": "cash flow forecast"}}]},
        {"tool_calls": [{"name": "write_brief", "arguments": make_brief()}]},
    ])
    resumed = run(["ground", "--resume"], env, typed="My answer.\nyes\n")
    assert resumed.returncode == 0, resumed.stderr
    assert "First question?" in resumed.stdout and "Brief saved (confirmed)" in resumed.stdout
    assert not (tmp_path / "var" / "grounding_state.json").exists()


def test_resume_with_nothing_to_resume(tmp_path, reference_file):
    result = run(["ground", "--resume"], environment(tmp_path, reference_file, []))
    assert result.returncode == 1 and "no interview to resume" in result.stderr


def test_a_failing_model_stops_cleanly_and_can_be_resumed(tmp_path, reference_file):
    env = environment(tmp_path, reference_file, [])               # the first model call runs out of script
    result = run(["ground"], env, typed="I want help.\n")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr and "--resume" in result.stderr
    assert (tmp_path / "var" / "grounding_state.json").exists()
