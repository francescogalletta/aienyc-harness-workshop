"""Runs one module in a process of its own (SPEC 5.3).

The harness starts this file with `python -I` and talks to it over standard
input and output, so a module that misbehaves cannot disturb the harness,
and what it prints is never mistaken for a result.

    python -I runner.py <module folder>      then one JSON request on standard input:
        {"action": "test"}                    run the unit tests and the golden examples
        {"action": "call", "inputs": {...}}   run calculate(**inputs)
"""
import contextlib
import importlib
import io
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import values  # noqa: E402  (the sibling file; this script runs outside the package)


def load(folder: Path):
    spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(folder))
    return spec, importlib.import_module("module")


def call(spec: dict, module, inputs: dict):
    kinds = {item["name"]: item["type"] for item in spec["inputs"]}
    missing = [name for name in kinds if name not in inputs]
    extra = [name for name in inputs if name not in kinds]
    if missing or extra:
        raise ValueError(f"wrong inputs: missing {missing}, not expected {extra}")
    arguments = {}
    for name, kind in kinds.items():
        try:
            arguments[name] = values.from_json(inputs[name], kind)
        except ValueError as error:
            raise ValueError(f"input '{name}': {error}") from None
    return values.to_json(module.calculate(**arguments))


def run_tests(folder: Path, spec: dict, module) -> dict:
    report = {"tests": [], "golden": []}
    tests = importlib.import_module("tests")
    for name in sorted(vars(tests)):
        if name.startswith("test_") and callable(getattr(tests, name)):
            try:
                getattr(tests, name)()
                report["tests"].append({"name": name, "passed": True})
            except Exception:
                report["tests"].append({"name": name, "passed": False,
                                        "error": traceback.format_exc(limit=4)})
    golden_path = folder / "golden.json"
    examples = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.exists() else []
    for index, example in enumerate(examples, start=1):
        try:
            got = call(spec, module, example["inputs"])
            passed = values.same(example["expected"], got)
            report["golden"].append({"index": index, "passed": passed, "got": got})
        except Exception as error:
            report["golden"].append({"index": index, "passed": False,
                                     "error": f"{type(error).__name__}: {error}"})
    report["passed"] = (bool(report["tests"]) and all(t["passed"] for t in report["tests"])
                        and all(g["passed"] for g in report["golden"]))
    return report


def main() -> None:
    folder = Path(sys.argv[1])
    request = json.loads(sys.stdin.read())
    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):       # a module's own output is not a result
            spec, module = load(folder)
            if request["action"] == "test":
                answer = {"ok": True, "report": run_tests(folder, spec, module)}
            else:
                answer = {"ok": True, "output": call(spec, module, request["inputs"])}
    except Exception as error:
        answer = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    sys.stdout.write(json.dumps(answer))


if __name__ == "__main__":
    main()
