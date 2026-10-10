# Step 5: review

Paste everything below the line into your coding agent, from the root of this repository.

---

You are building layer 5 of a small agent harness, the Financial Advisor Harness. Steps 0 to 4 are built. The repository holds the contract, the tests and the given files for this layer. Write the code that makes the layer 5 tests pass without breaking the earlier layers.

What this layer does:

A reviewer looks at how the problem is being thought about and challenges weak assumptions, inputs, methods or the shape of the plan. It runs in the background on its own lane, after the plan is accepted and when new assumptions appear. A challenge belongs to a step and is a thread in the chat; the person uses it or dismisses it. A challenge that cites outside information carries a source the harness fetched; only a general term goes to the web.

Read these first, in this order:

1. `SPEC.md`: section 1 (ground rules), then section 7 (review, 7.1 to 7.4). Follow its names, signatures, templates and behaviour exactly.
2. `ARCHITECTURE.md`: section 2 (files and layers), then 3.4 (threads and challenges), 4 and the notes marked A5 in section 11.
3. `harness/core/` and `harness/layers.py`, to see what the core offers a layer, and the earlier layers' packages, to see how they are written.
4. `tests/layer5/`. These tests are the definition of done.

Build these files, all in `harness/review/`:

- `__init__.py`: a docstring only
- `layer.py`: `LAYER`: the state contribution, hooks, the actions `use_challenge` and `dismiss_challenge`, the `challenges` expectation
- `reviewer.py`: a review pass, its checks and the cap per pass
- `schema.sql`: the `challenges` and `review_passes` tables

Given files (do not edit; read them):

- `harness/review/analyst.md`
- `harness/review/reviewer.md`
- `harness/ui/page.html` and everything else in the core

Rules:

- Edit only the files listed above. Do not edit `SPEC.md`, `ARCHITECTURE.md`, anything under `tests/`, `design/`, `examples/`, `workshop/` or `my/`, the given files, or the core (`harness/core/`, `harness/model/`, `harness/ui/` and the top-level files). If you believe one of them is wrong, stop and say so.
- Layer 5 imports only layers below 5. It never reads `config.layers`, never writes another layer's tables, and never names an example (no "wedding").
- A number reaches the person only from a tested module, a saved input, the plan, their own words or today's date. Do not add a path around the test gate or the number check.
- Use only the Python standard library. Do not run the `claude` command or make a network call: every test runs offline with the scripted model.
- Do not read the git history of `harness/`: it holds the finished code.
- Keep it small and readable. People will read this code on a projector.

Done means this layer's tests pass and the earlier layers still pass. Run each folder on its own (two `tests/layer*` folders in one run share the name `conftest`):

```
uv run pytest tests/layer5 -q
uv run pytest tests/layer4 -q
uv run pytest tests/layer3 -q
uv run pytest tests/layer2 -q
uv run pytest tests/layer1 -q
uv run pytest tests/layer0 -q
```

Tests of layers above this one fail until they are built; that is expected. Then try it on the main example. The seeded wedding plan gets challenges on its steps; one can be used and one dismissed. If you are stuck, `uv run python -m workshop finish 5` restores the finished layer from git (your files are set aside first).

When you think you are done, report briefly: the files you created, the test results, and anything in the contract you found unclear or had to guess.
