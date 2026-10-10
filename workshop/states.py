"""The manifest, the stored states, resolving, materialising, setting aside, and where a copy stands (DESIGN 4 to 8.1).

Every function takes the root folder as an argument; ROOT is only the default. Paths are written with "/", relative to
the root. Standard library only; nothing from harness/ is imported (files are read as bytes)."""
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET_ASIDE_FOLDER = "my/var/set-aside"


class DataBroken(Exception):
    """A file of the workshop data is missing or not valid JSON."""


class InTheWay(Exception):
    """A folder where a file should be, or the other way round."""

    def __init__(self, path):
        super().__init__(path)
        self.path = path


# ---- reading files -------------------------------------------------------------------------------------------------

def is_ignored(parts):
    return any(part in ("__pycache__", ".pytest_cache") for part in parts) or parts[-1].endswith(".pyc")


def is_shared(path):
    """SPEC.md and the tests: the same bytes in every state that has them, taken from the finished tree (DESIGN 6)."""
    return path == "SPEC.md" or path.startswith("tests/")


def test_step(path):
    """The step whose folder `path` is in (tests/step<N>/...), or None for the fixtures and tests/data."""
    match = re.match(r"tests/step(\d+)/", path)
    return int(match.group(1)) if match else None


def under(path, entry):
    """Is `path` the file `entry`, or below the folder `entry` (an entry ending in "/")?"""
    return path.startswith(entry) if entry.endswith("/") else path == entry


def read_tree(folder, roots):
    """The tree of a folder (DESIGN 3): path -> bytes for every file under the managed roots, minus ignored names."""
    folder = Path(folder)
    tree = {}
    for root in roots:
        start = folder / root.rstrip("/")
        files = [start] if start.is_file() else sorted(start.rglob("*")) if start.is_dir() else []
        for file in files:
            relative = file.relative_to(folder)
            if file.is_file() and not is_ignored(relative.parts):
                tree[relative.as_posix()] = file.read_bytes()
    return tree


def dump_json(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DataBroken(f"{path.parent.name + '/' if path.parent.name else ''}{path.name} is missing")
    except (ValueError, UnicodeDecodeError):
        raise DataBroken(f"{path.name} is not valid JSON")


# ---- the data ------------------------------------------------------------------------------------------------------

class Data:
    """manifest.json and states/ of a root, loaded once. `steps` is the number of steps in the manifest."""

    def __init__(self, root, manifest, finished, overlays, absent, starts):
        self.root = Path(root)
        self.manifest = manifest
        self.finished = finished          # path -> bytes
        self.overlays = overlays          # N -> {path: bytes}, the files of N-done
        self.absent = absent              # N -> sorted list of paths
        self.starts = starts              # N -> {path: bytes}, the files of N-build
        self.steps = len(manifest["steps"])
        self._maps = {}

    # names
    def names(self):
        return [f"{n}-{kind}" for n in range(self.steps) for kind in ("build", "done")]

    def step(self, n):
        return self.manifest["steps"][n]

    def roots(self):
        return self.manifest["roots"]

    def all_paths(self):
        """U: every path that some state has."""
        paths = set(self.finished)
        for n in range(self.steps - 1):
            paths |= set(self.overlays[n]) | set(self.absent[n])
        for n in self.starts:
            paths |= set(self.starts[n])
        return paths

    def expand(self, entries):
        """Files and folders ("x/") of the manifest, expanded over U: a sorted list of paths."""
        paths = self.all_paths()
        return sorted(p for p in paths if any(under(p, entry) for entry in entries))

    def given(self, n):
        """What step N installs: its given files and its tests folder, folders expanded over U."""
        return self.expand([*self.step(n)["given"], self.step(n)["tests"]])

    def start_paths(self, n):
        return list(self.step(n)["start"])

    def code_paths(self):
        paths = set()
        for step in self.manifest["steps"]:
            paths |= set(step["built"]) | set(step["start"]) | set(step["changed"])
        return paths

    def contract_files(self):
        return sorted(self.all_paths() - self.code_paths())

    # content (DESIGN 6)
    def done_map(self, n):
        """The map of N-done: SPEC.md and the tests of steps 0 to N from finished/, the rest as finished/ with this
        state's overlay and absent list (the last step has neither: it is the finished tree)."""
        key = ("done", n)
        if key not in self._maps:
            state = {p: b for p, b in self.finished.items()
                     if is_shared(p) and (test_step(p) is None or test_step(p) <= n)}
            for p, b in self.finished.items():
                if not is_shared(p) and p not in self.absent.get(n, ()):
                    state[p] = b
            state.update(self.overlays.get(n, {}))
            self._maps[key] = state
        return self._maps[key]

    def build_map(self, n, with_start=True):
        key = ("build", n, with_start)
        if key not in self._maps:
            if n == 0:
                before = {}
            else:
                before = self.done_map(n - 1)
            state = dict(before)
            done = self.done_map(n)
            for p in self.given(n):
                if p in done:
                    state[p] = done[p]
                else:
                    state.pop(p, None)
            if with_start:
                for p in self.start_paths(n):
                    if p in self.starts.get(n, {}):
                        state[p] = self.starts[n][p]
            self._maps[key] = state
        return self._maps[key]

    def state_map(self, name):
        n, kind = name.split("-")
        return self.done_map(int(n)) if kind == "done" else self.build_map(int(n))

    def content(self, name, path):
        return self.state_map(name).get(path)

    def known_versions(self, path):
        return {state[path] for state in map(self.state_map, self.names()) if path in state}

    def label(self, name):
        n, kind = name.split("-")
        if kind == "build":
            return f"the start of step {n}"
        if int(n) == self.steps - 1:
            return f"the end of step {n}, the finished harness"
        return f"the end of step {n}"


def load(root=ROOT):
    """Load manifest.json and states/ from root/workshop. Raises DataBroken when something is missing or not JSON."""
    base = Path(root) / "workshop"
    manifest = read_json(base / "manifest.json")
    try:
        steps = len(manifest["steps"])
        roots = manifest["roots"]
    except (KeyError, TypeError):
        raise DataBroken("manifest.json has no steps or roots")
    states = base / "states"
    if not (states / "finished").is_dir():
        raise DataBroken("states/finished is missing")
    finished = _read_folder(states / "finished")
    overlays, absent, starts = {}, {}, {}
    for n in range(steps - 1):
        overlays[n] = _read_folder(states / f"{n}-done" / "files")
        listed = read_json(states / f"{n}-done" / "absent.json")
        if not isinstance(listed, list):
            raise DataBroken(f"{n}-done/absent.json is not a list")
        absent[n] = listed
    for n in range(steps):
        starts[n] = _read_folder(states / f"{n}-build" / "files")
    return Data(root, manifest, finished, overlays, absent, starts)


def _read_folder(folder):
    """Every file below a folder, keyed by its path relative to the folder; a missing folder holds nothing."""
    tree = {}
    if folder.is_dir():
        for file in sorted(folder.rglob("*")):
            relative = file.relative_to(folder)
            if file.is_file() and not is_ignored(relative.parts):
                tree[relative.as_posix()] = file.read_bytes()
    return tree


# ---- where the copy stands (DESIGN 8.1) -----------------------------------------------------------------------------

def where(data, tree):
    """Where the copy stands, as a dict with
       exact     the name of the state whose content equals the tree over U, or None;
       contract  the highest step whose contract files are all in the tree, or None;
       own_code  with a contract: the code paths that differ from the end of that step;
       closest   without a contract: the step with fewest differing contract files, and
       differ    those paths."""
    paths = data.all_paths()
    exact = None
    for name in data.names():
        state = data.state_map(name)
        if all(tree.get(p) == state.get(p) for p in paths):
            exact = name
            break
    contract_files = data.contract_files()
    differing = {n: [p for p in contract_files if tree.get(p) != data.done_map(n).get(p)] for n in range(data.steps)}
    fitting = [n for n in differing if not differing[n]]
    if fitting:
        n = max(fitting)
        own = sorted(p for p in data.code_paths() if tree.get(p) != data.done_map(n).get(p))
        return {"exact": exact, "contract": n, "own_code": own, "closest": n, "differ": []}
    closest = min(differing, key=lambda k: (len(differing[k]), -k))
    return {"exact": exact, "contract": None, "own_code": [], "closest": closest, "differ": differing[closest]}


# ---- materialising ----------------------------------------------------------------------------------------------------

def stamp_folder(root, now=None):
    """The set-aside folder of one command run: my/var/set-aside/<stamp>, with _2, _3 when it exists."""
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", now or time.localtime())
    base = Path(root) / SET_ASIDE_FOLDER
    folder, k = base / stamp, 1
    while folder.exists():
        k += 1
        folder = base / f"{stamp}_{k}"
    return folder


def apply(data, target, paths, root=None, now=None, report=None):
    """DESIGN 7.1. Bring `paths` of the working tree to `target` (path -> bytes). Returns (written, removed, aside),
    `aside` a list of (path, copy). Raises InTheWay before anything is written. `report(path, copy)` is called for
    each file set aside, before it is copied."""
    root = Path(root or data.root)
    plan = []
    for p in sorted(paths):
        want = target.get(p)
        file = root / p
        if want is not None:
            for place in [file, *[root / parent for parent in _parents(p)]]:
                if place.is_dir() if place == file else place.is_file():
                    raise InTheWay(place.relative_to(root).as_posix())
        have = file.read_bytes() if file.is_file() else None
        if want != have:
            plan.append((p, want, have))
    folder = None
    aside = []
    for p, want, have in plan:
        if have is not None and have not in data.known_versions(p):
            folder = folder or stamp_folder(root, now)
            copy = folder / p
            if report:
                report(p, copy)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / p, copy)
            aside.append((p, copy))
    written = removed = 0
    managed = [r.rstrip("/") for r in data.roots()]
    for p, want, have in plan:
        file = root / p
        if want is None:
            file.unlink()
            removed += 1
            folder = file.parent
            while folder != root and folder.relative_to(root).as_posix() not in managed and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(want)
            written += 1
    return written, removed, aside


def _parents(path):
    return [str(parent.as_posix()) for parent in Path(path).parents if str(parent) != "."]


def materialise(data, name, destination, with_pyproject=True, root=None):
    """DESIGN 7.2. Write the state into `destination` (an existing empty folder); returns it."""
    destination = Path(destination)
    for p, content in sorted(data.state_map(name).items()):
        file = destination / p
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    if with_pyproject:
        shutil.copy2(Path(root or data.root) / "pyproject.toml", destination / "pyproject.toml")
    return destination


def temporary_copy(data, name, root=None):
    return materialise(data, name, tempfile.mkdtemp(prefix=f"workshop-{name}-"), True, root)


# ---- storing (DESIGN 8.7) ---------------------------------------------------------------------------------------------

def write_overlay(states, n, new_state, finished):
    """Rewrite N-done/files and absent.json so that N-done equals `new_state` (path -> bytes) over `finished`."""
    folder = states / f"{n}-done"
    if (folder / "files").exists():
        shutil.rmtree(folder / "files")
    files = {p: b for p, b in new_state.items() if not is_shared(p) and finished.get(p) != b}
    absent = sorted(p for p in finished if not is_shared(p) and p not in new_state)
    for p, content in sorted(files.items()):
        target = folder / "files" / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "absent.json").write_text(dump_json(absent), encoding="utf-8")
    return files, absent


class NotStart(Exception):
    """A store of N-build with files that are not start files."""

    def __init__(self, paths):
        super().__init__(paths)
        self.paths = paths


def store_done(data, n, tree):
    """Store `tree` (path -> bytes) as N-done, N below the last step. Returns (files, absent)."""
    return write_overlay(Path(data.root) / "workshop" / "states", n, tree, data.finished)


def store_build(data, n, tree):
    """Store the start files of step N from `tree`. Raises NotStart when other files differ from the derived start."""
    derived = data.build_map(n, with_start=False)
    start = data.start_paths(n)
    wrong = sorted(p for p in set(tree) | set(derived) if tree.get(p) != derived.get(p) and p not in start)
    if wrong:
        raise NotStart(wrong)
    folder = Path(data.root) / "workshop" / "states" / f"{n}-build" / "files"
    if folder.exists():
        shutil.rmtree(folder)
    stored = [p for p in start if p in tree]
    for p in stored:
        (folder / p).parent.mkdir(parents=True, exist_ok=True)
        (folder / p).write_bytes(tree[p])
    return stored


def store_finished(data, tree):
    """Replace finished/ with `tree` and rewrite every overlay so that no other state changes. Returns the list of
    (state, path) overlay files this added."""
    states = Path(data.root) / "workshop" / "states"
    old = {n: dict(data.done_map(n)) for n in range(data.steps - 1)}
    before = {n: set(data.overlays[n]) for n in range(data.steps - 1)}
    shutil.rmtree(states / "finished", ignore_errors=True)
    for p, content in sorted(tree.items()):
        (states / "finished" / p).parent.mkdir(parents=True, exist_ok=True)
        (states / "finished" / p).write_bytes(content)
    added = []
    for n in range(data.steps - 1):
        files, _ = write_overlay(states, n, old[n], tree)
        added += [(f"{n}-done", p) for p in sorted(set(files) - before[n])]
    return added
