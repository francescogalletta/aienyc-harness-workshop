# Facilitator notes

Rehearsed block by block on 11 October 2026 against the real model, driving the page in a browser. Times are what the room waits. "n/n" is how often a moment came out as written. `harness ...` is `uv run python -m harness ...`; `workshop ...` is `uv run python -m workshop ...`. Slides are elsewhere.

Three rules that cost a rehearsal each:

- **The page reads the step when it starts.** After `workshop at N`, stop the page (Ctrl+C) and start it again. A reload shows the old step.
- **The example copy keeps your last run** (`my/var/examples/wedding`). Delete it, then start the page, to begin a block clean. The page without an example keeps its interview in `my/var/harness.db` and `my/var/grounding_state.json`: delete both for an empty page.
- **The page uses the real date.** Prepared sentences here use absolute dates, so figures that depend on today (shortfalls) can differ by a few hundred if the day is not 12 October 2026. Read them off the screen.

## Minute by minute (110 of 120 minutes, 10 spare)

| Block | Min | Clock | Command | The one thing to show |
| --- | --- | --- | --- | --- |
| 0 Setup | 10 | 0:00 | `workshop at 0`; `harness check`; `HARNESS_DB=my/var/shell.db harness ui` | Empty page; a message gets "Nothing here can answer that yet." |
| 1 The plan | 18 | 0:10 | `workshop at 1`; `harness ui`; then `HARNESS_EXAMPLE=wedding harness ui` | Live interview to a plan you correct; then the seeded plan, step 3's origin |
| 2 Build | 20 | 0:28 | `workshop at 2`; delete `modules/monthly_surplus`; `HARNESS_EXAMPLE=wedding harness ui` | `Stale · rebuild`, click, step 3 built and tested |
| 3 Answers | 17 | 0:48 | `workshop at 3`; the prepared sentence | Every number underlined; click 54,500, its step lights up |
| 4 Needs you | 25 | 1:05 | `workshop at 4`; prepared sentences | `◌` mark, Confirm, 40/60 (14,800 and 22,200); your call; a side thread |
| 5 Review | 12 | 1:30 | `workshop at 5` | Reviewer finds 2 or 3 challenges in 15 s; Use this, Dismiss |
| Wrap | 8 | 1:42 | `workshop at 5` | What they take home; `leave` only in a throwaway clone |

Spare 10 minutes: 1:50 to 2:00. If behind, cut in this order: the live interview in block 1 (use the seeded plan), the live rebuild in block 2 (use `replay`), the side thread in block 4.

## Before the day (paste in order; each line says what you should see)

```
git pull --ff-only && git status -sb                          # "## main...origin/main", no changes
uv run pytest -q                                              # every test passes ("535 passed" at rehearsal, about 70 s)
uv run python -m workshop check                               # last line "Nothing surprised." (5 minutes; start it, then do the rest in another terminal)
claude auth status | grep loggedIn; env | grep ANTHROPIC_API_KEY   # "loggedIn": true; the second prints nothing
uv run python -m harness check                                # "Setup works: the model replied and the check was saved as event N." (4 s)
uv run python -m harness replay wedding cover_each_payment    # "PASS wedding/cover_each_payment (layer 3) 51 s" (about 1 minute)
workshop/fallback/open.sh 3-answers                           # "Kept run 3-answers at layer 3: http://127.0.0.1:8765/": open it, see 43,000 in step 1, Ctrl+C
rm -rf my/var/examples/wedding my/var/harness.db* my/var/grounding_state.json my/var/fallback my/var/replay
uv run python -m workshop at 0                                # "This copy now runs as the harness at step 0"
```

Also: Wi-Fi in the room may block Wikipedia and the model; tether a phone as a spare. Close other Claude Code sessions (they share the plan's usage).

## Run of show

### Block 0: setup (10 min)

- Principle: one core owns the conversation, three lanes and the plan state; the model is one swappable interface.
- `workshop at 0`, `harness --help`: `check, events, ui, replay`. `harness check` (3 to 5 s here; up to a minute on a slow link), then `harness events`: one line, `core.check`.
- Page: `HARNESS_DB=my/var/shell.db harness ui`. Empty. Type "I want to pay for my wedding": the reply is "Nothing here can answer that yet." at once (1/1). Say: the core takes the message and no layer wants it. Use the throwaway database so block 1's empty page stays empty.
- Attendees: all run `harness check`. Path (c) reads `SPEC.md` section 1 and the first ten lines of `ARCHITECTURE.md`.
- If it goes wrong: sign-in (`claude auth status`, `claude update`), `ANTHROPIC_API_KEY` set by mistake (unset it). Fallback: `workshop/fallback/open.sh 0-setup`.

### Block 1: the plan (18 min)

- Principle: an interview turns a vague goal into a plan everyone agrees on.
- `workshop at 1`; `harness --help` now has `ground`.
- Before: Ctrl+C the old page, delete `my/var/harness.db*` and `my/var/grounding_state.json`, `harness ui`. Empty page. Type `I want to pay for my wedding`. First question after 10 to 14 s (2/2). The research ("reading up on: sinking fund, ...") is printed only in the terminal command `harness ground`, not in the page: say it, do not look for it.
- Click the link under the question, **Propose the plan now**: a 4 to 5 step plan appears after 28 to 46 s (2/2). Click step 2 and type `This should also include 3,000 for the honeymoon.` The plan redraws after 18 to 26 s (2/2): a new input "Honeymoon cost", and "The plan is revised: changed steps ...". Do not accept; Ctrl+C. During each wait: say what the interview, the proposal and the correction are for.
- After: `HARNESS_EXAMPLE=wedding harness ui`. Seven steps; `●` with a number is an open question, `✎` proposed by the assistant, `❝` the person's words; step 4 is a figure from the person, step 7 (dashed) their call. Click step 3: the pop-up shows its formula, particulars with origins and the open question.
- Saying something is wrong works only while a plan is proposed. On the seeded, accepted plan the reply is "Nothing here can answer that yet." (1/1): do not try it there.
- Attendees: (a) open the example and click steps. (b) `harness ui` with their goal. (c) `workshop start 1`, prompt `prompts/step1_plan.md`, `uv run pytest tests/layer1 -q`.
- If it goes wrong: a slow interview, press Propose the plan now after the first question. No model: `workshop/fallback/open.sh 1-plan` (the seeded plan).

### Block 2: build (20 min)

- Principle: the model never adds up; a calculation runs only if its module's tests pass now.
- `workshop at 2`, `harness --help` has `build`. Before: the page at step 1 shows no build state. After (restart the page): `All 6 built` and on each calculation step `N examples · P/P`: 4/4, 3/3, 4/4, 5/5, 5/5 (the counts differ per step; steps 4 and 7 are the person's, no tag). Step 8, "not in the plan", is the step the seed added in a conversation; say so.
- Live: Ctrl+C, `rm -rf my/var/examples/wedding/modules/monthly_surplus`, restart. Step 3 shows `Stale · rebuild`; the button says **Rebuild 1 step**. Click: it says "Building" for 25 to 35 s (2/2), not minutes, and makes only step 3, which then reads 4 or 5 examples, 4/4. Talk during the wait: the code writer never sees the examples; a second pass checks them.
- Open step 3: Examples marked "checked by a second pass", "4 tests, all passing", Code and tests. Take the first example, read its inputs, work it out on a calculator in front of them. Examples differ per build; say that nobody has confirmed them.
- Attendees: (a) open steps, read examples. (b) build their plan early: a whole 4-step plan took 200 s (1/1), about 50 s a step. (c) `workshop start 2`, `prompts/step2_build.md`, `uv run pytest tests/layer2 -q`.
- If it goes wrong: `harness replay wedding build_monthly_surplus` (28 s, PASS) does the same in a scratch copy. No model: `workshop/fallback/open.sh 2-build`.

### Block 3: answers (17 min)

- Principle: every number in an answer leads to the step that produced it; a number no step produced is never shown.
- `workshop at 3`, `harness --help` has `ask`; restart the page. Before: at step 2 the same sentence gets "Nothing here can answer that yet." Paste this into the chat (it is `cover_each_payment` with absolute dates and spending of 8,500, so there is a shortfall on any day):

  `Can I cover each wedding payment? The wedding is on 12 June 2027 and I expect between 150 and 200 guests, at 230 each for dinner. Costs that do not depend on guests: 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due on 1 November 2026, and it counts towards the total. The second is half of what remains, due 30 days before the wedding, and the third is the other half, due 14 days before. I take home 10,000 a month and spend about 8,500 a month. I have 10,000 saved for the wedding. My families will give 20,000 on 29 May 2027.`

- Wait 53 to 68 s (4/4). Say what the analyst is doing: it runs the modules, the number check holds back anything no step made. Answer: totals 43,000 and 54,500, payments 18,500 and 24,250, surplus 1,500; on 12 October the 200-guest shortfall at payment 2 is 9,750 (4/4) and 4,000 for 150 guests.
- Click an underlined number (54,500): step 1 is selected, its pop-up shows "In the last answer ... Came out 54,500", steps not used fade. Then type `What if my families give nothing?`: 40 to 60 s (1/1), payment 3 now short by 22,500 and 34,000.
- Attendees: (a) ask it, change the guest range. (b) ask about their plan, built first. (c) `prompts/step3_answers.md`, `uv run pytest tests/layer3 -q`.
- If it goes wrong: `replay wedding cover_each_payment` (51 s, PASS; fixes its date so 5,250 shows). No model: `open.sh 3-answers` (underlines, 5,250); the before is `open.sh 3-answers 8765 2`.

### Block 4: needs you (25 min)

- Principle: assumptions run and are marked; only a call that is the person's stops.
- `workshop at 4`, restart the page on a fresh copy (`rm -rf my/var/examples/wedding`).
- Marks: paste `What are my three wedding payments? The wedding is on 12 June 2027. I expect 150 guests at 230 each for dinner, plus 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due on 1 November 2026. The second and third are shares of what remains, due 30 days and 14 days before the wedding.` After 22 to 28 s (4/4) the answer has `◌ This rests on ...` with the 50/50 split, sometimes also "the 6,000 counts toward the total". Click **Confirm** (instant). Then type `On second thought, the second payment is 40% of what remains, and the third is the other 60%.`: 12 to 13 s (2/2), 14,800 and 22,200. After Confirm there is no Change it button; just type.
- Your call: fresh copy, restart, paste the block 3 sentence with ` Once you have the results, help me decide what to update first.` added. After 54 to 65 s (3/3) step 7 asks with four buttons; pick one; step 7 reads "Decided"; open it: "You chose: ...".
- Side thread: ask any question, then at once click **On the side** and type `What is a sinking fund?`. The side answer arrives while the main one runs; nothing changes. It answers from the plan's glossary and offers to look it up; it did not look it up (1/1).
- Attendees: (a) as shown. (b) their plan. (c) `prompts/step4_needs_you.md`, `uv run pytest tests/layer4 -q`.
- If it goes wrong: no `◌`, say the model chose no assumption, rephrase (0 misses in 4). No buttons after 90 s: `open.sh 4-call` (replay `decide_what_to_update` passed 1 of 3, so do not rely on it). No model: `open.sh 4-marks` shows `◌` open; `open.sh 4-marks-corrected` the 14,800 and 22,200.

### Block 5: review (12 min)

- Principle: someone other than the analyst looks at how the problem is being thought about.
- `workshop at 5`, restart the page. The reviewer runs on open: **Reviewing**, then `Review · 2` after 15 s (1/1; the replay raised 3). Steps carry `▲`. Click **Review**: one line per challenge with **Use this**, **Dismiss**, **Open thread**.
- Click Use this on one: the analyst replies in about 10 s (it asks for inputs not saved yet). Dismiss the other: the line closes. Threads show "used" and "dismissed".
- Attendees: (a) as shown. (c) `prompts/step5_review.md`, `uv run pytest tests/layer5 -q`.
- If it goes wrong: nothing raised, send the block 4 marks sentence for a second pass. Outside lookups need Wikipedia; challenges then carry no source. No model: `open.sh 5-review`, before: `open.sh 5-review 8765 4`.

### Wrap (8 min)

`workshop at 5`. Do not run `workshop leave` in this copy: it deletes `workshop/`, this file included. Show it in a throwaway clone (it asks; `yes`; verified). What they take home, the limitation in `README.md` here.

## Fallbacks

`workshop/fallback/open.sh BLOCK [PORT] [LAYER]` opens a kept run in the page with the model off (`HARNESS_MODEL_PROVIDER=scripted`, reviewer off), on a copy under `my/var/fallback/`. Blocks: `0-setup 1-plan 2-build 3-answers 4-marks 4-marks-corrected 4-call 5-review`. Details and how to remake them: `workshop/fallback/README.md`.

## Known rough edges

- Timings measured: check 3 s, short reply 10 to 15 s, a full answer 50 to 70 s, rebuild of one step 25 to 35 s, a whole 4-step build 200 s, reviewer 15 s, `replay` per scenario 28 to 90 s.
- Marks are only as complete as the analyst's list; the mark appeared 4/4 here. The side assistant offers a lookup, it does not make one.
- The seeded examples' worked examples were recomputed by an AI agent, not by a person.
- A scenario that fails once deserves a second run; `decide_what_to_update` failed twice in three (no call raised).
- `workshop status` without `--quick` runs every step's tests.
