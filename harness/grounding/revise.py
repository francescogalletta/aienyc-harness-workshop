"""Changing an accepted plan (SPEC 3.3).

One interviewer conversation, not an interview: the interviewer's prompt, the accepted brief, and a
`[harness]` line asking for exactly one change. Layer 3's analyst calls `revise_plan` from its
`change_plan` tool; the person's words are the consent.
"""
import copy
import json
from datetime import datetime, timezone

from .brief import load_brief, person_quotes, save_brief, step_fingerprint, validate_brief
from .interview import INSTRUCTIONS, TOOLS, look_up_all
from .research import default_desk

MAX_ATTEMPTS = 3
MAX_CALLS = 8
ASK = ("[harness] The plan was accepted. This is the plan:\n{brief}\n\n[harness] Change the plan in exactly this "
       "way, {about}and in what follows from it, keep everything else as it was, and submit the whole brief "
       "with write_brief. The person said: {words}")
NO_PLAN = "there is no accepted plan to change"


def revise_plan(work, *, words: str, step: str | None = None, by: str = "person") -> dict:
    """Make one change to the accepted plan. Returns {"changed": [step ids]} or {"error": one line}.

    `changed` lists the steps added, removed, or whose fingerprint (SPEC 4.4) changed. The new brief is
    saved as confirmed with a new `revisions` entry, and hook `plan_changed(work, changed)` is called.
    """
    path = work.config.brief_dir
    accepted = load_brief(path)
    if accepted is None:
        return {"error": f"the plan was not changed: {NO_PLAN}"}
    meta = accepted["meta"]
    brief = {key: value for key, value in accepted.items() if key != "meta"}
    state = {"research": [], "lookups": list(meta.get("lookups") or [])}
    allowed = [words, *person_quotes(brief)]        # their words now, and what the plan already holds of theirs
    desk = work.desk() or default_desk(work.config, work.conn)

    name = next((each["name"] for each in brief["process"] if each["id"] == step), None) if step else None
    where = f"about step {step}{f' ({name})' if name else ''}, " if step else ""
    messages = [{"role": "user", "content": ASK.format(brief=json.dumps(brief, indent=1, ensure_ascii=False),
                                                       about=where, words=words)}]
    system = INSTRUCTIONS.read_text(encoding="utf-8").replace("{max_questions}", "0")
    work.progress("changing the plan", step=step)
    rejected = 0
    for _ in range(MAX_CALLS):
        response = work.model.complete(system=system, messages=messages, tools=TOOLS)
        if not response.tool_calls:
            return {"error": f"the plan was not changed: {' '.join(response.text.split()) or 'no reply'}"}
        looked_up = look_up_all([call for call in response.tool_calls if call.name == "look_up"], desk, state, work)
        results, new = [], None
        for call in response.tool_calls:
            if call.name == "look_up":
                results.append(looked_up[call.id])
                continue
            if call.name != "write_brief" or new is not None:
                results.append({"role": "tool", "tool_call_id": call.id, "is_error": True,
                                "content": "Call write_brief once, with the whole brief."})
                continue
            candidate = copy.deepcopy(call.arguments)
            errors = validate_brief(candidate, state["lookups"], allowed)
            if errors:
                rejected += 1
                work.record("plan.brief_rejected", {"errors": errors, "draft": False, "revision": True}, "harness")
                results.append({"role": "tool", "tool_call_id": call.id, "is_error": True,
                                "content": "The brief was not accepted. Fix these and submit it again:\n"
                                           + "\n".join(f"- {error}" for error in errors)})
            else:
                new = candidate
                results.append({"role": "tool", "tool_call_id": call.id, "content": "Saved as confirmed."})
        if new is not None:
            return _save(work, accepted, new, state, words, step, by)
        if rejected >= MAX_ATTEMPTS:
            return {"error": "the plan was not changed: the new plan did not pass the checks"}
        messages.append({"role": "assistant", "content": response.text, "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
        messages.extend(results)
    return {"error": "the plan was not changed: the interviewer made too many calls"}


def changed_steps(old: dict, new: dict) -> list[str]:
    """Step ids added, removed, or whose fingerprint changed, in the new plan's order, then the removed."""
    before = {step["id"]: step_fingerprint(old, step["id"]) for step in old["process"]}
    after = [step["id"] for step in new["process"]]
    return [found for found in after if before.get(found) != step_fingerprint(new, found)] + [
        gone for gone in before if gone not in after]


def _save(work, accepted: dict, new: dict, state: dict, words: str, step, by: str) -> dict:
    meta = accepted["meta"]
    seen = {each["query"] for each in meta.get("lookups") or []}
    revision = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "words": words, "step": step, "by": by}
    lookups = [*(meta.get("lookups") or []), *(each for each in state["lookups"] if each["query"] not in seen)]
    save_brief(new, work.config.brief_dir,
               {"session_id": meta.get("session_id", ""), "lookups": lookups, "status": "confirmed",
                "revisions": [*(meta.get("revisions") or []), revision]})
    old = {key: value for key, value in accepted.items() if key != "meta"}
    changed = changed_steps(old, new)
    work.record("plan.revised", {"words": words, "step": step, "by": by, "changed": changed},
                "person" if by == "person" else "agent")
    work.changed()
    work.hook("plan_changed", work, changed)
    return {"changed": changed}

