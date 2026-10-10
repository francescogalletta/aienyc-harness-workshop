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


def two_steps(build, conn, notes):
    """Step s1 gets a note at the plan check and one from the helper; then step s3 is built. Returns the model."""
    notes.add_note(conn, step_id="s0", text=EARLIER, session_id="earlier")
    script = [propose_spec(), propose_spec(revised_spec()), propose_examples(revised_examples()), respond("note"),
              write_module(REVISED_PY, REVISED_TESTS), *months_script()]
    answers = [FEEDBACK, "yes", HELPER, "/accept", "/accept", "/accept", *built()]
    results, model, _ = build(script, answers)
    assert [r["outcome"] for r in results] == ["built", "built"]
    return model


def test_no_note_reaches_the_example_writer_or_the_code_writer(build, conn, notes):
    model = two_steps(build, conn, notes)
    for prompt in ("example_writer.md", "module_writer.md"):
        calls = h.phase_calls(model, prompt)
        assert len(calls) == 2
        for call in calls:
            text = call["system"] + str(call["messages"])
            for marker in ("EARLIER-MARKER", "FEEDBACK-MARKER", "HELPER-MARKER", "4242", "450"):
                assert marker not in text, (prompt, marker)


