"""Regression tests for Python 3.9-3.13 & PyQt5/PyQt6 (Anki 2.1.50+) compatibility."""
from __future__ import annotations

import ast
import pathlib
import warnings
from types import SimpleNamespace

from aqt.qt import QStyle, QStyleOptionViewItem, Qt

from ankizin.compat import clear_style_state, qt_flag_int

_PKG_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _introduced_python_files() -> list[pathlib.Path]:
    files = [
        _PKG_ROOT / "__init__.py",
        _PKG_ROOT / "compat.py",
        _PKG_ROOT / "constants.py",
    ]
    for sub in ("onboarding", "study_hub", "ui", "home"):
        files.extend(sorted((_PKG_ROOT / sub).rglob("*.py")))
    return files


def test_py39_to_313_and_qt_compat_invariants():
    # 1. qt_flag_int works for both PyQt6 scoped enums and PyQt5 int-like QFlags
    combined = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    assert isinstance(qt_flag_int(combined), int)
    assert qt_flag_int(combined) == int(getattr(combined, "value", combined))

    class _PyQt5Flag(int):
        def __or__(self, other):
            return _PyQt5Flag(int(self) | int(other))

    assert qt_flag_int(_PyQt5Flag(0x0082)) == 0x0082

    # 2. clear_style_state works on real QStyleOptionViewItem (PyQt6)
    opt = QStyleOptionViewItem()
    opt.state |= QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus
    clear_style_state(
        opt,
        QStyle.StateFlag.State_Selected,
        QStyle.StateFlag.State_MouseOver,
        QStyle.StateFlag.State_HasFocus,
    )
    assert not (opt.state & QStyle.StateFlag.State_Selected)
    assert not (opt.state & QStyle.StateFlag.State_MouseOver)
    assert not (opt.state & QStyle.StateFlag.State_HasFocus)

    # 3. clear_style_state also works on PyQt5-style QFlags where `opt.state &= ~int` fails
    class _PyQt5QFlags:
        def __init__(self, val: int) -> None:
            self._v = int(val)

        def __int__(self) -> int:
            return self._v

        def __or__(self, other):
            return _PyQt5QFlags(self._v | int(other))

    stub_opt = SimpleNamespace(state=_PyQt5QFlags(0b1111))
    clear_style_state(stub_opt, _PyQt5QFlags(0b0010), _PyQt5QFlags(0b0100))
    assert isinstance(stub_opt.state, _PyQt5QFlags)
    assert int(stub_opt.state) == 0b1001

    # 4. AST & SyntaxWarning checks across all introduced modules
    for path in _introduced_python_files():
        src = path.read_text(encoding="utf-8")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", SyntaxWarning)
            compile(src, str(path), "exec")
        syntax_warnings = [w for w in caught if issubclass(w.category, SyntaxWarning)]
        assert not syntax_warnings, f"SyntaxWarning in {path}: {syntax_warnings[0].message}"

        tree = ast.parse(src, filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        has_future_ann = any(
            isinstance(n, ast.ImportFrom)
            and n.module == "__future__"
            and any(a.name == "annotations" for a in n.names)
            for n in tree.body
        )

        for node in ast.walk(tree):
            # Disallow `match` statement (Python 3.10+)
            assert not isinstance(node, ast.Match), f"Python 3.10+ match statement in {path}:{node.lineno}"

            # Disallow runtime `|` in isinstance / issubclass (Python 3.10+)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("isinstance", "issubclass"):
                if len(node.args) >= 2:
                    has_bitor = any(
                        isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
                        for sub in ast.walk(node.args[1])
                    )
                    assert not has_bitor, f"Python 3.10+ union type in {node.func.id}() in {path}:{node.lineno}"

            # Disallow `|` in annotations unless `from __future__ import annotations` is present
            if not has_future_ann:
                anns = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    anns.extend(
                        a.annotation
                        for a in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
                        if a.annotation is not None
                    )
                    if node.args.vararg and node.args.vararg.annotation is not None:
                        anns.append(node.args.vararg.annotation)
                    if node.args.kwarg and node.args.kwarg.annotation is not None:
                        anns.append(node.args.kwarg.annotation)
                    if node.returns is not None:
                        anns.append(node.returns)
                elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
                    anns.append(node.annotation)
                for ann in anns:
                    has_bitor = any(
                        isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
                        for sub in ast.walk(ann)
                    )
                    assert not has_bitor, f"Python 3.10+ | annotation without __future__ in {path}:{node.lineno}"

            # Disallow .exec_() calls (removed in PyQt6)
            if isinstance(node, ast.Attribute) and node.attr == "exec_":
                raise AssertionError(f"Deprecated .exec_() attribute in {path}:{node.lineno}")

            # Disallow unscoped Qt.<Member> accesses (e.g. Qt.AlignCenter instead of Qt.AlignmentFlag.AlignCenter)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Qt":
                parent = parents.get(node)
                if not (isinstance(parent, ast.Attribute) and parent.value is node):
                    raise AssertionError(f"Unscoped Qt.{node.attr} in {path}:{node.lineno}")
