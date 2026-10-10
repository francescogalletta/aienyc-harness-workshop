# How each stored state was made

This file is a log for a maintainer. History is never read at run time
(DESIGN section 11): the states in this folder are maintained by hand, and
this says how they were made the first time (DESIGN section 10), so that a
later change can be told from a forward-port.

Words used below. `R` is the restructuring commit `0616545` (the finished
tree). `E` is a step-end commit. "From E" means `git archive E SPEC.md
harness tests examples reference` (the names the commit has), extracted as
the starting point. "Taken from R" means the file of R, byte for byte, used
because no commit between E and R touched that file, so R's version is E's
plus the restructuring and nothing else. Every state was built by one script
(`git archive`, then the steps below, then `store`), never by copying into
`states/` by hand.

## Every state: the restructuring (F4)

For every `N-done`:

- `tests/fixtures/accounts/` (the account files, their generator and key, moved
  from `data/`), `tests/data/test_example_data.py` (new paths) and
  `tests/step0/test_layout.py` (new): taken from R. The old root `data/`,
  `brief/` and `modules/` are not taken.
- Every file of the state that no commit after E touched (apart from R) is
  taken from R. That is how `config.py`, `test_config.py`, `test_registry.py`,
  the `tests/step3` and `tests/step4` conftest files and the replay tests got
  their `my/var/...` paths in `3-done` and `4-done`.
- `SPEC.md` (DESIGN 10.4): built from the step-end SPEC, not by pruning R's.
  Applied, in this order: the fixes of F1 where the state lacks them; R's
  hunks (`git diff c1eeef0 R -- SPEC.md`, 23 hunks) for the features the
  state has, by `patch`; and by hand the introduction, the status table (one
  row per section of the state, each "Fixed, covered by `tests/step<N>`", and
  the line about `tests/data`), ground rules 1.2, 1.8 and 1.9, and section 2
  (the three places, the layout cut to the state's folders, "An older copy"
  from step 1). The draft section for the later steps at the end of the
  step-end SPEC is cut (its heading would break the `spec` check).
  Hunks of R that were not taken: those for sections the state does not have;
  the step-marked passages ("(step 4)", "(step 5)") in R's rule 1.2 and
  section 6; R's hunks 18 to 23 where the section is a later step's.
  Unmarked changes of later steps that were kept out: ground rule 1.4's
  step 5 wording, "five read endpoints" and "seven keys" (step 5), "(for
  `run` and, step 5, `data`)".
- The older-copy check (SPEC 4.5) mentions "(5.10, 6.7, 7.7)" in every state
  from step 1 on, because the tuple `LEGACY_COMMANDS` names the commands of
  later steps (DESIGN decision 16). In `1-done` and `2-done` those sections do
  not exist yet; the sentence is kept as it is in R.

## 0-done (from `4426932`)

| What | Why | From |
| --- | --- | --- |
| `harness/model/__init__.py`, `harness/model/providers.py`: `resolve_provider`, the `auto` entry, `NO_PROVIDER`, `MISSING_PACKAGE` | F1, automatic provider and plain provider errors | `git diff 4426932 c28b41a` on those files |
| `tests/step0/test_model.py`: the `auto` tests, the table with `auto`, `resolve_provider` in `__all__` | F1 | same diff |
| `harness/config.py`: `HARNESS_MODEL_PROVIDER` defaults to `auto` | F1 (the default only) | `c28b41a` |
| `harness/__main__.py`: `check()` prints the provider that was used (`resolve_provider`) | F1 (the `check()` hunks only) | `c28b41a` |
| `tests/step0/test_config.py`: `auto` | F1 | `c28b41a` |
| `TOOL_RULES` in `harness/model/claude_code_provider.py` | F2, the reworded Claude Code tool rules | `c28b41a` (copied from R: the block is the same) |
| `tests/step0/test_claude_code_adapter.py` | F2 | `git diff 4426932 c28b41a` |
| `harness/config.py`: `HARNESS_DB` defaults to `my/var/harness.db`; `tests/step0/test_config.py`: the same, and one new test of it | F4 | R |
| SPEC: the `auto` text of 3.1, 3.2, 3.7 and the tool-rules text of 3.8 | F1 and F2 | hunks 4 to 9 of `git diff 4426932 c28b41a -- SPEC.md` |
| SPEC rule 1.4: "(these come in a later step)" in place of the pointer to a draft section | the draft section is not in the state; `c28b41a` reworded it the same way | `c28b41a` |

The new test of the database default is the same in `0-done`, `1-done` and
`2-done` (it tests only `db_path`), so `tests/step0/test_config.py` is one
file in the three states. `3-done` has R's version (step 3 revises that file
anyway: it clears `HARNESS_EXAMPLE`).

`tests/step0/test_model.py` keeps R's `data/example` in the domain scan: R did
not change it (DESIGN 10.2 said it would). It is a substring check on
`harness/`, not a path.

## 1-done (from `f8da442`)

The same F1, F2 and F4 ports as `0-done` (the files they touch are the same
bytes in both states, except `config.py`, `__main__.py` and
`claude_code_provider.py`, which step 1 changes: the ports were applied by
text edit to those three). Plus:

| What | Why | From |
| --- | --- | --- |
| `harness/config.py`: `HARNESS_BRIEF_DIR` defaults to `my/brief` | F4 | R |
| `harness/__main__.py`: `LEGACY_COMMANDS`, `LEGACY_LAYOUT`, `legacy_layout()` and the check after `parse_args()`; imports `os` and `Path` | F4 (SPEC 4.5) | R |
| `tests/step1/test_legacy_layout.py` | F4 | R, with `AVAILABLE = ("ground", "ui")` and `PROBE = "ground"` added, because argparse refuses the other five commands before the check; the `returncode == 0` lines are dropped (`ground` ends 1 with no input) |

## 2-done (from `c28b41a`)

`c28b41a` already holds F1 and F2 (it is where they were made). Plus F4:

| What | From |
| --- | --- |
| `harness/config.py`: `my/var/harness.db`, `my/brief`, `my/modules` | R |
| `harness/__main__.py`: the older-copy check (as in `1-done`) | R |
| `tests/step0/test_config.py` (as in `0-done`), `tests/step2/test_registry.py` (`my/modules`) | R |
| `tests/step1/test_legacy_layout.py` with `AVAILABLE = ("ground", "ui", "build", "modules", "ask")`, `PROBE = "modules"` | R, adapted as in `1-done` |

`2-build` holds `harness/calc/safety.py` and `harness/calc/runner.py` of
`bb7ccb0`. Nothing in them needed the restructuring.

## 3-done (from `a793043`)

| What | Why | From |
| --- | --- | --- |
| Example mode on a copy: `EXAMPLE_COPIES`, `EXAMPLE_COPIED`, `copy_example()` and its call in `main()`; the older-copy check; `REPLAY_DIR = "my/var/replay"` | F4 (SPEC 6.2, 6.5, 4.5) | R's hunks, written as text edits on `a793043`'s `__main__.py` and `replay.py`; `config.py` taken from R |
| `tests/step3/test_example_selector.py` | F4 | `git diff c1eeef0 R` (the one step 5 line of that file, `h.no_findings()`, is not in this state) |
| `tests/step3/test_example_copy.py`, `tests/step3/test_writes_only_under_my.py`, `tests/step1/test_legacy_layout.py` | F4 | R; in `test_writes_only_under_my.py` the script of the `ask` is `script(s3.ask_script())`, without the step 5 `h.no_findings()` reply that the verifier asks for |
| `examples/README.md`: the wedding brief is no longer `brief/`, the copy in example mode, `my/var/replay` | F4 | the hunks of R that apply; the paragraph about `tests/fixtures/accounts/` belongs to step 5 and is not in this state |

## 4-done (from `0129b62`, then `36c0f51`)

| What | Why | From |
| --- | --- | --- |
| All of `examples/`, and `tests/step4/test_seeded_examples.py` | the step 4 scenarios and docs | `36c0f51` (before the step 5 data and scenarios of `c1eeef0`) |
| `harness/calc/analyst.md`: the bullet "Never put a figure or a date of your own in a question ..." | F3 | `36c0f51`; not its step 5 hunks, not `verifier.md`, not its SPEC section 9 |
| `harness/calc/aside.md`: "do not lean" at a choice | F3 and decision 12 | `c1eeef0` |
| SPEC: "prompts/step4_human_in_the_loop.md" in the files table; the sentence about the moving example's opening line in 8.8 | the two unmarked step 4 hunks of `36c0f51` | `36c0f51` |
| Everything of `3-done`'s F4 list, applied to `0129b62`'s `__main__.py`, `replay.py` and `examples/README.md`; `tests/step4/conftest.py` taken from R | F4 | as `3-done` |

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

## Manifest additions found by `check` (DESIGN 4.3 had no row for them)

- `tests/step1/test_legacy_layout.py` is in the `given` of steps 2 and 3: the
  commands it runs arrive in those steps, so it differs in `2-done` and
  `3-done`.
- `tests/step3/test_writes_only_under_my.py` is in the `given` of step 5: the
  verifier's first model reply (`h.no_findings()`) arrives with it.
- `red_at_start` of step 5 holds `tests/step2/test_agent.py`,
  `tests/step3/test_evidence_functions.py` and
  `tests/step3/test_evidence_summary.py`: they use `ASK_DECISION_SCHEMA` of
  `step2_helpers.py` and the summary keys of `step3_evidence_helpers.py`, both
  of which step 5 changed.
