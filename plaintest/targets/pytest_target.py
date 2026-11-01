"""The pytest Target: Python code, tests tagged with `@pytest.mark.check("<check id>")`.

Conventions:
- a subject is `path/to/file.py::Name.attr` relative to the project root;
- generated tests go in `<project>/tests/plaintest/test_<spec id>.py`;
- tests run with `python -m pytest` from the project root, so they import the code by path
  from the root (`from cart import Cart`).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..models import Test
from .base import Outcome, Run
from .pytest_plugin import RESULTS_ENV

PLAINTEST_ROOT = Path(__file__).resolve().parents[2]  # so the test process can import the plugin


class PytestTarget:
    name = "pytest"
    language = "Python"
    notes = (
        "Tests run with `python -m pytest` from the project root, so import the code under test "
        "by its module path from the root (for `cart.py`, `from cart import Cart`). "
        "Use plain functions and `assert`; use `pytest.raises` for expected errors."
    )

    def read_code(self, project: Path, paths: list[Path]) -> str:
        parts = []
        for p in paths:
            p = Path(p).resolve()
            parts.append(f"### {p.relative_to(Path(project).resolve()).as_posix()}\n"
                         f"```python\n{p.read_text()}```")
        return "\n\n".join(parts)

    def subject_file(self, project: Path, subject: str) -> Path:
        return Path(project) / subject.split("::", 1)[0]

    def subject_exists(self, project: Path, subject: str) -> bool:
        path = self.subject_file(project, subject)
        if not path.exists():
            return False
        if "::" not in subject:
            return True
        body = ast.parse(path.read_text()).body
        for name in subject.split("::", 1)[1].split("."):
            node = next((n for n in body if _defines(n, name)), None)
            if node is None:
                return False
            body = getattr(node, "body", [])
        return True

    def test_file(self, project: Path, spec_id: str) -> Path:
        return Path(project) / "tests" / "plaintest" / f"test_{spec_id.replace('-', '_')}.py"

    def tag(self, check_id: str) -> str:
        return f'@pytest.mark.check("{check_id}")'

    def find_tests(self, project: Path) -> list[Test]:
        project = Path(project)
        tests = []
        for file in sorted(project.glob("tests/**/test_*.py")):
            rel = file.relative_to(project).as_posix()
            try:
                tree = ast.parse(file.read_text())
            except SyntaxError:
                continue  # a test that doesn't parse covers nothing; `runs` will say why
            for prefix, fn in _test_functions(tree):
                for check_id in _check_tags(fn):
                    tests.append(Test(check_id=check_id, name=f"{rel}::{prefix}{fn.name}", file=file))
        return tests

    def run(self, project: Path, tests: list[Test]) -> dict[str, Run]:
        if not tests:
            return {}
        project = Path(project).resolve()
        files = sorted({str(t.file.resolve().relative_to(project)) for t in tests})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "results.json"
            env = {
                **os.environ,
                RESULTS_ENV: str(out),
                "PYTHONPATH": os.pathsep.join(filter(None, [str(PLAINTEST_ROOT), os.environ.get("PYTHONPATH")])),
            }
            cmd = [sys.executable, "-m", "pytest", "-q", "-p", "plaintest.targets.pytest_plugin",
                   "-p", "no:cacheprovider", "--rootdir", str(project), *files]
            proc = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True, timeout=600)
            results = json.loads(out.read_text()) if out.exists() else {}

        runs = {}
        for t in tests:
            file_id = t.name.split("::", 1)[0]
            r = results.get(t.name) or results.get(file_id)
            if r is None:
                r = {"outcome": "error", "detail": "the test did not run\n" + proc.stdout[-1500:]}
            runs[t.name] = Run(Outcome(r["outcome"]), r["detail"])
        return runs


def _defines(node: ast.stmt, name: str) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == name
    return False


def _test_functions(tree: ast.Module):
    """(node-id prefix, function) for top-level test functions and methods of Test classes."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield "", node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test"):
                    yield f"{node.name}::", m


def _check_tags(fn: ast.FunctionDef) -> list[str]:
    """The IDs in every `@pytest.mark.check("<id>")` on a function."""
    ids = []
    for d in fn.decorator_list:
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "check"
                and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)):
            ids.append(d.args[0].value)
    return ids
