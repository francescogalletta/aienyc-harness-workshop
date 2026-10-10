# The `workshop` command: design

This is the contract of the workshop tool, the way `SPEC.md` is the
contract of the harness. It covers the step machinery: the manifest, the
stored snapshots, the commands and the drift check. The harness side of
the restructuring (the three places, `my/`, the new defaults, the message
for an older copy) is in `SPEC.md`, sections 1, 2, 4.5, 6.2 and 6.5.

The workshop is not built to help someone write an entirely different
harness from scratch in two hours. Variations on the main example follow
along best.

## 1. What it does, and what it never does

`python -m workshop` moves this copy of the repository between twelve
**states**: for each step N from 0 to 5, **the start of step N**
(`N-build`) and **the end of step N** (`N-done`). A fresh clone is `5-done`,
the finished harness.

- `N-done`: `SPEC.md`, code, tests and examples exactly as they are when
  step N is complete, with every later fix that applies to them.
- `N-build`: `N-1-done`, plus step N's contract, tests and given files.
  Step N's tests fail; the earlier steps' tests pass (with the exceptions
  the manifest lists, 4.3). `0-build` has no harness code at all.

It only copies, removes and sets aside files under the **managed roots**:
`SPEC.md`, `harness/`, `tests/`, `examples/` and `reference/`. It never calls
a model, never touches `my/` (except to write into `my/var/set-aside/`),
`.git/`, `.venv/`, `workshop/` itself, `README.md`, `pyproject.toml`,
`uv.lock`, `.gitignore` or `.python-version`, and never runs `git`.

The harness never imports or reads `workshop/` (SPEC ground rule 9). The
workshop imports nothing from `harness/` either: it reads files as bytes.

## 2. Package layout

```
workshop/
  __init__.py        a docstring only
  __main__.py        the command line: argparse, the commands, every printed constant
  states.py          the manifest, the stored states, resolving, materialising, setting aside, where the copy stands
  checks.py          the drift check (section 9)
  manifest.json      which files belong to which step (section 4)
  states/            the stored snapshots (section 5)
  tests/             the workshop's own tests (section 12)
  prompts/           the build prompts, step0_setup.md to step5_verification.md
  BUILD_PLAN.md, README.md, FACILITATOR.md, DESIGN.md
```

Standard library only. `python -m workshop ...` works from the repository
root with no install, because `workshop/` is a package in the current
folder. Every path is resolved from `ROOT = Path(__file__).resolve().parent.parent`,
not from the current folder, so it also works from elsewhere. Paths in the
manifest and in the stored files are written with `/`, relative to `ROOT`.

## 3. Words used below

- **Ignored names.** A path with a part named `__pycache__` or
  `.pytest_cache`, or a name ending in `.pyc`, is never read, compared,
  copied, stored or removed.
- **The tree.** The files under the managed roots of a folder, minus ignored
  names. Hidden files count (`examples/wedding/data/.generate.py`).
- **`content(S, p)`**: the bytes of path `p` in state `S`, or `None` when `S`
  has no such file (section 6).
- **Known paths `U`**: every path that some state has. A path outside `U` is
  never touched by any command: it is the person's own extra file.
- **Known versions of `p`**: the set of `content(S, p)` over all twelve
  states, `None` left out.
- **Code paths**: every path listed in `built`, `start` or `changed` of any
  step. These are the files a person building their own harness writes.
- **Contract files**: `U` minus the code paths: `SPEC.md`, tests, fixtures,
  given files and examples.

## 4. The manifest: `workshop/manifest.json`

### 4.1 Format

JSON, UTF-8, written with `json.dumps(value, indent=2, ensure_ascii=False) + "\n"`.

```
{"format": 1,
 "roots":  ["SPEC.md", "harness/", "tests/", "examples/", "reference/"],
 "always": ["tests/data/"],
 "steps":  [<step>, <step>, <step>, <step>, <step>, <step>]}       steps 0 to 5, in order

<step> = {"step":    <int, its index>,
          "name":    "<short name>",
          "prompt":  "workshop/prompts/<file>.md",
          "tests":   "tests/step<N>/",
          "built":   ["<file>", ...],      new code the person writes in this step
          "start":   ["<file>", ...],      new code given in a starting form; the person changes it in this step
          "changed": ["<file>", ...],      code of an earlier step that the person changes in this step
          "given":   ["<file or folder/>", ...],   contract, tests, given files and data this step installs, new or revised
          "red_at_start": {"<test file>": "<one-line reason>", ...}}
```

- An entry ending in `/` is a folder: it stands for every known path below
  it. In `given`, it means "make this folder match `N-done`": add, replace
  and remove known paths below it.
- `built`, `start` and `changed` hold files only, all under `harness/`.
- `always`: test folders that hold in every state (the account-file
  fixture's tests). They are run with the earlier steps' tests.
- `red_at_start`: earlier-step test files (not under `tests/step<N>/`) that
  may fail in `N-build`, beyond the test files `given` lists (which are
  never run in `N-build`). Each needs a reason, for example "uses
  `ASK_DECISION_SCHEMA` from `step2_helpers.py`, which step 5 changed". It
  starts empty and is filled only from what `check` shows.

### 4.2 Rules (checked by `check`, section 9.1)

1. Every known path is **introduced** by exactly one step, through one of
   its `built`, `start` or `given` entries (a `given` folder counts). A
   later step may list it again: in `given` when the step revises it, in
   `changed` when the person changes it. `SPEC.md` is introduced by step 0
   and revised by every later step. "Introduced by step K" means: absent in
   every state before `K-build`; absent in `K-build` too when `built`;
   present in `K-done`.
2. A `changed` path of step K was introduced by an earlier step through
   `built` or `start`. No code path is in any step's `given`.
3. Between `K-1-done` and `K-done` (for K = 0, between the empty tree and
   `0-done`), every path whose content differs is in `built`, `start`,
   `changed` or `given` of step K. Each file entry of those lists does
   differ, and each `given` folder has at least one path that differs. So
   the manifest explains every change, and lists nothing stale.
4. Every `built` path of step N appears in the text of that step's
   prompt, as written, or through its folder written with a final `/`
   (step 0's prompt names `harness/model/`). Step 2's prompt did not name
   `harness/calc/added.py` or `harness/migrations/0005_added_steps.sql`; it
   now does.

### 4.3 Initial content

Derived from the history (`git diff --name-status` between the step ends
of section 10) and from the files tables of `SPEC.md` sections 5 and 7 to 9.
Fixes forward-ported to earlier states (section 10.3) make a file the same
in two states, so they appear in no list. `SPEC.md` is in every step's
`given`.

| Step | Prompt | Built by the person | Given in a starting form (`start`) | Changed by the person | Given (installed by the step) |
| --- | --- | --- | --- | --- | --- |
| 0 setup | `step0_setup.md` | `harness/__init__.py`, `harness/config.py`, `harness/db.py`, `harness/migrations/0001_init.sql`, `harness/model/__init__.py`, `harness/model/interface.py`, `harness/model/scripted.py`, `harness/model/anthropic_provider.py`, `harness/model/providers.py`, `harness/model/claude_code_provider.py`, `harness/__main__.py` | | | `SPEC.md`, `tests/step0/` (with the new `test_layout.py`), `tests/data/`, `tests/fixtures/accounts/` |
| 1 shared domain | `step1_shared_domain.md` | `harness/grounding/__init__.py`, `harness/grounding/brief.py`, `harness/grounding/claude_code_research.py`, `harness/grounding/interview.py`, `harness/grounding/research.py`, `harness/migrations/0002_lookups.sql`, `harness/ui/__init__.py`, `harness/ui/server.py`, `harness/ui/session.py` | | `harness/config.py`, `harness/__main__.py`, `harness/model/claude_code_provider.py` | `SPEC.md`, `tests/step1/`, `harness/grounding/interviewer.md`, `harness/grounding/researcher.md`, `harness/grounding/planner.md`, `harness/ui/grounding.html`, `reference/` |
| 2 consistency | `step2_consistency.md` | `harness/calc/__init__.py`, `harness/calc/registry.py`, `harness/calc/notes.py`, `harness/calc/added.py`, `harness/calc/gate.py`, `harness/calc/builder.py`, `harness/calc/provenance.py`, `harness/calc/agent.py`, `harness/migrations/0004_notes.sql`, `harness/migrations/0005_added_steps.sql` | `harness/calc/safety.py`, `harness/calc/runner.py` | `harness/config.py`, `harness/__main__.py` | `SPEC.md`, `tests/step2/`, `harness/calc/values.py`, `harness/calc/spec_writer.md`, `harness/calc/example_writer.md`, `harness/calc/example_helper.md`, `harness/calc/module_writer.md`, `harness/calc/analyst.md`, `harness/migrations/0003_calc.sql` |
| 3 evidence (with examples and replay) | `step3_evidence.md` | `harness/calc/adopt.py`, `harness/replay.py`, `harness/ui/evidence.py` | | `harness/config.py`, `harness/__main__.py`, `harness/calc/added.py`, `harness/calc/agent.py`, `harness/calc/provenance.py`, `harness/ui/server.py` | `SPEC.md`, `tests/step3/`, `harness/ui/evidence.html`, `harness/ui/grounding.html` (revised: a link to `/work`), `examples/README.md`, `examples/moving/`, `examples/wedding/`; earlier tests revised: `tests/step0/conftest.py`, `tests/step0/test_config.py`, `tests/step1/conftest.py`, `tests/step1/test_ui_cli.py`, `tests/step2/conftest.py`, `tests/step2/test_gate.py`, `tests/step2/test_request_decision.py` |
| 4 human in the loop | `step4_human_in_the_loop.md` | `harness/migrations/0006_decisions.sql`, `harness/calc/decisions.py`, `harness/calc/aside.py` | | `harness/calc/agent.py`, `harness/__main__.py`, `harness/replay.py`, `harness/ui/evidence.py` | `SPEC.md`, `tests/step4/`, `harness/calc/aside.md`, `harness/calc/analyst.md` (revised), `harness/ui/evidence.html` (revised), `examples/README.md`, `examples/moving/scenarios/`, `examples/wedding/scenarios/`; earlier tests revised: `tests/step2/step2_helpers.py`, `tests/step2/test_agent.py`, `tests/step2/test_request_module.py`, `tests/step3/test_evidence_conversation.py`, `tests/step3/test_evidence_events.py`, `tests/step3/test_evidence_page.py`, `tests/step3/test_evidence_summary.py`, `tests/step3/test_scenario_validation.py` |
| 5 verification | `step5_verification.md` | `harness/migrations/0007_data.sql`, `harness/sources/__init__.py`, `harness/sources/adapter.py`, `harness/sources/summaries.py`, `harness/calc/findings.py`, `harness/calc/verifier.py` | | `harness/calc/agent.py`, `harness/calc/decisions.py`, `harness/calc/provenance.py`, `harness/replay.py`, `harness/ui/evidence.py`, `harness/ui/server.py`, `harness/__main__.py` | `SPEC.md`, `tests/step5/`, `harness/calc/verifier.md`, `harness/calc/analyst.md` (revised), `harness/ui/evidence.html` (revised), `examples/README.md`, `examples/wedding/data/`, `examples/wedding/scenarios/`; earlier tests revised: `tests/step2/step2_helpers.py`, `tests/step2/test_added_cli.py`, `tests/step2/test_calc_cli.py`, `tests/step3/step3_evidence_helpers.py`, `tests/step3/test_evidence_page.py`, `tests/step3/test_example_selector.py`, `tests/step3/test_trace_function.py`, `tests/step3/test_unadopted_check.py`, `tests/step4/step4_helpers.py`, `tests/step4/test_aside_terminal.py`, `tests/step4/test_decisions_records.py`, `tests/step4/test_evidence_decisions.py`, `tests/step4/test_seeded_examples.py` |

Notes on the table:

- Every step's `prompt` is `workshop/prompts/<the file above>`, and `tests`
  is `tests/step<N>/`. `red_at_start` is `{}` for every step except 5.
- Additions that `check` found necessary (the table above had no row for
  them): `tests/step1/test_legacy_layout.py` is in the `given` of steps 2
  and 3 (the commands it runs arrive then); `tests/step3/test_writes_only_under_my.py`
  is in the `given` of step 5 (the verifier's first reply arrives then).
  `red_at_start` of step 5 holds `tests/step2/test_agent.py`,
  `tests/step3/test_evidence_functions.py` and
  `tests/step3/test_evidence_summary.py`, which use `ASK_DECISION_SCHEMA` of
  `step2_helpers.py` and the summary keys of `step3_evidence_helpers.py`,
  both of which step 5 revised.
- Step 0's `given` holds the account-file fixture and its tests, which pass
  with no harness code.
- Step 2's `safety.py` and `runner.py` are the only `start` files: SPEC 5.2
  and 5.3 give them, each with one change for the person to make. Their
  starting form is the one of commit `bb7ccb0`, restructured.
- Step 3's earlier-test revisions are step 3's own (clearing
  `HARNESS_EXAMPLE`, the `example` field, the `/work` line, the `adopt`
  reason). The restructuring changes some of the same files in every
  state; that is not a step 3 change.
- `harness/calc/aside.md` is not in step 5's `given`: its one later change
  (commit `c1eeef0`, "stays neutral at a choice") is forward-ported to
  `4-done` as a prompt fix.
- `harness/calc/verifier.md` came with the step 5 contract (commit
  `36c0f51`); it is step 5's, absent from `4-done`.
- `README.md` and the root files are not in the manifest: they are the same
  in every state (decision 6).

If `check` rule 3 finds a difference that this table does not explain, the
table is wrong or the snapshot is: fix whichever the history says.

## 5. Stored snapshots: `workshop/states/`

```
workshop/states/
  finished/<path>            a full copy of the tree of 5-done: every file under the managed roots
  <N>-done/files/<path>      for N = 0 to 4: the files of N-done whose content differs from finished/
  <N>-done/absent.json       for N = 0 to 4: the sorted list of paths of finished/ that N-done does not have
  <N>-build/files/<path>     only where a step has `start` files (today only 2-build): their starting form
```

- `absent.json` is a JSON list of strings, written like the manifest.
- An overlay file never equals the `finished/` file at the same path, and
  `absent.json` names only paths of `finished/` (both checked, 9.1).
- `N-build` is not stored: it is derived (section 6). `<N>-build/files/`
  holds exactly the `start` paths of step N, nothing else.
- Built size: 6 overlay files in `0-done`, 10 in `1-done`, 22 in `2-done`,
  29 in `3-done`, 25 in `4-done`, and 2 in `2-build`, `SPEC.md` included.
  `finished/` holds 257 files (3.2 MB).

## 6. The content of a state

```
content("5-done", p)  = finished/p, or None
content("N-done", p)  = N-done/files/p                    if stored there
                      = None                              if p is in N-done/absent.json
                      = finished/p, or None               otherwise
content("N-build", p) = N-build/files/p                   if p is in start(N)
                      = content("N-done", p)              if p is in given(N), folders expanded over U
                      = content("N-1-done", p)            otherwise; for N = 0, None
```

`U` is the union of the paths of `finished/`, of every overlay, and of
every `absent.json`. A state is resolved in memory as a map from path to
bytes; nothing is cached on disk.

## 7. Materialising a state

### 7.1 Into the working tree (`start`, `finish`, `next`)

`apply(target_map, paths)`, where `paths` is `U` for `start` and `finish`,
and the paths `next` installs (8.4) for `next`. For each path `p` in
`paths`, sorted:

1. `want = target_map[p]` (or `None`); `have` = the bytes of `ROOT/p`, or
   `None` when it is not a file.
2. If `want == have`: nothing.
3. Otherwise, when `have` is not `None` and is not one of the known
   versions of `p`, **set it aside** (7.3) first.
4. Write `want` (creating parent folders), or, when `want` is `None`,
   remove the file and then every parent folder that is now empty, up to
   but not including its managed root. A folder that holds only ignored
   names (`__pycache__`) is not removed.

If `ROOT/p` is a folder where a file should be, or the other way round, the
command stops before writing anything and prints `IN_THE_WAY` (8.8), exit 1.
All decisions are made first and all writes after, so a refusal changes
nothing.

Never touched, whatever happens: paths outside the managed roots (`my/`
except `my/var/set-aside/`, `workshop/`, `.git/`, `.venv/`, root files),
ignored names, and paths outside `U`.

### 7.2 Into a temporary folder (`check`, `export`)

`tempfile.mkdtemp(prefix="workshop-<state>-")`. Write every path whose
content is not `None`. Copy `ROOT/pyproject.toml` beside them (pytest's
settings). Nothing else. For `export`, the same into the given empty folder,
without `pyproject.toml`.

### 7.3 Setting aside

A file is set aside when a command would replace or remove it and its bytes
match no known version of its path, so the person changed it (or wrote it).
A file equal to some known version can always be had again, so it is not
copied.

- Folder: `my/var/set-aside/<stamp>/`, where `<stamp>` is the local time at
  the start of the command, `YYYY-MM-DD_HH-MM-SS`. If that folder exists,
  `_2`, `_3`, ... is added. One folder per command run, made only when
  something is set aside.
- The file is copied (bytes and modification time, `shutil.copy2`) to
  `my/var/set-aside/<stamp>/<p>`, before anything is written.
- One line per file: `SET_ASIDE` (8.8).

Nothing is ever deleted without a copy, except files equal to a known
version.

## 8. The commands

`python -m workshop <command>`. Exit codes: 0 done; 1 refused or failed; 2
wrong usage (argparse). `N` must be one of `0` to `5`, else `BAD_STEP` to
standard error, exit 2. Before any command, `manifest.json` and
`states/` are loaded; if a file is missing or not valid JSON, it prints
`DATA_BROKEN` to standard error and exits 1. All output lines are the
constants of 8.8, on standard output unless said.

### 8.1 Where the copy stands (no state file)

The tree is the state: nothing is recorded about it. `where()` returns:

- **exact**: the state `S` whose content equals the tree over all of `U`
  (paths outside `U` ignored), if any. Search order: `0-build`, `0-done`,
  ..., `5-done`; the first that matches.
- **contract**: the highest N for which every contract file (section 3)
  has `content("N-done", p)` in the tree (`None`: absent). `None` when no
  N fits. Code paths are not compared, so a person's own code, even a file
  of a later step written early, never hides the contract.
- **own code**: when the contract is N, the code paths whose bytes differ
  from `content("N-done", p)`.
- **closest**: when no N fits, the N with the fewest contract files that
  differ, and those paths (ties: the higher N).

`N-build` and `N-done` share their contract files, so a person's own copy
is "the contract of step N, with your own code", and the tests tell
whether step N is built.

### 8.2 `status [--quick]`

1. Prints where the copy stands: `STATUS_EXACT` with the label of the
   state, or `STATUS_CONTRACT` and `STATUS_OWN_CODE`, or `STATUS_NO_MATCH`.
2. Without `--quick`: `STATUS_TESTS_INTRO`, then for each `tests/step<K>/`
   folder present in the tree, in order, it runs
   `sys.executable -m pytest -q -p no:cacheprovider tests/step<K>`
   (for K = 0 with the `always` folders added) in `ROOT`, with
   `PYTHONDONTWRITEBYTECODE=1`, and prints `STATUS_TEST_LINE`. `<result>`
   is `pass` for exit 0, else `FAIL: <pytest's last output line, stripped>`.
   With `--quick`: `STATUS_TESTS_SKIPPED`. If pytest cannot be run
   (`python -c "import pytest"` fails): `NO_PYTEST` and no test lines.
3. The hint: at `N-build`, `HINT_BUILD`; at `N-done`, `HINT_NEXT`
   (`HINT_FINISHED` for 5); with own code, `HINT_NEXT` when step N's line
   is `pass`, `HINT_BUILD` when it failed, and with `--quick` both
   `HINT_BUILD` and `HINT_WHEN_GREEN`; with no match, `HINT_NO_MATCH`.

Exit 0, also when tests fail or nothing matches.

### 8.3 `start N` and `finish N`

`apply(state map of N-build or N-done, U)`. Then `APPLIED`, then:

- `start N`: `START_DONE` (`START_DONE_ZERO` for 0), then `HINT_BUILD`.
- `finish N`: `FINISH_DONE`, then `HINT_NEXT` (`HINT_FINISHED` for 5).

When nothing had to change, `ALREADY` instead of `APPLIED`. Exit 0. They
never refuse because of the person's changes: setting aside is the
protection (decision 4). They do not touch the database, `my/brief` or
`my/modules`.

### 8.4 `next`

For someone building their own code. It installs step N's contract, tests,
prompt and given files, and leaves their code alone.

1. `where()`. No contract: `NEXT_NO_MATCH` (with the closest step and up to
   five paths, then `and <k> more`), exit 1. Contract 5: `NEXT_LAST`,
   exit 1. Otherwise `L` is the contract and `N = L + 1`.
2. If any `built` path of step L is missing from the tree:
   `NEXT_UNFINISHED`, exit 1. (It does not run tests: a step that is
   there but red is the person's to judge; the hint says how.)
3. The paths installed are `given(N)`, folders expanded over `U`, plus
   `start(N)`. `apply(state map of N-build, those paths)`. No code path is
   in any `given` (rule 2), and the `start` paths of step N are new, so the
   person's code is untouched.
4. `NEXT_DONE`, then `HINT_BUILD`. Exit 0.

The prompt itself is in `workshop/prompts/`, which no state changes: it is
"installed" in the sense that `HINT_BUILD` names it.

### 8.5 `leave`

1. Prints `LEAVE_STATE` with where the copy stands (its exact state's label,
   or "the contract of step N with your own code", or "no step").
2. Asks `LEAVE_ASK` and reads one line. `yes` (stripped, lower-cased)
   removes `ROOT/workshop` with `shutil.rmtree` and prints `LEAVE_DONE`.
   Anything else, or the end of input, prints `LEAVE_KEPT`. Exit 0 both.

It sets nothing aside: `workshop/` is ours, and git brings it back. It does
not change the harness, so a copy left at `2-build` stays there.

### 8.6 `check [STATE ...] [--keep]`

The drift check, section 9. With state names (`0-build` ... `5-done`), only
those states run; the static checks always run. `--keep` keeps each
temporary folder and prints its path.

### 8.7 For maintainers: `export STATE DIR` and `store STATE DIR`

- `export STATE DIR` writes the state into `DIR`, which must not exist or be
  empty (`DIR_NOT_EMPTY`, exit 1). `STATE` may also be `finished`.
- `store STATE DIR` reads the tree of `DIR` and stores it as that state:
  - `N-done` (N from 0 to 4): rewrites `N-done/files/` and `absent.json`
    against `finished/`, so that `content("N-done", p)` equals the tree of
    `DIR` for every path. Overlay files equal to `finished/` are not kept.
  - `N-build`: `DIR` is a full tree (`export N-build DIR`, then replace the
    start files). Every path whose content in `DIR` differs from the derived
    `N-build` (section 6, without the overlay) must be in `start(N)`;
    otherwise `STORE_NOT_START` lists them and nothing is stored, exit 1.
    Stores those files.
  - `finished` (also `5-done`): first resolves every other state with the
    old `finished/` and keeps it: after replacing `finished/` with the tree
    of `DIR`, it rewrites every overlay so that no other state changes. It
    prints `STORE_PINNED` per overlay file this added. A fix to the finished
    tree therefore never reaches an earlier state by accident: removing
    those overlay files, or editing them, is a deliberate act (section 11).
  - Then `STORED`. Exit 0.

These two are not in the attendee guide.

### 8.8 Printed lines

```
BAD_STEP          = "Steps are numbered 0 to 5."
DATA_BROKEN       = "The workshop data is incomplete: {reason}. Run: python -m workshop check"
IN_THE_WAY        = "{path} is a folder where the workshop needs a file, or a file where it needs a folder. Move it away and run the command again. Nothing was changed."
SET_ASIDE         = "Set aside your version of {path} in {copy}"

STATUS_EXACT      = "This copy is at {label}."
STATUS_CONTRACT   = "This copy has the contract of step {n}: SPEC.md, the tests and the given files of step {n}."
STATUS_OWN_CODE   = "Code: your own. {count} code files differ from the reference at the end of step {n}."
STATUS_NO_MATCH   = "This copy matches no step: the closest is step {n}, and these files differ from it: {paths}."
STATUS_TESTS_INTRO   = "Running the tests of each step. This takes a few minutes, about 6 for all six steps; --quick skips it."
STATUS_TEST_LINE     = "  step {k}: {result} ({seconds} s)"
STATUS_TESTS_SKIPPED = "Tests not run (--quick)."
NO_PYTEST         = "pytest is not installed here. Run the workshop with: uv run python -m workshop status"

HINT_BUILD        = "Next: paste {prompt} into your coding agent. Then run: uv run pytest tests/step{n}"
HINT_NEXT         = "Next: python -m workshop next  (step {m}'s contract, tests and given files; your code stays as it is)"
HINT_WHEN_GREEN   = "When the tests of step {n} pass: python -m workshop next"
HINT_FINISHED     = "This is the finished harness. To keep it without the workshop: python -m workshop leave"
HINT_NO_MATCH     = "Put those files back with git checkout -- <file>, or move the whole copy with: python -m workshop start N, or finish N"

APPLIED           = "{written} files written and {removed} removed in SPEC.md, harness/, tests/, examples/ and reference/. my/ was not touched."
ALREADY           = "This copy was already there. Nothing changed."
START_DONE        = "This copy is at the start of step {n}: the contract, tests and given files of step {n}, with the reference code at the end of step {prev}."
START_DONE_ZERO   = "This copy is at the start of step 0: the contract, tests and test fixture of step 0, and no harness code yet."
FINISH_DONE       = "This copy is at the end of step {n}: the reference code, tests and contract of step {n}."

NEXT_NO_MATCH     = "next needs a copy whose contract is that of a step. The closest is step {n}, and these files differ from it: {paths}."
NEXT_LAST         = "There is no step after step 5."
NEXT_UNFINISHED   = "Step {n} does not look built yet: these files are missing: {paths}. Build it with {prompt}, or take the reference with: python -m workshop finish {n}"
NEXT_DONE         = "Installed step {n}: {count} contract, test and given files. Your code was not touched."

LEAVE_STATE       = "This copy is at {label}."
LEAVE_ASK         = "This removes workshop/: the build plan, the prompts, the guides, the snapshots and this command. The harness, its tests and my/ stay as they are. Type yes to remove it."
LEAVE_DONE        = "Removed workshop/. If this copy is in git, commit the removal; git checkout -- workshop brings it back."
LEAVE_KEPT        = "Nothing removed."

CHECK_INTRO       = "Each state runs its tests in a temporary folder. All twelve take about 25 minutes."
CHECK_LINE        = "{name:<10} {mark}  {detail}"
CHECK_DONE        = "{passed} of {total} checks passed."

DIR_NOT_EMPTY     = "{dir} is not empty."
STORE_NOT_START   = "Only the start files of step {n} can differ from the derived start of step {n}, and these differ too: {paths}. Nothing was stored."
STORE_PINNED      = "Kept {state} as it was: stored its own {path}."
STORED            = "Stored {state}: {files} files in its overlay, {absent} absent."
```

- `{label}`: `the start of step N` (N-build) or `the end of step N`
  (N-done); `5-done` is `the end of step 5, the finished harness`.
- `{paths}`: up to five paths, joined by `, `, then ` and {k} more`.
- `{prev}` is N-1; `{m}` is N+1; `{prompt}` is the step's `prompt`.
- `{seconds}`: whole seconds.
- `{written}` counts writes, `{removed}` removals, of 7.1 step 4.

## 9. The drift check

`python -m workshop check` tells us when the stored states and the
finished tree have drifted apart in a way some test notices.

### 9.1 Static checks (seconds; one line each)

| Name | Passes when |
| --- | --- |
| `manifest` | `manifest.json` has the format of 4.1, and rules 1 and 2 of 4.2 hold |
| `snapshots` | every overlay file differs from `finished/`; every `absent.json` names only paths of `finished/`; every `N-build/files/` holds exactly `start(N)`; rule 3 of 4.2 holds for every step |
| `finished` | the working tree equals `finished/` over `U` (on `main`; after `start`, `next` or `finish` this line fails, and its detail says so) |
| `spec` | in every state, `SPEC.md` has no marker `(step M)` with M above the state's step, and no `## <k>.` heading beyond the state's last section (step 0: 3; 1: 4; 2: 5; 3: 7; 4: 8; 5: 9) |
| `prompts` | rule 4 of 4.2 holds for every step |

A failing static check prints up to five offending paths in its detail.

### 9.2 Per state (minutes; one line each)

Each state is materialised into its own temporary folder (7.2) and pytest
runs there, as in 8.2 (`sys.executable -m pytest -q -p no:cacheprovider`,
current folder the temporary one, `PYTHONDONTWRITEBYTECODE=1`, every
`HARNESS_*` variable removed from the environment). The static checks of 9.1
always run and do not gate the state runs; a check that raises is reported
as `FAIL`. Marks are `ok` and `FAIL`. An unknown state name is a usage
error, exit 2. `IN_THE_WAY` and the `NEXT_*` refusals go to stdout.

- **`N-done`**: run every test folder of the state. Passes on exit 0.
- **`N-build`**:
  - *earlier*: the `always` folders and `tests/step0/` to `tests/step<N-1>/`,
    with `--ignore=<p>` for every `test_*.py` path of `given(N)` under those
    step folders (not the `always` folders) and every key of `red_at_start` of step N. Must exit 0. For
    N = 0 only the `always` folders.
  - *this step*: `tests/step<N>/`. Must exit 1 (tests failed) or 2
    (collection errors, as when a module is missing). Exit 0 is a
    surprise ("step N passes before it is built"); 5 is a surprise ("step
    N's tests collected nothing").

`detail` is, for a pass, `every test passes (<pytest's last line>)` or
`earlier steps pass and step N fails, as it should`; for a failure, what
went wrong and up to three failing test ids (from `-rf` output lines that
start with `FAILED`). The state's line ends with `({seconds} s)`. The
temporary folder is removed unless `--keep`.

`CHECK_DONE` last. Exit 0 when every line passed, 1 otherwise.

### 9.3 What it cannot tell

- A fix made on the finished tree that no test notices in an earlier state:
  a reworded prompt (`analyst.md`), a page change in `evidence.html`, SPEC
  prose, `examples/README.md`. Such a fix is either pinned away from the
  earlier states by `store finished` or missing from them, silently.
- Whether an `N-build` can be built from its prompt by a coding agent. Only
  running the prompt tells.
- Whether `SPEC.md` in a state describes that state's code exactly, beyond
  the markers and section headings.
- Whether a test that should fail in `N-build` fails for the right reason.

## 10. Building the snapshots from history (one-off)

Do this after Part 1 of the restructuring is committed on `main` (call that
commit `R`): that tree is `5-done`. Work in a scratch folder outside the
repository. Store with `store` (8.7), never by hand-copying into `states/`.

### 10.1 Step ends

| State | Start from |
| --- | --- |
| `0-done` | `4426932` |
| `1-done` | `f8da442` |
| `2-done` | `c28b41a` |
| `3-done` | `a793043` |
| `4-done` | `0129b62`, then from `36c0f51`: all of `examples/`, `tests/step4/test_seeded_examples.py`, and the one step 4 hunk of `harness/calc/analyst.md` (the bullet "Never put a figure or a date of your own in a question ..."). Not its step 5 hunks of `analyst.md`, not `harness/calc/verifier.md`, not its SPEC section 9. |
| `5-done` | `R` (`store finished .`) |
| `2-build` | `harness/calc/safety.py` and `harness/calc/runner.py` from `bb7ccb0` |

For each, `git archive <commit> SPEC.md harness tests examples reference | tar -x -C <scratch>/<state>`
(drop the names a commit does not have). Root `brief/` and `modules/` are
not taken: they left the repository. `data/` is not taken: the fixture is
the same in every state (next step).

### 10.2 Apply the restructuring

In every state:

1. `tests/fixtures/accounts/` and `tests/data/test_example_data.py`: copy
   from `R`. Add `tests/step0/test_layout.py` from `R`.
2. Apply the hunks of `R` to each file the state has: `git diff <R's parent> R -- <file>`
   (if `R` is several commits, diff across all of them), then
   `patch -p1 -d <scratch>/<state>` or by hand where it does not apply,
   taking only the hunks for features the state has:

   | Change | From state |
   | --- | --- |
   | `HARNESS_DB` default `my/var/harness.db` (`config.py`, `tests/step0/test_config.py`) | 0 |
   | the domain scan of `tests/step0/test_model.py`: R did not change it (`data/example` stays; it is a substring check, not a path), so nothing to port | - |
   | `tests/step0/test_config.py` is one file in `0-done`, `1-done` and `2-done` (it tests only `db_path`); `tests/step1/test_legacy_layout.py` gets `AVAILABLE` and `PROBE` constants per state (1, 2); `tests/step3/test_writes_only_under_my.py` uses `script(s3.ask_script())` in `3-done` and `4-done` | 0-4 |
   | `HARNESS_BRIEF_DIR` default `my/brief`; `LEGACY_COMMANDS`, `LEGACY_LAYOUT` and their check in `main()` (SPEC 4.5), and its tests | 1 |
   | `HARNESS_MODULES_DIR` default `my/modules` (`tests/step2/test_registry.py`) | 2 |
   | example mode under `my/var/examples/`, `EXAMPLE_COPIES`, `EXAMPLE_COPIED` and the copy (SPEC 6.2); `REPLAY_DIR`; `my/var/...` in `tests/step3/` (`conftest.py`, `test_example_selector.py`, `test_replay_run.py`, `test_replay_cli.py`, `test_work_cli.py`) | 3 |
   | `examples/README.md`: `my/var/...` paths, the copy in example mode, the fixture's new place | 3 |
   | `my/var/replay` in `tests/step4/conftest.py` | 4 |
   | `tests/step5/conftest.py`, `EXAMPLE_DATA` in `tests/step5/step5_helpers.py` | 5 (already in `R`) |

3. Check: `grep -rnE "\"var/|'var/|Path\(\"(brief|modules)\"\)|data/example" harness tests`
   in the state finds nothing that is not `my/var/` or `tests/fixtures/`.

### 10.3 Forward-port the later fixes

| Fix | Where it was made | Files | Into |
| --- | --- | --- | --- |
| F1 the `auto` provider default and plain provider errors | `c28b41a` | `harness/config.py` (the default only), `harness/model/__init__.py`, `harness/model/providers.py`, the `check()` hunks of `harness/__main__.py` (`resolve_provider`), `tests/step0/test_config.py`, `tests/step0/test_model.py` | `0-done`, `1-done` |
| F2 the reworded Claude Code tool rules | `c28b41a` | `TOOL_RULES` in `harness/model/claude_code_provider.py` and `tests/step0/test_claude_code_adapter.py` | `0-done`, `1-done` |
| F3 prompt fixes | `36c0f51` (`analyst.md`, the bullet above), `c1eeef0` (`aside.md`, neutral at a choice) | `harness/calc/analyst.md`, `harness/calc/aside.md` | `4-done` |
| F4 the restructuring | `R` | 10.2 | all |

How to recognise any other fix: for each file of a state, list the later
commits that touched it (`git log --oneline <start>..R -- <file>`) and
read each hunk. It belongs to the later step when that step's SPEC files
table lists the file as changed or revised, or the hunk carries a
"(step M)" mark, or it serves something only that step has. Otherwise it is
a fix: port it. When unsure, leave it out and add a line to section 11's
log.

### 10.4 `SPEC.md` for each state

As built: each state's SPEC is the step-end SPEC plus the F1/F2 hunks, plus
R's restructuring hunks (`git diff c1eeef0 R -- SPEC.md`) for the sections
the state has, plus hand edits (introduction, status table, rules 1.2, 1.8,
1.9, section 2), with the draft section cut. The pruning recipe below
describes the same result from the other side:

Start from `SPEC.md` of `R` (it has every fix and the restructuring), then:

1. Remove the sections of later steps (step 0 keeps 1 to 3; 1: to 4; 2: to
   5; 3: to 7; 4: to 8) and their rows in the status table.
2. Remove every passage marked "(step M)" with M above the state's step: a
   sentence, list item, table row or code-block line. Where the mark labels
   a rewording of older text, put back the older wording from the step end
   commit. In section 2, remove the lines that name a later step's folder or
   files (`sources/`, the `calc/` notes about sections 8 and 9, `replay.py`,
   `examples/` before step 3).
3. Diff the result against `git show <step end>:SPEC.md` (for `4-done`,
   against `0129b62`, and `36c0f51` for section 8.8). Every remaining hunk
   is a fix (keep it), a restructuring hunk (keep it), or a later step's
   unmarked change (revert it). Known unmarked later changes: section 6.6
   ("Changes to step 2") is step 3's and is a section of its own; 3.7's
   `auto` is F1 and stays.
4. The status table says, for the last section of the state, "Fixed,
   covered by `tests/step<N>`".

`N-build` uses `N-done`'s `SPEC.md`: an attendee building step 2 reads the
step 2 contract as it was, never step 4's in-place edits.

### 10.5 Store and accept

1. `python -m workshop store finished .` on a clean `main` at `R`.
2. For each state: `python -m workshop store <state> <scratch>/<state>`.
3. Write `manifest.json` from 4.3.
4. `python -m workshop check`. **Acceptance: every line passes.** Fill
   `red_at_start` only for failures that come from a revised helper or
   given file of step N, each with its reason; anything else is fixed in
   the snapshot.
5. Read the diffs once: `export` two consecutive states and `diff -r` them;
   every difference should match the manifest row of the later step.

## 11. Maintaining them afterwards

History is never read at run time; the stored states are maintained by
hand.

- **A fix on the finished tree.** Commit it on `main`, then
  `python -m workshop store finished .`: every earlier state is pinned as it
  was (`STORE_PINNED` lines). For each earlier state the fix applies to,
  `export` it, apply the fix, `store` it. Run `check`.
- **A change to an earlier step's contract or tests.** `export` the
  `N-done` states concerned, edit, `store`, update the manifest if a file's
  step changes, run `check`.
- **A new file.** Add it to the manifest row of the step that introduces it.
  `check` rule 3 fails until it is there.
- Keep a short log of fixes deliberately not ported, with the reason, in
  `states/NOTES.md` (the `analyst.md` bullet is not in `2-done` or `3-done`).
- `check` runs before every release of the workshop and after every change
  to `harness/`, `tests/`, `examples/`, `reference/` or `SPEC.md`.

## 12. The workshop's own tests

In `workshop/tests/`, run with `uv run pytest workshop/tests` (the
harness's `testpaths` is `tests`, so the harness suite never collects
them). They build a small fake `states/` and manifest in a temporary
folder (two or three steps, a handful of files), point the code at it
(the functions take the root folder as an argument; `ROOT` is only the
default), and check: content resolution (6), `apply` with setting aside and
the never-touched paths (7), `where()` (8.1), each command's lines and exit
codes (8), the static checks (9.1) on broken data, and `store finished`
pinning. They do not run the harness's tests. The real data is checked by
`python -m workshop check`.

## 13. Decisions

1. **The tree is the state.** No state file: `where()` compares the tree
   with the stored states. A person's own code is recognised as "the
   contract of step N with your own code", and their tests say whether
   step N is built. Nothing can go stale.
2. **A full copy of the finished tree is stored** (`states/finished/`), and
   overlays are relative to it. The working tree cannot be the reference,
   because `start` changes it, and history is not read at run time. `check`
   says when `finished/` and `main` differ.
3. **"Changed by the person" means: equal to no known version of that
   path.** A file equal to any stored version can always be had again, so
   only other files are set aside.
4. **`start` and `finish` never refuse.** Telling the person's work from
   the workshop's own earlier moves is not cheap without a state file or
   git; setting aside protects everything that is not a known version.
5. **`N-build` is derived, not stored**, except the starting form of
   `start` files (only step 2's `safety.py` and `runner.py`).
6. **`README.md`, `pyproject.toml` and the other root files are the same
   in every state.** The README describes the finished harness; section
   headings say which step each part belongs to.
7. **The build prompts live in `workshop/prompts/` and are the same in
   every state.** Each prompt is for one step; the manifest names it.
8. **`next` checks that the previous step's built files exist, and runs no
   tests.** The hint says which tests to run. A copy whose contract files
   match no step is refused, with the files that differ.
9. **In `N-build`, earlier test files that step N revised are not run**,
   and `red_at_start` names any other earlier test that a revised helper
   breaks, with a reason.
10. **`store finished` pins every other state.** A fix reaches an earlier
    state only by a deliberate edit, so a step-5 change can never leak into
    `2-done`.
11. **The account-file fixture (`tests/fixtures/accounts/`, moved as is
    from `data/`) and `tests/data/` are the same in every state** and pass
    with no harness code; the later note added to its key is a fix.
12. **`aside.md`'s "neutral at a choice" line is ported to `4-done`**: it
    applies to judgment calls as well as to findings.
13. **`leave` sets nothing aside**: `workshop/` is ours and git restores it.
14. **The workshop never touches the database.** Migrations are additive:
    going back a step leaves later tables unused; going forward applies the
    new ones. If a person's own migration differs from the reference under
    the same name, they start a fresh database by moving `my/var/harness.db`
    away (the attendee guide says so).

Decisions in `SPEC.md` made for the restructuring:

15. **Example mode works on a copy** under `my/var/examples/<name>/`
    (brief, modules, database), made once and never refreshed, so the
    harness never writes into `examples/` (SPEC 6.2). This replaces "files
    are not copied".
16. **The older-copy check** is defined once, in step 1 (SPEC 4.5), with a
    fixed tuple of the commands that read or write the brief or modules,
    later steps' commands included, so no later step changes it.

## 14. Risks

| Risk | How to detect it |
| --- | --- |
| A hunk is put in the wrong step: a later step's change ported back as a fix, or a fix left out | `check` rule 3 (every difference between consecutive states is listed in the manifest); the tests of each state; the `diff -r` read of 10.5 |
| `SPEC.md` of a state keeps a later step's unmarked wording, or loses a fix | the `spec` static check catches markers and headings only; read the diff of 10.4 step 3 hunk by hunk |
| A revised helper of step N (`step2_helpers.py` in steps 4 and 5) breaks unchanged earlier tests in `N-build` | `check` reports the `N-build` line; the honest fix is a `red_at_start` entry with its reason, never a weakened test |
| The restructuring is incomplete in an early state (an old `var/` default left in `2-done`) | the grep of 10.2 step 3; `test_config` and `test_registry` defaults; `check` |
| `evidence.html` in `3-done` and `4-done` misses a fix made later to a view it already had | not visible to `check`; diff the page between `4-done` and `5-done` and classify each hunk outside the Data view |
| `finished/` lags `main` after a change | the `finished` static check |
| A test depends on the repository root (`ROOT / "my" / "var" / "replay"`) or on timing, and fails only in a temporary folder | `check --keep`, rerun the state alone |
| Attendees pull an update on the day over a copy moved by `start` | the attendee guide says to `finish 5` (or commit their work) before `git pull` |
