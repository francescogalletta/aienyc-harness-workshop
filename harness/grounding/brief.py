"""The domain brief: its shape, the checks it must pass, and how it is written out (SPEC 4.3).

The model proposes a brief. This file decides whether it is acceptable, and
turns an accepted one into the two files every later step reads. None of
this involves a model.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

KINDS = ("calculation", "judgment", "input")
ARITHMETIC = "arithmetic"       # the method of a calculation with no finance method behind it
MODES = ("ongoing", "one_off")

_TEXT = {"type": "string"}
_TEXT_LIST = {"type": "array", "items": _TEXT}

# The shape of a brief, as JSON Schema. It is what the model is asked to fill in.
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string", "description": "One sentence, in standard terms."},
        "mode": {"type": "string", "enum": list(MODES),
                 "description": "ongoing: something to keep on top of. one_off: answered once."},
        "scope": {"type": "object",
                  "properties": {"in": _TEXT_LIST, "out": _TEXT_LIST}, "required": ["in", "out"]},
        "glossary": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "The standard name."},
                "definition": _TEXT,
                "person_says": {"type": "string",
                                "description": "The words this person uses for it, or empty."},
                "source": {"type": "string",
                           "description": "Address of a source returned by look_up, or empty."}},
            "required": ["term", "definition"]}},
        "particulars": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "How this person differs from the standard case."},
                "handling": {"type": "string", "description": "The agreed way to handle it."}},
            "required": ["what", "handling"]}},
        "inputs": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": _TEXT, "description": _TEXT}, "required": ["name", "description"]}},
        "process": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Short and unique, such as s1."},
                "name": _TEXT,
                "kind": {"type": "string", "enum": list(KINDS)},
                "method": {"type": "string",
                           "description": ("For a calculation: the glossary term it applies, or "
                                           "'arithmetic' when it is plain arithmetic.")},
                "formula": {"type": "string",
                            "description": "For a calculation: how it is worked out, in one plain line."},
                "needs": {"type": "array", "items": _TEXT,
                          "description": "Ids of other steps, or names of inputs."},
                "produces": _TEXT,
                "cadence": {"type": "string", "description": "How often it runs, such as monthly."}},
            "required": ["id", "name", "kind", "needs", "produces"]}},
        "definition_of_done": _TEXT_LIST,
        "open_questions": _TEXT_LIST,
    },
    "required": ["goal", "mode", "scope", "glossary", "particulars", "inputs", "process",
                 "definition_of_done", "open_questions"],
}


def validate_brief(brief, lookups: list[dict]) -> list[str]:
    """Return what is wrong with a proposed brief. An empty list means it is acceptable.

    `lookups` are the lookups made in this interview. A brief may only cite
    sources that one of them returned.
    """
    if not isinstance(brief, dict):
        return ["the brief must be an object"]
    errors = []

    for key in BRIEF_SCHEMA["required"]:
        if key not in brief:
            errors.append(f"missing: {key}")
    if errors:
        return errors

    if not _is_text(brief["goal"]):
        errors.append("goal must be a non-empty sentence")
    if brief["mode"] not in MODES:
        errors.append(f"mode must be one of: {', '.join(MODES)}")
    scope = brief["scope"]
    if not isinstance(scope, dict) or not _is_text_list(scope.get("in")) or not scope.get("in"):
        errors.append("scope.in must list at least one thing that is in scope")
    elif not _is_text_list(scope.get("out")):
        errors.append("scope.out must be a list (it may be empty)")
    for key in ("definition_of_done", "open_questions"):
        if not _is_text_list(brief[key]):
            errors.append(f"{key} must be a list of sentences")
    if _is_text_list(brief["definition_of_done"]) and not brief["definition_of_done"]:
        errors.append("definition_of_done must say at least one way the person will know it works")
    for key in ("glossary", "particulars", "inputs", "process"):
        if not isinstance(brief[key], list) or not all(isinstance(item, dict) for item in brief[key]):
            errors.append(f"{key} must be a list of objects")
    if errors:
        return errors

    # Glossary: every source must be one a lookup really returned.
    known_sources = {source["url"] for lookup in lookups for source in lookup.get("sources", [])}
    sourced_terms, all_terms = set(), set()
    for entry in brief["glossary"]:
        term = entry.get("term")
        if not _is_text(term) or not _is_text(entry.get("definition")):
            errors.append("every glossary entry needs a term and a definition")
            continue
        all_terms.add(_plain(term))
        source = entry.get("source") or ""
        if source and source not in known_sources:
            errors.append(f"glossary term '{term}': the source {source} did not come from a look_up "
                          "in this interview; look the term up and use a source it returns")
        elif source:
            sourced_terms.add(_plain(term))

    for item in brief["particulars"]:
        if not _is_text(item.get("what")) or not _is_text(item.get("handling")):
            errors.append("every particular needs both 'what' and 'handling'")
    input_names = []
    for item in brief["inputs"]:
        if not _is_text(item.get("name")) or not _is_text(item.get("description")):
            errors.append("every input needs a name and a description")
        else:
            input_names.append(item["name"])
    if len(set(input_names)) != len(input_names):
        errors.append("input names must be unique")

    # Process: steps link to each other and to inputs, and a calculation
    # must apply a standard method that was looked up.
    if not brief["process"]:
        errors.append("process must have at least one step")
    ids = [step.get("id") for step in brief["process"]]
    if len(set(ids)) != len(ids):
        errors.append("process step ids must be unique")
    for step in brief["process"]:
        label = f"process step '{step.get('id')}'"
        if not _is_text(step.get("id")) or not _is_text(step.get("name")) or not _is_text(step.get("produces")):
            errors.append(f"{label}: needs an id, a name and what it produces")
        if step.get("kind") not in KINDS:
            errors.append(f"{label}: kind must be one of: {', '.join(KINDS)}")
        needs = step.get("needs")
        if not _is_text_list(needs):
            errors.append(f"{label}: needs must be a list")
        else:
            for need in needs:
                if need not in ids and need not in input_names:
                    errors.append(f"{label}: needs '{need}', which is neither a step id nor an input name")
                elif need == step.get("id"):
                    errors.append(f"{label}: cannot need itself")
        if step.get("kind") == "calculation":
            method = step.get("method") or ""
            if not _is_text(step.get("formula")):
                errors.append(f"{label}: a calculation must give its formula in one plain line")
            if _plain(method) == ARITHMETIC:
                pass        # plain arithmetic needs no finance method behind it
            elif _plain(method) not in all_terms:
                errors.append(f"{label}: a calculation must name its method: a glossary term, or "
                              f"'{ARITHMETIC}' for plain arithmetic (got '{method}')")
            elif _plain(method) not in sourced_terms:
                errors.append(f"{label}: its method '{method}' has no source; look it up and give the "
                              "glossary entry a source that look_up returned")
    return errors


def render_brief(brief: dict, meta: dict) -> str:
    """The brief as a page a person can read. Same brief in, same page out."""
    lines = ["# Domain brief", ""]
    status = "Confirmed by the person" if meta.get("status") == "confirmed" else "Draft, not confirmed"
    lines += [f"{status}. Written {meta.get('written_at', '')}. Interview session `{meta.get('session_id', '')}`.", ""]
    if meta.get("errors"):
        lines += ["This draft did not pass the harness checks:", ""]
        lines += [f"- {error}" for error in meta["errors"]] + [""]

    mode = "ongoing" if brief.get("mode") == "ongoing" else "one-off"
    lines += ["## Goal", "", f"{brief.get('goal', '')} ({mode})", ""]

    scope = brief.get("scope") or {}
    lines += ["## Scope", "", "In scope:", ""] + [f"- {item}" for item in scope.get("in", [])]
    lines += ["", "Out of scope:", ""] + ([f"- {item}" for item in scope.get("out", [])] or ["- nothing listed"]) + [""]

    lines += ["## Glossary", "", "| Standard term | Meaning | You call it | Source |", "| --- | --- | --- | --- |"]
    for entry in brief.get("glossary", []):
        source = f"[source]({entry['source']})" if entry.get("source") else "not looked up"
        lines.append(f"| {_cell(entry.get('term'))} | {_cell(entry.get('definition'))} "
                     f"| {_cell(entry.get('person_says'))} | {source} |")
    lines.append("")

    lines += ["## What is particular to you", ""]
    if brief.get("particulars"):
        lines += ["| What is different | How it is handled |", "| --- | --- |"]
        lines += [f"| {_cell(item.get('what'))} | {_cell(item.get('handling'))} |" for item in brief["particulars"]]
    else:
        lines.append("Nothing recorded.")
    lines.append("")

    lines += ["## Inputs", ""]
    lines += [f"- **{item.get('name')}**: {item.get('description')}" for item in brief.get("inputs", [])] or ["None listed."]
    lines.append("")

    lines += ["## Process", "", "| Step | Kind | Method | Formula | Needs | Produces | How often |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for step in brief.get("process", []):
        lines.append(f"| {_cell(step.get('id'))}: {_cell(step.get('name'))} | {_cell(step.get('kind'))} "
                     f"| {_cell(step.get('method'))} | {_cell(step.get('formula'))} "
                     f"| {_cell(', '.join(step.get('needs') or []))} "
                     f"| {_cell(step.get('produces'))} | {_cell(step.get('cadence'))} |")
    lines += ["", "Steps marked `calculation` must run as tested code.", "", *_diagram(brief), ""]

    lines += ["## Definition of done", ""] + [f"- [ ] {item}" for item in brief.get("definition_of_done", [])] + [""]
    lines += ["## Open questions", ""] + ([f"- {item}" for item in brief.get("open_questions", [])] or ["None."]) + [""]
    return "\n".join(lines)


def summarise_brief(brief: dict) -> str:
    """The brief as plain text, short enough to read in a terminal before confirming."""
    mode = "ongoing" if brief["mode"] == "ongoing" else "one-off"
    lines = ["", "PROPOSED BRIEF", "", f"Goal ({mode}): {brief['goal']}", "", "In scope:"]
    lines += [f"  - {item}" for item in brief["scope"]["in"]]
    lines += ["Out of scope:"] + ([f"  - {item}" for item in brief["scope"]["out"]] or ["  - nothing listed"])
    lines += ["", "Terms we agreed:"]
    for entry in brief["glossary"]:
        yours = f" (you call it: {entry['person_says']})" if entry.get("person_says") else ""
        checked = "" if entry.get("source") else " [not looked up]"
        lines.append(f"  - {entry['term']}{yours}: {entry['definition']}{checked}")
    lines += ["", "What is particular to you:"]
    lines += [f"  - {item['what']} -> {item['handling']}" for item in brief["particulars"]] or ["  - nothing recorded"]
    lines += ["", "Data you have:"] + [f"  - {item['name']}: {item['description']}" for item in brief["inputs"]]
    lines += ["", "Steps:"]
    for step in brief["process"]:
        needs = f" (needs: {', '.join(step['needs'])})" if step["needs"] else ""
        lines.append(f"  - {step['id']} [{step['kind']}] {step['name']}{needs} -> {step['produces']}")
        if step["kind"] == "calculation":
            lines.append(f"      method: {step.get('method')}; formula: {step.get('formula')}")
    lines += ["", "You will know it works when:"] + [f"  - {item}" for item in brief["definition_of_done"]]
    if brief["open_questions"]:
        lines += ["", "Still open:"] + [f"  - {item}" for item in brief["open_questions"]]
    return "\n".join(lines) + "\n"


def _diagram(brief: dict) -> list[str]:
    """A Mermaid flowchart of inputs and steps: what feeds what, and what is code."""
    names = {}
    lines = ["```mermaid", "flowchart TD"]
    for number, item in enumerate(brief.get("inputs", []), start=1):
        names[item.get("name")] = f"in{number}"
        lines.append(f'    in{number}(["{_label(item.get("name"))}"]):::input')
    for number, step in enumerate(brief.get("process", []), start=1):
        names[step.get("id")] = f"st{number}"
        lines.append(f'    st{number}["{_label(step.get("name"))}"]:::{step.get("kind")}')
    for step in brief.get("process", []):
        for need in step.get("needs") or []:
            if need in names:
                lines.append(f"    {names[need]} --> {names[step.get('id')]}")
    lines += ["    classDef calculation stroke-width:3px",
              "    classDef judgment stroke-dasharray:5 5",
              "    classDef input stroke-dasharray:2 2",
              "```",
              "",
              "Thick border: calculation (code). Dashed: judgment. Dotted: input from you."]
    return lines


def save_brief(brief: dict, folder, meta: dict) -> tuple[Path, Path]:
    """Write domain_brief.json and domain_brief.md into `folder`. Return both paths."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta}
    json_path, page_path = folder / "domain_brief.json", folder / "domain_brief.md"
    json_path.write_text(json.dumps({**brief, "meta": meta}, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    page_path.write_text(render_brief(brief, meta), encoding="utf-8")
    return json_path, page_path


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _plain(text: str) -> str:
    return " ".join(str(text).lower().replace("-", " ").replace("_", " ").split())


def _cell(value) -> str:
    """Text made safe for one table cell."""
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _label(value) -> str:
    """Text made safe for a diagram label."""
    return " ".join(str(value or "").split()).replace('"', "'")
