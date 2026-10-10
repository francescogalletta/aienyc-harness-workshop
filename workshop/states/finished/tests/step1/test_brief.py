"""SPEC 4.3: the brief's checks and how it is written out."""
import json

from harness.grounding import render_brief, save_brief, summarise_brief, validate_brief

from step1_helpers import SOURCE, lookups_made, make_brief


def errors_for(**changes):
    return validate_brief(make_brief(**changes), lookups_made())


def test_a_complete_brief_passes():
    assert validate_brief(make_brief(), lookups_made()) == []


def test_missing_parts_are_named():
    brief = make_brief()
    del brief["glossary"], brief["definition_of_done"]
    assert validate_brief(brief, lookups_made()) == ["missing: glossary", "missing: definition_of_done"]
    assert validate_brief("not a brief", lookups_made()) == ["the brief must be an object"]


def test_a_source_must_come_from_a_lookup_in_this_interview():
    """No invented citations: a source the researcher never returned is refused."""
    glossary = make_brief()["glossary"]
    glossary[0] = {**glossary[0], "source": "https://example.org/made-up"}
    found = errors_for(glossary=glossary)
    assert any("https://example.org/made-up" in e and "look_up" in e for e in found)
    # The same brief is refused when no lookup was made at all.
    assert any(SOURCE in e for e in validate_brief(make_brief(), []))


def test_a_calculation_must_apply_a_looked_up_method_or_be_plain_arithmetic():
    def with_step(**changes):
        process = make_brief()["process"]
        process[2] = {**process[2], **changes}
        return errors_for(process=process)

    assert with_step() == []
    assert any("'s3'" in e and "method" in e for e in with_step(method="my own trick"))
    assert any("'s3'" in e and "method" in e for e in with_step(method=""))
    # "Typical month" is in the glossary but was never looked up.
    assert any("'s3'" in e and "no source" in e for e in with_step(method="Typical month"))
    assert any("'s3'" in e and "formula" in e for e in with_step(formula=""))
    assert with_step(method="Arithmetic") == []
    # Judgment and input steps need neither.
    assert with_step(kind="judgment", method="", formula="") == []


def test_steps_must_link_to_real_things():
    def with_step(index, **changes):
        process = make_brief()["process"]
        process[index] = {**process[index], **changes}
        return errors_for(process=process)

    assert any("'s3'" in e and "'s9'" in e for e in with_step(2, needs=["s9"]))
    assert any("cannot need itself" in e for e in with_step(2, needs=["s3"]))
    assert any("unique" in e for e in with_step(1, id="s1"))
    assert any("kind" in e for e in with_step(0, kind="magic"))
    assert any("produces" in e for e in with_step(0, produces=""))
    inputs = [{"name": "Bank export", "description": "one"}, {"name": "Bank export", "description": "two"}]
    assert any("input names must be unique" in e for e in errors_for(inputs=inputs))


def test_the_page_is_built_by_code_and_is_always_the_same():
    meta = {"status": "confirmed", "session_id": "abc123", "written_at": "2026-10-09T10:00:00+00:00"}
    page = render_brief(make_brief(), meta)
    assert page == render_brief(make_brief(), meta)
    assert page.startswith("# Domain brief\n")
    assert "Confirmed by the person" in page and "abc123" in page
    for heading in ("## Goal", "## Scope", "## Glossary", "## What is particular to you", "## Inputs",
                    "## Process", "## Definition of done", "## Open questions"):
        assert heading in page, heading
    assert f"[source]({SOURCE})" in page and "not looked up" in page
    assert "closing balance = opening balance + money in - money out" in page

    # The diagram shows what feeds what, and which steps are code.
    diagram = page.split("```mermaid\n")[1].split("```")[0]
    assert diagram.startswith("flowchart TD\n")
    assert 'in1(["Bank export"]):::input' in diagram
    assert 'st3["Forecast the balance month by month"]:::calculation' in diagram
    assert 'st2["Decide which payments are regular"]:::judgment' in diagram
    assert "in1 --> st3" in diagram and "st1 --> st3" in diagram and "st3 --> st4" in diagram

    draft = render_brief(make_brief(), {"status": "draft", "errors": ["process step 's3': something"]})
    assert "Draft, not confirmed" in draft and "- process step 's3': something" in draft


def test_saving_writes_both_files(tmp_path):
    json_path, page_path = save_brief(make_brief(), tmp_path / "out",
                                      {"status": "confirmed", "session_id": "abc123", "lookups": lookups_made()})
    assert json_path == tmp_path / "out" / "domain_brief.json"
    assert page_path == tmp_path / "out" / "domain_brief.md"
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["goal"] == make_brief()["goal"]
    assert saved["meta"]["status"] == "confirmed" and saved["meta"]["session_id"] == "abc123"
    assert saved["meta"]["lookups"] == lookups_made() and saved["meta"]["written_at"]
    assert page_path.read_text(encoding="utf-8").startswith("# Domain brief\n")
