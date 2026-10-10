# Contract: Financial Advisor Harness, version 2

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
   awaiting acceptance wait for the person.
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
  step NULL, title, status)`.
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
  3. else the harness posts `NO_ROUTE`.
- A job that raises is caught: `error` is set to one line, the event
  `core.job_failed` is recorded, the lane goes on with its next job.
- **Templates** (posted by the harness):

```
NO_ROUTE = "Nothing here can answer that yet."
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
   is not empty; kind `result`. A number is written with thousands separators
   and its decimals as given; a date as given; text cut to 18 characters; a
   list or an object as `{n} values`.
4. `build.status` is `built`: `{examples} examples · {passing}/{tests}`; kind
   `tested` when every test and example passes, else null.
5. `build.status` is `stale`: `Stale · rebuild`; `not_built`: `Not built`;
   kind null.
6. `calls.records` is not empty: `Decided`; kind null.
7. Otherwise `line` is null.

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
| `/side TEXT` | `side` with a new thread |
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
 "lines": [str | {"act": action, ...payload}],     may be empty for build
 "expect": {key: value}}
```

`run_scenario` works in a scratch folder under `my/var/replay/`: it copies the
brief and the modules (leaving out the `without` steps), sets the database,
brief and modules variables to it, `HARNESS_LAYERS` to the scenario's layer and
`HARNESS_REVIEW` to `auto` when `review` is true, else `off`, and opens a
`Session` (which adopts the modules). For `build` it acts `build`. It then
plays the lines in order, settling before each: a string is `say`; an object
is that action, where `challenge` may be given as `"index": k` (the k-th open
challenge, from 1). It stops when the lines run out, settles, and checks.
`load_scenarios` skips scenarios whose `layer` is above the enabled layers and
reports them as skipped.

Expectation keys are registered by layers (`Layer.expects`), each with a
validator and a checker that returns `{"what", "passed", "seen"}`. Unknown keys
are errors. Checks never read wording.

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
`step` is underlined and selects its step. Text is inserted as text, never
HTML. A feature whose keys are absent is not drawn.

## 3. Layer 1: the plan (`harness/grounding/`)

### 3.1 The brief

`domain_brief.json` and `domain_brief.md` in `brief_dir`, written by
`save_brief`. Version 2 shape:

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

`validate_brief(brief, lookups, words)` keeps every version 1 check and adds:
every origin has a known kind; a `person` quote is at least three characters
and appears in `words` (the person's messages of this interview or revision),
compared case-folded with runs of white space as one space; a `looked_up`
source came from a lookup; every `step` of a particular or open question is a
process id; every entry of a step's `needs` is the exact name of an input or the id of an earlier step;
every input is named in the `needs` of at least one step (an input no step uses is drawn nowhere).
Errors go back to the interviewer, as before.

### 3.2 The interview

The version 1 interview is kept (one question per message, the research plan
before the first question, `look_up` through the research desk with its limits,
`write_brief`, three rejections then a draft, `/wrap`, the question limit). It
runs as a main-lane job: its questions are posted as assistant messages and it
waits with `{"kind": "message"}`; its progress lines set `activity`. The state
`grounding_state.json` is kept for resuming, and `loaded` resumes it.

- A person's answer with a step attached reaches the interviewer prefixed with
  `[harness] About step {id} ({name}):`.
- A valid `write_brief` makes the brief **proposed**: `phase` is `proposed`,
  the steps are drawn from it, the harness posts `PLAN_PROPOSED` (kind `plan`)
  and waits with `{"kind": "plan"}`.
- `accept_plan`: the brief is saved as confirmed, the harness posts
  `PLAN_ACCEPTED`, `phase` is `accepted`, hook `plan_accepted`.
- A message instead: it is a correction. The tool result to the interviewer is
  `NOT_CONFIRMED` and the words, with the step prefix when a step is attached.
  The interviewer submits a revised brief; the diagram redraws from it.
- A brief with open questions can be accepted.

```
PLAN_PROPOSED = "This is the plan as I understand it. Click a step to say what is wrong, or accept it."
PLAN_ACCEPTED = "The plan is accepted."
```

### 3.3 Revising an accepted plan: `revise.py`

`revise_plan(work, *, words, step, by) -> {"changed": [ids]} | {"error": str}`.
One interviewer conversation: the interviewer's system prompt, the accepted
brief, and a `[harness]` line asking for exactly the change in `words`
(about `step` when given), with `look_up` and `write_brief` as tools, up to three
attempts. A valid brief is saved as confirmed with a new `revisions` entry.
`changed` lists the steps added, removed, or whose step fingerprint (4.4)
changed. Hook `plan_changed(changed)`. A reply with no `write_brief` returns
`{"error": "the plan was not changed: <reply>"}`.

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
Actions `start`, `accept_plan`, `wrap`. Command `ground`. Events: `plan.answer`,
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
- `propose_spec` gains `departures`: a required list of sentences, each one way
  the spec departs from the brief's step (an input the step does not list, a
  formula made exact where the brief leaves it open, a need left out). Empty
  when there are none. The person is not asked about the spec.
- New table `build_steps (step_id PRIMARY KEY, status, module, spec, departures,
  departures_confirmed, examples, disagreement, reason, ts)`; `spec`,
  `departures`, `examples`, `disagreement` are JSON. New table
  `example_confirmations (id, ts, step_id, n, answer)`.

### 4.3 The unattended build

`build` queues one main-lane job. For each calculation step in plan order
whose status is `none`, `not_built` or `stale`, with progress text for each
phase:

1. **Spec.** As in version 1, with the notes and the registered modules, and
   `[current spec]` when the step has a stored spec; `reuse_module` still maps
   the step. No person check. `plan_check` in the state is null when
   `departures` is empty.
2. **Examples.** The example writer proposes three to five.
3. **Second pass** (4.5). Examples it agrees with are `checked_by:
   "second_pass"`. Examples the person confirmed earlier for this step are
   kept as `you`, with their answer. Fewer than two checked: the writer is
   asked once more for new examples, which are checked the same way. Still
   fewer than two: the step is not built.
4. **Code.** As in version 1, up to three attempts, with the checked examples
   as `golden.json`. When the code still fails an example, the step is not
   built and `disagreement` lists each failing example: `n`, `expected`,
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
step fingerprint differs from the stored one, or its files changed. The gate
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
the plan (an `added_` step is re-created as in version 1), has its tests run and
is registered on a pass, with a `build_steps` row from its files. A folder
that fails gets status `not_built`, reason `its tests do not pass here`.

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
  - `save_input {name, value, note}`: as in version 1; a different value
    replaces the saved one.
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

### 5.2 Figures and last runs: `figures.py`

`figures(text, sources) -> [Figure]` uses `provenance.trace` and maps as in
ARCHITECTURE.md 3.4. `contribute` sets `last_run` on each calculation step:
its module's latest run in this conversation, with `in_last_answer` true when
the run was made in the turn of the latest posted reply; and `used` on inputs
named by a step in the last answer.

### 5.3 What it registers

Table `inputs` (as version 1). Tools above. Prompt `analyst.md`. Command
`ask`. Expects `runs`, `shown`, `not_shown`, `max_withheld`,
`max_corrections`, as in version 1. Events: `ask.message`, `ask.reply`,
`ask.correction`, `ask.withheld`, `ask.stopped`, `ask.input_saved`,
`ask.plan_changed`, and the gate's `calc.run`, `calc.refused`.

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
  assumptions were unconfirmed.
- A message with `notice` set (the person's "Change it"): the notice's
  assumptions become `corrected` with the person's words; the notice becomes
  `changed`; the analyst turn starts with `CORRECTED = "[harness] The person
  says this is not right: {assumptions}. Their words follow. Run again the
  steps that rested on it."` A corrected assumption used again counts as
  unconfirmed.
- Context section `assumptions`: each with its status and words.

### 6.2 Calls that are the person's: `calls.py`

Table `decisions (id, ts, conversation, step_id, question, options, suggested,
why, choice, words, runs)`.

- Tool `ask_decision {step, question, options, suggested?, why?, runs}`. `step`
  is required and must be a plan step. The version 1 checks are kept (two to
  four distinct options, a reason with a suggestion, known runs, the number
  check, one per reply, two per person message).
- The harness posts a `decision` message and waits with `{"kind": "decision"}`.
  The step is `needs_you`. `choose {decision, option}` picks an option. A
  message answers it in the person's words: a number or an option's words
  pick that option; `yes` picks the suggestion; anything else is `something
  else` with the words.
- The record is a `decisions` row and the step's `calls.records`. The tool
  result is as in version 1.
- Context section `decisions`.

### 6.3 Missing calculations: `requests.py`

Tool `request_module {case: step | new | replace, target, works_out,
from_what, gives, formula, why}` with the version 1 checks and limits. It does
not ask. `step` builds that step; `new` adds a step (`added_<n>`, `in_plan`
false) and builds it; `replace` keeps the words as a note and rebuilds the
module. The harness posts `BUILT_NOT_IN_PLAN` (for `new`) or `BUILT_STEP` and
the result goes to the analyst (`built`, `reused` or `not_built` with the
spec or the reason).

```
BUILT_NOT_IN_PLAN = "A calculation that is not in the plan was needed: {name}. It is built and tested."
BUILT_STEP        = "Step {number} {name} is built and tested."
NOT_BUILT_STEP    = "Step {number} {name} could not be built. Click it to see why."
```

### 6.4 Side threads: `side.py`

`side {text, step?, thread?}` without `thread` starts a side thread (title: the
step's name, or the first words of the text, cut to 45 characters); with
`thread` it replies in that thread, side or review. One reply per message, on
the side lane, with `side.md` and the tool `look_up` (through
`look_up_general`, at most three per thread). Up to six person messages per
thread.

- **It sees**: the plan (goal, context, steps with formula, needs, produces,
  particulars, open questions); for the attached step, its spec in plain words,
  examples and who checked them, last run, unconfirmed assumptions, decisions,
  challenges; the last ten main-chat messages as text; for a review thread,
  its challenge; the thread's own messages.
- **It cannot** run, save, build, decide or change anything, and nothing
  passes back. Its reply is number-checked against what it sees, the thread's
  messages and its lookups; unbacked twice: `WITHHELD`.
- It works in every phase.

### 6.5 What it registers

Prompt part `analyst.md`. Tools `ask_decision`, `request_module`. Actions
`choose`, `confirm_assumptions`, `side`. Route: a message with `notice`.
`contribute`: `unconfirmed`, `calls`, `needs_you` for a decision, `notice` and
`decision` on messages, side threads. Expects `decisions` (`[{step, choice,
count}]`), `marks` (`{"min", "max"}`: open notices), `side_threads` (int), `added`
(int: added steps). Events: `you.decision_asked`, `you.decision`,
`you.decision_refused`, `you.assumptions_confirmed`,
`you.assumptions_corrected`, `you.module_requested`, `you.request_refused`,
`you.side_opened`, `you.side_message`, `you.side_reply`, `you.side_withheld`,
`you.side_lookup`.

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

- `use_challenge`: the challenge and its thread become `used`; the harness
  posts, as the person, `USE_THIS` with the step attached, and routes it.
- `dismiss_challenge`: both become `dismissed`. Later passes are told.
- A reply in its thread is a `side` action (6.4); the person's words reach the
  next pass and change nothing now.

```
USE_THIS = "Use the reviewer's suggestion on step {number} {name}: {proposal}"
```

### 7.4 What it registers

Table `challenges (id, ts, pass, step_id, kind, title, concern, proposal,
change, impact, rank, sources, status, thread_id)` and `review_passes (id, ts,
trigger, lookups, kept, dropped)`. Prompt part `analyst.md`. Actions
`use_challenge`, `dismiss_challenge`. `contribute`: `challenges` on steps,
`challenge` on review threads, `review`. Expects `challenges` (`{"min",
"max", "steps"}`). Events: `review.started`, `review.lookup`, `review.kept`,
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
