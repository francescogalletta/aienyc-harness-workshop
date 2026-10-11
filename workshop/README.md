# Workshop guide

> **Before you arrive** (about ten minutes, on your own laptop)
> 1. Install [uv](https://docs.astral.sh/uv/) (macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`) and git.
> 2. Install Claude Code and sign in with your plan (`claude auth status` should say `"loggedIn": true`), or `export ANTHROPIC_API_KEY=...` and add `--extra claude` after every `uv run`, or install Codex and sign in (`codex login status`).
> 3. `git clone https://github.com/francescogalletta/aienyc-harness-workshop && cd aienyc-harness-workshop && uv run python -m harness check` (it should end with `Setup works`).

This is for people taking part. The facilitator's notes are in `FACILITATOR.md`.

Words used here: the **harness** is the program in `harness/`: a core plus five layers. **Step N** (0 to 5) is the harness with layers up to N switched on. A **step in the plan** is a box in the diagram on the page. **The page** is the screen `uv run python -m harness ui` opens in your browser: the plan as a diagram, and a chat beside it. **The example** is the seeded wedding plan.

## Read this first

The session is not made for building an entirely different harness, or a very different plan, from scratch. It will likely not fit in two hours.

- Following the main example works best. So does a variation of it with your own figures and dates.
- Your plan must be a money question that arithmetic on amounts and dates can answer.
- You need model access on your own machine.

## What you need

1. git, and [uv](https://docs.astral.sh/uv/), which fetches Python and the packages the first time you run a command (the root `README.md` has the install line, including Windows).
2. Model access: Claude Code signed in with your plan, an Anthropic API key, or Codex signed in (see "Set up" in `README.md`; with a key, add `--extra claude` after `uv run` in every command below). If `ANTHROPIC_API_KEY` is set and you want to use Claude Code, unset it.
3. The repository cloned (`git clone https://github.com/francescogalletta/aienyc-harness-workshop`) and a terminal open in its folder. Every command below runs from there. A check:

```
uv run python -m harness check
```

It should end with `Setup works`. It takes a few seconds; a longer model reply can take up to a minute.

## The six steps

The harness is a core (step 0) and five layers (steps 1 to 5): the plan, build, answers, needs you, review. "The harness at step N" is the finished harness with layers above N off. `workshop/STEPS.md` has the table.

```
uv run python -m workshop status --quick   # which layers are present and on
uv run python -m workshop at N             # run this copy as the harness at step N
```

`at N` removes and copies nothing. It writes `N` to `my/var/layers`, and `harness` reads it when it starts: stop the page (Ctrl+C) and start it again after `at N`, a reload is not enough (`at N` prints a line saying so). `at 5` is the whole harness. If `HARNESS_LAYERS` is set in your shell, it wins, and `at` says so.

## Three ways to take part

Pick one. You can change at any step.

### (a) Follow the main example

The seeded wedding plan. Nothing you do touches `my/`: the example is copied to `my/var/examples/wedding/` the first time, and your database lives beside it. Delete that folder to start again.

```
uv run python -m workshop at 1
HARNESS_EXAMPLE=wedding uv run python -m harness ui     # PowerShell: $env:HARNESS_EXAMPLE="wedding"; uv run python -m harness ui
```

Then `at 2`, `at 3` and so on: stop the page (Ctrl+C), run `at N`, start the page again. Change a figure, choose differently, and look at what changes. `examples/README.md` lists scenarios you can replay against the real model, for instance `uv run python -m harness replay wedding cover_each_payment` (the example is an argument, so `HARNESS_EXAMPLE` is not needed).

### (b) A variation with your own figures and plan

Same kind of plan (saving towards dated payments). It all lives in `my/`, without `HARNESS_EXAMPLE`.

```
uv run python -m workshop at 5
uv run python -m harness ui
```

Say what you want help with, answer the questions (or click **Propose the plan now**), accept the plan, click **Build the calculations**, then ask. A build takes one to four minutes. If the page shows an earlier plan, delete `my/var/harness.db*` and `my/var/grounding_state.json` to start again. Check each worked example with a calculator: a second model pass checks them, and a mistake both passes make gets through. Never type account numbers or passwords.

### (c) Build a layer's code yourself

You write the code with your own coding agent (Claude Code, Cursor, or similar), one layer at a time. Each step has a contract (`SPEC.md`, `ARCHITECTURE.md`), tests and a build prompt.

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
| 1 the plan | adds `ground` | Describe a goal and an interview proposes a plan; click a step and say what is wrong while it is proposed, and the plan redraws. On the example the plan is already accepted and drawn: steps, inputs, origins, open questions; click a step to read them |
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
