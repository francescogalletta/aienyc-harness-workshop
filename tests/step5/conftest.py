import importlib
import json
import shutil

import pytest

from harness import db
import step5_helpers as s5
from step5_helpers import DAY, ROOT, SESSION, Model, h, s3, s4

SETTINGS = ("HARNESS_DB", "HARNESS_MODEL_PROVIDER", "HARNESS_MODEL", "HARNESS_SCRIPT", "HARNESS_RESEARCHER",
            "HARNESS_REFERENCE", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Every test starts with its own database, modules folder, brief folder and scripted model."""
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
    return h.make_brief()


@pytest.fixture
def files(tmp_path):
    """Write a file into a folder of the test: `files("name.csv", text_or_bytes)` -> its path."""
    def write(name, content, folder="files"):
        return s5.write(tmp_path / folder, name, content)
    return write


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


# The modules of step 5 are imported when a test asks for them, so that a file still to be written fails the tests
# that need it and not the collection of the whole folder.
def _module(fixture_name, module_name):
    @pytest.fixture(name=fixture_name)
    def fixture():
        return importlib.import_module(module_name)
    return fixture


adapter = _module("adapter", "harness.sources.adapter")
sources = _module("sources", "harness.sources")
summaries = _module("summaries", "harness.sources.summaries")
findings = _module("findings", "harness.calc.findings")
verifier = _module("verifier", "harness.calc.verifier")
decisions = _module("decisions", "harness.calc.decisions")
agent = _module("agent", "harness.calc.agent")
provenance = _module("provenance", "harness.calc.provenance")
replay = _module("replay", "harness.replay")
evidence = _module("evidence", "harness.ui.evidence")


@pytest.fixture
def installed(conn):
    """The two example modules, registered for steps s1 and s3."""
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


@pytest.fixture
def example_loaded(adapter, conn):
    """The three real account files of data/example/ loaded (bank files money out negative, card positive)."""
    return s5.load_example(adapter, conn)


@pytest.fixture
def check_verifier(verifier, conn, brief):
    """Run one check: `check(script, message, **options)` -> (findings, person, model). `say` goes to the person's log."""
    def run(script, message=s5.MESSAGE, *, session_id=SESSION, today=s5.TODAY, brief=brief, model=None):
        person = h.Person()
        model = model or Model(script, person)
        found = verifier.verify(model=model, conn=conn, brief=brief, message=message, session_id=session_id,
                                today=today, say=person.say)
        return found, person, model
    return run


@pytest.fixture
def talk(agent, conn, brief, installed):
    """Run the agent with verification on, a scripted model and a person who answers from a list.

    `talk(script, answers, question=..., verify=True)` -> (model, person). The person's log also holds ("call", role)
    each time a model is called (the roles are `verifier`, `analyst` and `aside`).
    """
    def run(script, answers=("/quit",), *, question=s5.MESSAGE, verify=True, desk=None, **options):
        person = h.Person(*answers)
        model = Model(script, person)
        options = {"today": DAY, "session_id": SESSION, "brief": brief, **options}
        if desk is not None:
            options["desk"] = desk
        agent.run_agent(model=model, conn=conn, ask=person.ask, say=person.say, question=question, verify=verify,
                        **options)
        return model, person
    return run


@pytest.fixture
def replay_scratch(monkeypatch):
    """Replay works in var/replay of the working folder. Run from the repository root, and take away what the test
    leaves behind."""
    monkeypatch.chdir(ROOT)
    folder = ROOT / "var" / "replay"
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
    """Call it to write an example folder (two modules, one ask scenario unless told otherwise)."""
    def make(**options):
        return s3.make_example(tmp_path / "examples", **options)
    return make


@pytest.fixture
def served(tmp_path):
    """Start the evidence server over whatever database the environment names: `start()` -> send."""
    started = []

    def start(session=None, **options):
        server, thread, send = s3.start_server(session, tmp_path=tmp_path, **options)
        started.append((server, thread))
        return send

    yield start
    for server, thread in started:
        s3.stop_server(server, thread)


@pytest.fixture
def api(served, conn):
    send = served()

    class Api:
        sender = staticmethod(send)

        @staticmethod
        def get(path, **options):
            reply = send("GET", path, **options)
            return reply.status, reply.json()

    return Api
