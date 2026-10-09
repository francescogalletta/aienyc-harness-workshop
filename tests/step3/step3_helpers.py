"""Shared by the step 3 tests (SPEC sections 6 and 7).

The fixed strings below are copied from the SPEC on purpose: the tests check the harness against the
contract, not against its own constants. The step 2 helpers (a small brief, two example modules, script
builders, a recording person) are reused: this file puts that folder on the import path.
"""
import http.client
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "step2"))

import step2_helpers as h                                   # noqa: E402  (after the path is set)
from step2_helpers import Person, TracingModel              # noqa: E402,F401

# ---- fixed strings (SPEC 6.2, 6.3, 6.4, 6.6, 6.7) ---------------------------------------------------

ADOPT_INTRO = "These module folders are not registered here. Their worked examples were checked by hand, but not by you:"
ADOPT_QUESTION = ("Adopting a module means trusting worked examples you did not check yourself. Its tests and "
                  "examples run first, and it is registered only if they pass. Type yes to adopt them. Anything "
                  "else adopts nothing.")
ADOPT_MISSING = "missing files: {files}"
ADOPT_BAD_SPEC = "spec.json is not a valid spec for this folder"
ADOPT_BAD_EXAMPLES = "golden.json does not hold at least 2 worked examples"
ADOPT_NO_STEP = "the process has no calculation step '{step}'"
ADOPT_STEP_TAKEN = "step {step} already has the module '{other}'"
REASON_DECLINED = "you did not accept the worked examples"
REASON_TESTS = "its tests or worked examples do not pass here"
ADOPTED_STEP = "Re-created from the module '{module}' when it was adopted."
UNADOPTED = ("The modules folder has modules that are not registered here: {names}. Adopt them first with: "
             "python -m harness adopt")
NOTHING_TO_ADOPT = "Every module folder is already registered."
ALL_ADOPTED = "Every module folder is registered now."
SOME_NOT_ADOPTED = ("Some module folders are not registered. Fix them, or rebuild their steps with: "
                    "python -m harness build")
UNKNOWN_EXAMPLE = "There is no example called '{name}'. The examples are: {names}."
NO_SCENARIO = "There is no scenario '{scenario}' in {folder}. The scenarios are: {names}."
NO_SCENARIOS = "There are no scenarios in {folder}."
REPLAY_DONE = "{passed} of {total} scenarios passed."
NO_BUILT_MODULES = "No modules are built yet. Build them first with: python -m harness build"

NOT_REGISTERED = h.NOT_REGISTERED
ACCEPT3 = ["/accept"] * 3
BUILD_LINES = ["yes", *ACCEPT3]            # the answers of a person who builds one step at the first try

GOOD_META = {"status": "confirmed", "session_id": "s", "lookups": []}


# ---- small tools -------------------------------------------------------------------------------------

def typed(*answers):
    return "".join(answer + "\n" for answer in answers)


def dump(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def sql(path, query, params=()):
    """Rows of a read-only look at a database file, as dicts (the harness is not involved)."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(query, params)]
    finally:
        conn.close()


def stored_events(path, *, session=None, kind=None):
    """(id, kind, actor, session_id, payload) of the events of a database file, oldest first."""
    query, params = "SELECT * FROM events", []
    clauses = []
    if session is not None:
        clauses.append("session_id = ?")
        params.append(session)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    return [{**row, "payload": json.loads(row["payload"])} for row in sql(path, query + " ORDER BY id", params)]


def event_kinds(path, session=None):
    return [e["kind"] for e in stored_events(path, session=session)]


def record(conn, session, kind, actor="harness", **payload):
    from harness import db
    return db.record_event(conn, session_id=session, kind=kind, actor=actor, payload=payload)


def record_payload(conn, session, kind, payload, actor="harness"):
    from harness import db
    return db.record_event(conn, session_id=session, kind=kind, actor=actor, payload=payload)


def save_the_brief(brief_dir, brief=None, status="confirmed"):
    from harness.grounding import save_brief
    return save_brief(brief or h.make_brief(), Path(brief_dir), {**GOOD_META, "status": status})


def put_module(modules_dir, files):
    """Write a module folder (named after its spec) into the modules folder. Returns the folder."""
    name = json.loads(files["spec.json"])["name"]
    return h.write_files(Path(modules_dir) / name, files)


def surplus_folder(modules_dir, step_id="s1", **options):
    return put_module(modules_dir, h.surplus_files(step_id, **options))


def months_folder(modules_dir, step_id="s3", **options):
    return put_module(modules_dir, h.months_files(step_id, **options))


def yearly_folder(modules_dir, step_id="added_1"):
    return put_module(modules_dir, h.yearly_files(step_id))


def renamed_files(files, name, step_id=None):
    """The same module under another name (and, when given, for another step)."""
    spec = json.loads(files["spec.json"])
    spec["name"] = name
    if step_id is not None:
        spec["step_id"] = step_id
    return {**files, "spec.json": dump(spec)}


def with_spec(files, **changes):
    spec = json.loads(files["spec.json"])
    spec.update(changes)
    return {**files, "spec.json": dump(spec)}


def plan_text(spec):
    """plan_words of SPEC 5.7, worked out here."""
    def words(text):
        return text.replace("_", " ")
    lines = [f"To work this out: {words(spec['formula'])}", "I will need from you:"]
    for item in spec["inputs"]:
        lines.append(f"  - {words(item['name'])} ({h.KIND_WORDS[item['type']]}): {item['description']}")
    lines.append(f"It gives back: {spec['output']['description']}")
    return "\n".join(lines)


def step_ref(step_id, in_brief):
    return {"id": step_id, "label": h.label(step_id), "in_brief": in_brief}


# ---- a replay example on disk -------------------------------------------------------------------------

ASK_QUESTION = "I earn 5000 and spend 3000 a month. What is left each month?"


def make_example(parent, name="savings", *, modules=None, scenarios=None, brief=None, status="confirmed",
                 with_brief=True):
    """Write examples/<name>/ (brief, modules, scenarios) under `parent`. Returns the example folder.

    `modules` maps a folder name to the files of the module; `scenarios` maps a file stem to a scenario dict
    (written as JSON) or to raw text (written as it is).
    """
    folder = Path(parent) / name
    folder.mkdir(parents=True, exist_ok=True)
    if with_brief:
        save_the_brief(folder / "brief", brief, status)
    if modules is None:
        modules = {"monthly_surplus": h.surplus_files("s1"), "months_to_goal": h.months_files("s3")}
    (folder / "modules").mkdir(exist_ok=True)
    for module_name, files in modules.items():
        h.write_files(folder / "modules" / module_name, files)
    scenarios = {"upfront": ask_scenario("upfront")} if scenarios is None else scenarios
    (folder / "scenarios").mkdir(exist_ok=True)
    for stem, value in scenarios.items():
        text = value if isinstance(value, str) else dump(value)
        (folder / "scenarios" / f"{stem}.json").write_text(text, encoding="utf-8")
    return folder


def ask_scenario(name="upfront", **changes):
    """A valid ask scenario for the example above: the person asks, the module runs, the reply shows 2,000."""
    scenario = {"name": name, "kind": "ask", "description": "Ask what is left.", "today": "2031-07-22",
                "lines": [ASK_QUESTION],
                "expect": {"runs": [{"module": "monthly_surplus", "inputs": {"income": "5000"}}],
                           "shown": ["2,000"], "max_withheld": 0, "max_corrections": 0}}
    scenario.update(changes)
    return {key: value for key, value in scenario.items() if value is not None}


def ask_script(reply="You have 2,000 left each month."):
    return [h.run_module(), h.say_text(reply)]


def build_scenario(name="rebuild_one", **changes):
    scenario = {"name": name, "kind": "build", "without": ["s1"], "lines": list(BUILD_LINES),
                "expect": {"steps": {"s1": "built", "s3": "kept"}}}
    scenario.update(changes)
    return {key: value for key, value in scenario.items() if value is not None}


# ---- running the command line -----------------------------------------------------------------------------

def cli_env(**extra):
    """The test environment plus `extra`; a value of None removes the variable."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    for key, value in extra.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def run_in(cwd, args, typed_text="", *, timeout=180, **env):
    """Run `python -m harness ...` with `cwd` as the working folder (the harness is found through PYTHONPATH)."""
    return subprocess.run([sys.executable, "-m", "harness", *args], cwd=cwd, input=typed_text,
                          capture_output=True, text=True, env=cli_env(**env), timeout=timeout)


# ---- a running server ---------------------------------------------------------------------------------------

class Reply:
    def __init__(self, status, content_type, text, headers):
        self.status, self.content_type, self.text, self.headers = status, content_type, text, headers

    def json(self):
        assert self.content_type and self.content_type.startswith("application/json"), (self.status, self.content_type, self.text[:200])
        return json.loads(self.text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)       # no proxy, no redirects

STAND_IN_PAGE = "<!doctype html><title>Stand-in evidence page</title><script>const token = '__HARNESS_TOKEN__';</script>"
STAND_IN_INTERVIEW = "<!doctype html><title>Stand-in interview</title><script>const token = '__HARNESS_TOKEN__';</script>"


def start_server(session=None, *, work_page=None, page=None, tmp_path):
    """Start the server on a free port in a thread. Returns (server, thread, send)."""
    from harness.ui.server import TOKEN_HEADER, make_server

    options = {}
    if work_page is not False:
        path = tmp_path / "work_page.html"
        path.write_text(STAND_IN_PAGE if work_page is None else work_page, encoding="utf-8")
        options["work_page_path"] = path
    if page is not None:
        path = tmp_path / "page.html"
        path.write_text(page, encoding="utf-8")
        options["page_path"] = path
    server = make_server(session, port=0, **options)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()

    def send(method, path, body=None, token="default", raw=None):
        if token == "default":
            token = server.token
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}", data=data, method=method)
        if token is not None:
            request.add_header(TOKEN_HEADER, token)
        try:
            with DIRECT.open(request, timeout=60) as reply:
                return Reply(reply.status, reply.headers["Content-Type"], reply.read().decode("utf-8"), reply.headers)
        except urllib.error.HTTPError as error:
            return Reply(error.code, error.headers["Content-Type"], error.read().decode("utf-8"), error.headers)

    send.server = server
    return server, thread, send


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(5)


# ---- the recorded story the evidence tests read ------------------------------------------------------------------

BUILD, ADOPT, CHAT1, CHAT2, REPLAY = "build-1", "adopt-1", "chat-1", "chat-2", "replay-1"
DAY1, DAY2, DAY3 = date(2026, 3, 14), date(2026, 4, 2), date(2026, 5, 5)
NOTE_TEXT = "My car costs 700 a month."
Q1 = ("I earn 5000 and spend 3000 a month, or 6000 and 4000 in a good month, plus 450 on the side. "
      "I also owe 900.")
GOOD_REPLY = ("You keep 2,000 a month, or 2,000 again in a good month, from 5,000 less 3,000. Your 450 on the side "
              "is saved. Your car's 700 and the 1,150 rent are covered, and the 900 you owe is known. "
              "That is 3 payments, as of 2026-03-14.")
GOOD_REPLY_NUMBERS = [("2,000", "run", 2), ("2,000", "run", 2), ("5,000", "run", 1), ("3,000", "run", 1),
                      ("450", "input", None), ("700", "note", None), ("1,150", "brief", None),
                      ("900", "person", None), ("3", "small", None), ("2026-03-14", "today", None)]
CORRECTED_REPLY = "You will have 2,500."
WITHHELD_REPLY = "Perhaps 2,600."
Q2 = "My subscriptions cost 250 a month. What is that over a whole year?"
Q2_REQUEST_WHY = "you asked about 250 a month over a year"
Q2_REPLY = "It comes to 3,000 a year, from 250 a month."
Q3 = "I earn 4000 and spend 3500. What is left?"
Q3_REPLY = "You keep 500 a month."
REPLAY_SCENARIO = {"example": "savings", "scenario": "first_look", "kind": "ask", "lines": [Q3],
                   "expect": {"runs": [{"module": "monthly_surplus"}]}, "without": []}


def traced(text, expected):
    """The trace items a text should give, from [(written, source, run id)] read left to right."""
    items, position = [], 0
    for written, source, run_id in expected:
        start = text.index(written, position)
        items.append({"text": written, "start": start, "end": start + len(written), "source": source,
                      "run_id": run_id})
        position = start + len(written)
    return items


def build_world(root):
    """Record a small story through the public functions: a build, an adoption and four conversations.

    Layout under `root`: brief/, modules/, var/harness.db. Everything runs with the scripted model.
    Returns nothing; the tests read the files.
    """
    from harness import db
    from harness.calc import added, adopt, agent, builder, notes
    from harness.model import ScriptedModel

    root = Path(root)
    settings = {"HARNESS_DB": root / "var" / "harness.db", "HARNESS_BRIEF_DIR": root / "brief",
                "HARNESS_MODULES_DIR": root / "modules", "HARNESS_MODEL_PROVIDER": "scripted"}
    with pytest.MonkeyPatch.context() as patch:
        for name in ("HARNESS_EXAMPLE", "HARNESS_SCRIPT"):
            patch.delenv(name, raising=False)
        for name, value in settings.items():
            patch.setenv(name, str(value))
        brief = h.make_brief()
        save_the_brief(root / "brief", brief)
        conn = db.connect()
        db.migrate(conn)

        # 1. A build of step s1, with a note kept before it (SPEC 5.5, 5.7).
        notes.add_note(conn, step_id="s1", text=NOTE_TEXT, session_id=BUILD)
        person = Person(*BUILD_LINES)
        builder.build_step(model=ScriptedModel(h.surplus_script()), conn=conn, brief=brief, step=brief["process"][0],
                           ask=person.ask, say=person.say, session_id=BUILD)

        # 2. An adoption of the folder of step s3 (SPEC 6.3).
        months_folder(root / "modules")
        person = Person("yes")
        adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=ADOPT)

        # 3. A conversation with a correction, a withheld reply, a saved input and a shown reply.
        script = [h.tools(("run_module", h.run_module()["tool_calls"][0]["arguments"]),
                          ("run_module", h.run_module(inputs={"income": "6000", "spending": "4000"})["tool_calls"][0]["arguments"]),
                          ("save_input", h.save_input("side_income", "450", "said by the person")["tool_calls"][0]["arguments"])),
                  h.say_text(CORRECTED_REPLY), h.say_text(WITHHELD_REPLY), h.say_text(GOOD_REPLY)]
        person = Person("Please try again", "/quit")
        agent.run_agent(model=ScriptedModel(script), conn=conn, brief=brief, ask=person.ask, say=person.say,
                        session_id=CHAT1, question=Q1, today=DAY1)

        # 4. A conversation in which the agent asks for a step that is not in the brief, and the person says yes.
        why = {"why": Q2_REQUEST_WHY}
        script = [h.request_module("new", **why), *h.yearly_script(),
                  h.run_module("yearly_cost", {"monthly": "250"}, expected="about 3000"), h.say_text(Q2_REPLY)]
        person = Person("yes", *BUILD_LINES, "/quit")
        agent.run_agent(model=ScriptedModel(script), conn=conn, brief=brief, ask=person.ask, say=person.say,
                        session_id=CHAT2, question=Q2, today=DAY2)

        # 5. A conversation marked as a replay (the marker is what `replay` writes first, SPEC 6.8).
        record_payload(conn, REPLAY, "replay.scenario", REPLAY_SCENARIO)
        person = Person("/quit")
        script = [h.run_module("monthly_surplus", {"income": "4000", "spending": "3500"}), h.say_text(Q3_REPLY)]
        agent.run_agent(model=ScriptedModel(script), conn=conn, brief=brief, ask=person.ask, say=person.say,
                        session_id=REPLAY, question=Q3, today=DAY3)
        assert added.list_added_steps(conn)[0]["id"] == "added_1"
        conn.close()


class World:
    """A copy of the recorded story in a test's own folder, with the environment pointing at it."""

    def __init__(self, root):
        self.root = Path(root)
        self.db_path = self.root / "var" / "harness.db"
        self.brief_dir = self.root / "brief"
        self.modules_dir = self.root / "modules"

    def sql(self, query, params=()):
        return sql(self.db_path, query, params)

    def events(self, **options):
        return stored_events(self.db_path, **options)

    def counts(self):
        return {table: self.sql(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
                for table in ("events", "test_runs", "calc_runs", "modules", "notes", "added_steps")}

    def module_text(self, name, file):
        return (self.modules_dir / name / file).read_text(encoding="utf-8")

    def edit(self, name, file="module.py", prefix="# edited\n"):
        path = self.modules_dir / name / file
        path.write_text(prefix + path.read_text(encoding="utf-8"), encoding="utf-8")


def copy_world(template, target, patch):
    shutil.copytree(template, target)
    world = World(target)
    patch.setenv("HARNESS_DB", str(world.db_path))
    patch.setenv("HARNESS_BRIEF_DIR", str(world.brief_dir))
    patch.setenv("HARNESS_MODULES_DIR", str(world.modules_dir))
    return world


def http_connection(server):
    return http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)


# ---- running adopt -----------------------------------------------------------------------------------------

def run_adopt(conn, brief, *answers, how="asked", session_id=h.SESSION, **options):
    """Call `adopt` with a recording person. Returns (results, person)."""
    import importlib
    adopt = importlib.import_module("harness.calc.adopt")
    person = Person(*answers)
    results = adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=session_id,
                          how=how, **options)
    return results, person


def adopted_line(name, step_id):
    return f"{name} -> {h.label(step_id)} (adopted)"


def refused_line(name, reason):
    return f"{name}: not adopted ({reason})"


def listing(name, step_id, n=3, decisions=None):
    decisions = decisions or ["accepted"] * n
    return f"  {name} for step {h.label(step_id)}: {n} worked examples ({', '.join(decisions)})"


def result(name, step, outcome="adopted", reason=""):
    return {"module": name, "step": step, "outcome": outcome, "reason": reason}
