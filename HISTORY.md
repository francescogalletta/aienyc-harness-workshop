# History: notes made while the harness was built

This file is history, not contract. The contract is `SPEC.md` with
`ARCHITECTURE.md` sections 3 to 5, and section 12 where `SPEC.md` cites it.
Where a note here disagrees with them, they win.

The notes were made while the harness was built, one package at a time: A0 to
A6 for behaviour, B2 for the page, D0 to D6 for the decision history of
`ARCHITECTURE.md` section 12, then fixes from end-to-end and live runs (E2E,
"Live fixes", DG, "Seen with the real model"). They record interfaces and
choices the contract leaves open. Where a note mentions an earlier package, a
later one, or the previous version of the harness, it describes the harness as
it was then. The labels are the ones the build prompts and the code cite. They
used to be section 9 of `ARCHITECTURE.md`; a "section N" below is a section of
`ARCHITECTURE.md`.

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
  every layer; `chips` are required on every message while layer 3 is on, and `proposal` on every thread while layer 4
  is on (until D3a and D4a landed, two flags at its top kept them optional; the flags are gone). The five older sample
  states gained the new core keys.
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
  `review_challenges.json` gained `"proposal": null`.
- **D6 · Replay acts and scenarios.** The scenarios are `branch_that_joins` and `branch_that_dies` (SPEC 6.6 gives them; the question is one the real
  model answers reliably, and `today` is 2026-10-12). `branch` takes a `chip` or a
  `step`, not both. "Newest" is the highest number in the id (a review pass on load makes thread ids unpredictable), `accept` and
  `decline` look at every thread's pending proposal, `close` at open side branches (origin any, kind `side`). The terminal's `/yes`, `/no`,
  `/close` pick the same way, and it prints a pending proposal once with `Type /yes to decide it, or /no.`.
