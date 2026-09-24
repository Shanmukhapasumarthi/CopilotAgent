"""Static checks for generated Python. This is not a sandbox."""

from __future__ import annotations

import ast
from dataclasses import dataclass

ALLOWED_SOLUTION_MODULES = {
    "abc",
    "array",
    "bisect",
    "collections",
    "copy",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "fractions",
    "functools",
    "heapq",
    "itertools",
    "json",
    "math",
    "numbers",
    "operator",
    "re",
    "statistics",
    "string",
    "typing",
    "unicodedata",
}

ALLOWED_TEST_MODULES = ALLOWED_SOLUTION_MODULES | {"pytest", "solution", "unittest"}

FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",
    "exit",
    "quit",
    "open",
    "input",
}


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    error: str | None = None


def validate_python(source: str, *, kind: str = "solution", max_chars: int = 20000) -> GuardResult:
    if not source or not source.strip():
        return GuardResult(False, "Generated source was empty")
    if len(source) > max_chars:
        return GuardResult(False, f"Generated source exceeds {max_chars} characters")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return GuardResult(False, f"SyntaxError: {exc.msg} (line {exc.lineno})")

    allowed = ALLOWED_TEST_MODULES if kind == "tests" else ALLOWED_SOLUTION_MODULES
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in allowed:
                    return GuardResult(False, f"Disallowed import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level and kind != "tests":
                return GuardResult(False, "Relative imports are not allowed in solution code")
            if node.module:
                root = node.module.split(".")[0]
                if root not in allowed:
                    return GuardResult(False, f"Disallowed import: {node.module}")
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in FORBIDDEN_CALLS:
                return GuardResult(False, f"Disallowed call: {name}")
    compile(source, "<generated>", "exec")
    return GuardResult(True, None)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
