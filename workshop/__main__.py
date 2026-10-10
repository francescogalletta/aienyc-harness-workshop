"""The command line: `python -m workshop <command>`. See DESIGN.md section 8. Every printed line is a constant here."""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import checks, states

BAD_STEP = "Steps are numbered 0 to 5."
DATA_BROKEN = "The workshop data is incomplete: {reason}. Run: python -m workshop check"
IN_THE_WAY = ("{path} is a folder where the workshop needs a file, or a file where it needs a folder. "
              "Move it away and run the command again. Nothing was changed.")
SET_ASIDE = "Set aside your version of {path} in {copy}"

STATUS_EXACT = "This copy is at {label}."
STATUS_CONTRACT = "This copy has the contract of step {n}: SPEC.md, the tests and the given files of step {n}."
STATUS_OWN_CODE = "Code: your own. {count} code files differ from the reference at the end of step {n}."
STATUS_NO_MATCH = "This copy matches no step: the closest is step {n}, and these files differ from it: {paths}."
STATUS_TESTS_INTRO = ("Running the tests of each step. This takes about a minute for all six steps; "
                      "--quick skips it.")
STATUS_TEST_LINE = "  step {k}: {result} ({seconds} s)"
STATUS_TESTS_SKIPPED = "Tests not run (--quick)."
NO_PYTEST = "pytest is not installed here. Run the workshop with: uv run python -m workshop status"

HINT_BUILD = "Next: paste {prompt} into your coding agent. Then run: uv run pytest tests/step{n}"
HINT_NEXT = ("Next: python -m workshop next  (step {m}'s contract, tests and given files; "
             "your code stays as it is)")
HINT_WHEN_GREEN = "When the tests of step {n} pass: python -m workshop next"
HINT_FINISHED = "This is the finished harness. To keep it without the workshop: python -m workshop leave"
HINT_NO_MATCH = ("Put those files back with git checkout -- <file>, or move the whole copy with: "
                 "python -m workshop start N, or finish N")

APPLIED = ("{written} files written and {removed} removed in SPEC.md, harness/, tests/, examples/ and reference/. "
           "Your my/brief, my/modules and database were not touched.")
ALREADY = "This copy was already there. Nothing changed."
START_DONE = ("This copy is at the start of step {n}: the contract, tests and given files of step {n}, "
              "with the reference code at the end of step {prev}.")
START_DONE_ZERO = ("This copy is at the start of step 0: the contract, tests and test fixture of step 0, "
                   "and no harness code yet.")
FINISH_DONE = "This copy is at the end of step {n}: the reference code, tests and contract of step {n}."

NEXT_NO_MATCH = ("next needs a copy whose contract is that of a step. The closest is step {n}, "
                 "and these files differ from it: {paths}.")
NEXT_LAST = "There is no step after step 5."
NEXT_UNFINISHED = ("Step {n} does not look built yet: these files are missing: {paths}. "
                   "Build it with {prompt}, or take the reference with: python -m workshop finish {n}")
NEXT_DONE = "Installed step {n}: {count} contract, test and given files. Your code was not touched."

LEAVE_STATE = "This copy is at {label}."
LEAVE_ASK = ("This removes workshop/: the build plan, the prompts, the guides, the snapshots and this command. "
             "The harness, its tests and my/ stay as they are. Type yes to remove it.")
LEAVE_DONE = "Removed workshop/. If this copy is in git, commit the removal; git checkout -- workshop brings it back."
LEAVE_KEPT = "Nothing removed."
ACCEPT_WORDS = {"/accept", "yes", "y", "yes.", "ok", "okay", "si", "sí"}     # the words the harness takes as a yes

CHECK_INTRO = "Each state runs its tests in a temporary folder. All twelve take a few minutes."
CHECK_LINE = "{name:<10} {mark}  {detail}"
CHECK_DONE = "{passed} of {total} checks passed."

DIR_NOT_EMPTY = "{dir} is not empty."
STORE_NOT_START = ("Only the start files of step {n} can differ from the derived start of step {n}, "
                   "and these differ too: {paths}. Nothing was stored.")
STORE_PINNED = "Kept {state} as it was: stored its own {path}."
STORED = "Stored {state}: {files} files in its overlay, {absent} absent."
STORED_FINISHED = "Stored finished: {files} files."


class Refused(Exception):
    """Print this line on standard output and exit 1."""


def paths_text(paths):
    return checks.sample(paths)


def tree_of(data, root):
    return states.read_tree(root, data.roots())


# ---- status ----------------------------------------------------------------------------------------------------------

def have_pytest():
    return subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0


def run_step_tests(data, root, tree):
    """Run the tests of each step folder present in the tree. Returns {k: (passed, seconds, result)}."""
    results = {}
    for k in range(data.steps):
        folder = data.step(k)["tests"]
        if not any(p.startswith(folder) for p in tree):
            continue
        args = [folder] + (list(data.manifest["always"]) if k == 0 else [])
        start = time.time()
        code, output = checks.pytest_run(args, root)
        seconds = int(time.time() - start)
        results[k] = (code == 0, seconds, "pass" if code == 0 else f"FAIL: {checks.last_line(output)}")
    return results


def build_hint(data, n):
    return HINT_BUILD.format(prompt=data.step(n)["prompt"], n=n)


def next_hint(data, n):
    return HINT_FINISHED if n == data.steps - 1 else HINT_NEXT.format(m=n + 1)


def command_status(data, root, args):
    tree = tree_of(data, root)
    where = states.where(data, tree)
    lines = []
    if where["exact"]:
        lines.append(STATUS_EXACT.format(label=data.label(where["exact"])))
    elif where["contract"] is not None:
        lines.append(STATUS_CONTRACT.format(n=where["contract"]))
        lines.append(STATUS_OWN_CODE.format(count=len(where["own_code"]), n=where["contract"]))
    else:
        lines.append(STATUS_NO_MATCH.format(n=where["closest"], paths=paths_text(where["differ"])))
    print("\n".join(lines))
    results = {}
    if args.quick:
        print(STATUS_TESTS_SKIPPED)
    elif not have_pytest():
        print(NO_PYTEST)
    else:
        print(STATUS_TESTS_INTRO)
        results = run_step_tests(data, root, tree)
        for k, (_, seconds, result) in results.items():
            print(STATUS_TEST_LINE.format(k=k, result=result, seconds=seconds))
    if where["exact"]:
        n, kind = where["exact"].split("-")
        print(build_hint(data, int(n)) if kind == "build" else next_hint(data, int(n)))
    elif where["contract"] is not None:
        n = where["contract"]
        if n in results:
            print(next_hint(data, n) if results[n][0] else build_hint(data, n))
        else:
            print(build_hint(data, n))
            print(HINT_WHEN_GREEN.format(n=n))
    else:
        print(HINT_NO_MATCH)
    return 0


# ---- start, finish, next ---------------------------------------------------------------------------------------------

def move(data, root, target, paths):
    def report(path, copy):
        print(SET_ASIDE.format(path=path, copy=copy.relative_to(root).as_posix()))

    try:
        written, removed, _ = states.apply(data, target, paths, root, report=report)
    except states.InTheWay as error:
        raise Refused(IN_THE_WAY.format(path=error.path))
    print(APPLIED.format(written=written, removed=removed) if written or removed else ALREADY)


def command_start(data, root, args):
    n = args.step
    move(data, root, data.build_map(n), data.all_paths())
    print(START_DONE_ZERO if n == 0 else START_DONE.format(n=n, prev=n - 1))
    print(build_hint(data, n))
    return 0


def command_finish(data, root, args):
    n = args.step
    move(data, root, data.done_map(n), data.all_paths())
    print(FINISH_DONE.format(n=n))
    print(next_hint(data, n))
    return 0


def command_next(data, root, args):
    where = states.where(data, tree_of(data, root))
    if where["contract"] is None:
        raise Refused(NEXT_NO_MATCH.format(n=where["closest"], paths=paths_text(where["differ"])))
    last = where["contract"]
    if last == data.steps - 1:
        raise Refused(NEXT_LAST)
    n = last + 1
    missing = [p for p in data.step(last)["built"] if not (root / p).is_file()]
    if missing:
        raise Refused(NEXT_UNFINISHED.format(n=last, paths=paths_text(missing), prompt=data.step(last)["prompt"]))
    paths = sorted(set(data.given(n)) | set(data.start_paths(n)))
    try:
        states.apply(data, data.build_map(n), paths, root,
                     report=lambda path, copy: print(SET_ASIDE.format(path=path,
                                                                      copy=copy.relative_to(root).as_posix())))
    except states.InTheWay as error:
        raise Refused(IN_THE_WAY.format(path=error.path))
    print(NEXT_DONE.format(n=n, count=len(paths)))
    print(build_hint(data, n))
    return 0


# ---- leave ------------------------------------------------------------------------------------------------------------

def command_leave(data, root, args):
    where = states.where(data, tree_of(data, root))
    if where["exact"]:
        label = data.label(where["exact"])
    elif where["contract"] is not None:
        label = f"the contract of step {where['contract']} with your own code"
    else:
        label = "no step"
    print(LEAVE_STATE.format(label=label))
    print(LEAVE_ASK)
    sys.stdout.flush()
    answer = sys.stdin.readline().strip().lower()
    if answer in ACCEPT_WORDS:
        shutil.rmtree(root / "workshop")
        print(LEAVE_DONE)
    else:
        print(LEAVE_KEPT)
    return 0


# ---- check ------------------------------------------------------------------------------------------------------------

def command_check(data, root, args):
    wanted = args.states or data.names()
    print(CHECK_INTRO)
    total = passed = 0

    def line(name, ok, detail):
        nonlocal total, passed
        total += 1
        passed += ok
        print(CHECK_LINE.format(name=name, mark="ok" if ok else "FAIL", detail=detail), flush=True)

    tree = tree_of(data, root)
    static = {
        "manifest": lambda: checks.manifest(data),
        "snapshots": lambda: checks.snapshots(data),
        "finished": lambda: checks.finished(data, tree),
        "prompts": lambda: checks.prompts(data),
    }
    for name, function in static.items():
        try:
            problems = function()
        except Exception as error:                       # broken data must not stop the other lines
            problems = [f"the check could not run: {type(error).__name__}: {error}"]
        line(name, not problems, "ok" if not problems else "; ".join(problems[:5]))
    for name in wanted:
        try:
            (ok, detail, folder), seconds = checks.timed(checks.check_state, data, name, args.keep, root)
        except Exception as error:
            line(name, False, f"the check could not run: {type(error).__name__}: {error}")
            continue
        where = f" in {folder}" if args.keep else ""
        line(name, ok, f"{detail} ({seconds} s){where}")
    print(CHECK_DONE.format(passed=passed, total=total))
    return 0 if passed == total else 1


# ---- export and store --------------------------------------------------------------------------------------------------

def command_export(data, root, args):
    target = Path(args.dir)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise Refused(DIR_NOT_EMPTY.format(dir=args.dir))
    target.mkdir(parents=True, exist_ok=True)
    state = data.state_map(canonical(data, args.state))
    for p, content in sorted(state.items()):
        (target / p).parent.mkdir(parents=True, exist_ok=True)
        (target / p).write_bytes(content)
    return 0


def canonical(data, name):
    """`finished` is the end of the last step."""
    return data.names()[-1] if name == "finished" else name


def command_store(data, root, args):
    tree = states.read_tree(args.dir, data.roots())
    name = canonical(data, args.state)
    n, kind = name.split("-")
    n = int(n)
    if name == data.names()[-1]:
        for state, path in states.store_finished(data, tree):
            print(STORE_PINNED.format(state=state, path=path))
        print(STORED_FINISHED.format(files=len(tree)))
    elif kind == "done":
        files, absent = states.store_done(data, n, tree)
        print(STORED.format(state=name, files=len(files), absent=len(absent)))
    else:
        try:
            stored = states.store_build(data, n, tree)
        except states.NotStart as error:
            raise Refused(STORE_NOT_START.format(n=n, paths=paths_text(error.paths)))
        print(STORED.format(state=name, files=len(stored), absent=0))
    return 0


# ---- the command line ------------------------------------------------------------------------------------------------

def step_number(text):
    if text not in ("0", "1", "2", "3", "4", "5"):
        print(BAD_STEP, file=sys.stderr)
        raise SystemExit(2)
    return int(text)


def parser():
    p = argparse.ArgumentParser(prog="python -m workshop", description="Move this copy between the workshop's steps.")
    commands = p.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="where this copy stands, and whether each step's tests pass")
    status.add_argument("--quick", action="store_true", help="do not run the tests")
    for name, text in (("start", "put the copy at the start of step N"), ("finish", "put the copy at the end of step N")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("step", type=step_number)
    commands.add_parser("next", help="install the next step's contract, tests and given files; your code stays")
    commands.add_parser("leave", help="remove workshop/ and keep the harness")
    check = commands.add_parser("check", help="the drift check (for the workshop's authors)")
    check.add_argument("states", nargs="*", help="only these states, for example 2-build")
    check.add_argument("--keep", action="store_true", help="keep each temporary folder")
    export = commands.add_parser("export", help="write a state into an empty folder (for the authors)")
    export.add_argument("state")
    export.add_argument("dir")
    store = commands.add_parser("store", help="store a folder as a state (for the authors)")
    store.add_argument("state")
    store.add_argument("dir")
    return p


COMMANDS = {"status": command_status, "start": command_start, "finish": command_finish, "next": command_next,
            "leave": command_leave, "check": command_check, "export": command_export, "store": command_store}


def main(argv=None, root=states.ROOT):
    command_line = parser()
    args = command_line.parse_args(argv)
    root = Path(root)
    try:
        data = states.load(root)
    except states.DataBroken as error:
        print(DATA_BROKEN.format(reason=error), file=sys.stderr)
        return 1
    valid = data.names() + ["finished"]
    for name in (args.states if args.command == "check" else [args.state] if args.command in ("export", "store") else []):
        if name not in valid:
            command_line.error(f"unknown state {name}; the states are {', '.join(valid)}")
    try:
        return COMMANDS[args.command](data, root, args)
    except Refused as error:
        print(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
