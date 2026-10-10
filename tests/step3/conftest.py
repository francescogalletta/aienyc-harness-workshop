import importlib
import json
import shutil
from pathlib import Path

import pytest

from harness import db
import step3_helpers as s3
from step3_helpers import ROOT, make_example, start_server, stop_server

SETTINGS = ("HARNESS_DB", "HARNESS_MODEL_PROVIDER", "HARNESS_MODEL", "HARNESS_SCRIPT", "HARNESS_RESEARCHER",
            "HARNESS_REFERENCE", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Every test starts with its own database, modules folder, brief folder and scripted model.

    `HARNESS_EXAMPLE` is removed too, so that a shell that has it set cannot change a default.
    """
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "var" / "harness.db"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.setenv("HARNESS_SCRIPT", str(tmp_path / "script.json"))
    return tmp_path


@pytest.fixture
def modules_dir(tmp_path):
    return tmp_path / "modules"


@pytest.fixture
def conn():
    """A migrated connection to the test database."""
    connection = db.connect()
    db.migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def brief():
    return s3.h.make_brief()


@pytest.fixture
def write_script(tmp_path):
    def write(entries):
        (tmp_path / "script.json").write_text(json.dumps(entries), encoding="utf-8")
    return write


@pytest.fixture
def save_confirmed_brief(tmp_path):
    def save(brief=None, status="confirmed"):
        return s3.save_the_brief(tmp_path / "brief", brief, status)
    return save


# The modules of step 3 are imported when a test asks for them, so that a file still to be written fails the
# tests that need it and not the collection of the whole folder.
def _module(fixture_name, module_name):
    @pytest.fixture(name=fixture_name)
    def fixture():
        return importlib.import_module(module_name)
    return fixture


adopt_module = _module("adopt", "harness.calc.adopt")
agent_module = _module("agent", "harness.calc.agent")
builder_module = _module("builder", "harness.calc.builder")
registry_module = _module("registry", "harness.calc.registry")
gate_module = _module("gate", "harness.calc.gate")
added_module = _module("added", "harness.calc.added")
notes_module = _module("notes", "harness.calc.notes")
provenance_module = _module("provenance", "harness.calc.provenance")
replay_module = _module("replay", "harness.replay")
evidence_module = _module("evidence", "harness.ui.evidence")


@pytest.fixture
def adopt_folders(tmp_path):
    """Write the two example module folders (steps s1 and s3) into the modules folder, unregistered."""
    s3.surplus_folder(tmp_path / "modules")
    s3.months_folder(tmp_path / "modules")


@pytest.fixture
def person():
    def make(*answers):
        return s3.Person(*answers)
    return make


# ---- the replay scratch folders -----------------------------------------------------------------------

@pytest.fixture
def replay_scratch(monkeypatch):
    """Replay works in my/var/replay of the working folder. Run from the repository root, and take away what the
    test leaves behind (the folders it kept, and my/var/replay itself when it made it)."""
    monkeypatch.chdir(ROOT)
    folder = ROOT / "my" / "var" / "replay"
    existed = folder.exists()
    before = set(folder.iterdir()) if existed else set()
    yield folder
    if folder.exists():
        for path in set(folder.iterdir()) - before:
            shutil.rmtree(path, ignore_errors=True)
        if not existed:
            try:
                folder.rmdir()
            except OSError:
                pass


@pytest.fixture
def example(tmp_path):
    """Call it to write an example folder (two modules, one ask scenario unless told otherwise) under the test's folder."""
    def make(**options):
        return make_example(tmp_path / "examples", **options)
    return make


# ---- the recorded story ----------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def world_template(tmp_path_factory):
    """The story of `build_world`, recorded once for the whole run and copied for each test."""
    root = tmp_path_factory.mktemp("story")
    s3.build_world(root)
    return root


@pytest.fixture
def world(world_template, tmp_path, monkeypatch):
    """A copy of the story in the test's own folder; the environment points at the copy."""
    return s3.copy_world(world_template, tmp_path / "world", monkeypatch)


@pytest.fixture
def served(tmp_path):
    """Start the evidence server (no interview session) over whatever database the environment names.

    Returns `send(method, path, body=None, token=<the server's>, raw=None)` -> Reply, with `.server`.
    """
    started = []

    def start(session=None, **options):
        server, thread, send = start_server(session, tmp_path=tmp_path, **options)
        started.append((server, thread))
        return send

    yield start
    for server, thread in started:
        stop_server(server, thread)


@pytest.fixture
def api(world, served):
    """GET and POST helpers over a server on the story: `api.get(path)` -> (status, body), `api.post(path, body)`."""
    send = served()

    class Api:
        server = send.server
        sender = staticmethod(send)

        @staticmethod
        def get(path, **options):
            reply = send("GET", path, **options)
            return reply.status, reply.json()

        @staticmethod
        def post(path, body=None, **options):
            reply = send("POST", path, {} if body is None else body, **options)
            return reply.status, reply.json()

    Api.world = world
    return Api
