"""CLAUDE.md rule 1: nothing under scoreanim/core/ may import Qt.

Walks every .py file under core/ as an AST and rejects any import of
PySide6/PyQt/Qt at any nesting depth (module level, inside functions,
inside try/except) — an import-time check would miss lazy imports.
"""

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "scoreanim" / "core"

FORBIDDEN_PREFIXES = ("PySide6", "PySide2", "PyQt5", "PyQt6", "qtpy", "Qt")


def _forbidden(module_name: str | None) -> bool:
    if not module_name:
        return False
    top = module_name.split(".")[0]
    return top in FORBIDDEN_PREFIXES


def test_core_never_imports_qt() -> None:
    assert CORE.is_dir(), f"core package missing at {CORE}"
    violations: list[str] = []
    for py in sorted(CORE.rglob("*.py")):
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _forbidden(alias.name):
                        violations.append(f"{py}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and _forbidden(node.module):
                    violations.append(f"{py}:{node.lineno} from {node.module} import ...")
    assert not violations, "Qt import(s) inside core/:\n" + "\n".join(violations)
