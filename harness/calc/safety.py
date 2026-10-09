"""A check that code written by a model is only a calculation (SPEC 5.2).

The harness is about to run this code on the person's machine, so it reads
it first. A module may do arithmetic with numbers and dates. It may not
touch files, the network, the system, or Python's own machinery.

This is a check on the code, not a sandbox: it refuses what it recognises.
"""
import ast

ALLOWED_IMPORTS = {"decimal", "datetime", "math", "fractions", "calendar", "statistics"}
FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "input", "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
    "print", "type", "super", "classmethod", "staticmethod", "object",
}
FORBIDDEN_ATTRIBUTES = {"today", "now", "utcnow"}      # reading the clock makes the answer change


def check_code(source: str, also_allow: tuple[str, ...] = ()) -> list[str]:
    """Return why this code is refused. An empty list means it may run."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"line {error.lineno}: it is not valid Python: {error.msg}"]
    allowed = ALLOWED_IMPORTS | set(also_allow)
    problems = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in allowed:
                    problems.append(f"line {line}: imports '{alias.name}', which a calculation may not use")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in allowed:
                problems.append(f"line {line}: imports from '{node.module}', which a calculation may not use")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"line {line}: uses '{node.id}', which a calculation may not use")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            problems.append(f"line {line}: reaches into '{node.attr}', which a calculation may not use")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            problems.append(f"line {line}: uses '{node.attr}', which makes the answer depend on when it runs")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.ClassDef, ast.AsyncFunctionDef,
                               ast.With, ast.AsyncWith, ast.Try, ast.While, ast.Lambda)):
            problems.append(f"line {line}: uses '{type(node).__name__}', which a calculation does not need")
    return sorted(set(problems), key=problems.index)
