# Facilitator notes

Two hours, six blocks: setup, then the five layers. You show each layer on the main example (`examples/wedding`) by switching one copy with `workshop at N`, so nothing is built live unless you choose to. Attendees take one of three paths, described in `README.md` here: (a) follow the example, (b) a variation with their own figures, (c) build the layer's code themselves with `workshop start N`.

Commands below are `uv run python -m harness ...` (written `harness ...`) and `uv run python -m workshop ...`. The page is `HARNESS_EXAMPLE=wedding harness ui`. Reload it after each `at N`.

## Before the day

- `git pull`, then `uv run pytest -q` (about 40 seconds).
- `uv run python -m workshop check` (about five minutes). Every line must be ok. A SURPRISE means a test holds only with a later layer present, or the manifest and tree disagree.
- `harness check` (model access works).
- One replay: `harness replay wedding cover_each_payment` (about two minutes). If it passes, the model, the seeded modules and the harness agree.
- Open the page once: `HARNESS_EXAMPLE=wedding harness ui`, then `workshop at 1` to `at 5` and look at each.
- Reset the example's copy so no leftovers show: `rm -rf my/var/examples/wedding`, then start the page once. Put the copy at the step you begin from: `workshop at 0`.

## Run of show

| Block | Min | Principle | Command | New in the page |
| --- | --- | --- | --- | --- |
| 0 Setup | 10 | One core, five layers; the model is one swappable interface | `at 0` | Empty shell |
| 1 The plan | 20 | Agree the plan before any number | `at 1` | The plan as a diagram |
| 2 Build | 25 | Numbers come only from tested code | `at 2` | Build, tests per step |
| 3 Answers | 15 | Every number leads to the step that made it | `at 3` | Answers with evidence |
| 4 Needs you | 25 | Nothing blocks unless the call is yours | `at 4` | Marks, your calls, side threads |
| 5 Review | 15 | Someone challenges the plan | `at 5` | Review |
| Wrap | 10 | `leave`, questions | `leave` | |

### Block 0: setup (10 min)

- Principle: the core owns the conversation, three lanes and the plan state document; layers plug into it. The harness talks to one model interface.
- Command: `workshop at 0`, then `harness --help`: `check`, `events`, `ui`, `replay`.
- Show: `harness check`, then `harness events` lists the record. Open the page: empty, nothing to draw.
- Attendees: all run `harness check`. Path (c) reads `SPEC.md` section 1 and the first ten lines of `ARCHITECTURE.md`.
- Slips: model sign-in, an old `claude` (run `claude update`), `ANTHROPIC_API_KEY` set by mistake.

### Block 1: the plan (20 min)

- Principle: an interview turns a vague goal into a plan everyone agrees on.
- Command: `workshop at 1`; `harness --help` now has `ground`.
- Before: an empty page with no example (`harness ui`). Type "I want to pay for my wedding" and show the first question and the research lines; stop there.
- After: `HARNESS_EXAMPLE=wedding harness ui`. The seeded plan is drawn: steps, inputs, a mark `●` on steps with open questions. Click step 3 ("Work out monthly surplus") to show its origin, then say something is wrong about it and watch the plan redraw.
- Attendees: (a) open the example and click steps. (b) `harness ui` with their goal. (c) `workshop start 1`, the prompt `prompts/step1_plan.md`, `uv run pytest tests/layer1 -q`.
- Slips: the interview takes many minutes (each reply is 20 to 60 seconds). Cut it at the first proposed plan.

### Block 2: build (25 min)

- Principle: the model never adds up; a calculation runs only if its module's tests pass now.
- Command: `workshop at 2`; `harness --help` now has `build`.
- Before (`at 1`): steps show no build state. After: `4 examples · 4/4` on each calculation step.
- Live build: after the page has started once, delete `my/var/examples/wedding/modules/monthly_surplus`, restart the page. Step 3 shows `Stale · rebuild`. Click the build button ("Rebuild 1 step"): an unattended build takes one to four minutes; it makes only that step. Open the step to show examples ("checked by a second pass"), tests and code. The scenario `build_monthly_surplus` does the same in a scratch copy: `harness replay wedding build_monthly_surplus`.
- Attendees: (a) open steps and read the examples. (b) build their own plan; start it early. (c) `start 2`, `prompts/step2_build.md`, `uv run pytest tests/layer2 -q`.
- Slips: this is the longest block. Do the build while you talk. Examples are not confirmed by a person: say so, and show one against a calculator.

### Block 3: answers (15 min)

- Principle: every number in an answer leads to the step that produced it; a number no step produced is never shown.
- Command: `workshop at 3`; `harness --help` now has `ask`.
- Show: paste the first line of `examples/wedding/scenarios/cover_each_payment.json` into the chat. Totals for 150 and 200 guests are 43,000 and 54,500; the 200-guest shortfall at the second payment is 5,250. Click an underlined number: its step is selected, and steps not used fade. Figures that depend on today's date differ from the scenario, which fixes its date.
- Alternative: `no_family_contribution.json`, shortfalls 24,500 (200 guests) and 13,000 (150) at the third payment. At step 2 the same question in the chat gets "Nothing here can answer that yet."
- Attendees: (a) ask the question and change guests. (b) ask about their plan. (c) `prompts/step3_answers.md`, `uv run pytest tests/layer3 -q`.
- Slips: attendees on their own plan who skipped the build have nothing to ask. The example is already built.

### Block 4: needs you (25 min)

- Principle: assumptions run and are marked; only a call that is the person's stops.
- Command: `workshop at 4`.
- Marks: send the first line of `confirm_and_correct.json` (payments, no split said). The answer carries `◌` because it rests on an unsaid split. Click confirm, then say "the second payment is 40% of what remains, and the third 60%": 14,800 and 22,200, run again.
- Your call: the first line of `decide_what_to_update.json`. Step 7 ("Review results and decide updates") asks with options as buttons; pick one and open the step to see the record.
- Side thread: turn on "On the side" and ask what a sinking fund is. It changes nothing. Open one while an answer is running.
- Attendees: (a) as shown. (b) their own plan. (c) `prompts/step4_needs_you.md`, `uv run pytest tests/layer4 -q`.
- Slips: the model chooses what to list as an assumption, so the mark may not appear. Say so and rephrase the question. The moving example has `side_thread_and_new_step` for a new step built in a conversation.

### Block 5: review (15 min)

- Principle: someone other than the analyst looks at how the problem is being thought about.
- Command: `workshop at 5`.
- Show: the reviewer runs when the page opens on the accepted plan (15 to 20 seconds). Steps show `▲` and a count; the **Review** toggle shows one line per challenged step. Open a challenge thread: "use this" makes the analyst answer, "dismiss" closes it. The scenario is `review_the_plan.json`.
- Attendees: (a) as shown. (c) `prompts/step5_review.md`, `uv run pytest tests/layer5 -q`.
- Slips: the reviewer varies between runs. If it raises nothing, send the question from block 4, which starts a second pass.

### Wrap (10 min)

`workshop at 5`, `workshop leave` (it asks; `yes`, `y` or `ok` removes `workshop/`), what they take home, the limitation in `README.md` here.

## Known rough edges

- A model reply takes 20 to 60 seconds through Claude Code. An unattended build takes one to four minutes. A replay of the whole wedding example takes 6 to 7 minutes.
- Marks are only as complete as the analyst's list of assumptions. In live runs it left some in its prose, and wrote a run id ("run 15") in a reply, which held that answer back. A prompt change helped: `confirm_and_correct` marked in 3 of 3 runs after 0 of 4.
- The side assistant did not look up "sinking fund" by itself; it offered to.
- The reviewer's outside lookups depend on Wikipedia being reachable. From the developer's machine it was not (the proxy answered 403): the lookup then finds nothing and the challenge carries no source. The reviewer asked for no lookup in three runs.
- The seeded examples' worked examples were recomputed by an AI agent, not yet by a person.
- A scenario that fails once deserves a second run. One that fails every time points at the harness.
- `my/var/examples/wedding` keeps whatever you did last. Delete it to reset.
- `workshop status` without `--quick` runs every step's tests.
