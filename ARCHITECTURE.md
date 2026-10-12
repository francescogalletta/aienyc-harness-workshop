# Architecture: Financial Advisor Harness

This file says how the harness is built: the core, the plan state document,
the layers and what each owns, the actions, how long work is reported, how
the harness up to layer N is produced, and the database. Section 12 is the
decision history the right-hand panel draws. Section 9 holds implementation
notes the contract leaves open.
`SPEC.md` is the contract for behaviour; it relies on sections 3 to 5 here,
which are part of the contract too, and on section 12 where `SPEC.md` cites
it. The product design is in `design/`
(`design/ui-design-decisions.md` and `design/system/`). Where this file and the
design differ, the design wins; tell the maintainer.

## 1. In brief

1. One **core** (`harness/core/`) owns the conversation, the waiting slot, three
   work lanes and the plan state document. It knows no layer by name.
2. The **plan state document** is one JSON object. The page and the terminal
   draw everything from it. Nothing else is read by a front end.
3. **Actions** are the only way in: `POST /api/act` from the page, method calls
   from the terminal and from replay.
4. Work runs on three **lanes** (main, side, review), one job at a time each.
   The page polls `GET /api/state` and sees progress in `activity`.
5. Five **layers** plug into the core through one `Layer` object each: schema,
   state contribution, actions, chat routing, agent tools, prompt part, hooks,
   commands, replay expectations.
6. Layer N may import layers below N, never above. Layer N's files are one
   package.
7. `HARNESS_LAYERS=N` switches layers above N off; a missing package does the
   same. That is the harness up to layer N.
8. The database is one schema file per layer, created on connect. No migration
   history.
9. Fixed code, no model, decides what counts: values, safety, runner,
   registry, test gate, number check. Models sit behind `harness/model/`.
10. Not here: reading account files, checking against the person's own data.
11. The chat is a **decision history** (section 12): a trunk of decisions that
    changed the analysis, and branches, each about one thing in the plan, that
    join the trunk with the person's yes or die without a consequence.

## 2. Files and layers

Every file belongs to exactly one layer. Tests of layer K live in
`tests/layer<K>/`.

| Layer | Package | Owns |
| --- | --- | --- |
| 0 core | `harness/` top level, `harness/core/`, `harness/model/`, `harness/ui/` | `__main__.py`, `config.py`, `db.py`, `schema.sql`, `layers.py`, `terminal.py`, `replay.py`, `core/session.py`, `core/state.py`, `core/lanes.py`, `model/*` (unchanged), `ui/server.py`, `ui/page.html` (given) |
| 1 the plan | `harness/grounding/` | `layer.py`, `brief.py`, `interview.py`, `revise.py`, `research.py`, `claude_code_research.py`, `schema.sql`; given: `interviewer.md`, `planner.md`, `researcher.md`; data: `reference/`, `examples/*/brief/` |
| 2 build | `harness/calc/` | `layer.py`, `values.py`, `safety.py`, `runner.py`, `registry.py`, `gate.py`, `provenance.py`, `builder.py`, `checker.py`, `helper.py`, `notes.py`, `added.py`, `adopt.py`, `schema.sql`; given: `spec_writer.md`, `example_writer.md`, `checker.md`, `module_writer.md`, `step_helper.md`; data: `examples/*/modules/` |
| 3 answers | `harness/answers/` | `layer.py`, `agent.py`, `figures.py`, `rerun.py`, `schema.sql`; given: `analyst.md` |
| 4 needs you | `harness/needs_you/` | `layer.py`, `marks.py`, `calls.py`, `requests.py`, `side.py`, `join.py`, `schema.sql`; given: `analyst.md` (a part), `side.md` |
| 5 review | `harness/review/` | `layer.py`, `reviewer.py`, `schema.sql`; given: `reviewer.md`, `analyst.md` (a part) |

Scenarios (`examples/*/scenarios/*.json`) carry a `"layer"` field and belong to
that layer.

## 3. The plan state document

`Session.state()` returns it. `GET /api/state` sends it. It is rebuilt from
the database and the core's memory on every call; nothing in it is written by
a model at display time. Keys a disabled layer would add are absent, and the
page hides what they feed. IDs are strings so the page never mixes kinds.

### 3.1 Top level

```
{
  "version": 57,                          int; goes up on every change the core sees
  "layers": [0, 1, 2, 3, 4, 5],           enabled layers
  "product": "Financial Advisor Harness",
  "phase": "empty" | "interview" | "proposed" | "accepted",
  "error": null | "one line",             the last job that failed, until the next action
  "lanes": {"main": Lane, "side": Lane, "review": Lane},
  "activity": [Activity, ...],            what is running now, oldest first
  "waiting": null | Waiting,              what the main lane waits for from the person
  "goal": null | {"text": str, "mode": "ongoing" | "one_off", "origin": Origin},
  "context": null | Context,              the whole-plan section
  "inputs": {"<input id>": Input, ...},
  "steps": [Step, ...],                   plan order; added steps last
  "edges": [{"from": "<step id>", "to": "<step id>"}, ...],
  "chat": [Message, ...],                 the main chat, oldest first
  "history": {"trunk": [Node, ...],       the decisions of this conversation, oldest first (3.5)
              "latest": "n5" | null},     the newest node
  "threads": [Thread, ...],               (layer 4 and 5) the branches: side, reviewer and harness threads
  "review": {"open": int, "running": bool}   (layer 5)
}

Lane     = "idle" | "working" | "waiting"
Activity = {"lane": "main" | "side" | "review", "what": "interview" | "build" | "answer"
            | "helper" | "tests" | "side" | "review" | "join", "step": "<step id>" | null,
            "thread": "<thread id>" | null,         the thread a side job is answering
            "text": "writing the code, attempt 2", "since": "<ISO time>"}
Waiting  = {"kind": "message"}                     the person may type; nothing else waits
         | {"kind": "plan"}                        a proposed plan awaits Accept plan or a correction
         | {"kind": "decision", "decision": "d4", "step": "s7"}   a call that is the person's
Origin   = {"kind": "person", "quote": "exact words they used"}
         | {"kind": "looked_up", "source": {"title": str, "url": str}}
         | {"kind": "proposed"}
Item     = {"text": str, "origin": Origin}
```

`phase` is `empty` with no plan and no interview, `interview` while the
interview runs, `proposed` while a brief waits for "Accept plan", `accepted`
once a confirmed brief exists. Without layer 1 it is always `empty`.

`waiting` is null while the main lane works. A message typed then is queued
(it appears in `chat` with `"queued": true`) and handled when the lane is free.

### 3.2 Whole-plan context, inputs, edges (layer 1)

```
Context = {
  "scope_in": [Item], "scope_out": [Item],
  "assumptions": [Item],          particulars with no step: "what" as text, "handling" in "handling"
  "done": [Item],                 definition of done
  "open_questions": [Item],       open questions with no step
  "glossary": [{"term", "definition", "person_says", "origin"}],
  "revisions": [{"ts", "words", "step", "by": "person" | "reviewer"}]
}
Input = {"id": "in:guest_count", "name": "Guest count", "description": str, "origin": Origin,
         "steps": ["s1"],             steps whose needs name it; the page draws one pill above each
         "used": bool,                (layer 3) it took part in the last answer
         "value": null | str,         (layer 3) its saved value as written; null: none saved yet
         "changed_by": null | "n5"}   the newest trunk node whose `touched.inputs` names it (core, 3.5)
```

Assumption items carry an extra key `"handling"`. An input id is `in:` plus
the input's name lower-cased with runs of non-letters as `_`. `edges` holds
one entry per need that is a step id. A need that names an input is not an
edge: it is a pill.

### 3.3 Step

```
Step = {
  "id": "s5", "number": 5, "name": "Fund balance",
  "kind": "calculation" | "from_you" | "your_call",     from the brief's calculation | input | judgment
  "in_plan": true,                false for an added step: "not in the plan"
  "method": str, "formula": str, "produces": str, "cadence": str,
  "needs": ["s2", "in:guest_count"],
  "inputs": ["in:guest_count"],   the pills above it, in need order
  "origin": Origin,
  "particulars": [Item + "handling"], "open_questions": [Item],
  "line": null | {"text": "4 examples · 6/6", "kind": null | "tested" | "result" | "strong"},
  "marks": [{"symbol": "●" | "▲" | "◌" | "plan check", "count": int | null, "title": str}],
  "needs_you": bool,              true for at most one step in the document
  "changed_by": null | "n5",      the newest trunk node whose `touched.steps` names it (core, 3.5)

  "build": null | Build,          (layer 2) calculation steps only
  "last_run": null | LastRun,     (layer 3)
  "runs": [Run],                  (layer 3) its last five runs, newest first
  "near": null | "s5",            (layer 4) added steps: the step that asked for it
  "unconfirmed": [Assumption],    (layer 4) of last_run, still unconfirmed
  "calls": null | Calls,          (layer 4) your_call steps, and any step a decision named
  "challenges": ["c3"]            (layer 5) open challenge ids
}

Build = {
  "status": "none" | "building" | "built" | "not_built" | "stale",
  "module": str | null,
  "examples": int, "tests": int, "passing": int, "examples_passing": int,
  "reason": str,                  why not built, or why stale; "" otherwise
  "plan_check": null | {"departures": [str], "confirmed": bool},
  "spec": null | {"formula": str, "inputs": [{"name", "type", "description"}], "output": {...}},
  "example_list": [Example],
  "disagreement": [{"n": 2, "expected": json, "code_gives": json | "an error",
                    "shown": {"expected": Shown, "code_gives": Shown}}],
  "code": null | {"module_py": str, "tests_py": str},
  "tested_at": null | ISO time    the latest test run of this module
}
Example = {"n": 1, "inputs": {...}, "expected": json, "working": str,
           "checked_by": "second_pass" | "you" | null,      null: left out, the passes disagreed
           "second_pass": null | json,                      the checker's answer when it differed
           "shown": {"inputs": [[name, Shown]], "expected": Shown, "second_pass": null | Shown}}
Run     = {"run": "r17", "message": "m12" | null,   the message that ended the turn it was made in
           "inputs": {...}, "output": json, "assumptions": [str], "ts": ISO time, "test_run": int,
           "shown": {"inputs": [[name, Shown]], "output": Shown}}
LastRun = Run + {"in_last_answer": bool}           the step is in the last answer (SPEC 5.2)
Shown   = {"text": "1,888.89"}                     a value as the harness writes it (SPEC 2.4)
        | {"text": "6 values", "rows": [[name, text]]}                       an object, or a list of values
        | {"text": "3 values", "columns": [name], "table": [[text]]}         a list of rows
Assumption = {"id": "a3", "text": str}
Calls = {"open": null | "d4",
         "records": [{"decision": "d2", "question": str, "options": [str], "choice": "2" | "something else",
                      "words": str, "ts": ISO time}]}
```

`line` and `marks` are computed by the core (`core/state.py`) after every
layer has contributed, by the rule in SPEC 2.4. The page shows them as they
come and never works out its own.

`needs_you` is true for the step of the open decision; with none, for the
first step in plan order whose build is `not_built` with a disagreement or too
few checked examples.

### 3.4 Chat and threads

```
Message = {
  "id": "m12", "ts": ISO time,
  "who": "you" | "assistant" | "harness",
  "text": str,                    plain text, never HTML
  "step": "s2" | null,            the chip: the step the message is about
  "queued": bool,                 (you) typed while the main lane was busy
  "kind": "text" | "plan" | "decision" | "notice" | "withheld",
  "figures": [Figure],            (layer 3, 4) assistant messages; a decision's question too
  "decision": null | Decision,    kind "decision" (layer 4); `text` is its `question`
  "notice": null | Notice,        (layer 4) set on the assistant reply it belongs to
  "chips": [Chip]                 (layer 3, 4) on a message that ended a turn with runs, and on a join
                                  notice; [] on every other message once layer 3 is on (3.5)
}
Figure   = {"start": 13, "end": 19, "text": "43,000",
            "step": "s1" | null, "run": "r17" | null, "input": "in:guest_count" | null,
            "superseded": false}     (layer 3) true only when a join ran its run again and the run that
                                     came last no longer produces this value; an unchanged one stays false
Decision = {"id": "d4", "step": "s7", "question": str, "options": [str], "suggested": 2 | null,
            "why": str, "status": "open" | "answered", "choice": null | "2" | "something else"}
Notice   = {"assumptions": [Assumption], "steps": ["s5"], "status": "open" | "confirmed" | "changed"}
Thread   = {"id": "t3", "kind": "side" | "review" | "harness", "step": "s5" | null, "title": str (≤45 chars),
            "after": "m12" | null,    the main-chat message it follows: drawn right after it; the core
                                      sets it to the last main message when the thread starts
            "status": "open" | "used" | "dismissed",      kept for the current page; `outcome` replaces it
            "messages": [{"who": "you" | "assistant" | "reviewer" | "harness", "text": str,
                          "sources": [{"title", "url"}]}],
            "challenge": null | Challenge,
            -- a thread is a branch (3.5):
            "origin": "you" | "assistant" | "reviewer" | "harness",   who opened it
            "subject": Subject,       what in the plan it is about
            "from": "n3" | null,      the trunk node it left from: the newest when it opened
            "outcome": "open" | "joined" | "dead",
            "node": "n5" | null,      the trunk node it joined as
            "proposal": null | Proposal}               (layer 4) its newest proposal, whatever its status
Challenge = {"id": "c3", "step": "s5", "kind": "challenge" | "question", "concern": str,
             "proposal": str, "change": "plan" | "assumption" | "input" | "build_step"
             | "replace_step" | "none", "impact": "high" | "medium" | "low", "rank": 1,
             "sources": [{"title", "url"}], "status": "open" | "used" | "dismissed", "pass": 2}
```

A `kind: "plan"` message is the harness's "here is the plan" message; the
page puts "Accept plan" under it while `waiting.kind` is `plan`.

**How a number refers to its step.** Every assistant message in the main chat
carries `figures`: one entry per number or date the number check reads in its
text, from `provenance.trace` (layer 2). A figure whose source is a module run
(a value the run produced, not one it was given: SPEC 5.2) gets that run's id
and the step the run's module carries out; clicking it opens that step's
pop-up on that run. A figure from a
saved input gets the input id when the input's name matches a brief input id,
else none. Every other figure (the person's words, the brief, today, a small
number) gets neither and is shown as plain text. `start` and `end` are
character offsets in `text`. Only figures with a `step` are drawn as
`fah-num` and select their step when clicked. A decision message is the same:
its `text` is the decision's `question`, and its `figures` index that text.

### 3.5 Decision history, subjects, chips and proposals

The mechanics are in section 12; these are the shapes.

```
Node     = {"id": "n5", "ts": ISO time,
            "who": "you" | "assistant" | "harness" | "reviewer",       who decided
            "kind": "plan_accepted" | "plan_revised" | "value" | "assumption_confirmed"
                    | "assumption_corrected" | "call" | "built" | "challenge_used",
            "text": str,              one line the harness writes from the change (≤ 80 chars), never a model's
            "change": Change,         typed by kind, below
            "touched": {"inputs": ["in:guest_count"], "steps": ["s1", "s2"]},   what it changed in the plan
            "branch": "t4" | null,    the branch it joined from; null: decided in the main chat
            "after": "m19" | null}    the main-chat message it follows (the last one when it was recorded)

Change, by kind:
  plan_accepted         {}
  plan_revised          {"step": "s2" | null, "words": str, "changed": ["s2"]}
  value                 {"input": "guest_count", "label": "Guest count", "from": "120" | null, "to": "150",
                         "runs": {"r3": "r9", "r4": "r10"},        each re-run: old run -> new run
                         "failed": [{"run": "r5", "step": "s5", "reason": str}]}
  assumption_confirmed  {"assumptions": ["a3"]}
  assumption_corrected  {"assumptions": ["a3"], "words": str}
  call                  {"decision": "d4", "step": "s7", "choice": "2" | "something else", "words": str}
  built                 {"steps": {"s5": "built" | "reused"}, "why": "build" | "step" | "new" | "replace"
                         | "rebuilt" | "files_changed"}
  challenge_used        {"challenge": "c3", "step": "s5", "change": Challenge.change}

Subject  = {"kind": "plan"}                                            the whole plan
         | {"kind": "step", "step": "s5"}
         | {"kind": "input", "input": "in:guest_count", "step": "s1" | null}     a plan input (a pill)
         | {"kind": "value", "run": "r3", "key": "guest_count", "value": "120",   a value that went into a run
            "input": "in:guest_count" | null, "step": "s1" | null}
         | {"kind": "result", "run": "r3", "step": "s1" | null, "value": "36100"}  what a run produced
         | {"kind": "assumption", "run": "r4", "step": "s2" | null, "text": str,
            "assumption": "a3" | null}                                 (the id once layer 4 is on)
         | {"kind": "decision", "node": "n5"}                          a trunk node

Chip     = {"kind": "value" | "assumption" | "result" | "decision",
            "label": str,             "Guest count", a step's name, "" for an assumption
            "text": str,              the value as shown ("120", "43,000", "3 values"), an assumption's sentence,
                                      a node's text
            "status": null | "unconfirmed" | "confirmed" | "corrected",   assumptions, once layer 4 is on
            "subject": Subject}

Proposal = {"id": "p2", "status": "pending" | "accepted" | "declined" | "replaced" | "failed",
            "change": {"kind": "value", "input": "guest_count", "label": "Guest count",
                       "from": "120" | null, "to": "150"}
                    | {"kind": "plan", "step": "s1" | null, "words": str},
            "words": str,             the person's words in the branch it rests on
            "text": "Guest count: 120 → 150",          one line the harness writes
            "impact": Impact,
            "node": "n5" | null,      once joined
            "reason": str}            why it failed; "" otherwise
Impact   = {"inputs": ["in:guest_count"],  plan inputs it changes
            "runs": ["r3", "r4"],          runs of the last answer that will run again, in order
            "steps": ["s1", "s2"],         their steps: these re-run
            "downstream": ["s5", "s6"]}    steps the plan's edges reach from them that are not in the last answer:
                                           touched, not re-run
```

**What every chip carries.** A chip's `subject` is enough for the three
actions of its hover menu, with nothing else looked up: *see it in the graph*
selects `subject.input` when there is one, else `subject.step`, and opens the
step's pop-up on `subject.run` when there is one (a decision chip selects the
node's `touched` steps); *challenge or correct it* and *talk about it* both
send `side` with `subject` (section 5), the first with the composer of the new
branch focused for a correction. A computed number is never edited: a result
chip's branch is about the run's inputs or its step.

**Figures and subjects.** A Figure (3.4) is a subject without the word: a figure
with `run` and `step` is `{"kind": "result", "run", "step", "value": text}`,
a figure with `input` is `{"kind": "input", "input"}`. The page builds that
subject for a figure's hover menu; nothing new is stored. Clicking a figure
selects its step.

### 3.6 A small example

```
{"version": 9, "layers": [0,1,2,3,4], "product": "Financial Advisor Harness", "phase": "accepted",
 "error": null, "lanes": {"main": "idle", "side": "idle", "review": "idle"}, "activity": [],
 "waiting": {"kind": "message"},
 "goal": {"text": "Cover each wedding payment on its due date", "mode": "ongoing",
          "origin": {"kind": "person", "quote": "can I cover each payment"}},
 "context": {"scope_in": [], "scope_out": [], "assumptions": [], "done": [], "open_questions": [],
             "glossary": [], "revisions": []},
 "inputs": {"in:guest_count": {"id": "in:guest_count", "name": "Guest count", "description": "...",
            "origin": {"kind": "proposed"}, "steps": ["s1"], "used": true, "value": "150"}},
 "steps": [{"id": "s1", "number": 1, "name": "Total cost", "kind": "calculation", "in_plan": true,
            "method": "arithmetic", "formula": "guests x price + fixed costs", "produces": "total",
            "cadence": "", "needs": ["in:guest_count"], "inputs": ["in:guest_count"],
            "origin": {"kind": "proposed"}, "particulars": [], "open_questions": [],
            "line": {"text": "→ 43,000 ◌", "kind": "result"},
            "marks": [{"symbol": "◌", "count": null, "title": "rests on something unconfirmed"}],
            "needs_you": false,
            "build": {"status": "built", "module": "total_cost", "examples": 4, "tests": 6, "passing": 6,
                      "examples_passing": 4, "reason": "", "plan_check": null, "spec": null,
                      "example_list": [], "disagreement": [], "code": null, "tested_at": "2026-10-10T10:00:00+00:00"},
            "last_run": {"run": "r3", "message": "m7", "in_last_answer": true,
                         "inputs": {"guest_count": "150"}, "output": "43000.00",
                         "assumptions": ["The guest count stays at 150."], "ts": "...", "test_run": 11},
            "unconfirmed": [{"id": "a1", "text": "The guest count stays at 150."}],
            "calls": null}],
 "edges": [],
 "chat": [{"id": "m7", "ts": "...", "who": "assistant", "text": "total_cost gives 43,000.00.",
           "step": null, "queued": false, "kind": "text",
           "figures": [{"start": 18, "end": 27, "text": "43,000.00", "step": "s1", "run": "r3", "input": null}],
           "decision": null,
           "notice": {"assumptions": [{"id": "a1", "text": "The guest count stays at 150."}],
                      "steps": ["s1"], "status": "open"},
           "chips": [{"kind": "value", "label": "Guest count", "text": "150", "status": null,
                      "subject": {"kind": "value", "run": "r3", "key": "guest_count", "value": "150",
                                  "input": "in:guest_count", "step": "s1"}},
                     {"kind": "assumption", "label": "", "text": "The guest count stays at 150.",
                      "status": "unconfirmed",
                      "subject": {"kind": "assumption", "run": "r3", "step": "s1",
                                  "text": "The guest count stays at 150.", "assumption": "a1"}},
                     {"kind": "result", "label": "Total cost", "text": "43,000", "status": null,
                      "subject": {"kind": "result", "run": "r3", "step": "s1", "value": "43000.00"}}]}],
 "history": {"trunk": [{"id": "n1", "ts": "...", "who": "you", "kind": "plan_accepted", "text": "Plan accepted",
                        "change": {}, "touched": {"inputs": [], "steps": []}, "branch": null, "after": null}],
             "latest": "n1"},
 "threads": []}
```

(`changed_by` is null on the step and the input here: node `n1` touched nothing.)

## 4. The core and its extension points

### 4.1 Session

```python
class Session:                                     # harness/core/session.py
    def __init__(self, config, *, model_factory=get_model, desk_factory=None,
                 layers=None, memory=None): ...   # layers: replaces discovery (tests); memory: starts self.memory
    def state(self) -> dict                        # section 3
    def act(self, action: str, payload: dict) -> tuple[bool, str]   # (applied, reason when not)
    def settle(self, timeout: float | None = None) -> dict         # wait until every lane is idle
                                                   # or waiting on the person; returns state()
    def close(self) -> None
```

On creation it opens the database (applying the schemas of the enabled
layers), loads the enabled layers, reads the current conversation id from the
`meta` table (making one if there is none), and runs the `loaded` hook of each
layer (layer 1 resumes an unfinished interview; layer 2 adopts module folders,
SPEC 4.6).

### 4.2 Lanes, the waiting slot, and how work is reported

- Three lanes, each a thread with a FIFO queue of jobs: **main** (interview
  turns, plan revisions, the build, analyst turns, step-helper turns, test
  runs), **side** (replies in side and reviewer threads), **review** (reviewer
  passes; a pass asked for while one runs is coalesced into one more).
- A job gets a `Work` object: its own database connection, the model,
  `progress(text, step=None, what=None, thread=None)` (sets its `activity`
  entry), `post(message)` (adds to `chat` or a thread), and `wait(kind, **data)
  -> answer` (main lane only: sets `waiting` to `{"kind": kind, **data}`,
  blocks until a message or an action answers it).
- `version` goes up whenever `activity`, `waiting`, a lane, or the database
  changes through the core.
- **Reporting: polling is kept.** The page polls `GET /api/state` every second
  while any lane is not idle, every five seconds otherwise, and redraws only
  when `version` changed. No streaming, no long poll: the standard library
  server does this as it is, tests call `state()` and `settle()` directly,
  and a model reply takes seconds, so a second of delay is invisible.
- SQLite runs in WAL mode with a busy timeout of five seconds, so the server
  thread can read while a lane writes. Every thread opens its own connection.

### 4.3 The Layer object

```python
@dataclass(frozen=True)
class Layer:                                       # harness/layers.py
    number: int
    name: str
    schema: Path | None = None                     # CREATE TABLE IF NOT EXISTS ...
    contribute: Callable[[View, dict], None] | None = None    # adds its keys to the state document
    actions: dict[str, Callable[[Core, dict], None]] = {}     # raise NotNow(reason) to refuse
    route: Callable[[Core, Message], Callable | None] | None = None   # main-chat handler, or None
    tools: Callable[[Turn], list[Tool]] | None = None          # analyst tools (layers 3 and 4)
    prompt: Path | None = None                     # a part of the analyst's system prompt
    context: Callable[[sqlite3.Connection], dict] | None = None   # sections for the analyst's "What you know"
    hooks: dict[str, Callable] = {}                # see below
    commands: dict[str, Command] = {}              # terminal subcommands
    expects: dict[str, Expect] = {}                # replay expectation keys
```

- **Discovery.** `layers.enabled(config)` imports `harness.grounding.layer`,
  `harness.calc.layer`, `harness.answers.layer`, `harness.needs_you.layer`,
  `harness.review.layer` in order, up to `config.layers`. It stops at the first
  package that is missing (`ModuleNotFoundError` naming that package): layers
  are contiguous. A disabled layer is never imported.
- **Contribute** runs in layer order on a dict the core started (top level
  and empty steps). Later layers may add keys to steps an earlier one made.
- **Route.** For a person's message in the main chat, after the core has
  answered the waiting slot if one waits (SPEC 2.3), the core asks each
  enabled layer's `route` from the highest down; the first that returns a
  handler gets the message as a main-lane job. None: the harness posts
  `NO_ROUTE` (SPEC 2.3).
- **Tools.** The analyst (layer 3) collects the tools of every enabled layer
  in order. `Tool = (ToolSpec, handle(turn, call) -> tool result dict)`.
- **Prompt.** The analyst's system prompt is the `prompt` files of the
  enabled layers in order, joined by a blank line, then `## What you know`
  and the context: the `context` sections of the enabled layers in order,
  written with `format_sections`. Layer 3 owns the first part.
- **Hooks**, called on the lane that caused them, in layer order:
  `loaded(core)`, `plan_accepted(work)`, `plan_changed(work, changed_steps)`,
  `step_built(work, step_id)`, `turn_finished(work, turn)`, and inside an analyst turn
  `run_ready(work, turn, arguments)` and `reply_ready(work, turn, text)` (SPEC 5.1). A hook may queue
  jobs; it never waits on the person.
- **Commands** are added to `python -m harness`. **Expects** are added to the
  scenario validator and checker (SPEC 2.6).

What a layer must not do: import a higher layer, write to another layer's
tables, or read `config.layers` itself. The core is the only place that knows
which layers are on.

### 4.4 The decision history in the core

The core owns the trunk and the branch columns of threads, as it owns messages
and threads; it knows no kind of change by meaning. Every layer records its own
decisions through it.

```python
# harness/core/session.py, beside add_message and add_thread
def decide(conn, conversation, *, who, kind, text, change=None, touched=None,
           branch=None) -> str                     # "n<id>"; records `core.decided`; with `branch`,
                                                   # sets that thread's outcome "joined" and its node
def add_thread(conn, conversation, *, kind, title, step=None, after=None,
               origin="you", subject=None) -> str  # `from` is the newest node of the conversation;
                                                   # subject defaults to {"kind": "step", "step"} or {"kind": "plan"}
def set_outcome(conn, thread, outcome) -> None     # "open" | "joined" | "dead" (joined only through decide)
def list_trunk(conn, conversation) -> list[dict]   # the Nodes, oldest first
Session.decide(**same but conn and conversation**) and Work.decide(...)   # also call changed()
```

`plan_state.start` takes the trunk and puts `history` in the document;
`plan_state.finish` sets `changed_by` on every step and input (the newest node
whose `touched` names it; null when none). `list_threads` returns `origin`,
`subject`, `from`, `outcome` and `node` with every thread. `history` is there
at every layer; at layer 0 its trunk is empty.

## 5. Actions

`POST /api/act` with `{"action": name, ...payload}`. 200 `{"ok": true,
"version": n}` when applied; 409 `{"ok": false, "error": reason}` when not
now; 400 for a bad body or an unknown action. The page fetches the state after
every action.

| Action | Payload | Layer | Allowed when | Effect |
| --- | --- | --- | --- | --- |
| `say` | `text`, `step`?, `notice`? | 0 | always | A person message in the main chat; answers `waiting`, or is routed (SPEC 2.3) |
| `start` | `text` | 1 | `phase` is `empty` | Starts the interview with the opening statement |
| `accept_plan` | | 1 | `waiting.kind` is `plan` | Saves the brief as confirmed; trunk node `plan_accepted`; hook `plan_accepted` |
| `wrap` | | 1 | the interview waits for an answer | Asks the interviewer to propose the plan now |
| `build` | | 2 | `phase` is `accepted`, no build queued or running | Queues the unattended build |
| `confirm_example` | `step`, `n` | 2 | that example exists and is not yours already, and its step is not being built | Records "confirmed by you" |
| `confirm_plan_check` | `step` | 2 | the step has departures not yet confirmed | Clears the plan-check mark |
| `run_tests` | `step` | 2 | the step has a registered module | Queues a test run |
| `choose` | `decision`, `option` | 4 | that decision is the one waiting | Posts the option's text as the person's message (`who` "you", the decision's step), then answers the decision with the option number; trunk node `call` (an answer in words records it too) |
| `confirm_assumptions` | `message` | 4 | that message's notice is open | Confirms its assumptions; trunk node `assumption_confirmed` |
| `side` | `text`, `step`?, `thread`?, `subject`? | 4 | always | Without `thread`: opens a branch (origin `you`) on `subject` (default: the step, else the whole plan) and marks the person's other answered side branches dead. With `thread`: says something in that branch (side or review); a dead side branch opens again |
| `accept_proposal` | `proposal` | 4 | the proposal is pending, and the main lane does not wait on a decision | Status `accepted`; queues the join on the main lane (section 12.3) |
| `decline_proposal` | `proposal` | 4 | the proposal is pending | Status `declined`; the branch is dead |
| `close_branch` | `thread` | 4 | a side branch whose outcome is `open` | The branch is dead; a pending proposal in it is declined |
| `use_challenge` | `challenge` | 5 | the challenge is open, is not a question, its step is still in the plan, and the main lane does not wait on the person | Marks it used; trunk node `challenge_used` (who `reviewer`), the review branch joined; posts the person's "use this" message and routes it |
| `dismiss_challenge` | `challenge` | 5 | the challenge is open | Marks it dismissed; the review branch is dead |

"Change it" under a notice is the page putting the notice's steps in the
composer; the message then goes as `say` with `notice` set (trunk node
`assumption_corrected`). The Review toggle, pop-ups, "Whole plan", selection,
and the chip's "see it in the graph" are page-only. A chip's "challenge or
correct" and "talk about it" are `side` with the chip's `subject`; the branch
starts with the person's first message, so an empty branch is never stored.

The terminal maps typed lines to the same actions (SPEC 2.5). Replay plays a
scenario's lines as actions (SPEC 2.6).

## 6. Events

Hooks are the core's events between layers (4.3). The event log
(`events` table, append-only) records what happened, for evidence; each layer
writes its own kinds with a prefix: `core.` (messages, actions, job failures),
`plan.` (interview, lookups, brief, revisions), `build.` (spec, examples,
second pass, code, tests, registration, not built, confirmations), `ask.`
(model replies, corrections, withheld replies, runs, saved inputs), `you.`
(decisions, assumption confirmations and corrections, side threads),
`review.` (passes, lookups, challenges kept and dropped, use and dismiss).
Kinds are listed in each layer's section of the SPEC. Tests assert kinds and
payload keys, never wording.

The decision history adds (section 12):

| Kind | Payload | Recorded by |
| --- | --- | --- |
| `core.decided` | `node, kind, who, branch, touched` | `decide`, for every trunk node, whatever layer asked |
| `you.side_opened` | with `subject` | `side` without `thread` |
| `you.branch_dead` | `thread, reason`: `closed`, `declined`, `moved_on`, `new_branch` | layer 4 (a dismissed review branch is dead with `review.dismissed`, layer 5) |
| `you.branch_reopened` | `thread` | a message in a dead side branch |
| `you.proposed` | `thread, proposal, change, impact` | `propose_change`, when it passes the checks |
| `you.proposal_refused` | `thread, reason, change` | `propose_change`, when it does not; `reason` one of `not_their_words`, `unknown_input`, `value_unbacked`, `ambiguous`, `same`, `unknown_step`, `one_per_reply` |
| `you.proposal_accepted`, `you.proposal_declined` | `thread, proposal` | the two actions |
| `you.joined` | `thread, proposal, node, runs, failed` | the join, when it ends |

## 7. Testing one layer at a time (HARNESS_LAYERS)

- **One setting.** `HARNESS_LAYERS=N` (default 5) turns layers above N off.
- **Files absent.** A tree without the packages of layers above N is the
  harness up to layer N; discovery stops at the first missing package. Nothing
  is stored but the finished tree.
- **What each layer registers** is its `Layer` object (4.3): layer 1 plan
  actions, routing before acceptance, `ground`; layer 2 build actions,
  routing for steps, `build`; layer 3 routing after acceptance, its tools and
  prompt, `ask`, figures; layer 4 marks, decisions, automatic builds, side
  threads, its tools and prompt part; layer 5 the reviewer, challenges, its
  prompt part.
- **What tests assume.** `tests/layer<K>/conftest.py` sets
  `HARNESS_LAYERS=K` for every test in it, with the files of every layer
  present. So a test of layer K checks the harness up to layer K, inside any
  later tree, and is never true only with fewer layers. A test of layer K never
  asserts that a later layer's key, tool, table or event is absent, and never
  counts all tools, keys or events. `tests/layer0` also checks that
  discovery stops at a missing package and at the setting.
- **Shared files** (the core, the server, the page, the terminal, replay,
  `__main__.py`) are the same whichever layers are on. They act on what layers
  register and on which keys the state document has. The page is complete
  with any number of layers and hides what it has no keys for.
- **Where this is not fully additive.** The core knows the generic shapes later
  layers fill (threads, decisions in `waiting`, the step-line rule reads keys
  of layers 2 to 5, the trunk and the branch columns of section 12); it does
  not import them, and it never names a kind of change. The page is one given file for
  every layer setting, not built layer by layer. The analyst prompt is composed of parts,
  so a later part must only add, never contradict an earlier one; the layer 4
  part says plainly what it changes. These are the fallbacks, and they are
  enough for the four uses.

## 8. The database

The database is local and disposable: one `schema.sql` per layer, `CREATE
TABLE IF NOT EXISTS`, applied on every connect for the enabled layers. No
migration history. After a schema change, delete `my/var/harness.db` (and
`my/var/examples/`, which holds the example copies and their databases).

## 9. Implementation notes

Choices the contract leaves open, and known limits. The contract wins where
they differ.

- **Model provider.** `HARNESS_MODEL_PROVIDER` forces `claude_code`,
  `anthropic` (needs `uv run --extra claude`), `openrouter` or `scripted`
  (prepared replies, used by every test); `auto` picks as SPEC 2.2 says.
  `HARNESS_MODEL` picks the model (default `claude-sonnet-5-5`); with
  OpenRouter it takes any OpenRouter model id. To add a provider, add one file
  under `harness/model/` with a `complete` method and one entry in
  `harness/model/providers.py`.
- **Lookups.** The research desk checks `reference/terms.json` first and asks
  Wikipedia only for terms the file does not know, sending only a short
  general term, never the person's figures. `HARNESS_RESEARCHER=reference`
  stays offline. The reviewer's outside lookups also need Wikipedia.

- **Session memory.** `Session.memory` is a dict the layers share for the life
  of the Session. Each layer uses its own keys: `plan` and `plan_file` (layer 1,
  the interview and the cached brief), `calc` (layer 2, the step being built),
  `analyst` (layer 3, the model's messages for the current conversation).
  `today` is set by whoever opens the Session (`Session(..., memory={"today":
  ...})`, as replay and tests do) and replaces the clock. Read it only through
  `answers.agent.today_of(memory)`. The analyst, the number check and the
  reviewer all use it, so a fixed `today` applies everywhere.
- **Paths come from the environment.** The gate's brief
  (`gate.step_refusal`), `registry.module_dir`, adoption and the build's
  staging folder `_build/` call `load_config()`. They do not read the
  Session's config. A Session opened with a config that differs from the
  environment reads and writes modules somewhere else. Replay sets the
  `HARNESS_*` variables for this reason. This is a known limit.
- **Two step fingerprints.** `modules.step_fingerprint` is the fingerprint of
  the step the module was registered for. `build_steps.step_fingerprint` is the
  fingerprint of the row's step when the row was written. They differ when a
  step reuses a module built for another step. A step's status
  (`registry.step_status`) is judged from `build_steps`; the gate compares the
  module's own fingerprint.
- **A not-built step's module does not answer.** After a failed rebuild the
  old module stays registered, but it disagrees with an example the person or
  the second pass agreed on. So the gate refuses it (`gate.NOT_BUILT`) until
  the step is built again. It checks this first, even with no confirmed plan.
  Staleness is checked only when there is a confirmed plan and the module has
  a stored fingerprint.
- **An example's inputs count as a source.** The example writer's expected
  answer, and the checker's answer, may repeat a number or date taken from the
  example's own inputs. A correct answer that only repeats an input date would
  otherwise be rejected. A number found in neither the working nor the inputs
  is still refused.
- **Why `reply_ready` is narrow.** It sends a reply back only when the turn
  ran modules and the person asked to decide, or attached a judgment step the
  runs feed. A wider trigger, such as any question with "or" after a run,
  would turn offers like "do you want me to also run 200?" into decisions and
  stop turns that are fine.

## 12. Decision history

How the chat records the decisions that changed the analysis. The two
examples of 12.10 show it end to end.

### 12.1 The model

- The chat is a **decision history**. Its **trunk** holds only decisions that
  changed the analysis, from the plan's acceptance on. Each is a **node**:
  who decided (you, the assistant, the harness, the reviewer), a typed change,
  what it touched in the plan, and the branch it came from, if any.
- A **branch** is a thread. It leaves the trunk at the newest node, is about
  one **subject** in the plan (an input, a value in a run, a result, an
  assumption, a step, a node, or the whole plan), holds its messages, and has
  an **outcome**: `open`, `joined` (naming its node) or `dead`.
- A branch **joins** only through a change with a consequence: a value that
  goes into the runs, or the plan. It is **dead** when it ends without one.
- In the main chat the person asks and the analyst answers. A value
  given or changed in the main chat is conversation, not a node; it becomes a
  decision when the person challenges its chip and accepts the proposal, or
  uses one of their own buttons (choose, confirm, "Change it", "use this").

### 12.2 Where nodes and branches come from

| Where it happens | In the decision history | Layer |
| --- | --- | --- |
| The plan accepted (`accept_plan`; a confirmed plan found on load with an empty trunk, as a seeded example) | The first node, `plan_accepted`, who `you` | 1 |
| A plan revision after acceptance (`revise_plan`, from `change_plan` or from a plan proposal) | Node `plan_revised`, who `you` (`reviewer` when `by` is the reviewer); `branch` set when it came from a proposal | 1 |
| A side thread (`threads` kind `side`) | A branch, origin `you`, subject from `side` (default `{"kind": "step"}` or `{"kind": "plan"}`) | 4 |
| A side reply | Talk in the branch. The side assistant may **propose** a change through `propose_change` (12.3); it applies nothing | 4 |
| A review thread and its challenge (`challenges` row) | A branch, origin `reviewer`, subject `{"kind": "step"}`. "Use this" records node `challenge_used` (who `reviewer`) and joins it; the analyst then acts on the person's message as on any other, and what it changes records its own node. "Dismiss" makes it dead | 5 |
| A notice under an answer (`notice`, `assumptions` rows) | Stays a notice. Its assumptions are also assumption chips. "Confirm" records `assumption_confirmed`; "Change it" records `assumption_corrected` and the analyst runs again | 4 |
| A chip's correction of an assumption | A branch on `{"kind": "assumption"}`; its proposal is a `value` of that run; the join also marks the assumption `corrected` with the words | 4 |
| A call answered (`decisions` row, `answered`) | Node `call`, who `you`, touched: the decision's step | 4 |
| A build the analyst asked for (`request_module`) | Node `built`, who `assistant`, `why` its case, no branch | 4 |
| A rebuild by the harness itself (module files changed and adopted again on load; a helper rebuild; a step built again after it went stale) | A branch of kind `harness`, origin `harness`, subject the step, holding the harness's lines; joined at once as node `built`, who `harness`. Open while the step is not built. Not built: no layer records it yet (SPEC 4.9) | 2 |
| The unattended build (`build`) | Node `built`, who `harness`, `why` `build`, all its steps, no branch. Not built: no layer records it yet (SPEC 4.9) | 2 |
| Stale propagation | No node: a plan revision makes changed steps stale | 2 |
| Every event | Still recorded; `core.decided` and the `you.` kinds of section 6 record the history | all |

No parallel table: a branch is a `threads` row with five branch columns, a node
is a `trunk` row, a proposal is a `proposals` row (12.8).

### 12.3 The join

**A proposal.** On a branch, the side assistant calls `propose_change` (SPEC
6.6) with a fixed shape: `kind` `value` (`input`: the value's name as the
runs give it, `value`: the new value in plain form) or `plan` (`step`), and
`words`: the person's words in this branch it rests on. The harness, with no
model:

1. checks the words are in a person's message of this branch;
2. resolves the target: for `value`, `input` must be a top-level input of a
   run of the last answer, or the branch's subject is a plan input and `input`
   is its id without `in:`; for `plan`, `step` is empty or a plan step;
3. number-checks the new value against the person's messages **in this branch
   only** (as `marks.given_texts` reads them: number words and dates too): a
   value of theirs, never one the model worked out;
4. finds the old value: the subject's `value` when the subject is a value of
   that input; else that input's value in the subject's run (a result or an
   assumption subject); else the saved input; else the one value that input
   has in the last answer (two or more, as a range: refused `ambiguous`, open
   the branch from one of them); refused `same` when old and new are the same;
5. computes the impact (12.4) and stores the proposal, `pending`. A pending
   proposal in the branch becomes `replaced`. One proposal per reply.

A refusal goes back to the model as the tool's error, with the reason; the
model then says plainly what it cannot propose. The person sees the proposal
at the end of the branch: its `text`, what it touches (`impact`), Yes and No.

**Yes** (`accept_proposal`): status `accepted`; a main-lane job `join` is
queued (it waits behind an analyst turn; it is refused while a decision waits
on the person). For a **value** the job:

1. computes the runs again from the last answer as it is now (12.4);
2. saves the value: `answers.agent.store_input(conn, key, new, note, conversation)`,
   the note `on a branch: <words>`; the plan input's pill shows it;
3. when the branch's subject is an assumption, marks it `corrected` with the words;
4. runs again what 12.4 says, through the gate, with progress
   `running step N again` (activity `what` `join`, `step` that step);
5. posts the join notice in the main chat (`JOINED`, SPEC 6.6, a `harness`
   message) with private `_runs` (the new last answer: the old one without the
   replaced runs, plus the new runs) and `_chip_runs` (the new runs only);
6. records the node: `decide(who="you", kind="value", text, change, touched,
   branch)`: `touched.inputs` is `in:<key>` when that is a plan input,
   `touched.steps` the steps run again; the branch is `joined`;
7. sets the message's `_node`, the proposal's `node`, records `you.joined`,
   and tells the analyst with `answers.agent.tell_analyst(session, JOIN_NOTE)`
   (a `[harness]` line put before the person's next message, as a withheld
   note is).

For a **plan** proposal the job calls `revise_plan(work, words, step,
by="person", branch=thread)`; `revise_plan` records `plan_revised` with that
branch, which joins it. An error makes the proposal `failed` with the reason,
posted in the branch as a `harness` line; the branch stays open. Changed steps
go stale; nothing runs again.

**No** (`decline_proposal`): status `declined`, the branch is dead.

### 12.4 What runs again

Let `A` be the runs of the last answer (layer 3: the runs of its turn and the
runs its figures name), oldest first; `key` the input, `old` and `new` its
values.

1. A run of `A` is **direct** when its inputs have `key` at the top level with
   a value equal to `old` (the same number as the number check reads it, or the
   same text; with `old` null, every run of `A` with `key`).
2. Going through `A` in order, a run is run again when it is direct, or when a
   value anywhere in its inputs equals an old value that an earlier re-run
   changed. Old and new outputs of each re-run are compared leaf by leaf (by
   key path; a list by position); each leaf that differs maps its old value
   to its new one. A run whose inputs come out unchanged is not run again and
   stays in the answer.
3. Its inputs are the old ones with `key` set to `new` (direct) and each mapped
   value replaced, written as the input was: text as the shortest plain decimal
   (`43000`, `18500`, `0.4`) or the date as written; any other value keeps its
   type. One old value mapped to two different new ones: that run is not run
   again (`failed`, `a value it took is ambiguous`).
4. Its assumptions are its own, less the branch's assumption subject and less
   any sentence that holds `old` or names `key` in words. `expected` is
   `RERUN_EXPECTED` (SPEC 6.6).
5. It goes through `gate.call`. A refusal goes in `failed` with the gate's
   words, and the later runs that needed its output fail with `an earlier step
   could not run again`. The join still saves the value and records the node.

**Impact** is the same walk without running: the direct runs, then each run
of `A` holding a value an earlier listed run produced (`provenance._produced`).
`steps` are their steps; `downstream` the steps the plan's `edges` reach from
them that are not in `steps` (for a value no run used: the input's `steps` and
what they reach). Downstream steps are shown as touched and not run: the
analyst runs them when asked.

### 12.5 When a branch dies

A side branch whose outcome is `open` becomes `dead`:

- the person closes it (`close_branch`, reason `closed`);
- the person declines its proposal (`declined`);
- the person opens another branch (`new_branch`), or the analyst finishes
  answering a main-chat message sent after the branch's last message
  (`moved_on`, from layer 4's `turn_finished`): in both cases only when its
  last message is the side assistant's and it has no pending proposal.

A message in a dead side branch opens it again (`you.branch_reopened`). A
joined branch stays joined; it may go on as talk, and a later accepted
proposal there records another node (its `node` is the newest). Review
branches die only by "dismiss". A branch never joins without a node. Dead
branches stay in the history, drawn dimmed.

### 12.6 Who may join without asking

- **The person's yes is needed** for every proposal: a value that goes into
  their runs, or the plan. Their own buttons in the main chat (choose,
  confirm, "Change it", "use this") are their yes already.
- **Automatic**, shown as the assistant's doing: a build the analyst asked
  for. It does not change a figure of the person's or the plan's shape: an added step is "not
  in the plan".
- The side assistant and the analyst never join anything.

### 12.7 Less prose: chips

The analyst's reply becomes one or two sentences, the answer to the question
with the one or two numbers that answer it. Everything else is chips, built
by the harness from its own records, never asked of the model:

- **Where from.** Layer 3's `contribute`, at every `state()`, from a message's
  private `_runs` (`_chip_runs` on a join notice) and the `calc_runs` rows.
- **For each run, oldest first:**
  - *value* chips: each top-level input that no earlier run of the same
    message produced (`_produced`) and that is not today's date. Label: the
    plan input's name when `in:<key>` is a plan input, else the key in words
    with a capital (`Dinner cost per guest`). Text: `display(value)["text"]`.
    The same key with the same value: one chip.
  - *assumption* chips: each sentence of the run's `assumptions`, once per
    message; `status` and `subject.assumption` are set by layer 4 from the
    `assumptions` table.
  - *result* chips: one per run whose module carries out a step in the state
    (added steps too). Label: the step's name. Text: `show_value(output,
    spec.output)`, as the step line writes it.
- **Order:** values, assumptions, results. A join notice keeps only what the join
  changed (layer 4, from `_node`): a *decision* chip first (label `Decided`, text the
  node's text), the *value* chip of the changed input with text `new (was old)`
  (`150 (was 120)`), and one *result* chip per re-run whose text is the last leaf that
  differs between the old run's output and the new one, both as `show_scalar` writes
  them (`18,500 (was 15,050)`; the new value alone when nothing differs). The re-runs'
  other inputs and assumptions are the old answer's and stay with it.
- A withheld reply keeps its chips: a result of a tested module may be shown.
- Figures in the prose stay as they are (3.4).

### 12.8 Storage

```sql
-- harness/schema.sql (layer 0): the branch columns of threads, and the trunk
CREATE TABLE IF NOT EXISTS threads (
    ...,                                               -- id to status: SPEC 2.2, harness/schema.sql
    origin     TEXT NOT NULL DEFAULT 'you',            -- "you" | "assistant" | "reviewer" | "harness"
    subject    TEXT NOT NULL DEFAULT '{"kind": "plan"}',  -- JSON Subject
    from_node  INTEGER,                                -- trunk.id it left from, NULL before any node
    outcome    TEXT NOT NULL DEFAULT 'open',           -- "open" | "joined" | "dead"
    node       INTEGER                                 -- trunk.id it joined as
);
CREATE TABLE IF NOT EXISTS trunk (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,   -- shown as "n<id>"
    ts            TEXT NOT NULL,
    conversation  TEXT NOT NULL,
    who           TEXT NOT NULL,                       -- "you" | "assistant" | "harness" | "reviewer"
    kind          TEXT NOT NULL,
    text          TEXT NOT NULL,
    change        TEXT NOT NULL DEFAULT '{}',          -- JSON Change
    touched       TEXT NOT NULL DEFAULT '{"inputs": [], "steps": []}',
    thread        INTEGER,                             -- the branch it joined from
    after         INTEGER                              -- the main-chat message it follows
);

-- harness/needs_you/schema.sql (layer 4)
CREATE TABLE IF NOT EXISTS proposals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,   -- shown as "p<id>"
    ts            TEXT NOT NULL,
    conversation  TEXT NOT NULL,
    thread        INTEGER NOT NULL,
    kind          TEXT NOT NULL,                       -- "value" | "plan"
    change        TEXT NOT NULL,                       -- JSON, the Proposal's change
    words         TEXT NOT NULL,
    impact        TEXT NOT NULL,                       -- JSON Impact, as proposed
    status        TEXT NOT NULL,                       -- "pending" | "accepted" | "declined" | "replaced" | "failed"
    reason        TEXT NOT NULL DEFAULT '',
    node          INTEGER                              -- trunk.id once joined
);
```

Message `data` holds private keys: `_chip_runs` and `_node` (a join notice).

### 12.9 Layers

| Layer | Owns | Holds with later layers off because |
| --- | --- | --- |
| 0 | `trunk`, the branch columns, `decide`, `set_outcome`, `list_trunk`, `history`, `changed_by` | the trunk is empty and every thread is `open` until a layer records something |
| 1 | `plan_accepted` (accept, and on load), `plan_revised` (with `branch`) | its own nodes only |
| 2 | nothing yet: harness branches and `built` nodes for rebuilds and the build are reserved (SPEC 4.9), and the core accepts their kinds | — |
| 3 | chips (value, assumption without status, result); `answers/rerun.py` (`impact`, `rerun`); `store_input`; `tell_analyst`; the shorter prose | the engine is tested by calling it, without a branch |
| 4 | subjects on branches, `propose_change`, `proposals`, the three actions, the join job, the death rule, `call` and `assumption_*` nodes, assumption chip status, decision chips, `side.md`, its analyst part | — |
| 5 | review branches (origin, subject), `challenge_used`, dead on dismiss | — |

### 12.10 The two examples, as the harness runs them

**1. A branch that joins** (scenario `branch_that_joins`). The person asks for
the three payments with 120 guests. The analyst runs `wedding_total_cost`
(r1: 36,100) and `wedding_payment_schedule` (r2: 6,000, 15,050, 15,050); the
reply is a sentence or two, with chips: values (Guest count 120, Dinner cost
per guest 230, ...), results (36,100; the schedule). The person hovers
`Guest count 120`, chooses "challenge or correct", and writes "We will get no
fewer than 150 guests." (`side` with subject `{"kind": "value", "run": "r1",
"key": "guest_count", "value": "120", "input": "in:guest_count", "step":
"s1"}`). The side assistant calls `propose_change {kind: value, input:
guest_count, value: "150", words: "no fewer than 150 guests"}`. The harness
checks the words, finds 150 in them, takes 120 from the subject, and walks the
last answer: r1 is direct; r2 took 36100, which r1 produced: impact `{inputs:
[in:guest_count], runs: [r1, r2], steps: [s1, s2], downstream: [s5, s6, s7]}`.
The branch shows "Guest count: 120 → 150", touching steps 1 and 2 (and 5, 6, 7
downstream). The person says Yes. The join saves `guest_count` = 150, runs r1
again with 150 (r3: 43,000), maps 36100 to 43000, runs r2 again with
`total_cost` "43000" (r4: 18,500 and 18,500), posts "Decided on a branch:
Guest count is 150 (was 120). Run again: steps 1, 2." with a decision chip and
result chips 43,000 and the new schedule, records node `value` (who `you`,
branch t1, touched in:guest_count, s1, s2), and the branch joins. The plan
graph: the pill reads 150, steps 1 and 2 show their new results and are
marked as changed by that node.

**2. A branch that dies** (scenario `branch_that_dies`). The person opens a
branch on step 5 and asks what a sinking fund is. The side assistant
answers from the plan and the standard terms and proposes nothing. The person closes the
branch (or opens another one, or goes on in the main chat): it is dead, drawn
dimmed, no node is recorded, and the plan is as it was.

