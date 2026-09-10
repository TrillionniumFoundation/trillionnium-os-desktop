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
POLICY_FIELDS = set(LEGACY.TRUE_POLICY_KEYS) | {
    "minimum_readme_bytes",
    "required_sections",
}
VALIDATOR_ARGV = (
    "/usr/bin/python3",
    "-I",
    "tools/validate_module_documentation.py",
)
PINNED_CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
ALLOWED_JOB_KEYS = {"name", "if", "runs-on", "timeout-minutes", "continue-on-error", "steps"}
ALLOWED_JOB_IF = {
    "github.event_name == 'pull_request'",
    "${{ github.event_name == 'pull_request' }}",
}
ALLOWED_STEP_KEYS = {
    "name",
    "id",
    "uses",
    "with",
    "run",
    "shell",
    "if",
    "continue-on-error",
    "timeout-minutes",
    "working-directory",
    "env",
}
MAPPING_RE = re.compile(
    r"^(?P<indent> *)(?P<sequence>- )?"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]*(?P<value>.*))?$"
)


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
    required_positions: list[int] = []
    for title in REQUIRED_TITLES:
        all_matches = [item for item in headings if item[2] == title]
        correct = [item for item in all_matches if item[1] == 2]
        if len(correct) != 1:
            errors.append(
                f"{label} README must contain exactly one visible level-2 heading '## {title}'"
            )
            continue
        if len(all_matches) != 1:
            errors.append(f"{label} README repeats required heading {title!r}")
        start = correct[0][0]
        required_positions.append(start)
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
                f"(visible_bytes={byte_count}, words={word_count}; require {MIN_VISIBLE_BYTES}/{MIN_WORDS})"
            )
    if len(required_positions) == len(REQUIRED_TITLES) and required_positions != sorted(required_positions):
        errors.append(f"{label} README required sections are out of normative order")
    return result


def _exact_command(command: str) -> bool:
    try:
        return tuple(shlex.split(command, comments=True, posix=True)) == VALIDATOR_ARGV
    except ValueError:
        return False


def _make_target_executes(text: str, target: str) -> bool:
    """Require the validator to be the first failure-propagating recipe command."""
    lines = text.splitlines()
    if any("\t" in line[: len(line) - len(line.lstrip())] and not line.startswith("\t") for line in lines):
        return False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\.ONESHELL\s*:", stripped):
            return False
        if re.match(r"^\.IGNORE\s*:", stripped):
            value = stripped.split(":", 1)[1].strip()
            if not value or target in value.split():
                return False
        if re.match(r"^(?:override\s+)?(?:SHELL|\.SHELLFLAGS)\s*[:?+]?=", stripped):
            return False

    start: int | None = None
    for index, line in enumerate(lines):
        if not line[:1].isspace() and re.match(rf"^{re.escape(target)}\s*:", line):
            start = index + 1
            break
    if start is None:
        return False

    recipes: list[tuple[str, str]] = []
    for line in lines[start:]:
        if line and not line[0].isspace():
            break
        if not line.startswith("\t"):
            continue
        raw = line[1:].strip()
        if not raw or raw.startswith("#"):
            continue
        prefix = ""
        while raw[:1] in {"@", "-", "+"}:
            prefix += raw[0]
            raw = raw[1:].lstrip()
        recipes.append((prefix, raw))
    if not recipes:
        return False
    prefix, command = recipes[0]
    return set(prefix) <= {"@"} and _exact_command(command)


def _indent(line: str) -> int:
    prefix = line[: len(line) - len(line.lstrip())]
    if "\t" in prefix:
        return -1
    return len(prefix)


def _unquote_scalar(value: str) -> str | None:
    value = value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        if len(value) < 2 or value[-1] != value[0]:
            return None
        quote = value[0]
        body = value[1:-1]
        if quote == "'":
            return body.replace("''", "'")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, str) else None
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def _mapping(line: str, *, expected_indent: int, sequence: bool | None = None) -> tuple[str, str] | None:
    match = MAPPING_RE.match(line)
    if match is None or len(match.group("indent")) != expected_indent:
        return None
    has_sequence = match.group("sequence") is not None
    if sequence is not None and has_sequence != sequence:
        return None
    value = _unquote_scalar(match.group("value") or "")
    if value is None:
        return None
    return match.group("key"), value


def _job_block(text: str, name: str) -> list[str] | None:
    lines = text.splitlines()
    pattern = re.compile(rf"^  {re.escape(name)}:\s*(?:#.*)?$")
    next_job = re.compile(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*(?:#.*)?$")
    matches = [i for i, line in enumerate(lines) if pattern.match(line)]
    if len(matches) != 1:
        return None
    start = matches[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if next_job.match(lines[index]):
            end = index
            break
    return lines[start:end]


def _workflow_context_safe(text: str) -> bool:
    lines = text.splitlines()
    if any(_indent(line) < 0 for line in lines):
        return False
    jobs = [i for i, line in enumerate(lines) if line.strip() == "jobs:" and _indent(line) == 0]
    if len(jobs) != 1:
        return False
    for line in lines[: jobs[0]]:
        mapping = _mapping(line, expected_indent=0, sequence=False)
        if mapping and mapping[0] in {"defaults", "env"}:
            return False
        stripped = line.strip()
        if stripped.startswith(("<<:", "&", "*", "!")):
            return False
    return True


def _parse_job(block: list[str]) -> tuple[dict[str, str], list[tuple[dict[str, str], list[str]]]] | None:
    if not block or _indent(block[0]) != 2:
        return None
    job: dict[str, str] = {}
    steps_start: int | None = None
    steps_end = len(block)

    for index, line in enumerate(block[1:], start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = _indent(line)
        if indent < 0:
            return None
        if indent == 4:
            item = _mapping(line, expected_indent=4, sequence=False)
            if item is None:
                return None
            key, value = item
            if key in job or key not in ALLOWED_JOB_KEYS:
                return None
            job[key] = value
            if key == "steps":
                if value or steps_start is not None:
                    return None
                steps_start = index + 1
                continue
            if steps_start is not None:
                steps_end = index
                break
        elif steps_start is None and indent > 4:
            return None

    if steps_start is None or set(job) - ALLOWED_JOB_KEYS:
        return None
    if job.get("runs-on") != "ubuntu-24.04":
        return None
    condition = job.get("if")
    if condition is not None and condition not in ALLOWED_JOB_IF:
        return None
    if "continue-on-error" in job and job["continue-on-error"] != "false":
        return None

    steps: list[tuple[dict[str, str], list[str]]] = []
    current: dict[str, str] | None = None
    current_nested: list[str] = []
    for line in block[steps_start:steps_end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = _indent(line)
        if indent < 0 or indent < 6:
            return None
        if indent == 6:
            item = _mapping(line, expected_indent=6, sequence=True)
            if item is None:
                return None
            if current is not None:
                steps.append((current, current_nested))
            current = {}
            current_nested = []
            key, value = item
            if key not in ALLOWED_STEP_KEYS:
                return None
            current[key] = value
        elif indent == 8:
            if current is None:
                return None
            item = _mapping(line, expected_indent=8, sequence=False)
            if item is None:
                return None
            key, value = item
            if key in current or key not in ALLOWED_STEP_KEYS:
                return None
            current[key] = value
        else:
            if current is None:
                return None
            current_nested.append(line)
    if current is not None:
        steps.append((current, current_nested))
    return job, steps


def _checkout_step_safe(step: dict[str, str], nested: list[str]) -> bool:
    if set(step) != {"name", "uses", "with"}:
        return False
    if step["uses"] != PINNED_CHECKOUT or step["with"] != "":
        return False
    values: dict[str, str] = {}
    for line in nested:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _mapping(line, expected_indent=10, sequence=False)
        if item is None:
            return False
        key, value = item
        if key in values or key not in {"ref", "fetch-depth", "persist-credentials"}:
            return False
        values[key] = value
    return (
        bool(values.get("ref"))
        and values.get("fetch-depth") in {"1", "2", "0"}
        and values.get("persist-credentials") == "false"
    )


def _job_executes(text: str, name: str) -> bool:
    """Require one closed, failure-propagating validator step in a named job.

    The admitted job uses Ubuntu 24.04, has no workflow/job defaults or mutable
    environment, and may use only the single pull-request condition used by the
    prospective jobs. The validator must be the first command-bearing step,
    immediately after a fully pinned credential-free checkout. Its step mapping
    is closed to ``name`` plus an exact isolated absolute-Python command.
    """
    if not _workflow_context_safe(text):
        return False
    block = _job_block(text, name)
    if block is None:
        return False
    parsed = _parse_job(block)
    if parsed is None:
        return False
    job, steps = parsed
    condition = job.get("if")
    if "prospective" in name:
        if condition not in ALLOWED_JOB_IF:
            return False
    elif condition is not None:
        return False

    candidates = [
        index
        for index, (step, _nested) in enumerate(steps)
        if "run" in step and _exact_command(step["run"])
    ]
    if candidates != [1] or len(steps) < 2:
        return False
    if not _checkout_step_safe(*steps[0]):
        return False

    step, nested = steps[1]
    if nested:
        return False
    allowed_candidate_keys = {"name", "run"}
    if step.get("continue-on-error") == "false":
        allowed_candidate_keys.add("continue-on-error")
    if set(step) != allowed_candidate_keys:
        return False
    if not _exact_command(step["run"]):
        return False

    for preceding, _nested in steps[:1]:
        if "run" in preceding:
            return False
    return True


def _integration(root: Path, errors: list[str]) -> None:
    try:
        makefile = (root / "Makefile").read_text(encoding="utf-8")
        if not _make_target_executes(makefile, "validate"):
            errors.append(
                "Makefile validate target does not execute the isolated module "
                "documentation validator as its first failure-propagating recipe"
            )
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for job in ("repository-contracts", "repository-contracts-prospective-merge"):
            if not _job_executes(ci, job):
                errors.append(
                    f"CI job {job!r} does not contain the closed trusted validator execution shape"
                )
        dedicated = (root / ".github/workflows/module-documentation.yml").read_text(
            encoding="utf-8"
        )
        for job in ("exact-head", "prospective-merge"):
            if not _job_executes(dedicated, job):
                errors.append(
                    f"module-documentation job {job!r} does not contain the closed trusted validator execution shape"
                )
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
                errors.append(
                    f"{label} README visible status projection is missing, repeated, or stale"
                )
            if isinstance(claim, str) and status_body.count(f"Claim ceiling: `{claim}`") != 1:
                errors.append(
                    f"{label} README visible claim projection is missing, repeated, or stale"
                )
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
