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

To use Claude instead of the scripted stand-in:

```
pip install anthropic
export ANTHROPIC_API_KEY=...
python -m harness check
```

`HARNESS_MODEL` picks the model. Another provider is one new file under
`harness/model/` and one new branch in `get_model`; nothing else in the
harness changes.

## Build it yourself

Each branch `step-N` is the repository at the end of step N, and
`step-0-start` is the starting point before any harness code exists. To
rebuild a step with your own coding agent, check out the branch before it
and paste in the matching prompt from `prompts/`:

```
git checkout step-0-start     # then run prompts/step0_setup.md
git checkout step-0           # the finished step 0, to compare or catch up
```
