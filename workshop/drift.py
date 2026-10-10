"""The drift check: every step's tests, run with the later layers absent and with them switched off."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import tree

COPY_SKIPS = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "*.pyc")


COUNTED = re.compile(r"(\d+) (passed|failed|errors?|skipped)")


def run_pytest(dirs, cwd, env=None):
    """Run pytest on each test folder in turn (together, the folders' conftest files clash). Returns
    (exit code: the first that is not 0, a summary of the counts, seconds). Harness settings from outside are dropped."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("HARNESS_")}
    clean.update(env or {}, PYTHONPATH=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    began, code, counts, last = time.monotonic(), 0, {}, ""
    for folder in dirs:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", folder],
                              cwd=cwd, env=clean, capture_output=True, text=True)
        code = code or done.returncode
        lines = (done.stdout + done.stderr).strip().splitlines() or ["no output"]
        last = lines[-1]
        for number, word in COUNTED.findall(lines[-1]):
            word = "error" if word.startswith("error") else word
            counts[word] = counts.get(word, 0) + int(number)
    summary = ", ".join(f"{counts[w]} {w}" for w in ("passed", "failed", "error", "skipped") if w in counts)
    return code, summary or last, time.monotonic() - began


def tests_of(manifest, ks):
    return [manifest["steps"][k]["tests"].rstrip("/") for k in ks]


LEFT_OUT = {"my/var", "my/brief", "my/modules"}      # the person's own: never read, never copied


def make_copy(root, into, name):
    root = Path(root).resolve()

    def ignore(folder, names):
        skipped = list(COPY_SKIPS(folder, names))
        rel = Path(folder).relative_to(root)
        return skipped + [n for n in names if (rel / n).as_posix() in LEFT_OUT]
    target = Path(into) / name
    shutil.copytree(root, target, ignore=ignore)
    return target


def states(manifest, root):
    """The states to prove, in order: (name, what it is, function(tmp) -> (ok, detail))."""
    out = []
    for n in tree.STEPS:
        mine = tests_of(manifest, range(n + 1))

        def absent(tmp, n=n, mine=mine):
            copy = make_copy(root, tmp, f"absent{n}")
            for k in range(n + 1, 6):
                shutil.rmtree(copy / tree.package(manifest, k), ignore_errors=True)
            code, summary, secs = run_pytest(mine, copy)
            return code == 0, f"layers 0-{n}: {summary}", secs

        def switched(tmp, n=n, mine=mine):
            copy = make_copy(root, tmp, f"switched{n}")
            code, summary, secs = run_pytest(mine, copy, {"HARNESS_LAYERS": str(n)})
            return code == 0, f"layers 0-{n}: {summary}", secs

        def started(tmp, n=n):
            copy = make_copy(root, tmp, f"start{n}")
            tree.start(copy, manifest, n, aside=False, ref=None)
            before = tests_of(manifest, range(n))
            code, summary, secs = run_pytest(before or tests_of(manifest, [0]), copy)
            if n == 0:
                return code == 0, f"nothing to build; layer 0: {summary}", secs
            code2, summary2, secs2 = run_pytest(tests_of(manifest, [n]), copy)
            ok = code == 0 and code2 not in (0, 5)       # 5: nothing collected, which proves nothing
            return ok, f"earlier: {summary}; step {n}: {summary2}", secs + secs2

        out += [(f"layers<={n} only", absent), (f"HARNESS_LAYERS={n}", switched), (f"start {n}", started)]
    return out


def check(manifest, root=tree.ROOT, *, write=print, workers=4, only=None) -> int:
    """Print one line per state. Returns 0 when nothing surprised, else 1."""
    found = tree.problems(manifest, root)
    failures = len(found)
    write(f"{'manifest':<18}{'ok' if not found else 'DRIFT'}  "
          f"{sum(len(tree.step_files(manifest, k)) for k in tree.STEPS) + len(manifest['core'])} files, 6 steps")
    for line in found:
        write(f"  {line}")
    if found:
        return 1
    wanted = [s for s in states(manifest, root) if only is None or s[0] in only]
    with tempfile.TemporaryDirectory(prefix="workshop-check-") as tmp, ThreadPoolExecutor(workers) as pool:
        jobs = [(name, pool.submit(fn, tmp)) for name, fn in wanted]
        for name, job in jobs:
            try:
                ok, detail, secs = job.result()
            except Exception as error:      # a state that could not run is a surprise too
                ok, detail, secs = False, f"could not run: {error}", 0.0
            failures += not ok
            write(f"{name:<18}{'ok' if ok else 'SURPRISE'}  {detail} ({secs:.0f} s)")
    write("Nothing surprised." if not failures else f"{failures} state(s) surprised.")
    return 1 if failures else 0
