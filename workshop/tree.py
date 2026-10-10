"""The manifest, the git calls and the file moves behind every command. Standard library only (DESIGN.md)."""
import json
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).with_name("manifest.json")
LAYERS_FILE = Path("my/var/layers")
SET_ASIDE = Path("my/var/set-aside")
STEPS = range(6)
NO_GIT = ("This copy is not a git checkout, so there is nothing to restore from. "
          "Nothing was changed. Clone the repository again, or copy the files from someone who has them.")


class Problem(Exception):
    """A message for the person, printed as it is. Nothing has been changed when one is raised."""


def load(path=MANIFEST) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert [s["step"] for s in data["steps"]] == list(STEPS)
        for key in ("built", "given"):
            assert all(isinstance(f, str) for s in data["steps"] for f in s[key])
        assert all(isinstance(f, str) for f in data["core"])
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        raise Problem(f"workshop/manifest.json is not readable ({error.__class__.__name__}). "
                      "Restore it with: git checkout -- workshop/manifest.json") from None
    return data


def step_files(manifest, k):
    step = manifest["steps"][k]
    return list(step["built"]) + list(step["given"])


def package(manifest, k):
    return manifest["steps"][k]["package"]       # "harness/calc/", or None for step 0


def files_under(root, folder):
    """Relative paths of the files under a folder, without caches."""
    base = Path(root) / folder
    return sorted(p.relative_to(root).as_posix() for p in base.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def problems(manifest, root=ROOT) -> list[str]:
    """Where the manifest and the tree disagree: every file under harness/ is in exactly one place."""
    found, seen = [], {}
    for where, listed in [("the core", manifest["core"])] + [(f"step {k}", step_files(manifest, k)) for k in STEPS]:
        for rel in listed:
            if rel in seen:
                found.append(f"{rel} is in {seen[rel]} and in {where}")
            seen[rel] = where
    tree = set(files_under(root, "harness"))
    found += [f"{rel} ({seen[rel]}) is not in the tree" for rel in sorted(set(seen) - tree)]
    found += [f"{rel} is under harness/ but in no step and not in the core" for rel in sorted(tree - set(seen))]
    for k in STEPS:
        step = manifest["steps"][k]
        if any(f.startswith("harness/") and package(manifest, k) and not f.startswith(package(manifest, k))
               for f in step_files(manifest, k)):
            found.append(f"step {k} lists a file outside {package(manifest, k)}")
        if not any((Path(root) / step["tests"]).glob("test_*.py")):
            found.append(f"{step['tests']} has no tests")
    return found


# git ------------------------------------------------------------------------------------------------------------

def is_git(root=ROOT) -> bool:
    return (Path(root) / ".git").exists() and shutil.which("git") is not None


def reference(manifest, root=ROOT) -> str:
    """The commit the finished files come from: the manifest's, else HEAD."""
    ref = manifest.get("reference") or "HEAD"
    probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"],
                           capture_output=True)
    if probe.returncode:
        raise Problem(f"The commit {ref} named for the finished files is not in this repository. Nothing was changed.")
    return ref


def at_reference(root, ref, rel):
    """The bytes of a file at the reference commit, or None when the commit does not have it."""
    shown = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{rel}"], capture_output=True)
    return shown.stdout if shown.returncode == 0 else None


# moving files ---------------------------------------------------------------------------------------------------

def set_aside(root, rels, ref, *, stamp=None) -> Path | None:
    """Copy each file that differs from the reference (every file when there is no reference) to
    my/var/set-aside/<timestamp>/<path>. Returns that folder, or None when nothing differed."""
    root = Path(root)
    changed = [rel for rel in rels if (root / rel).is_file()
               and (ref is None or (root / rel).read_bytes() != at_reference(root, ref, rel))]
    if not changed:
        return None
    base = root / SET_ASIDE / (stamp or time.strftime("%Y%m%d-%H%M%S"))
    folder, n = base, 1
    while folder.exists():
        n += 1
        folder = base.with_name(f"{base.name}-{n}")
    for rel in changed:
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, folder / rel)
    return folder


def start(root, manifest, n, *, aside=True, ref="unset") -> dict:
    """Remove layer n's built files and the packages of later layers, setting aside what differs first."""
    root = Path(root)
    if ref == "unset":
        ref = reference(manifest, root) if is_git(root) else None
    doomed = [f for f in manifest["steps"][n]["built"] if (root / f).is_file()]
    folders = [package(manifest, k) for k in range(n + 1, 6) if (root / package(manifest, k)).is_dir()]
    for folder in folders:
        doomed += files_under(root, folder.rstrip("/"))
    kept = set_aside(root, doomed, ref) if aside else None
    for rel in doomed:
        (root / rel).unlink()
    if n and (root / package(manifest, n) / "__pycache__").is_dir():
        shutil.rmtree(root / package(manifest, n) / "__pycache__")
    for folder in folders:
        shutil.rmtree(root / folder)
    return {"removed": doomed, "set_aside": kept}


def finish(root, manifest, n) -> dict:
    """Put back the files of layers 1 to n from the reference commit, setting aside those that differ."""
    root = Path(root)
    if not is_git(root):
        raise Problem(NO_GIT)
    ref = reference(manifest, root)
    wanted = [rel for k in range(1, n + 1) for rel in step_files(manifest, k)]
    content = {rel: at_reference(root, ref, rel) for rel in wanted}
    missing = [rel for rel, data in content.items() if data is None]
    if missing:
        raise Problem(f"The commit {ref} does not have: {', '.join(missing)}. Nothing was changed.")
    todo = [rel for rel, data in content.items() if not (root / rel).is_file() or (root / rel).read_bytes() != data]
    kept = set_aside(root, todo, ref)
    for rel in todo:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(content[rel])
    return {"restored": todo, "same": len(wanted) - len(todo), "set_aside": kept, "ref": ref}


def read_layers_file(root=ROOT):
    try:
        return (Path(root) / LAYERS_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def write_layers_file(root, n):
    path = Path(root) / LAYERS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{n}\n", encoding="utf-8")


def present(root, manifest) -> list[bool]:
    """Per layer 0 to 5: is its package there (layer.py), whatever the setting says."""
    return [True] + [(Path(root) / package(manifest, k) / "layer.py").is_file() for k in range(1, 6)]
