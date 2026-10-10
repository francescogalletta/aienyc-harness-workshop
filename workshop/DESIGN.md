# The workshop tool

How `python -m workshop` is built. The harness is built from five layers on one core
(`ARCHITECTURE.md` sections 2 and 7), and "the harness at step N" is the finished tree with
later layers off or absent. The tool therefore stores nothing: no copies of earlier versions
of files, no snapshots. It moves one working copy between steps with the files it already has
and with git.

## What it keeps to

- Standard library only. It never calls a model.
- `harness/` never imports `workshop/`; `tests/layer0/test_layout.py` checks that. Deleting
  `workshop/` leaves a harness whose tests pass.
- It never touches `my/brief`, `my/modules` or the database. The only things it writes under
  `my/` are `my/var/layers` (the `at` command) and `my/var/set-aside/` (copies of the person's
  changed files). `my/var/` is git-ignored.
- Every change that could lose work first copies the files that differ from the reference to
  `my/var/set-aside/<timestamp>/<path>`. A command that cannot finish says why and changes
  nothing.

## Files

| File | Holds |
| --- | --- |
| `manifest.json` | The one source of truth, below |
| `tree.py` | Reading the manifest, comparing it with the tree, git, set-aside, `start`, `finish` |
| `drift.py` | The `check` command |
| `__main__.py` | The commands and their messages, and the table written to `STEPS.md` |
| `STEPS.md` | The six steps in one table, generated from the manifest |
| `tests/` | The tool's own tests: `uv run pytest workshop/tests` (not part of `uv run pytest`) |
| `README.md`, `FACILITATOR.md`, `BUILD_PLAN.md`, `prompts/` | Guides for people; not read by the tool |

## The manifest

`core` lists the given core: `harness/*.py`, `core/`, `model/`, `ui/` (including the page).
Section 7 says the shared files are the same at every step, so step 0 builds nothing.
Steps 1 to 5 each name their `package`, the files an attendee `built` (everything in the package
that is not a prompt: code, `__init__.py`, `schema.sql`), the `given` files (the `.md` prompts),
their `tests` folder (`tests/layer<N>/`), the principle and what can be run after the step.
`reference` is empty, which means HEAD. Set it to a commit when HEAD may move past the finished
tree (a person's own commits); `finish` and the set-aside comparison then use that commit.
Data (`reference/`, `examples/`) is outside the manifest and never moved.

Rule, checked by `check`: every file under `harness/` is in exactly one place, the core or one
step, and every listed file exists. A new file in the harness fails `check` until it is listed.

## Commands

| Command | Does |
| --- | --- |
| `status [--quick]` | The setting in force (`HARNESS_LAYERS`, else `my/var/layers`, else none); per layer: package present, on, built files present; then each step's tests, unless `--quick` |
| `at N` | Writes `N` to `my/var/layers`. Removes and copies nothing. The harness's `config` reads that file when `HARNESS_LAYERS` is unset, so no shell export is needed; the variable still wins and `at` says so |
| `start N` | For someone who builds step N: sets aside what differs, then removes step N's built files and the packages of layers above N. Keeps the contract, step N's given files and every `tests/layer*` folder. Warns if `my/var/layers` is below N |
| `finish N` | Restores the files of layers 1 to N from git (`git show <ref>:<path>`), after setting aside those that differ. Not a git checkout: says so and stops. A commit that lacks a file: stops before writing |
| `leave` | Removes `workshop/` after an accept word (`yes`, `y`, `ok`, `okay`, `si`, `/accept`) |
| `check` | The drift check, below |
| `steps [--write]` | Prints the table, or writes `STEPS.md` |

The core is not touched by `start` or `finish`. `start 0` only removes layers 1 to 5.

## The drift check

Three states for each step N from 0 to 5 (18 lines):

- `layers<=N only`: a temporary copy with the packages of layers above N deleted; the tests of
  steps 0 to N pass.
- `HARNESS_LAYERS=N`: a temporary copy of the full tree with that setting; the same tests pass.
- `start N`: a temporary copy after `start N`; the tests of steps below N pass and step N's
  fail (for N = 0 nothing is built, so layer 0 passes).

Each folder is run by its own pytest, because two `tests/layer*` folders in one run share the name
`conftest`. Copies leave out `.git`, `my/var`, `my/brief` and `my/modules`. States run four at a time.
One line per state; exit 1 on any surprise, on a manifest that disagrees with the tree and on a stale
`STEPS.md`. With two cores it takes about four minutes.

A failure of "layers<=N only" or "HARNESS_LAYERS=N" is a finding about layering (section 7: a test of
layer K must hold in any later tree, and in an earlier one with its own layer): fix the test or move it
to the layer it belongs to.

## Not done

- `next` of version 1 is gone: `at N` is the follower's switch, `finish N` the catch-up.
- Tests of layers above N stay after `start N` and fail until their layer exists; run
  `uv run pytest tests/layerN`, as `STEPS.md` says.
