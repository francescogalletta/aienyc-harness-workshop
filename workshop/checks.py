"""The drift check (DESIGN 9): static checks on the manifest and the stored states, and each state's tests."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import states

STEP_KEYS = ("step", "name", "prompt", "tests", "built", "start", "changed", "given")
LIST_KEYS = ("built", "start", "changed", "given")


def sample(paths):
    paths = list(paths)
    text = ", ".join(paths[:5])
    return text + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")


# ---- the static checks (DESIGN 9.1): each returns a list of problems, empty when it passes ----------------------------

def manifest(data):
    m = data.manifest
    problems = []
    if m.get("format") != 1:
        problems.append("format is not 1")
    for key in ("roots", "always"):
        if not (isinstance(m.get(key), list) and all(isinstance(x, str) for x in m[key])):
            problems.append(f"{key} is not a list of strings")
    steps = m.get("steps")
    if not isinstance(steps, list) or not steps:
        return problems + ["steps is not a list of steps"]
    for k, step in enumerate(steps):
        if not isinstance(step, dict) or set(step) != set(STEP_KEYS):
            problems.append(f"step {k} does not have exactly the keys {', '.join(STEP_KEYS)}")
            continue
        if step["step"] != k:
            problems.append(f"step {k} has the index {step['step']}")
        for key in ("name", "prompt", "tests"):
            if not isinstance(step[key], str) or not step[key]:
                problems.append(f"step {k}: {key} is not a string")
        if step["tests"] != f"tests/step{k}/":
            problems.append(f"step {k}: tests is not tests/step{k}/")
        for key in LIST_KEYS:
            if not (isinstance(step[key], list) and all(isinstance(x, str) for x in step[key])):
                problems.append(f"step {k}: {key} is not a list of strings")
        for key in ("built", "start", "changed"):
            for p in step[key] if isinstance(step[key], list) else []:
                if p.endswith("/") or not p.startswith("harness/"):
                    problems.append(f"step {k}: {key} holds {p}, which is not a file under harness/")
    if problems:
        return problems
    problems += introduced(data)
    return problems


def first_step(data, p):
    """The first step whose end has `p`, or None."""
    return next((n for n in range(data.steps) if p in data.done_map(n)), None)


def introduced(data):
    """Rules 1 and 2 of DESIGN 4.2."""
    problems = []
    names = data.names()
    given = {n: set(data.given(n)) for n in range(data.steps)}
    listed = {n: {"built": set(data.step(n)["built"]), "start": set(data.step(n)["start"])} for n in range(data.steps)}
    for p in sorted(data.all_paths()):
        k = first_step(data, p)
        if k is None:
            problems.append(f"{p}: no state has it")
            continue
        before = names[:names.index(f"{k}-build")]
        if any(p in data.state_map(name) for name in before):
            problems.append(f"{p}: present before the start of step {k}")
            continue
        if p in listed[k]["built"]:
            if p in data.build_map(k):
                problems.append(f"{p}: built in step {k} but present at its start")
        elif not (p in listed[k]["start"] or p in given[k]):
            problems.append(f"{p}: introduced by step {k}, which lists it nowhere")
        elif p not in data.build_map(k):
            problems.append(f"{p}: given in step {k} but absent at its start")
        for j in range(data.steps):
            if j != k and (p in listed[j]["built"] or p in listed[j]["start"]):
                problems.append(f"{p}: introduced by step {k} but built or started in step {j}")
    code = data.code_paths()
    for n in range(data.steps):
        for p in sorted(code & given[n]):
            problems.append(f"{p}: a code path in the given files of step {n}")
        for p in data.step(n)["changed"]:
            j = first_step(data, p)
            if j is None or j >= n or not (p in listed[j]["built"] or p in listed[j]["start"]):
                problems.append(f"{p}: changed in step {n}, which no earlier step builds or starts")
    return problems


def difference(data, n):
    """The paths whose content differs between the end of step N-1 and the end of step N."""
    before = {} if n == 0 else data.done_map(n - 1)
    after = data.done_map(n)
    return {p for p in set(before) | set(after) if before.get(p) != after.get(p)}


def snapshots(data):
    problems = []
    for n in range(data.steps - 1):
        for p, content in data.overlays[n].items():
            if data.finished.get(p) == content:
                problems.append(f"{n}-done/files/{p} equals finished/")
            if states.is_shared(p):
                problems.append(f"{n}-done/files/{p} is SPEC.md or a test: those come from finished/")
        for p in data.absent[n]:
            if p not in data.finished:
                problems.append(f"{n}-done/absent.json names {p}, which finished/ does not have")
            if states.is_shared(p):
                problems.append(f"{n}-done/absent.json names {p}, which is SPEC.md or a test")
    for n in range(data.steps):
        if set(data.starts.get(n, {})) != set(data.step(n)["start"]):
            problems.append(f"{n}-build/files does not hold exactly the start files of step {n}")
    for n in range(data.steps):
        step = data.step(n)
        differ = difference(data, n)
        listed = set(step["built"]) | set(step["start"]) | set(step["changed"]) | set(data.given(n))
        unexplained = sorted(differ - listed)
        if unexplained:
            problems.append(f"step {n}: not in the manifest but different from step {n - 1}: {sample(unexplained)}")
        for key in ("built", "start", "changed"):
            stale = [p for p in step[key] if p not in differ]
            if stale:
                problems.append(f"step {n}: {key} lists files that do not differ: {sample(stale)}")
        for entry in step["given"]:
            if not any(states.under(p, entry) for p in differ):
                problems.append(f"step {n}: given lists {entry}, which does not differ")
    return problems


def finished(data, tree):
    paths = data.all_paths()
    differ = sorted(p for p in paths if tree.get(p) != data.finished.get(p))
    if differ:
        return [f"the working tree differs from finished/ (expected after start, next or finish): {sample(differ)}"]
    return []


LATER_STEP_SENTENCE = 'Passages of `SPEC.md` marked "(step M)" for a step later than this one do not apply yet.'
PROMPT_LISTS = (("Build these files (new):", "built"), ("Change these files (they exist already):", "change"),
                ("Given files (do not edit):", "given"))


def listed_in(text, heading):
    """The paths of the bullets "- `path` (...)" that follow `heading`, up to the first line that is not one."""
    if heading not in text:
        return []
    paths = []
    for line in text.split(heading, 1)[1].splitlines()[1:]:
        if line.startswith("- `"):
            paths.append(line[3:].split("`", 1)[0])
        elif line.strip():
            break
    return paths


def expected_lists(step):
    """What a prompt must list (DESIGN 4.2 rule 4): the files built, the files changed (the start files are given in
    a starting form and changed), and the given files: SPEC.md, the step's tests and the manifest's given entries."""
    return {"built": step["built"], "change": [*step["start"], *step["changed"]],
            "given": ["SPEC.md", step["tests"], *[g for g in step["given"] if g != "SPEC.md"]]}


def prompts(data):
    problems = []
    for n in range(data.steps):
        step = data.step(n)
        file = Path(data.root) / step["prompt"]
        if not file.is_file():
            problems.append(f"{step['prompt']} is missing")
            continue
        text = file.read_text(encoding="utf-8")
        if LATER_STEP_SENTENCE not in text:
            problems.append(f"{step['prompt']} lacks the sentence about passages of a later step")
        for (heading, key), want in zip(PROMPT_LISTS, expected_lists(step).values()):
            have = listed_in(text, heading)
            if sorted(have) != sorted(want) or len(have) != len(set(have)):
                wrong = sorted(set(have) ^ set(want)) or ["a path listed twice"]
                problems.append(f"{step['prompt']}: '{heading}' differs from the manifest: {sample(wrong)}")
    return problems


STATIC = ("manifest", "snapshots", "finished", "prompts")


# ---- each state's tests (DESIGN 9.2) ---------------------------------------------------------------------------------

def pytest_run(args, cwd):
    """Run pytest in cwd with the check's environment. Returns (exit code, output)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HARNESS_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *args],
                            cwd=cwd, env=env, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def last_line(output):
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "no output"


def failing(output):
    return [line.split()[1] for line in output.splitlines() if line.startswith("FAILED") and len(line.split()) > 1][:3]


def folders_of(data, state, up_to):
    """The test folders of a state to run in an N-build: the always folders and steps 0 to up_to."""
    present = [p for p in data.manifest["always"] if any(q.startswith(p) for q in state)]
    steps = [data.step(k)["tests"] for k in range(up_to + 1) if any(q.startswith(data.step(k)["tests"]) for q in state)]
    return present + steps


def check_state(data, name, keep=False, root=None):
    """Run one state. Returns (passed, detail, folder or None)."""
    n, kind = name.split("-")
    n = int(n)
    folder = states.temporary_copy(data, name, root)
    try:
        state = data.state_map(name)
        if kind == "done":
            code, output = pytest_run(["tests"], folder)
            if code == 0:
                return True, f"every test passes ({last_line(output)})", folder
            return False, f"exit {code}: {last_line(output)}; {', '.join(failing(output))}", folder
        step = data.step(n)
        earlier = folders_of(data, state, n - 1) if n else folders_of(data, state, -1)
        problems = []
        if earlier:
            code, output = pytest_run(earlier, folder)
            if code != 0:
                problems.append(f"earlier steps fail (exit {code}): {last_line(output)}; {', '.join(failing(output))}")
        code, output = pytest_run([step["tests"]], folder)
        if code == 0:
            problems.append(f"step {n} passes before it is built")
        elif code == 5:
            problems.append(f"step {n}'s tests collected nothing")
        elif code not in (1, 2):
            problems.append(f"step {n}'s tests ended with exit {code}: {last_line(output)}")
        if problems:
            return False, "; ".join(problems), folder
        return True, f"earlier steps pass and step {n} fails, as it should", folder
    finally:
        if not keep:
            shutil.rmtree(folder, ignore_errors=True)


def timed(function, *args, **kwargs):
    start = time.time()
    result = function(*args, **kwargs)
    return result, int(time.time() - start)
