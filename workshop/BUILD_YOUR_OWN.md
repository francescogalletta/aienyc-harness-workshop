# Build your own harness

This guide is for someone who wants a harness like ours in their own domain, built from an empty folder with the coding agent of their choice. It follows the five principles of the session, in order. It does not follow our file layout or specific implementation details. 

## Before principle 1: the skeleton

Every principle below needs three things to stand on. Keep them small.

- **One model interface.** One function that takes a system prompt, messages and tools, and returns text and tool calls. Only this part knows the provider. Add a scripted model behind the same interface so tests run offline.
- **One place to record everything.** A local database with an append-only event log: every message, model reply, run and decision.
- **One state the screen draws from.** A single JSON object rebuilt from the database. The terminal (or a page, later) reads only this. Each principle adds keys to it.

A terminal is enough. You do not need a UI to follow this guide.

How ours does it:

- `harness/model/interface.py` (the interface) and `harness/model/scripted.py` (the offline model).
- `harness/schema.sql` and `harness/db.py` (the event log and its triggers).
- `ARCHITECTURE.md` section 1 and section 3 (the plan state document).

```
In an empty folder, start a small harness for <your domain>.
Use one language and its standard library where you can.
Build three things:
1. A model interface: complete(system, messages, tools) returning text and
   tool calls. One real provider, and a scripted provider for tests.
2. A local SQLite database with an append-only events table. Any update or
   delete on it must fail.
3. A function state() that rebuilds one JSON object from the database.
   A terminal command prints it. Nothing else reads the database for display.
Write tests that run offline with the scripted model, including one that
proves an event cannot be changed once written.
```

You know it works when the tests pass with no network and a second `state()` call returns the same object.

## 1 Shared Domain: Agree the plan before any number.

### The rule

Agree the plan before any number. What is obvious to you is not what the model learned. Start from the goal and work backwards, together. Without it you get one shot, a vague goal, and your reality assumed to be everyone's.

### What to build

- An interview that asks one question per message and ends in a written plan: a goal, the person's particulars, named inputs and ordered steps.
- An origin on every item of the plan: the person's own words (a quote), a looked-up source, or proposed by the model.
- A validator, in code, that rejects a plan where a quote is not in the person's messages, a step needs something that does not exist, or a calculation has no formula.
- An explicit accept. Before it, no step runs and no number is computed.
- A list of open questions the plan keeps, rather than guesses.

### How ours does it

- `harness/grounding/brief.py`: the plan's shape and `validate_brief`.
- `harness/grounding/interview.py` and the prompts `interviewer.md`, `planner.md`.
- `SPEC.md` section 3.1 (the brief) and 3.2 (the interview); `ARCHITECTURE.md` 3.1 for `Origin`.
- `examples/wedding/brief/domain_brief.json`: an accepted plan.

### A prompt for your coding agent

```
Add a planning interview to the harness for <your domain>.
Invariant: no number is computed until the person accepts a plan.
The interview asks one question per message, then proposes a plan as JSON:
goal, particulars, inputs, steps (id, name, kind, formula, needs, produces),
open questions. Every item has an origin: {"kind": "person", "quote"},
{"kind": "looked_up", "source"} or {"kind": "proposed"}.
Write validate_plan(plan, person_messages) that returns what is wrong:
a quote not found in the person's messages, a need that names no input or
earlier step, a calculation without a formula. Errors go back to the model.
Only an "accept" action marks the plan accepted. Add it to state().
Tests: a plan with an invented quote is rejected; a run before accept fails.
```

You know it works when a quote the person never typed is refused, and the plan states each assumption as `proposed` rather than as fact.

## 2 Consistency: Numbers come only from tested code.

The shared plan says which parts never change.

### The rule

Numbers come only from tested code. Write the calculation once and run it the same way every time. The model picks the tool. It never does the arithmetic. Without it: arithmetic in the model's head, new code for every question, and the same question giving a different answer.

### What to build

- One module per calculation step, written from the step's spec, each with its own tests and worked examples.
- Worked examples written separately from the code, and checked by a second model pass that does not see the first answers. The code writer never sees the examples.
- A gate in front of every run: the module is registered, its files are unchanged, its step has not changed in the plan, and its tests pass, every time.
- A fingerprint of each step in the plan. When the step changes, its module is stale and the gate refuses it until it is built again.
- A build that runs unattended. A step it cannot build is marked not built, with the reason.

### How ours does it

- `harness/calc/gate.py`: `call` runs the tests before every run.
- `harness/calc/builder.py` and `harness/calc/checker.py`: the unattended build and the second pass.
- `examples/wedding/modules/monthly_surplus/`: `spec.json`, `golden.json`, `module.py`, `tests.py`.
- `SPEC.md` sections 4.3 to 4.5.

### A prompt for your coding agent

```
Add tested calculations to the harness for <your domain>.
Invariant: a number is computed only by a registered module whose tests
pass at the moment it runs.
For each calculation step of the accepted plan, build a folder: spec.json,
module.py, tests.py and golden.json (worked examples).
One model writes the spec and examples; a second model call answers the
examples blind, and only examples both agree on are kept. The code writer
sees the spec and is told only which example failed.
Write gate.call(module, inputs) that refuses an unregistered module, changed
files, a step whose plan fingerprint changed, or failing tests. Record every
run and every refusal as an event.
Tests: edit a module file and the gate refuses; change the step in the plan
and the module is stale; the same inputs give the same output twice.
```

You know it works when you cannot get a number out of the harness without a test run just before it in the event log.

## 3 Evidence: Every number can be followed back.

Tested code (and everything else) leaves a trail we can follow.

### The rule

Every number can be followed back. Not all information is the same: a remark in chat is an interpretation, the agent's memory is an assumption. Keep the trail, and show the receipts for what matters, not everything. Without it: everything treated as fact, a rough guess used as the truth, and "I ran the numbers" with no receipts.

### What to build

- A number check in code: every number in a reply, and every value passed to code or saved, must appear in a known source (a run's output, a saved input, the plan, the person's words, today's date).
- A reply with an unbacked number goes back to the model once. The second time it is held back, and the person is told why.
- A trace from each figure in a reply to the run that produced it, and from that run to its step.
- Short replies, with the values used and the assumptions made shown as separate items under the reply.

### How ours does it

- `harness/calc/provenance.py`: `unbacked` (the number check) and `trace`.
- `harness/answers/agent.py` (the analyst turn) and `harness/answers/figures.py` (figures to steps).
- `SPEC.md` section 1 rule 1, and sections 5.1 and 5.2.

### A prompt for your coding agent

```
Add answers with evidence to the harness for <your domain>.
Invariant: every number the person reads came from a run, a saved input,
the plan, the person's own words or today's date.
Write unbacked(text, sources) that lists each number or date in text that
no source holds. Small whole numbers may be exempt; say which.
The answering agent runs modules through the gate. Check its reply with
unbacked: if anything is unbacked, send it back once; a second time, hold
the reply back and post a fixed notice naming the numbers.
For each figure shown, record the run and step that produced it, and add
that link to state().
Tests: a reply with an invented figure is held back on the second try; a
figure that a run produced leads to that run's step.
```

You know it works when you can point at any number on the screen and name the run, the inputs and the step behind it.

## 4 Accountability: Ask only where a person must decide.

The evidence is what you decide with.

### The rule

Ask only where a person must decide. Agents face no real-world consequences. You do. Reduce ambiguity, do not remove it: the judgement calls stay with the person, and the harness makes them easy to make. Few gates, high signal. Without it: "the stochastic machine said it was fine", or approving every calculation.

### What to build

- Three cases, kept apart. Two plausible readings that conflict: stop and ask. An assumption: run it, and mark it. Arithmetic: never ask.
- Assumptions stored with each run. A result that rests on an unconfirmed one carries a visible mark until the person confirms or changes it.
- A check in code that a value passed to a run is the person's, or else listed as an assumption. An unlisted one is refused the first time.
- A decision tool for calls that are the person's: a plain question, two to four options, an optional suggestion with a reason. Only this waits.
- A record of each decision. Nothing changes a figure of the person's or the plan's shape without their yes.

### How ours does it

- `harness/needs_you/marks.py`: run and mark, confirm and correct.
- `harness/needs_you/calls.py`: `ask_decision` and how an answer is read.
- `harness/needs_you/side.py` and `join.py`: a proposed change waits for the person's yes.
- `SPEC.md` sections 1 rules 6 and 7, 6.1, 6.2 and 6.6.

### A prompt for your coding agent

```
Add "needs you" to the harness for <your domain>.
Invariant: only a call that is the person's waits for them, and no figure
of theirs changes without their yes.
Store each run's assumptions. A result resting on an unconfirmed one is
marked in state() until the person confirms or corrects it.
Before a run, check each input value: it is the person's (their words, a
saved input, a confirmed assumption, an earlier result) or it must be listed
as an assumption. Refuse the first run with an unlisted one.
Add ask_decision(question, options, suggested, why): two to four options,
numbers checked as before. Record every decision.
Tests: an unlisted value is refused; confirming clears the mark; arithmetic
never triggers a question; a proposed change to a figure waits for yes.
```

You know it works when a session asks you a handful of real questions, and every assumption it made is marked rather than hidden.

## 5 Verification: A reviewer challenges the plan.

Each challenge is yours to use or dismiss.

### The rule

A reviewer challenges the plan. Experts do not check every cell. They know where it usually goes wrong, and roughly what the answer should look like. The model has everyone's experience, averaged; its "probably fine" may look nothing like yours. Without it: checking everything line by line, or checking nothing.

### What to build

- A separate reviewer with its own prompt. It reads the plan, the specs, the assumptions, the decisions and the last runs. It does not read the code or answer the person.
- A report tool with a fixed shape: the step, a short title, the concern, a proposal, and an impact of high, medium or low.
- Checks in code on each challenge: a real step, the number check on its text, no repeat of one already used or dismissed. Keep only the strongest few.
- Each kept challenge goes to the person, who uses it (it becomes a recorded decision) or dismisses it (later passes are told).
- Passes run on their own after the plan is accepted or changed, and block nothing.

### How ours does it

- `harness/review/reviewer.py`: one pass, its sections and `check`.
- `harness/review/reviewer.md`: what the reviewer looks for and how it ranks.
- `SPEC.md` section 7.

### A prompt for your coding agent

```
Add a reviewer to the harness for <your domain>.
Invariant: the reviewer changes nothing by itself; every challenge is the
person's to use or dismiss.
Run a review pass after the plan is accepted or changed, without blocking.
Give the reviewer the plan, specs (never code), assumptions with status,
decisions and the last runs. It reports challenges as JSON: step, title,
concern, proposal, impact (high, medium, low).
In code, drop a challenge on an unknown step, with unbacked numbers, or
repeating an open, used or dismissed one. Keep at most three, high first.
"Use" records a decision; "dismiss" closes it and later passes are told.
Tests: an invented figure in a challenge is dropped; a dismissed challenge
is not raised again; nothing in the plan changes until the person uses one.
```

You know it works when the reviewer raises the question an expert in your domain would ask first, and nothing moves until you say so.

## What next

- `SPEC.md` and `ARCHITECTURE.md` are the full contract of our version: the same five principles, with every rule, table and template written out.
- `examples/wedding/` is a finished plan to compare against: its brief, its built modules, and scenarios you can replay with `uv run python -m harness replay wedding`.
- Run your own harness on one real question from your domain. Where it guessed, go back to principle 1.
