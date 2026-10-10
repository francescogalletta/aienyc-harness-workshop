# Step 2: build and tested calculations

Paste everything below the line into your coding agent, from the root of this repository.

---

You are building layer 2 of a small agent harness, the Financial Advisor Harness. Steps 0 and 1 are built. The repository holds the contract, the tests and the given files for this layer. Write the code that makes the layer 2 tests pass without breaking the earlier layers.

What this layer does:

Every number comes from a tested module. An unattended build turns each calculation step of the accepted plan into a spec, worked examples, a second-pass check of those examples and code written without seeing them. Only code that passes is registered. A test gate runs a module's tests before every run; a changed step makes its module stale; modules already on disk are adopted on load; the person can talk to a step through the step helper.

Read these first, in this order:

1. `SPEC.md`: section 1 (ground rules), then section 4 (build and tested calculations, 4.1 to 4.8). Follow its names, signatures, templates and behaviour exactly.
2. `ARCHITECTURE.md`: section 2 (files and layers), then 3.3 (a step and its `build`), 4 and the notes marked A2a and A2b in section 11.
3. `harness/core/` and `harness/layers.py`, to see what the core offers a layer, and the earlier layers' packages, to see how they are written.
4. `tests/layer2/`. These tests are the definition of done.

Build these files, all in `harness/calc/`:

- `__init__.py`: a docstring only
- `added.py`: steps added in a conversation (not in the plan)
- `adopt.py`: adoption of module folders already on disk
- `builder.py`: the unattended build, phase by phase
- `checker.py`: the second pass over the worked examples
- `gate.py`: running tests, and the one way a calculation runs
- `helper.py`: the step helper (the person on a step)
- `layer.py`: `LAYER`: the `build` key of every step, the actions `build`, `confirm_example`, `confirm_plan_check` and `run_tests`, routing for steps, the `build` command, hooks
- `notes.py`: notes kept during a build
- `provenance.py`: the number check
- `registry.py`: module folders, spec check, fingerprints, build records, step status
- `runner.py`: running a module in a subprocess
- `safety.py`: what module code may import and do
- `schema.sql`: the tables of SPEC 4.1
- `values.py`: typed values (money, dates, text)

Given files (do not edit; read them):

- `harness/calc/checker.md`
- `harness/calc/example_writer.md`
- `harness/calc/module_writer.md`
- `harness/calc/spec_writer.md`
- `harness/calc/step_helper.md`
- `harness/ui/page.html` and everything else in the core

Rules:

- Edit only the files listed above. Do not edit `SPEC.md`, `ARCHITECTURE.md`, anything under `tests/`, `design/`, `examples/`, `workshop/` or `my/`, the given files, or the core (`harness/core/`, `harness/model/`, `harness/ui/` and the top-level files). If you believe one of them is wrong, stop and say so.
- Layer 2 imports only layers below 2. It never reads `config.layers`, never writes another layer's tables, and never names an example (no "wedding").
- A number reaches the person only from a tested module, a saved input, the plan, their own words or today's date. Do not add a path around the test gate or the number check.
- Use only the Python standard library. Do not run the `claude` command or make a network call: every test runs offline with the scripted model.
- Do not read the git history of `harness/`: it holds the finished code.
- Keep it small and readable. People will read this code on a projector.

Done means this layer's tests pass and the earlier layers still pass. Run each folder on its own (two `tests/layer*` folders in one run share the name `conftest`):

```
uv run pytest tests/layer2 -q
uv run pytest tests/layer1 -q
uv run pytest tests/layer0 -q
```

Tests of layers above this one fail until they are built; that is expected. Then try it on the main example. With the seeded modules adopted, each calculation step of the wedding plan shows `N examples · N/N`. If you are stuck, `uv run python -m workshop finish 2` restores the finished layer from git (your files are set aside first).

When you think you are done, report briefly: the files you created, the test results, and anything in the contract you found unclear or had to guess.
