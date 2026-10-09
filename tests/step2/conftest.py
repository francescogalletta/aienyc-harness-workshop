import importlib
import json

import pytest

from harness import db
from harness.grounding import save_brief
from harness.model import ScriptedModel

from step2_helpers import SESSION, Person, make_brief

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
def agent():
    return importlib.import_module("harness.calc.agent")


@pytest.fixture
def build(builder, conn, brief):
    """Run `build` with a scripted model and a recording person. Returns (results, model, person)."""
    def run(script, answers=(), *, brief=brief, **options):
        model = ScriptedModel(script)
        person = Person(*answers)
        results = builder.build(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say,
                                session_id=SESSION, **options)
        return results, model, person
    return run
