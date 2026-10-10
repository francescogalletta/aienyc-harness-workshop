"""SPEC 7.7: `python -m harness work` and the second line of `ui`, run as programs on a free port."""
import queue
import re
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

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


def test_it_serves_the_evidence_page_with_the_token(running):
    from harness.ui.server import WORK_PAGE
    command, port = start_work(running)
    status, headers, text = get(port, "/work")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    token = token_of(text, WORK_PAGE)
    assert token and "__HARNESS_TOKEN__" not in text
    assert get(port, "/api/work/summary")[0] == 403
    assert get(port, "/api/work/summary", token)[0] == 200


# ---- ui -----------------------------------------------------------------------------------------------------------------------
