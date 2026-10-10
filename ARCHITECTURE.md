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
         "used": bool}                (layer 3) it took part in the last answer
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
  "figures": [Figure],            (layer 3) assistant messages
  "decision": null | Decision,    kind "decision" (layer 4)
  "notice": null | Notice         (layer 4) set on the assistant reply it belongs to
}
Figure   = {"start": 13, "end": 19, "text": "43,000",
            "step": "s1" | null, "run": "r17" | null, "input": "in:guest_count" | null}
Decision = {"id": "d4", "step": "s7", "question": str, "options": [str], "suggested": 2 | null,
            "why": str, "status": "open" | "answered", "choice": null | "2" | "something else"}
Notice   = {"assumptions": [Assumption], "steps": ["s5"], "status": "open" | "confirmed" | "changed"}
Thread   = {"id": "t3", "kind": "side" | "review", "step": "s5" | null, "title": str (≤45 chars),
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
`fah-num` and select their step when clicked.

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
            "origin": {"kind": "proposed"}, "steps": ["s1"], "used": true}},
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
| `choose` | `decision`, `option` | 4 | that decision is the one waiting | Answers it with an option number |
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
