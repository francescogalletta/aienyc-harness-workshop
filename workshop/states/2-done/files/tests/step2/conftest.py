import importlib
import json

import pytest

from harness import db
from harness.grounding import save_brief
import step2_helpers as h
from step2_helpers import DAY, QUESTION, SESSION, Person, TracingModel, make_brief

SETTINGS = ("HARNESS_DB", "HARNESS_MODEL_PROVIDER", "HARNESS_MODEL", "HARNESS_SCRIPT",
            "HARNESS_RESEARCHER", "HARNESS_REFERENCE", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Every test starts with its own database, modules folder, brief folder and scripted model.

    The script file is not written until a test (or `write_script`) asks for it.
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
    """The brief as `load_brief` returns it (no `meta`)."""
    return make_brief()


@pytest.fixture
def write_script(tmp_path):
    """Write the entries the `scripted` provider will replay (for the command line)."""
    def write(entries):
        (tmp_path / "script.json").write_text(json.dumps(entries), encoding="utf-8")
    return write


@pytest.fixture
def save_confirmed_brief(tmp_path):
    """Save a brief to the brief folder the way step 1 does, `confirmed` unless told otherwise."""
    def save(brief=None, status="confirmed"):
        return save_brief(brief or make_brief(), tmp_path / "brief", {"status": status, "session_id": "s", "lookups": []})
    return save


# The new modules of step 2 are imported when a test asks for them, so that a file still to be
# written fails the tests that need it and not the collection of the whole folder.
@pytest.fixture
def registry():
    return importlib.import_module("harness.calc.registry")


@pytest.fixture
def gate():
    return importlib.import_module("harness.calc.gate")


@pytest.fixture
def builder():
    return importlib.import_module("harness.calc.builder")


@pytest.fixture
def notes():
    return importlib.import_module("harness.calc.notes")


@pytest.fixture
def agent():
    return importlib.import_module("harness.calc.agent")


@pytest.fixture
def added():
    return importlib.import_module("harness.calc.added")


@pytest.fixture
def build(builder, conn, brief):
    """Run `build` with a scripted model and a recording person. Returns (results, model, person).

    The person's log also holds ("call", role) each time the model is called, so the order of the calls
    among what is said and asked can be read from it.
    """
    def run(script, answers=(), *, brief=brief, **options):
        person = Person(*answers)
        model = TracingModel(script, person)
        results = builder.build(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say,
                                session_id=SESSION, **options)
        return results, model, person
    return run


@pytest.fixture
def build_one(builder, conn, brief):
    """Run `build_step` with a scripted model and a recording person. Returns (result, model, person)."""
    def run(script, answers=(), *, step="s1", brief=brief, **options):
        person = Person(*answers)
        model = TracingModel(script, person)
        if isinstance(step, str):
            step = next(s for s in brief["process"] if s["id"] == step)
        result = builder.build_step(model=model, conn=conn, brief=brief, step=step, ask=person.ask,
                                    say=person.say, session_id=SESSION, **options)
        return result, model, person
    return run


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
def both(installed):
    """The two example modules, registered for steps s1 and s3 (under a name that says what a test needs)."""


@pytest.fixture
def chat(agent, conn, brief):
    """Run the agent with a scripted model and a person who answers from a list (then must be done).

    The person's log also holds ("call", role) each time a model is called, whoever calls it.
    """
    def run(script, answers=("/quit",), *, question=QUESTION, **options):
        person = Person(*answers)
        model = TracingModel(script, person)
        options = {"today": DAY, "session_id": SESSION, "brief": brief, **options}
        agent.run_agent(model=model, conn=conn, ask=person.ask, say=person.say, question=question, **options)
        return model, person
    return run


@pytest.fixture
def ask_agent(chat, installed):
    """`chat`, with both example modules registered."""
    return chat
