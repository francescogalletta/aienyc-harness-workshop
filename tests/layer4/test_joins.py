"""SPEC 6.4 and 6.6, ARCHITECTURE.md 12.3 to 12.5: branches on a subject, proposals and their checks, the join on
the main lane with no model call, and when a branch dies. Offline, with a scripted model for each lane."""
import json
import shutil

import pytest

from harness.config import load_config
from harness.core import BadAction, Session
from harness.model import ScriptedModel
from layer4_helpers import SETTLE, ask, call, events, problems, reply, run, until

SIDE_START = "You help one person understand"
PROPOSED = {"kind": "proposed"}
STEP = {"method": "arithmetic", "cadence": "", "origin": PROPOSED}
ASKED = "I need 40 units at 100 each, and the first payment is 500. What do I pay?"
TEST_HEAD = "from decimal import Decimal\nfrom module import calculate\n\n\n"


def _plan() -> dict:
    """c1 total -> c2 split -> c3 (no module) -> j1. Inputs Unit count, Unit price, First, Extra (c3 only)."""
    item = lambda text: {"text": text, "origin": PROPOSED}          # noqa: E731
    return {
        "goal": item("Know the payments"), "mode": "one_off",
        "scope": {"in": [item("Payments")], "out": [item("Taxes")]}, "glossary": [],
        "particulars": [{"what": "Amounts are in euros", "handling": "Say so", "step": "c1", "origin": PROPOSED}],
        "inputs": [{"name": name, "description": name.lower(), "origin": PROPOSED}
                   for name in ("Unit count", "Unit price", "First", "Extra")],
        "process": [
            {"id": "c1", "name": "Total", "kind": "calculation", "formula": "count x price",
             "needs": ["Unit count", "Unit price"], "produces": "total", **STEP},
            {"id": "c2", "name": "Split", "kind": "calculation", "formula": "first, then the rest in halves",
             "needs": ["c1", "First"], "produces": "three payments", **STEP},
            {"id": "c3", "name": "Later", "kind": "calculation", "formula": "rest + extra", "needs": ["c2", "Extra"],
             "produces": "later", **STEP},
            {"id": "j1", "name": "Is it enough?", "kind": "judgment", "method": "", "formula": "", "needs": ["c3"],
             "produces": "a decision", "cadence": "", "origin": PROPOSED}],
        "definition_of_done": [item("I know the payments")], "open_questions": [],
        "meta": {"status": "confirmed", "written_at": "2026-10-10T00:00:00+00:00", "session_id": "x",
                 "lookups": [], "revisions": []}}


def _module(name, step, inputs, output, code, test, examples):
    spec = {"name": name, "description": name, "step_id": step, "method": "arithmetic", "formula": name,
            "inputs": [{"name": key, "type": "number", "description": key} for key in inputs],
            "output": {"type": output, "description": name}}
    golden = [{"inputs": given, "expected": expected, "working": "by hand", "checked_by": "second_pass"}
              for given, expected in examples]
    return {"spec.json": json.dumps(spec), "golden.json": json.dumps(golden), "module.py": code,
            "tests.py": TEST_HEAD + test}


MODULES = {
    "total": _module(
        "total", "c1", ["unit_count", "unit_price"], "number",
        "def calculate(unit_count, unit_price):\n    return unit_count * unit_price\n",
        "def test_it():\n    assert calculate(unit_count=Decimal('2'), unit_price=Decimal('3')) == Decimal('6')\n",
        [({"unit_count": "2", "unit_price": "3"}, "6"), ({"unit_count": "0", "unit_price": "5"}, "0"),
         ({"unit_count": "10", "unit_price": "2.5"}, "25")]),
    "split": _module(
        "split", "c2", ["total", "first"], "object",
        "def calculate(total, first):\n"
        "    if total < first:\n        raise ValueError('the total must be at least the first payment')\n"
        "    rest = (total - first) / 2\n"
        "    return {'first': first, 'rest': rest, 'last': total - first - rest}\n",
        "def test_it():\n    assert calculate(total=Decimal('10'), first=Decimal('2'))['rest'] == Decimal('4')\n",
        [({"total": "100", "first": "50"}, {"first": "50", "rest": "25", "last": "25"}),
         ({"total": "10", "first": "0"}, {"first": "0", "rest": "5", "last": "5"}),
         ({"total": "8", "first": "8"}, {"first": "8", "rest": "0", "last": "0"})]),
}


@pytest.fixture(scope="module")
def adopted(tmp_path_factory):
    folder = tmp_path_factory.mktemp("branches")
    (folder / "brief").mkdir()
    (folder / "brief" / "domain_brief.json").write_text(json.dumps(_plan()), encoding="utf-8")
    for name, files in MODULES.items():
        (folder / "modules" / name).mkdir(parents=True)
        for file, text in files.items():
            (folder / "modules" / name / file).write_text(text, encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HARNESS_LAYERS", "4")
        patch.setenv("HARNESS_DB", str(folder / "harness.db"))
        patch.setenv("HARNESS_BRIEF_DIR", str(folder / "brief"))
        patch.setenv("HARNESS_MODULES_DIR", str(folder / "modules"))
        patch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
        session = Session(load_config(), model_factory=lambda: ScriptedModel([]))
        session.settle(SETTLE)
        session.close()
    return folder


class Routed:
    """The side assistant's calls go to `side`, every other call to `main`."""

    def __init__(self, main, side):
        self.main, self.side = ScriptedModel(list(main)), ScriptedModel(list(side))

    def complete(self, *, system, messages, tools=()):
        target = self.side if system.startswith(SIDE_START) else self.main
        return target.complete(system=system, messages=messages, tools=tools)


@pytest.fixture
def make(tmp_path, adopted):
    for name in ("brief", "modules"):
        shutil.copytree(adopted / name, tmp_path / name)
    shutil.copy(adopted / "harness.db", tmp_path / "harness.db")
    opened = []

    def open_session(main=(), side=()):
        model = Routed(main, side)
        session = Session(load_config(), model_factory=lambda: model)
        session.models = model
        session.memory["today"] = "2026-10-10"
        opened.append(session)
        session.settle(SETTLE)
        return session

    yield open_session
    for session in opened:
        session.close()


ANSWER = [run("total", {"unit_count": 40, "unit_price": 100}, expected="4000"),
          run("split", {"total": 4000, "first": 500}, expected="500, then 1750 twice"),
          reply("You pay 500, then 1,750 twice.")]


def propose(input="unit_count", value="50", words="we need 50 units", kind="value", step=""):
    return call("propose_change", kind=kind, input=input, value=value, step=step, words=words)


def act(session, action, **payload):
    applied, why = session.act(action, payload)
    assert applied, why
    return session.settle(SETTLE)


def answered(make, side=(), main_after=()):
    """A session whose last answer ran total (r1: 4000) and split (r2) for the person's figures."""
    session = make(main=[*ANSWER, *main_after], side=side)
    act(session, "say", text=ASKED)
    return session


def chip(state, kind, label=None):
    found = [each for message in state["chat"] for each in message["chips"]
             if each["kind"] == kind and (label is None or each["label"] == label)]
    return found[-1]


def branch(session, text, subject=None, step=None):
    payload = {"text": text, **({"subject": subject} if subject else {}), **({"step": step} if step else {})}
    return act(session, "side", **payload)


def thread_of(state, n=-1):
    return [thread for thread in state["threads"] if thread["kind"] == "side"][n]


def valid(state):
    found = problems(state)
    assert found == [], found
    return state


# --- Opening a branch on a subject ---

def test_a_branch_opens_on_a_chip_subject_with_its_step_and_records_it(make):
    session = answered(make, side=[reply("That is the count of units.")])
    state = session.state()
    subject = chip(state, "value", "Unit count")["subject"]
    state = branch(session, "Why this count?", subject)
    found = thread_of(state)
    assert found["subject"] == subject and found["step"] == "c1" and found["origin"] == "you"
    assert found["outcome"] == "open" and found["proposal"] is None and found["from"] == state["history"]["latest"]
    assert [each["subject"] for each in events(session, "you.side_opened")] == [subject]
    valid(state)


@pytest.mark.parametrize("subject", [
    {"kind": "nothing"}, "plan", {"kind": "step", "step": "c9"}, {"kind": "input", "input": "in:nope"},
    {"kind": "value", "run": "r99", "key": "unit_count", "value": "40"},
    {"kind": "value", "run": "r1", "key": "not_an_input", "value": "40"},
    {"kind": "result", "run": "x1", "value": "4000"}, {"kind": "decision", "node": "n99"},
    {"kind": "assumption", "run": "r1", "text": "Something.", "assumption": "a99"}])
def test_a_subject_whose_ids_do_not_exist_is_a_bad_action(make, subject):
    session = answered(make)
    with pytest.raises(BadAction):
        session.act("side", {"text": "Is this right?", "subject": subject})
    assert session.state()["threads"] == []


def test_the_side_assistant_sees_the_subject_and_the_last_answer_and_may_propose(make):
    session = answered(make, side=[reply("It is the count.")])
    state = branch(session, "What went in?", chip(session.state(), "result", "Split")["subject"])
    sent = session.models.side.calls[0]
    assert {tool.name for tool in sent["tools"]} == {"look_up", "propose_change"}
    assert "split" in sent["system"] and "1750" in sent["system"]           # the subject's run, and its output
    assert "total" in sent["system"] and "unit_count" in sent["system"]       # the last answer's runs
    valid(state)


def test_propose_change_is_not_offered_before_the_plan_is_accepted(tmp_path):
    model = Routed([], [reply("A plan has steps.")])
    session = Session(load_config(), model_factory=lambda: model)
    try:
        session.act("side", {"text": "What is a plan?"})
        session.settle(SETTLE)
        assert [tool.name for tool in model.side.calls[0]["tools"]] == ["look_up"]
    finally:
        session.close()


# --- A proposal and its checks ---

def test_a_proposal_that_passes_is_pending_with_its_impact(make):
    session = answered(make, side=[propose(), reply("I proposed 50 units.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    found = thread_of(state)["proposal"]
    assert found["status"] == "pending" and found["node"] is None and found["words"] == "we need 50 units"
    assert found["change"] == {"kind": "value", "input": "unit_count", "label": "Unit count", "from": "40",
                               "to": "50"}
    assert "40" in found["text"] and "50" in found["text"]
    assert found["impact"] == {"inputs": ["in:unit_count"], "runs": ["r1", "r2"], "steps": ["c1", "c2"],
                               "downstream": ["c3", "j1"]}
    result = [m for m in session.models.side.calls[1]["messages"] if m["role"] == "tool"][-1]
    assert not result.get("is_error")
    assert [each["proposal"] for each in events(session, "you.proposed")] == [found["id"]]
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 2     # nothing ran
    valid(state)


@pytest.mark.parametrize("arguments, reason", [
    ({"words": "we need sixty units"}, "not_their_words"),
    ({"input": "head_count"}, "unknown_input"),
    ({"value": "60"}, "value_unbacked"),
    ({"value": "40", "words": "we need 40 units after all"}, "same"),
    ({"kind": "plan", "step": "c9"}, "unknown_step")])
def test_a_proposal_that_fails_a_check_is_refused_with_its_reason(make, arguments, reason):
    words = arguments.get("words", "we need 50 units")
    session = answered(make, side=[propose(**{**{"words": words}, **arguments}), reply("I cannot propose that.")])
    state = branch(session, "No, we need 50 units. Or we need 40 units after all.",
                   chip(session.state(), "value", "Unit count")["subject"])
    assert thread_of(state)["proposal"] is None
    assert [each["reason"] for each in events(session, "you.proposal_refused")] == [reason]
    result = [m for m in session.models.side.calls[1]["messages"] if m["role"] == "tool"][-1]
    assert result["is_error"]


def test_a_value_the_last_answer_took_twice_is_ambiguous_from_the_whole_plan(make):
    twice = [run("total", {"unit_count": 40, "unit_price": 100}), run("total", {"unit_count": 60, "unit_price": 100}),
             reply("4,000 or 6,000.")]
    session = make(main=twice, side=[propose(), reply("Which one?")])
    act(session, "say", text="What is the total for 40 units or 60 units at 100 each?")
    state = branch(session, "Make it: we need 50 units")
    assert thread_of(state)["proposal"] is None
    assert [each["reason"] for each in events(session, "you.proposal_refused")] == ["ambiguous"]


def test_one_proposal_per_reply_and_a_new_one_replaces_the_pending_one(make):
    two = {"tool_calls": [propose()["tool_calls"][0], propose(value="55", words="or 55 units")["tool_calls"][0]]}
    session = answered(make, side=[two, reply("Proposed 50."), propose(value="55", words="or 55 units"),
                                   reply("Proposed 55.")])
    subject = chip(session.state(), "value", "Unit count")["subject"]
    state = branch(session, "we need 50 units, or 55 units", subject)
    assert [each["reason"] for each in events(session, "you.proposal_refused")] == ["one_per_reply"]
    first = thread_of(state)["proposal"]
    state = act(session, "side", text="Actually or 55 units", thread=thread_of(state)["id"])
    second = thread_of(state)["proposal"]
    assert second["id"] != first["id"] and second["change"]["to"] == "55" and second["status"] == "pending"
    statuses = [row["status"] for row in session.conn.execute("SELECT status FROM proposals ORDER BY id")]
    assert statuses == ["replaced", "pending"]


# --- The join ---

def test_yes_joins_the_branch_with_no_model_call_and_records_the_node(make):
    session = answered(make, side=[propose(), reply("I proposed 50 units.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    proposal, thread = thread_of(state)["proposal"]["id"], thread_of(state)["id"]
    main_calls = len(session.models.main.calls)
    state = act(session, "accept_proposal", proposal=proposal)
    assert len(session.models.main.calls) == main_calls                   # the re-run asks no model
    rows = session.conn.execute("SELECT module, inputs, output FROM calc_runs ORDER BY id").fetchall()
    assert [(row["module"], json.loads(row["inputs"])) for row in rows[2:]] == [
        ("total", {"unit_count": "50", "unit_price": "100"}), ("split", {"total": "5000", "first": "500"})]
    node = state["history"]["trunk"][-1]
    assert (node["kind"], node["who"], node["branch"]) == ("value", "you", thread)
    assert node["touched"] == {"inputs": ["in:unit_count"], "steps": ["c1", "c2"]}
    assert node["change"]["from"] == "40" and node["change"]["to"] == "50" and node["change"]["runs"] == {
        "r1": "r3", "r2": "r4"}
    found = thread_of(state)
    assert found["outcome"] == "joined" and found["node"] == node["id"]
    assert found["proposal"]["status"] == "accepted" and found["proposal"]["node"] == node["id"]
    assert state["inputs"]["in:unit_count"]["value"] == "50"
    assert state["inputs"]["in:unit_count"]["changed_by"] == node["id"]
    assert {step["id"] for step in state["steps"] if step["changed_by"] == node["id"]} == {"c1", "c2"}
    assert [each["node"] for each in events(session, "you.joined")] == [node["id"]]
    valid(state)


def test_the_join_notice_carries_a_decision_chip_first_and_the_new_results(make):
    session = answered(make, side=[propose(), reply("Proposed.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    state = act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    notice = state["chat"][-1]
    assert notice["who"] == "harness"
    kinds = [each["kind"] for each in notice["chips"]]
    assert kinds[0] == "decision" and notice["chips"][0]["subject"] == {"kind": "decision",
                                                                         "node": state["history"]["latest"]}
    assert [each["subject"]["run"] for each in notice["chips"] if each["kind"] == "result"] == ["r3", "r4"]
    assert [(each["label"], each["text"]) for each in notice["chips"] if each["kind"] == "value"] == [
        ("Unit count", "50 (was 40)")]                      # only the value that changed, old to new (12.7)
    assert [(each["label"], each["text"]) for each in notice["chips"] if each["kind"] == "result"] == [
        ("Total", "5,000 (was 4,000)"), ("Split", "2,250 (was 1,750)")]   # an object: the leaf that changed
    assert "assumption" not in kinds                         # the old answer keeps those
    assert {step["id"]: step["last_run"]["run"] for step in state["steps"] if step["id"] in ("c1", "c2")} == {
        "c1": "r3", "c2": "r4"}


def test_after_a_join_the_analyst_is_told_with_the_next_message(make):
    session = answered(make, side=[propose(), reply("Proposed.")], main_after=[reply("Noted.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    act(session, "say", text="And now?")
    told = session.models.main.calls[-1]["messages"][-1]["content"]
    assert told.startswith("And now?") and "[harness]" in told and "5000" in told and "2250" in told


def test_an_assumption_subject_is_corrected_on_the_join_and_left_out_of_the_run(make):
    with_assumption = [run("total", {"unit_count": 40, "unit_price": 100},
                           assumptions=["The unit count stays as it is."]), reply("The total is 4,000.")]
    session = make(main=with_assumption, side=[propose(), reply("Proposed.")])
    act(session, "say", text=ASKED)
    found = chip(session.state(), "assumption")
    assert found["status"] == "unconfirmed" and found["subject"]["assumption"]
    state = branch(session, "No, we need 50 units.", found["subject"])
    state = act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    row = session.conn.execute("SELECT status FROM assumptions WHERE id = ?",
                               (int(found["subject"]["assumption"][1:]),)).fetchone()
    assert row["status"] == "corrected"
    assert json.loads(session.conn.execute("SELECT assumptions FROM calc_runs ORDER BY id DESC").fetchone()[0]) == []
    assert chip(state, "assumption")["status"] == "corrected"
    valid(state)


def test_a_value_no_run_used_joins_with_nothing_run_again(make):
    session = answered(make, side=[propose(input="extra", value="70", words="the extra is 70"), reply("Proposed.")])
    state = branch(session, "the extra is 70", {"kind": "input", "input": "in:extra", "step": "c3"})
    assert thread_of(state)["proposal"]["impact"] == {"inputs": ["in:extra"], "runs": [], "steps": [],
                                                      "downstream": ["c3", "j1"]}
    state = act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    node = state["history"]["trunk"][-1]
    assert node["touched"] == {"inputs": ["in:extra"], "steps": []} and node["change"]["from"] is None
    assert [each["kind"] for each in state["chat"][-1]["chips"]] == ["decision"]
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 2
    valid(state)


def test_a_run_the_gate_refuses_is_named_and_the_value_is_still_joined(make):
    session = answered(make, side=[propose(value="2", words="only 2 units"), reply("Proposed.")])
    state = branch(session, "only 2 units", chip(session.state(), "value", "Unit count")["subject"])
    state = act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    node = state["history"]["trunk"][-1]
    assert [(each["run"], each["step"]) for each in node["change"]["failed"]] == [("r2", "c2")]
    assert node["touched"]["steps"] == ["c1"] and thread_of(state)["outcome"] == "joined"
    assert state["inputs"]["in:unit_count"]["value"] == "2"
    valid(state)


def test_yes_is_refused_unless_pending_and_while_a_decision_waits(make):
    waiting = [*ANSWER[:2], ask("j1", "Is it enough?", ["Yes", "No"], runs=[2]), reply("Noted.")]
    session = make(main=waiting, side=[propose(), reply("Proposed.")])
    session.act("say", {"text": ASKED})
    until(session, lambda state: (state["waiting"] or {}).get("kind") == "decision")
    subject = {"kind": "value", "run": "r1", "key": "unit_count", "value": "40", "input": "in:unit_count",
               "step": "c1"}                                     # the chips come once the turn ends
    session.act("side", {"text": "No, we need 50 units.", "subject": subject})
    state = until(session, lambda state: thread_of(state)["proposal"] is not None and state["lanes"]["side"] == "idle")
    proposal = thread_of(state)["proposal"]["id"]
    applied, why = session.act("accept_proposal", {"proposal": proposal})
    assert not applied and why
    with pytest.raises(BadAction):
        session.act("accept_proposal", {"proposal": "x1"})
    decision = state["waiting"]["decision"]
    act(session, "choose", decision=decision, option=1)
    state = act(session, "accept_proposal", proposal=proposal)
    assert thread_of(state)["outcome"] == "joined"
    applied, _ = session.act("accept_proposal", {"proposal": proposal})
    assert not applied


# --- A bundle: several values in one proposal (12.3) ---

BUNDLE_WORDS = "we need 50 units and the first payment is 600"


def bundle(items=(("unit_count", "50"), ("first", "600")), words=BUNDLE_WORDS):
    return call("propose_change", kind="value", words=words,
                changes=[{"input": key, "value": value} for key, value in items])


def test_a_bundle_proposal_is_pending_with_every_change_and_the_union_of_their_impact(make):
    session = answered(make, side=[bundle(), reply("I proposed both.")])
    state = branch(session, "No: " + BUNDLE_WORDS + ".", chip(session.state(), "value", "Unit count")["subject"])
    found = thread_of(state)["proposal"]
    assert found["status"] == "pending"
    assert found["change"]["changes"] == [
        {"input": "unit_count", "label": "Unit count", "from": "40", "to": "50"},
        {"input": "first", "label": "First", "from": "500", "to": "600"}]
    assert {key: found["change"][key] for key in ("kind", "input", "label", "from", "to")} == {
        "kind": "value", "input": "unit_count", "label": "Unit count", "from": "40", "to": "50"}
    assert "50" in found["text"] and "600" in found["text"] and "First" in found["text"]
    assert found["impact"] == {"inputs": ["in:unit_count", "in:first"], "runs": ["r1", "r2"], "steps": ["c1", "c2"],
                               "downstream": ["c3", "j1"]}
    valid(state)


def test_a_bundle_with_one_bad_change_is_refused_as_a_whole(make):
    session = answered(make, side=[bundle(items=(("unit_count", "50"), ("first", "700"))),
                                   reply("I cannot propose that.")])
    state = branch(session, "No: " + BUNDLE_WORDS + ".", chip(session.state(), "value", "Unit count")["subject"])
    assert thread_of(state)["proposal"] is None
    assert [each["reason"] for each in events(session, "you.proposal_refused")] == ["value_unbacked"]
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 2


def test_yes_on_a_bundle_saves_every_value_and_runs_each_reached_run_once(make):
    session = answered(make, side=[bundle(), reply("Proposed.")], main_after=[reply("Noted.")])
    state = branch(session, "No: " + BUNDLE_WORDS + ".", chip(session.state(), "value", "Unit count")["subject"])
    thread = thread_of(state)["id"]
    state = act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    rows = session.conn.execute("SELECT module, inputs FROM calc_runs ORDER BY id").fetchall()
    assert [(row["module"], json.loads(row["inputs"])) for row in rows[2:]] == [
        ("total", {"unit_count": "50", "unit_price": "100"}), ("split", {"total": "5000", "first": "600"})]
    assert state["inputs"]["in:unit_count"]["value"] == "50" and state["inputs"]["in:first"]["value"] == "600"
    node = state["history"]["trunk"][-1]
    assert (node["kind"], node["who"], node["branch"]) == ("value", "you", thread)
    assert node["touched"] == {"inputs": ["in:unit_count", "in:first"], "steps": ["c1", "c2"]}
    assert node["change"]["runs"] == {"r1": "r3", "r2": "r4"} and node["change"]["failed"] == []
    assert [each["to"] for each in node["change"]["changes"]] == ["50", "600"]
    assert "50" in node["text"] and "600" in node["text"] and len(node["text"]) <= 80
    assert state["inputs"]["in:first"]["changed_by"] == node["id"]
    notice = state["chat"][-1]
    assert [(each["label"], each["text"]) for each in notice["chips"] if each["kind"] == "value"] == [
        ("Unit count", "50 (was 40)"), ("First", "600 (was 500)")]
    assert [(each["label"], each["text"]) for each in notice["chips"] if each["kind"] == "result"] == [
        ("Total", "5,000 (was 4,000)"), ("Split", "2,200 (was 1,750)")]
    assert "50" in notice["text"] and "600" in notice["text"]
    act(session, "say", text="And now?")
    told = session.models.main.calls[-1]["messages"][-1]["content"]
    assert "[harness]" in told and "600" in told and "2200" in told
    valid(state)


# --- No, closing, and deaths ---

def test_no_declines_and_the_branch_is_dead_with_no_node(make):
    session = answered(make, side=[propose(), reply("Proposed.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    nodes = len(state["history"]["trunk"])
    state = act(session, "decline_proposal", proposal=thread_of(state)["proposal"]["id"])
    assert thread_of(state)["outcome"] == "dead" and thread_of(state)["proposal"]["status"] == "declined"
    assert len(state["history"]["trunk"]) == nodes
    assert [each["reason"] for each in events(session, "you.branch_dead")] == ["declined"]
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 2
    valid(state)


def test_closing_a_branch_declines_its_proposal_and_it_cannot_be_closed_twice(make):
    session = answered(make, side=[propose(), reply("Proposed.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    thread = thread_of(state)["id"]
    state = act(session, "close_branch", thread=thread)
    assert thread_of(state)["outcome"] == "dead" and thread_of(state)["proposal"]["status"] == "declined"
    assert [each["reason"] for each in events(session, "you.branch_dead")] == ["closed"]
    applied, _ = session.act("close_branch", {"thread": thread})
    assert not applied
    with pytest.raises(BadAction):
        session.act("close_branch", {"thread": "m1"})
    valid(state)


def test_a_question_answered_dies_when_another_branch_opens_but_one_with_a_proposal_does_not(make):
    session = answered(make, side=[reply("A split is a division."), propose(), reply("Proposed."),
                                   reply("Another answer.")])
    state = branch(session, "What is a split?", step="c2")
    state = branch(session, "No, we need 50 units.", chip(state, "value", "Unit count")["subject"])
    assert [thread["outcome"] for thread in state["threads"]] == ["dead", "open"]
    state = branch(session, "And the price?", step="c1")
    assert [thread["outcome"] for thread in state["threads"]] == ["dead", "open", "open"]
    assert [each["reason"] for each in events(session, "you.branch_dead")] == ["new_branch"]
    assert state["history"]["trunk"][-1]["kind"] != "value"


def test_moving_on_in_the_main_chat_kills_an_answered_branch_and_a_message_reopens_it(make):
    session = answered(make, side=[reply("A split is a division."), reply("Yes.")], main_after=[reply("Hello.")])
    state = branch(session, "What is a split?", step="c2")
    thread = thread_of(state)["id"]
    state = act(session, "say", text="Thanks, next question")
    assert thread_of(state)["outcome"] == "dead"
    assert [each["reason"] for each in events(session, "you.branch_dead")] == ["moved_on"]
    state = act(session, "side", text="One more thing?", thread=thread)
    assert thread_of(state)["outcome"] == "open"
    assert [each["thread"] for each in events(session, "you.branch_reopened")] == [thread]
    valid(state)


def test_a_plan_proposal_whose_revision_fails_is_failed_and_the_branch_stays_open(make):
    plan = call("propose_change", kind="plan", step="c2", words="split it in three equal parts")
    session = answered(make, side=[plan, reply("Proposed.")], main_after=[reply("I will not write a plan.")])
    state = branch(session, "Please split it in three equal parts", step="c2")
    found = thread_of(state)["proposal"]
    assert found["change"] == {"kind": "plan", "step": "c2", "words": "split it in three equal parts"}
    assert found["impact"]["steps"] == ["c2"] and found["impact"]["downstream"] == ["c3", "j1"]
    state = act(session, "accept_proposal", proposal=found["id"])
    found = thread_of(state)
    assert found["proposal"]["status"] == "failed" and found["proposal"]["reason"]
    assert found["outcome"] == "open" and found["messages"][-1]["who"] == "harness"
    valid(state)


# --- Replay ---

def test_the_branches_expectation_counts_side_branches_by_outcome_and_node_kind(make):
    from harness.needs_you.layer import LAYER
    expect = LAYER.expects["branches"]
    assert expect.validate({"joined": 1, "dead": 0, "nodes": ["value"]}) is None
    assert expect.validate({"joined": -1}) and expect.validate({"nodes": ["nope"]}) and expect.validate([])
    session = answered(make, side=[propose(), reply("Proposed.")])
    state = branch(session, "No, we need 50 units.", chip(session.state(), "value", "Unit count")["subject"])
    assert not expect.check({"joined": 1}, session)["passed"]
    act(session, "accept_proposal", proposal=thread_of(state)["proposal"]["id"])
    assert expect.check({"joined": 1, "dead": 0, "nodes": ["value"]}, session)["passed"]
    assert not expect.check({"nodes": ["plan_revised"]}, session)["passed"]
