# Step 0: setup

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 0 of a small agent harness. The repository already
holds the contract, the tests and the account-file fixture
(`tests/fixtures/accounts/`). Your job is to write the
code that makes the step 0 tests pass.

Passages of `SPEC.md` marked "(step M)" for a step later than this one do not apply yet.

Read these first, in this order:

1. `SPEC.md`, sections 1 to 3. It is the contract. Follow its names,
   signatures and behaviour exactly.
2. `tests/step0/`. These tests are the definition of done.

Then build what section 3 of `SPEC.md` describes, under `harness/`.

Build these files (new):

- `harness/__init__.py` (a one-line docstring is enough)
- `harness/config.py`
- `harness/db.py`
- `harness/migrations/0001_init.sql`
- `harness/model/__init__.py`
- `harness/model/interface.py` (the interface)
- `harness/model/scripted.py` (the scripted stand-in)
- `harness/model/anthropic_provider.py` (the Claude API adapter)
- `harness/model/providers.py` (the provider table)
- `harness/model/claude_code_provider.py` (the Claude Code adapter)
- `harness/__main__.py`

Given files (do not edit):

- `SPEC.md`
- `tests/step0/` (the definition of done)
- `tests/data/` (tests of the account-file fixture)
- `tests/fixtures/` (the account-file fixture, with its generator and key)

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, or anything under `workshop/`. If you believe one of them is wrong, stop and
  say so instead of changing it.
- Build only step 0. Do not start on anything in section 4 of `SPEC.md`.
- Use only the Python standard library. The `anthropic` package may be
  imported in `harness/model/anthropic_provider.py` and nowhere else, and
  the step 0 tests must pass without it installed. They must also pass
  without Claude Code installed: do not run the `claude` command yourself.
- Keep it small and readable. People will read this code on a projector.
  No abstractions beyond what the contract asks for.

When you think you are done, run:

```
python -m pytest tests/step0 tests/data -q
HARNESS_MODEL_PROVIDER=scripted python -m harness check
python -m harness events
```

(Put `uv run` in front of each command if the project is set up with uv, or
use `python3` in place of `python` if that is what your machine has.)
All tests must pass and the last two commands must run cleanly. Then report,
briefly: the files you created, the test result, the output of the two
commands, and anything in the contract you found unclear or had to guess.
