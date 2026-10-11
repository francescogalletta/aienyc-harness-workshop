"""SPEC 3.3: changing an accepted plan."""
import json
from pathlib import Path

from layer1_helpers import SETTLE, asks, item, looks_up, small_brief, write_brief

from harness.config import load_config
from harness.grounding import revise_plan
from harness.grounding.revise import PLAN_CHANGED
from harness.grounding.layer import LAYER


def accepted_session(open_session, script, brief=None):
    """A session whose brief folder already holds an accepted plan, and the changes the hook saw."""
    folder = Path(load_config().brief_dir)
    folder.mkdir(parents=True, exist_ok=True)
    brief = brief or small_brief()
    (folder / "domain_brief.json").write_text(json.dumps({**brief, "meta": {
        "status": "confirmed", "session_id": "x", "lookups": [{"query": "sinking fund", "found": True,
        "sources": [{"title": "Sinking fund (Example)", "url": "https://example.test/sinking-fund"}]}],
        "revisions": []}}), encoding="utf-8")
    session = open_session(script)
    seen = []
    session.layers[1] = type(LAYER)(**{**LAYER.__dict__, "hooks": {"plan_changed": lambda work, changed: seen.append(changed)}})
    return session, seen


def revise(session, **options):
    done = []
    session.queue("main", lambda work: done.append(revise_plan(work, **options)), what="answer")
    session.settle(SETTLE)
    return done[0]


def test_a_revision_saves_the_new_plan_records_it_and_lists_the_steps_that_changed(open_session):
    new = small_brief()
    new["process"][0]["formula"] = "van hire + rent + deposit"
    new["process"].append({"id": "a3", "name": "Extra", "kind": "judgment", "method": "", "formula": "",
                           "needs": ["a2"], "produces": "x", "cadence": "", "origin": {"kind": "proposed"}})
    session, seen = accepted_session(open_session, [write_brief(new)])
    result = revise(session, words="include the deposit", step="a1", by="person")
    assert result == {"changed": ["a1", "a3"], "node": "n2"}
    state = session.state()
    assert [step["id"] for step in state["steps"]] == ["a1", "a2", "a3"] and state["phase"] == "accepted"
    assert state["steps"][0]["formula"] == "van hire + rent + deposit"
    [revision] = state["context"]["revisions"]
    assert (revision["words"], revision["step"], revision["by"]) == ("include the deposit", "a1", "person")
    assert seen == [["a1", "a3"]]
    *_, told = state["chat"]
    assert (told["who"], told["text"]) == ("harness", PLAN_CHANGED.format(changes="added step 3 Extra; changed step 1 Move cost"))
    sent = session.script.calls[0]["messages"][0]["content"]
    assert "include the deposit" in sent and "a1" in sent
    assert json.loads((Path(load_config().brief_dir) / "domain_brief.json").read_text())["meta"]["status"] == "confirmed"


def test_a_removed_step_is_a_changed_step(open_session):
    new = small_brief()
    new["process"].pop()
    new["open_questions"][0]["step"] = None
    session, seen = accepted_session(open_session, [write_brief(new)])
    assert revise(session, words="drop the decision", step=None, by="reviewer") == {"changed": ["a2"], "node": "n2"}
    assert session.state()["context"]["revisions"][0]["by"] == "reviewer"


def test_the_persons_earlier_quotes_in_the_plan_stay_valid_and_new_ones_must_be_theirs(open_session):
    fresh = small_brief()
    fresh["scope"]["out"].append(item("The new flat", {"kind": "person", "quote": "not the new flat"}))
    session, _seen = accepted_session(open_session, [write_brief(fresh)])
    assert revise(session, words="not the new flat, please")["changed"] == []
    invented = small_brief()
    invented["scope"]["out"].append(item("Tax", {"kind": "person", "quote": "words they never wrote"}))
    session, _seen = accepted_session(open_session, [write_brief(invented)] * 3)
    assert revise(session, words="leave out tax")["error"].startswith("the plan was not changed")


def test_a_reply_without_a_brief_is_an_error_and_changes_nothing(open_session):
    session, seen = accepted_session(open_session, [asks("I cannot do that because the step is needed.")])
    result = revise(session, words="remove everything")
    assert result["error"].startswith("the plan was not changed") and "cannot do that" in result["error"]
    assert seen == [] and session.state()["context"]["revisions"] == []


def test_a_revision_can_look_a_term_up(open_session, researcher):
    session, _seen = accepted_session(open_session, [looks_up("Opening Balance"), write_brief()])
    assert revise(session, words="use the opening balance") == {"changed": [], "node": "n2"}
    assert researcher.asked == ["Opening Balance"]


def test_with_no_accepted_plan_there_is_nothing_to_change(open_session):
    assert "error" in revise(open_session([]), words="anything")


def test_what_changed_is_said_by_the_harness_from_the_two_plans():
    from harness.grounding.brief import describe_changes
    old = small_brief()
    new = small_brief()
    new["process"][1]["name"] = "Decide now"
    new["process"].append({"id": "a3", "name": "Extra", "kind": "judgment", "method": "", "formula": "",
                           "needs": ["a2"], "produces": "x", "cadence": "", "origin": {"kind": "proposed"}})
    assert describe_changes(old, new) == "added step 3 Extra; changed step 2 Decide now"
    assert describe_changes(new, old) == "changed step 2 Keep the date?; removed step 3 Extra"
    assert describe_changes(old, {**old, "goal": item("Another goal")}) == "no step changed; the goal did"
    assert describe_changes(old, old) == "nothing changed"


def test_a_revision_records_a_plan_revised_node_of_the_person_touching_the_changed_steps(open_session):
    new = small_brief()
    new["process"][0]["formula"] = "van hire + rent + deposit"
    session, _seen = accepted_session(open_session, [write_brief(new)])
    revise(session, words="include the deposit", step="a1")
    _accepted, node = session.state()["history"]["trunk"]
    assert (node["who"], node["kind"], node["branch"]) == ("you", "plan_revised", None)
    assert node["change"] == {"step": "a1", "words": "include the deposit", "changed": ["a1"]}
    assert node["touched"] == {"inputs": [], "steps": ["a1"]} and node["text"].startswith("Plan changed: ")
    assert len(node["text"]) <= 80 and node["after"] == session.state()["chat"][-1]["id"]
    assert session.state()["steps"][0]["changed_by"] == node["id"]


def test_a_reviewers_revision_is_the_reviewers_node(open_session):
    new = small_brief()
    new["process"].pop()
    new["open_questions"][0]["step"] = None
    session, _seen = accepted_session(open_session, [write_brief(new)])
    revise(session, words="drop the decision", by="reviewer")
    _accepted, node = session.state()["history"]["trunk"]
    assert (node["who"], node["kind"]) == ("reviewer", "plan_revised")


def test_a_revision_from_a_branch_joins_that_branch(open_session):
    from harness.core import add_thread, list_threads
    new = small_brief()
    new["process"][0]["formula"] = "van hire + rent + deposit"
    session, _seen = accepted_session(open_session, [write_brief(new)])
    thread = add_thread(session.conn, session.conversation, kind="side", title="the deposit", step="a1")
    result = revise(session, words="include the deposit", step="a1", branch=thread)
    state = session.state()
    [branch] = list_threads(session.conn, session.conversation)
    assert branch["outcome"] == "joined" and branch["node"] == result["node"]
    assert state["history"]["trunk"][1]["branch"] == thread


def test_a_revision_that_changes_nothing_records_no_node(open_session):
    session, _seen = accepted_session(open_session, [{"text": "I would not change that."}])
    assert "error" in revise(session, words="include the deposit")
    assert [node["kind"] for node in session.state()["history"]["trunk"]] == ["plan_accepted"]   # the one found on load
