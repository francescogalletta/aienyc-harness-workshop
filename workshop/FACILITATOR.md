# Speaker notes

The root [`README.md`](../README.md) is the workshop: every step, prepared sentence and expected result is there, one section per principle. Drive the page from it. These notes hold only what a speaker needs beyond it. Times are what the room waits, measured against the real model in rehearsal; "n/n" is how often a moment came out as written. `harness ...` is `uv run python -m harness ...`. The slides are `workshop/slides/deck.html` (`workshop/slides/README.md` says how to rebuild them).

Four rules worth knowing:

- **The reviewer runs on its own.** When the example opens or a plan is accepted, the reviewer looks at the plan in the background; its challenges appear as branches after 10 to 13 s. Leave them until principle 5.
- **The example copy keeps your last run** (`my/var/examples/wedding`), the decision history included. Reset (README, "Open the example") to begin a principle clean. The page without an example keeps its interview in `my/var/harness.db` and `my/var/grounding_state.json`: delete both for an empty page.
- **Spotlight one principle with the legend.** On the example, everything but Evidence is on the page when it opens. Click the principle's legend entry and keep it while you talk; click again or press Escape to let go.
- **The page uses the real date.** "Due 21 days from today" is true on any day, but the dates and shortfalls that follow move by a few hundred with the day. Read them off the screen.

## Before the day (paste in order; each line says what you should see)

```
git pull --ff-only && git status -sb                          # "## main...origin/main", no changes
uv run pytest -q                                              # every test passes (about 700, about a minute)
claude auth status | grep loggedIn; env | grep ANTHROPIC_API_KEY   # "loggedIn": true; the second prints nothing
uv run python -m harness check                                # "Setup works: the model replied and the check was saved as event N." (a few seconds, up to a minute)
uv run python -m harness replay wedding branch_that_joins     # "PASS wedding/branch_that_joins (layer 4) 37 to 46 s" (about 1 minute with the start)
rm -rf my/var/examples/wedding my/var/harness.db* my/var/grounding_state.json my/var/replay
```

Also: Wi-Fi in the room may block Wikipedia and the model; tether a phone as a spare. Close other Claude Code sessions (they share the plan's usage).

## Per principle

What to say and point at that the README does not. The steps are in the README section named.

**Setup** (README 1 and 2). One core owns the conversation, three lanes and the plan state; the model is one swappable interface. `harness --help`: `check`, `events`, `ui`, `replay` come with the core; `ground`, `build` and `ask` with layers 1 to 3. After `harness check`, `harness events` shows one line, `core.check`. `harness ui` without the example is empty: no plan, nothing to draw. Do not type there yet.

**1 Shared Domain** (README 3). Legend entry 1. Do the interview live first (action 3; first question after 10 to 14 s, the plan after 28 to 46 s, the correction 18 to 26 s, 2/2), then open the example. The research ("reading up on: sinking fund, ...") is printed only by the terminal command `harness ground`, not on the page: say it, do not look for it. During each wait, say what the interview, the proposal and the correction are for. On the example, say the trunk's one node, "Plan accepted", is where the history of decisions starts.

**2 Consistency** (README 4). Legend entry 2. Bridge: "The shared plan says which parts never change." The model never adds up; a calculation runs only if its module's tests pass now. Step 8, "not in the plan", is the step the seed added in a conversation. The rebuild of step 3 (action 2) takes 33 to 35 s (3/3); talk during the wait: the code writer never sees the examples, a second pass checks them. Take one example and work it out on a calculator in front of the room; examples differ per build, and nobody has confirmed them. A whole 4-step build took 200 s (1/1).

**3 Evidence** (README 5). Legend entry 3; it lights up with the first answer. Bridge: "Tested code (and everything else) leaves a trail we can follow." The prepared sentence (action 3) takes 30 to 50 s; the spending of 8,500 makes a shortfall on any day. Say what the analyst did: it ran the modules, and the number check holds back anything no step made. Clicking an underlined shortfall selects step 5 and opens its pop-up. The `◌` on the reply belongs to principle 4. "What if my families give nothing?" takes 17 to 60 s.

**4 Accountability** (README 6). Legend entry 4. Bridge: "The evidence is what you decide with." Point at the right panel first: the trunk is only confirmed decisions; the conversation is below. The 120-guest reply takes 30 to 35 s (3/3): say "less prose, more objects". The proposal comes after 4 to 6 s (4/4): steps 1, 2 and 5 are outlined dashed, 6 and 7 faded; say that anything that touches your figures needs your yes. The join takes 1.5 to 4.5 s (3/3); `harness events` shows a `calc.run` for each re-run step. The sinking fund answer (5 to 6 s, 2/2) comes from the plan's glossary and offers a lookup it does not make. The call takes about 10 s (1/1); its trunk node shows the start of the question, not the choice.

**5 Verification** (README 7). Legend entry 5. Bridge: "Each challenge is yours to use or dismiss." Reset first so the room sees the reviewer start: `Review · 2` or `Review · 3` after 10 to 13 s (3/3). Someone other than the analyst looks at how the problem is being thought about. After Use this the analyst replies in 4 to 6 s (2/2) and asks for inputs not saved yet.

**Wrap.** What they take home: `harness/` and their `my/`. `workshop/` is teaching material; deleting it leaves a harness whose tests pass. Repeat the limits from README 8: a variation of the example with their own figures and dates works; a very different plan, or a new harness, is for `workshop/BUILD_YOUR_OWN.md`.

If short on time, cut in this order: the live interview in principle 1 (use the seeded plan), the live rebuild in principle 2 (use `replay`), the call in principle 4, then the dead branch.

## Known rough edges

- Timings measured: check a few seconds (up to a minute on a first run), short reply 10 to 15 s, a full answer 30 to 50 s, a branch's proposal 4 to 6.5 s, the join 1.5 to 4.6 s, rebuild of one step 35 s, a whole 4-step build 200 s, reviewer 10 to 13 s, `replay` per scenario 4 to 88 s (all eight in a row: 307 s, 8 of 8 passed).
- A proposal needs a value the person wrote in the branch. A range ("between 150 and 200") is ambiguous: open the branch from one value (use the 120-guest sentence). One proposal per reply; the side assistant sometimes asks first.
- A join re-runs only the steps the value reaches in the last answer (1, 2 and 5 here). Steps 6 and 7 are shown as further on and stay as they were until asked. A re-run the gate refuses (a module changed under it) still saves the value and records the node; the node lists the steps that could not run again.
- Only your own buttons make trunk nodes (Confirm, Change it, a choice, Use this, Yes). A value you type in the main chat is conversation, not a decision: the 40/60 line typed after Confirm changes the answer and adds no node.
- A figure in an old reply is struck through only when its re-run gave a different value; a result chip is struck when its run re-ran, even if one of its several values did not move. After a later answer, steps it did not use fade and show examples instead of values until asked again.
- The glossary of the wedding example now carries sourced definitions for sinking fund, cash flow forecast and budget (from `reference/terms.json`); savings goal, net income and gross income have no saved source and stay the assistant's proposal.
- Marks are only as complete as the analyst's list; the mark appeared 4/4 here. The side assistant offers a lookup, it does not make one.
- The seeded examples' worked examples were recomputed by an AI agent, not by a person.
- Two layer 4 safeguards can re-do a reply before you see it (a call left in prose; a run input you never gave and no assumption lists). They add 5 to 15 s and show as a longer wait, nothing else. With "21 days from today" the first payment no longer shows up as an assumption.
- If the folder of a module is deleted, step 3 reads `Stale · rebuild` (its reason is "its folder is missing"); changed code reads "its files changed". On a copy that has never run, a deleted folder reads "Not built".
- A scenario that fails once deserves a second run; `decide_what_to_update` failed twice in three on an earlier day (no call raised) and passed in the last two full runs.
