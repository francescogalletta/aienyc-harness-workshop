"""The command line: `python -m workshop <command>`. See DESIGN.md. Standard library only; never calls a model."""
import argparse
import os
import sys
import time
from pathlib import Path

from . import drift, tree
from .tree import Problem, ROOT

ACCEPT_WORDS = {"/accept", "yes", "y", "yes.", "ok", "okay", "si", "sí"}     # the words the harness takes as a yes
BAD_STEP = "Steps are numbered 0 to 5."
SETTING = {"env": "HARNESS_LAYERS={value} (in your shell)", "file": "my/var/layers says {value}",
           "none": "no setting: every layer that is present is on"}
LEAVE_ASK = ("This removes workshop/: the guides, the prompts and this command. The harness, its tests and my/ stay "
             "as they are. Type yes to remove it: ")
STEPS_HEAD = ("# The six steps\n\nGenerated from `manifest.json` by `uv run python -m workshop steps --write`; "
              "`python -m workshop check` fails when this file is out of date.\n\n")


def setting():
    """Which layers setting applies now, as config reads it: the variable, else my/var/layers, else none."""
    if os.environ.get("HARNESS_LAYERS"):
        return "env", os.environ["HARNESS_LAYERS"]
    value = tree.read_layers_file(ROOT)
    return ("file", value) if value else ("none", "")


def status(manifest, args, write=print):
    here = tree.present(ROOT, manifest)
    kind, value = setting()
    on_limit = int(value) if value.isdigit() else 5
    write("Setting: " + SETTING[kind].format(value=value))
    write("Layer  Package            Present  On   Built files")
    on = True
    for k in tree.STEPS:
        on = on and here[k] and k <= on_limit
        built = manifest["steps"][k]["built"]
        have = sum((ROOT / f).is_file() for f in built)
        name = (tree.package(manifest, k) or "harness/ (core)").ljust(19)
        write(f"  {k}    {name} {'yes' if here[k] else 'no ':<8} {'yes' if on else 'no ':<4} "
              f"{have}/{len(built)}" if built else f"  {k}    {name} {'yes' if here[k] else 'no ':<8} {'yes' if on else 'no ':<4} (given)")
    if args.quick:
        write("Tests not run (--quick).")
        return 0
    write("Tests, per step:")
    for k in tree.STEPS:
        if not here[k]:
            write(f"  step {k}: not run, the package is not here")
            continue
        code, summary, secs = drift.run_pytest(drift.tests_of(manifest, [k]), ROOT)
        write(f"  step {k}: {'pass' if code == 0 else 'FAIL'}  {summary} ({secs:.0f} s)")
    return 0


def cmd_at(manifest, args, write=print):
    n = step_number(args.n)
    tree.write_layers_file(ROOT, n)
    write(f"This copy now runs as the harness at step {n} (my/var/layers holds {n}). Nothing was removed or copied.")
    if os.environ.get("HARNESS_LAYERS"):
        write(f"Your shell sets HARNESS_LAYERS={os.environ['HARNESS_LAYERS']}, which wins over the file. Unset it.")
    gone = [k for k in range(1, n + 1) if not tree.present(ROOT, manifest)[k]]
    if gone:
        write(f"Layer {gone[0]} is not in this copy, so it runs only up to layer {gone[0] - 1}. "
              f"To get it back: python -m workshop finish {n}")
    return 0


def cmd_start(manifest, args, write=print):
    n = step_number(args.n)
    done = tree.start(ROOT, manifest, n)
    if done["set_aside"]:
        write(f"Set aside your changed files in {done['set_aside'].relative_to(ROOT)}/ (a copy; the originals are gone).")
    write(f"Removed {len(done['removed'])} files." if done["removed"] else "There was nothing to remove.")
    if n == 0:
        write("Step 0 has nothing to build: the core is given. Layers 1 to 5 are removed.")
    else:
        given = ", ".join(Path(f).name for f in manifest["steps"][n]["given"]) or "none"
        write(f"Step {n}: build {tree.package(manifest, n)}. Given and kept: {given}. "
              f"Tests: uv run pytest {manifest['steps'][n]['tests']} -q (they fail until you are done).")
    value = tree.read_layers_file(ROOT)
    if value and value.isdigit() and int(value) < n:
        write(f"my/var/layers says {value}, so layer {n} will stay off. Run: python -m workshop at {n}")
    return 0


def cmd_finish(manifest, args, write=print):
    n = step_number(args.n)
    if n == 0:
        write("Step 0 is the given core; there is nothing to restore.")
        return 0
    done = tree.finish(ROOT, manifest, n)
    if done["set_aside"]:
        write(f"Set aside your changed files in {done['set_aside'].relative_to(ROOT)}/ before replacing them.")
    write(f"Restored {len(done['restored'])} files of layers 1 to {n} from {done['ref']}; "
          f"{done['same']} were already as they are there.")
    return 0


def cmd_leave(manifest, args, write=print, ask=input):
    try:
        answer = ask(LEAVE_ASK)
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ACCEPT_WORDS:
        write("Nothing removed.")
        return 0
    import shutil
    shutil.rmtree(ROOT / "workshop")
    write("Removed workshop/. If this copy is in git, commit the removal; git checkout -- workshop brings it back.")
    value = tree.read_layers_file(ROOT)
    if value and value != "5":
        write(f"my/var/layers still says {value}; delete it to run all five layers.")
    return 0


def render_steps(manifest) -> str:
    def names(files, folder):
        return ", ".join(f"`{f.removeprefix(folder)}`" for f in files) or "none"
    rows = ["| Step | Principle | Package | You build | Given | Test | Then you can run |", "|---|---|---|---|---|---|---|"]
    for step in manifest["steps"]:
        folder = step["package"] or ""
        k = step["step"]
        if k == 0:
            core = sorted({f.rsplit("/", 1)[0] + "/" if f.count("/") > 1 else "harness/*.py" for f in manifest["core"]})
            built, given = "nothing, the core is given", f"{len(manifest['core'])} files: " + ", ".join(f"`{c}`" for c in core)
        else:
            built, given = names(step["built"], folder), names(step["given"], folder)
        rows.append(f"| {k} | {step['principle']} | {('`' + folder + '`') if folder else '`harness/`'} | {built} | {given} | "
                    f"`uv run pytest {step['tests'].rstrip('/')} -q` | {step['run']} |")
    return STEPS_HEAD + "\n".join(rows) + "\n"


def cmd_steps(manifest, args, write=print):
    text = render_steps(manifest)
    if args.write:
        (Path(__file__).resolve().parent / "STEPS.md").write_text(text, encoding="utf-8")
        write("Wrote workshop/STEPS.md.")
    else:
        write(text.rstrip("\n"))
    return 0


def cmd_check(manifest, args, write=print):
    stale = []
    steps_md = Path(__file__).resolve().parent / "STEPS.md"
    if not steps_md.is_file() or steps_md.read_text(encoding="utf-8") != render_steps(manifest):
        stale = ["workshop/STEPS.md is out of date: run python -m workshop steps --write"]
    code = drift.check(manifest, ROOT, write=write, workers=args.workers)
    for line in stale:
        write(line)
    return 1 if stale else code


def step_number(text):
    if not (text.isascii() and text.isdigit() and int(text) in tree.STEPS):
        raise Problem(BAD_STEP)
    return int(text)


def parser():
    top = argparse.ArgumentParser(prog="python -m workshop", description="Move this copy between the six steps.")
    sub = top.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="which layers are present and on, and whether each step's tests pass") \
        .add_argument("--quick", action="store_true", help="do not run the tests")
    for name, text in (("at", "run this copy as the harness at step N (writes my/var/layers; removes nothing)"),
                       ("start", "remove step N's built files and later layers, to build step N yourself"),
                       ("finish", "restore the files of layers 1 to N from git")):
        sub.add_parser(name, help=text).add_argument("n", metavar="N", help="0 to 5")
    sub.add_parser("leave", help="remove workshop/ and keep the harness")
    check = sub.add_parser("check", help="the drift check: every step's tests with later layers absent and off")
    check.add_argument("--workers", type=int, default=4)
    sub.add_parser("steps", help="print the table of steps").add_argument("--write", action="store_true")
    return top


COMMANDS = {"status": status, "at": cmd_at, "start": cmd_start, "finish": cmd_finish, "leave": cmd_leave,
            "check": cmd_check, "steps": cmd_steps}


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return COMMANDS[args.command](tree.load(), args)
    except Problem as problem:
        print(problem, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
