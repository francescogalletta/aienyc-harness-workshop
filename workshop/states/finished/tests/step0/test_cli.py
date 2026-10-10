"""SPEC 3.6: `python -m harness check` proves the setup end to end."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(args, env_extra):
    env = {**os.environ, **env_extra}
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True)


def test_check_with_the_scripted_model(tmp_path):
    db_path = tmp_path / "harness.db"
    script = tmp_path / "script.json"
    script.write_text(json.dumps([{"text": "pong from the script"}]), encoding="utf-8")
    env = {"HARNESS_DB": str(db_path), "HARNESS_MODEL_PROVIDER": "scripted",
           "HARNESS_MODEL": "stand-in", "HARNESS_SCRIPT": str(script)}

    result = run(["check"], env)
    assert result.returncode == 0, result.stderr
    for expected in ("scripted", "stand-in", str(db_path), "pong from the script"):
        assert expected in result.stdout, expected
    assert result.stdout.strip().splitlines()[-1] == (
        "Setup works: the model replied and the check was saved as event 1.")

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT kind, actor, payload FROM events").fetchall()
    assert len(rows) == 1
    kind, actor, payload = rows[0]
    assert (kind, actor) == ("harness.check", "harness")
    payload = json.loads(payload)
    assert payload["provider"] == "scripted"
    assert payload["model"] == "stand-in"
    assert payload["reply"] == "pong from the script"
    assert payload["migrations"][0] == "0001_init.sql"

    listing = run(["events"], env)
    assert listing.returncode == 0, listing.stderr
    fields = listing.stdout.split()
    assert fields[0] == "1" and fields[2:] == ["harness.check", "harness"]

    # A second run applies no new migration but still records all of them,
    # under a different session id.
    assert run(["check"], env).returncode == 0
    second = conn.execute("SELECT session_id, payload FROM events ORDER BY id").fetchall()
    assert len(second) == 2
    assert json.loads(second[1][1])["migrations"] == payload["migrations"]
    assert second[0][0] != second[1][0]


def test_check_fails_cleanly_when_the_model_call_fails(tmp_path):
    db_path = tmp_path / "harness.db"
    script = tmp_path / "empty.json"
    script.write_text("[]", encoding="utf-8")   # the first call runs out of script
    env = {"HARNESS_DB": str(db_path), "HARNESS_MODEL_PROVIDER": "scripted",
           "HARNESS_SCRIPT": str(script)}
    result = run(["check"], env)
    assert result.returncode == 1
    assert result.stderr.strip() and "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
