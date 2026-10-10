import importlib
import json
import shutil

import pytest

from harness import db
import step4_helpers as s4
from step4_helpers import DAY, QUESTION, ROOT, SESSION, Model, h, s3

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
def write_script(tmp_path):
    def write(entries):
        (tmp_path / "script.json").write_text(json.dumps(entries), encoding="utf-8")
    return write


@pytest.fixture
def save_confirmed_brief(tmp_path):
    def save(brief=None, status="confirmed"):
        return s3.save_the_brief(tmp_path / "brief", brief, status)
    return save


# The modules of step 4 are imported when a test asks for them, so that a file still to be written fails the
# tests that need it and not the collection of the whole folder.
def _module(fixture_name, module_name):
    @pytest.fixture(name=fixture_name)
    def fixture():
        return importlib.import_module(module_name)
    return fixture


decisions = _module("decisions", "harness.calc.decisions")
aside = _module("aside", "harness.calc.aside")
agent = _module("agent", "harness.calc.agent")
builder = _module("builder", "harness.calc.builder")
registry = _module("registry", "harness.calc.registry")
gate = _module("gate", "harness.calc.gate")
notes = _module("notes", "harness.calc.notes")
adopt = _module("adopt", "harness.calc.adopt")
replay = _module("replay", "harness.replay")
evidence = _module("evidence", "harness.ui.evidence")


@pytest.fixture
def installed(conn):
    """The two example modules, registered for steps s1 and s3."""
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


@pytest.fixture
def months_only(conn):
    """Only the months module is registered, so that step s1 has no working module."""
    h.install_months(conn, "s3")


@pytest.fixture
def talk(agent, conn, brief):
    """Run the agent with a scripted model and a person who answers from a list (then must be done).

    The person's log also holds ("call", role) each time a model is called, whoever calls it, and the role of a
    side conversation is `aside`. Returns (model, person).
    """
    def run(script, answers=("/quit",), *, question=QUESTION, desk=None, **options):
        person = h.Person(*answers)
        model = Model(script, person)
        options = {"today": DAY, "session_id": SESSION, "brief": brief, **options}
        if desk is not None:
            options["desk"] = desk
        agent.run_agent(model=model, conn=conn, ask=person.ask, say=person.say, question=question, **options)
        return model, person
    return run


@pytest.fixture
def ask_agent(talk, installed):
    """`talk`, with both example modules registered."""
    return talk


@pytest.fixture
def side_talk(aside, conn, brief):
    """An `Asides` object over a scripted model and a recording person: `make(script, answers, **options)`.

    Returns (asides, person, model). The model also logs its calls in the person's log.
    """
    def make(script, answers=(), *, desk=None, session_id=SESSION, today=s4.TODAY, brief=brief):
        person = h.Person(*answers)
        model = Model(script, person)
        asides = aside.Asides(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say,
                              session_id=session_id, today=today, desk=desk)
        return asides, person, model
    return make


@pytest.fixture
def one_aside(aside, conn, brief):
    """`run_aside` with a recording person and a scripted model: `go(script, answers, **options)` ->
    ((how, carried), person, model)."""
    def go(script, answers=(), *, first="What does this mean?", looking_at=None, aside_number=1, desk=None,
           session_id=SESSION, today=s4.TODAY, brief=brief):
        person = h.Person(*answers)
        model = Model(script, person)
        outcome = aside.run_aside(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say,
                                  session_id=session_id, aside=aside_number, looking_at=looking_at, first=first,
                                  today=today, desk=desk)
        return outcome, person, model
    return go


# ---- the replay scratch folders ----------------------------------------------------------------------------

@pytest.fixture
def replay_scratch(monkeypatch):
    """Replay works in my/var/replay of the working folder. Run from the repository root, and take away what the
    test leaves behind."""
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
    """Call it to write an example folder (two modules, one ask scenario unless told otherwise)."""
    def make(**options):
        return s3.make_example(tmp_path / "examples", **options)
    return make


# ---- the evidence server ------------------------------------------------------------------------------------

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
def api(served):
    send = served()

    class Api:
        sender = staticmethod(send)

        @staticmethod
        def get(path, **options):
            reply = send("GET", path, **options)
            return reply.status, reply.json()

    return Api
