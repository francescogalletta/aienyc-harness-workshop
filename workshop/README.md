# Workshop guide

This is for people taking part. The facilitator's notes are in `FACILITATOR.md`.

## Read this first

The session is not made for building an entirely different harness, or a very different plan, from scratch. It will likely not fit in two hours.

- Following the main example works best. So does a variation of it with your own figures and dates.
- Your plan must be a money question that arithmetic on amounts and dates can answer.
- You need model access on your own machine.

## What you need

1. [uv](https://docs.astral.sh/uv/). The root `README.md` has the install line.
2. Model access: Claude Code signed in with your plan, or an Anthropic API key (see "Set up" in `README.md`).
3. A check, from the repository root:

```
uv run python -m harness check
```

It should end with `Setup works`. A model reply takes 20 to 60 seconds.

## The six steps

The harness is a core (step 0) and five layers (steps 1 to 5): the plan, build, answers, needs you, review. "The harness at step N" is the finished harness with layers above N off. `workshop/STEPS.md` has the table.

```
uv run python -m workshop status --quick   # which layers are present and on
uv run python -m workshop at N             # run this copy as the harness at step N
```

`at N` removes and copies nothing. It writes `N` to `my/var/layers`, and `harness` reads it. `at 5` is the whole harness. If `HARNESS_LAYERS` is set in your shell, it wins, and `at` says so.

## Three ways to take part

Pick one. You can change at any step.

### (a) Follow the main example

The seeded wedding plan. Nothing you do touches `my/`: the example is copied to `my/var/examples/wedding/` the first time, and your database lives beside it. Delete that folder to start again.

```
uv run python -m workshop at 1
HARNESS_EXAMPLE=wedding uv run python -m harness ui
```

Then `at 2`, `at 3` and so on, and reload the page. Change a figure, choose differently, and look at what changes. `examples/README.md` lists scenarios you can replay against the real model, for instance `uv run python -m harness replay wedding cover_each_payment` (the example is an argument, so `HARNESS_EXAMPLE` is not needed).

### (b) A variation with your own figures and plan

Same kind of plan (saving towards dated payments). It all lives in `my/`, without `HARNESS_EXAMPLE`.

```
uv run python -m workshop at 5
uv run python -m harness ui
```

Say what you want help with, answer the questions, accept the plan, click **Build the calculations**, then ask. A build takes one to four minutes. Check each worked example with a calculator: a second model pass checks them, and a mistake both passes make gets through. Never type account numbers or passwords.

### (c) Build a layer's code yourself

You write the code with your own coding agent, one layer at a time. Each step has a contract (`SPEC.md`, `ARCHITECTURE.md`), tests and a build prompt.

```
uv run python -m workshop start 1       # removes layer 1's code and every later layer; keeps the tests
```

Paste the prompt `workshop/prompts/step1_plan.md` into your coding agent. It says what to build and what is given. Done means:

```
uv run pytest tests/layer1 -q           # this layer's tests pass
uv run pytest tests/layer0 -q           # and earlier layers still pass
```

Run each `tests/layerN` folder on its own. Tests of layers above N fail until you build them. Then `start 2` and the next prompt. If you get stuck, `uv run python -m workshop finish N` restores layers 1 to N from git. Anything of yours it would replace is copied first to `my/var/set-aside/<time>/`. Do not let your coding agent read the git history of `harness/`: it holds the finished code. The prompts are `step1_plan.md`, `step2_build.md`, `step3_answers.md`, `step4_needs_you.md` and `step5_review.md`. Step 0 builds nothing: the core is given.

## What you can do after each step

Commands are `uv run python -m harness ...`; `harness --help` lists what exists at the step.

| After step | Commands | In the page |
| --- | --- | --- |
| 0 core | `check`, `events`, `ui`, `replay` | An empty shell: no plan, nothing to draw yet |
| 1 the plan | adds `ground` | Describe a goal and an interview agrees a plan. On the example the plan is already drawn: steps, inputs, origins, open questions. Click a step to say what is wrong |
| 2 build | adds `build` | A build button. Each calculation step shows its examples and how many tests pass. Open a step to see examples, tests and code |
| 3 answers | adds `ask` | Ask in the chat. Each number in an answer leads to the step that made it. Steps used light up, the rest fade |
| 4 needs you | same commands | An answer that rests on something unconfirmed is marked `◌`: confirm or change it. Your calls ask with options. A missing calculation is built and shows as "not in the plan". "On the side" opens a side thread. In the terminal: `/confirm`, `/side TEXT`, `/reply TEXT` |
| 5 review | same commands | A reviewer challenges steps. A **Review** toggle shows them. Use or dismiss each, or reply in its thread |

## Catching up

```
uv run python -m workshop status          # where this copy stands (--quick skips the tests)
uv run python -m workshop at N            # see the finished harness as it is at step N
uv run python -m workshop finish N        # if you built it yourself: restore layers 1 to N from git
```

`at N` is enough to follow along. `finish N` is only for path (c).

## Taking it home

```
uv run python -m workshop at 5            # the whole harness
uv run python -m workshop leave
```

`leave` asks first (type `yes`, `y` or `ok`), then removes `workshop/`. What is left is the harness (`harness/`, `tests/`, `reference/`, `examples/`, `design/`, `SPEC.md`, `ARCHITECTURE.md`) and your `my/`. Commit the removal, `my/brief` and `my/modules`. `my/var/` is never committed. `my/var/layers` stays as it is, so `at 5` first, or delete that file, and the whole harness runs.
