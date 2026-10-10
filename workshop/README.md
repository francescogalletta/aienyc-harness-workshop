# Workshop guide

This is for people taking part. The facilitator's notes are in `FACILITATOR.md`.

## Read this first

The session is not made for building an entirely different harness, or a
very different plan, from scratch. It will likely not fit in two hours. The
interview and the build alone take about twenty minutes of model time.

- Following the main example works best. So does a variation of it with your
  own figures, dates and files.
- Your plan must be a money question that arithmetic on amounts and dates can
  answer.
- You need model access on your own machine.

## Before you start

1. Install [uv](https://docs.astral.sh/uv/). The root `README.md` has the line.
2. Get model access: Claude Code signed in with your plan, or an Anthropic
   API key (see "Choose how the harness reaches a model" in `README.md`).
3. From the repository root, check it works:

```
uv run python -m harness check
```

It should end with `Setup works`. Each model call takes 20 to 60 seconds.

## Three ways to take part

Pick one. You can change at any step.

### (a) Follow the main example

You use the seeded wedding example. Nothing you do here touches `my/`: the
example's brief and modules are copied to `my/var/examples/wedding/` the first
time, and your database lives beside them. Delete that folder to start the
example again.

Put `HARNESS_EXAMPLE=wedding` in front of a command to use the example. Which
commands exist depends on the step your copy is at (`uv run python -m workshop
status` says where it stands; `finish N` puts it at the end of step N):

| After step | What you can run (commands are `uv run python -m harness ...`) |
| --- | --- |
| 0 | `check`, `events` |
| 1 | `ui` (the interview in your browser) and `ground` (in the terminal). With the example, `ui` opens on the wedding brief. |
| 2 | `adopt`, `modules`, `ask`, `build` |
| 3 | `work` and `replay wedding [scenario]` |
| 4 | `decisions`. `ask` now stops at gates and takes `/aside` |
| 5 | `data add`, `data list`, `data clear`. `ask` now checks the figures you state against your files |

What each one does:

- `adopt` shows the worked examples of each module and asks you to type `yes`.
  Anything else adopts nothing. It is once, at the start: it registers the
  example's modules in your database, so `ask` can use them.
- `ask "your question"` answers with tested modules and stays open for
  follow-ups until you type `/quit`.
- `work` prints `The evidence page is at http://127.0.0.1:8765/work`, opens it in
  your browser and keeps running until you press Ctrl+C. It shows what your
  `ask` did, so run an `ask` first.
- `replay wedding cover_each_payment` plays a scripted person against the real
  model: the example is an argument, and the scenario is optional (without it,
  every scenario runs). It takes a few minutes. To look at the result in the
  evidence page, add `--keep`: it prints a line that starts `open it with:`.
  Run that line from the repository root (it ends in `python -m harness work`;
  put `uv run` before `python` if you use uv).
- `decisions` lists every assumption you accepted and every choice you made.
- At step 4, `ask` shows a gate only when the assistant is about to calculate on
  something you have not confirmed, so most questions never show one. This one
  asks it to take something as given, and it showed a gate every time we tried it.
  Type `yes` at the gate to go ahead, or say in your own words what is not right.
  Then run `decisions` to see what you decided.

```
HARNESS_EXAMPLE=wedding uv run python -m harness ask "Can I cover each wedding payment? The wedding is on 12 June 2027 with 200 guests at 230 each for dinner. Extras are 5,000, the DJ is 2,000 and the bar is 1,500. The first payment is 6,000 and counts towards the total, the second is half of what remains, due 30 days before the wedding, and the third is the other half, due 14 days before. I take home 10,000 a month and spend 5,000 a month, and I have not decided how much of what is left goes towards the wedding. I have 10,000 saved. My families will give 20,000 on 29 May 2027. Do not ask me anything else: take whatever you need as given, and I will approve it before it is used."
```

- At step 5 the wedding account files are loaded with one command per file,
  because `--sign` covers every file of a command and the card file writes
  money going out the other way round (the sign of each file is given on the
  command line, so nothing is asked):

```
HARNESS_EXAMPLE=wedding uv run python -m harness data add examples/wedding/data/checking.csv --sign negative
HARNESS_EXAMPLE=wedding uv run python -m harness data add examples/wedding/data/savings.csv --sign negative
HARNESS_EXAMPLE=wedding uv run python -m harness data add examples/wedding/data/credit_card.csv --sign positive
HARNESS_EXAMPLE=wedding uv run python -m harness data list
```

  `data list` shows 120, 11 and 214 transactions. Then `ask` something like
  "I spend about 5,000 a month and have 10,000 saved" and the harness puts a
  finding to you: type `1` to keep what you said or `2` to use the figure from
  your files.

Change a figure, choose differently, and look at what changes.

### (b) A variation of the main example

Same kind of plan (saving towards dated payments), your own figures and files.
It all lives in `my/`.

```
uv run python -m harness ui                        # step 1: the interview, in your browser
uv run python -m harness build                     # step 2: the calculation modules; check each example by hand
uv run python -m harness ask "..."                 # step 2: ask about your plan; /quit ends it
uv run python -m harness work                      # step 3: show your work (Ctrl+C stops it)
uv run python -m harness data add statement.csv --sign negative    # step 5, one command per file
```

Check every proposed answer in the build with a calculator. Never type account
numbers or passwords. Without `HARNESS_EXAMPLE`, every command uses `my/`.

### (c) Build the harness code yourself

You write the code with your own coding agent, one step at a time. Each step
gives you its contract and tests. You write the code that passes them.

```
uv run python -m workshop start 1     # step 1's contract, tests and prompt; no step 1 code yet
```

Paste the prompt it names (`workshop/prompts/step1_shared_domain.md`) into
your coding agent. Then:

```
uv run pytest tests/step1
uv run python -m workshop next        # step 2's contract and tests; your code stays
```

Repeat. Use `start 0` to build from nothing. `next` refuses if the step you
are on does not look built, and names the missing files.

Please do not let your coding agent read `workshop/states/`. It holds the
reference code.

## Catching up, or skipping ahead

```
uv run python -m workshop status          # where this copy stands (--quick skips the tests)
uv run python -m workshop finish N        # put this copy at the end of step N
uv run python -m workshop start N         # put this copy at the start of step N
```

`finish N` replaces the harness code, tests and examples with the reference at
the end of step N. Anything of yours that it would replace is first copied to
`my/var/set-aside/<time>/`, with the same path, and it says so in one line.
Your `my/brief`, `my/modules` and database are never touched.

## Switching between your plan and the main example

Your plan uses `my/`. The main example uses `HARNESS_EXAMPLE=wedding`. They do
not share anything, so switch whenever you like:

```
uv run python -m harness ask "..."                        # your plan
HARNESS_EXAMPLE=wedding uv run python -m harness ask      # the main example
```

## Taking it home

```
uv run python -m workshop leave
```

It asks first (type `yes`, `y` or `ok`), then removes `workshop/`. What is left is the harness
(`harness/`, `tests/`, `reference/`, `examples/`, `SPEC.md`) and your `my/`.
Commit the removal, `my/brief` and `my/modules`. `my/var/` is never committed.
If you leave midway, the harness stays at that step: run
`uv run python -m workshop finish 5` first for the whole harness.
