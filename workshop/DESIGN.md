# The `workshop` command: design

This is the contract of the workshop tool, the way `SPEC.md` is the
contract of the harness. It covers the step machinery: the manifest, the
stored snapshots, the commands and the drift check. The harness side of
the restructuring (the three places, `my/`, the new defaults, the message
for an older copy) is in `SPEC.md`, sections 1, 2, 4.5, 4.8 and 6.5.

The workshop is not built to help someone write an entirely different
harness from scratch in two hours. Variations on the main example follow
along best.

## 1. What it does, and what it never does

`python -m workshop` moves this copy of the repository between twelve
**states**: for each step N from 0 to 5, **the start of step N**
(`N-build`) and **the end of step N** (`N-done`). A fresh clone is `5-done`,
the finished harness.

- `N-done`: today's `SPEC.md`; the tests of steps 0 to N (the finished
  tree's `tests/step0/` to `tests/step<N>/`, with the fixtures and shared
  test support); and the harness code, the given files and the examples
  exactly as they are when step N is complete, with every later fix that
  applies to them.
- `N-build`: `N-1-done`, plus step N's tests, given files and starting
  files. Step N's tests fail; the tests of steps 0 to N-1 pass. `0-build`
  has no harness code at all.

Two rules of the harness's tests make this small:

1. **A test of `tests/step<N>/` is true of the harness at the end of step N
   and at the end of every later step.** So the tests are stored once, in the
   finished tree, and a state simply has the test folders up to its step.
   No state keeps an older version of a test. A test that breaks the rule
   is fixed (or deleted) on the finished tree; `check` tells which.
2. **`SPEC.md` is one file for every state**: today's. Each build prompt
   says in one sentence that passages marked "(step M)" for a later step do
   not apply yet.

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
          "given":   ["<file or folder/>", ...]}   given files, data and examples this step installs, new or revised
```

- An entry ending in `/` is a folder: it stands for every known path below
  it. In `given`, it means "make this folder match `N-done`": add, replace
  and remove known paths below it.
- `built`, `start` and `changed` hold files only, all under `harness/`.
- `tests` is the step's test folder. It is installed by the step along with
  `given`, so `given` never lists tests or (after step 0) `SPEC.md`.
- Step 0's `given` also holds what every state has and no step changes:
  `SPEC.md`, `tests/data/` and `tests/fixtures/` (the account-file fixture).
- `always`: test folders that hold in every state. They are run with the
  earlier steps' tests.

### 4.2 Rules (checked by `check`, section 9.1)

1. Every known path is **introduced** by exactly one step, through one of
   its `built`, `start` or `given` entries, or through its `tests` folder.
   A later step may list it again: in `given` when the step revises it, in
   `changed` when the person changes it. "Introduced by step K" means:
   absent in every state before `K-build`; absent in `K-build` too when
   `built`; present in `K-done`.
2. A `changed` path of step K was introduced by an earlier step through
   `built` or `start`. No code path is in any step's `given`.
3. Between `K-1-done` and `K-done` (for K = 0, between the empty tree and
   `0-done`), every path whose content differs is in `built`, `start`,
   `changed`, `given` or the `tests` folder of step K. Each file entry of
   those lists does differ, and each `given` folder has at least one path
   that differs. So the manifest explains every change, and lists nothing
   stale.
4. Each build prompt lists exactly what the manifest says, under three fixed
   headings, one bullet per path, written "- `path` (comment)":
   `Build these files (new):` is `built`;
   `Change these files (they exist already):` is `start` and `changed`
   (the section is left out when both are empty);
   `Given files (do not edit):` is `SPEC.md`, the `tests` folder and
   `given`. It also holds the sentence of decision 17.

### 4.3 Content

Derived from the history (`git diff --name-status` between the step ends
of section 10) and from the files tables of `SPEC.md` sections 5 and 7 to 9.
Fixes forward-ported to earlier states (section 10.3) make a file the same
in two states, so they appear in no list.

| Step | Prompt | Built by the person | Given in a starting form (`start`) | Changed by the person | Given (besides SPEC.md and the step's tests) |
| --- | --- | --- | --- | --- | --- |
| 0 setup | `step0_setup.md` | `harness/__init__.py`, `harness/config.py`, `harness/db.py`, `harness/migrations/0001_init.sql`, `harness/model/__init__.py`, `harness/model/interface.py`, `harness/model/scripted.py`, `harness/model/anthropic_provider.py`, `harness/model/providers.py`, `harness/model/claude_code_provider.py`, `harness/__main__.py` | | | `tests/data/`, `tests/fixtures/` |
| 1 shared domain | `step1_shared_domain.md` | `harness/grounding/__init__.py`, `harness/grounding/brief.py`, `harness/grounding/claude_code_research.py`, `harness/grounding/interview.py`, `harness/grounding/research.py`, `harness/migrations/0002_lookups.sql`, `harness/ui/__init__.py`, `harness/ui/server.py`, `harness/ui/session.py` | | `harness/config.py`, `harness/__main__.py`, `harness/model/claude_code_provider.py` | `harness/grounding/interviewer.md`, `harness/grounding/researcher.md`, `harness/grounding/planner.md`, `harness/ui/grounding.html`, `reference/`, `examples/moving/brief/`, `examples/wedding/brief/` |
| 2 consistency | `step2_consistency.md` | `harness/calc/__init__.py`, `harness/calc/registry.py`, `harness/calc/notes.py`, `harness/calc/added.py`, `harness/calc/gate.py`, `harness/calc/builder.py`, `harness/calc/provenance.py`, `harness/calc/agent.py`, `harness/calc/adopt.py`, `harness/migrations/0004_notes.sql`, `harness/migrations/0005_added_steps.sql` | `harness/calc/safety.py`, `harness/calc/runner.py` | `harness/config.py`, `harness/__main__.py` | `harness/calc/values.py`, `harness/calc/spec_writer.md`, `harness/calc/example_writer.md`, `harness/calc/example_helper.md`, `harness/calc/module_writer.md`, `harness/calc/analyst.md`, `harness/migrations/0003_calc.sql`, `examples/moving/modules/`, `examples/wedding/modules/` |
| 3 evidence (with examples and replay) | `step3_evidence.md` | `harness/replay.py`, `harness/ui/evidence.py` | | `harness/__main__.py`, `harness/calc/agent.py`, `harness/calc/provenance.py`, `harness/ui/server.py` | `harness/ui/evidence.html`, `harness/ui/grounding.html` (revised: a link to `/work`), `examples/README.md`, `examples/moving/scenarios/`, `examples/wedding/scenarios/` |
| 4 human in the loop | `step4_human_in_the_loop.md` | `harness/migrations/0006_decisions.sql`, `harness/calc/decisions.py`, `harness/calc/aside.py` | | `harness/calc/agent.py`, `harness/__main__.py`, `harness/replay.py`, `harness/ui/evidence.py` | `harness/calc/aside.md`, `harness/calc/analyst.md` (revised), `harness/ui/evidence.html` (revised), `examples/README.md`, `examples/moving/scenarios/`, `examples/wedding/scenarios/` |
| 5 verification | `step5_verification.md` | `harness/migrations/0007_data.sql`, `harness/sources/__init__.py`, `harness/sources/adapter.py`, `harness/sources/summaries.py`, `harness/calc/findings.py`, `harness/calc/verifier.py` | | `harness/calc/agent.py`, `harness/calc/decisions.py`, `harness/calc/provenance.py`, `harness/replay.py`, `harness/ui/evidence.py`, `harness/ui/server.py`, `harness/__main__.py` | `harness/calc/verifier.md`, `harness/calc/analyst.md` (revised), `harness/ui/evidence.html` (revised), `examples/README.md`, `examples/wedding/data/`, `examples/wedding/scenarios/` |

Notes on the table:

- Every step's `prompt` is `workshop/prompts/<the file above>`, and `tests`
  is `tests/step<N>/`. The tests of a step are not "given" in the manifest
  sense: they are the finished tree's, and a state has them by rule (6).
- Step 2's `safety.py` and `runner.py` are the only `start` files: SPEC 5.2
  and 5.3 give them, each with one change for the person to make. Their
  starting form is the one of commit `bb7ccb0`, restructured.
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
  finished/<path>            a full copy of the finished tree: every file under the managed roots
  <N>-done/files/<path>      for N = 0 to 4: the harness, example and reference files of N-done that differ from finished/
  <N>-done/absent.json       for N = 0 to 4: the sorted list of those paths of finished/ that N-done does not have
  <N>-build/files/<path>     only where a step has `start` files (today only 2-build): their starting form
```

- `absent.json` is a JSON list of strings, written like the manifest.
- **`SPEC.md` and the tests are never in an overlay or an absent list**: a
  state gets them from `finished/` by rule (6). An overlay file never equals
  the `finished/` file at the same path, and `absent.json` names only paths
  of `finished/` (all checked, 9.1).
- `N-build` is not stored: it is derived (section 6). `<N>-build/files/`
  holds exactly the `start` paths of step N, nothing else.
- Built size (files in the overlay): 3 in `0-done`, 4 in `1-done`, 6 in
  `2-done`, 13 in `3-done`, 10 in `4-done`, and 2 in `2-build`. `finished/`
  holds 252 files.

## 6. The content of a state

A path is **shared** when it is `SPEC.md` or under `tests/`. The test folder
of a shared path is `K` when the path is under `tests/step<K>/`; `tests/data/`
and `tests/fixtures/` belong to no step.

```
content("N-done", p) = finished/p                         if p is SPEC.md, or under tests/data/ or tests/fixtures/,
                                                           or under tests/step<K>/ with K <= N; None for K > N
                     = N-done/files/p                     if stored there (p is not shared)
                     = None                               if p is in N-done/absent.json
                     = finished/p, or None                otherwise
content("5-done", p) = finished/p, or None
content("N-build", p) = N-build/files/p                   if p is in start(N)
                      = content("N-done", p)              if p is in given(N), folders expanded over U;
                                                           given(N) includes the tests folder of step N
                      = content("N-1-done", p)            otherwise; for N = 0, None
```

`U` is the union of the paths of `finished/`, of every overlay, and of
every `absent.json`. A state is resolved in memory as a map from path to
bytes; nothing is cached on disk. `given(N)` is the manifest's `given`
entries of step N and its `tests` folder, expanded over `U`. Because the
tests of a state are the finished tree's up to its step, the earlier tests
of `N-build` are exactly those of `N-1-done`.

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
3. The paths installed are `given(N)`, folders expanded over `U` (step N's
   given files and its tests, no other step's), plus `start(N)`.
   `apply(state map of N-build, those paths)`. `SPEC.md` and the earlier
   tests are the same in every state, so they are not replaced. No code path
   is in any `given` (rule 2), and the `start` paths of step N are new, so
   the person's code is untouched.
4. `NEXT_DONE`, then `HINT_BUILD`. Exit 0.

The prompt itself is in `workshop/prompts/`, which no state changes: it is
"installed" in the sense that `HINT_BUILD` names it.

### 8.5 `leave`

1. Prints `LEAVE_STATE` with where the copy stands (its exact state's label,
   or "the contract of step N with your own code", or "no step").
2. Asks `LEAVE_ASK` and reads one line. An accept word (stripped,
   lower-cased: `yes`, `y`, `ok`, `okay`, `/accept`, `yes.`, `si`, `sí`, the
   words of `ACCEPT_WORDS` in the harness's `builder.py`, repeated here
   because the workshop imports nothing from `harness/`) removes `ROOT/workshop` with `shutil.rmtree` and prints `LEAVE_DONE`.
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
    `DIR` for every path that is not shared (6). `SPEC.md` and the tests in
    `DIR` are ignored: they come from `finished/`. Overlay files equal to
    `finished/` are not kept.
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
    `SPEC.md` and the tests are never pinned: a change to them in the
    finished tree reaches every state that has them, which is the point.
  - Then `STORED` (`STORED_FINISHED` for `finished`). Exit 0.

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
STATUS_TESTS_INTRO   = "Running the tests of each step. This takes about a minute for all six steps; --quick skips it."
STATUS_TEST_LINE     = "  step {k}: {result} ({seconds} s)"
STATUS_TESTS_SKIPPED = "Tests not run (--quick)."
NO_PYTEST         = "pytest is not installed here. Run the workshop with: uv run python -m workshop status"

HINT_BUILD        = "Next: paste {prompt} into your coding agent. Then run: uv run pytest tests/step{n}"
HINT_NEXT         = "Next: python -m workshop next  (step {m}'s contract, tests and given files; your code stays as it is)"
HINT_WHEN_GREEN   = "When the tests of step {n} pass: python -m workshop next"
HINT_FINISHED     = "This is the finished harness. To keep it without the workshop: python -m workshop leave"
HINT_NO_MATCH     = "Put those files back with git checkout -- <file>, or move the whole copy with: python -m workshop start N, or finish N"

APPLIED           = "{written} files written and {removed} removed in SPEC.md, harness/, tests/, examples/ and reference/. Your my/brief, my/modules and database were not touched."
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

CHECK_INTRO       = "Each state runs its tests in a temporary folder. All twelve take a few minutes."
CHECK_LINE        = "{name:<10} {mark}  {detail}"
CHECK_DONE        = "{passed} of {total} checks passed."

DIR_NOT_EMPTY     = "{dir} is not empty."
STORE_NOT_START   = "Only the start files of step {n} can differ from the derived start of step {n}, and these differ too: {paths}. Nothing was stored."
STORE_PINNED      = "Kept {state} as it was: stored its own {path}."
STORED            = "Stored {state}: {files} files in its overlay, {absent} absent."
STORED_FINISHED   = "Stored finished: {files} files."
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
| `snapshots` | every overlay file differs from `finished/`; every `absent.json` names only paths of `finished/`; no overlay or absent list holds `SPEC.md` or a test; every `N-build/files/` holds exactly `start(N)`; rule 3 of 4.2 holds for every step |
| `finished` | the working tree equals `finished/` over `U` (on `main`; after `start`, `next` or `finish` this line fails, and its detail says so) |
| `prompts` | rule 4 of 4.2 holds for every step: the three lists equal the manifest's, and the sentence about passages of a later step is there |

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
    all of them, nothing ignored. Must exit 0. For N = 0 only the `always`
    folders.
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

- A fix made on the finished tree to a harness, given or example file that
  no test notices in an earlier state: a reworded prompt (`analyst.md`), a
  page change in `evidence.html`, `examples/README.md`. Such a fix is either
  pinned away from the earlier states by `store finished` or missing from
  them, silently. (Fixes to tests and `SPEC.md` reach every state by rule.)
- Whether an `N-build` can be built from its prompt by a coding agent. Only
  running the prompt tells.
- Whether a state's code matches the parts of `SPEC.md` that apply to it:
  there is one `SPEC.md`, and only the tests of the state judge the code.
- Whether a test that should fail in `N-build` fails for the right reason.

## 10. Building the snapshots from history (one-off, done)

This is how the stored states were made the first time. The log of what was
actually done, file by file, is `workshop/states/NOTES.md`. Work in a
scratch folder outside the repository. Store with `store` (8.7), never by
hand-copying into `states/`. Only `harness/`, `examples/` and `reference/`
are built this way: the tests and `SPEC.md` of every state are the finished
tree's (rule 1 and 2 of section 1), so no history of them is needed.

### 10.1 Step ends

| State | Start from |
| --- | --- |
| `0-done` | `4426932` |
| `1-done` | `f8da442` |
| `2-done` | `c28b41a` |
| `3-done` | `a793043` |
| `4-done` | `0129b62`, then from `36c0f51`: all of `examples/` and the one step 4 hunk of `harness/calc/analyst.md` (the bullet "Never put a figure or a date of your own in a question ..."). Not its step 5 hunks of `analyst.md`, not `harness/calc/verifier.md`. |
| `5-done` | the finished tree (`store finished .`) |
| `2-build` | `harness/calc/safety.py` and `harness/calc/runner.py` from `bb7ccb0` |

For each, `git archive <commit> harness examples reference | tar -x -C <scratch>/<state>`
(drop the names a commit does not have).

### 10.2 Apply the restructuring (F4)

In every state, apply the restructuring hunks of the finished tree to the
harness and example files the state has, taking only the hunks for features
the state has:

| Change | From state |
| --- | --- |
| `HARNESS_DB` default `my/var/harness.db` (`config.py`) | 0 |
| `HARNESS_BRIEF_DIR` default `my/brief`; `LEGACY_COMMANDS`, `LEGACY_LAYOUT` and their check in `main()` (SPEC 4.5) | 1 |
| `HARNESS_MODULES_DIR` default `my/modules` | 2 |
| example mode under `my/var/examples/`, `EXAMPLE_COPIES`, `EXAMPLE_COPIED` and the copy (SPEC 4.8) | 1 |
| `REPLAY_DIR` | 3 |
| `examples/README.md`: `my/var/...` paths, the copy in example mode | 3 |

Check: `grep -rnE "\"var/|'var/|Path\(\"(brief|modules)\"\)" harness` in the state
finds nothing that is not `my/var/`.

### 10.3 Forward-port the later fixes

| Fix | Where it was made | Files | Into |
| --- | --- | --- | --- |
| F1 the `auto` provider default and plain provider errors | `c28b41a` | `harness/config.py` (the default only), `harness/model/__init__.py`, `harness/model/providers.py`, the `check()` hunks of `harness/__main__.py` (`resolve_provider`) | `0-done`, `1-done` |
| F2 the reworded Claude Code tool rules | `c28b41a` | `TOOL_RULES` in `harness/model/claude_code_provider.py` | `0-done`, `1-done` |
| F3 prompt fixes | `36c0f51` (`analyst.md`, the bullet above), `c1eeef0` (`aside.md`, neutral at a choice) | `harness/calc/analyst.md`, `harness/calc/aside.md` | `4-done` |
| F4 the restructuring | the finished tree | 10.2 | all |

How to recognise any other fix: for each file of a state, list the later
commits that touched it (`git log --oneline <start>..HEAD -- <file>`) and
read each hunk. It belongs to the later step when that step's SPEC files
table lists the file as changed or revised, or the hunk carries a
"(step M)" mark, or it serves something only that step has. Otherwise it is
a fix: port it. When unsure, leave it out and add a line to
`states/NOTES.md`.

### 10.4 Store and accept

1. `python -m workshop store finished .` on a clean `main`.
2. For each state: `python -m workshop store <state> <scratch>/<state>`.
   (A tree that also holds `SPEC.md` and tests is fine: they are ignored.)
3. Write `manifest.json` from 4.3 and the prompts from its lists.
4. `python -m workshop check`. **Acceptance: every line passes.** When a
   state fails, decide which it is, and fix that:
   - the snapshot lacks a forward-port: fix the snapshot, and log it in
     `states/NOTES.md` (what, why, from which commit);
   - the manifest gives a file to the wrong step: fix the manifest;
   - a test breaks rule 1 of section 1 (it is not true at the end of its own
     step and every later one): fix the test on the finished tree, with the
     smallest change that keeps what it protects at its own step, or delete
     it when it only makes sense later. Then `store finished .`.
5. Read the diffs once: `export` two consecutive states and `diff -r` them;
   every difference should match the manifest row of the later step.

## 11. Maintaining them afterwards

History is never read at run time; the stored states are maintained by
hand.

- **A fix to `SPEC.md` or a test.** Make it on `main`, then
  `python -m workshop store finished .`. Every state has it at once; nothing
  else to do. Run `check`: a test that is no longer true at an earlier step
  breaks rule 1 of section 1, and is fixed (or deleted) there.
- **A fix to harness, given or example files.** Commit it on `main`, then
  `python -m workshop store finished .`: every earlier state is pinned as it
  was (`STORE_PINNED` lines). For each earlier state the fix applies to,
  `export` it, apply the fix, `store` it. Run `check`.
- **A change to which step a file belongs to.** Update the manifest (and the
  prompt lists, which `check` compares with it), run `check`.
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
9. **No state stores an older test, and `N-build` runs every earlier test.**
   A test that is not true in an earlier "done" state is fixed on the
   finished tree, never skipped or excused in the manifest.
10. **`store finished` pins every other state.** A fix reaches an earlier
    state only by a deliberate edit, so a step-5 change can never leak into
    `2-done`.
11. **The account-file fixture (`tests/fixtures/accounts/`, moved as is
    from `data/`) and `tests/data/` are in every state** and pass with no
    harness code.
12. **`aside.md`'s "neutral at a choice" line is ported to `4-done`**: it
    applies to judgment calls as well as to findings.
13. **`leave` sets nothing aside**: `workshop/` is ours and git restores it.
14. **The workshop never touches the database.** Migrations are additive:
    going back a step leaves later tables unused; going forward applies the
    new ones. If a person's own migration differs from the reference under
    the same name, they start a fresh database by moving `my/var/harness.db`
    away (the attendee guide says so).

17. **One `SPEC.md` for every state, and one sentence in each prompt.**
    Each build prompt says: `Passages of `SPEC.md` marked "(step M)" for a
    step later than this one do not apply yet.` `check` looks for it. The
    reader of step 2's contract therefore also sees step 4's marked
    changes; the prompt and the tests say which section is theirs.
18. **A state's tests are derived, not stored.** `content` takes the test
    folders `tests/step0/` to `tests/step<N>/` from `finished/`. `next`
    installs step N's folder; `finish` and `start` install whatever the state
    has. A person's edit to a test is set aside like any other file.

Decisions in `SPEC.md` made for the restructuring:

15. **Example mode works on a copy** under `my/var/examples/<name>/`
    (brief, modules, database), made once and never refreshed, so the
    harness never writes into `examples/` (SPEC 4.8). This replaces "files
    are not copied".
16. **The older-copy check** is defined once, in step 1 (SPEC 4.5), with a
    fixed tuple of the commands that read or write the brief or modules,
    later steps' commands included, so no later step changes it.

## 14. Risks

| Risk | How to detect it |
| --- | --- |
| A hunk is put in the wrong step: a later step's change ported back as a fix, or a fix left out | `check` rule 3 (every difference between consecutive states is listed in the manifest); the tests of each state; the `diff -r` read of 10.4 |
| A test is written that is true at its own step only (it counts events, names a key a later step adds, lists every scenario) | `check` fails an `N-done` or `N-build` line; fix the test on the finished tree (smallest change that keeps what it protects) |
| A given file of step N needs code the person builds in step N, so an earlier test fails in `N-build` (scenarios with keys the old `replay.py` rejects) | `check` reports the `N-build` line; the test of the earlier step must name the files of its own step, not every file in a folder |
| The restructuring is incomplete in an early state (an old `var/` default left in `2-done`) | the grep of 10.2; `tests/step0/test_config.py` and `test_registry.py`; `check` |
| `evidence.html` in `3-done` and `4-done` misses a fix made later to a view it already had | not visible to `check`; diff the page between `4-done` and `5-done` and classify each hunk outside the Data view |
| `finished/` lags `main` after a change | the `finished` static check |
| A test depends on the repository root (`ROOT / "my" / "var" / "replay"`) or on timing, and fails only in a temporary folder | `check --keep`, rerun the state alone |
| Attendees pull an update on the day over a copy moved by `start` | the attendee guide says to `finish 5` (or commit their work) before `git pull` |
