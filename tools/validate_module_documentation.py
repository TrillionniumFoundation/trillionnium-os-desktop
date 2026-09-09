#!/usr/bin/env python3
"""Hardened module-documentation gate layered over the reviewed v1 inventory gate."""
from __future__ import annotations

import importlib.util
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATH = Path(__file__).with_name("validate_module_documentation_legacy.py")
_spec = importlib.util.spec_from_file_location("_module_docs_v1", LEGACY_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load {LEGACY_PATH}")
LEGACY = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LEGACY)

REQUIRED_SECTIONS = LEGACY.REQUIRED_SECTIONS
REQUIRED_TITLES = tuple(item.removeprefix("## ") for item in REQUIRED_SECTIONS)
MIN_VISIBLE_BYTES = 80
MIN_WORDS = 8
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*$")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/+-]*|[\u3400-\u9fff]")
FALSE_VALUES = {"false", "${{ false }}", "0", "no", "off"}
POLICY_FIELDS = set(LEGACY.TRUE_POLICY_KEYS) | {
    "minimum_readme_bytes",
    "required_sections",
}


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON member {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant {value!r}")


def _reject_float(value: str) -> None:
    raise ValueError(f"floating-point value {value!r} is forbidden")


def _strict_registry(root: Path, errors: list[str]) -> dict[str, Any]:
    path = root / LEGACY.REGISTRY
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicates,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append("module registry must be an object")
        return {}
    if set(value) != {"schema", "plan_revision", "policy", "modules"}:
        errors.append("module registry top-level fields differ from closed schema")
    policy = value.get("policy")
    if not isinstance(policy, dict) or set(policy) != POLICY_FIELDS:
        errors.append("module registry policy fields differ from closed schema")
    return value


def _strip_comment(line: str, active: bool) -> tuple[str, bool]:
    out: list[str] = []
    cursor = 0
    while cursor < len(line):
        if active:
            end = line.find("-->", cursor)
            if end < 0:
                return "".join(out), True
            cursor = end + 3
            active = False
            continue
        start = line.find("<!--", cursor)
        if start < 0:
            out.append(line[cursor:])
            break
        out.append(line[cursor:start])
        cursor = start + 4
        active = True
    return "".join(out), active


def _visible_lines(text: str) -> list[str]:
    visible: list[str] = []
    comment = False
    fence_char: str | None = None
    fence_len = 0
    for raw in text.splitlines():
        line, comment = _strip_comment(raw, comment)
        stripped = line.lstrip()
        if fence_char is not None:
            run = len(stripped) - len(stripped.lstrip(fence_char))
            if run >= fence_len and not stripped[run:].strip():
                fence_char = None
                fence_len = 0
            continue
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            fence_char, fence_len = marker[0], len(marker)
            continue
        visible.append(line)
    return visible


def _plain(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_>#~-]", " ", text)
    return " ".join(text.split())


def _sections(text: str, label: str, errors: list[str]) -> dict[str, str]:
    lines = _visible_lines(text)
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    result: dict[str, str] = {}
    for title in REQUIRED_TITLES:
        all_matches = [item for item in headings if item[2] == title]
        correct = [item for item in all_matches if item[1] == 2]
        if len(correct) != 1:
            errors.append(
                f"{label} README must contain exactly one visible level-2 heading "
                f"'## {title}'"
            )
            continue
        if len(all_matches) != 1:
            errors.append(f"{label} README repeats required heading {title!r}")
        start = correct[0][0]
        end = len(lines)
        for index, level, _ in headings:
            if index > start and level <= 2:
                end = index
                break
        body_lines = lines[start + 1 : end]
        result[title] = "\n".join(body_lines)
        plain = _plain(body_lines)
        byte_count = len(plain.encode("utf-8"))
        word_count = len(WORD_RE.findall(plain))
        if byte_count < MIN_VISIBLE_BYTES or word_count < MIN_WORDS:
            errors.append(
                f"{label} README section {title!r} is not substantive "
                f"(visible_bytes={byte_count}, words={word_count}; require "
                f"{MIN_VISIBLE_BYTES}/{MIN_WORDS})"
            )
    return result


def _exact_command(command: str) -> bool:
    try:
        return shlex.split(command, comments=True, posix=True) == [
            "python3",
            "tools/validate_module_documentation.py",
        ]
    except ValueError:
        return False


def _make_commands(text: str, target: str) -> list[str]:
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if not line[:1].isspace() and re.match(rf"^{re.escape(target)}\s*:", line):
            start = index + 1
            break
    if start is None:
        return []
    commands: list[str] = []
    for line in lines[start:]:
        if line and not line[0].isspace():
            break
        if line.startswith("\t"):
            command = line[1:].strip().lstrip("@+-").strip()
            if command and not command.startswith("#"):
                commands.append(command)
    return commands


def _job_block(text: str, name: str) -> list[str] | None:
    lines = text.splitlines()
    pattern = re.compile(rf"^  {re.escape(name)}:\s*(?:#.*)?$")
    next_job = re.compile(r"^  [A-Za-z0-9_-]+:\s*(?:#.*)?$")
    start = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if next_job.match(lines[index]):
            end = index
            break
    return lines[start:end]


def _constant_false(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("if:"):
            value = stripped[3:].strip().strip("'\"").lower()
            if value in FALSE_VALUES:
                return True
    return False


def _job_executes(text: str, name: str) -> bool:
    block = _job_block(text, name)
    if block is None or _constant_false(block[:8]):
        return False
    for index, line in enumerate(block):
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
        if not match:
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        if inline and inline not in {"|", ">", "|-", ">-", "|+", ">+"}:
            if _exact_command(inline):
                return True
            continue
        step_start = index
        while step_start > 0:
            previous = block[step_start - 1]
            previous_indent = len(previous) - len(previous.lstrip())
            if previous.lstrip().startswith("- ") and previous_indent < indent:
                break
            step_start -= 1
        if _constant_false(block[step_start:index]):
            continue
        commands: list[str] = []
        for body in block[index + 1 :]:
            if body.strip() and len(body) - len(body.lstrip()) <= indent:
                break
            stripped = body.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
        if any(_exact_command(command) for command in commands):
            return True
    return False


def _integration(root: Path, errors: list[str]) -> None:
    try:
        makefile = (root / "Makefile").read_text(encoding="utf-8")
        if not any(_exact_command(item) for item in _make_commands(makefile, "validate")):
            errors.append("Makefile validate target does not execute the module documentation validator")
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for job in ("repository-contracts", "repository-contracts-prospective-merge"):
            if not _job_executes(ci, job):
                errors.append(f"CI job {job!r} does not execute the module documentation validator")
        dedicated = (root / ".github/workflows/module-documentation.yml").read_text(encoding="utf-8")
        for job in ("exact-head", "prospective-merge"):
            if not _job_executes(dedicated, job):
                errors.append(f"module-documentation job {job!r} does not execute the validator")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot inspect validator integration: {error}")


def _binary_symlinks(root: Path, module: str, errors: list[str]) -> None:
    base = root / module
    main = base / "src/main.rs"
    if main.is_symlink():
        errors.append(f"{module} conventional binary path is a symlink: src/main.rs")
    bin_dir = base / "src/bin"
    if bin_dir.is_symlink():
        errors.append(f"{module} conventional binary directory is a symlink: src/bin")
        return
    if not bin_dir.exists() or not bin_dir.is_dir():
        return
    for entry in bin_dir.iterdir():
        relative = entry.relative_to(base).as_posix()
        if entry.is_symlink():
            errors.append(f"{module} conventional binary entry is a symlink: {relative}")
        elif entry.is_dir() and (entry / "main.rs").is_symlink():
            nested = (entry / "main.rs").relative_to(base).as_posix()
            errors.append(f"{module} conventional binary entry is a symlink: {nested}")


def validate(root: Path = ROOT, *, integration_checks: bool = True) -> list[str]:
    errors = list(LEGACY.validate(root, integration_checks=False))
    registry = _strict_registry(root, errors)
    modules = registry.get("modules", []) if isinstance(registry, dict) else []
    if isinstance(modules, list):
        for index, entry in enumerate(modules):
            if not isinstance(entry, dict):
                continue
            module = entry.get("path")
            documentation = entry.get("documentation")
            if not isinstance(module, str) or not isinstance(documentation, str):
                continue
            _binary_symlinks(root, module, errors)
            path = root / documentation
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            label = f"module entry #{index}"
            sections = _sections(text, label, errors)
            status_body = sections.get("Status and claim ceiling", "")
            status = entry.get("status")
            claim = entry.get("claim_ceiling")
            if isinstance(status, str) and status_body.count(f"Status: `{status}`") != 1:
                errors.append(f"{label} README visible status projection is missing, repeated, or stale")
            if isinstance(claim, str) and status_body.count(f"Claim ceiling: `{claim}`") != 1:
                errors.append(f"{label} README visible claim projection is missing, repeated, or stale")
    if integration_checks:
        _integration(root, errors)
    return errors


def main() -> int:
    errors = validate()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"module documentation validation failed ({len(errors)} errors)", file=sys.stderr)
        return 1
    print("module documentation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
