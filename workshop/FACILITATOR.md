# Facilitator notes

Two hours, six blocks. You build the harness live on the main example
(`examples/wedding`). Attendees take one of three paths, described in
`README.md` here: (a) follow the example, (b) a variation with their own
figures, (c) build the code themselves.

## Before the day

- `git pull`, then `uv run pytest -q` (under a minute).
- `uv run python -m workshop check` (about four minutes). The static checks on
  the first line must be ok. If a state fails, a fix on the finished tree has
  not reached a snapshot.
- `uv run python -m harness check` (model access works).
- One replay: `uv run python -m harness replay wedding cover_each_payment`
  (a few minutes). If it passes, the model, the seeded modules and the harness
  agree.
- Put the copy at step 0 or the step you start from: `uv run python -m workshop start 0`.
- Optional: remove `examples/wedding/data/.FACILITATOR_KEY.md` from the copy you
  hand out, so people find the planted quirks themselves.

## Run of show

Each block: say the principle, run `start N` (or `finish N`), build, show the
proof. Model calls take 20 to 60 seconds. Start a slow command, then talk.
Every command below exists at the step of its block; the main example works
from step 1 (`HARNESS_EXAMPLE=wedding` in front of a command), so you can
demonstrate every block on it. Commands are `uv run python -m harness ...`; the
short form `harness ...` below stands for that.

| Block | Min | Principle | New after this step |
| --- | --- | --- | --- |
| 0 Setup | 10 | The model is one swappable interface | `check`, `events` |
| 1 Shared domain | 20 | Agree the words before any number | `ui`, `ground`; `HARNESS_EXAMPLE` |
| 2 Consistency | 25 | Numbers come only from tested code | `adopt`, `ask`, `build`, `modules` |
| 3 Evidence | 15 | Every number can be followed back | `work`, `replay` |
| 4 Human in the loop | 20 | Ask only where a person must decide | `decisions`; gates and `/aside` in `ask` |
| 5 Verification | 20 | Check what people say against their own files | `data add`, `data list`, `data clear` |
| Wrap | 10 | `leave`, questions | |

### Block 0: setup (10 min)

- Principle: the harness talks to one model interface, and a database records everything.
- Live: `workshop start 0`, then paste `step0_setup.md`, or `workshop finish 0`.
- Show, before: there is nothing to run yet (`harness check` says there is no `harness.__main__`). Show the contract
  instead, `SPEC.md` section 3, and the failing tests: `uv run pytest tests/step0` stops with five collection errors.
- Show, after: `harness check` talks to a model and leaves one record; `harness events` lists it.
- Attendees: all paths run `harness check`. Path (c) builds step 0 with their agent.
- Slips: model sign-in, an old `claude` (run `claude update`), `ANTHROPIC_API_KEY` set by mistake.

### Block 1: shared domain (20 min)

- Principle: an interview turns a vague goal into a brief everyone agrees on.
- Live: `workshop start 1` (or `finish 0` then `start 1`), build, then `harness ui`.
- Show: before, "I want to pay for my wedding"; after, the brief. On the main example,
  `HARNESS_EXAMPLE=wedding harness ui` opens the page on the finished wedding brief
  (`examples/wedding/brief/domain_brief.md` is the same brief as a file).
- Attendees: (a) `HARNESS_EXAMPLE=wedding harness ui`, and read the brief. (b) `harness ui` with their own goal. (c) paste the prompt, run `uv run pytest tests/step1`, then `workshop next`.
- Slips: the interview takes longer than anyone plans. Cut it at the first proposed brief.

### Block 2: consistency (25 min)

- Principle: the model never adds up; it can only run a module whose tests pass.
- Live: `workshop start 2`, build, then `HARNESS_EXAMPLE=wedding harness adopt` and `HARNESS_EXAMPLE=wedding harness ask "..."`.
  `adopt` lists the worked examples and asks you to type `yes`; once is enough. `ask "question"` stays open for follow-ups until `/quit`.
- Show: before, the model sums a reply in prose. After, a module run, and a failing test stops it.
  For the question, copy the first line of `examples/wedding/scenarios/cover_each_payment.json` or `no_family_contribution.json`
  (`replay` comes at step 3, so at this step you ask it yourself). The modules of the example are already built:
  a full `harness build` on a brief of your own takes about eight minutes, so start it early.
- Attendees: (a) `adopt`, `ask`. (b) `harness build` on their brief; start it early. (c) build, tests, `next`.
- Slips: this is the longest block. Proposed worked examples can be wrong (check with a calculator).

### Block 3: evidence (15 min)

- Principle: everything is recorded, and the page reads only the database.
- Live: `workshop start 3` or `finish 3`, then `harness work`. It prints `The evidence page is at http://127.0.0.1:8765/work`,
  opens the browser and runs until Ctrl+C, so use a second terminal for anything else.
- Show: after one `ask`, follow a number to its run, module and tests; press "Run the tests now".
  Or replay a scenario and open it: `HARNESS_EXAMPLE` is not used by `replay`, the example is an argument:
  `harness replay wedding cover_each_payment --keep` (a few minutes). It prints a line that starts `open it with:`;
  run that line from the repository root to see that replay in the evidence page.
- Attendees: (a) and (b) open `work` after an `ask`. (c) build `evidence.py`, then `next`.
- Slips: attendees who never ran an `ask` have nothing to show.

### Block 4: human in the loop (20 min)

- Principle: gates only on assumptions and judgment calls, never on computed numbers.
- Live: `workshop start 4` or `finish 4`, then `HARNESS_EXAMPLE=wedding harness ask "..."` (adopt first if this copy is new).
- Show: a gate on an unconfirmed assumption; `/aside` to ask what a term means, `/back`; `harness decisions`.
  A gate appears only when the assistant is about to calculate on something nobody has confirmed, and most questions never
  raise one (the earlier advice, to give a date or figure the brief lacks, does not make it more likely). A question that did:

  ```
  HARNESS_EXAMPLE=wedding harness ask "Can I cover each wedding payment? The wedding is on 12 June 2027 with 200 guests at 230 each for dinner. Extras are 5,000, the DJ is 2,000 and the bar is 1,500. The first payment is 6,000 and counts towards the total, the second is half of what remains, due 30 days before the wedding, and the third is the other half, due 14 days before. I take home 10,000 a month and spend 5,000 a month, and I have not decided how much of what is left goes towards the wedding. I have 10,000 saved. My families will give 20,000 on 29 May 2027. Do not ask me anything else: take whatever you need as given, and I will approve it before it is used."
  ```

  It showed a gate in 9 of 9 real runs (3 at the end of step 4, 6 at the end of step 5 with no files loaded): the assistant
  proposed that the whole monthly surplus goes to the wedding fund, and waited for a yes. It is the model's choice, so
  it is not a guarantee: two phrasings that left out the last sentence or the undecided saving did it in 1 of 4 and 1 of 3.
  Have `harness decisions` ready as the fallback, and the scenarios `decide_what_to_update` and `aside_before_asking`
  (`harness replay wedding decide_what_to_update`; they answer a gate if one comes, and do not promise one).
  Type `yes` at the gate to carry on, or something else to refuse; then run `harness decisions`.
  With account files loaded (step 5) the same question raises a finding first, so clear them for this demo.
- Attendees: (a) and (b) try `/aside` at a question. (c) build, test, `next`.
- Slips: if no gate appears, say so; it is the design (no gate means nothing unconfirmed was assumed).

### Block 5: verification (20 min)

- Principle: a figure someone states is checked against their own files; they decide.
- Live: `workshop start 5` or `finish 5`, then load the three files, one command each (`--sign` covers every file of a command):

  ```
  HARNESS_EXAMPLE=wedding harness data add examples/wedding/data/checking.csv --sign negative
  HARNESS_EXAMPLE=wedding harness data add examples/wedding/data/savings.csv --sign negative
  HARNESS_EXAMPLE=wedding harness data add examples/wedding/data/credit_card.csv --sign positive
  HARNESS_EXAMPLE=wedding harness data list
  ```

  `data list` shows checking 120, savings 11 and credit_card 214 transactions (a bare `data add` loads the same three in
  name order and asks for each sign, `negative`, `positive`, `negative`; the first rows of `savings.csv` are deposits and look positive).
- Show: say "I spend about 5,000 a month and have 10,000 saved" in a full question, for instance the first line of
  `examples/wedding/scenarios/check_my_figures.json`. Files show 5,640.53 and 9,230.13. At each finding type `1` (keep
  what you said) or `2` (use the figure from the files).
  Scenarios: `check_my_figures`, `pay_agrees_with_files` (no finding), `new_dinner_price`, `spending_vs_brief`
  (`harness replay wedding check_my_figures`; a replay loads the files itself).
- Attendees: (a) as shown. (b) `data add` their own file with its `--sign`. (c) build the adapter and verifier.
- Slips: file formats of their own; the adapter refuses what it cannot read whole, with one reason.

### Wrap (10 min)

`workshop leave` (it asks; `yes`, `y` or `ok` removes `workshop/`), what they take home, the limitation in `README.md` here.

## Known rough edges

- Model calls take 20 to 60 seconds each through Claude Code. An `ask` replay takes a few minutes.
- The finding block states the file figure twice.
- The worked examples in the seeded modules were checked by an AI agent, not yet by a person.
- `workshop start N` removes later files and rewrites many; it sets aside any you changed, in `my/var/set-aside/`.
- `workshop status` without `--quick` runs every step's tests, about a minute.
