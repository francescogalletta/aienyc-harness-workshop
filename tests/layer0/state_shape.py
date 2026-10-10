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
         "plan_check": OPT({"departures": LIST(STR), "confirmed": BOOL}),
         "spec": OPT({"formula": STR, "inputs": LIST({"name": STR, "type": STR, "description": STR}),
                      "output": {"type": STR, "description": STR}}),
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


def build_problems(state: dict) -> list[str]:
    """What layer 2 must keep true of the `build` keys, beyond their shape (ARCHITECTURE.md 3.3, SPEC 2.4)."""
    out: list[str] = []
    accepted = state["phase"] == "accepted"
    added_started = False
    for n, step in enumerate(state["steps"]):
        where, build = f"steps[{n}] ({step['id']})", step.get("build")
        if step["in_plan"] == step["id"].startswith("added_"):
            out.append(f"{where}: in_plan and the added_ id disagree")
        if not step["in_plan"]:
            added_started = True
        elif added_started:
            out.append(f"{where}: a step of the plan after an added step")
        if step["kind"] != "calculation" or not accepted:
            if build is not None:
                out.append(f"{where}: a build on a step that is not a calculation, or before the plan is accepted")
            continue
        if build is None:
            out.append(f"{where}: a calculation step with no build")
            continue
        status = build["status"]
        if not (0 <= build["passing"] <= build["tests"] and 0 <= build["examples_passing"] <= build["examples"]):
            out.append(f"{where}: passing counts are out of range")
        if bool(build["reason"]) != (status in ("not_built", "stale")):
            out.append(f"{where}: reason {build['reason']!r} for status {status}")
        if build["disagreement"] and status != "not_built":
            out.append(f"{where}: a disagreement while {status}")
        if status == "built" and not (build["module"] and build["code"] and build["spec"]):
            out.append(f"{where}: built without a module, code or spec")
        if status == "none" and (build["module"] or build["tests"]):
            out.append(f"{where}: status none but a module or tests")
        if [each["n"] for each in build["example_list"]] != list(range(1, len(build["example_list"]) + 1)):
            out.append(f"{where}: examples are not numbered 1, 2, 3 ...")
        if build["tests"] and not build["tested_at"]:
            out.append(f"{where}: tests without tested_at")
        if build["plan_check"] is not None and not build["plan_check"]["departures"]:
            out.append(f"{where}: a plan check with no departures")
        line = step["line"] or {}
        if not step["needs_you"] and not step.get("last_run", {}) and status == "building" and line.get("text") != "Building":
            out.append(f"{where}: building but the line says {line.get('text')!r}")
        if (not step["needs_you"] and not (step.get("last_run") or {}).get("in_last_answer") and status == "built"
                and line.get("text") != f"{build['examples']} examples · {build['passing']}/{build['tests']}"):
            out.append(f"{where}: built but the line says {line.get('text')!r}")
        unconfirmed = bool(build["plan_check"]) and not build["plan_check"]["confirmed"]
        if unconfirmed != any(mark["symbol"] == "plan check" for mark in step["marks"]):
            out.append(f"{where}: the plan check mark and the departures disagree")
    return out


def layer4_problems(state: dict) -> list[str]:
    """What layer 4 must keep true of its keys, beyond their shape (ARCHITECTURE.md 3.3, 3.4; SPEC 2.4, 6)."""
    out: list[str] = []
    step_ids = {step["id"] for step in state["steps"]}
    waiting = state["waiting"] or {}
    decisions = {m["decision"]["id"]: m for m in state["chat"] if m["kind"] == "decision" and m.get("decision")}
    open_ids = [each for each, m in decisions.items() if m["decision"]["status"] == "open"]
    if len(open_ids) > 1:
        out.append(f"more than one open decision: {open_ids}")
    if open_ids and waiting.get("decision") != open_ids[0]:
        out.append("an open decision that the main lane does not wait for")
    for each, message in decisions.items():
        decision = message["decision"]
        if decision["step"] not in step_ids or message["step"] != decision["step"]:
            out.append(f"{each}: a decision of an unknown step, or a message about another step")
        if decision["suggested"] is not None and not 1 <= decision["suggested"] <= len(decision["options"]):
            out.append(f"{each}: suggested is not an option")
        if not 2 <= len(decision["options"]) <= 4:
            out.append(f"{each}: {len(decision['options'])} options")
        if decision["status"] == "open" and decision["choice"] is not None:
            out.append(f"{each}: open but chosen")
        if decision["choice"] not in (None, "something else") and not (
                decision["choice"].isdigit() and 1 <= int(decision["choice"]) <= len(decision["options"])):
            out.append(f"{each}: choice {decision['choice']!r} is none of the options")
    for n, step in enumerate(state["steps"]):
        where = f"steps[{n}] ({step['id']})"
        calls = step.get("calls")
        named = [each for each, m in decisions.items() if m["decision"]["step"] == step["id"]]
        if step["kind"] == "your_call" and calls is None:
            out.append(f"{where}: a your_call step with no calls")
        if calls is None and named:
            out.append(f"{where}: a decision names this step but it has no calls")
        if calls is not None:
            if calls["open"] is not None and calls["open"] != waiting.get("decision"):
                out.append(f"{where}: calls.open is not the decision the main lane waits for")
            if (calls["open"] is not None) != bool(step["needs_you"] and waiting.get("step") == step["id"]):
                out.append(f"{where}: calls.open and needs_you disagree")
            for record in calls["records"]:
                if record["choice"] not in ("something else", *[str(k) for k in range(1, len(record["options"]) + 1)]):
                    out.append(f"{where}: record {record['decision']} has choice {record['choice']!r}")
        loose = step.get("unconfirmed") or []
        if len({each["id"] for each in loose}) != len(loose):
            out.append(f"{where}: an assumption twice in unconfirmed")
        if loose and not step.get("last_run"):
            out.append(f"{where}: unconfirmed assumptions but no last run")
        if bool(loose) != any(mark["symbol"] == "◌" for mark in step["marks"]):
            out.append(f"{where}: the ◌ mark and unconfirmed disagree")
        if loose and (step.get("last_run") or {}).get("in_last_answer") and not step["needs_you"] \
                and not (step["line"] or {}).get("text", "").endswith(" ◌"):
            out.append(f"{where}: unconfirmed in the last answer but the line says {step['line']!r}")
    for message in state["chat"]:
        notice = message.get("notice")
        if not notice:
            continue
        where = f"{message['id']}.notice"
        if message["who"] == "you":
            out.append(f"{where}: a notice on the person's own message")
        if not notice["assumptions"] or not notice["steps"] and notice["status"] == "open":
            out.append(f"{where}: a notice with nothing to confirm or no step")
        out.extend(f"{where}: unknown step {each}" for each in notice["steps"] if each not in step_ids)
    return out


def layer5_problems(state: dict) -> list[str]:
    """What layer 5 must keep true of its keys, beyond their shape (ARCHITECTURE.md 3.3, 3.4; SPEC 2.4, 7)."""
    out: list[str] = []
    threads = {thread["id"]: thread for thread in state.get("threads") or []}
    challenges = {}
    for thread in threads.values():
        found = thread["challenge"]
        if (thread["kind"] == "review") != (found is not None):
            out.append(f"{thread['id']}: a review thread has a challenge, and a side thread has none")
        if found is None:
            continue
        where = f"{thread['id']}.challenge {found['id']}"
        challenges[found["id"]] = (thread, found)
        if found["step"] != thread["step"] or found["step"] not in {step["id"] for step in state["steps"]}:
            out.append(f"{where}: its step is not the thread's step, or not a step")
        if found["status"] != thread["status"]:
            out.append(f"{where}: status {found['status']} but the thread is {thread['status']}")
        if not 1 <= len(thread["title"]) <= 45:
            out.append(f"{where}: title of {len(thread['title'])} characters")
        if found["kind"] == "question" and (found["proposal"] or found["change"] != "none"):
            out.append(f"{where}: a question with a proposal or a change")
        if found["kind"] == "challenge" and not found["proposal"]:
            out.append(f"{where}: a challenge with no proposal")
        if found["rank"] < 1 or found["pass"] < 1:
            out.append(f"{where}: rank or pass below 1")
        if not thread["messages"] or thread["messages"][0]["who"] != "reviewer":
            out.append(f"{where}: the first message is not the reviewer's")
        elif thread["messages"][0]["sources"] != found["sources"]:
            out.append(f"{where}: the first message does not carry the challenge's sources")
    ranks = [(found["pass"], found["rank"]) for _, found in challenges.values()]
    if len(set(ranks)) != len(ranks):
        out.append("two challenges of one pass have the same rank")
    listed = []
    for n, step in enumerate(state["steps"]):
        where = f"steps[{n}] ({step['id']})"
        ids = step.get("challenges") or []
        listed += ids
        for each in ids:
            if each not in challenges or challenges[each][1]["status"] != "open" or challenges[each][1]["step"] != step["id"]:
                out.append(f"{where}: {each} is not an open challenge of this step")
        mark = [m for m in step["marks"] if m["symbol"] == "▲"]
        if bool(ids) != bool(mark) or (mark and mark[0]["count"] != len(ids)):
            out.append(f"{where}: the ▲ mark and challenges disagree")
    if sorted(listed) != sorted(each for each, (_, found) in challenges.items() if found["status"] == "open"):
        out.append("an open challenge is on no step, or on two")
    if state["review"]["open"] != len(listed):
        out.append("review.open is not the number of open challenges")
    if state["review"]["running"] != (state["lanes"]["review"] != "idle"):
        out.append("review.running and lanes.review disagree")
    return out


def problems(state: dict, strict: bool = False) -> list[str]:
    """What is wrong with the shape of `state`. `strict` also runs the checks a live state must keep
    (`build_problems`); the hand-written samples in `states/` are sparse and are checked without it."""
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
        if 3 in layers and message["who"] == "assistant":
            if not isinstance(message.get("figures"), list):
                out.append(f"{where}: an assistant message carries figures (layer 3)")
            for figure in message.get("figures") or []:
                if figure["input"] is not None and figure["input"] not in state["inputs"]:
                    out.append(f"{where}: figure of unknown input {figure['input']}")
                if figure["run"] is not None and figure["input"] is not None:
                    out.append(f"{where}: a figure is of a run or of an input, not both")
        if message["kind"] == "decision":
            check(message.get("decision"), DECISION, f"{where}.decision", out)
            if message.get("decision") and message["decision"]["question"] != message["text"]:
                out.append(f"{where}: a decision message's text is its question")
        if message.get("notice") is not None:
            check(message["notice"], NOTICE, f"{where}.notice", out)
    if 3 in layers:
        answered = {step["last_run"]["message"] for step in state["steps"]
                    if step.get("last_run") and step["last_run"]["in_last_answer"]}
        if len(answered) > 1:
            out.append(f"steps of the last answer name different messages: {sorted(answered)}")
        for step in state["steps"]:
            run = step.get("last_run")
            if run and run["message"] is not None and run["message"] not in messages:
                out.append(f"{step['id']}: last_run feeds a message that is not in the chat")
            if run and run["in_last_answer"] and step["kind"] != "calculation":
                out.append(f"{step['id']}: only a calculation has a run")
        lit = {step["id"] for step in state["steps"] if (step.get("last_run") or {}).get("in_last_answer")}
        for key, entry in state["inputs"].items():
            if entry.get("used") != any(step in lit for step in entry["steps"]):
                out.append(f"inputs.{key}: used differs from the steps of the last answer")
    if waiting and waiting.get("kind") == "decision":
        open_ids = [m["decision"]["id"] for m in messages.values()
                    if m["kind"] == "decision" and m["decision"]["status"] == "open"]
        if waiting["decision"] not in open_ids:
            out.append("waiting: no open decision message of that id")
    if strict and 2 in layers:
        out.extend(build_problems(state))
    if strict and 4 in layers:
        out.extend(layer4_problems(state))
    if strict and 5 in layers:
        out.extend(layer5_problems(state))
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
