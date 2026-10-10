# Step 4: when the harness needs you

Paste everything below the line into your coding agent, from the root of this repository.

---

You are building layer 4 of a small agent harness, the Financial Advisor Harness. Steps 0 to 3 are built. The repository holds the contract, the tests and the given files for this layer. Write the code that makes the layer 4 tests pass without breaking the earlier layers.

What this layer does:

Nothing blocks unless the call is the person's. An assumption is run and marked; the person confirms or changes it. A call that is the person's stops and asks, with options. A calculation the plan lacks is built automatically and shown as not in the plan. Side threads answer questions on the side and never change anything.

Read these first, in this order:

1. `SPEC.md`: section 1 (ground rules), then section 6 (when the harness needs the person, 6.1 to 6.5). Follow its names, signatures, templates and behaviour exactly.
2. `ARCHITECTURE.md`: section 2 (files and layers), then 3.3 and 3.4 (`unconfirmed`, `calls`, decisions, threads), 4 and the notes marked A4a, A4b and B2 in section 11.
3. `harness/core/` and `harness/layers.py`, to see what the core offers a layer, and the earlier layers' packages, to see how they are written.
4. `tests/layer4/`. These tests are the definition of done.

Build these files, all in `harness/needs_you/`:

- `__init__.py`: a docstring only
- `calls.py`: decisions that wait for the person
- `layer.py`: `LAYER`: the state contribution, the tools, the actions `choose`, `confirm_assumptions` and `side`, hooks, replay expectations
- `marks.py`: assumptions, notices, confirm and correct
- `requests.py`: `request_module`, the automatic build of a missing calculation
- `schema.sql`: the `assumptions`, `run_assumptions` and `decisions` tables
- `side.py`: the side assistant and the `side` action

Given files (do not edit; read them):

- `harness/needs_you/analyst.md`
- `harness/needs_you/side.md`
- `harness/ui/page.html` and everything else in the core

Rules:

- Edit only the files listed above. Do not edit `SPEC.md`, `ARCHITECTURE.md`, anything under `tests/`, `design/`, `examples/`, `workshop/` or `my/`, the given files, or the core (`harness/core/`, `harness/model/`, `harness/ui/` and the top-level files). If you believe one of them is wrong, stop and say so.
- Layer 4 imports only layers below 4. It never reads `config.layers`, never writes another layer's tables, and never names an example (no "wedding").
- A number reaches the person only from a tested module, a saved input, the plan, their own words or today's date. Do not add a path around the test gate or the number check.
- Use only the Python standard library. Do not run the `claude` command or make a network call: every test runs offline with the scripted model.
- Do not read the git history of `harness/`: it holds the finished code.
- Keep it small and readable. People will read this code on a projector.

Done means this layer's tests pass and the earlier layers still pass. Run each folder on its own (two `tests/layer*` folders in one run share the name `conftest`):

```
uv run pytest tests/layer4 -q
uv run pytest tests/layer3 -q
uv run pytest tests/layer2 -q
uv run pytest tests/layer1 -q
uv run pytest tests/layer0 -q
```

Tests of layers above this one fail until they are built; that is expected. Then try it on the main example. An answer on an unsaid split is marked `◌`; confirm it, then change it to 40/60. If you are stuck, `uv run python -m workshop finish 4` restores the finished layer from git (your files are set aside first).

When you think you are done, report briefly: the files you created, the test results, and anything in the contract you found unclear or had to guess.
