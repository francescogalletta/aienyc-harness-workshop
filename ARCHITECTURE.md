# Architecture: Financial Advisor Harness, version 2

This file says how version 2 is built: the core, the plan state document, the
layers and what each owns, the actions, how long work is reported, what is
removed, how "the harness at step N" is produced, and the work plan.
`SPEC.md` is the contract for behaviour; it relies on sections 3 to 5 here,
which are part of the contract too. The product design is in `design/`
(`design/ui-design-decisions.md` and `design/system/`). Where this file and the
design differ, the design wins; tell the maintainer.

## 1. In ten lines

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
9. Kept and adapted: values, safety, runner, registry, gate, number check,
   research desk, model adapters, builder phases and their prompts.
10. Removed: account files, verifier, findings, evidence page, the two pages,
    the assumption gate, pass-back from side conversations, workshop snapshots.

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
  "threads": [Thread, ...],               (layer 4 and 5) side and reviewer threads
  "review": {"open": int, "running": bool}   (layer 5)
}

Lane     = "idle" | "working" | "waiting"
Activity = {"lane": "main" | "side" | "review", "what": "interview" | "build" | "answer"
            | "helper" | "tests" | "side" | "review", "step": "<step id>" | null,
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
         "value": null | str}         (layer 3) its saved value as written; null: none saved yet
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

  "build": null | Build,          (layer 2) calculation steps only
  "last_run": null | LastRun,     (layer 3)
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
  "disagreement": [{"n": 2, "expected": json, "code_gives": json | "an error"}],
  "code": null | {"module_py": str, "tests_py": str},
  "tested_at": null | ISO time    the latest test run of this module
}
Example = {"n": 1, "inputs": {...}, "expected": json, "working": str,
           "checked_by": "second_pass" | "you" | null,      null: left out, the passes disagreed
           "second_pass": null | json}                       the checker's answer when it differed
LastRun = {"run": "r17", "message": "m12" | null,   the reply it fed, if any
           "in_last_answer": bool, "inputs": {...}, "output": json,
           "assumptions": [str], "ts": ISO time, "test_run": int}
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
  "notice": null | Notice         (layer 4) set on the assistant reply it belongs to
}
Figure   = {"start": 13, "end": 19, "text": "43,000",
            "step": "s1" | null, "run": "r17" | null, "input": "in:guest_count" | null}
Decision = {"id": "d4", "step": "s7", "question": str, "options": [str], "suggested": 2 | null,
            "why": str, "status": "open" | "answered", "choice": null | "2" | "something else"}
Notice   = {"assumptions": [Assumption], "steps": ["s5"], "status": "open" | "confirmed" | "changed"}
Thread   = {"id": "t3", "kind": "side" | "review", "step": "s5" | null, "title": str (≤45 chars),
            "after": "m12" | null,    the main-chat message it follows: drawn right after it; the core
                                      sets it to the last main message when the thread starts
            "status": "open" | "used" | "dismissed",
            "messages": [{"who": "you" | "assistant" | "reviewer", "text": str,
                          "sources": [{"title", "url"}]}],
            "challenge": null | Challenge}
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
gets that run's id and the step the run's module carries out. A figure from a
saved input gets the input id when the input's name matches a brief input id,
else none. Every other figure (the person's words, the brief, today, a small
number) gets neither and is shown as plain text. `start` and `end` are
character offsets in `text`. Only figures with a `step` are drawn as
`fah-num` and select their step when clicked. A decision message is the same:
its `text` is the decision's `question`, and its `figures` index that text.

### 3.5 A small example

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
            "line": {"text": "→ 43,000.00 ◌", "kind": "result"},
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
                      "steps": ["s1"], "status": "open"}}],
 "threads": []}
```

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
  `step_built(work, step_id)`, `turn_finished(work, turn)`. A hook may queue
  jobs; it never waits on the person.
- **Commands** are added to `python -m harness`. **Expects** are added to the
  scenario validator and checker (SPEC 2.6).

What a layer must not do: import a higher layer, write to another layer's
tables, or read `config.layers` itself. The core is the only place that knows
which layers are on.

## 5. Actions

`POST /api/act` with `{"action": name, ...payload}`. 200 `{"ok": true,
"version": n}` when applied; 409 `{"ok": false, "error": reason}` when not
now; 400 for a bad body or an unknown action. The page fetches the state after
every action.

| Action | Payload | Layer | Allowed when | Effect |
| --- | --- | --- | --- | --- |
| `say` | `text`, `step`?, `notice`? | 0 | always | A person message in the main chat; answers `waiting`, or is routed (SPEC 2.3) |
| `start` | `text` | 1 | `phase` is `empty` | Starts the interview with the opening statement |
| `accept_plan` | | 1 | `waiting.kind` is `plan` | Saves the brief as confirmed; hook `plan_accepted` |
| `wrap` | | 1 | the interview waits for an answer | Asks the interviewer to propose the plan now |
| `build` | | 2 | `phase` is `accepted`, no build queued or running | Queues the unattended build |
| `confirm_example` | `step`, `n` | 2 | that example exists and is not yours already | Records "confirmed by you" |
| `confirm_plan_check` | `step` | 2 | the step has departures not yet confirmed | Clears the plan-check mark |
| `run_tests` | `step` | 2 | the step has a registered module | Queues a test run |
| `choose` | `decision`, `option` | 4 | that decision is the one waiting | Posts the option's text as the person's message (`who` "you", the decision's step), then answers the decision with the option number |
| `confirm_assumptions` | `message` | 4 | that message's notice is open | Confirms its assumptions |
| `side` | `text`, `step`?, `thread`? | 4 | always | Starts a side thread, or replies in one (side or review) |
| `use_challenge` | `challenge` | 5 | the challenge is open | Marks it used; posts the person's "use this" message and routes it |
| `dismiss_challenge` | `challenge` | 5 | the challenge is open | Marks it dismissed |

"Change it" under a notice is the page putting the notice's steps in the
composer; the message then goes as `say` with `notice` set. The Review toggle,
pop-ups, "Whole plan" and selection are page-only.

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

## 7. "The harness at step N"

- **One setting.** `HARNESS_LAYERS=N` (default 5) turns layers above N off.
  The facilitator presents step N on the finished tree with
  `HARNESS_LAYERS=N uv run python -m harness ui`.
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
  of layers 2 to 5); it does not import them. The page is one given file for
  every step, not built step by step. The analyst prompt is composed of parts,
  so a later part must only add, never contradict an earlier one; the layer 4
  part says plainly what it changes. These are the fallbacks, and they are
  enough for the four uses.

## 8. What is removed

Delete, with their tests, rather than leave dormant:

- `harness/sources/` (account files, summaries), `harness/calc/findings.py`,
  `verifier.py`, `verifier.md`, and every `data` command, scenario key and
  table.
- `harness/ui/evidence.py`, `evidence.html`, `grounding.html`, `session.py`;
  the `work` and `decisions` commands. Their content moves into step pop-ups.
- `harness/migrations/` (replaced by one `schema.sql` per layer).
- The assumption gate, `GATE_*` texts, `ask.gate`; the build-request question
  (`REQUEST_QUESTION`); the plan check question to the person; the person's
  check of every example in the terminal; the `adopt` and `modules` commands
  (adoption is automatic, SPEC 4.6).
- `harness/calc/aside.py`, `aside.md`, `/aside`, `/back`, the pass-back
  question.
- `harness/calc/agent.py`, `analyst.md`, `decisions.py`, `example_helper.md`
  (replaced by `answers/`, `needs_you/`, `step_helper.md`).
- `examples/wedding/data/`, the scenarios `check_my_figures`,
  `pay_agrees_with_files`, `spending_vs_brief`; `tests/fixtures/accounts/`,
  `tests/data/`, `tests/step0` to `tests/step5`.
- `workshop/states/`, the snapshot parts of `workshop/states.py` and
  `DESIGN.md` sections 5, 6, 10 and 11.

**Database.** Start a fresh schema. The database is local and disposable: one
`schema.sql` per layer, `CREATE TABLE IF NOT EXISTS`, applied on every connect
for the enabled layers. No migration history, no `schema_migrations`. After a
schema change, delete `my/var/harness.db`; README says so.

## 9. Work plan

Each package is sized for one agent. "Reads" always includes `SPEC.md`, this
file and `AGENTS.md`; the page package also reads `design/`. Every package
leaves `uv run pytest -q` passing and adds no test that breaks the rule in
section 7. A package that changes behaviour gets a second agent that writes
its tests from the contract (AGENTS.md); the tests agent may start once the
contract is final, in parallel with the code agent.

### Phase A: behaviour, no new page

| Id | What | Writes | Model | Depends on | Parallel with |
| --- | --- | --- | --- | --- | --- |
| A0 | Core, lanes, waiting slot, layer discovery, per-layer schema, `db.py`, `config.py` (`HARNESS_LAYERS`, `HARNESS_REVIEW`), server with `/api/state` and `/api/act` and a placeholder page, terminal driver, `__main__.py` by discovery, `core/state.py` with the step-line rule. Deletes everything in section 8 except what A1 to A4 replace. ~50 tests in `tests/layer0` | `harness/` base files, `tests/layer0/` | **Opus** | none | B1 |
| A1 | Layer 1: brief v2 (origins, step links, validation), interview on the core, corrections with a step, `revise.py`, `contribute`, `ground`. ~55 tests | `harness/grounding/`, `tests/layer1/` | Sonnet | A0 | A1d, B1 |
| A1d | Example briefs to v2: origins, step links, `checked_by` in every `golden.json`, scenarios tagged with `layer` (contents left to A6) | `examples/` | Sonnet | contract only | A0, A1 |
| A2a | Layer 2 build engine: unattended builder, second-pass checker, `build_steps`, staleness, automatic adoption, `gate`/`registry` changes. ~70 tests | `harness/calc/` engine files | **Opus** | A1 | B1 |
| A2b | Layer 2 surface: step helper chat, actions, `contribute`, `build` command. ~40 tests | `harness/calc/helper.py`, `layer.py`, `tests/layer2/` | Sonnet | A2a | A3 |
| A3 | Layer 3: analyst on the core, tools `run_module`, `save_input`, `change_plan`, figures, last runs, `ask`. ~60 tests | `harness/answers/`, `tests/layer3/` | Sonnet | A2a | A2b |
| A4a | Layer 4: marks (run-and-mark), calls (`ask_decision` via the waiting slot), automatic module requests, prompt part. ~45 tests | `harness/needs_you/` but `side.py` | Sonnet | A3 | A5 |
| A4b | Layer 4: side threads everywhere. ~25 tests | `harness/needs_you/side.py`, its registration | Sonnet | A4a | A5 |
| A5 | Layer 5: reviewer, challenges, use and dismiss, triggers. ~40 tests | `harness/review/`, `tests/layer5/` | Sonnet | A4a | A4b |
| A6 | Replay on the core, expectation keys by layer, scenarios of both examples rewritten, `examples/README.md`; run `replay wedding` and `replay moving` against the real model and report | `harness/replay.py`, `examples/*/scenarios/`, `tests/layer0` replay tests | Sonnet | A5, A4b | B2 |
| A7 | `README.md`, `AGENTS.md` for version 2 | root docs | Sonnet | A6 | C1 |

### Phase B: the screen

| Id | What | Writes | Model | Depends on | Parallel with |
| --- | --- | --- | --- | --- | --- |
| B1 | The single page: diagram and chat, pop-ups, Review view, composer with step chip and "On the side", decisions, notices, polling; design system inlined, no web font, no network. Works from sample state documents it writes under `tests/layer0/states/` | `harness/ui/page.html`, sample states | **Opus** | this file (section 3) | all of Phase A |
| B2 | Serve the page; tests that the page is self-contained (no `http` URL, no external load), carries the token, and renders each sample state without a script error (a static check of the bundle's presence and IDs, no browser) | `harness/ui/server.py`, `tests/layer0/` | Sonnet | A0, B1 | A6 |

### Phase C: the workshop

| Id | What | Writes | Model | Depends on | Parallel with |
| --- | --- | --- | --- | --- | --- |
| C1 | Workshop machinery by layer: manifest lists each layer's built and given files; `start`, `next`, `finish` remove or restore files; `check` runs each step's tests on the finished tree minus later layers; delete `states/`; rewrite `DESIGN.md` | `workshop/` code and `DESIGN.md` | Sonnet | A6 | A7 |
| C2 | Guides, facilitator notes, one build prompt per layer | `workshop/*.md`, `workshop/prompts/` | Sonnet | C1 | none |

Order: A0 → A1 → A2a → (A2b ‖ A3) → A4a → (A4b ‖ A5) → A6 → (A7 ‖ C1) → C2.
B1 runs beside all of Phase A; B2 after A0 and B1. Test budget: about 390 in
all, under one minute.

## 10. Questions for the maintainer

Each has the default the work plan takes.

1. **Changing the plan after it is accepted.** The design shows corrections
   before acceptance only. Default: after acceptance the person can still
   change it in their own words; the analyst calls `change_plan`, the plan is
   revised and saved as accepted (their words are the consent), and changed
   steps go stale.
2. **Figures the person gave.** "A number no step produced is never shown"
   could forbid echoing the person's own figures. Default: the number check is
   unchanged (the person's words, saved inputs, the brief and today are
   sources); only figures a step produced are underlined and lead to a step.
3. **Reviewer research.** Default: the research desk's chain (saved reference
   file, then Wikipedia's top search hit, one request, no model), with only a
   general question of at most 100 characters and no digits. Offline
   (`HARNESS_RESEARCHER=reference`) the reviewer still runs but cites no
   outside source. `claude_code` gives better answers where available.
4. **What attendees build at step 0.** Default: `config.py`, `db.py` and
   `model/` as today; the core, server, page, terminal and replay are given.
5. **Starting the build.** Default: the person presses Build after accepting;
   accepting does not start it.
6. **The chat across restarts.** Default: one conversation per plan, kept in
   the database and shown again; the analyst starts each process with a fresh
   context (the system prompt holds saved inputs, decisions and last runs).
7. **The Kitchen components.** Default: not used; their licence is unstated and
   they are React.
8. **Commands dropped.** Default: `adopt`, `modules`, `work`, `decisions`,
   `data` go; `check`, `events`, `ground`, `ui`, `build`, `ask`, `replay` stay.

## 11. Decisions made while building

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
  differs from the record's, `its files changed` when the module's files changed or are gone), else `built`.
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
- **A3 · Figures.** For `trace`, only a run's result is labelled `run` (a run's inputs back a number but never
  lead to the step), and runs are given newest first so that of several runs showing the same number (a later step
  repeats what an earlier one produced) the earliest is the source. A `run` figure carries the run's id and its
  module's own step (`spec.step_id`), or no step when the plan no longer has it. `run` wins over `input`, `input`
  over the person's words, as `trace` orders them; so a number the person gave that a step's result happens to
  repeat leads to that step. A figure from a saved input gets `input` only when the name is a brief input id
  without `in:` (the model is told to use the plan's names). Only assistant replies carry `figures`.
- **A3 · Runs and the last answer.** A turn's reply (or withheld or stop notice) keeps the turn's run ids in its
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
  checks layer 3 (assistant messages carry `figures`, figures name known inputs, `last_run.message` is in the chat, the
  steps of the last answer share one message, `used` agrees with them).
