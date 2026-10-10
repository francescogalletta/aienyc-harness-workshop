"""SPEC 2.5: the command line. `check`, `events` and `ui` are the base; layers add theirs by discovery."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from harness.__main__ import parser_for
from harness.layers import BASE, Command
from layer0_helpers import fake_layer

ROOT = Path(__file__).resolve().parents[2]


def run(args, env_extra):
    env = {**os.environ, **env_extra}
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)


def test_check_with_the_scripted_model_and_events_lists_it(tmp_path):
    db_path = tmp_path / "harness.db"
    script = tmp_path / "script.json"
    script.write_text(json.dumps([{"text": "pong from the script"}]), encoding="utf-8")
    env = {"HARNESS_DB": str(db_path), "HARNESS_MODEL_PROVIDER": "scripted", "HARNESS_MODEL": "stand-in",
           "HARNESS_SCRIPT": str(script)}
    result = run(["check"], env)
    assert result.returncode == 0, result.stderr
    for expected in ("scripted", "stand-in", str(db_path), "pong from the script"):
        assert expected in result.stdout, expected
    rows = sqlite3.connect(db_path).execute("SELECT kind, actor, payload FROM events").fetchall()
    assert [(kind, actor) for kind, actor, _ in rows] == [("core.check", "harness")]
    assert json.loads(rows[0][2])["reply"] == "pong from the script"
    listing = run(["events"], env)
    assert listing.returncode == 0 and listing.stdout.split()[2:] == ["core.check", "harness"]


def test_check_fails_cleanly_in_one_line_when_the_model_call_fails(tmp_path):
    script = tmp_path / "empty.json"
    script.write_text("[]", encoding="utf-8")
    result = run(["check"], {"HARNESS_DB": str(tmp_path / "harness.db"), "HARNESS_MODEL_PROVIDER": "scripted",
                             "HARNESS_SCRIPT": str(script)})
    assert result.returncode == 1
    assert len(result.stderr.strip().splitlines()) == 1 and "Traceback" not in result.stderr


def test_a_bad_layer_setting_stops_the_command_with_one_line_naming_it(tmp_path):
    result = run(["events"], {"HARNESS_DB": str(tmp_path / "harness.db"), "HARNESS_LAYERS": "9"})
    assert result.returncode == 1
    assert "HARNESS_LAYERS" in result.stderr and "Traceback" not in result.stderr


def test_the_base_commands_are_there_at_step_0(tmp_path):
    result = run(["--help"], {"HARNESS_DB": str(tmp_path / "harness.db"), "HARNESS_LAYERS": "0"})
    assert result.returncode == 0
    for command in ("check", "events", "ui"):
        assert command in result.stdout


def test_a_layer_command_is_added_and_runs():
    seen = []

    def arguments(parser):
        parser.add_argument("question", nargs="*")

    def ask(args):
        seen.append(args.question)
        return 7

    layer = fake_layer(1, commands={"fake_ask": Command(help="a made-up command", run=ask, arguments=arguments)})
    args = parser_for([BASE, layer]).parse_args(["fake_ask", "how", "much"])
    assert args.run(args) == 7 and seen == [["how", "much"]]
