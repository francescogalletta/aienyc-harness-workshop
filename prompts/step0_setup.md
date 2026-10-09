# Step 0: setup

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 0 of a small agent harness. The repository already
holds the contract, the tests and the example data. Your job is to write the
code that makes the step 0 tests pass.

Read these first, in this order:

1. `SPEC.md`, sections 1 to 3. It is the contract. Follow its names,
   signatures and behaviour exactly.
2. `tests/step0/`. These tests are the definition of done.

Then build what section 3 of `SPEC.md` describes, under `harness/`:

- `harness/__init__.py` (a one-line docstring is enough)
- `harness/config.py`
- `harness/model/` (the interface, the scripted stand-in, the provider table,
  the Claude API adapter and the Claude Code adapter)
- `harness/db.py` and `harness/migrations/0001_init.sql`
- `harness/__main__.py`

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, anything under `data/`, or
  anything under `prompts/`. If you believe one of them is wrong, stop and
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

(Use `python3` in place of `python` if that is what your machine has.)
All tests must pass and the last two commands must run cleanly. Then report,
briefly: the files you created, the test result, the output of the two
commands, and anything in the contract you found unclear or had to guess.
