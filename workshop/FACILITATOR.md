# Facilitator notes

Times are what the room waits, measured against the real model, driving the page in a browser. "n/n" is how often a moment came out as written in rehearsal. `harness ...` is `uv run python -m harness ...`. The slides are in `workshop/slides/`: open the built deck `workshop/slides/deck.html` in a browser (`workshop/slides/README.md` says how to rebuild it).

Every block runs the whole harness, all five layers, and shows what one layer adds. Three rules worth knowing before you start:

- **The reviewer runs on its own.** When the example opens or a plan is accepted, the reviewer (layer 5) looks at the plan in the background; its challenges appear as branches after 10 to 13 s. Leave them until block 5.
- **The example copy keeps your last run** (`my/var/examples/wedding`), the decision history included. Delete it, then start the page, to begin a block clean. The page without an example keeps its interview in `my/var/harness.db` and `my/var/grounding_state.json`: delete both for an empty page.
- **The page uses the real date.** "Due 21 days from today" is true on any day, but the dates and shortfalls that follow from it move by a few hundred with the day. Read them off the screen.

## Minute by minute (110 of 120 minutes, 10 spare)

| Block | Min | Clock | Command | The one thing to show |
| --- | --- | --- | --- | --- |
| 0 Setup | 10 | 0:00 | `harness --help`; `harness check`; `harness ui` | `Setup works`; the empty page |
| 1 The plan | 18 | 0:10 | `harness ui`; then `HARNESS_EXAMPLE=wedding harness ui` | Live interview to a plan you correct; then the seeded plan, step 3's origin |
| 2 Build | 20 | 0:28 | delete `modules/monthly_surplus`; `HARNESS_EXAMPLE=wedding harness ui` | `Stale · rebuild`, click, step 3 built and tested |
| 3 Answers | 17 | 0:48 | the prepared sentence | A short reply with chips; click an underlined number or the 54,500 chip, its step lights up |
| 4 Needs you | 25 | 1:05 | a fresh copy; the 120-guest sentence | Chip, "no fewer than 150", Yes: 43,000 and 18,500 re-run, a trunk node; a dead branch; Confirm; your call |
| 5 Review | 12 | 1:30 | a fresh copy; `HARNESS_EXAMPLE=wedding harness ui` | The reviewer's challenges are branches: Use this joins the trunk, Dismiss is dead |
| Wrap | 8 | 1:42 | none | What they take home |

Spare 10 minutes: 1:50 to 2:00. If behind, cut in this order: the live interview in block 1 (use the seeded plan), the live rebuild in block 2 (use `replay`), the call in block 4, then the dead branch.

## Before the day (paste in order; each line says what you should see)

```
git pull --ff-only && git status -sb                          # "## main...origin/main", no changes
uv run pytest -q                                              # every test passes (several hundred, under a minute)
claude auth status | grep loggedIn; env | grep ANTHROPIC_API_KEY   # "loggedIn": true; the second prints nothing
uv run python -m harness check                                # "Setup works: the model replied and the check was saved as event N." (a few seconds, up to a minute)
uv run python -m harness replay wedding branch_that_joins     # "PASS wedding/branch_that_joins (layer 4) 37 to 46 s" (about 1 minute with the start)
rm -rf my/var/examples/wedding my/var/harness.db* my/var/grounding_state.json my/var/replay
```

Also: Wi-Fi in the room may block Wikipedia and the model; tether a phone as a spare. Close other Claude Code sessions (they share the plan's usage).

## Run of show

### Block 0: setup (10 min)

- Principle: one core owns the conversation, three lanes and the plan state; the model is one swappable interface.
- `harness --help`: `check, events, ui, replay` come with the core; `ground`, `build` and `ask` with layers 1 to 3. `harness check` (a few seconds, up to a minute on a first run or a slow link), then `harness events`: one line, `core.check`.
- Page: `harness ui`. Empty: no plan, nothing to draw yet. Do not type: a message starts the interview, which is block 1. Ctrl+C.
- Attendees: all run `harness check`. Anyone rebuilding a layer reads `SPEC.md` section 1 and section 1 of `ARCHITECTURE.md`.
- If it goes wrong: sign-in (`claude auth status`, `claude update`), `ANTHROPIC_API_KEY` set by mistake (unset it).

### Block 1: the plan (18 min)

- Principle: an interview turns a vague goal into a plan everyone agrees on.
- Delete `my/var/harness.db*` and `my/var/grounding_state.json`, `harness ui`. Empty page. Type `I want to pay for my wedding`. First question after 10 to 14 s (2/2). The research ("reading up on: sinking fund, ...") is printed only in the terminal command `harness ground`, not in the page: say it, do not look for it.
- Click the link under the question, **Propose the plan now**: a 4 to 5 step plan appears after 28 to 46 s (2/2). Click step 2 and type `This should also include 3,000 for the honeymoon.` The plan redraws after 18 to 26 s (2/2): a new input "Honeymoon cost", and "The plan is revised: changed steps ...". Do not accept; Ctrl+C. During each wait: say what the interview, the proposal and the correction are for.
- Then: `HARNESS_EXAMPLE=wedding harness ui`. Seven steps; `●` with a number is an open question, `✎` proposed by the assistant, `❝` the person's words; step 4 is a figure from the person, step 7 (dashed) their call. Click step 3: among other things the pop-up shows its formula, particulars with origins and the open question. The trunk on the right has one node, "Plan accepted"; say it is where the history of decisions starts.
- Attendees: (a) open the example and click steps. (b) `harness ui` with their goal. Rebuilding the layer: `prompts/step1_plan.md`, `uv run pytest tests/layer1 -q`.
- If it goes wrong: a slow interview, press Propose the plan now after the first question.

### Block 2: build (20 min)

- Principle: the model never adds up; a calculation runs only if its module's tests pass now.
- On the example page: `All 6 built` and on each calculation step `N examples · P/P`: 4/4, 3/3, 4/4, 5/5, 5/5 (the counts differ per step; steps 4 and 7 are the person's, no tag). Step 8, "not in the plan", is the step the seed added in a conversation; say so.
- Live: Ctrl+C, `rm -rf my/var/examples/wedding/modules/monthly_surplus`, restart (the copy must have run once, as it has after block 1). Step 3 shows `Stale · rebuild`; the button says **Rebuild 1 step**. Click: it says "Building" for 33 to 35 s (3/3), not minutes, and makes only step 3, which then reads `4 examples · 5/5` (counts differ per build). Talk during the wait: the code writer never sees the examples; a second pass checks them.
- Open step 3: Examples marked "checked by a second pass", "4 tests, all passing", Code and tests. Take the first example, read its inputs, work it out on a calculator in front of them. Examples differ per build; say that nobody has confirmed them.
- Attendees: (a) open steps, read examples. (b) build their plan early: a whole 4-step plan took 200 s (1/1), about 50 s a step. Rebuilding the layer: `prompts/step2_build.md`, `uv run pytest tests/layer2 -q`.
- If it goes wrong: `harness replay wedding build_monthly_surplus` (20 to 28 s, PASS) does the same in a scratch copy.

### Block 3: answers (17 min)

- Principle: every number in an answer leads to the step that produced it; a number no step produced is never shown.
- Paste this into the chat (spending of 8,500, so there is a shortfall on any day):

  `Can I cover each wedding payment? The wedding is on 12 June 2027 and I expect between 150 and 200 guests, at 230 each for dinner. Costs that do not depend on guests: 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due 21 days from today, and it counts towards the total. The second is half of what remains, due 30 days before the wedding, and the third is the other half, due 14 days before. I take home 10,000 a month and spend about 8,500 a month. I have 10,000 saved for the wedding. My families will give 20,000 on 29 May 2027.`

- Wait 30 to 50 s. The reply is short: "Not fully, in either case", with the shortfalls in the sentence. On 12 October: 150 guests, payment 2 short by 4,000 and payment 3 by 2,500; 200 guests, 9,750 and 14,000. Under it are chips: the totals 43,000 and 54,500 and the surplus 1,500 (results), the values it used and what it assumed (a `◌` mark on it is block 4). Say what the analyst did: it ran the modules, and the number check holds back anything no step made.
- Click an underlined number (9,750): step 5 is selected and its pop-up opens; click the chip `Estimate total wedding cost 54,500` and step 1 is selected (2/2). Steps not used fade. Then type `What if my families give nothing?`: 17 to 60 s, payment 3 now short by 22,500 and 34,000.
- Attendees: (a) ask it, change the guest range. (b) ask about their plan, built first. Rebuilding the layer: `prompts/step3_answers.md`, `uv run pytest tests/layer3 -q`.
- If it goes wrong: `replay wedding cover_each_payment` (30 to 35 s, PASS; fixes its date so 5,250 shows).

### Block 4: needs you (25 min)

- Principle: assumptions run and are marked; only a call that is the person's stops; a branch joins the trunk only with your yes.
- Restart the page on a fresh copy (`rm -rf my/var/examples/wedding`). Point at the right panel: the trunk, with "Plan accepted" at the top, is only confirmed decisions; below it the conversation. The reviewer's branches come back too; leave them for block 5. Paste (120 guests, so a branch can change it):

  `Can I cover the three payments if we invite 120 guests? The wedding is on 12 June 2027. Dinner is 230 a guest, plus 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due 21 days from today, and it counts toward the total. The second and third payments are each half of what remains, due 30 and 14 days before the wedding.`

- After 30 to 35 s (3/3) a two-sentence reply: with 120 guests the fund covers all three payments. Chips under it, step 1 reading 36,100, and a dashed `◌ This rests on 2 things you haven't confirmed` with **Confirm** and **Change it** (the two assumptions differ per run). Say: less prose, more objects.
- The join. Hover the chip `Guest count 120` (under "Rests on"): three small icons, the middle one is "challenge or correct". Click it and type `We will get no fewer than 150 guests.` A branch opens at the top of the panel. After 4 to 6 s (4/4) it proposes `Change guest count to 150?`: `120 → 150`, `Re-runs 1 2 5`, `Further on 6 7`. On the plan the Guest count pill turns orange, steps 1, 2 and 5 are outlined dashed, 6 and 7 are faded. Say: anything that touches your figures needs your yes. Click **Yes, change it**.
- It takes 1.5 to 4.5 s (3/3): "Decided on a branch: Guest count is 150 (was 120). Run again: steps 1, 2 and 5." Step 1 reads 43,000, steps 1, 2 and 5 carry `re-ran`, the pill reads 150, the trunk has a node `Guest count: 150 (was 120)` with the chips `43,000 (was 36,100)`, `18,500 (was 15,050)` and `22,000 (was 28,900)`. In the old reply the figures that moved are struck through; 4,000 and the dates are not. Say: the join re-runs through the same test gate, with no model call (`harness events` shows a `calc.run` for each step).
- The branch that dies. Click step 5, then **New branch** (bottom right of the box), type `What is a sinking fund?`. It answers in 5 to 6 s (2/2) from the plan's glossary, now with a sourced definition, and offers to look up more; it does not. Click **Close branch**: the branch is dimmed, `no change`; the trunk and the plan are as they were. Say: a branch with no consequence stays dead.
- Confirm. Scroll down, click **Confirm** (instant): a trunk node `Confirmed: ... and 1 more`. Say: the trunk is only confirmed decisions. Spare, 15 s: instead of Confirm click **Change it** and type `On second thought, the second payment is 40% of what remains, and the third is the other 60%.` for a node `Corrected: ...`, 14,800 and 22,200 (2/2).
- Your call. Type `Now help me decide what to update first.` After 10 s (1/1) step 7 asks with four buttons, the words differ each time; pick one: a trunk node appears at once and step 7 reads "Decided", the reply follows in 5 s. The node shows the start of the question, not your choice; open step 7 for "You chose: ...".
- Attendees: (a) as shown; change 150 to 180 from a branch. (b) their plan. Rebuilding the layer: `prompts/step4_needs_you.md`, `uv run pytest tests/layer4 -q`. Exercise 4.4 is the join.
- If it goes wrong: no proposal after 15 s, say it plainly again (`Change the guest count to 150.`); the side assistant may ask a question first. No buttons after 90 s: move on; `harness replay wedding decide_what_to_update` plays the call in a scratch copy.

### Block 5: review (12 min)

- Principle: someone other than the analyst looks at how the problem is being thought about.
- Restart the page on a fresh copy (`rm -rf my/var/examples/wedding`) so the room sees the reviewer start. It runs on open: `Review · 2` or `Review · 3` after 10 to 13 s (3/3). Each challenge is a branch off the trunk, tagged `challenge` or `question`; steps carry `▲`. Click one to open it: **Use this**, **Dismiss**, a reply box. A question has no Use this: pick another.
- Click **Use this** on a challenge: the branch joins the trunk as `Reviewer's suggestion used on step 5` and the analyst replies in 4 to 6 s (2/2; it asks for inputs not saved yet). Open another and click **Dismiss**: instant, the branch is dimmed, `dismissed`. Say: the reviewer's challenges are branches; Use this joins, Dismiss is dead.
- Attendees: (a) as shown. Rebuilding the layer: `prompts/step5_review.md`, `uv run pytest tests/layer5 -q`.
- If it goes wrong: nothing raised, send the block 4 sentence for a second pass. Outside lookups need Wikipedia; challenges then carry no source.

### Wrap (8 min)

What they take home: `harness/` and their `my/`. `workshop/` is teaching material; deleting it by hand leaves a harness whose tests pass. The limitation in `README.md` here.

## Known rough edges

- Timings measured: check a few seconds (up to a minute on a first run), short reply 10 to 15 s, a full answer 30 to 50 s, a branch's proposal 4 to 6.5 s, the join 1.5 to 4.6 s, rebuild of one step 35 s, a whole 4-step build 200 s, reviewer 10 to 13 s, `replay` per scenario 4 to 88 s (all eight in a row: 307 s, 8 of 8 passed).
- A proposal needs a value the person wrote in the branch. A range ("between 150 and 200") is ambiguous: open the branch from one value (use the 120-guest sentence). One proposal per reply; the side assistant sometimes asks first.
- A join re-runs only the steps the value reaches in the last answer (1, 2 and 5 here). Steps 6 and 7 are shown as further on and stay as they were until asked. A re-run the gate refuses (a module changed under it, exercise 4.4) still saves the value and records the node; the node lists the steps that could not run again.
- Only your own buttons make trunk nodes (Confirm, Change it, a choice, Use this, Yes). A value you type in the main chat is conversation, not a decision: the 40/60 line typed after Confirm changes the answer and adds no node.
- A figure in an old reply is struck through only when its re-run gave a different value; a result chip is struck when its run re-ran, even if one of its several values did not move. After a later answer, steps it did not use fade and show examples instead of values until asked again.
- The glossary of the wedding example now carries sourced definitions for sinking fund, cash flow forecast and budget (from `reference/terms.json`); savings goal, net income and gross income have no saved source and stay the assistant's proposal.
- Marks are only as complete as the analyst's list; the mark appeared 4/4 here. The side assistant offers a lookup, it does not make one.
- The seeded examples' worked examples were recomputed by an AI agent, not by a person.
- Two layer 4 safeguards can re-do a reply before you see it (a call left in prose; a run input you never gave and no assumption lists). They add 5 to 15 s and show as a longer wait, nothing else. With "21 days from today" the first payment no longer shows up as an assumption.
- If the folder of a module is deleted, step 3 reads `Stale · rebuild` (its reason is "its folder is missing"); changed code reads "its files changed". On a copy that has never run, a deleted folder reads "Not built".
- A scenario that fails once deserves a second run; `decide_what_to_update` failed twice in three on an earlier day (no call raised) and passed in the last two full runs.
