# Architecture: Financial Advisor Harness

This file says how the harness is built: the core, the plan state document,
the layers and what each owns, the actions, how long work is reported, how
"the harness at step N" is produced, and the database. Section 12 is the
decision history the right-hand panel draws. Section 9 keeps the notes made
while each part was built.
`SPEC.md` is the contract for behaviour; it relies on sections 3 to 5 here,
which are part of the contract too. The product design is in `design/`
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
   same. That is "the harness at step N", with no stored copies.
8. The database is one schema file per layer, created on connect. No migration
   history.
9. Fixed code, no model, decides what counts: values, safety, runner,
   registry, test gate, number check. Models sit behind `harness/model/`.
10. Not here: reading account files, checking against the person's own data,
    stored copies of earlier steps.
11. The chat is a **decision history** (section 12): a trunk of decisions that
    changed the analysis, and branches, each about one thing in the plan, that
    join the trunk with the person's yes or die without a consequence.

## 2. Files and layers

Every file belongs to exactly one layer. Tests of layer K live in
`tests/layer<K>/`.

| Layer | Package | Owns |
| --- | --- | --- |
| 0 base | `harness/` top level, `harness/core/`, `harness/model/`, `harness/ui/` | `__main__.py`, `config.py`, `db.py`, `schema.sql`, `layers.py`, `terminal.py`, `replay.py`, `core/session.py`, `core/state.py`, `core/lanes.py`, `model/*` (unchanged), `ui/server.py`, `ui/page.html` (given) |
| 1 the plan | `harness/grounding/` | `layer.py`, `brief.py`, `interview.py`, `revise.py`, `research.py`, `claude_code_research.py`, `schema.sql`; given: `interviewer.md`, `planner.md`, `researcher.md`; data: `reference/`, `examples/*/brief/` |
| 2 build | `harness/calc/` | `layer.py`, `values.py`, `safety.py`, `runner.py`, `registry.py`, `gate.py`, `provenance.py`, `builder.py`, `checker.py`, `helper.py`, `notes.py`, `added.py`, `adopt.py`, `schema.sql`; given: `spec_writer.md`, `example_writer.md`, `checker.md`, `module_writer.md`, `step_helper.md`; data: `examples/*/modules/` |
| 3 answers | `harness/answers/` | `layer.py`, `agent.py`, `figures.py`, `schema.sql`; given: `analyst.md` |
| 4 needs you | `harness/needs_you/` | `layer.py`, `marks.py`, `calls.py`, `requests.py`, `side.py`, `schema.sql`; given: `analyst.md` (a part), `side.md` |
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
still selects its step, as today.

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
    def __init__(self, config, *, model_factory=get_model, desk_factory=None): ...
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
  `progress(text, step=None)` (sets its `activity` entry), `post(message)`
  (adds to `chat` or a thread), and `wait(kind, data) -> answer` (main lane
  only: sets `waiting`, blocks until an action answers it).
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
| `confirm_example` | `step`, `n` | 2 | that example exists and is not yours already | Records "confirmed by you" |
| `confirm_plan_check` | `step` | 2 | the step has departures not yet confirmed | Clears the plan-check mark |
| `run_tests` | `step` | 2 | the step has a registered module | Queues a test run |
| `choose` | `decision`, `option` | 4 | that decision is the one waiting | Posts the option's text as the person's message (`who` "you", the decision's step), then answers the decision with the option number; trunk node `call` (an answer in words records it too) |
| `confirm_assumptions` | `message` | 4 | that message's notice is open | Confirms its assumptions; trunk node `assumption_confirmed` |
| `side` | `text`, `step`?, `thread`?, `subject`? | 4 | always | Without `thread`: opens a branch (origin `you`) on `subject` (default: the step, else the whole plan) and marks the person's other answered side branches dead. With `thread`: says something in that branch (side or review); a dead side branch opens again |
| `accept_proposal` | `proposal` | 4 | the proposal is pending, and the main lane does not wait on a decision | Status `accepted`; queues the join on the main lane (section 12.3) |
| `decline_proposal` | `proposal` | 4 | the proposal is pending | Status `declined`; the branch is dead |
| `close_branch` | `thread` | 4 | a side branch whose outcome is `open` | The branch is dead; a pending proposal in it is declined |
| `use_challenge` | `challenge` | 5 | the challenge is open | Marks it used; trunk node `challenge_used` (who `reviewer`), the review branch joined; posts the person's "use this" message and routes it |
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
| `you.side_opened` | gains `subject` | `side` without `thread`, as today |
| `you.branch_dead` | `thread, reason`: `closed`, `declined`, `moved_on`, `new_branch` | layer 4 (a dismissed review branch is dead with `review.dismissed`, layer 5) |
| `you.branch_reopened` | `thread` | a message in a dead side branch |
| `you.proposed` | `thread, proposal, change, impact` | `propose_change`, when it passes the checks |
| `you.proposal_refused` | `thread, reason, change` | `propose_change`, when it does not; `reason` one of `not_their_words`, `unknown_input`, `value_unbacked`, `ambiguous`, `same`, `unknown_step`, `one_per_reply` |
| `you.proposal_accepted`, `you.proposal_declined` | `thread, proposal` | the two actions |
| `you.joined` | `thread, proposal, node, runs, failed` | the join, when it ends |

## 7. "The harness at step N"

- **One setting.** `HARNESS_LAYERS=N` (default 5) turns layers above N off.
  The facilitator presents step N on the finished tree with
  `HARNESS_LAYERS=N uv run python -m harness ui`.
- **A local default.** When `HARNESS_LAYERS` is unset or empty, `config` reads one whole number from
  `my/var/layers` (git-ignored, under `my/` like everything the harness reads locally); no file means 5. The
  variable wins over the file. `python -m workshop at N` writes the file, so a presenter or an attendee needs no
  shell export; deleting it returns to the finished tree. A bad file is an error that names it.
- **Files absent.** A tree without the packages of layers above N is the
  harness at step N; discovery stops at the first missing package. This is
  how an attendee's copy is at step N (`workshop start N` removes the files of
  layers N and above; `finish N` puts back layer N). Nothing is stored but the
  finished tree.
- **What each layer registers** is its `Layer` object (4.3): layer 1 plan
  actions, routing before acceptance, `ground`; layer 2 build actions,
  routing for steps, `build`; layer 3 routing after acceptance, its tools and
  prompt, `ask`, figures; layer 4 marks, decisions, automatic builds, side
  threads, its tools and prompt part; layer 5 the reviewer, challenges, its
  prompt part.
- **What tests assume.** `tests/layer<K>/conftest.py` sets
  `HARNESS_LAYERS=K` for every test in it, with the files of every layer
  present. So a test of layer K checks the harness at step K, inside any later
  tree, and is never true only at an earlier step. A test of layer K never
  asserts that a later layer's key, tool, table or event is absent, and never
  counts all tools, keys or events. `tests/layer0` also checks that
  discovery stops at a missing package and at the setting.
- **Shared files** (the core, the server, the page, the terminal, replay,
  `__main__.py`) are the same at every step. They act on what layers register
  and on which keys the state document has. The page is complete at every
  step and hides what it has no keys for.
- **Where this is not fully additive.** The core knows the generic shapes later
  layers fill (threads, decisions in `waiting`, the step-line rule reads keys
  of layers 2 to 5, the trunk and the branch columns of section 12); it does
  not import them, and it never names a kind of change. The page is one given file for
  every step, not built step by step. The analyst prompt is composed of parts,
  so a later part must only add, never contradict an earlier one; the layer 4
  part says plainly what it changes. These are the fallbacks, and they are
  enough for the four uses.

## 8. The database

The database is local and disposable: one `schema.sql` per layer, `CREATE
TABLE IF NOT EXISTS`, applied on every connect for the enabled layers. No
migration history. After a schema change, delete `my/var/harness.db`.

## 9. Implementation notes

Notes made while the harness was built, one package at a time (A0 to A6 for
behaviour, B2 for the page, C1 for the workshop tool, D0 to D6 for the decision
history of section 12, then fixes from end-to-end and live runs). They record interfaces and choices the contract leaves open.
Where a note mentions an earlier package, a later one, or the previous version
of the harness, it is history: `SPEC.md` and sections 1 to 8 are the contract.

- **A0 · Discovery.** A layer package's `layer.py` holds `LAYER`. A package whose folder or `layer.py`
  is missing counts as missing; any other `ModuleNotFoundError` is an error. `layers.enabled()` returns
  `layers.BASE` (number 0, schema `harness/schema.sql`) first; the state's `layers` lists the numbers.
  All five packages have a skeleton `layer.py` now; packages 1 to 3 carry the version 1 tables their
  kept code uses (`grounding/schema.sql`: `lookups`; `calc/schema.sql`: the six tables of SPEC 4.1;
  `answers/schema.sql`: `inputs`).
- **A0 · Session.** `Session(config, *, model_factory, desk_factory, layers=None)`: `layers` replaces
  discovery, for tests. `harness.core.Core` is `Session`. What layers use: `conn` (the calling
  thread's connection; in a job, the job's), `model()` (made once, shared), `memory` (a dict for
  in-memory layer state), `desk_factory`, `waiting`, `lane(name)`, `queue(lane, run, *, what, step,
  text, key)` (`key`: at most one queued job with that key per lane, for coalescing), `answer(data)`
  (NotNow when nothing waits), `post(text, *, who, kind, step, thread, data)`, `update_message`,
  `new_conversation()`, `hook(name, *args)`, `record(kind, payload, actor)`, `changed()`, `version`,
  `wait_for_change(version, timeout)`. `Work` has `conn`, `model`, `config`, `lane`, `conversation`,
  `progress(text, step, what)`, `post`, `wait(kind, **data)`, `queue`, `hook`, `record`, `changed`,
  `desk()`. Thread helpers (`add_thread`, `set_thread_status`, `list_threads`) are in `core/session.py`.
- **A0 · Routing.** `route(core, message)` returns `handler(work, message)` or None; the activity
  `what` is `handler.what` (default `answer`). `message` is `{"id", "text", "step", "notice"}`, and is
  also what a message answers a wait with; an action answers with what it passes to `core.answer`. A
  message typed while the main lane works is stored with `queued: true` and routed when the lane
  reaches it; a job that calls `wait` first takes the oldest such message. A waiting job is not in
  `activity`.
- **A0 · Messages.** Ids are integers shown as `m<n>` and `t<n>`. The keys of a message's `data` are
  merged into the Message as they are; keys starting with `_` are the harness's own (the person's
  notice reference is `_notice`). Layers put `figures`, `decision`, `notice`, `sources` there.
- **A0 · Actions and events.** `act` raises `BadAction` (a ValueError: unknown action, bad payload;
  the server gives 400) and returns `(False, reason)` on NotNow. Every action, applied or not, clears
  `error`. Events: `core.message` (every message), `core.action` (every applied action),
  `core.job_failed`, `core.check`; `session_id` is the conversation id.
- **A0 · Step line.** Text over 18 characters is cut to 17 and `…`; a boolean is `yes`/`no`. The core
  keeps at most one `needs_you`: an open decision's step, else a step a layer set, else the first
  `not_built` step with a disagreement or fewer than two examples whose `checked_by` is set.
- **A0 · Front ends.** The server serves a placeholder page while `ui/page.html` is missing, and a
  500 JSON body for a fault in the harness. The terminal reads a line when neither the main nor the
  side lane works. The legacy-layout check of version 1 is gone.
- **A0 · Until later packages.** `replay` is not a command until A6 rewrites `replay.py` (the old file
  is deleted); `ground`, `build` and `ask` come back with A1, A2b and A3. `calc/agent.py`,
  `decisions.py`, `analyst.md`, `example_helper.md`, `builder.py` and `adopt.py` are version 1 code,
  kept for A2a to A4a to replace, not wired to the core; `agent.py` lost the assumption gate, findings,
  verifier and asides, and its build requests no longer ask. The old `decisions` table is in no schema.
- **A0 · Tests.** Unit tests of kept code were parked: `tests/layer1/test_wikipedia.py`,
  `tests/layer2/test_values.py`, `test_safety.py`, `test_provenance.py`, each folder with a conftest
  that sets its `HARNESS_LAYERS`.
- **B2 · Gaps between the page and the state document.** Closed in section 3: a thread has `after`, an
  activity entry has `thread`, an input has `value`, a decision message carries `figures`; and `choose`
  posts the person's message (section 5). The core owns `after` (`add_thread` takes it, default the last
  main message; the `threads` table has the column; delete `my/var/harness.db` after pulling this) and
  `thread` (`queue(..., thread=)`, `work.progress(..., thread=)`). The page draws a thread right after
  its `after` message (a thread with none goes after the last message), the side thread's "Answering"
  from the activity entry, an input's value in the step pop-up, a decision's figures, and no longer
  makes up the person's message for an answered decision. Page source: `design/page/` (`python
  design/page/build_page.py` rebuilds `harness/ui/page.html`). Samples: `tests/layer0/states/`.
- **B2 · For layer 1.** Each input in `inputs` is made without `used` and `value`; layer 3 adds them.
- **B2 · For layer 3.** Set `inputs[id]["value"]` to the saved input's value as written (null while
  none), beside `used`.
- **B2 · For layer 4.** `choose` posts the option's text as the person's message before it answers;
  a decision message's `text` is the question and its `figures` come from the number check, as for an
  assistant reply; side jobs queue with `thread=` (or call `work.progress(thread=)` once the thread
  exists) so `activity` names it.
- **B2 · For layer 5.** Review threads start with `add_thread` as they are, so they follow the last main
  message when the pass finished; pass `after=` to place one elsewhere.
- **A1 · Files.** Beside `layer.py`, `interview.py`, `revise.py`, `research.py`: `brief.py` holds the schema,
  `validate_brief`, `draw` (the layer 1 keys of the state document from a brief), `load_brief(folder)` (the
  confirmed brief with its `meta`, else None), `step_fingerprint`, `input_ids` and `person_quotes`. There is no
  example selector in layer 1: `HARNESS_EXAMPLE` is layer 0's. `research.default_desk(config, conn)` is the desk
  used when the session was given no `desk_factory`.
- **A1 · Interview state.** While there is an interview, its state dict is `core.memory["plan"]` and
  `grounding_state.json` (beside the database); the state document draws from the memory. When the plan is
  accepted the file and the memory entry go and the confirmed brief in `brief_dir` is the plan (re-read when
  its file changes). `loaded` resumes an unfinished interview from the file, without asking its last question
  again. If a job died (a failed model call), the next message the person sends reaches `route`, which resumes
  the interview with that message.
- **A1 · Phase.** `proposed` lasts from the first valid brief until acceptance, including while a correction is
  being worked on (the diagram stays drawn); `waiting` is `{"kind": "plan"}` only while the plan awaits
  acceptance or a correction. A draft saved after three rejections is not a plan: the phase stays `interview`,
  the harness posts where the draft is, and the interviewer is told to ask the person one question.
- **A1 · Starting.** `start` and the routed first message both begin the interview; a new conversation is made
  only when the current one holds something besides the opening message. The opening statement is the first
  message of the interviewer's conversation, with a `[harness]` line listing the terms already read up on.
- **A1 · Words and origins.** `validate_brief(brief, lookups, words)`: `words` is every message the person
  wrote in this interview (opening, answers, corrections). A revision may also quote what the accepted plan
  already quotes. A brief's `looked_up` origin is the address; the state shows `{title, url}`, the title from
  the lookups, else the address. An input's id is `input_ids(brief)[name]` (the ARCHITECTURE 3.2 rule, with
  `_2`, `_3` for names that would give the same id); layer 3 should use it. Inputs are drawn without `used`
  and `value`. A step's id in the state is the brief's process id.
- **A1 · Fingerprint.** `brief.step_fingerprint(brief, step_id)` is the one SPEC 4.4 defines (layer 2 stores
  and compares it; do not rewrite it): SHA-256 of the sorted-key compact JSON of `kind`, `method`, `formula`,
  `needs` (in brief order, names as written), `produces` and the `what`/`handling` pairs of the step's
  particulars, sorted. A step's name, cadence and origin are not in it.
- **A1 · Revising.** `revise_plan(work, *, words, step=None, by="person")` runs on the calling job's lane
  (layer 3's `change_plan` calls it). Layer 1 itself routes nothing after acceptance. `plan_changed(work,
  changed)` is called after every saved revision, with `changed` possibly empty. Three rejections by the
  checks, a reply without `write_brief`, or eight calls end it with an `error`.
- **A1 · Lookups.** `look_up_general` returns a research entry with status `failed` and an `error` for a refused
  query; it never raises. The interview limits are v1's (twelve terms, one lookup per term).
- **A1 · Terminal.** `ground` prints the proposed plan as text before it reads (the terminal driver only
  prints chat messages), stops when the phase is `accepted` and the main lane is idle, and exits 0 then, else 1.
  A message typed in the terminal has no step, so a correction with a step is a page action.
- **A1 · Not core.** Nothing in `harness/core/` was changed.
- **A2a · Files.** `builder.py` is the unattended engine; `checker.py` the second pass; `adopt.py` adoption without
  asking; `registry.py` also holds the build records (`get_build`, `save_build`, `update_build`), `step_status`,
  `build_view`, `plan_fingerprint`, `calculation_steps`, `find_step`, `module_for_step`, `examples_from_golden`,
  `latest_test_run`; `gate.step_refusal`. Deleted: `agent.py` (nothing used it), `example_helper.md`, and version 1's
  terminal loops (plan question, the person's check of every example, the example helper). `decisions.py` and
  `calc/analyst.md` stay for A3 and A4a to replace (`ACCEPT_WORDS` is inlined in `decisions.py`).
- **A2a · What A2b calls.** In `builder.py`: `start_build(core)` (raises `NotNow`; the `build` action is already
  wired to it), `run_build(work)`, `build_step(work, step_or_id, *, rebuild=None, code_only=False) -> {"step",
  "outcome", "module", "reason"}`, `building_step(memory)`, `build_running(memory)`, `plan_of(config)` (the
  confirmed brief or None), `record_confirmation(conn, step_id, n, *, answer=None, session_id) -> {"rebuild":
  bool}` (answer None confirms as it stands; raises ValueError for an unknown example or an answer that does not
  fit the output type; the number check of the answer is the helper's; when `rebuild` is true, queue
  `build_step(work, step, code_only=True)`), `confirm_departures(conn, step_id, *, session_id)`,
  `run_step_tests(conn, step_id, *, session_id)` (the `run_tests` action; ValueError when the step has no module),
  `format_sections`. In `registry.py`: `build_view(conn, brief, step_id, building=False)` is the whole `Build` of
  ARCHITECTURE 3.3; `get_build(conn, step_id)` is the record the helper shows (spec, departures, examples,
  disagreement, reason). `layer.py` already has `contribute` (the `build` key on every step, null but on
  calculation steps; added steps drawn after the plan's, `in_plan` false), the `build` action, and the hooks
  `loaded` and `plan_accepted`; A2b adds `route`, the other three actions, the `build` command and `expects`.
- **A2a · What A3 and A4a call.** `gate.call` keeps its signature. `build_step(work, "added_<n>")` builds a step
  made with `added.add_step` (layer 4's `new` case); `rebuild=NAME` is the `replace` case. `calculation_steps`,
  `module_for_step` and `registry.list_modules` describe what is built.
- **A2a · Status.** `step_status(conn, brief, step_id) -> (status, reason)`: `none` (no record, no module),
  `not_built` (the record's reason), `stale` (reason `the step changed in the plan` when the plan's fingerprint
  differs from the record's, `its files changed` when the module's files changed, `its folder is missing` when they are gone), else `built`.
  `building` comes from `building_step(memory)`. `build_steps` has one more column than SPEC 4.2,
  `step_fingerprint`, because a reused module carries a step other than its own; `modules.step_fingerprint` is of
  the module's own step. `test_runs.reason` may also be `adopt`.
- **A2a · The gate.** Besides `STALE` (the module's own step has a different fingerprint in the confirmed plan, or
  left it), the gate refuses a module whose own step's last build ended `not_built` (`gate.NOT_BUILT`): after a
  failed rebuild the old module stays registered, but it disagrees with an example the person or the passes
  agreed on, so it must not answer. With no confirmed plan, or a module registered without a fingerprint, the
  gate checks neither.
- **A2a · Build rules.** A rebuild of a step whose own module exists keeps the module's name (the spec writer gets
  `[current spec]` and no `reuse_module`). Examples the person confirmed are carried into a full rebuild first,
  if they still fit the spec; the writer's are numbered after them. A confirmation is applied to the record at
  once; `example_confirmations` is the log, its `n` the number at that time. `code_only` first tries the code
  already there (the module's, else the last failed attempt's) against the examples as they now stand, and calls
  the code writer only if that fails: confirming a left-out example costs no model call. The writer must give at
  least three examples; no maximum is enforced. A failed model call counts as an attempt of its phase (its error
  goes in `build.not_built`'s `error`); a failed checker call leaves every example out. `departures_confirmed`
  survives a rebuild only when the departures are the same. `step_built` is called by `build_step`, so layer 4's
  builds call it too. `BUILD_NEEDS_YOU` lists the step names, comma separated; `BUILD_DONE` counts steps built
  after the build, whatever built them.
- **A2a · The Build view.** `tests`/`passing` are the unit tests of the module's latest test run, `examples`/
  `examples_passing` the worked examples of that run (before any run, the checked examples); `tested_at` is that
  run's time. `code` comes from the module folder, else from `_build/<name>` (the last failed attempt).
  `disagreement` is shown only while `not_built`. `spec` holds `formula`, `inputs`, `output`.
- **A2a · Adoption.** `loaded` queues adoption as a main-lane job (`what` `tests`) only when there is a confirmed
  plan and a candidate folder; `plan_accepted` adopts in its own job. A folder with no readable spec, or naming no
  calculation step, or a step another unchanged module carries out, is left alone without an event. A registered
  module whose files changed is stale in the session that sees it and is adopted again on the next load if its
  tests pass (SPEC 4.6). Example mode needs nothing more: `main()` copies the example, the session adopts it.
- **A2a · Events.** Renamed to the `build.` prefix: `build.tests_run` (every test run, gate's included),
  `build.registered`, `build.note`, `build.step_added`. Payloads: `build.started {step, code_only, rebuild}` (per
  step), `build.second_pass {step, module, agreed: [n], left_out: [{n, answer, why, given}]}` (`given`: what the checker sent, kept as evidence when it did not count), `build.not_built {step, reason,
  error}`, `build.adopted {module, step, outcome: adopted | not_built, reason, test_run_id}`, `build.finished
  {steps}`; the others carry `step`. The gate's `calc.run`, `calc.refused`, `calc.run_failed` keep their names.
- **A2a · Numbers copied from the inputs.** SPEC 4.5 says a checker's answer counts only when its own working
  shows every number in it; the example writer's check was the same. In the live build both rejected correct
  answers that only repeated a date of the example's inputs (the writer lost an attempt, the checker an
  example). Decision: the example's inputs are a source too, for the writer's expected answer and the checker's
  answer. A number that is in neither is still refused.
- **A2a · Not done here.** `registry.module_dir` and the staging folder still read `load_config()` rather than the
  session's config (as in version 1; a Session made with another config than the environment's would build
  elsewhere). The example writer is asked once more only for the step's whole set, not per left-out example.
- **A2b · Files.** `helper.py` is the step helper (`route`, `handle`, `wants(core, step_id)`, `rebuild_code(work,
  step_id)`); `layer.py` has the actions `confirm_example`, `confirm_plan_check`, `run_tests`, the `build` command
  (`run_build_command(session, write=)`: builds, prints the activity and a line per calculation step, exit 0 only when
  all are built) and the `steps` expectation. `wants(core, step_id)` takes the session (or anything with `conn` and
  `config`); layer 3 calls it as `helper.wants(core, step_id)`.
- **A2b · The state.** `build` is a key of every step once layer 2 is on: null before the plan is accepted and on steps
  that are not calculations. While a step is `building` its `reason` is "" and its `disagreement` empty (the old ones
  are not shown while the step is rebuilt). The build button's label and progress are not a key of their own: the page
  works them out from `activity` (`what` `build`, `step`, `text`) and the steps' `build.status`. Steps "not in the
  plan" are the added steps, last, `in_plan` false, with `needs` and `inputs` empty (their `needs` is free text).
  `tests/layer0/state_shape.py` checks the Build's spec shape always, and what a live state must keep
  (`build_problems`, `problems(state, strict=True)`: counts, reasons, numbering, line) only when asked, since the
  hand-written samples are sparse.
- **A2b · The helper's checks.** One model call, no retry. A `correct` answer must fit the spec's output type, have the
  shape of the example's `expected` (same keys, same list lengths), and every number must be in the person's message or
  in the example's `inputs`, `expected` or `second_pass` (so "the second answer is right" works). An `explain` message
  is number-checked against the person's words, the step, spec, departures, examples, disagreement and reason. Any
  failure, an unknown example, a missing tool call, or `confirm` 0 with no departures to confirm gives
  `HELPER_UNCLEAR` (a harness message with the step) and changes nothing. `note` and `rebuild` keep the person's own
  words (`message["text"]`) as the note, not the model's. The helper's own text (`explain`) is posted as `assistant`;
  every other line (`NOTE_KEPT`, `EXAMPLE_CONFIRMED`, `EXAMPLE_CORRECTED`, `DEPARTURES_CONFIRMED`, `REBUILDING`,
  `STEP_BUILT`, `STEP_NOT_BUILT`) as `harness`, with the step. They carry no `figures`. A rebuild or a code-only check
  runs inside the helper's job (activity `helper`, then `build` per phase), and ends with `STEP_BUILT` or
  `STEP_NOT_BUILT`. New event `build.helper {step, action, example, accepted}`, one per helper turn.
- **A2b · Actions.** `confirm_example` is refused (NotNow) for an unknown step or example, an example that is already
  yours, or a step being built now; a missing or ill-typed `step` or `n` is a BadAction. When `record_confirmation`
  says `rebuild`, a main-lane job (`what` `build`) runs the code-only rebuild, with no model call when the module's code
  already passes. `confirm_plan_check` is refused with no unconfirmed departures. `run_tests` queues a main-lane job
  (`what` `tests`, one per step in the queue) and is refused when the step has no registered module.
- **A2b · Expectation `steps`.** `check(value, session)` gets the replay's Session and compares `value` with the `steps`
  of the latest `build.finished` event (`seen` is that map); it validates a non-empty map of step id to `built`,
  `reused`, `kept` or `not_built`. A6 passes the Session as the context.
- **A2b · The wedding seed.** The input "Wedding date" is now in the `needs` of s2 (the payment schedule, the one step
  whose module takes `wedding_date`). The seed records no step fingerprints (adoption computes them from the plan at
  adoption time), so nothing had to be updated and the seeded modules adopt as `built`, not `stale`.
  `tests/layer1/test_brief.py` no longer special-cases it, and `tests/layer2/test_adopt.py` checks the input's step.
- **A2b · Not changed in `harness/core/`.** Layer 2 touched only `harness/calc/` (`helper.py` new, `layer.py`, a two-line
  change in `registry.build_view` for the `building` status).
- **A3 · Files and interfaces.** `answers/agent.py` (the analyst turn, `Turn`, the number-check sources, the system
  prompt, the three tools), `figures.py` (`figures(text, sources, *, step_of_run, input_of)`, `input_backing`),
  `layer.py` (`contribute`, `route`, `ask`, expects). `Turn` has `work`, `message`, `runs` (calc_runs ids made in the
  turn), `reply` (the id of the message that ended it), `withheld`, `corrections`, and `unbacked(value)`, `sources()`,
  `plan()`, `today()`, `record()`. A tool is `(ToolSpec, handle(turn, call) -> result)`; the result is
  `agent.tool_result(call, content, error=False)`. The hook is `turn_finished(work, turn)`. The analyst prompt is the
  `prompt` files of the enabled layers, joined, then `## What you know` with layer 3's sections (`today`, `goal`,
  `particulars`, `inputs the plan names`, `process` with each calculation step's `module` and `build` status,
  `modules`, `saved inputs`, `notes`, and `earlier runs in this conversation`, the last eight, so a new process knows
  them), then every other layer's `context(conn)` (called with the connection only, as 4.3 says).
- **A3 · No action.** Layer 3 registers no action: the person speaks through `say`, and the `ask` command is `say`
  through the terminal driver (`ask [QUESTION...]`; it exits 1 with a pointer to `ground` when there is no accepted
  plan, because a message then would start an interview).
- **A3 · Today.** `core.memory["today"]` (a date or an ISO date) replaces the clock for the prompt, the number check
  and the gate's callers; replay sets it from the scenario's `today`. Without it, today is the real date.
- **A3 · Number check.** Sources of the reply check: the confirmed plan (without `meta`) and the added steps, today,
  every message the person typed in the main chat (a choice made by `choose` is posted as one, so decision words
  need no source of their own), saved inputs, notes, and the inputs and results of this conversation's runs. Tool
  inputs are checked too: `run_module`'s `inputs` and `assumptions` (not `expected`, which is never shown) and
  `save_input`'s `value`; a refusal goes back to the model as an error result and counts as `ask.correction`
  (`reason` `run_module` or `save_input`). The reply check is corrected once per turn (`reason` `reply`), then
  withheld. A withheld or stopped notice is a `harness` message (kinds `withheld`, `text`) and carries no `figures`;
  the model is told of a withheld reply in the person's next message.
- **A3 · Figures** (the order of runs and "a number the person gave that a result repeats" are superseded by E2E, below). For `trace`, only a run's result is labelled `run` (a run's inputs back a number but never
  lead to the step), and runs are given newest first so that of several runs showing the same number (a later step
  repeats what an earlier one produced) the earliest is the source. A `run` figure carries the run's id and its
  module's own step (`spec.step_id`), or no step when the plan no longer has it. `run` wins over `input`, `input`
  over the person's words, as `trace` orders them; so a number the person gave that a step's result happens to
  repeat leads to that step. A figure from a saved input gets `input` only when the name is a brief input id
  without `in:` (the model is told to use the plan's names). Only assistant replies carry `figures`.
- **A3 · Runs and the last answer** (what counts as the last answer is widened by E2E, below). A turn's reply (or withheld or stop notice) keeps the turn's run ids in its
  private `_runs`. "The last answer" is the latest such message with at least one run, so a reply that only asks or
  explains leaves the steps and inputs of the answer before it lit; a newer answer with runs replaces them. A
  withheld answer still lights the steps it ran. `last_run` is the module's latest run in the conversation; for a
  range (two runs of one module in a turn) it is the later run, and each number's figure names its own run.
  `message` is the message that ended the turn of that run, else null. Layer 3 sets `last_run` on every step (null but
  on calculation steps once the plan is accepted) and `value` and `used` on every input; it never sets
  `unconfirmed` (layer 4).
- **A3 · Saved inputs on the plan.** `inputs[id].value` is the saved value as written for the saved name equal to the
  id without `in:` (a non-text value is shown as JSON). Saved inputs are kept across conversations.
- **A3 · Routing.** The analyst takes a message in phase `accepted` unless it has a step and `calc.helper.wants(core,
  step)` is true. The model's messages are kept in `core.memory["analyst"]`, started again in a new conversation; a failed
  model call drops the half turn.
- **A3 · Replay expectations.** `runs`, `shown`, `not_shown`, `max_withheld`, `max_corrections` as in version 1;
  `check(value, session)` is given the Session and reads `calc_runs` and the `ask.*` events of its conversation. A
  `runs` entry matches when the module ran with those inputs written as text (`"150"`, not `150`).
- **A3 · Not changed outside layer 3.** Nothing in `harness/core/` or `harness/calc/`. Shared: `tests/layer0/state_shape.py`
  checks layer 3 (assistant messages carry `figures`, figures name known inputs, `last_run.message` is in the chat,
  `used` agrees with the steps of the last answer).
- **A4a · Files and interfaces.** `marks.py` (assumption store, notices, `confirm`, `correct`, `route`, hook
  `turn_finished`), `calls.py` (`ask_decision`, `choose`, `read_choice`), `requests.py` (`request_module`), `layer.py`
  (`contribute`, `context`, `tools`, the actions `choose` and `confirm_assumptions`, hooks `loaded` and
  `turn_finished`, expects `decisions`, `marks`, `added`). A4b adds `side.py`, the `side` action, the real `threads` and
  the `side_threads` expectation to `layer.py`; until then `threads` is `[]` (the state shape wants the key once layer 4
  is on) and the terminal's `/side` is refused as an unknown action.
- **A4a · Tables.** `assumptions (id, key UNIQUE, text, status, words, ts)` and `run_assumptions` as SPEC 6.1;
  `decisions` also has `message` (the decision message) and `status` (`open`, `answered`, `dropped`). The row is written
  when the question is asked, with `choice` NULL. `loaded` marks every row still `open` as `dropped` (its process is
  gone): the state then shows that decision as `answered` with `choice` null, nothing waits, nothing `needs_you`, and the
  analyst is not told of it (it may be asked again). `Decision` and `Calls` in the state are read from the table on every
  call, not from the message; the message keeps the decision as asked.
- **A4a · Marks.** Assumptions are global (the key is unique), so one confirmation clears the same sentence wherever it
  is the only unconfirmed one. A run's assumptions are stored by the `turn_finished` hook and, for a run no hook saw
  (a turn that failed), when the state is read (`marks.of_run`: it only inserts what is missing). A step's `unconfirmed`
  is its `last_run`'s assumptions whose status is not `confirmed`; `corrected` counts, so a corrected step keeps `◌`
  until it is run again without the sentence. The notice goes on the turn's final message even when that is a withheld
  or stopped notice (the steps are marked either way, and a notice is the only thing the person can confirm from).
  A notice reads `confirmed` in the state once every assumption in it is confirmed, whichever answer confirmed them.
  `confirm_assumptions` confirms all of the notice's assumptions (it overrides `corrected`: the person confirms again);
  a "Change it" message corrects only those not yet confirmed (all of them when none is open). The `CORRECTED` line is
  put before the person's words in the text given to `answers.agent.answer`, so the `ask.message` event holds that text.
  A message with a notice reference that names no notice is an ordinary message.
- **A4a · Calls.** `step` may be any plan step, added ones too, whatever its kind: a decision on a `from_you` step puts
  `Needs you · your call` on it. `calls` is non-null for `your_call` steps and for any step a decision of this
  conversation names; `records` are the answered ones. Decisions are scoped to the current conversation; the section
  `decisions` too. "One per reply" of version 1 is not kept (a tool cannot tell which model reply a call came in); the
  limit is two per person message, and a second question can only follow the first one's answer. `run_ids` accepts
  `4`, `"4"` or `"r4"`. An answer in words: a number, `option N`, an option's words, `yes` for the suggestion; else
  `something else` with the words. `choose` posts the option's text as the person's message (with the decision's step)
  before it answers. A "Change it" message that arrives while a decision waits answers the decision (the core gives a
  waiting job the message first); its notice is not processed.
- **A4a · Requests.** The tool takes an optional `name` for a new step. Limit two per person message, counted once the
  words pass the checks, whatever the outcome. The build runs inside the analyst's turn on the main lane (the person sees
  `activity` with `what` `build` and the new step, and the harness message when it ends, before the answer); an
  exception in the build is a `not_built` result. `request_module` for `step` is refused only when the step's status is
  `built` (a stale step is built again). Posted: `BUILT_NOT_IN_PLAN` for `new`, else `BUILT_STEP`, or `NOT_BUILT_STEP`;
  `you.module_requested` also carries `seconds`.
- **A4a · Expectations.** `decisions`: a list of `{step, choice?, count?}`; each needs at least `count` (1) answered
  decisions on the step, with that choice when given. `marks`: `{min?, max?}` open notices in the state at the end.
  `added`: at least that many `you.module_requested` events of case `new` that did not end `not_built`.
- **A4a · Changed outside layer 4.** `answers/agent.py`: `Turn.extra` (a dict a later layer's tools count in, within
  the turn). Deleted: `calc/decisions.py` and `calc/analyst.md` (version 1, replaced by `needs_you/calls.py` and
  `analyst.md`). `tests/layer0/state_shape.py`: `layer4_problems` (run by `problems(strict=True)`).
- **A4a · For A5.** `turn_finished` of layer 4 runs before layer 5's (layer order), so a turn's notice exists when the
  reviewer's hook looks at it. New assumptions are in the `assumptions` table (`marks.of_run(conn, run_id, sentences)`
  gives a run's with their status); `request_module` builds go through `build_step`, so `step_built` fires for them.
  `Turn.extra` is free for layer 5's tools.
- **A4a · Seen with the real model** (`claude` CLI, wedding example, layer 4). The analyst marked a derived date and
  a dinner price, but said some assumptions only in its prose (the 6,000 counting toward the total) and left them out of
  the run's `assumptions`: the mark is only as complete as that list. Twice it wrote a run id in its reply ("run 15"), which
  is not a number source, so one answer was withheld. An automatic build of a new step took 45 seconds.
- **A4b · Files and interfaces.** `side.py` (the `side` action, `reply(work, thread, upto)`, the sections the side assistant
  reads); `layer.py` registers the action, makes `threads` from `core.list_threads` (review threads of layer 5 are in the same
  table; each message gets `sources: []` and each thread `challenge: null`, which layer 5 overwrites) and the expectation
  `side_threads` (int: at least that many side threads with an assistant message). The terminal has `/side @STEP TEXT`, `/side tN
  TEXT` and `/reply TEXT` (the latest side thread); it reads a line only when the main lane is not working, so from the terminal a
  thread opens while the main lane waits or is idle, not during a build.
- **A4b · What it sees.** Built from `state()` on the side lane, so it is what the person sees: the plan (goal, scope, assumptions,
  done, open questions, glossary, inputs with saved values, every step with formula, needs, produces, particulars), the attached
  step in detail (spec, examples with `checked_by` and the second answer, disagreement, last run, unconfirmed, decisions, open
  challenges; never code), the last ten main-chat lines as text and, in a review thread, its challenge. The model's messages are the
  thread's own (person and its replies, up to the message answered; reviewer words and withheld notices left out). Number sources: all
  of that, the thread's messages and this reply's lookups.
- **A4b · Rules.** `side` with a `thread` that is not in this conversation is refused (NotNow); an unknown `step` or a malformed id
  is a BadAction. Six person messages per thread (NotNow after). Any thread, whatever its status, takes a reply. One job per message;
  two quick messages give two replies, the first one seeing only up to its own message. Three lookups per thread, counted by
  `you.side_lookup` events and including refused ones; only a general term goes out (`look_up_general`). A second unbacked reply is
  posted as an assistant message of kind `withheld` (thread messages carry no `kind` in the state; the page shows it as text), and
  no model failure is caught: a failed call is a `core.job_failed` and `error`. Events as SPEC 6.5, with `thread` in every payload;
  `you.side_withheld {thread, numbers, text}`. There is no `you.side_correction`.
- **A4b · Three fixes of A4a.** A withheld reply gets no notice (the steps keep `◌`; a stopped turn still gets one). The chat says
  `BUILDING` (a harness message with the step) before an automatic build starts, then `BUILT_*` or `NOT_BUILT_STEP` as before. The
  layer 4 analyst part now says every assumption relied on must be in the run's `assumptions`, not only in the reply's words.
- **A4b · Seen with the real model** (`claude` CLI, wedding example, layer 4). A thread opened on step 1 while the main lane worked
  was answered in about 6 seconds and a follow-up in about 5, the main answer finished after, with no mention of the thread; the
  thread followed the person's message. The side assistant did not call `look_up` for "sinking fund" (the plan's glossary had it,
  noted as from general knowledge) and offered to.
- **A4b · Changed outside layer 4.** `harness/terminal.py` (`/reply`, `@STEP`, `tN` forms), `SPEC.md` 2.5 (the two table rows). No core change.
- **A5 · Files and interfaces.** `reviewer.py` (a pass: `run_pass(work, trigger)`, `queue_pass(core_or_work, trigger)`, the
  user message, the checks `check`/`keep`, `new_assumptions`), `layer.py` (hooks, `contribute`, the two actions, the
  `challenges` expectation), `schema.sql` (`challenges` has one more column than SPEC 7.4, `conversation`; `review_passes` has
  `conversation`, `seconds` and `assumption_mark`). A pass is its own model conversation: `reviewer.md` as the system prompt
  and one user message of sections (today, plan, built specs, assumptions with their steps and status, decisions, saved inputs,
  last eight runs, earlier challenges, the person's replies in review threads). It never sees the main chat, the analyst's
  messages or any code. Challenges belong to the current conversation (a new interview starts them afresh).
- **A5 · When.** Besides SPEC 7.1, a session that opens on an accepted plan with no pass yet in the conversation queues one
  (`loaded`, trigger `loaded`): a seeded example is accepted from the start and would otherwise never be reviewed. "A
  never-seen assumption" is an assumption id of the turn's runs above the highest id when the last pass began
  (`review_passes.assumption_mark`); `step_built` starts nothing. A pass with no accepted plan does nothing.
- **A5 · Checks and cap.** Any step of the process may carry a challenge, an added one too. Kept per pass: `min(3, 5 - open)`
  (SPEC: first three, none at five open; with three open this keeps two). A drop is recorded with a `reason`: `unknown_step`,
  `bad_title`, `bad_value`, `bad_question`, `no_proposal`, `source_not_fetched`, `number_unbacked`, `repeat`, `over_cap`,
  `too_many_open`. "Cites outside information" is decided by what the harness can see: a listed source that no lookup of this
  pass returned, a URL in the text that none returned, or the word Wikipedia with no source. A reasoned challenge with no
  source is kept. The number check reads the user message and the lookups' names and definitions.
- **A5 · Thread.** One first message by `reviewer`: the concern, then `Proposed: ...` (a question has no such line), with the
  challenge's `sources`. The thread's `after` and title follow `add_thread` and the challenge title. `contribute` adds review
  threads only if layer 4 has not drawn them (it does draw every thread, with `challenge` null) and then sets `challenge`;
  `review.running` is "the review lane is not idle". A5 reads the `challenges` table; layer 4's side assistant reads the
  challenge from the state document, so nothing in `needs_you/` was touched.
- **A5 · Use this.** `use_challenge` sets the challenge and thread `used`, then goes through the core's `say` with the step
  attached, so the message is the person's, visible, and routed as any message (analyst, or the step helper for a step that
  is not built). A correction of an assumption or an input is therefore only what the analyst does on that message; in the live
  run it asked the person for the missing figure. Refused: a `question` (answered in its thread; it can be dismissed), a
  settled challenge, an unknown id, a step no longer in the plan, and while the main lane waits on a decision (the message
  would answer it). `dismiss_challenge` has none of these but the first two. Replying is layer 4's `side` action.
- **A5 · Expectation.** `challenges {min?, max?, steps?}` counts the challenges raised in the conversation, whatever became of
  them; each of `steps` needs at least one.
- **A5 · Seen with the real model** (`claude` CLI, wedding example, all layers). Passes took 15.5, 20.9 and 15.9 s; one model call
  each and no lookup was asked for (the reviewer did not ask). Wikipedia is unreachable from this machine (proxy answers
  403), and the research chain then returns `not_found` for a term the reference file lacks, without an error. A second
  message sent while a pass ran was answered in 6 s.
- **C1 · The local layers default.** `config` reads `my/var/layers` when `HARNESS_LAYERS` is not set (section 7).
  `workshop at N` writes it; tests that check the default of 5 run in an empty folder.
- **A6 · Files and interfaces.** `replay.py`: `validate_scenario(value, *, stem, brief, layers=None)`, `load_scenarios(example_dir,
  only=None) -> (scenarios, skipped)`, `run_scenario(scenario, *, example_dir, keep=False, model_factory=None, write=print,
  timeout=900) -> {"scenario", "passed", "checks", "error", "seconds", "folder"}`, `expectations(layer)` (the `Expect`s of layers 0
  to `layer`), and the `replay EXAMPLE [SCENARIO] [--keep]` command (a base command in `__main__.py`). Output: a line per line
  played, then one `ok`/`FAIL` line per expectation (`what [seen]`), then `PASS`/`FAIL example/scenario (layer N) S s`; exit 0 only
  when nothing failed (skipped scenarios do not fail it). The example is copied to `my/var/replay/<example>-<scenario>-<random>/`
  (removed unless `--keep`); `HARNESS_DB`, `_BRIEF_DIR`, `_MODULES_DIR`, `_LAYERS` and `_REVIEW` are set there for the run and put
  back after. Replay records `replay.scenario` and `replay.checked` in the scratch database.
- **A6 · The scripted person.** A string is `say`. An object has `act` (and optionally `"settle": false`, to play it without waiting
  for the harness to finish the previous line: a side thread opened mid-answer). Acts: `say {text, step?}`, `build`, `confirm`
  (`confirm_assumptions` on the latest open notice), `correct {text}` (`say` with the latest notice attached, open or already
  confirmed: "Change it"), `choose {option}` (the decision the main lane waits on), `side {text, step?, reply?}` (`reply: true`
  goes into the latest side thread), `use {index?}` and `dismiss {index?}` (the index-th open review challenge, from 1; `use`
  counts only challenges, not questions). Each needs its layer (`build` 2, `confirm`/`correct`/`choose`/`side` 4, `use`/`dismiss`
  5). A kind `build` scenario plays `build` first. Replay settles before each line (and first of all, which adopts the modules and
  runs the first review pass of a `review` scenario), then at the end; a lane still working after 900 s, a job that failed
  (`state.error`) or a line the core refuses stops the scenario with that reason, and the checks are still made and listed.
- **A6 · Validation.** A scenario's expectation keys must be registered by layers up to the scenario's own, each value checked by
  its validator; `without` names calculation steps of the brief; `steps` and `decisions` name steps of the brief (or `added_N`);
  `today` only for `ask`. A scenario whose layer is above the layers present is skipped without validating its expectations.
  `read_brief` reads the example's brief as plain JSON, so replay names no layer.
- **A6 · Changed outside replay.** `Session(..., memory=)`: what `self.memory` starts with, so `today` is set before the `loaded`
  hooks (the review pass of a seeded plan starts there). Layer 4 `marks` also takes `confirmed` and `corrected` (at least that many
  `you.assumptions_*` events), layer 5 `challenges` takes `used` and `dismissed` (at least that many in that state), so a scenario
  can expect counts and states. Layer 3 `shown` and `not_shown` read the assistant's text and decision messages in the chat
  (they read `ask.reply` events only, so a figure in a decision's question was "not shown"), and, since the decision graph,
  the text of each harness message too, and with every message the text of its chips, so the figures of a join notice and the results a short reply leaves to its chips can be expected.
- **A6 · Prompt changed on replay evidence.** `needs_you/analyst.md`: one bullet says a value put into a run that the person did
  not give (a share they only called "shares", a rate, a date worked out, whether a payment counts toward a total) is an
  assumption to list in the run's `assumptions`. Before it, four of four live runs of `confirm_and_correct` gave the 50/50 split
  as a run input and "the 6,000 counts toward the total" in the prose only, with no notice; after it, three of three marked it.
- **A6 · Seen with the real model** (`claude` CLI, all layers). Whole-example runs take 6 to 7 minutes for wedding, about 2.5 for
  moving. The new-step build for "what share of the upfront cost is the deposit" worked in a side-thread scenario. The reviewer
  raised three challenges in the seeded wedding plan; `use` made the analyst answer, `dismiss` closed the next.
- **E2E · Fixes from the second browser run.** (1) `core/state.py` is the one place values are written for the eye:
  `show_number`, `show_scalar`, `show_value(value, output)` (the line; `key_value` picks an obvious key of an object or
  of a list's last row), `display`/`display_inputs` (the `Shown` of runs and examples, ARCHITECTURE 3.3) and
  `tidy_numbers` (a decision's longer decimals, after the number check). Layers 2 to 4 import them from the core.
  (2) `provenance.trace` takes a run as `("run", id, output, inputs)` and counts only what it produced
  (`_produced`: a single output; of an object or a list, the values not among its inputs; dates whole, never their parts); the first source of a label wins,
  and `answers.agent.trace_sources(..., turn_runs)` orders runs: this turn's newest first, then the others newest
  first. A later step that only repeats an earlier result no longer competes with it (its input holds the value).
  (3) The last answer is the latest turn-ending message with runs or with a figure leading to a step; its steps are
  those its turn ran and those its figures lead to. `state_shape` no longer wants the steps of the last answer to name
  one message. (4) Each step has `runs` (five). (5) `brief.describe_changes(old, new)`; `PLAN_REVISED` after a
  correction, `PLAN_CHANGED` after `revise_plan`. (6) `interviewer.md` names inputs and never asks for files or their
  form; `propose_spec`'s departures have kinds and `made_exact` is kept out of the plan check
  (`builder.read_departures`); `answers.layer.connect_added` gives an added step needs, pills and edges from its latest
  run; `you.module_requested` records `near` (`requests.asked_from`) and layer 4 sets it on added steps; layer 1's
  `loaded` posts `PREPARED` in example mode on an empty chat.
- **Live fixes · A call left in prose, an assumption left unlisted.** Seen in live replays at b729d6d:
  `decide_what_to_update` 8 of 12 (all four failures ended "Next I'll ask you what to update first": no question,
  no decision, nothing waited) and `confirm_and_correct` 11 of 12 (one run took the plan's 50% split as 0.5 with
  empty `assumptions`: no notice). Two layer 4 hooks inside the analyst turn (layer 3 calls them; `Turn.send_back`
  carries a refusal or a send-back). `reply_ready` sends a reply back once with `DECISION_SEND_BACK` when the
  person asked to decide (or attached a judgment step) and the turn ran modules but asked no decision; it never
  makes options, and a second prose reply is shown. The reply up to its question is posted before the decision,
  so the results are not lost (a first version without this lost the figures in 3 of 12). It does not look at a
  turn where the person did not ask: in a first version that also fired on any question with "or" after runs, the
  model turned "do you want me to use 150, or also run 200?" and "do you want to see it if the contribution comes
  later?" into decisions (one false stop in 12 `confirm_and_correct` runs, one in 4 `cover_each_payment` runs
  at layer 4). `run_ready` refuses the first run of a turn that has an
  input value the person did not give and the run does not list, and adds `AUTO_ASSUMED` sentences on later runs of
  the turn, so a run on such a value always carries a mark. The plan's `proposed` items do not count as the
  person's (they still pass the number check). After: `decide_what_to_update` 12 of 12 (fired once, obeyed),
  `confirm_and_correct` 12 of 12 (refused 4 times, each time listed on the next call), `cover_each_payment` 4 of 4
  at layer 3 and 4 of 4 at layer 4 (nothing fired). What stays unchecked: text and true/false inputs (whether a
  payment counts toward a total), whole numbers up to 12, a value of the person's put into the wrong input, and a
  call left in prose when the person did not ask to decide.
- **DG · The rule reversed.** "A side thread never changes anything" (SPEC 6.4 before, the design's section 4) no
  longer holds: a branch's assistant may propose, and a proposal the person accepts joins the trunk (section 12).
  The side assistant still applies nothing; the harness applies, with the person's yes.
- **DG · One table per thing.** A branch is a `threads` row (five columns more, layer 0), a node a `trunk` row (layer
  0), a proposal a `proposals` row (layer 4). No `branches` table; `decisions` keeps its meaning (the person's calls).
  `status` on threads stays for the current page; `outcome` is the branch's.
- **DG · The re-run is the harness's, not the model's.** The join re-runs the last answer's runs that the value reaches,
  by value lineage, through the gate, with no model call (12.4). Reasons: it is deterministic for the demo, fast, and a
  number the person sees still comes only from a tested module. The analyst is told afterwards in a `[harness]` line.
- **DG · Chips from records.** Chips are built at `state()` from `_runs` and `calc_runs`, not asked of the model; the
  analyst's prompt only says to keep the prose short (12.7).
- **DG · Death is stored.** A branch dies by an action or a hook and records `you.branch_dead`; nothing is derived at
  display time, so a replay can check it and the page draws what it gets.
- **DG · Events kept.** `you.side_opened` keeps its name and gains `subject`; existing tests of event kinds hold.
- **D0 · Checks in the core.** `decide` refuses a `who` or `kind` outside 3.5 and a `branch` that is not a thread of the
  conversation (ValueError); `text` is whitespace-folded and cut to 80 characters ending in `…`; `touched` always has both lists.
  `set_outcome` takes only `open` or `dead` (`joined` only through `decide`). `plan_state.start(..., trunk=)` puts `history` in
  the document, `finish` sets `changed_by` (None when no node), and a `finish` on a bare dict without `history` is fine.
- **D0 · The validator.** `tests/layer0/state_shape.py` requires `history`, `changed_by`, and the branch keys on threads at
  every layer; `chips` and `proposal` are checked when present and required only once `CHIPS_REQUIRED`/`PROPOSAL_REQUIRED` at
  its top are set True (do that when D3a and D4a land). The five older sample states gained the new core keys.
- **D3b · Re-run details.** `rerun` returns `replaced` and `failed[].run` as `"r<id>"` (the `value` Change's form) and
  `runs` as ints (the `_runs` form); failed runs stay in `runs`. `impact` takes an optional `conversation` (default: the
  current one from `meta`; the state has none). A value one leaf of a re-run kept and another changed is ambiguous, as one
  mapped to two values. "Needed its output" is "holds a value it produced" (`_produced`). Only re-run outputs map; the
  changed input itself maps nowhere but its own top-level key. `RERUN_EXPECTED` lives in `answers/rerun.py` (layer 4 imports it).
- **D3a · Chips.** Built in `answers/layer.py` (`add_chips`, `run_chips`): every main-chat message gets `chips`, `[]` without
  runs. A value chip's subject `value` and a result chip's are the input or output as written (text as is, a list or object
  as JSON); a "produced" value is one whose every number and date an earlier run of the same message produced; no step for
  the run: no result chip, `step` null on its value chips. `tell_analyst` adds to the note that goes with the next message
  (as `WITHHELD_NOTE` does, after the person's words); `store_input` writes only, `save_input` keeps its event.
- **D1 · Nodes of layer 1.** `plan_accepted` is recorded in `_run` after `PLAN_ACCEPTED` is posted and before the `plan_accepted` hook (so a
  node follows that message); `loaded` records it for a confirmed plan with an empty trunk and no interview, after `PREPARED`. `revise_plan`
  gains `branch=None`, returns `{"changed", "node"}`, and records `plan_revised` (text `Plan changed: {changes}`, touched steps `changed`)
  after `PLAN_CHANGED`; a revision that errors records nothing. Every layer 2 and later session on a saved plan therefore starts with `n1`.
- **D4b · Nodes of layer 4.** `call` is recorded in `ask_decision` right after the answer is stored, so `choose` and words both record it
  (text `{question} {words}`, `words` being the option's text for `choose`). `assumption_confirmed` and `assumption_corrected` use the
  notice's steps and all the notice's (resp. corrected) assumptions; text `Confirmed: `/`Corrected: ` + first sentence (+ ` and n more`),
  kept within 80 characters by `marks.node_text`. `built` is recorded when `request_module` ends `built` or `reused` (`why` is the case).
- **D5 · Review branches.** `open_thread` passes `origin="reviewer"` and subject `{"kind": "step", "step"}`. `use_challenge` records
  `challenge_used` (after settling the challenge, before the "use this" message) with `branch` the thread; `dismiss_challenge` calls
  `set_outcome(thread, "dead")`. A question branch stays `open` until dismissed.
- **D4a · Branches and joins.** In `needs_you/join.py` (proposals, checks, the three actions, the join, deaths) and `side.py`
  (subject, sections, the tool). A `value` proposal's `input` may also be the branch subject's own key (a value chip of an
  older answer, a plan input's pill); a leading `in:` is dropped; a bad `kind` is refused `unknown_input`. The new value's
  numbers are checked strictly (small whole numbers too; dates whole). Proposal text `{label}: {from or none} → {to}`, or
  `Plan[, step N Name]: {words}` cut to 80; the node's text is SPEC 6.6's `{label}: {new} (was {old})`. The join notice is a
  `harness` message of kind `text` with `figures: []`; a failed run with no step gets `step` "" in the node's `failed`. A value
  join that raises makes the proposal `failed` (reason posted in the branch) and still sets `error`. The `turn_finished` hook
  is marks' then the `moved_on` death. A join notice first had every value chip of its new runs (13 in a live
  wedding run); after the first browser run it keeps the changed value and the results, each `new (was old)` (12.7).
  `review_challenges.json` gained `"proposal": null`; `workshop/manifest.json` lists `join.py`.
- **D6 · Replay acts and scenarios.** The scenarios are `branch_that_joins` and `branch_that_dies` (SPEC 6.6 gives them; the question is one the real
  model answers reliably, and `today` is 2026-10-12). `branch` takes a `chip` or a
  `step`, not both. "Newest" is the highest number in the id (a review pass on load makes thread ids unpredictable), `accept` and
  `decline` look at every thread's pending proposal, `close` at open side branches (origin any, kind `side`). The terminal's `/yes`, `/no`,
  `/close` pick the same way, and it prints a pending proposal once with `Type /yes to decide it, or /no.`.

## 12. Decision history

The scope is deliberately small: two examples must be right (12.10);
everything else may stay as it is, as long as it does not look broken beside
them.

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
- The main chat stays as it is: the person asks, the analyst answers. A value
  given or changed in the main chat is conversation, not a node; it becomes a
  decision when the person challenges its chip and accepts the proposal, or
  uses one of their own buttons (choose, confirm, "Change it", "use this").

### 12.2 What exists, and what it becomes

| Today | Becomes | Layer |
| --- | --- | --- |
| The plan accepted (`accept_plan`; a confirmed plan found on load with an empty trunk, as a seeded example) | The first node, `plan_accepted`, who `you` | 1 |
| A plan revision after acceptance (`revise_plan`, from `change_plan` or from a plan proposal) | Node `plan_revised`, who `you` (`reviewer` when `by` is the reviewer); `branch` set when it came from a proposal | 1 |
| A side thread (`threads` kind `side`) | A branch, origin `you`, subject from `side` (default `{"kind": "step"}` or `{"kind": "plan"}`) | 4 |
| A side reply | Talk in the branch. The side assistant may now **propose** a change through `propose_change` (12.3); it still applies nothing | 4 |
| A review thread and its challenge (`challenges` row) | A branch, origin `reviewer`, subject `{"kind": "step"}`. "Use this" records node `challenge_used` (who `reviewer`) and joins it; the analyst then acts on the person's message as today, and what it changes records its own node. "Dismiss" makes it dead | 5 |
| A notice under an answer (`notice`, `assumptions` rows) | Stays a notice. Its assumptions are also assumption chips. "Confirm" records `assumption_confirmed`; "Change it" records `assumption_corrected` and the analyst runs again, as today | 4 |
| A chip's correction of an assumption | A branch on `{"kind": "assumption"}`; its proposal is a `value` of that run; the join also marks the assumption `corrected` with the words | 4 |
| A call answered (`decisions` row, `answered`) | Node `call`, who `you`, touched: the decision's step | 4 |
| A build the analyst asked for (`request_module`) | Node `built`, who `assistant`, `why` its case, no branch | 4 |
| A rebuild by the harness itself (module files changed and adopted again on load; a helper rebuild; a step built again after it went stale) | A branch of kind `harness`, origin `harness`, subject the step, holding the harness's lines; joined at once as node `built`, who `harness`. Open while the step is not built. Not built: no layer records it yet (SPEC 4.9) | 2 |
| The unattended build (`build`) | Node `built`, who `harness`, `why` `build`, all its steps, no branch. Not built: no layer records it yet (SPEC 4.9) | 2 |
| Stale propagation | Unchanged: a plan revision makes changed steps stale, as today | 2 |
| Every event | Unchanged; `core.decided` and the `you.` kinds of section 6 are added | all |

No parallel table: a branch is a `threads` row with five more columns, a node
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
   note is today).

For a **plan** proposal the job calls `revise_plan(work, words, step,
by="person", branch=thread)`; `revise_plan` records `plan_revised` with that
branch, which joins it. An error makes the proposal `failed` with the reason,
posted in the branch as a `harness` line; the branch stays open. Changed steps
go stale as today; nothing runs again.

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

The database is disposable: after pulling this, delete `my/var/harness.db`
and `my/var/examples/`.

```sql
-- harness/schema.sql (layer 0): threads gains five columns, and a new table
CREATE TABLE IF NOT EXISTS threads (
    ...as today...,
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

Message `data` gains private keys: `_chip_runs` and `_node` (a join notice).

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

