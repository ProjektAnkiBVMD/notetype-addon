import ast
import pathlib
import unittest

SRC = pathlib.Path(__file__).parent.parent / "src"


def uses_union_annotation(tree: ast.AST) -> bool:
    """`str | None` in an annotation is evaluated on import, which fails before Python 3.10."""
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations += [a.annotation for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs]
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    return any(
        isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
        for a in annotations if a
        for n in ast.walk(a)
    )


class TestPythonCompat(unittest.TestCase):
    def test_union_annotations_are_not_evaluated(self):
        for path in SRC.rglob("*.py"):
            tree = ast.parse(path.read_text(), feature_version=(3, 9))  # the add-on supports Python 3.9, which Anki 2.1.50 to 25.05 ship
            has_future = any(
                isinstance(n, ast.ImportFrom) and n.module == "__future__"
                and any(a.name == "annotations" for a in n.names)
                for n in tree.body
            )
            if uses_union_annotation(tree):
                self.assertTrue(has_future, f"{path.name}: add `from __future__ import annotations` (Anki may run Python < 3.10)")
