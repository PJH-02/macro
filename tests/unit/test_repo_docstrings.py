from __future__ import annotations

import ast
from pathlib import Path


def test_all_repository_functions_have_docstrings() -> None:
    missing: list[str] = []

    for path in sorted(Path("src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        path_text = str(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        def visit(
            nodes: list[ast.stmt],
            prefix: str = "",
            *,
            current_path: str = path_text,
        ) -> None:
            for node in nodes:
                if isinstance(node, ast.ClassDef):
                    visit(node.body, prefix=f"{prefix}{node.name}.", current_path=current_path)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if ast.get_docstring(node) is None:
                        missing.append(f"{current_path}:{prefix}{node.name}")

        visit(tree.body)

    assert missing == []
