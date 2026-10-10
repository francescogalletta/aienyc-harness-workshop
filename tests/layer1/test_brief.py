"""SPEC 3.1: the version 2 brief, its checks, how it is drawn as state, and written out."""
import json

import pytest
from conftest import EXAMPLES
from layer1_helpers import PROPOSED, item, small_brief

from harness.grounding import (ResearchDesk, draw, input_ids, load_brief, person_quotes, save_brief,
                               step_fingerprint, validate_brief)

LOOKUPS = [{"sources": [{"title": "Sinking fund (Example)", "url": "https://example.test/sinking-fund"}]}]
WORDS = ["I want to save for a move next spring"]


def errors(brief, words=WORDS, lookups=LOOKUPS):
    return validate_brief(brief, lookups, words)


@pytest.mark.parametrize("name", ["wedding", "moving"])
def test_the_example_briefs_are_valid_version_2_briefs(name):
    brief = json.loads((EXAMPLES / name / "brief" / "domain_brief.json").read_text(encoding="utf-8"))
    found = validate_brief(brief, brief["meta"]["lookups"], person_quotes(brief))
    assert found == []


def test_a_small_valid_brief_passes_and_a_missing_key_does_not():
    assert errors(small_brief()) == []
    broken = small_brief()
    del broken["definition_of_done"]
    assert errors(broken)


def test_a_person_origin_must_quote_what_they_wrote():
    quoted = lambda quote: small_brief(goal=item("A goal", {"kind": "person", "quote": quote}))   # noqa: E731
    assert errors(quoted("SAVE   for a MOVE")) == []                # case and white space do not matter
    assert errors(quoted("buy a house"))                            # not theirs
    assert errors(quoted("ab"))                                     # too short to be a quote
    assert errors(quoted("save for a move"), words=[])              # they have said nothing


def test_an_origin_needs_a_known_kind_and_a_source_that_was_looked_up():
    assert errors(small_brief(goal=item("A goal", {"kind": "guessed"})))
    assert errors(small_brief(goal=item("A goal", {"kind": "looked_up", "source": "https://example.test/else"})))
    assert errors(small_brief(goal={"text": "A goal"}))             # no origin at all


def test_a_step_link_must_be_a_process_id_or_null():
    brief = small_brief()
    brief["open_questions"][0]["step"] = "zz"
    assert errors(brief)
    brief = small_brief()
    brief["particulars"][0]["step"] = "zz"
    assert errors(brief)


def test_version_1_checks_are_kept():
    brief = small_brief()
    brief["process"][0]["needs"] = ["Nothing like it"]
    assert errors(brief)
    brief = small_brief()
    brief["process"][0]["method"] = "Invented method"
    assert errors(brief)


def test_draw_gives_the_layer_1_part_of_the_state_document(moving_brief):
    part = draw(moving_brief, moving_brief["meta"]["lookups"])
    assert set(part) == {"goal", "context", "inputs", "steps", "edges"}
    assert part["goal"]["mode"] == "ongoing" and part["goal"]["origin"] == PROPOSED
    first, second, _third, last = part["steps"]
    assert (first["id"], first["number"], first["kind"], first["in_plan"]) == ("m1", 1, "calculation", True)
    assert last["kind"] == "your_call"
    assert second["needs"] == ["m1", "in:savings_so_far", "in:months_until_the_move"]
    assert second["inputs"] == ["in:savings_so_far", "in:months_until_the_move"]
    assert {"from": "m1", "to": "m2"} in part["edges"]
    assert not any(edge["from"].startswith("in:") for edge in part["edges"])
    assert second["origin"] == {"kind": "looked_up", "source": {
        "title": "Sinking fund (Wikipedia)", "url": "https://en.wikipedia.org/wiki/Sinking_fund"}}
    assert [each["origin"]["kind"] for each in first["particulars"]] == ["proposed", "person"]
    assert first["particulars"][0].keys() == {"text", "handling", "origin"}
    assert len(first["open_questions"]) == 3
    assert part["inputs"]["in:deposit"]["steps"] == ["m1"]
    assert set(part["inputs"]["in:deposit"]) == {"id", "name", "description", "origin", "steps"}


def test_whole_plan_particulars_and_questions_go_to_the_context():
    part = draw(small_brief())
    context = part["context"]
    assert [each["text"] for each in context["assumptions"]] == ["Figures are in euros"]
    assert context["assumptions"][0]["handling"]
    assert [each["text"] for each in context["open_questions"]] == ["Is there a second van?"]
    assert [each["text"] for each in part["steps"][0]["particulars"]] == ["Rent is paid twice for a month"]
    assert context["glossary"][0]["origin"]["kind"] == "looked_up"
    assert set(context) == {"scope_in", "scope_out", "assumptions", "done", "open_questions", "glossary",
                            "revisions"}


def test_input_ids_are_the_name_lower_cased_with_runs_of_non_letters_as_underscores():
    brief = small_brief(inputs=[{"name": "Guest count", "description": "d", "origin": PROPOSED},
                                {"name": "Guest  count!", "description": "d", "origin": PROPOSED}])
    assert list(input_ids(brief).values()) == ["in:guest_count", "in:guest_count_2"]


def test_a_steps_fingerprint_follows_its_substance_not_its_name():
    brief = small_brief()
    before = step_fingerprint(brief, "a1")
    brief["process"][0]["name"] = "Another name"
    assert step_fingerprint(brief, "a1") == before
    brief["process"][0]["formula"] = "van hire"
    assert step_fingerprint(brief, "a1") != before
    changed = step_fingerprint(brief, "a1")
    brief["particulars"][0]["handling"] = "Leave it out"
    assert step_fingerprint(brief, "a1") != changed
    assert step_fingerprint(brief, "nope") is None


def test_save_brief_writes_the_json_and_page_and_load_brief_reads_only_confirmed(tmp_path):
    folder = tmp_path / "brief"
    json_path, page_path = save_brief(small_brief(), folder, {"session_id": "x", "lookups": [], "status": "confirmed"})
    assert json_path.exists() and page_path.read_text(encoding="utf-8").startswith("# Domain brief")
    assert load_brief(folder)["meta"]["revisions"] == []
    save_brief(small_brief(), folder, {"status": "draft"})
    assert load_brief(folder) is None
    assert load_brief(tmp_path / "nowhere") is None


def test_the_desk_refuses_a_general_query_with_a_digit_or_too_long_before_any_request(researcher, tmp_path):
    from harness import db
    conn = db.connect(tmp_path / "desk.db")
    from harness.layers import BASE
    from harness.grounding.layer import LAYER
    db.apply_schemas(conn, [BASE, LAYER])
    desk = ResearchDesk(researcher, conn)
    for query in ("what is 5 percent of rent", "x" * 101, "one two three four five six seven eight nine ten eleven twelve thirteen"):
        assert desk.look_up_general(query)["status"] == "failed"
    assert researcher.asked == []
    assert desk.look_up_general("sinking fund")["status"] == "found"


def test_an_input_that_no_step_uses_is_refused_and_the_error_says_how_to_attach_it():
    brief = small_brief()
    brief["process"][0]["needs"] = []                               # "Van hire" now feeds nothing
    found = errors(brief)
    assert len(found) == 1 and "'Van hire' is used by no step" in found[0] and "needs" in found[0]


def test_needs_that_name_neither_an_input_nor_an_earlier_step_are_refused_with_the_valid_names():
    brief = small_brief()
    brief["process"][0]["needs"] = ["Van hire", "a2"]               # a2 comes later
    assert any("comes later" in each for each in errors(brief))
    brief["process"][0]["needs"] = ["Van hire", "van-hire-step"]
    found = errors(brief)
    assert len(found) == 1 and "step ids: a1, a2" in found[0] and "input names: Van hire" in found[0]


def test_a_quote_of_other_words_is_refused_even_on_a_calculation_step():
    brief = small_brief()
    brief["process"][0]["origin"] = {"kind": "person", "quote": "the total of the move"}
    assert any("is not in anything the person wrote" in each for each in errors(brief))
