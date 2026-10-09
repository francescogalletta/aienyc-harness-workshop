"""SPEC 5.5 and 5.7: who receives the notes. The spec writer does; no other role of the build does."""
import step2_helpers as h
from step2_helpers import (REVISED_PY, REVISED_TESTS, built, months_script, only_step, propose_examples, propose_spec,
                           respond, revised_examples, revised_spec, saved_spec, sections, surplus_script, write_module)

EARLIER = "EARLIER-MARKER I keep 4242 aside"
FEEDBACK = "FEEDBACK-MARKER I have a list of costs"
HELPER = "HELPER-MARKER I pay 450 a month for the van"


def test_the_spec_writer_gets_every_note_from_every_session_oldest_first(build, conn, notes):
    notes.add_note(conn, step_id="s3", text="said at the later step", session_id="one")
    notes.add_note(conn, step_id="s1", text="said at the first step", session_id="two")
    brief = only_step("s1")
    _, model, _ = build(surplus_script(), built(), brief=brief)
    assert model.calls[0]["messages"][0]["content"] == sections(
        ("step", brief["process"][0]), ("brief", brief), ("registered modules", []),
        ("notes", [{"step": "s3", "text": "said at the later step"}, {"step": "s1", "text": "said at the first step"}]))


def test_the_notes_come_before_the_current_spec_on_a_rebuild(build, conn, notes):
    h.install_surplus(conn, step_id="s1")
    notes.add_note(conn, step_id="s1", text="a note", session_id="one")
    brief = only_step("s1")
    _, model, _ = build(surplus_script(), built(), brief=brief, rebuild="monthly_surplus")
    assert model.calls[0]["messages"][0]["content"] == sections(
        ("step", brief["process"][0]), ("brief", brief), ("registered modules", []),
        ("notes", [{"step": "s1", "text": "a note"}]), ("current spec", saved_spec(h.surplus_spec(), "s1")))


def two_steps(build, conn, notes):
    """Step s1 gets a note at the plan check and one from the helper; then step s3 is built. Returns the model."""
    notes.add_note(conn, step_id="s0", text=EARLIER, session_id="earlier")
    script = [propose_spec(), propose_spec(revised_spec()), propose_examples(revised_examples()), respond("note"),
              write_module(REVISED_PY, REVISED_TESTS), *months_script()]
    answers = [FEEDBACK, "yes", HELPER, "/accept", "/accept", "/accept", *built()]
    results, model, _ = build(script, answers)
    assert [r["outcome"] for r in results] == ["built", "built"]
    return model


def test_notes_saved_in_one_step_reach_the_spec_writer_of_the_next(build, conn, notes):
    model = two_steps(build, conn, notes)
    content = h.phase_calls(model, "spec_writer.md")[-1]["messages"][0]["content"]
    assert content.endswith(sections(("notes", [
        {"step": "s0", "text": EARLIER}, {"step": "s1", "text": FEEDBACK}, {"step": "s1", "text": HELPER}])))


def test_no_note_reaches_the_example_writer_or_the_code_writer(build, conn, notes):
    model = two_steps(build, conn, notes)
    for prompt in ("example_writer.md", "module_writer.md"):
        calls = h.phase_calls(model, prompt)
        assert len(calls) == 2
        for call in calls:
            text = call["system"] + str(call["messages"])
            for marker in ("EARLIER-MARKER", "FEEDBACK-MARKER", "HELPER-MARKER", "4242", "450"):
                assert marker not in text, (prompt, marker)


def test_the_example_helper_gets_only_what_was_said_about_its_example(build, conn, notes):
    model = two_steps(build, conn, notes)
    [call] = h.phase_calls(model, "example_helper.md")
    text = call["system"] + call["messages"][0]["content"]
    assert "EARLIER-MARKER" not in text and "FEEDBACK-MARKER" not in text and HELPER in text


def test_the_plan_feedback_reaches_the_writer_as_the_tool_result_and_not_in_its_first_message(build, conn, notes):
    model = two_steps(build, conn, notes)
    first, second = h.phase_calls(model, "spec_writer.md")[:2]
    assert FEEDBACK not in first["messages"][0]["content"] and FEEDBACK in second["messages"][-1]["content"]
