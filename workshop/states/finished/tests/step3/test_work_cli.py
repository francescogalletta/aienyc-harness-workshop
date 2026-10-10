"""SPEC 7.7: `python -m harness work` and the second line of `ui`, run as programs on a free port."""
import os
import queue
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

import step3_helpers as s3
from step3_helpers import DIRECT, ROOT, cli_env

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the tests stop the command with an interrupt signal")

ADDRESS = re.compile(r"http://127\.0\.0\.1:(\d+)/")
EVIDENCE_LINE = re.compile(r"^The evidence page is at http://127\.0\.0\.1:(\d+)/work$")
HOLD_LINE = "Press Ctrl+C to stop."


class Running:
    """A command that keeps running until it is interrupted. Lines of standard output are read as they come."""

    def __init__(self, args, env, cwd=ROOT):
        self.process = subprocess.Popen([sys.executable, "-m", "harness", *args], cwd=cwd, env=env, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.lines = queue.Queue()
        self.seen = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line.rstrip("\n"))
        self.lines.put(None)

    def line(self, timeout=30):
        text = self.lines.get(timeout=timeout)
        if text is not None:
            self.seen.append(text)
        return text

    def stop(self):
        self.process.send_signal(signal.SIGINT)
        out, err = self.process.communicate(timeout=20)
        rest = []
        while True:
            try:
                item = self.lines.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                rest.append(item)
        return self.seen + rest + out.splitlines(), err

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.communicate()


@pytest.fixture
def running():
    started = []

    def start(args, **env):
        command = Running(args, cli_env(**env))
        started.append(command)
        return command

    yield start
    for command in started:
        command.kill()


def get(port, path, token=None, method="GET", body=None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, data=body)
    if token:
        request.add_header("X-Harness-Token", token)
    try:
        with DIRECT.open(request, timeout=20) as reply:
            return reply.status, reply.headers, reply.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode("utf-8")


def token_of(page_text, page_file):
    """The token the server put into the page, found by comparing with the file it came from."""
    before, after = page_file.read_text(encoding="utf-8").split("__HARNESS_TOKEN__")
    assert page_text.startswith(before) and page_text.endswith(after)
    return page_text[len(before):len(page_text) - len(after)]


def start_work(running, *extra, **env):
    command = running(["work", "--port", "0", "--no-browser", *extra], **env)
    first = command.line()
    match = EVIDENCE_LINE.match(first or "")
    assert match, (first, command.process.poll())
    return command, int(match.group(1))


# ---- work -------------------------------------------------------------------------------------------------------------------

def test_work_says_where_the_page_is_and_how_to_stop(running):
    command, port = start_work(running)
    assert command.line() == HOLD_LINE
    assert port > 0


def test_interrupted_it_says_stopped_and_exits_0(running):
    command, _ = start_work(running)
    assert command.line() == HOLD_LINE
    lines, err = command.stop()
    assert command.process.returncode == 0 and lines[-1] == "Stopped." and "Traceback" not in err
    assert lines[:2] == [command.seen[0], HOLD_LINE]


def test_it_serves_the_evidence_page_with_the_token(running):
    from harness.ui.server import WORK_PAGE
    command, port = start_work(running)
    status, headers, text = get(port, "/work")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    token = token_of(text, WORK_PAGE)
    assert token and "__HARNESS_TOKEN__" not in text
    assert get(port, "/api/work/summary")[0] == 403
    assert get(port, "/api/work/summary", token)[0] == 200


def test_it_runs_migrate_so_that_an_empty_database_can_be_read(running, tmp_path):
    from harness.ui.server import WORK_PAGE
    command, port = start_work(running)
    token = token_of(get(port, "/work")[2], WORK_PAGE)
    assert (tmp_path / "var" / "harness.db").exists()
    status, _, text = get(port, "/api/work/summary", token)
    import json
    body = json.loads(text)
    assert status == 200 and body["interview"] is False and body["database"] == str(tmp_path / "var" / "harness.db")
    assert body["conversations"] == [] and body["runs"] == [] and body["modules"] == [] and body["brief"] is None
    assert get(port, "/api/work/events", token)[0] == 200


def test_it_shows_the_story_of_the_database_it_is_pointed_at(running, world):
    import json
    from harness.ui.server import WORK_PAGE
    command, port = start_work(running)
    token = token_of(get(port, "/work")[2], WORK_PAGE)
    body = json.loads(get(port, "/api/work/summary", token)[2])
    assert [c["session_id"] for c in body["conversations"]] == ["replay-1", "chat-2", "chat-1"]
    assert [m["name"] for m in body["modules"]] == ["monthly_surplus", "months_to_goal", "yearly_cost"]
    assert body["brief"]["status"] == "confirmed"


def test_it_has_no_interview_so_the_root_goes_to_the_evidence_page(running):
    command, port = start_work(running)
    status, headers, _ = get(port, "/")
    assert status == 303 and headers["Location"] == "/work"


def test_it_never_calls_a_model_even_when_none_could_be_made(running, tmp_path):
    command, port = start_work(running, HARNESS_MODEL_PROVIDER="anthropic", ANTHROPIC_API_KEY=None, HARNESS_SCRIPT=None)
    assert command.line() == HOLD_LINE and command.process.poll() is None
    assert get(port, "/api/state", "x")[0] in (403, 404)


def test_a_port_that_cannot_be_used(running):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        command = running(["work", "--port", str(port), "--no-browser"])
        out, err = command.process.communicate(timeout=30)
    finally:
        blocker.close()
    assert command.process.returncode == 1 and out == ""
    assert err.splitlines()[0].startswith(f"could not start on port {port}: ")
    assert len(err.splitlines()[0]) > len(f"could not start on port {port}: ") and "Traceback" not in err


def test_the_page_is_opened_in_the_browser_unless_told_not_to(running, tmp_path):
    recorder = tmp_path / "browser.sh"
    opened = tmp_path / "opened.txt"
    recorder.write_text(f'#!/bin/sh\necho "$1" >> {opened}\n', encoding="utf-8")
    recorder.chmod(recorder.stat().st_mode | stat.S_IEXEC)
    command = running(["work", "--port", "0"], BROWSER=recorder, DISPLAY=None)
    match = EVIDENCE_LINE.match(command.line() or "")
    assert match
    for _ in range(100):
        if opened.exists() and opened.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    assert opened.read_text(encoding="utf-8").strip() == f"http://127.0.0.1:{match.group(1)}/work"


def test_no_browser_means_no_browser(running, tmp_path):
    recorder = tmp_path / "browser.sh"
    opened = tmp_path / "opened.txt"
    recorder.write_text(f'#!/bin/sh\necho "$1" >> {opened}\n', encoding="utf-8")
    recorder.chmod(recorder.stat().st_mode | stat.S_IEXEC)
    command, _ = start_work(running, BROWSER=recorder)
    assert command.line() == HOLD_LINE
    time.sleep(1.5)
    assert not opened.exists()


def test_it_writes_nothing_by_itself(running, world):
    before = world.counts()
    command, port = start_work(running)
    command.line()
    from harness.ui.server import WORK_PAGE
    token = token_of(get(port, "/work")[2], WORK_PAGE)
    for path in ("/api/work/summary", "/api/work/events", "/api/work/run?id=1", "/api/work/module?name=monthly_surplus",
                 "/api/work/conversation?session=chat-1"):
        assert get(port, path, token)[0] == 200
    command.stop()
    assert world.counts() == before


def test_the_test_button_works_through_the_program(running, world):
    import json
    from harness.ui.server import WORK_PAGE
    command, port = start_work(running)
    token = token_of(get(port, "/work")[2], WORK_PAGE)
    status, _, text = get(port, "/api/work/test", token, method="POST", body=b'{"module": "monthly_surplus"}')
    body = json.loads(text)
    assert status == 200 and body["test_run"]["reason"] == "status" and body["test_run"]["passed"] is True
    command.stop()
    rows = world.sql("SELECT reason FROM test_runs ORDER BY id DESC LIMIT 1")
    assert rows == [{"reason": "status"}]
    last = world.events()[-1]
    assert last["kind"] == "calc.tests_run" and re.fullmatch(r"[0-9a-f]{32}", last["session_id"])


# ---- ui -----------------------------------------------------------------------------------------------------------------------

def test_ui_serves_both_pages_and_says_where_the_work_page_is(running):
    from harness.ui.server import WORK_PAGE
    command = running(["ui", "--port", "0", "--no-browser"])
    first = command.line()
    address = ADDRESS.search(first or "")
    assert address, first
    second = command.line()
    assert second == f"What the harness did is at {address.group()}work"
    port = int(address.group(1))
    status, _, interview = get(port, "/")
    assert status == 200 and "Show your work" in interview
    status, _, evidence = get(port, "/work")
    assert status == 200
    token = token_of(evidence, WORK_PAGE)
    import json
    summary = json.loads(get(port, "/api/work/summary", token)[2])
    assert summary["interview"] is True
    command.stop()
    assert command.process.returncode == 0


def test_ui_starts_the_same_way_as_before_on_its_first_line(running):
    command = running(["ui", "--port", "0", "--no-browser"])
    first = command.line()
    assert ADDRESS.search(first or "") and "What the harness did" not in first
