#!/usr/bin/env python3
"""Enforce one integrated-status authority and an import-only non-status library."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_AUTHORITY_PATHS = (
    "docs/status-documents.v1.json",
    "tools/structured_status_model.py",
    "tools/structured_status.py",
    "docs/CURRENT_STATE.md",
)

REQUIRED_SUPPORT_PATHS = (
    "tools/structured_status_repository.py",
    "tools/non_status_project_truth.py",
    "tools/validate_project_truth.py",
)

RETIRED_AUTHORITY_PATHS = (
    "docs/status-facts.v1.json",
    "tools/validate_status_facts.py",
    "tests/test_status_facts.py",
    ".github/workflows/status-facts.yml",
    "tools/_validate_project_truth_base.py",
)

ACTIVE_STATUS_IMPLEMENTATIONS = {
    "structured_status_model.py",
    "structured_status.py",
    "structured_status_repository.py",
    "validate_project_truth.py",
    "validate_status_authority_singleton.py",
}

COMPETING_FUNCTIONS = {
    "status_projection_errors",
    "check_status_documents",
    "render_integrated_state",
    "validate_integrated_state",
}

COMPETING_ASSIGNMENTS = {
    "STATUS_REGISTRY_PATH",
    "STATUS_REGISTRY_SCHEMA",
    "STATUS_ROLES",
    "PENDING_MERGE_ACTION",
    "FORBIDDEN_CLOSURE_MARKERS",
}

NON_STATUS_FORBIDDEN_MARKERS = (
    "docs/status-documents.v1.json",
    "docs/CURRENT_STATE.md",
    "status_projection_errors",
    "check_status_documents",
    "render_integrated_state",
    "validate_integrated_state",
    "STATUS_REGISTRY_PATH",
    "STATUS_ROLES",
    "PENDING_MERGE_ACTION",
)

PROJECTION_MARKER = (
    "<!-- generated from docs/status-documents.v1.json; do not edit by hand -->"
)


def _assignment_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    targets: list[ast.expr] = []
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        else:
            targets.append(node.target)
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.update(item.id for item in target.elts if isinstance(item, ast.Name))
    return names


def _has_main_guard(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        left = test.left
        comparators = test.comparators
        if (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and isinstance(test.ops[0], ast.Eq)
            and len(comparators) == 1
            and isinstance(comparators[0], ast.Constant)
            and comparators[0].value == "__main__"
        ):
            return True
    return False


def _parse(path: Path, relative: str, errors: list[str]) -> tuple[str, ast.Module] | None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except (OSError, UnicodeError, SyntaxError) as error:
        errors.append(f"cannot parse {relative}: {error}")
        return None
    return source, tree


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in (*ACTIVE_AUTHORITY_PATHS, *REQUIRED_SUPPORT_PATHS):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"required status-boundary path must be a regular file: {relative}")

    for relative in RETIRED_AUTHORITY_PATHS:
        path = root / relative
        if path.exists() or path.is_symlink():
            errors.append(f"retired status authority must be absent: {relative}")

    projection = root / "docs/CURRENT_STATE.md"
    if projection.is_file() and not projection.is_symlink():
        try:
            first_line = projection.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, UnicodeError, IndexError) as error:
            errors.append(f"cannot read integrated status projection: {error}")
        else:
            if first_line != PROJECTION_MARKER:
                errors.append(
                    "docs/CURRENT_STATE.md must identify docs/status-documents.v1.json "
                    "as its sole generated authority"
                )

    tools = root / "tools"
    if tools.is_dir():
        for path in sorted(tools.glob("*.py")):
            relative = path.relative_to(root).as_posix()
            parsed = _parse(path, relative, errors)
            if parsed is None:
                continue
            _source, tree = parsed
            if path.name in ACTIVE_STATUS_IMPLEMENTATIONS:
                continue
            functions = {
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assignments: set[str] = set()
            for node in tree.body:
                assignments.update(_assignment_names(node))
            competing = sorted(
                (functions & COMPETING_FUNCTIONS)
                | (assignments & COMPETING_ASSIGNMENTS)
            )
            if competing:
                errors.append(f"{relative} defines competing status semantics: {competing}")

    non_status = root / "tools/non_status_project_truth.py"
    if non_status.is_file() and not non_status.is_symlink():
        parsed = _parse(non_status, "tools/non_status_project_truth.py", errors)
        if parsed is not None:
            source, tree = parsed
            if source.startswith("#!"):
                errors.append("non-status project-truth library must not be executable")
            if _has_main_guard(tree):
                errors.append("non-status project-truth library must not have a __main__ path")
            for marker in NON_STATUS_FORBIDDEN_MARKERS:
                if marker in source:
                    errors.append(
                        "non-status project-truth library contains integrated-status "
                        f"semantics: {marker}"
                    )

    wrapper = root / "tools/validate_project_truth.py"
    if wrapper.is_file() and not wrapper.is_symlink():
        try:
            source = wrapper.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read tools/validate_project_truth.py: {error}")
        else:
            if 'TOOLS / "non_status_project_truth.py"' not in source:
                errors.append("validate_project_truth.py must load non_status_project_truth.py")
            for marker in (
                "_validate_project_truth_base.py",
                "check_status_documents =",
                "_BASE.check_status_documents",
            ):
                if marker in source:
                    errors.append(
                        "validate_project_truth.py retains retired status delegation: "
                        f"{marker}"
                    )
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"status-authority singleton validation failed with {len(errors)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("status-authority singleton validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
