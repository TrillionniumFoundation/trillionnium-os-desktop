"""Source invalidation for named CI Python commands and reviewed local loaders.

This checks repository source, never starts a hosted workflow or infers a
runtime pass. It deliberately does not expand arbitrary data reads, Makefile
targets, ambient packages, or unselected dispatcher branches into dependencies.
"""
from __future__ import annotations

import ast
import copy
import fnmatch
from pathlib import Path
import re
import shlex
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMMAND = re.compile(
    r'^\s*(?:/usr/bin/)?python3\s+(?:-[A-Za-z]+\s+)*["\']?'
    r'(?:[^\s"\']*/)?(?P<path>tools/[A-Za-z0-9_]+\.py)(?=[\s"\';|&<>]|$)'
)
DISPATCHER = "tools/qualify_servo_exact_pin_v3.py"
# These source modules have reviewed, fixed importlib loaders. Their target
# filenames are read from the actual AST, rather than duplicated here.
LOADER_MODULES = frozenset({
    "tools/validate_module_documentation.py",
    "tools/validate_repository.py",
    "tools/validate_project_truth.py",
    "tools/structured_status_repository.py",
    "tools/structured_status.py",
})


def workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def commands(document: dict) -> list[tuple[str, str]]:
    result = []
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            for line in step.get("run", "").replace("\\\n", "").splitlines():
                match = COMMAND.match(line)
                if match:
                    rest = line[match.end():].lstrip('"\' \t')
                    arguments = shlex.split(rest)
                    selector = "verify-d3-patch" if arguments and arguments[0] == "verify-d3-patch" else "default"
                    result.append((match["path"], selector))
    return sorted(set(result))


def resolve(root: Path, current: str, module: str, level: int = 0) -> str | None:
    if level:
        base = Path(current).parent
        for _ in range(level - 1):
            base = base.parent
        path = base.joinpath(*module.split("."))
    else:
        path = Path("tools").joinpath(*module.removeprefix("tools.").split("."))
    candidates = (path.with_suffix(".py"), path / "__init__.py")
    return next((p.as_posix() for p in candidates if (root / p).is_file()), None)


def imports(root: Path, current: str, selector: str) -> list[tuple[str, str]]:
    tree = ast.parse((root / current).read_text(encoding="utf-8"))
    inspected = tree
    if current == DISPATCHER:
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        branch = main.body[0]
        if not isinstance(branch, ast.If) or not any(
            isinstance(n, ast.Constant) and n.value == "verify-d3-patch" for n in ast.walk(branch.test)
        ) or not any(isinstance(n, ast.Return) for n in branch.body):
            raise ValueError("qualification dispatcher no longer has its reviewed returning branch")
        inspected = ast.Module(body=branch.body if selector == "verify-d3-patch" else main.body[1:], type_ignores=[])
    edges = []
    for node in ast.walk(inspected):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            target = resolve(root, current, module, node.level) if module else None
            if target:
                edges.append((target, f"import at line {node.lineno}"))
            # `from tools import helper` and package-relative imports need the
            # alias too; `from helper import function` does not resolve locally.
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                child = resolve(root, current, full, node.level)
                if child:
                    edges.append((child, f"import alias at line {node.lineno}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                target = resolve(root, current, alias.name)
                if target:
                    edges.append((target, f"import at line {node.lineno}"))
    if current in LOADER_MODULES:
        if not any(isinstance(n, ast.Attribute) and n.attr == "exec_module" for n in ast.walk(tree)):
            raise ValueError(f"reviewed fixed loader disappeared: {current}")
        for node in ast.walk(tree):
            literal = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "with_name" and len(node.args) == 1:
                literal = node.args[0]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_load" and len(node.args) == 2:
                expression = node.args[1]
                if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
                    literal = expression.right
            if isinstance(literal, ast.Constant) and isinstance(literal.value, str) and literal.value.endswith(".py"):
                target = Path(current).with_name(literal.value).as_posix()
                if not (root / target).is_file():
                    raise ValueError(f"fixed loader dependency is absent: {target}")
                edges.append((target, f"fixed loader AST at line {node.lineno}"))
    return sorted(set(edges))


def dependencies(root: Path, document: dict) -> tuple[set[str], list[dict]]:
    visited, traces = set(), []

    def visit(path: str, selector: str, chain: list[str]) -> None:
        identity = (path, selector if path == DISPATCHER else "default")
        if identity in visited:
            return
        if not (root / path).is_file():
            raise ValueError(f"named workflow tool is absent: {path}")
        visited.add(identity)
        traces.append({"path": path, "chain": chain})
        for target, reason in imports(root, path, selector):
            visit(target, "default", [*chain, f"{path}: {reason} -> {target}"])

    for path, selector in commands(document):
        visit(path, selector, [f"named Python command: {path} ({selector})"])
    return {path for path, _selector in visited}, traces


def matches(document: dict, event: str, path: str) -> bool:
    selected = document["on"][event]
    patterns = selected.get("paths") if isinstance(selected, dict) else None
    if patterns is None:
        return True
    selected = False
    for pattern in patterns:
        negative = pattern.startswith("!")
        if fnmatch.fnmatchcase(path, pattern[1:] if negative else pattern):
            selected = not negative
    return selected


def uncovered(root: Path, document: dict, event: str) -> list[str]:
    paths, _traces = dependencies(root, document)
    return sorted(path for path in paths if not matches(document, event, path))


class SourceDependencyFilterTests(unittest.TestCase):
    def test_named_python_command_import_and_fixed_loader_dependencies_trigger_both_events(self):
        for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
            document = workflow(path)
            for event in ("pull_request", "push"):
                if event in document["on"]:
                    with self.subTest(workflow=path.name, event=event):
                        self.assertEqual(uncovered(ROOT, document, event), [])

    def test_dispatcher_selects_actual_s08_and_exact_pin_branches(self):
        s08, _ = dependencies(ROOT, workflow(ROOT / ".github/workflows/s08-servo-vertical-slice.yml"))
        exact, _ = dependencies(ROOT, workflow(ROOT / ".github/workflows/servo-exact-pin.yml"))
        self.assertIn("tools/verify_d3_servo_patch.py", s08)
        self.assertNotIn("tools/_qualify_servo_exact_pin_v3_impl.py", s08)
        self.assertNotIn("tools/qualify_servo_exact_pin.py", s08)
        self.assertIn("tools/_qualify_servo_exact_pin_v3_impl.py", exact)
        self.assertIn("tools/qualify_servo_exact_pin.py", exact)
        self.assertNotIn("tools/verify_d3_servo_patch.py", exact)

    def test_removing_reader_filter_is_detected_through_real_native_consumer_imports(self):
        original = workflow(ROOT / ".github/workflows/g2-native-product-owner.yml")
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                document = copy.deepcopy(original)
                document["on"][event]["paths"].remove("tools/artifact_evidence.py")
                self.assertIn("tools/artifact_evidence.py", uncovered(ROOT, document, event))

    def test_removing_named_validator_filter_is_detected_without_changing_run(self):
        original = workflow(ROOT / ".github/workflows/approved-mechanism-policy.yml")
        self.assertIn(("tools/validate_contract_foundation.py", "default"), commands(original))
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                document = copy.deepcopy(original)
                document["on"][event]["paths"].remove("tools/validate_contract_foundation.py")
                self.assertIn("tools/validate_contract_foundation.py", uncovered(ROOT, document, event))

    def test_fixed_dynamic_loader_targets_come_from_actual_source_ast(self):
        paths, traces = dependencies(ROOT, workflow(ROOT / ".github/workflows/module-documentation.yml"))
        self.assertIn("tools/validate_module_documentation_legacy.py", paths)
        self.assertIn("tools/_validate_repository_impl.py", paths)
        self.assertIn("tools/structured_status_model.py", paths)
        self.assertTrue(any("fixed loader AST" in item for trace in traces for item in trace["chain"]))

    def test_comments_and_data_strings_are_not_named_python_commands(self):
        document = {"jobs": {"fixture": {"steps": [{"run": '# python3 tools/not_executed.py\nprint("python3 tools/not_executed.py")\npython3 tools/qualify_servo_exact_pin_v3.py verify-d3-patch --source-only\n'}]}}}
        self.assertEqual(commands(document), [(DISPATCHER, "verify-d3-patch")])

    def test_exact_dispatch_argument_and_ordered_negative_filter_are_preserved(self):
        document = {"jobs": {"fixture": {"steps": [{"run": 'python3 tools/qualify_servo_exact_pin_v3.py \\\n verify-d3-patch-other\n'}]}}}
        self.assertEqual(commands(document), [(DISPATCHER, "default")])
        document = workflow(ROOT / ".github/workflows/g2-native-product-owner.yml")
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                changed = copy.deepcopy(document)
                changed["on"][event]["paths"].append("!tools/artifact_evidence.py")
                self.assertIn("tools/artifact_evidence.py", uncovered(ROOT, changed, event))


if __name__ == "__main__":
    unittest.main()
