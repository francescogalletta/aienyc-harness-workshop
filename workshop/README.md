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

You use the seeded wedding example. Nothing you do here touches `my/`.

```
HARNESS_EXAMPLE=wedding uv run python -m harness adopt    # once: register its modules
HARNESS_EXAMPLE=wedding uv run python -m harness ask      # ask about the plan
HARNESS_EXAMPLE=wedding uv run python -m harness work     # see how each number was reached
uv run python -m harness replay wedding cover_each_payment   # a scripted person, the real model
```

When the facilitator reaches a step, run the same commands. Change a figure,
choose differently, and look at what changes. In step 5 add the account
files: `HARNESS_EXAMPLE=wedding uv run python -m harness data add`.
Your changes live in `my/var/examples/wedding/`. Delete that folder to start
the example again.

### (b) A variation of the main example

Same kind of plan (saving towards dated payments), your own figures and files.
It all lives in `my/`.

```
uv run python -m harness ui                        # the interview, in your browser
uv run python -m harness build                     # the calculation modules; check each example by hand
uv run python -m harness ask "..."                 # ask about your plan
uv run python -m harness data add statement.csv --sign negative
uv run python -m harness work                      # show your work
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

It asks first, then removes `workshop/`. What is left is the harness
(`harness/`, `tests/`, `reference/`, `examples/`, `SPEC.md`) and your `my/`.
Commit the removal, `my/brief` and `my/modules`. `my/var/` is never committed.
If you leave midway, the harness stays at that step: run
`uv run python -m workshop finish 5` first for the whole harness.
