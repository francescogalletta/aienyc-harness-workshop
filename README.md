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

## Try it

Python 3.11 or later. Nothing to install for the offline run except pytest.
Run everything from the repository root, and use `python3` if your machine
has no `python`.

```
pip install pytest
python -m pytest -q
HARNESS_MODEL_PROVIDER=scripted python -m harness check
python -m harness events
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
python -m harness check
```

If `ANTHROPIC_API_KEY` is set in your shell, Claude Code uses that key
instead of your plan, so unset it first. If the check reports an unknown
option, update Claude Code with `claude update`.

With an API key:

```
pip install anthropic
export ANTHROPIC_API_KEY=...
export HARNESS_MODEL_PROVIDER=anthropic
python -m harness check
```

`HARNESS_MODEL` picks the model. The default is `claude-sonnet-5-5`; with
`claude_code` you can also use an alias such as `sonnet` or `haiku`.

### Add another provider

Any other model API, a free tier or a local model is one new file under
`harness/model/` and one new line in the table in
`harness/model/providers.py`. Nothing else in the harness changes. `SPEC.md`
section 3.7 has the recipe, and the Claude Code adapter is a worked example
of a provider that is not an API at all.

## Build it yourself

Each branch `step-N` is the repository at the end of step N, and
`step-0-start` is the starting point before any harness code exists. To
rebuild a step with your own coding agent, check out the branch before it
and paste in the matching prompt from `prompts/`:

```
git checkout step-0-start     # then run prompts/step0_setup.md
git checkout step-0           # the finished step 0, to compare or catch up
```
