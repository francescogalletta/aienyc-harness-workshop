"""A small validator for the plan state document as ARCHITECTURE.md section 3 states it.

`problems(state)` returns a list of what is wrong (empty when the document has the shape). Keys that
belong to a layer are checked only when that layer is in `state["layers"]`.
"""
import re

STR, INT, BOOL, ANY = str, int, bool, object
def OPT(*kinds):
    return ("opt", kinds)                            # None, or one of the kinds


def LIST(kind):
    return ("list", kind)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

LANES = ("idle", "working", "waiting")


def check(value, shape, where, out):
    """Compare `value` with `shape`: a type, a dict of keys, ("list", shape), ("opt", ...), a tuple of choices."""
    if isinstance(shape, tuple) and shape and shape[0] == "opt":
        if value is not None:
            check(value, shape[1][0] if len(shape[1]) == 1 else shape[1], where, out)
        return
    if isinstance(shape, tuple) and shape and shape[0] == "list":
        if not isinstance(value, list):
            return out.append(f"{where}: not a list")
        for n, item in enumerate(value):
            check(item, shape[1], f"{where}[{n}]", out)
    elif isinstance(shape, tuple):                   # a choice of literals, or of types
        if not any(value == s if not isinstance(s, type) else isinstance(value, s) and not (s is int and isinstance(value, bool))
                   for s in shape):
            out.append(f"{where}: {value!r} is none of {shape}")
    elif isinstance(shape, dict):
        if not isinstance(value, dict):
            return out.append(f"{where}: not an object")
        for key, sub in shape.items():
            if key not in value:
                out.append(f"{where}: missing {key}")
            else:
                check(value[key], sub, f"{where}.{key}", out)
    elif shape is ANY:
        pass
    elif isinstance(shape, str):                     # a literal
        if value != shape:
            out.append(f"{where}: {value!r} is not {shape!r}")
    elif not isinstance(value, shape) or (shape is int and isinstance(value, bool)):
        out.append(f"{where}: {value!r} is not {shape.__name__}")


SOURCE = {"title": STR, "url": STR}
ORIGIN_SHAPE = {"kind": ("person", "looked_up", "proposed")}
ITEM = {"text": STR, "origin": ANY}
ACTIVITY = {"lane": ("main", "side", "review"),
            "what": ("interview", "build", "answer", "helper", "tests", "side", "review"),
            "step": OPT(STR), "thread": OPT(STR), "text": STR, "since": STR}
FIGURE = {"start": INT, "end": INT, "text": STR, "step": OPT(STR), "run": OPT(STR), "input": OPT(STR)}
DECISION = {"id": STR, "step": STR, "question": STR, "options": LIST(STR), "suggested": OPT(INT), "why": STR,
            "status": ("open", "answered"), "choice": OPT(STR)}
NOTICE = {"assumptions": LIST({"id": STR, "text": STR}), "steps": LIST(STR), "status": ("open", "confirmed", "changed")}
MESSAGE = {"id": STR, "ts": STR, "who": ("you", "assistant", "harness"), "text": STR, "step": OPT(STR),
           "queued": BOOL, "kind": ("text", "plan", "decision", "notice", "withheld")}
CHALLENGE = {"id": STR, "step": STR, "kind": ("challenge", "question"), "concern": STR, "proposal": STR,
             "change": ("plan", "assumption", "input", "build_step", "replace_step", "none"),
             "impact": ("high", "medium", "low"), "rank": INT, "sources": LIST(SOURCE),
             "status": ("open", "used", "dismissed"), "pass": INT}
THREAD = {"id": STR, "kind": ("side", "review"), "step": OPT(STR), "after": OPT(STR), "title": STR,
          "status": ("open", "used", "dismissed"),
          "messages": LIST({"who": ("you", "assistant", "reviewer"), "text": STR, "sources": LIST(SOURCE)}),
          "challenge": OPT(CHALLENGE)}
BUILD = {"status": ("none", "building", "built", "not_built", "stale"), "module": OPT(STR), "examples": INT,
         "tests": INT, "passing": INT, "examples_passing": INT, "reason": STR,
         "plan_check": OPT({"departures": LIST(STR), "confirmed": BOOL}), "spec": ANY,
         "example_list": LIST({"n": INT, "inputs": dict, "expected": ANY, "working": STR,
                               "checked_by": (None, "second_pass", "you"), "second_pass": ANY}),
         "disagreement": LIST({"n": INT, "expected": ANY, "code_gives": ANY}),
         "code": OPT({"module_py": STR, "tests_py": STR}), "tested_at": OPT(STR)}
LAST_RUN = {"run": STR, "message": OPT(STR), "in_last_answer": BOOL, "inputs": dict, "output": ANY,
            "assumptions": LIST(STR), "ts": STR, "test_run": INT}
CALLS = {"open": OPT(STR), "records": LIST({"decision": STR, "question": STR, "options": LIST(STR),
                                             "choice": STR, "words": STR, "ts": STR})}
STEP = {"id": STR, "number": INT, "name": STR, "kind": ("calculation", "from_you", "your_call"), "in_plan": BOOL,
        "method": STR, "formula": STR, "produces": STR, "cadence": STR, "needs": LIST(STR), "inputs": LIST(STR),
        "origin": ORIGIN_SHAPE, "particulars": LIST(dict), "open_questions": LIST(ITEM),
        "line": OPT({"text": STR, "kind": (None, "tested", "result", "strong")}),
        "marks": LIST({"symbol": ("●", "▲", "◌", "plan check"), "count": OPT(INT), "title": STR}),
        "needs_you": BOOL}
LAYER_STEP_KEYS = {2: {"build": OPT(BUILD)}, 3: {"last_run": OPT(LAST_RUN)},
                   4: {"unconfirmed": LIST({"id": STR, "text": STR}), "calls": OPT(CALLS)},
                   5: {"challenges": LIST(STR)}}
INPUT = {"id": STR, "name": STR, "description": STR, "origin": ORIGIN_SHAPE, "steps": LIST(STR)}
CONTEXT = {"scope_in": LIST(ITEM), "scope_out": LIST(ITEM), "assumptions": LIST(dict), "done": LIST(ITEM),
           "open_questions": LIST(ITEM), "glossary": LIST({"term": STR, "definition": STR, "person_says": ANY,
                                                           "origin": ANY}), "revisions": LIST(dict)}
WAITING = ({"kind": "message"}, {"kind": "plan"}, {"kind": "decision", "decision": STR, "step": STR})


def problems(state: dict) -> list[str]:
    out: list[str] = []
    check(state, {"version": INT, "layers": LIST(INT), "product": STR, "phase": ("empty", "interview", "proposed", "accepted"),
                  "error": OPT(STR), "lanes": {"main": LANES, "side": LANES, "review": LANES},
                  "activity": LIST(ACTIVITY), "waiting": ANY, "goal": OPT({"text": STR, "mode": ("ongoing", "one_off"),
                                                                           "origin": ANY}),
                  "context": OPT(CONTEXT), "inputs": dict, "steps": LIST(STEP), "edges": LIST({"from": STR, "to": STR}),
                  "chat": LIST(MESSAGE)}, "state", out)
    if out:
        return out
    layers = set(state["layers"])
    waiting = state["waiting"]
    if waiting is not None:
        kind = waiting.get("kind") if isinstance(waiting, dict) else None
        if kind not in ("message", "plan", "decision"):
            out.append(f"waiting: unknown {waiting!r}")
        elif kind == "decision":
            check(waiting, WAITING[2], "waiting", out)
    step_ids = {step["id"] for step in state["steps"]}
    for n, step in enumerate(state["steps"]):
        for layer, keys in LAYER_STEP_KEYS.items():
            if layer in layers:
                check({key: step.get(key, "<missing>") for key in keys}, {key: ANY for key in keys}, f"steps[{n}]", out)
                for key, shape in keys.items():
                    if key in step:
                        check(step[key], shape, f"steps[{n}].{key}", out)
            else:
                out.extend(f"steps[{n}]: {key} but layer {layer} is off" for key in keys if key in step)
        out.extend(f"steps[{n}]: needs unknown {need}" for need in step["needs"]
                   if need not in step_ids and need not in state["inputs"])
    out.extend(f"edge {edge}: unknown step" for edge in state["edges"]
               if edge["from"] not in step_ids or edge["to"] not in step_ids)
    for key, entry in state["inputs"].items():
        check(entry, INPUT, f"inputs.{key}", out)
        if entry.get("id") != key:
            out.append(f"inputs.{key}: id differs")
        if 3 in layers:
            check(entry, {"used": BOOL, "value": OPT(STR)}, f"inputs.{key}", out)
    messages = {}
    for n, message in enumerate(state["chat"]):
        where = f"chat[{n}]"
        messages[message["id"]] = message
        if message["step"] is not None and message["step"] not in step_ids:
            out.append(f"{where}: unknown step")
        for figure in message.get("figures") or []:
            check(figure, FIGURE, f"{where}.figures", out)
            if message["text"][figure["start"]:figure["end"]] != figure["text"]:
                out.append(f"{where}: figure {figure['text']!r} is not at its offsets")
            if figure["step"] is not None and figure["step"] not in step_ids:
                out.append(f"{where}: figure of unknown step")
        if message["kind"] == "decision":
            check(message.get("decision"), DECISION, f"{where}.decision", out)
            if message.get("decision") and message["decision"]["question"] != message["text"]:
                out.append(f"{where}: a decision message's text is its question")
        if message.get("notice") is not None:
            check(message["notice"], NOTICE, f"{where}.notice", out)
    if waiting and waiting.get("kind") == "decision":
        open_ids = [m["decision"]["id"] for m in messages.values()
                    if m["kind"] == "decision" and m["decision"]["status"] == "open"]
        if waiting["decision"] not in open_ids:
            out.append("waiting: no open decision message of that id")
    if state["lanes"]["main"] == "waiting" and waiting is None:
        out.append("lanes.main waits but waiting is null")
    if len([step for step in state["steps"] if step["needs_you"]]) > 1:
        out.append("needs_you is true for more than one step")
    if 4 in layers or 5 in layers:
        check(state.get("threads"), LIST(THREAD), "threads", out)
        thread_ids = {thread["id"] for thread in state.get("threads") or []}
        for thread in state.get("threads") or []:
            if thread["after"] is not None and thread["after"] not in messages:
                out.append(f"{thread['id']}: follows a message that is not in the chat")
        for entry in state["activity"]:
            if entry["thread"] is not None and entry["thread"] not in thread_ids:
                out.append(f"activity: unknown thread {entry['thread']}")
    if 5 in layers:
        check(state.get("review"), {"open": INT, "running": BOOL}, "review", out)
        challenges = {t["challenge"]["id"] for t in state.get("threads") or [] if t["challenge"]}
        for step in state["steps"]:
            out.extend(f"{step['id']}: challenge {c} has no thread" for c in step.get("challenges", [])
                       if c not in challenges)
    return out
