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

| Block | Min | Principle |
| --- | --- | --- |
| 0 Setup | 10 | The model is one swappable interface |
| 1 Shared domain | 20 | Agree the words before any number |
| 2 Consistency | 25 | Numbers come only from tested code |
| 3 Evidence | 15 | Every number can be followed back |
| 4 Human in the loop | 20 | Ask only where a person must decide |
| 5 Verification | 20 | Check what people say against their own files |
| Wrap | 10 | `leave`, questions |

### Block 0: setup (10 min)

- Principle: the harness talks to one model interface, and a database records everything.
- Live: `workshop start 0`, then paste `step0_setup.md`, or `workshop finish 0`.
- Show: `harness check` talks to a model and leaves one record; `harness events` lists it.
- Attendees: all paths run `harness check`. Path (c) builds step 0 with their agent.
- Slips: model sign-in, an old `claude` (run `claude update`), `ANTHROPIC_API_KEY` set by mistake.

### Block 1: shared domain (20 min)

- Principle: an interview turns a vague goal into a brief everyone agrees on.
- Live: `workshop start 1` (or `finish 0` then `start 1`), build, then `harness ui`.
- Show: before, "I want to pay for my wedding"; after, the brief. Open
  `examples/wedding/brief/domain_brief.md` for what a finished one looks like.
- Attendees: (a) read the wedding brief. (b) run `harness ui` with their own goal. (c) paste the prompt, run `uv run pytest tests/step1`, then `workshop next`.
- Slips: the interview takes longer than anyone plans. Cut it at the first proposed brief.

### Block 2: consistency (25 min)

- Principle: the model never adds up; it can only run a module whose tests pass.
- Live: `workshop start 2`, build, then `HARNESS_EXAMPLE=wedding harness adopt` and `ask`.
- Show: before, the model sums a reply in prose. After, a module run, and a failing test stops it.
  Scenarios: `cover_each_payment` (ask), `no_family_contribution` (ask), `build_monthly_surplus` (build, about five minutes: start it early).
- Attendees: (a) `adopt`, `ask`. (b) `harness build` on their brief; start it early. (c) build, tests, `next`.
- Slips: this is the longest block. A full `build` takes about eight minutes, and proposed worked examples can be wrong (check with a calculator).

### Block 3: evidence (15 min)

- Principle: everything is recorded, and the page reads only the database.
- Live: `workshop start 3` or `finish 3`, then `harness work`.
- Show: after one `ask`, follow a number to its run, module and tests; press "Run the tests now".
  Scenario: `cover_each_payment`, replayed with `--keep` and opened with `work`.
- Attendees: (a) and (b) open `work` after an `ask`. (c) build `evidence.py`, then `next`.
- Slips: attendees who never ran an `ask` have nothing to show.

### Block 4: human in the loop (20 min)

- Principle: gates only on assumptions and judgment calls, never on computed numbers.
- Live: `workshop start 4` or `finish 4`, then `ask`.
- Show: a gate on an unconfirmed assumption; `/aside` to ask what a term means, `/back`; `harness decisions`.
  Scenarios: `decide_what_to_update`, `aside_before_asking`.
- Attendees: (a) and (b) try `/aside` at a question. (c) build, test, `next`.
- Slips: a gate only shows when something is unconfirmed; give a date or figure the brief lacks.

### Block 5: verification (20 min)

- Principle: a figure someone states is checked against their own files; they decide.
- Live: `workshop start 5` or `finish 5`, then `HARNESS_EXAMPLE=wedding harness data add` (`negative` for `checking.csv` and `savings.csv`, `positive` for `credit_card.csv`).
- Show: say "I spend about 5,000 a month and have 10,000 saved". Files show 5,640.53 and 9,230.13.
  Scenarios: `check_my_figures`, `pay_agrees_with_files` (no finding), `new_dinner_price`, `spending_vs_brief`.
- Attendees: (a) as shown. (b) `data add` their own file. (c) build the adapter and verifier.
- Slips: file formats of their own; the adapter refuses what it cannot read whole, with one reason.

### Wrap (10 min)

`workshop leave`, what they take home, the limitation in `README.md` here.

## Known rough edges

- Model calls take 20 to 60 seconds each through Claude Code. An `ask` replay takes a few minutes.
- The finding block states the file figure twice.
- The worked examples in the seeded modules were checked by an AI agent, not yet by a person.
- `workshop start N` removes later files and rewrites many; it sets aside any you changed, in `my/var/set-aside/`.
- `workshop status` without `--quick` runs every step's tests, about a minute.
