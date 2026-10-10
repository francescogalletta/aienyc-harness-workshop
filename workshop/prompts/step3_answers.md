# Step 3: answers with evidence

Paste everything below the line into your coding agent, from the root of this repository.

---

You are building layer 3 of a small agent harness, the Financial Advisor Harness. Steps 0 to 2 are built. The repository holds the contract, the tests and the given files for this layer. Write the code that makes the layer 3 tests pass without breaking the earlier layers.

What this layer does:

After the plan is accepted, the person's messages go to an analyst that can run only tested modules, save inputs and change the plan. Every number in a reply is checked against its sources; a reply with a number no step produced is corrected once, then held back. Each number in a reply carries the step that produced it, and steps get a `last_run`.

Read these first, in this order:

1. `SPEC.md`: section 1 (ground rules), then section 5 (answers with evidence, 5.1 to 5.3). Follow its names, signatures, templates and behaviour exactly.
2. `ARCHITECTURE.md`: section 2 (files and layers), then 3.3 and 3.4 (`last_run`, chat messages and their figures), 4 and the notes marked A3 in section 11.
3. `harness/core/` and `harness/layers.py`, to see what the core offers a layer, and the earlier layers' packages, to see how they are written.
4. `tests/layer3/`. These tests are the definition of done.

Build these files, all in `harness/answers/`:

- `__init__.py`: a docstring only
- `agent.py`: the analyst turn, its tools, the number-check sources, the system prompt from the layers' parts
- `figures.py`: the figures of a reply and the last answer
- `layer.py`: `LAYER`: the state contribution, routing after acceptance, the `ask` command, replay expectations
- `schema.sql`: the `inputs` table

Given files (do not edit; read them):

- `harness/answers/analyst.md`
- `harness/ui/page.html` and everything else in the core

Rules:

- Edit only the files listed above. Do not edit `SPEC.md`, `ARCHITECTURE.md`, anything under `tests/`, `design/`, `examples/`, `workshop/` or `my/`, the given files, or the core (`harness/core/`, `harness/model/`, `harness/ui/` and the top-level files). If you believe one of them is wrong, stop and say so.
- Layer 3 imports only layers below 3. It never reads `config.layers`, never writes another layer's tables, and never names an example (no "wedding").
- A number reaches the person only from a tested module, a saved input, the plan, their own words or today's date. Do not add a path around the test gate or the number check.
- Use only the Python standard library. Do not run the `claude` command or make a network call: every test runs offline with the scripted model.
- Do not read the git history of `harness/`: it holds the finished code.
- Keep it small and readable. People will read this code on a projector.

Done means this layer's tests pass and the earlier layers still pass. Run each folder on its own (two `tests/layer*` folders in one run share the name `conftest`):

```
uv run pytest tests/layer3 -q
uv run pytest tests/layer2 -q
uv run pytest tests/layer1 -q
uv run pytest tests/layer0 -q
```

Tests of layers above this one fail until they are built; that is expected. Then try it on the main example. The question in `examples/wedding/scenarios/cover_each_payment.json` gives 43,000 and 54,500, and each number leads to its step. If you are stuck, `uv run python -m workshop finish 3` restores the finished layer from git (your files are set aside first).

When you think you are done, report briefly: the files you created, the test results, and anything in the contract you found unclear or had to guess.
