# How each stored state was made

This file is a log for a maintainer. History is never read at run time
(DESIGN section 11): the states in this folder are maintained by hand, and
this says how they were made the first time (DESIGN section 10), so that a
later change can be told from a forward-port.

Only harness, given and example files are stored per state. `SPEC.md` and
the tests of every state are the finished tree's (DESIGN section 1); the
first version of these states also stored older tests and a SPEC per state,
and that part was dropped when the tests were cut to 470 and made true at
every step from their own.

Words used below. `R` is the restructuring commit `0616545`. `E` is a
step-end commit. "From E" means `git archive E harness examples reference`.
"Taken from R" means the file of R, byte for byte, used because no commit
between E and R touched that file. Every state was built by one script
(`git archive`, then the steps below, then `store`), never by copying into
`states/` by hand.

## Every state: the restructuring (F4)

The restructured paths and defaults of `harness/` and `examples/`: see the
rows of each state below. Not taken: the old root `data/`, `brief/` and
`modules/`.

## 0-done (from `4426932`)

| What | Why | From |
| --- | --- | --- |
| `harness/model/__init__.py`, `harness/model/providers.py`: `resolve_provider`, the `auto` entry, `NO_PROVIDER`, `MISSING_PACKAGE` | F1, automatic provider and plain provider errors | `git diff 4426932 c28b41a` on those files |
| `harness/config.py`: `HARNESS_MODEL_PROVIDER` defaults to `auto` | F1 (the default only) | `c28b41a` |
| `harness/__main__.py`: `check()` prints the provider that was used (`resolve_provider`) | F1 (the `check()` hunks only) | `c28b41a` |
| `harness/config.py`: `HARNESS_DB` defaults to `my/var/harness.db` | F4 | R |
| `TOOL_RULES` in `harness/model/claude_code_provider.py` | F2, the reworded Claude Code tool rules | `c28b41a` (copied from R: the block is the same) |

## 1-done (from `f8da442`)

The same F1, F2 and F4 ports as `0-done` (the files they touch are the same
bytes in both states, except `config.py`, `__main__.py` and
`claude_code_provider.py`, which step 1 changes: the ports were applied by
text edit to those three). Plus:

| What | Why | From |
| --- | --- | --- |
| `harness/config.py`: `HARNESS_BRIEF_DIR` defaults to `my/brief` | F4 | R |
| `harness/__main__.py`: `LEGACY_COMMANDS`, `LEGACY_LAYOUT`, `legacy_layout()` and the check after `parse_args()`; imports `os` and `Path` | F4 (SPEC 4.5) | R |

## 2-done (from `c28b41a`)

`c28b41a` already holds F1 and F2 (it is where they were made). Plus F4:

| What | From |
| --- | --- |
| `harness/config.py`: `my/var/harness.db`, `my/brief`, `my/modules` | R |
| `harness/__main__.py`: the older-copy check (as in `1-done`) | R |

`2-build` holds `harness/calc/safety.py` and `harness/calc/runner.py` of
`bb7ccb0`. Nothing in them needed the restructuring.

## 3-done (from `a793043`)

| What | Why | From |
| --- | --- | --- |
| Example mode on a copy: `EXAMPLE_COPIES`, `EXAMPLE_COPIED`, `copy_example()` and its call in `main()`; the older-copy check; `REPLAY_DIR = "my/var/replay"` | F4 (SPEC 6.2, 6.5, 4.5) | R's hunks, written as text edits on `a793043`'s `__main__.py` and `replay.py`; `config.py` taken from R |
| `examples/README.md`: the wedding brief is no longer `brief/`, the copy in example mode, `my/var/replay` | F4 | the hunks of R that apply; the paragraph about `tests/fixtures/accounts/` belongs to step 5 and is not in this state |

## 4-done (from `0129b62`, then `36c0f51`)

| What | Why | From |
| --- | --- | --- |
| `harness/calc/analyst.md`: the bullet "Never put a figure or a date of your own in a question ..." | F3 | `36c0f51`; not its step 5 hunks, not `verifier.md`, not its SPEC section 9 |
| `harness/calc/aside.md`: "do not lean" at a choice | F3 and decision 12 | `c1eeef0` |

The `analyst.md` bullet is in `4-done` only, as DESIGN 10.3 says. It is not in
`2-done` or `3-done`, though it applies to the agent there too. The same
goes for the `aside.md` line, which does not exist before step 4.

## What was read and left alone

- `evidence.html` of `0129b62` against R: the 28 hunks are the Data view,
  findings, the `data` label and the extra tab, all step 5. Nothing ported.
- The commits between each step end and R, file by file (`git log E..R --
  <file>`): every file listed is in the manifest as a later step's `changed`
  or `given` entry, or is one of F1 to F4 above. No other fix was found.
- Not ported on purpose: the F3 `analyst.md` bullet to `2-done` and
  `3-done` (above).

## Second pass: tests made true at every step, one SPEC

When the suite was cut to 470 tests, every test was made true at the end of
its own step and every later one, and states stopped storing tests and SPEC
(DESIGN section 1). The overlays lost their `tests/` and `SPEC.md` files and
their absent lists lost those paths (3, 4, 8, 13 and 10 harness, example and
reference files remain for `0-done` to `4-done`); `finished/` was refreshed
from `main` (`store finished .`), so it holds today's tests. The manifest lost
`red_at_start` and every tests/`SPEC.md` entry of `given`; the entries that
`check` had added for revised earlier tests (`test_legacy_layout.py`,
`test_writes_only_under_my.py`, the helper files) went with them.

`check` then found four tests that broke the rule. Each was fixed on the
finished tree:

| State | Test | Problem | Change |
| --- | --- | --- | --- |
| `0-done`, `1-build` | `tests/step0/test_config.py::test_the_defaults_are_under_my` | asserted `brief_dir`, a step 1 setting | step 0 keeps the database default (`test_the_database_default_is_under_my`); the brief default moved to `tests/step1/test_legacy_layout.py::test_the_brief_default_is_under_my` |
| `3-done`, `4-build` | `tests/step3/test_evidence_events.py::test_a_limit_gives_that_many_and_more` | expected event ids 50 to 41; later steps add events to the replay | expects the ten newest ids counted down from the newest stored id |
| `5-build` | `tests/step4/test_seeded_examples.py::test_every_scenario_still_loads_and_validates` | loaded every scenario in `examples/`, including step 5's, which use keys (`verify`, `data`, `findings`) the step 4 `replay.py` rejects; `5-build` has step 5's scenarios and step 4's code | loads the ten scenarios that exist at step 4 (named in the test) |

No snapshot lacked a forward-port and no file moved between steps: the
harness, example and reference overlays of the first pass passed unchanged.
