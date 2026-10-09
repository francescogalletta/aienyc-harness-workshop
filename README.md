# Finance harness workshop

A small agent harness for personal finance work, built one design principle
at a time. The running example is an agent that helps one person stay on
top of their money so that their wedding is paid for without surprises.

The harness itself knows nothing about weddings. The example lives in
`data/example/`.

## What is here

| Path | What it is |
| --- | --- |
| `SPEC.md` | The contract every build step follows |
| `BUILD_PLAN.md` | The steps, the proof for each, and what is done so far |
| `prompts/` | One build prompt per step, for any coding agent |
| `harness/` | The harness, as built so far |
| `tests/` | Acceptance tests per step, plus tests for the example data |
| `data/` | The example data, its generator, and the facilitator key |
| `reference/` | Saved finance terms with checked sources, for offline lookups |
| `brief/` | The domain brief, once you have run the interview |
| `modules/` | The tested calculation modules, once you have run the build |

## Set up

The simplest way is [uv](https://docs.astral.sh/uv/). It is one small tool
that fetches a suitable Python if your machine has none, and keeps
everything this project needs in a `.venv` folder inside the repository.
Nothing else on your machine changes, and deleting `.venv` undoes it.

```
curl -LsSf https://astral.sh/uv/install.sh | sh     # macOS or Linux (or: brew install uv)
```

On Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Then, from the repository root:

```
uv run pytest -q                                           # sets everything up, then runs the tests
HARNESS_MODEL_PROVIDER=scripted uv run python -m harness check
uv run python -m harness events
```

Put `uv run` in front of any command in this repository and it runs inside
that environment.

Without uv, any Python 3.11 or later works:

```
python3 -m venv .venv && source .venv/bin/activate
pip install pytest
python -m pytest -q
```

## Choose how the harness reaches a model

The harness talks to a model through one interface. `HARNESS_MODEL_PROVIDER`
picks what sits behind it:

| Provider | What you need | Notes |
| --- | --- | --- |
| `scripted` | Nothing | Replays prepared responses. Used by every test. |
| `claude_code` | [Claude Code](https://code.claude.com/docs/en/overview) installed and signed in with your Claude plan | No API key. Usage counts against your plan. |
| `anthropic` | A Claude API key | Billed to the key. This is the default. |

With a Claude subscription and no API key:

```
claude auth status                        # should say you are logged in
export HARNESS_MODEL_PROVIDER=claude_code
uv run python -m harness check
```

The check sends the model a one-line test and should end with
`Setup works: the model replied and the check was saved as event 1.`

If `ANTHROPIC_API_KEY` is set in your shell, Claude Code uses that key
instead of your plan, so unset it first. If the check reports an unknown
option, update Claude Code with `claude update`.

With an API key:

```
export ANTHROPIC_API_KEY=...
export HARNESS_MODEL_PROVIDER=anthropic
uv run --extra claude python -m harness check
```

`HARNESS_MODEL` picks the model. The default is `claude-sonnet-5-5`; with
`claude_code` you can also use an alias such as `sonnet` or `haiku`.

## Run the grounding interview

Step 1 is a short interview. The harness asks what you want help with, checks
the finance terms you use against their standard meaning, and writes a
**domain brief**: your goal, the terms you agreed, what is particular to you,
and the steps needed, with the ones that must run as code marked.

```
export HARNESS_MODEL_PROVIDER=claude_code
uv run python -m harness ui
```

This opens a page in your browser, served from your own machine. The
conversation is on the left. On the right, the shared understanding builds
up as you talk:

- **Reading**: what the harness is reading up on, and where each answer came from.
- **Concept map**: your words next to the standard term, with its source. Terms you had no word for are marked as new to you.
- **Assumptions**: what is different about you, and how it will be handled.
- **Open questions**: answer any of them right there once a brief is proposed.
- **Needed from you**: the figures and dates the steps will ask for when they run.
- **The plan**: a diagram of the steps. Click one to see its method and formula.

When the harness proposes a brief, press **Accept brief** or **Ask for
changes**. The brief is saved as `brief/domain_brief.md` and
`brief/domain_brief.json`. If a brief already exists, the page opens on it.

Everything asked, answered and looked up is in the database:
`uv run python -m harness events`.

**Lookups.** The harness reads up on a few terms before the first question,
side by side, and never looks the same term up twice. By default it checks
the saved file `reference/terms.json` first and asks Wikipedia only for
terms the file does not know. Only the term itself is sent. Set
`HARNESS_RESEARCHER=reference` to stay offline, or `claude_code` to use
Claude Code's web search where that is available.

**In a terminal instead.** `uv run python -m harness ground` runs the same
interview as text. Type `/accept` to accept the brief, `/wrap` to finish
with what you have, or `/quit` to stop; `--resume` carries on.

Do not type account numbers or passwords into the interview.

### Add another provider

Any other model API, a free tier or a local model is one new file under
`harness/model/` and one new line in the table in
`harness/model/providers.py`. Nothing else in the harness changes. `SPEC.md`
section 3.7 has the recipe, and the Claude Code adapter is a worked example
of a provider that is not an API at all.

## Build the calculations and ask

Step 2 turns each calculation step of your brief into code that is tested
before it is allowed to run. You need a confirmed brief first.

```
export HARNESS_MODEL_PROVIDER=claude_code
uv run python -m harness build
```

Each model call can take up to a minute through Claude Code. A full build of
five steps took about eight minutes. A progress line tells you what is being
written.

For each calculation step, in the terminal:

- The harness shows its plan in plain words: what it needs from you and what it gives back. It asks whether that fits what you have. Type `yes`, or say in your own words what you do have, and the plan is reshaped. If the module already exists, it is reused and nothing is asked.
- It then shows made-up examples with small round numbers. They are not your figures. Check each one by hand. Answer `yes`, type the right answer, say in your own words what is wrong, or ask a question. `/skip` leaves a step or an example out. `/quit` stops the build.
- The code is written by a separate model call that never sees the examples, your brief or your notes.
- The harness runs the tests and the examples you confirmed. Only code that passes is registered.

What you say about your real situation during the build is kept as notes. `ask` uses them.

**Check every proposed answer with a calculator.** The proposed answers can be wrong. In a live run, one proposed answer contradicted its own working, and accepting it made that module fail to build.

```
uv run python -m harness modules
uv run python -m harness ask "How much can I put aside each month?"
```

`modules` lists what is built and runs every module's tests again now.
`ask` answers from the brief and the tested modules. It asks you for missing
inputs one at a time and remembers them, and it runs only tested modules. If
its reply contains a number that no module produced, the reply is held back.
Type `/quit` to stop.

Code changes in one way only: `uv run python -m harness build --rebuild NAME`.
If a module's files change any other way, it will not run until it is
rebuilt. Commit `modules/` together with the brief.

## Build it yourself

Every step has two branches. `step-N-start` holds the contract, tests and
prompt for step N, before it is built. `step-N` is the repository at the end
of step N. To rebuild a step with your own coding agent, check out its start
branch and paste in the matching prompt from `prompts/`:

```
git checkout step-1-start     # then run prompts/step1_shared_domain.md
git checkout step-1           # the finished step 1, to compare or catch up
```
