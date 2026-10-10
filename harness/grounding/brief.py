"""The version 2 brief: its shape, the checks it must pass, how it is written out, and how it is drawn
as the layer 1 part of the plan state document (SPEC 3.1, ARCHITECTURE.md section 3).

The model proposes a brief. This file decides whether it is acceptable, and turns an accepted one into
the two files every later step reads. None of this involves a model.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

KINDS = ("calculation", "judgment", "input")
ARITHMETIC = "arithmetic"       # the method of a calculation with no finance method behind it
MODES = ("ongoing", "one_off")
ORIGINS = ("person", "looked_up", "proposed")
STATE_KINDS = {"calculation": "calculation", "input": "from_you", "judgment": "your_call"}
MIN_QUOTE = 3

_TEXT = {"type": "string"}
_TEXT_LIST = {"type": "array", "items": _TEXT}
_STEP = {"type": ["string", "null"],
         "description": "The id of the process step this concerns, or null for the whole plan."}
_ORIGIN = {
    "type": "object",
    "description": ("Where this came from: kind 'person' with their exact words in quote; kind 'looked_up' "
                    "with the address a look_up returned in source; or kind 'proposed'."),
    "properties": {"kind": {"type": "string", "enum": list(ORIGINS)}, "quote": _TEXT, "source": _TEXT},
    "required": ["kind"]}


def _item(extra: dict | None = None, required: tuple = ()) -> dict:
    properties = {"text": _TEXT, **(extra or {}), "origin": _ORIGIN}
    return {"type": "object", "properties": properties, "required": ["text", "origin", *required]}


# The shape of a brief, as JSON Schema. It is what the model is asked to fill in.
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": _item(),
        "mode": {"type": "string", "enum": list(MODES),
                 "description": "ongoing: something to keep on top of. one_off: answered once."},
        "scope": {"type": "object",
                  "properties": {"in": {"type": "array", "items": _item()},
                                 "out": {"type": "array", "items": _item()}}, "required": ["in", "out"]},
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
                "handling": {"type": "string", "description": "The agreed way to handle it."},
                "step": _STEP, "origin": _ORIGIN},
            "required": ["what", "handling", "step", "origin"]}},
        "inputs": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": _TEXT, "description": _TEXT, "origin": _ORIGIN},
            "required": ["name", "description", "origin"]}},
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
                "cadence": {"type": "string", "description": "How often it runs, such as monthly."},
                "origin": _ORIGIN},
            "required": ["id", "name", "kind", "needs", "produces", "origin"]}},
        "definition_of_done": {"type": "array", "items": _item()},
        "open_questions": {"type": "array", "items": _item({"step": _STEP}, ("step",))},
    },
    "required": ["goal", "mode", "scope", "glossary", "particulars", "inputs", "process",
                 "definition_of_done", "open_questions"],
}


# --- Checks ---

def validate_brief(brief, lookups: list[dict], words=()) -> list[str]:
    """Return what is wrong with a proposed brief. An empty list means it is acceptable.

    `lookups` are the lookups whose sources the brief may cite. `words` are the person's messages of
    this interview or revision: a `person` origin must quote them.
    """
    if not isinstance(brief, dict):
        return ["the brief must be an object"]
    errors = []

    for key in BRIEF_SCHEMA["required"]:
        if key not in brief:
            errors.append(f"missing: {key}")
    if errors:
        return errors

    known_sources = {source["url"] for lookup in lookups for source in lookup.get("sources", [])}
    spoken = [_spaced(text) for text in words if isinstance(text, str)]

    def origin_errors(item, label) -> None:
        origin = item.get("origin") if isinstance(item, dict) else None
        if not isinstance(origin, dict) or origin.get("kind") not in ORIGINS:
            errors.append(f"{label}: needs an origin of kind {', '.join(ORIGINS)}")
        elif origin["kind"] == "person":
            quote = _spaced(origin.get("quote"))
            if len(quote) < MIN_QUOTE:
                errors.append(f"{label}: a 'person' origin needs the person's own words in quote "
                              f"(at least {MIN_QUOTE} characters)")
            elif not any(quote in text for text in spoken):
                errors.append(f"{label}: the quote \"{origin.get('quote')}\" is not in anything the person "
                              "wrote; copy their words exactly, or mark this item 'proposed'")
        elif origin["kind"] == "looked_up" and origin.get("source") not in known_sources:
            errors.append(f"{label}: the source {origin.get('source')} did not come from a look_up "
                          "in this conversation; look it up and use a source it returns, or mark it 'proposed'")

    def items(value, label) -> None:
        if not isinstance(value, list) or not all(isinstance(each, dict) for each in value):
            errors.append(f"{label} must be a list of items, each with text and origin")
            return
        for number, each in enumerate(value, start=1):
            if not _is_text(each.get("text")):
                errors.append(f"{label} {number}: needs text")
            origin_errors(each, f"{label} {number}")

    goal = brief["goal"]
    if not isinstance(goal, dict) or not _is_text(goal.get("text")):
        errors.append("goal must be an item: one non-empty sentence in text, with an origin")
    else:
        origin_errors(goal, "goal")
    if brief["mode"] not in MODES:
        errors.append(f"mode must be one of: {', '.join(MODES)}")
    scope = brief["scope"]
    if not isinstance(scope, dict) or not isinstance(scope.get("in"), list) or not scope.get("in"):
        errors.append("scope.in must list at least one thing that is in scope")
    else:
        items(scope["in"], "scope.in")
        items(scope.get("out"), "scope.out")
    items(brief["definition_of_done"], "definition_of_done")
    if isinstance(brief["definition_of_done"], list) and not brief["definition_of_done"]:
        errors.append("definition_of_done must say at least one way the person will know it works")
    for key in ("glossary", "particulars", "inputs", "process", "open_questions"):
        if not isinstance(brief[key], list) or not all(isinstance(item, dict) for item in brief[key]):
            errors.append(f"{key} must be a list of objects")
    if errors:
        return errors

    ids = [step.get("id") for step in brief["process"]]
    if len(set(ids)) != len(ids):
        errors.append("process step ids must be unique")

    # Glossary: every source must be one a lookup really returned.
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

    def step_link(item, label) -> None:
        step = item.get("step")
        if step is not None and step not in ids:
            errors.append(f"{label}: step '{step}' is not a process step id (use null for the whole plan)")

    for item in brief["particulars"]:
        if not _is_text(item.get("what")) or not _is_text(item.get("handling")):
            errors.append("every particular needs both 'what' and 'handling'")
            continue
        label = f"particular '{item['what'][:40]}'"
        step_link(item, label)
        origin_errors(item, label)
    for item in brief["open_questions"]:
        if not _is_text(item.get("text")):
            errors.append("every open question needs text")
            continue
        label = f"open question '{item['text'][:40]}'"
        step_link(item, label)
        origin_errors(item, label)

    input_names = []
    for item in brief["inputs"]:
        if not _is_text(item.get("name")) or not _is_text(item.get("description")):
            errors.append("every input needs a name and a description")
        else:
            input_names.append(item["name"])
            origin_errors(item, f"input '{item['name']}'")
    if len(set(input_names)) != len(input_names):
        errors.append("input names must be unique")

    # Process: steps link to each other and to inputs, and a calculation
    # must apply a standard method that was looked up.
    if not brief["process"]:
        errors.append("process must have at least one step")
    for step in brief["process"]:
        label = f"process step '{step.get('id')}'"
        if not _is_text(step.get("id")) or not _is_text(step.get("name")) or not _is_text(step.get("produces")):
            errors.append(f"{label}: needs an id, a name and what it produces")
        else:
            origin_errors(step, label)
        if step.get("kind") not in KINDS:
            errors.append(f"{label}: kind must be one of: {', '.join(KINDS)}")
        needs = step.get("needs")
        if not _is_text_list(needs):
            errors.append(f"{label}: needs must be a list")
        else:
            for need in needs:
                if need not in ids and need not in input_names:
                    errors.append(f"{label}: needs '{need}', which is neither a process step id nor the exact "
                                  f"name of an entry in inputs (step ids: {', '.join(map(str, ids)) or 'none'}; "
                                  f"input names: {', '.join(input_names) or 'none'}); "
                                  "a step can only need an earlier step's id or an input's name")
                elif need == step.get("id"):
                    errors.append(f"{label}: cannot need itself")
                elif need in ids and need not in input_names and ids.index(need) > brief["process"].index(step):
                    errors.append(f"{label}: needs '{need}', which comes later in process; "
                                  "a step can only need an earlier step")
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

    # Every input is a small box above the step that uses it; one that no step names in needs is drawn nowhere.
    used = {need for step in brief["process"] if _is_text_list(step.get("needs")) for need in step["needs"]}
    for name in input_names:
        if name not in used:
            errors.append(f"input '{name}' is used by no step: write its exact name '{name}' in the needs of "
                          "each step that uses it (needs holds step ids and input names, and an input is not "
                          "also a step), or remove the input if nothing uses it")
    return errors


def person_quotes(brief: dict) -> list[str]:
    """Every quote of a `person` origin in a brief: what an accepted plan already holds of the person's words."""
    found = []

    def visit(value) -> None:
        if isinstance(value, dict):
            origin = value.get("origin")
            if isinstance(origin, dict) and origin.get("kind") == "person" and isinstance(origin.get("quote"), str):
                found.append(origin["quote"])
            for each in value.values():
                visit(each)
        elif isinstance(value, list):
            for each in value:
                visit(each)

    visit({key: value for key, value in brief.items() if key != "meta"})
    return found


# --- A step's fingerprint (SPEC 4.4; layer 2 stores and compares it) ---

def step_fingerprint(brief: dict, step_id: str) -> str | None:
    """SHA-256 of the canonical JSON of a step's kind, method, formula, needs and produces and the
    `what` and `handling` of its particulars. None when the brief has no such step."""
    step = next((each for each in brief.get("process", []) if each.get("id") == step_id), None)
    if step is None:
        return None
    particulars = sorted(({"what": item.get("what", ""), "handling": item.get("handling", "")}
                          for item in brief.get("particulars", []) if item.get("step") == step_id),
                         key=lambda item: (item["what"], item["handling"]))
    canonical = {"kind": step.get("kind", ""), "method": step.get("method") or "",
                 "formula": step.get("formula") or "", "needs": list(step.get("needs") or []),
                 "produces": step.get("produces", ""), "particulars": particulars}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


# --- The plan state document's layer 1 part ---

def input_id(name: str) -> str:
    """'in:' plus the name lower-cased with runs of non-letters as '_' (ARCHITECTURE.md 3.2)."""
    return "in:" + (re.sub(r"[^a-z]+", "_", str(name).lower()).strip("_") or "input")


def input_ids(brief: dict) -> dict[str, str]:
    """{input name: input id} for a brief's inputs; names that would give the same id get _2, _3."""
    taken, ids = set(), {}
    for item in brief.get("inputs", []):
        base = input_id(item["name"])
        found, number = base, 1
        while found in taken:
            number += 1
            found = f"{base}_{number}"
        taken.add(found)
        ids[item["name"]] = found
    return ids


def draw(brief: dict, lookups=()) -> dict:
    """The layer 1 keys of the state document for a brief: goal, context, inputs, steps, edges.

    `lookups` give the titles of looked-up sources; a source with no title shows its address.
    """
    titles = {source["url"]: source.get("title") or source["url"]
              for lookup in lookups for source in lookup.get("sources", [])}
    meta = brief.get("meta") or {}

    def origin(value) -> dict:
        value = value if isinstance(value, dict) else {}
        if value.get("kind") == "person":
            return {"kind": "person", "quote": value.get("quote", "")}
        if value.get("kind") == "looked_up":
            url = value.get("source", "")
            return {"kind": "looked_up", "source": {"title": titles.get(url, url), "url": url}}
        return {"kind": "proposed"}

    def item(each, **extra) -> dict:
        return {"text": each.get("text", ""), "origin": origin(each.get("origin")), **extra}

    ids = input_ids(brief)
    step_ids = [step["id"] for step in brief["process"]]
    particulars = brief.get("particulars", [])
    questions = brief.get("open_questions", [])

    def assumption(each) -> dict:
        return {"text": each["what"], "handling": each["handling"], "origin": origin(each.get("origin"))}

    context = {
        "scope_in": [item(each) for each in brief["scope"]["in"]],
        "scope_out": [item(each) for each in brief["scope"]["out"]],
        "assumptions": [assumption(each) for each in particulars if each.get("step") is None],
        "done": [item(each) for each in brief["definition_of_done"]],
        "open_questions": [item(each) for each in questions if each.get("step") is None],
        "glossary": [{"term": entry["term"], "definition": entry["definition"],
                      "person_says": entry.get("person_says") or "",
                      "origin": origin({"kind": "looked_up", "source": entry["source"]}
                                       if entry.get("source") else {"kind": "proposed"})}
                     for entry in brief["glossary"]],
        "revisions": list(meta.get("revisions") or []),
    }

    steps, edges = [], []
    for number, step in enumerate(brief["process"], start=1):
        needs = [need if need in step_ids else ids[need] for need in step.get("needs") or []
                 if need in step_ids or need in ids]
        steps.append({
            "id": step["id"], "number": number, "name": step["name"],
            "kind": STATE_KINDS[step["kind"]], "in_plan": True,
            "method": step.get("method") or "", "formula": step.get("formula") or "",
            "produces": step.get("produces") or "", "cadence": step.get("cadence") or "",
            "needs": needs, "inputs": [need for need in needs if need.startswith("in:") and need not in step_ids],
            "origin": origin(step.get("origin")),
            "particulars": [assumption(each) for each in particulars if each.get("step") == step["id"]],
            "open_questions": [item(each) for each in questions if each.get("step") == step["id"]],
        })
        edges += [{"from": need, "to": step["id"]} for need in needs if need in step_ids]

    inputs = {}
    for each in brief.get("inputs", []):
        found = ids[each["name"]]
        inputs[found] = {"id": found, "name": each["name"], "description": each["description"],
                         "origin": origin(each.get("origin")),
                         "steps": [step["id"] for step in steps if found in step["inputs"]]}
    return {"goal": {"text": brief["goal"]["text"], "mode": brief["mode"], "origin": origin(brief["goal"].get("origin"))},
            "context": context, "inputs": inputs, "steps": steps, "edges": edges}


# --- Writing out and reading back ---

def load_brief(folder) -> dict | None:
    """The confirmed brief in `folder` (with its `meta`), or None: no file, a draft, or not a version 2 brief."""
    try:
        brief = json.loads((Path(folder) / "domain_brief.json").read_text(encoding="utf-8"))
        if brief["meta"]["status"] != "confirmed":
            return None
        draw(brief)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return brief


def render_brief(brief: dict, meta: dict) -> str:
    """The brief as a page a person can read. Same brief in, same page out."""
    lines = ["# Domain brief", ""]
    status = "Confirmed by the person" if meta.get("status") == "confirmed" else "Draft, not confirmed"
    lines += [f"{status}. Written {meta.get('written_at', '')}. Interview session `{meta.get('session_id', '')}`.", ""]
    if meta.get("errors"):
        lines += ["This draft did not pass the harness checks:", ""]
        lines += [f"- {error}" for error in meta["errors"]] + [""]

    goal = brief.get("goal") if isinstance(brief.get("goal"), dict) else {"text": brief.get("goal", "")}
    mode = "ongoing" if brief.get("mode") == "ongoing" else "one-off"
    lines += ["## Goal", "", f"{goal.get('text', '')} ({mode}){_came(goal)}", ""]

    scope = brief.get("scope") or {}
    lines += ["## Scope", "", "In scope:", ""] + [f"- {_text(each)}{_came(each)}" for each in scope.get("in", [])]
    lines += ["", "Out of scope:", ""] + (
        [f"- {_text(each)}{_came(each)}" for each in scope.get("out", [])] or ["- nothing listed"]) + [""]

    lines += ["## Glossary", "", "| Standard term | Meaning | You call it | Source |", "| --- | --- | --- | --- |"]
    for entry in brief.get("glossary", []):
        source = f"[source]({entry['source']})" if entry.get("source") else "not looked up"
        lines.append(f"| {_cell(entry.get('term'))} | {_cell(entry.get('definition'))} "
                     f"| {_cell(entry.get('person_says'))} | {source} |")
    lines.append("")

    lines += ["## What is particular to you", ""]
    if brief.get("particulars"):
        lines += ["| What is different | How it is handled | Step | Came from |", "| --- | --- | --- | --- |"]
        lines += [f"| {_cell(item.get('what'))} | {_cell(item.get('handling'))} | {_cell(item.get('step') or 'whole plan')} "
                  f"| {_cell(_came(item, bare=True))} |" for item in brief["particulars"]]
    else:
        lines.append("Nothing recorded.")
    lines.append("")

    lines += ["## Inputs", ""]
    lines += [f"- **{item.get('name')}**: {item.get('description')}{_came(item)}"
              for item in brief.get("inputs", [])] or ["None listed."]
    lines.append("")

    lines += ["## Process", "", "| Step | Kind | Method | Formula | Needs | Produces | How often | Came from |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for step in brief.get("process", []):
        lines.append(f"| {_cell(step.get('id'))}: {_cell(step.get('name'))} | {_cell(step.get('kind'))} "
                     f"| {_cell(step.get('method'))} | {_cell(step.get('formula'))} "
                     f"| {_cell(', '.join(step.get('needs') or []))} "
                     f"| {_cell(step.get('produces'))} | {_cell(step.get('cadence'))} "
                     f"| {_cell(_came(step, bare=True))} |")
    lines += ["", "Steps marked `calculation` must run as tested code.", "", *_diagram(brief), ""]

    lines += ["## Definition of done", ""] + [
        f"- [ ] {_text(each)}{_came(each)}" for each in brief.get("definition_of_done", [])] + [""]
    lines += ["## Open questions", ""] + (
        [f"- {_text(each)}{' (' + each['step'] + ')' if each.get('step') else ''}{_came(each)}"
         for each in brief.get("open_questions", [])] or ["None."]) + [""]
    return "\n".join(lines)


def summarise_brief(brief: dict) -> str:
    """The brief as plain text, short enough to read in a terminal."""
    mode = "ongoing" if brief["mode"] == "ongoing" else "one-off"
    lines = ["", "THE PLAN", "", f"Goal ({mode}): {brief['goal']['text']}", "", "In scope:"]
    lines += [f"  - {_text(each)}" for each in brief["scope"]["in"]]
    lines += ["Out of scope:"] + ([f"  - {_text(each)}" for each in brief["scope"]["out"]] or ["  - nothing listed"])
    lines += ["", "Terms we agreed:"]
    for entry in brief["glossary"]:
        yours = f" (you call it: {entry['person_says']})" if entry.get("person_says") else ""
        checked = "" if entry.get("source") else " [not looked up]"
        lines.append(f"  - {entry['term']}{yours}: {entry['definition']}{checked}")
    lines += ["", "Data you have:"] + [f"  - {item['name']}: {item['description']}" for item in brief["inputs"]]
    lines += ["", "Steps:"]
    for step in brief["process"]:
        needs = f" (needs: {', '.join(step['needs'])})" if step["needs"] else ""
        lines.append(f"  - {step['id']} [{step['kind']}] {step['name']}{needs} -> {step['produces']}  "
                     f"[{_came(step, bare=True)}]")
        if step["kind"] == "calculation":
            lines.append(f"      method: {step.get('method')}; formula: {step.get('formula')}")
        for item in brief["particulars"]:
            if item.get("step") == step["id"]:
                lines.append(f"      particular: {item['what']} -> {item['handling']}")
        for item in brief["open_questions"]:
            if item.get("step") == step["id"]:
                lines.append(f"      open: {_text(item)}")
    whole = [item for item in brief["particulars"] if item.get("step") is None]
    if whole:
        lines += ["", "What is particular to you, for the whole plan:"]
        lines += [f"  - {item['what']} -> {item['handling']}" for item in whole]
    lines += ["", "You will know it works when:"] + [f"  - {_text(each)}" for each in brief["definition_of_done"]]
    loose = [item for item in brief["open_questions"] if item.get("step") is None]
    if loose:
        lines += ["", "Still open, for the whole plan:"] + [f"  - {_text(item)}" for item in loose]
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
    meta = {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "revisions": [], **meta}
    json_path, page_path = folder / "domain_brief.json", folder / "domain_brief.md"
    json_path.write_text(json.dumps({**brief, "meta": meta}, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    page_path.write_text(render_brief(brief, meta), encoding="utf-8")
    return json_path, page_path


def _came(each, bare: bool = False) -> str:
    """Where an item came from, as a few words."""
    origin = each.get("origin") if isinstance(each, dict) else None
    origin = origin if isinstance(origin, dict) else {}
    if origin.get("kind") == "person":
        words = f'you said "{origin.get("quote", "")}"'
    elif origin.get("kind") == "looked_up":
        words = f"looked up: {origin.get('source', '')}"
    else:
        words = "proposed"
    return words if bare else f" ({words})"


def _text(each) -> str:
    return each.get("text", "") if isinstance(each, dict) else str(each)


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _plain(text: str) -> str:
    return " ".join(str(text).lower().replace("-", " ").replace("_", " ").split())


def _spaced(text) -> str:
    """Case-folded, with runs of white space as one space."""
    return " ".join(str(text or "").casefold().split())


def _cell(value) -> str:
    """Text made safe for one table cell."""
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _label(value) -> str:
    """Text made safe for a diagram label."""
    return " ".join(str(value or "").split()).replace('"', "'")
