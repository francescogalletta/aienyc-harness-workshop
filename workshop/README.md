# Workshop guide

> **Before you arrive** (about ten minutes, on your own laptop)
> 1. Install [uv](https://docs.astral.sh/uv/) (macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`) and git.
> 2. Install Claude Code and sign in with your plan (`claude auth status` should say `"loggedIn": true`), or `export ANTHROPIC_API_KEY=...` and add `--extra claude` after every `uv run`.
> 3. `git clone https://github.com/francescogalletta/aienyc-harness-workshop && cd aienyc-harness-workshop && uv run python -m harness check` (it should end with `Setup works`).

This is for people taking part, and the start page for the workshop. Also here: hands-on exercises for each layer in `EXERCISES.md`, the slides in `slides/` (open `slides/deck.html` in a browser), and the facilitator's notes in `FACILITATOR.md`.

Words used here: the **harness** is the program in `harness/`: a core plus five layers. A fresh clone runs all of it, starting from an empty plan. A **step in the plan** is a box in the diagram on the page. **The page** is the screen `uv run python -m harness ui` opens in your browser: the plan as a diagram on the left, and on the right the **decision graph**: a trunk of the decisions that changed the plan, **branches** that leave it, and the conversation under it. A **chip** is a small box in a reply (a value, an assumption, a result); hover one for a menu. **The example** is the seeded wedding plan.

## Read this first

The session is not made for building an entirely different harness, or a very different plan, from scratch. It will likely not fit in two hours.

- Following the main example works best. So does a variation of it with your own figures and dates.
- Your plan must be a money question that arithmetic on amounts and dates can answer.
- You need model access on your own machine.

## What you need

1. git, and [uv](https://docs.astral.sh/uv/), which fetches Python and the packages the first time you run a command (the root `README.md` has the install line, including Windows).
2. Model access: Claude Code signed in with your plan, or an Anthropic API key (see "Set up" in `README.md`; with a key, add `--extra claude` after `uv run` in every command below). If `ANTHROPIC_API_KEY` is set and you want to use Claude Code, unset it.
3. The repository cloned (`git clone https://github.com/francescogalletta/aienyc-harness-workshop`) and a terminal open in its folder. Every command below runs from there. A check:

```
uv run python -m harness check
```

It should end with `Setup works`. It takes a few seconds, up to a minute on a first run.

## The five layers

The harness is a core and five layers: the plan, build, answers, needs you, review. All five are on. Each session block shows what one layer adds, on the same page.

## Two ways to take part

Pick one. You can change at any time.

### (a) Follow the main example

The seeded wedding plan. Nothing you do touches `my/`: the example is copied to `my/var/examples/wedding/` the first time, and your database lives beside it. Delete that folder to start again.

```
HARNESS_EXAMPLE=wedding uv run python -m harness ui     # PowerShell: $env:HARNESS_EXAMPLE="wedding"; uv run python -m harness ui
```

Change a figure, choose differently, and look at what changes. `examples/README.md` lists scenarios you can replay against the real model, for instance `uv run python -m harness replay wedding cover_each_payment`, or `branch_that_joins` for the decision graph (the example is an argument, so `HARNESS_EXAMPLE` is not needed). `EXERCISES.md` has exercises for each layer.

### (b) A variation with your own figures and plan

Same kind of plan (saving towards dated payments). It all lives in `my/`, without `HARNESS_EXAMPLE`.

```
uv run python -m harness ui
```

Say what you want help with, answer the questions (or click **Propose the plan now**), accept the plan, click **Build the calculations**, then ask. A build takes one to four minutes. If the page shows an earlier plan, delete `my/var/harness.db*` and `my/var/grounding_state.json` to start again. Check each worked example with a calculator: a second model pass checks them, and a mistake both passes make gets through. Never type account numbers or passwords.

### Optional: build a layer's code yourself

Not what the session is for. Each layer has a contract (`SPEC.md`, `ARCHITECTURE.md`), tests and a build prompt in `workshop/prompts/` (`step1_plan.md` to `step5_review.md`; the core is given). Delete the layer's folder by hand, and the folders of every later layer, since a layer imports only the ones below it (for layer 5: `rm -rf harness/review`). Paste the prompt into your coding agent (Claude Code, Cursor, or similar). Done means that layer's tests pass, then the earlier ones, each folder on its own (`uv run pytest tests/layer5 -q`, then `tests/layer4` and down). `git checkout -- harness/` brings the finished code back. Do not let your coding agent read the git history of `harness/`: it holds the finished code.

## What each layer adds

Commands are `uv run python -m harness ...`; `harness --help` lists them all.

| Layer | Command it adds | In the page |
| --- | --- | --- |
| 0 core | `check`, `events`, `ui`, `replay` | The page itself: with no plan yet, there is nothing to draw |
| 1 the plan | `ground` | Describe a goal and an interview proposes a plan; click a step and say what is wrong while it is proposed, and the plan redraws. On the example the plan is already accepted and drawn: steps, inputs, origins, open questions; click a step to read them |
| 2 build | `build` | A build button. Each calculation step shows its examples and how many tests pass. Open a step to see examples, tests and code |
| 3 answers | `ask` | Ask in the chat. The reply is short; the values it used, what it assumed and what it found are chips under it. Each number leads to the step that made it. Steps used light up, the rest fade |
| 4 needs you | none | An answer that rests on something unconfirmed is marked `◌`: confirm or change it. Your calls ask with options. A missing calculation is built and shows as "not in the plan". Hover a chip to challenge or correct it, or to open a branch about it (or click a step, then **New branch**). If a branch proposes a change to one of your figures, nothing changes until you say Yes: then it joins the trunk as a decision and the steps it reaches run again through the same test gate, with no model call. A branch that changes nothing stays on the page, dimmed. Confirm, Change it and your calls become trunk nodes too. In the terminal: `/confirm`, `/side TEXT`, `/reply TEXT`, `/yes`, `/no`, `/close` |
| 5 review | none | A reviewer challenges steps; each challenge is a branch off the trunk, and the **Review** button counts the open ones. **Use this** joins the trunk, **Dismiss** leaves the branch dimmed. Or reply in its thread |

## Taking it home

You take home the harness (`harness/`, `tests/`, `reference/`, `examples/`, `design/`, `SPEC.md`, `ARCHITECTURE.md`) and your `my/`. `workshop/` is only teaching material: delete it by hand if you like, and the harness's tests still pass. Commit `my/brief` and `my/modules`. `my/var/` is never committed.
