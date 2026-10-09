"""SPEC 4.7: `python -m harness ui` serves the interview on this machine until interrupted."""
import os
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform == "win32", reason="the test stops the command with an interrupt signal")
def test_ui_starts_serves_and_stops(tmp_path, reference_file):
    env = {**os.environ, "HARNESS_DB": str(tmp_path / "var" / "harness.db"),
           "HARNESS_BRIEF_DIR": str(tmp_path / "brief"), "HARNESS_MODEL_PROVIDER": "scripted",
           "HARNESS_RESEARCHER": "reference", "HARNESS_REFERENCE": str(reference_file)}
    # Port 0 asks for any free port. --no-browser: a test must not open a window.
    process = subprocess.Popen([sys.executable, "-m", "harness", "ui", "--port", "0", "--no-browser"],
                               cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        first_line = process.stdout.readline()
        address = re.search(r"http://127\.0\.0\.1:\d+/", first_line)
        assert address, first_line + process.stderr.read()

        # The interview is behind the token, which only the page is given.
        with pytest.raises(urllib.error.HTTPError) as refused:
            direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # never through a proxy
            direct.open(address.group() + "api/state", timeout=5)
        assert refused.value.code == 403

        process.send_signal(signal.SIGINT)
        _out, err = process.communicate(timeout=10)
    finally:
        process.kill()
    assert process.returncode == 0 and "Traceback" not in err
    assert (tmp_path / "var" / "harness.db").exists()
