# Contract: Financial Advisor Harness

This is the contract. `ARCHITECTURE.md` sections 3 (the plan state document),
4 (the core and its extension points) and 5 (actions) are part of it. The
product design is in `design/`. Change the contract first, then the tests,
then the code.

The contract states behaviour and interfaces. Fixed strings live in the code;
tests assert behaviour, event kinds and payload keys, not wording. The few
templates a person reads, and which tests may check, are written out here.

Sections follow the layers. A layer's section holds only what that layer adds.

## 1. Ground rules

1. **A number reaches the person only from tested code**, or from their own
   words, a saved input, the brief or today's date. The number check
   (`provenance.unbacked`) reads everything the models send to the person and
   every value they pass to code or save. A second unbacked reply is withheld.
2. **Every calculation runs through the gate**, which runs the module's tests
   first, every time.
3. **The code writer never sees the worked examples.** The second-pass checker
   never sees the example writer's answers or working.
4. **Nothing personal leaves the machine.** A web lookup sends a short general
   query and nothing else. The researcher that reads web pages holds no data of
   the person's. Text that comes back is data, not instructions.
5. **Everything that matters is in the local database**: every message, model
   reply, lookup, build phase, test run, run, decision, assumption, thread and
   challenge. The event log is append-only.
6. **Nothing blocks unless the call is the person's.** Builds run unattended.
   Assumptions run and are marked. Only a decision (`ask_decision`) and the plan
   awaiting acceptance wait for the person. A change proposed on a branch waits
   for the person's yes and blocks nothing.
12. **Decisions are recorded.** Every decision that changes the analysis is a
    trunk node (ARCHITECTURE.md section 12), recorded by the layer that made
    it. Nothing changes a figure of the person's or the plan's shape without
    their yes; the harness's own rebuilds join by themselves.
7. **Provider-agnostic.** Only `harness/model/` imports a provider SDK.
8. **Standard library only** for the harness. The page is one self-contained
   HTML file: the design system's three files inlined, no web font, no network.
9. **Nothing under `harness/` names an example domain.**
10. **The harness writes only under `my/`** with its default settings, and
    never uses `workshop/`. Deleting `workshop/` leaves a harness whose tests
    pass.
11. **Layers.** Layer N imports only layers below N. A test of layer K sets
    `HARNESS_LAYERS=K` and asserts nothing about later layers
    (ARCHITECTURE.md section 7).

## 2. Layer 0: the base

### 2.1 Settings: `harness/config.py`

`load_config()` reads the environment on every call; an empty variable is
unset.

| Variable | Default | Field |
| --- | --- | --- |
| `HARNESS_DB` | `my/var/harness.db` | `db_path` |
| `HARNESS_MODEL_PROVIDER` | `auto` | `model_provider` |
| `HARNESS_MODEL` | `claude-sonnet-5-5` | `model_name` |
| `HARNESS_SCRIPT` | none | `script_path` |
| `HARNESS_RESEARCHER` | `auto` | `researcher` |
| `HARNESS_REFERENCE` | `reference/terms.json` | `reference_path` |
| `HARNESS_BRIEF_DIR` | `my/brief` | `brief_dir` |
| `HARNESS_MODULES_DIR` | `my/modules` | `modules_dir` |
| `HARNESS_EXAMPLE` | none | `example` |
| `HARNESS_LAYERS` | `5` | `layers`: an int 0 to 5; anything else is an error naming the variable |
| `HARNESS_REVIEW` | `auto` | `review`: `auto` or `off` (off: no automatic review passes) |

Example mode is kept as it is: with `HARNESS_EXAMPLE=<name>` the database,
brief and modules default to a copy under `my/var/examples/<name>/`, made once
by `main()`.

### 2.2 Model and database

- `harness/model/` is kept unchanged: `Model.complete(system, messages,
  tools)`, `ToolSpec`, `ToolCall`, `ModelResponse`, the providers `scripted`,
  `anthropic`, `claude_code`, `auto`.
- `db.connect(path=None)` opens SQLite with WAL, `busy_timeout` 5000 ms and
  foreign keys, creating the folder. `db.apply_schemas(conn, layers)` runs the
  `schema.sql` of `harness/` and of each enabled layer. `record_event(conn, *,
  session_id, kind, actor, payload)` and `list_events` are kept.
- `harness/schema.sql`: `events` (append-only, with its two triggers), `meta
  (key PRIMARY KEY, value)`, `messages (id, ts, conversation, thread NULL, who,
  text, step NULL, kind, data JSON)`, `threads (id, ts, conversation, kind,
  step NULL, after NULL, title, status, origin, subject JSON, from_node NULL,
  outcome, node NULL)`, `trunk (id, ts, conversation, who, kind, text, change
  JSON, touched JSON, thread NULL, after NULL)` (ARCHITECTURE.md 12.8).
- There is no migration history (ARCHITECTURE.md section 8).

### 2.3 The core

`Session`, the lanes, `Work`, the waiting slot, discovery and `Layer` are as
in ARCHITECTURE.md section 4. Rules the code must keep:

- **Conversation.** `meta.conversation` holds the current conversation id.
  Layer 1 starts a new one when an interview starts. `chat` and `threads` in
  the state show the current conversation.
- **A person's message** (`say`): stored at once as a `you` message (with
  `queued: true` when the main lane is busy). Then, in order:
  1. if a main-lane job waits, the message answers it (`{"text", "step",
     "notice"}`);
  2. else the highest enabled layer whose `route` returns a handler gets it,
     as a main-lane job;
  3. else the harness posts `NO_ROUTE`, or `NO_ROUTE_PLAN` once a plan is accepted.
- A job that raises is caught: `error` is set to one line, the event
  `core.job_failed` is recorded, the lane goes on with its next job.
- **The decision history** (ARCHITECTURE.md 4.4). `decide(...)` stores a trunk
  node of the current conversation with `after` the last main-chat message,
  records `core.decided {node, kind, who, branch, touched}`, and, with
  `branch`, sets that thread's `outcome` to `joined` and its `node`. `who` is
  one of `you`, `assistant`, `harness`, `reviewer`; `text` is cut to 80
  characters. `add_thread` stores `origin`, `subject` and `from_node` (the
  newest node, or NULL). `history` is in the state at every layer;
  `changed_by` on a step or an input is the newest node whose `touched` names
  it.
- **Templates** (posted by the harness):

```
NO_ROUTE = "Nothing here can answer that yet."
NO_ROUTE_PLAN = NO_ROUTE + " At this step the plan can be read, but not changed or questioned. Asking about it arrives at step 3."
WITHHELD = "(The answer was held back, because it held numbers that no tested module produced: {numbers}.)"
TOO_MANY = "(The harness stopped working on this, because it took too many steps. Try asking in a simpler way.)"
```

### 2.4 The step line and marks: `harness/core/state.py`

After every layer has contributed, for each step, the first rule that applies
gives `line`:

1. `needs_you`: `Needs you · your call` (open decision) or `Needs you · not
   built`; kind `strong`.
2. `build.status` is `building`: `Building`; kind null.
3. `last_run.in_last_answer`: `→ ` and the output, then ` ◌` when `unconfirmed`
   is not empty; kind `result`. A number is shown as below; a date as given;
   text cut to 18 characters; a list or an object as its key value with the
   key's name (`shortfall 5,600`, `last balance 29,400` for a list of rows)
   when one is obvious (the only numeric key the step's output description
   names, else the only numeric key), else `{n} values`.
4. `build.status` is `built`: `{examples} examples · {passing}/{tests}`; kind
   `tested` when every test and example passes, else null.
5. `build.status` is `stale`: `Stale · rebuild`; `not_built`: `Not built`;
   kind null.
6. `calls.records` is not empty: `Decided`; kind null.
7. Otherwise `line` is null.

**How values are shown** (`core/state.py`, the one place): modules compute
exactly; what the harness shows on a step's line, in a pop-up's runs and
examples, and in a decision is written with thousands separators and at most
two decimals, the trailing zeros of a whole amount dropped (`1,888.89`,
`43,000`); a value below 1 keeps up to four decimals (`0.3095`). A whole
number under a key naming a year has no separators. Runs and examples in the
state carry `shown` (ARCHITECTURE.md 3.3): each value as text, an object as
rows of name and value, a list of rows as a small table. A decision's
question, options and reason have every longer decimal rewritten this way
after the number check. Formatting is presentation, never a source of
numbers: the exact values stay in the record and in the state.

`marks`, in this order, each only when it applies: `●` with the number of open
questions; `plan check` when departures are not confirmed; `▲` with the number
of open challenges; `◌` when `unconfirmed` is not empty.

### 2.5 The terminal: `harness/terminal.py`

A thin driver on a `Session`. It prints each new chat message once (`you:`,
`assistant:`, `harness:`), a decision with its options numbered, a notice
followed by `Type /confirm, or say what is different.`, and thread messages
indented with `  side | ` or `  review | `. It prints `activity` text when it
changes. It reads a line when the main lane waits or is idle:

| Typed | Action |
| --- | --- |
| `/accept` | `accept_plan` |
| `/wrap` | `wrap` |
| `/build` | `build` |
| `/confirm` | `confirm_assumptions` on the latest open notice |
| `/side TEXT` | `side` with a new thread (`/side @STEP TEXT`: about that step) |
| `/reply TEXT` | `side` in the latest side thread (`/side tN TEXT`: in thread tN) |
| `/yes`, `/no` | `accept_proposal`, `decline_proposal` on the newest pending proposal |
| `/close` | `close_branch` on the newest open side branch |
| `/quit`, end of input | stop the driver |
| anything else | `say` (a decision reads a number or an option's words) |

Commands: `ground` (stops once the plan is accepted; exit 0 then, 1 if
stopped before), `build` (runs `build`, settles, prints one line per
calculation step, exit 0 when all are built), `ask [QUESTION]` (sends the
question if given, then reads lines until `/quit`). `check`, `events`, `ui`
and `replay` are kept. `ui` serves the page with a `Session`.

### 2.6 Replay: `harness/replay.py`

A scenario is `examples/<name>/scenarios/<stem>.json`:

```
{"name": stem, "layer": 1..5, "kind": "ask" | "build", "description": str,
 "today": "YYYY-MM-DD" (ask only), "without": [calculation step ids], "review": bool (default false),
 "lines": [str | {"act": verb, ...payload, "settle": false?}],     may be empty for build
 "expect": {key: value}}
```

A string line is said to the main chat. An object is an action of the scripted person: `say {text, step?}`, `build`,
`confirm` (the latest open notice), `correct {text}` (the latest notice: "Change it"), `choose {option}` (the decision
the main lane waits on), `side {text, step?, reply?}` (`reply: true`: in the latest side thread), `use {index?}` and
`dismiss {index?}` (the k-th open challenge, from 1; `use` skips questions). `"settle": false` plays the line without
waiting for the previous one to finish (a side thread opened mid-answer).

The decision history adds four acts, all of layer 4. `branch {text, step?, chip?}` opens a branch with `side`: with
`chip` (`{kind, label?, text?}`), on the `subject` of the newest chip in the main chat of that kind whose label and
text match when given (case-folded, runs of white space as one; no such chip stops the scenario); with `step`, on
`{"kind": "step", "step"}`; else on the whole plan. `accept` and `decline` act on the newest pending proposal;
`close` closes the newest open side branch. Any of them with nothing to act on stops the scenario with that reason.

`run_scenario` works in a scratch folder under `my/var/replay/`: it copies the
brief and the modules (leaving out the `without` steps), sets the database,
brief and modules variables to it, `HARNESS_LAYERS` to the scenario's layer and
`HARNESS_REVIEW` to `auto` when `review` is true, else `off`, and opens a
`Session` (which adopts the modules) with `today` in its memory. For `build` it plays `build` first. It
settles before each line and plays them in order, stops when the lines run out, settles, and checks. A line the
core refuses, a job that failed, or a lane still working after 900 seconds stops it with that reason. `replay
EXAMPLE [SCENARIO] [--keep]` prints one line per expectation and one for the scenario, and exits 0 only when none
failed. `load_scenarios` skips scenarios whose `layer` is above the enabled layers and reports them as skipped.

Expectation keys are registered by layers (`Layer.expects`), each with a
validator and a checker that returns `{"what", "passed", "seen"}` and is given the Session. A scenario may use
the keys of its own layer and below. Unknown keys are errors. Checks never read wording.

### 2.7 The server: `harness/ui/server.py`

`ThreadingHTTPServer` on 127.0.0.1. `GET /` serves `page.html` with the token
put in place of `__HARNESS_TOKEN__`. `GET /api/state` and `POST /api/act` need
the header `X-Harness-Token`; without it, 403. Other paths: 404. Bodies over
1 MB: 400. Responses carry `Cache-Control: no-store`.

### 2.8 The page: `harness/ui/page.html` (given)

One file, built with the design system in `design/system/` (tokens, bundle
CSS and JS inlined; no web font). It draws the state document and nothing
else, polls as ARCHITECTURE.md 4.2 says, and sends actions. It follows the
design: the goal above the diagram; steps laid out by `edges` in columns,
inputs as pills above their steps; one pop-up at a time; the chat panel with
the composer, step chip, "On the side" toggle and placeholders; decisions,
notices and threads; the Review toggle (top right, after acceptance, with the
open count); "Whole plan" opening the context section. Once an answer exists,
steps not in it are faded and the inputs it used are darkened; a number with a
`step` is underlined, selects its step and opens its pop-up on the figure's
`run` (the step's other recent runs one click away). Values are drawn as the
state's `shown` writes them, with the exact values on demand. A step nothing
connects is placed in the column of its `near` step. Text is inserted as text, never
HTML. A feature whose keys are absent is not drawn.

## 3. Layer 1: the plan (`harness/grounding/`)

### 3.1 The brief

`domain_brief.json` and `domain_brief.md` in `brief_dir`, written by
`save_brief`. Its shape:

```
{"goal": Item, "mode": "ongoing" | "one_off",
 "scope": {"in": [Item], "out": [Item]},
 "glossary": [{"term", "definition", "person_says", "source"}],
 "particulars": [{"what", "handling", "step": id | null, "origin": Origin}],
 "inputs": [{"name", "description", "origin": Origin}],
 "process": [{"id", "name", "kind": "calculation" | "judgment" | "input", "method", "formula",
              "needs", "produces", "cadence", "origin": Origin}],
 "definition_of_done": [Item],
 "open_questions": [{"text", "step": id | null, "origin": Origin}],
 "meta": {"status": "confirmed" | "draft", "written_at", "session_id", "lookups",
          "revisions": [{"ts", "words", "step", "by": "person" | "reviewer"}]}}
```

`Item` and `Origin` are as in ARCHITECTURE.md 3.1, except that a brief's
`looked_up` origin holds `"source": url`. A glossary entry's origin is derived:
`looked_up` with a source, else `proposed`.

`validate_brief(brief, lookups, words)` returns what is wrong; an empty list
accepts the brief. It checks: every key is present; the goal has text; `mode` is
known; `scope.in` and `definition_of_done` have at least one item; process step
ids and input names are unique; a glossary entry has a term and a definition,
and its source, if any, came from a lookup; a particular has `what` and
`handling`; an input has a name and a description; the process has at least one
step, each with an id, a name, what it produces and a known kind, and no step
needs itself; a calculation has a formula and a method that is `arithmetic` or a
glossary term with a source. Then: every origin has a known kind; a `person`
quote is at least three characters and appears in `words` (the person's messages of this interview or revision),
compared case-folded with runs of white space as one space; a `looked_up`
source came from a lookup; every `step` of a particular or open question is a
process id; every entry of a step's `needs` is the exact name of an input or the id of an earlier step;
every input is named in the `needs` of at least one step (an input no step uses is drawn nowhere).
Errors go back to the interviewer.

### 3.2 The interview

The interview asks one question per message, plans its research before the
first question, looks terms up with `look_up` through the research desk (at
most twelve different terms, one lookup each), and ends with `write_brief`.
A third rejected brief in a row is saved as a draft and the interviewer asks
the person one question. `/wrap` asks it to propose the plan now; after twelve
answers it is told to write the brief. It runs as a main-lane job: its questions are posted as assistant messages and it
waits with `{"kind": "message"}`; its progress lines set `activity`. The state
`grounding_state.json` is kept for resuming, and `loaded` resumes it.

- A person's answer with a step attached reaches the interviewer prefixed with
  `[harness] About step {id} ({name}):`.
- A valid `write_brief` makes the brief **proposed**: `phase` is `proposed`,
  the steps are drawn from it, the harness posts `PLAN_PROPOSED` (kind `plan`)
  and waits with `{"kind": "plan"}`. After a correction it posts
  `PLAN_REVISED` instead, with `changes` worked out by the harness from the
  two versions (`brief.describe_changes`): the steps added, changed (step
  fingerprint or name) and removed, by number and name; with none, what
  around them changed.
- `accept_plan`: the brief is saved as confirmed, the harness posts
  `PLAN_ACCEPTED`, `phase` is `accepted`, the first trunk node is recorded
  (`plan_accepted`, who `you`, text `Plan accepted`), hook `plan_accepted`.
  On `loaded`, a confirmed plan whose conversation has no node yet (a seeded
  example, a database made before the trunk) records the same node, after
  `PREPARED` when that is posted.
- A message instead: it is a correction. The tool result to the interviewer is
  `NOT_CONFIRMED` and the words, with the step prefix when a step is attached.
  The interviewer submits a revised brief; the diagram redraws from it.
- A brief with open questions can be accepted.

```
PLAN_PROPOSED = "This is the plan as I understand it. Click a step to say what is wrong, or accept it."
PLAN_REVISED  = "The plan is revised: {changes}. Click a step to say what is wrong, or accept it."
PLAN_ACCEPTED = "The plan is accepted."
PREPARED      = "This is a prepared plan: {goal}. Ask a question about it, or click a step to see what it does."
```

In example mode (`HARNESS_EXAMPLE`), `loaded` posts `PREPARED` (a `harness`
message; `goal` is the first sentence of the plan's goal) when the plan is
accepted and the conversation has no message yet.

### 3.3 Revising an accepted plan: `revise.py`

`revise_plan(work, *, words, step, by, branch=None) -> {"changed": [ids], "node": "n<id>"} | {"error": str}`.
One interviewer conversation: the interviewer's system prompt, the accepted
brief, and a `[harness]` line asking for exactly the change in `words`
(about `step` when given), with `look_up` and `write_brief` as tools, up to three
attempts. A valid brief is saved as confirmed with a new `revisions` entry.
`changed` lists the steps added, removed, or whose step fingerprint (4.4)
changed. The harness posts `PLAN_CHANGED = "The plan is changed: {changes}."`
(`changes` as in 3.2), then records the trunk node `plan_revised` (who `you`, or `reviewer` when `by` is the reviewer;
text `Plan changed: {changes}`; change `{step, words, changed}`; touched steps `changed`; `branch` as given, which
joins that branch). Hook `plan_changed(changed)`. A reply with no `write_brief` returns
`{"error": "the plan was not changed: <reply>"}` and records nothing.

### 3.4 Lookups

The research desk, its researchers (`reference`, `wikipedia`, `claude_code`,
`auto`), its cache table `lookups` and `MAX_QUERY_LENGTH = 100` are kept.
`ResearchDesk.look_up_general(query)` is new: it refuses a query with a digit
in it, or longer than 100 characters, or of more than 12 words, before any
request; otherwise it is `look_up`. Layers 4 and 5 use it.

### 3.5 What it registers

`contribute`: `phase`, `goal`, `context`, `inputs`, `steps` (the base fields),
`edges`, from the proposed brief while there is one, else from the saved
brief. `route`: in phase `empty`, a message starts the interview (as `start`).
Actions `start`, `accept_plan`, `wrap`. Trunk nodes `plan_accepted`, `plan_revised`. Command `ground`. Events: `plan.answer`,
`plan.question`, `plan.correction` (one question rule), `plan.research_plan`,
`plan.lookup`, `plan.brief_rejected`, `plan.proposed`, `plan.changes`,
`plan.accepted`, `plan.revised`.

## 4. Layer 2: build and tested calculations (`harness/calc/`)

### 4.1 Kept as they are

`values.py`, `safety.py`, `runner.py`, `provenance.py` (`unbacked`, `trace`),
`notes.py`, `added.py`, the module folder (`spec.json`, `golden.json`,
`module.py`, `tests.py`) and its fingerprint, `validate_spec`,
`input_problems`, the three model phases and their conversations, the code
checks, and the rule that the code writer is told only which example failed and
its inputs. The tables `test_runs`, `modules`, `step_modules`, `calc_runs`,
`notes`, `added_steps` keep their columns, in `calc/schema.sql`.

### 4.2 What changes

- `modules` gains `step_fingerprint`.
- `golden.json` entries are `{"inputs", "expected", "working", "checked_by":
  "second_pass" | "you"}`. `register` needs at least two.
- `propose_spec` gains `departures`: a required list of `{kind, text}`, each
  one way the spec departs from the brief's step in substance: `formula` (a
  different quantity would come out), `input` (one the step's needs do not
  name), `left_out` (a need left out), `output` (a different output); or
  `made_exact` (the brief's step made exact: an input's shape, rounding,
  units, wording), which is recorded in `build.spec_proposed` and kept out of
  the plan check. A plain sentence counts as a departure. Empty when there are
  none. The person is not asked about the spec.
- New table `build_steps (step_id PRIMARY KEY, status, module, spec, departures,
  departures_confirmed, examples, disagreement, reason, ts)`; `spec`,
  `departures`, `examples`, `disagreement` are JSON. New table
  `example_confirmations (id, ts, step_id, n, answer)`.

### 4.3 The unattended build

`build` queues one main-lane job. For each calculation step in plan order
whose status is `none`, `not_built` or `stale`, with progress text for each
phase:

1. **Spec.** One conversation with `spec_writer.md`, given the step, the
   brief, the registered modules with unchanged files and the notes, and
   `[current spec]` when the step has a stored spec; up to three attempts. It
   proposes a spec (`propose_spec`, checked by `validate_spec`; a new module
   may not take a registered name) or maps the step to a registered module
   with unchanged files (`reuse_module`). No person check. `plan_check` in
   the state is null when `departures` is empty.
2. **Examples.** The example writer proposes three to five.
3. **Second pass** (4.5). Examples it agrees with are `checked_by:
   "second_pass"`. Examples the person confirmed earlier for this step are
   kept as `you`, with their answer. Fewer than two checked: the writer is
   asked once more for new examples, which are checked the same way. Still
   fewer than two: the step is not built.
4. **Code.** One conversation with `module_writer.md`, given only the spec,
   up to three attempts. The code is checked, then tested in a staging folder
   with the checked examples as `golden.json`, and moved into place and
   registered when it passes. When the code still fails an example, the step
   is not built and `disagreement` lists each failing example: `n`, `expected`,
   `code_gives`.

Reasons for not built, stored in `reason`: `no acceptable spec`, `no acceptable
examples`, `the second pass did not agree with enough examples`, `the code did
not pass`, `its tests do not pass here`. Hook `step_built` after each step. At
the end the event `build.finished` holds `{"steps": {id: outcome}}`, each
outcome `built`, `reused`, `kept` (already built and not stale) or
`not_built`, and the harness posts `BUILD_DONE`, and `BUILD_NEEDS_YOU` when a
step was not built.

```
BUILD_DONE      = "{built} of {total} calculation steps are built and tested."
BUILD_NEEDS_YOU = "These need you: {steps}. Click one to see why."
```

`build_step(work, step, *, rebuild=None, code_only=False)` builds one step; the
build job and layer 4 use it. `code_only` reruns step 4 with the stored spec
and examples.

### 4.4 Stale and the gate

A step's fingerprint is the SHA-256 of the canonical JSON of its `kind`,
`method`, `formula`, `needs`, `produces` and the `what` and `handling` of its
particulars. `register` stores it. A built step is `stale` when the plan's
step fingerprint differs from the stored one, or its files changed or its folder is gone (reasons `its files changed`, `its folder is missing`). The gate
also refuses a stale module: `STALE = "The step of '{name}' changed in the
plan, so '{name}' must be built again."` Every other gate rule is kept.

### 4.5 The second pass: `checker.py`

`check_examples(model, spec, examples) -> [{"n", "agrees": bool, "answer"}]`.
One model call per step with `checker.md` and the tool `answer_examples`
(`{"answers": [{"n": int, "answer": json, "working": str}]}`).

- **Given**: the spec's `name`, `description`, `method`, `formula`, `inputs`,
  `output`; and each example's `n` and `inputs`.
- **Not given**: the expected answers, the working, the example writer's
  messages, the brief, the notes, the person's words, other modules, any code.
- An answer counts only when it fits the output type and every number in it
  appears in its own working (`unbacked`). It agrees when `values.same(expected,
  answer)` is true.
- A missing, malformed or disagreeing answer leaves the example out:
  `checked_by: null` and `second_pass` set to the checker's answer (or null).
  Left-out examples are kept in `build_steps.examples` and shown in the pop-up.
- Known trade-off: a mistake both passes make gets through. The person can
  still confirm or correct any example.

### 4.6 Adoption on load

`loaded` adopts, without asking: each folder in `modules_dir` that is not
registered with unchanged files, whose spec's `step_id` is a calculation step of
the plan or an `added_<n>` step, has its tests run and is registered on a
pass (an `added_<n>` step the database lacks is re-created from the spec),
with a `build_steps` row from its files. A folder that fails gets status `not_built`, reason `its tests do not pass here`.

### 4.7 The person on a step: the step helper

`route`: in phase `accepted`, every message with a calculation step attached.
`helper.wants(step)` is true when that step is `not_built`, has a left-out
example, or has departures not confirmed; layer 3 leaves exactly those
messages to this route (5.1), so with layer 3 on only they reach the helper.
One model call with `step_helper.md`, the tool `respond`:

```
{"action": "correct" | "confirm" | "explain" | "note" | "rebuild",
 "example": int, "answer": json, "message": str}
```

- `correct`: `example` and `answer`. The answer fits the output type and every
  number in it is in the person's message or the example (number check). It is
  stored in `example_confirmations` and the step is rebuilt with `code_only`.
- `confirm`: `example`; recorded as confirmed by you, answer unchanged. When
  the person says the departures are fine, `example` is 0: departures are
  confirmed.
- `explain`: `message`, number-checked against the spec, the examples and the
  person's words; posted as the reply.
- `note`: the message is kept as a note for the step; the harness says so.
- `rebuild`: the message is kept as a note and the whole step is rebuilt.

A call that fails its checks gets `HELPER_UNCLEAR = "I could not tell what to
change. Say which example and the right answer, with every number written
out."`

### 4.8 What it registers

`contribute`: `build` on calculation steps. Actions `build`,
`confirm_example`, `confirm_plan_check`, `run_tests`. Command `build`. Expects
`steps` (`{step id: built | reused | kept | not_built}`). Events:
`build.started`, `build.spec_proposed`, `build.spec_rejected`,
`build.examples_proposed`, `build.examples_rejected`, `build.second_pass`,
`build.code_written`, `build.code_rejected`, `build.tests_run`,
`build.registered`, `build.reused`, `build.not_built`, `build.adopted`,
`build.example_confirmed`, `build.example_corrected`,
`build.departures_confirmed`, `build.note`, `build.finished`.

### 4.9 The harness's own branch (not built)

This is reserved: the core accepts these nodes (ARCHITECTURE.md 3.5), but nothing in
layer 2 records them yet.

The unattended build records one node when it ends with a step built: `built`, who `harness`, change
`{"steps": {id: outcome}, "why": "build"}` for the steps built or reused, no branch. A single step built again
outside it (the helper's rebuild, `code_only`, a stale step, or adoption of a registered module whose files
changed) opens a branch of kind `harness` (origin `harness`, subject the step), posts its lines there
(`REBUILDING_WHY = "Building step {number} {name} again: {why}."`, then `STEP_BUILT` or `STEP_NOT_BUILT`; what the
helper posts in the main chat today stays as it is), and
on `built` or `reused` records the node (`why` `rebuilt` or `files_changed`), which joins it. A step not built
leaves the branch open. The person is not asked.

## 5. Layer 3: answers with evidence (`harness/answers/`)

### 5.1 The analyst

`route`: in phase `accepted`, every message except one with a step attached
for which `helper.wants(step)` is true (4.7). Each message is one analyst turn
on the main lane.

- System prompt: the prompt parts of the enabled layers, then `## What you
  know` and the context sections: `today`, `goal`, `particulars`, `process`
  (the plan's steps, added ones included, with their ids), `modules` (name,
  step, spec), `saved inputs`, `notes`, then the sections of later layers.
- The model's messages are kept in memory for the life of the `Session`. A
  person's message with a step attached is prefixed `[harness] About step {id}
  ({name}):`.
- Up to 10 model calls per person message (`TOO_MANY` after that).
- Tools from the enabled layers. Layer 3's:
  - `run_module {module, inputs, assumptions: [str], expected: str}`: inputs
    number-checked, then `gate.call`. Never held for the person. Result:
    `{"module", "run_id", "output"}` or the refusal.
  - `save_input {name, value, note}`: `name` in snake_case, a non-empty
    value, number-checked, then saved; a different value replaces the saved
    one. The write is `store_input(conn, name, value, note, conversation)`,
    which layer 4's join also calls.
  - `change_plan {step, words}`: `words` must appear in a message the person
    typed in this conversation (compared as in 3.1). Calls `revise_plan`
    (`by: "person"`). Result: the changed steps or the error.
- A reply: number-checked against the sources (the brief, today, the person's
  messages, saved inputs, notes, runs and inputs of this conversation, decision
  words). Unbacked: sent back once; a second time `WITHHELD` is posted, kind
  `withheld`. Recorded as `ask.correction`, `ask.withheld`.
- The final reply is posted with `figures` (5.2). Hook `turn_finished(turn)`,
  where `turn` lists the runs made, the reply's message id and whether it was
  withheld.
- Two checks of later layers. Before a run that passed the number check goes
  to the gate, hook `run_ready(work, turn, arguments)`: a layer may add
  sentences to `arguments["assumptions"]`, or refuse the run by setting
  `turn.send_back` (that text is the tool's error result). A reply that passed
  the number check, while the turn has a model call left, goes to hook
  `reply_ready(work, turn, text)`: a layer that sets `turn.send_back` has the
  reply not shown and that text sent to the model as the next user message.

### 5.2 Figures and last runs: `figures.py`

`figures(text, sources) -> [Figure]` uses `provenance.trace` and maps as in
ARCHITECTURE.md 3.4. A figure leads to a step only when it matches what one of
that step's runs **produced**: its output, or a value inside an object or a
list output that is not also among that run's inputs (a value passed through).
A number that runs were only given is traced to where it came from (the
person's words, a saved input, the plan) and leads to no step. Of several runs that produced it, a run of the
current turn wins, the most recent first, then earlier turns, the most recent
first. A date leads to a step only when a run's output holds that date whole;
a year or any other part of a date never does. The number check (what may be
shown at all) is unchanged.

The **last answer** is the latest message ending an analyst turn that ran
modules or has a figure leading to a step. A step is in it (`in_last_answer`)
when the turn ran its module or a figure of the answer leads to it, whenever
that run was made. `contribute` sets on each calculation step `last_run` (the
latest of its runs the last answer used while it is in it, else its latest
run in this conversation) and `runs` (its last five runs, newest first, each
with `shown`); on an added step, `needs`, `inputs` and `edges` from its latest
run (an input named as a plan input, or held by a saved one, is a pill; an
input an earlier run of another step produced is an edge from that step); and
`used` on inputs named by a step in the last answer.

### 5.3 What it registers

Table `inputs (name PRIMARY KEY, value, note, ts, session_id)`, kept across
conversations. Tools above. Prompt `analyst.md`. Command
`ask`. Expects `runs`, `shown`, `not_shown`, `max_withheld`,
`max_corrections` (a list of module runs with inputs, numbers shown or not in
the assistant's messages, at most that many withheld replies or corrections).
`shown` and `not_shown` read what the person reads in the main chat: the
assistant's replies and decision questions and each harness message (a join
notice), each with the text of its chips. Events: `ask.message`, `ask.reply`,
`ask.correction`, `ask.withheld`, `ask.stopped`, `ask.input_saved`,
`ask.plan_changed`, and the gate's `calc.run`, `calc.refused`.

### 5.4 Chips and the re-run engine (ARCHITECTURE.md 12.4, 12.7)

- **Chips.** `contribute` sets `chips` on every message: built from its private `_runs` (`_chip_runs` when present)
  as ARCHITECTURE.md 12.7 says, else `[]`. Assumption chips have `status` null and `subject.assumption` null here.
  The prompt asks for one or two sentences; nothing checks the length.
- **Telling the analyst.** `tell_analyst(session, text)` puts `text` before the person's next message to the
  analyst, as `WITHHELD_NOTE` is today.
- **Re-runs.** `answers/rerun.py`: `last_answer_runs(conn, conversation)` (the runs of the last answer, 5.2, oldest
  first); `old_values(conn, conversation, key)` (the distinct values of the top-level input `key` among them, as
  written); `impact(conn, state, *, key, old) -> Impact`; `rerun(work, *, key, old, new, label, drop=()) ->
  {"replaced": {old run id: new run id}, "failed": [{"run", "step", "reason"}], "runs": [run ids]}`, where `runs` is
  the new last answer and `drop` the assumption sentences to leave out. Both follow ARCHITECTURE.md 12.4 exactly;
  `rerun` calls `gate.call` on `work.conn` and `work.progress` before each run, and posts nothing.

## 6. Layer 4: when the harness needs the person (`harness/needs_you/`)

### 6.1 Run and mark: `marks.py`

Tables `assumptions (id, key UNIQUE, text, status, words, ts)` and
`run_assumptions (run_id, assumption_id)`. `key` is the sentence on one line,
case-folded.

- After each run, each of its assumption sentences is stored (a new key is
  `unconfirmed`) and linked to the run.
- **Unconfirmed** means: an assumption of a run whose status is not
  `confirmed`. A step shows `◌` when its last run has one.
- When a turn's runs have unconfirmed assumptions, the turn's final message
  gets a `notice`: those assumptions and the steps of those runs, status
  `open`.
- `confirm_assumptions {message}`: each of the notice's assumptions becomes
  `confirmed`; the notice becomes `confirmed`. Marks clear wherever only those
  assumptions were unconfirmed. Trunk node `assumption_confirmed` (who `you`,
  text `Confirmed: {first sentence}` with ` and {n} more` when there are
  others, touched steps the notice's steps).
- A message with `notice` set (the person's "Change it"): the notice's
  assumptions become `corrected` with the person's words; the notice becomes
  `changed`; the analyst turn starts with `CORRECTED = "[harness] The person
  says this is not right: {assumptions}. Their words follow. Run again the
  steps that rested on it."` A corrected assumption used again counts as
  unconfirmed. Trunk node `assumption_corrected` (who `you`, text `Corrected:
  {first sentence}`, change `{assumptions, words}`, touched steps the notice's
  steps), recorded before the analyst's turn.
- **Unlisted assumptions** (hook `run_ready`). A value is the person's when
  the person's messages in this conversation (with `half`, `a third`, `a
  quarter` and number words read as numbers, and dates written as `12 June
  2027`), a saved input, an item of the plan whose origin is `person`, a
  confirmed assumption, today, or the output of a run of this conversation
  holds it: a number as the number check reads it, a date whole. A run input
  (at any depth) that is a number other than a whole number from 0 to 12, or
  an ISO date, and is not the person's, is an assumption. It is listed when a
  sentence of the run's `assumptions` holds its value or names its input
  (`second_payment_share` as `second payment share`). The first run of a turn
  with an unlisted one is refused with `UNLISTED`; a later run of that turn
  goes ahead with `AUTO_ASSUMED` added for each. A value only in a `proposed`
  item of the plan is therefore an assumption. Text and true/false values
  are not checked. Recorded as `you.assumption_unlisted {module, values,
  outcome: refused | marked}`.

```
UNLISTED     = "These values are not ones the person gave (in their words, a saved input, a confirmed assumption or an earlier result): {values}. Each is an assumption: give it in `assumptions`, with its value, in plain words. Then run again."
AUTO_ASSUMED = "{input} is taken to be {value}, which you did not give."
```

- Context section `assumptions`: each with its status and words.

### 6.2 Calls that are the person's: `calls.py`

Table `decisions (id, ts, conversation, step_id, question, options, suggested,
why, choice, words, runs, message, status)`; `status` is `open`, `answered` or
`dropped` (asked by a process that ended before an answer; the state shows it as
answered with no choice).

- Tool `ask_decision {step, question, options, suggested?, why?, runs}`. `step`
  is required and must be a plan step. Checks: a question in plain words;
  two to four distinct options; `suggested`, when given, is an option's number
  and comes with a reason; `runs` are runs of this conversation; the question,
  options and reason pass the number check. At most two per person message, and
  a second only after the first is answered.
- The harness posts a `decision` message and waits with `{"kind": "decision"}`.
  The step is `needs_you`. `choose {decision, option}` picks an option. A
  message answers it in the person's words: a number or an option's words
  pick that option; `yes` picks the suggestion; anything else is `something
  else` with the words.
- The record is a `decisions` row and the step's `calls.records`. The tool
  result is `{"outcome": "decided", "decision", "choice", "option", "said",
  "judgment_steps"}`: `option` is the chosen option's text (null for something
  else), `said` the person's words, and `judgment_steps` each judgment step
  with whether it is decided. An answered decision also records the trunk node
  `call` (who `you`, text `{question} {option's text or words}` cut to 80,
  change `{decision, step, choice, words}`, touched steps its step). A dropped
  decision records nothing.
- **A call left in prose** (hook `reply_ready`). It looks only at a turn
  where the person's message asks to decide or choose (a word such as
  `decide`, `decision`, `choose`, `choice`), or is attached to a `judgment`
  step its runs feed, and the turn ran a module and asked no decision. Such a turn's reply
  is sent back once with `DECISION_SEND_BACK` when it has a question (a
  sentence ending in `?`; reason `alternatives` when the question has the word
  `or` or is next to a list of two or more items, else `your call`), or when it
  has none but a run of the turn was of a step that an undecided `judgment`
  step needs (reason `your call`). `{steps}` names those judgment steps (else
  it is empty). The harness never makes the options. The reply up to that question (all of it for a reply with
  no question) is kept: if the model then asks a decision, it is posted first,
  as the assistant's message, so the results are not lost. The reply after the
  send-back is shown whatever it is. Recorded as `you.decision_prompted
  {reason, steps, text}`.

```
DECISION_SEND_BACK = "[harness] Your reply was not shown. It leaves to the person, in plain text, what may be a call of theirs{steps}. If it is a call only the person can make, such as a choice between ways forward or what to change, put it to them now with `ask_decision`, with the options you had in mind; your reply up to that question is shown first. If it only asks for a figure or a fact you lack, or offers to do more, send the same reply again."
```

- Context section `decisions`.

### 6.3 Missing calculations: `requests.py`

Tool `request_module {case: step | new | replace, target, name?, works_out,
from_what, gives, formula, why}` (`name`: a short name for a new step; else it is
cut from `works_out`). Every field in words is required and number-checked;
`step` must name a calculation step that is not built; `replace` must name a
registered module whose step is in the plan. At most two per person message,
counted whatever the outcome. It does not ask. `step` builds that step; `new`
adds a step (`added_<n>`, `in_plan` false) and builds it; `replace` keeps the words as a note and rebuilds the
module. The harness posts `BUILT_NOT_IN_PLAN` (for `new`) or `BUILT_STEP` and
the result goes to the analyst (`built`, `reused` or `not_built` with the
spec or the reason). `you.module_requested` records `near`: the step attached
to the person's message, else the step of the turn's latest run; an added
step carries it as `near` in the state. A step built or reused records the
trunk node `built` (who `assistant`, change `{"steps": {id: outcome}, "why":
case}`, text `Built step {number} {name}`), with no branch.

```
BUILT_NOT_IN_PLAN = "A calculation that is not in the plan was needed: {name}. It is built and tested."
BUILT_STEP        = "Step {number} {name} is built and tested."
NOT_BUILT_STEP    = "Step {number} {name} could not be built. Click it to see why."
```

### 6.4 Branches: `side.py`

A side thread is a branch (ARCHITECTURE.md 12). `side {text, step?, thread?,
subject?}` without `thread` opens one: origin `you`, subject `subject` (a
Subject of ARCHITECTURE.md 3.5 whose ids exist: a run of this conversation, a
plan step or input, an assumption, a node; anything else is a BadAction), else
`{"kind": "step", "step"}`, else `{"kind": "plan"}`; its `step` is the
subject's step; its title the first words of the text, cut to 45 characters
(the branch's first line names its subject). It marks the person's other open side branches dead as
12.5 says. With `thread` it says something in that thread, side or review; a
dead side branch opens again. One reply per message, on the side lane, with
`side.md` and the tools `look_up` (through `look_up_general`, at most three
per thread) and `propose_change` (6.6). Up to six person messages per thread.

- **It sees**: the plan (goal, context, steps with formula, needs, produces,
  particulars, open questions); for the attached step, its spec in plain words,
  examples and who checked them, last run, unconfirmed assumptions, decisions,
  challenges; the last ten main-chat messages as text; for a review thread,
  its challenge; the thread's own messages; and two new sections: `subject`
  (the subject with what it points at: the run's module, inputs and output, the
  input's name and saved value, the assumption's sentence, the node's text) and
  `last answer` (each of its runs: module, step, inputs, output).
- **It cannot** run, save, build, decide or apply anything. It may **propose**
  a change the person asked for (6.6); the harness applies it on their yes.
  Its reply is number-checked against what it sees, the thread's messages and
  its lookups; unbacked twice: `WITHHELD`.
- It works in every phase. `propose_change` is offered only in a side branch
  (not a reviewer's), once the plan is accepted.

### 6.5 What it registers

Prompt part `analyst.md`. Tools `ask_decision`, `request_module`. Actions
`choose`, `confirm_assumptions`, `side`, `accept_proposal`,
`decline_proposal`, `close_branch`. Route: a message with `notice`.
`contribute`: `unconfirmed`, `calls`, `needs_you` for a decision, `notice` and
`decision` on messages, side threads with `proposal`, assumption chips'
`status` and `subject.assumption`, a join notice's decision chip. Table
`proposals`. Trunk nodes `call`, `assumption_confirmed`,
`assumption_corrected`, `value`, `built`. Expects `decisions` (`[{step, choice,
count}]`), `marks` (`{"min", "max", "confirmed", "corrected"}`: open notices; actions done), `side_threads` (int), `added`
(int: added steps), `branches` (6.6). Events: `you.decision_asked`, `you.decision`,
`you.decision_refused`, `you.assumptions_confirmed`,
`you.assumptions_corrected`, `you.module_requested`, `you.request_refused`,
`you.side_opened` (with `subject`), `you.side_message`, `you.side_reply`, `you.side_withheld`,
`you.side_lookup`, `you.assumption_unlisted`, `you.decision_prompted`,
`you.branch_dead`, `you.branch_reopened`, `you.proposed`,
`you.proposal_refused`, `you.proposal_accepted`, `you.proposal_declined`,
`you.joined`. Hooks `run_ready` and `reply_ready` (5.1), and `turn_finished`
(marks, and the `moved_on` death).

### 6.6 Proposals and joins: `side.py`, `join.py`

The mechanics are ARCHITECTURE.md 12.3 to 12.5; this is the interface.

```
propose_change {"kind": "value" | "plan",
                "input": str,          value: the value's name as the last answer's runs give it
                "value": str,          value: the new value in plain form (digits, YYYY-MM-DD, or text)
                "step": str,           plan: the step it is about, or ""
                "words": str}          the person's words in this thread it rests on, copied exactly
```

Checks, in order, each refusal the tool's error result and a
`you.proposal_refused {thread, reason, change}`: `not_their_words` (the words,
compared as in 3.1, are in no person message of this thread); `unknown_input`
(12.3, point 2); `value_unbacked` (a number or date of `value` not in the
person's messages of this thread, read with number words and dates); `ambiguous`
(12.3, point 4); `same`; `unknown_step`; `one_per_reply`. A proposal that passes
is stored `pending` with its `impact`, replaces a pending one in the thread,
records `you.proposed`, and the tool result is `PROPOSED`.

`accept_proposal {proposal}`: NotNow unless it is `pending`, or while the main
lane waits on a decision (`ANSWER_FIRST = "Answer the question that is waiting first."`, layer 4's own). It becomes
`accepted`, records `you.proposal_accepted`, and queues the main-lane job
(`what` `join`). The job is 12.3; it ends with `JOINED` (or `JOINED_NOTHING`
when no run of the last answer used the value), `NOT_RUN_AGAIN` added for
failures, and `you.joined {thread, proposal, node, runs, failed}`. A plan
proposal whose revision fails becomes `failed`, its reason posted in the
branch as a `harness` message. `decline_proposal {proposal}`: NotNow unless
`pending`; `declined`, the branch dead. `close_branch {thread}`: NotNow unless
a side branch of this conversation whose outcome is `open`; a pending
proposal in it is declined; the branch dead. A malformed id is a BadAction.

```
PROPOSED        = "Proposed: {text}. It touches {steps}. The person sees it with Yes and No in this thread, with what it changes and re-runs: do not repeat that. Say only, in a few words, that it waits for their yes. Do not say it is done."
NOT_THEIR_WORDS = "Those are not words the person wrote in this thread. Copy them exactly from their message."
UNKNOWN_INPUT   = "Nothing in the last answer takes {input}. The values it took are: {inputs}. Propose one of them, or tell the person to say it in the main chat."
VALUE_UNBACKED  = "The new value must be in the person's words in this thread, and {numbers} is not. Ask them for the figure itself. Do not work it out."
AMBIGUOUS       = "The last answer used several values for {input}: {values}. Ask the person which one they mean."
SAME            = "{input} is already {value}."
UNKNOWN_STEP    = "There is no step {step} in the plan."
ONE_PER_REPLY   = "One proposal per reply."
JOINED          = "Decided on a branch: {label} is {new} (was {old}). Run again: {steps}."
JOINED_NOTHING  = "Decided on a branch: {label} is {new} (was {old}). Nothing in the last answer used it."
NOT_RUN_AGAIN   = " Not run again: {steps} ({reason})."
RERUN_EXPECTED  = "Run again by the harness: {label} is {new} (was {old})."
JOIN_NOTE       = "[harness] On a branch the person changed {label} from {old} to {new}, in their words: \"{words}\". The harness saved it and ran again: {runs}. These are now the current results; do not run them again unless the person asks."
```

`{old}` is `none` when there was no old value. `{steps}` is `step 1` or `steps
1, 2 and 5`; in `PROPOSED`, the impact's steps then ` (and {downstream} further
down)`. `{runs}` in `JOIN_NOTE` is `{module} gives {output as JSON}` for each
new run, joined by `; ` (never a run id). A node's `text` for a value is
`{label}: {new} (was {old})`.

Expectation `branches {"joined"?, "dead"?, "nodes"?}`: `joined` and `dead`
are the exact numbers of side branches (origin `you`) with that outcome at
the end; each kind in `nodes` is the kind of the node of a joined side branch.

**The two seeded scenarios** (`examples/wedding/scenarios/`):

`branch_that_joins.json`:

```json
{
  "name": "branch_that_joins",
  "layer": 4,
  "kind": "ask",
  "description": "The payments are worked out for 120 guests (total 36,100, later payments 15,050 each). From the guest count's chip the person opens a branch and says they will get no fewer than 150; the side assistant proposes 150, the person accepts, the branch joins the trunk as a decision, and steps 1 and 2 run again (total 43,000, later payments 18,500 each).",
  "today": "2026-10-12",
  "lines": [
    "Can I cover the three payments if we invite 120 guests? The wedding is on 12 June 2027. Dinner is 230 a guest, plus 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due 21 days from today, and it counts toward the total. The second and third payments are each half of what remains, due 30 and 14 days before the wedding.",
    {"act": "branch", "chip": {"kind": "value", "label": "Guest count", "text": "120"}, "text": "We will get no fewer than 150 guests."},
    {"act": "accept"}
  ],
  "expect": {
    "runs": [
      {"module": "wedding_total_cost", "inputs": {"guest_count": "120", "dinner_cost_per_guest": "230"}},
      {"module": "wedding_total_cost", "inputs": {"guest_count": "150", "dinner_cost_per_guest": "230"}},
      {"module": "wedding_payment_schedule", "inputs": {"total_cost": "36100", "first_payment_amount": "6000"}},
      {"module": "wedding_payment_schedule", "inputs": {"total_cost": "43000", "first_payment_amount": "6000"}}
    ],
    "branches": {"joined": 1, "dead": 0, "nodes": ["value"]},
    "max_withheld": 0,
    "shown": ["43,000", "18,500"]
  }
}
```

`branch_that_dies.json`:

```json
{
  "name": "branch_that_dies",
  "layer": 4,
  "kind": "ask",
  "description": "The person opens a branch on step 5 to ask what a sinking fund is. It is answered from the plan and the standard terms, nothing is proposed, and closing it leaves it dead: no decision is recorded and the plan is as it was.",
  "today": "2026-10-12",
  "lines": [
    {"act": "branch", "step": "s5", "text": "What is a sinking fund?"},
    {"act": "close"}
  ],
  "expect": {
    "side_threads": 1,
    "branches": {"joined": 0, "dead": 1}
  }
}
```

## 7. Layer 5: review (`harness/review/`)

### 7.1 When it runs

Unless `HARNESS_REVIEW=off`, a pass is queued on the review lane after
`plan_accepted`, after `plan_changed`, and after a turn whose runs stored an
assumption key never seen before. Passes do not overlap; one more is queued at
most.

### 7.2 A pass: `reviewer.py`

One conversation with `reviewer.md`, up to 8 model calls, tools `look_up`
(through `look_up_general`, at most four per pass) and `report`. Its user
message holds, as sections: the plan (goal, context, steps with ids, kinds,
formulas, needs, produces, particulars, open questions, origins), the built
specs (formula, inputs, output, departures; never code), the assumptions with
their status, the decisions, the saved inputs, the last runs' inputs and
outputs, the open, used and dismissed challenges, and the person's replies in
review threads.

```
report {"challenges": [{"step", "kind": "challenge" | "question", "title", "concern", "proposal",
                        "change": "plan" | "assumption" | "input" | "build_step" | "replace_step" | "none",
                        "impact": "high" | "medium" | "low", "sources": [url]}]}
```

The harness keeps a challenge only when: `step` is a plan step; `title` is 1 to
45 characters; kinds and values are known; a `question` has an empty proposal
and change `none`; a `challenge` has a proposal; every source is a URL a
lookup of this pass returned; `concern`, `proposal` and `title` pass the
number check against the user message and the lookups; it does not repeat an
open, used or dismissed challenge (same step and same title, compared as in
3.1). It sorts the kept ones by impact (high first), then the reviewer's order,
and keeps the first three; with five challenges already open it keeps none.
Every dropped one is recorded with its reason.

Each kept challenge opens a review thread on its step; the first message is
the reviewer's concern, then `Proposed: {proposal}`, with its sources.

### 7.3 Use this, dismiss, reply

- A review thread is a branch: origin `reviewer`, subject `{"kind": "step",
  "step"}` (layer 5 passes both to `add_thread`).
- `use_challenge`: the challenge and its thread become `used`; the trunk node
  `challenge_used` is recorded (who `reviewer`, text `Reviewer's suggestion
  used on step {number}`, change `{challenge, step, change}`, touched steps
  its step, `branch` the thread, which joins it); then the harness posts, as
  the person, `USE_THIS` with the step attached, and routes it.
- `dismiss_challenge`: both become `dismissed`; the branch is dead
  (`set_outcome`; the event is `review.dismissed`, as today). Later passes are
  told.
- A reply in its thread is a `side` action (6.4); the person's words reach the
  next pass and change nothing now.

```
USE_THIS = "Use the reviewer's suggestion on step {number} {name}: {proposal}"
```

### 7.4 What it registers

Table `challenges (id, ts, pass, step_id, kind, title, concern, proposal,
change, impact, rank, sources, status, thread_id)` and `review_passes (id, ts,
trigger, lookups, kept, dropped)`. Prompt part `analyst.md`. Actions
`use_challenge`, `dismiss_challenge`. Trunk node `challenge_used`. `contribute`: `challenges` on steps,
`challenge` on review threads, `review`. Expects `challenges` (`{"min",
"max", "used", "dismissed", "steps"}`). Events: `review.started`, `review.lookup`, `review.kept`,
`review.dropped`, `review.finished`, `review.used`, `review.dismissed`.

## 8. Given files

Files a build task does not rewrite. Prompts are read by the models and
tested only through behaviour.

| File | Layer |
| --- | --- |
| `harness/ui/page.html` | 0 |
| `harness/grounding/interviewer.md`, `planner.md`, `researcher.md`, `reference/terms.json` | 1 |
| `harness/calc/spec_writer.md`, `example_writer.md`, `checker.md`, `module_writer.md`, `step_helper.md` | 2 |
| `harness/answers/analyst.md` | 3 |
| `harness/needs_you/analyst.md`, `side.md` | 4 |
| `harness/review/reviewer.md`, `analyst.md` | 5 |
| `examples/` | data, per layer |
