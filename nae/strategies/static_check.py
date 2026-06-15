"""AST-only validation for user strategy modules (Model A).

``validate_strategy`` must not execute user code. Backtests load modules
only after static validation passes.
"""

from __future__ import annotations

import ast
from pathlib import Path

REQUIRED_HOOKS = ("should_enter", "should_exit")
OPTIONAL_HOOKS = ("position_size", "on_data", "on_bar", "filter")

_BLOCKED_IMPORT_ROOTS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "importlib",
        "ctypes",
        "pickle",
        "builtins",
        "multiprocessing",
        "threading",
        "http",
        "urllib",
        "requests",
    }
)

_BLOCKED_CALLS = frozenset({"exec", "eval", "compile", "__import__", "open", "input"})


def _check_node(node: ast.AST, errors: list[str]) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            root = (alias.name or "").split(".")[0]
            if root in _BLOCKED_IMPORT_ROOTS:
                errors.append(f"blocked import: {alias.name}")
    elif isinstance(node, ast.ImportFrom):
        root = (node.module or "").split(".")[0]
        if root in _BLOCKED_IMPORT_ROOTS:
            errors.append(f"blocked import from: {node.module}")
    elif isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id in _BLOCKED_CALLS:
            errors.append(f"blocked call: {fn.id}()")
        if isinstance(fn, ast.Attribute) and fn.attr in _BLOCKED_CALLS:
            errors.append(f"blocked call: {fn.attr}()")
    for child in ast.iter_child_nodes(node):
        _check_node(child, errors)


def static_validate_strategy(path: Path) -> dict:
    """Validate hooks and structure without executing the module."""
    if not path.is_file():
        raise ValueError(f"Strategy file not found: {path}")
    if path.suffix != ".py":
        raise ValueError("Strategy files must be Python (.py)")

    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Syntax error: {exc}") from exc

    errors: list[str] = []
    _check_node(tree, errors)
    if errors:
        raise ValueError("; ".join(errors))

    functions = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    has_params = any(isinstance(node, ast.Assign) for node in tree.body)

    hooks_found = [h for h in REQUIRED_HOOKS + OPTIONAL_HOOKS if h in functions]
    hooks_missing = [h for h in REQUIRED_HOOKS if h not in functions]

    warnings: list[str] = []
    if not has_params:
        warnings.append("No PARAMS assignment found — strategy has no configurable parameters")

    return {
        "file": str(path),
        "valid": not hooks_missing,
        "hooks_found": hooks_found,
        "hooks_missing": hooks_missing,
        "warnings": warnings,
        "static_only": True,
    }
