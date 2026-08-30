#!/usr/bin/env python3
"""Validate canonical project truth, gate identities, and immutable CI inputs."""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
# GitHub's workflow parser accepts a scalar after ``uses:``.  Keep the key
# detector separate from the scalar parser so malformed declarations cannot be
# silently skipped.  In particular, a line such as ``uses: action@main # ...``
# must be reported rather than treated as an ordinary non-action line.
# A workflow step may spell the mapping key either on its own indented line
# (after ``- name:``) or directly after the sequence marker (``- uses:``).
# Keep the optional marker in both expressions so every action declaration is
# checked rather than allowing the compact form to evade pin validation.
# YAML permits quoting mapping keys.  GitHub normalizes all of these spellings
# to the same ``uses`` key, so the pin audit must inspect each one.  Keep the
# key grammar deliberately narrow: only an exact quoted/unquoted key is
# recognized, avoiding accidental matches inside ordinary scalar text.
ACTION_KEY = re.compile(r"^\s*(?:-\s+)?(?:uses|'uses'|\"uses\")\s*:")
ACTION_SCALAR = re.compile(
    r"^\s*(?:-\s+)?(?:uses|'uses'|\"uses\")\s*:\s*(?P<value>.*)$"
)
# GitHub also accepts a workflow step written as a YAML flow mapping, for
# example ``- {uses: actions/checkout@<sha>}``.  Keep these expressions
# deliberately narrow: the opening ``{``/``,`` must be a flow delimiter and
# the key must be exactly the YAML ``uses`` key (including its quoted forms).
# Matches are filtered through ``_flow_syntax_state`` below so text inside
# quoted scalars or comments cannot be mistaken for an action declaration.
FLOW_ACTION_KEY = re.compile(
    r"(?P<delimiter>[{,])\s*(?:\?\s*)?(?:uses|'uses'|\"uses\")\s*:"
)
# YAML's explicit-key indicator may be placed on its own line inside a flow
# mapping (``{\n  ? uses: ...\n}``).  Keep a separate anchored form so the
# stateful scanner can reject that spelling too without matching ordinary
# question-mark-prefixed scalar text outside a flow map.
FLOW_EXPLICIT_ACTION_KEY = re.compile(
    r"^\s*\?\s*(?:uses|'uses'|\"uses\")\s*:"
)
# YAML block mappings can use an explicit key indicator outside a flow map.
# Both ? uses: value and the key-only first half of a multiline spelling
# (? uses followed by a separate : value line) are unsupported by this
# lightweight scanner, so emit a malformed candidate and fail closed.
BLOCK_EXPLICIT_ACTION_KEY = re.compile(
    r"^\s*(?:-\s+)?\?\s*(?:uses|'uses'|\"uses\")\s*(?::|\s+#|\s*$)"
)
BLOCK_EXPLICIT_KEY_MARKER = re.compile(r"^\s*(?:-\s+)?\?\s*$")
BLOCK_EXPLICIT_KEY_TOKEN = re.compile(
    r"^\s*(?:uses|'uses'|\"uses\")\s*:?\s*$"
)
ACTION_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})?"
    r"/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})?@[0-9a-f]{40}$"
)
LOCAL_ACTION = re.compile(r"^\./[A-Za-z0-9._/-]+$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
GATE_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
BRANCH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
CLAIM_CEILING = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
EVIDENCE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PLAN_REVISION = "2026-08-29-d6"
PLAN_PATH = "docs/DESKTOP_PLAN-2026-08-29-d6.md"
INTEGRATED_STAGE = "D0R_D0C06_D0A01_COMPILE_VALIDATED"
D3_ACTIVATION_TRUTH = {
    "development_live_activation_status": "BLOCKED_UPSTREAM_CROSS_UID_PROCFS",
    "development_source_wiring_only": True,
    "development_static_attestation_available": False,
    "development_static_attestation_scope": "d1_qualification_only",
    "development_service_user": "hepta-browserd",
    "development_expected_peer_user": "hepta-agent",
    "development_blocker": (
        "cross-UID /proc/<pid>/exe reads require PTRACE_MODE_READ_FSCREDS; "
        "the development service has no CAP_SYS_PTRACE"
    ),
}
D0A02_HISTORICAL_HEAD = "fe0ea6169127ce1f7950618b55374d83834a462c"
D0A02_EVIDENCE_LIFECYCLE = "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
D0A02_STALE_REASON = (
    "D0A-02 headed-host evidence is bound to historical source head "
    f"{D0A02_HISTORICAL_HEAD}; the PR #33 candidate supersedes that snapshot. "
    "Rerun servo-headed-runtime on the exact candidate head before promotion."
)
STALE_EVIDENCE_LIFECYCLE = "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
STALE_EVIDENCE_FRESHNESS = "STALE_EVIDENCE"
# ``run: |``/``run: >`` introduces an indented scalar whose contents are not
# YAML mappings.  Without tracking it, a shell/heredoc line such as
# ``uses: echo ...`` could be mistaken for an action declaration (or a real
# action declaration hidden in a script could evade review after a refactor).
BLOCK_SCALAR_START = re.compile(
    r":\s*[|>](?:(?:[1-9][+-]?)|(?:[+-][1-9]?))?(?:\s+#.*)?$"
)


def fail(message: str) -> None:
    ERRORS.append(message)


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical component of *path* is a symlink."""

    # Do not normalize through ``resolve`` before this walk: doing so would
    # erase a symlink component followed by ``..`` and make the check
    # vulnerable to the very redirect it is intended to reject.
    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in (lexical.anchor, "."):
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            # The final open below reports a missing path.  A missing suffix
            # cannot hide an existing symlink component later in the path.
            return False
        except OSError as error:
            raise OSError(f"cannot inspect project-truth path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _read_text_nofollow(path: Path) -> str:
    """Read one repository file without following links or escaping *ROOT*.

    Project-truth inputs are security-sensitive policy, not ordinary user
    documents.  Reject traversal and symlink components lexically, then use
    ``O_NOFOLLOW`` plus descriptor metadata so a final-component swap cannot
    turn a regular-file check into an arbitrary-file read.
    """

    path = Path(path)
    if any(component == ".." for component in path.parts):
        raise OSError(f"project-truth path contains '..': {path}")
    try:
        root = ROOT.resolve(strict=True)
        candidate = path if path.is_absolute() else Path.cwd() / path
        candidate = Path(os.path.abspath(os.fspath(candidate)))
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise OSError(f"project-truth path escapes repository root: {path}") from error
    if _has_symlink_component(candidate):
        raise OSError(f"project-truth path contains a symlink: {path}")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(candidate, os.O_RDONLY | nofollow | cloexec)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"project-truth path is not a regular file: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = None
            return stream.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return os.fspath(path)


def load_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    try:
        value = json.loads(_read_text_nofollow(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"invalid JSON {relative}: {error}")
        return {}
    if not isinstance(value, dict):
        fail(f"expected object in {relative}")
        return {}
    return value


def require_text(relative: str, needles: list[str]) -> str:
    path = ROOT / relative
    try:
        text = _read_text_nofollow(path)
    except (OSError, UnicodeError) as error:
        fail(f"cannot read {relative}: {error}")
        return ""
    for needle in needles:
        if needle not in text:
            fail(f"{relative} is missing canonical marker {needle!r}")
    return text


def parse_action_uses(line: str) -> str:
    """Return the canonical scalar from one ``uses:`` YAML line.

    This deliberately accepts only the subset needed by the repository's
    workflows: an unquoted scalar or a matching single/double-quoted scalar,
    optionally followed by a YAML comment.  YAML escape processing is not
    implemented here; rejecting escapes and folded values is safer than
    normalising a value that GitHub could interpret differently.
    """

    match = ACTION_SCALAR.fullmatch(line)
    if match is None:
        raise ValueError("malformed uses declaration")
    raw = match.group("value").strip()
    if not raw:
        raise ValueError("uses declaration has an empty value")

    # A quoted scalar must have one matching closing quote and no additional
    # quote/escape syntax.  This rejects mismatched wrappers which a generic
    # ``strip(\"'\")`` would accidentally turn into a valid action reference.
    if raw.startswith("'"):
        quoted = re.fullmatch(r"'([^']*)'(?:\s+#.*)?", raw)
        if quoted is None:
            raise ValueError("uses declaration has mismatched or escaped quotes")
        return quoted.group(1)
    if raw.startswith('"'):
        quoted = re.fullmatch(r'"([^"]*)"(?:\s+#.*)?', raw)
        if quoted is None:
            raise ValueError("uses declaration has mismatched or escaped quotes")
        return quoted.group(1)

    # For an unquoted scalar, ``#`` is only a comment delimiter when separated
    # from the value by whitespace.  A bare ``#`` or a second token is invalid.
    unquoted = re.fullmatch(r"(\S+)(?:\s+#.*)?", raw)
    if unquoted is None:
        raise ValueError("uses declaration has multiple tokens or malformed comment")
    return unquoted.group(1)


def validate_action_reference(value: str) -> str:
    """Validate and return one immutable remote or safe local action ref."""

    if LOCAL_ACTION.fullmatch(value):
        segments = value[2:].split("/")
        if all(segment not in {"", ".", ".."} for segment in segments):
            return value
        raise ValueError("local action path contains an empty or traversal segment")
    if ACTION_REPOSITORY.fullmatch(value):
        return value
    raise ValueError(
        "action reference must be a local ./path or owner/repository@40-hex-SHA"
    )


def workflow_action_lines(text: str) -> list[tuple[int, str]]:
    """Return candidate YAML mapping lines outside block scalar contents.

    This is intentionally not a complete YAML parser.  It only handles the
    scalar forms used by GitHub workflows and skips indented ``run: |``/``>``
    bodies so shell text cannot satisfy (or spuriously trip) the action gate.
    Any malformed scalar or unsupported YAML construct remains visible to the
    caller and is handled fail-closed by ``parse_action_uses``.
    """

    candidates: list[tuple[int, str]] = []
    scalar_parent_indent: int | None = None
    flow_stack: list[str] = []
    pending_block_explicit_key_indent: int | None = None
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if scalar_parent_indent is not None:
            # Blank lines belong to the scalar.  A non-blank line at or below
            # the introducing mapping's indentation ends it.
            if not stripped or indent > scalar_parent_indent:
                continue
            scalar_parent_indent = None
        if BLOCK_SCALAR_START.search(line) is not None:
            scalar_parent_indent = indent
            continue
        initial_flow_stack = list(flow_stack)
        candidates.append((line_number, line))
        # Flow mappings are valid YAML but do not begin with ``uses:`` and
        # would otherwise evade the immutable action-pin audit.  Add a
        # deliberately malformed canonical candidate so ``parse_action_uses``
        # rejects the unsupported construct instead of silently skipping it.
        declarations, flow_stack = flow_map_action_declarations(line, flow_stack)
        if pending_block_explicit_key_indent is not None:
            if not stripped:
                continue
            if (
                indent > pending_block_explicit_key_indent
                and not initial_flow_stack
                and BLOCK_EXPLICIT_KEY_TOKEN.fullmatch(stripped) is not None
            ):
                declarations.append("uses:")
            pending_block_explicit_key_indent = None
        if not initial_flow_stack:
            if BLOCK_EXPLICIT_ACTION_KEY.match(line) is not None:
                declarations.append("uses:")
            elif BLOCK_EXPLICIT_KEY_MARKER.match(line) is not None:
                pending_block_explicit_key_indent = indent
        for declaration in declarations:
            candidates.append((line_number, declaration))
    return candidates


def _flow_syntax_state(
    line: str, initial_stack: list[str] | None = None
) -> tuple[list[list[str]], list[bool], list[str]]:
    """Return delimiter stack and quote/comment visibility for ``line``.

    This is a small lexical helper, not a YAML parser.  It tracks enough YAML
    syntax to distinguish flow delimiters from occurrences inside quoted
    scalars and comments.  ``stack_before[i]`` is the delimiter stack before
    character ``i``; ``visible[i]`` is false for characters in a quote/comment.
    """

    stack: list[str] = list(initial_stack or [])
    stack_before: list[list[str]] = []
    visible: list[bool] = []
    quote: str | None = None
    escaped = False
    comment = False
    for index, character in enumerate(line):
        stack_before.append(stack.copy())
        if comment:
            visible.append(False)
            continue
        if quote is not None:
            visible.append(False)
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and character == "\\":
                escaped = True
            elif quote == "'" and character == "'":
                # YAML single quotes escape a quote by doubling it.  Leave the
                # second quote inside the scalar as quoted as well.
                next_character = line[index + 1] if index + 1 < len(line) else ""
                if next_character == "'":
                    continue
                quote = None
            elif character == quote:
                quote = None
            continue

        # A quote starts a YAML quoted scalar only at a token boundary.  An
        # apostrophe embedded in a plain scalar (for example ``don't``) must
        # remain visible, otherwise a later ``uses`` key could be skipped.
        quote_boundary = (
            index == 0
            or line[index - 1].isspace()
            or line[index - 1] in "{[,?:"
        )
        if character in ("'", '"') and quote_boundary:
            quote = character
            escaped = False
            visible.append(False)
            continue
        if character == "#" and (index == 0 or line[index - 1].isspace()):
            comment = True
            visible.append(False)
            continue

        visible.append(True)
        if character in "[{":
            stack.append(character)
        elif character == "]" and stack and stack[-1] == "[":
            stack.pop()
        elif character == "}" and stack and stack[-1] == "{":
            stack.pop()
    return stack_before, visible, stack


def flow_map_action_declarations(
    line: str, initial_stack: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """Return fail-closed candidates for inline flow-map ``uses`` keys.

    Flow mappings are intentionally unsupported by this lightweight audit.
    Returning an empty ``uses:`` declaration makes ``parse_action_uses`` fail
    closed, while still preserving the line number and avoiding a second YAML
    parser.  Callers can rewrite the step as a normal block mapping.  The
    lexical filter ensures comments and quoted scalar text are not rejected.
    """

    stack_before, visible, final_stack = _flow_syntax_state(line, initial_stack)
    declarations: list[str] = []
    for match in FLOW_ACTION_KEY.finditer(line):
        delimiter_index = match.start("delimiter")
        if delimiter_index >= len(visible) or not visible[delimiter_index]:
            continue
        # A comma is a flow entry delimiter only while inside a mapping.  An
        # opening brace always starts the candidate map itself.
        delimiter = match.group("delimiter")
        context = stack_before[delimiter_index]
        if delimiter == "," and (not context or context[-1] != "{"):
            continue
        declarations.append("uses:")
    # An explicit flow-map key can begin a physical line after the opening
    # brace.  Only treat it as an action when the carried delimiter state says
    # we are currently inside a mapping; otherwise ``? uses:`` is just an
    # ordinary (possibly invalid) YAML scalar and should not create a false
    # action finding.
    explicit = FLOW_EXPLICIT_ACTION_KEY.match(line)
    if explicit is not None:
        index = explicit.start()
        context = stack_before[index] if index < len(stack_before) else final_stack
        if context and context[-1] == "{":
            declarations.append("uses:")
    return declarations, final_stack


def candidate_validation_errors(
    candidate: object,
    *,
    gate_ids: set[str],
    status_vocabulary: set[str],
    gate_status_by_id: dict[str, Any],
    completed: set[str],
) -> list[str]:
    """Return fail-closed shape/provenance errors for one source candidate."""

    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["project-state contains a non-object source candidate"]

    required = {
        "id",
        "branch",
        "pr",
        "status",
        "base_sha",
        "candidate_head_sha",
        "claim_ceiling",
    }
    optional = {"evidence_artifact_digest", "evidence_artifact_id", "evidence_run_id"}
    missing = sorted(required - set(candidate))
    unknown = sorted(set(candidate) - required - optional)
    if missing:
        errors.append(f"candidate is missing required fields: {missing}")
    if unknown:
        errors.append(f"candidate has unknown fields: {unknown}")

    package = candidate.get("id")
    if not isinstance(package, str) or GATE_ID.fullmatch(package) is None:
        errors.append(f"candidate id is not a canonical gate id: {package!r}")
    else:
        if package not in gate_ids:
            errors.append(f"candidate package {package!r} is absent from gate registry")
        if package in completed:
            errors.append(f"candidate package {package} is also listed as integrated complete")

    branch = candidate.get("branch")
    if (
        not isinstance(branch, str)
        or BRANCH_NAME.fullmatch(branch) is None
        or ".." in branch
        or "//" in branch
        or branch.endswith(("/", "."))
        or any(segment.startswith(".") for segment in branch.split("/"))
    ):
        errors.append(f"candidate branch is unsafe or malformed: {branch!r}")

    pr = candidate.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or not 1 <= pr <= 2_000_000_000:
        errors.append(f"candidate PR number is invalid: {pr!r}")

    status = candidate.get("status")
    if not isinstance(status, str) or status not in status_vocabulary:
        errors.append(f"candidate package {package!r} has unknown status {status!r}")
    elif isinstance(package, str) and gate_status_by_id.get(package) != status:
        errors.append(f"candidate package {package!r} status disagrees with gate registry")

    for field in ("base_sha", "candidate_head_sha"):
        value = candidate.get(field)
        if (
            not isinstance(value, str)
            or SHA40.fullmatch(value) is None
            or set(value) == {"0"}
        ):
            errors.append(f"candidate {field} is not a lowercase 40-hex SHA: {value!r}")

    claim = candidate.get("claim_ceiling")
    if not isinstance(claim, str) or CLAIM_CEILING.fullmatch(claim) is None:
        errors.append(f"candidate claim_ceiling is malformed: {claim!r}")

    evidence_fields = {
        "evidence_artifact_digest",
        "evidence_artifact_id",
        "evidence_run_id",
    }
    present = evidence_fields & set(candidate)
    if present and present != evidence_fields:
        errors.append(
            "candidate evidence identity must include digest, artifact id, and run id together"
        )
    if "evidence_artifact_digest" in candidate and (
        not isinstance(candidate.get("evidence_artifact_digest"), str)
        or EVIDENCE_DIGEST.fullmatch(candidate["evidence_artifact_digest"]) is None
        or candidate["evidence_artifact_digest"] == "sha256:" + "0" * 64
    ):
        errors.append("candidate evidence_artifact_digest is not sha256:<64 lowercase hex>")
    for field in ("evidence_artifact_id", "evidence_run_id"):
        if field in candidate:
            value = candidate[field]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"candidate {field} must be a positive integer")
    return errors


def duplicate_candidate_ids(candidates: list[object]) -> list[str]:
    """Return sorted candidate IDs that occur more than once."""

    seen: set[str] = set()
    duplicates: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        package = candidate.get("id")
        if not isinstance(package, str):
            continue
        if package in seen:
            duplicates.add(package)
        seen.add(package)
    return sorted(duplicates)


def gate_contract_dependency_errors(
    contract: object, *, gate_ids: set[str], label: str
) -> list[str]:
    """Return shape/provenance errors for a gate contract dependency list.

    Gate contracts use canonical registry IDs for dependencies.  Keeping this
    check in the project-truth validator prevents a stale contract from
    referring to an unregistered/retired work package while still allowing
    the registry to remain the single source of gate identity.
    """

    errors: list[str] = []
    if not isinstance(contract, dict):
        return [f"{label} must be an object"]
    dependencies = contract.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        return [f"{label}.dependencies must be a non-empty list"]
    seen: set[str] = set()
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, str) or GATE_ID.fullmatch(dependency) is None:
            errors.append(
                f"{label}.dependencies[{index}] is not a canonical gate id: "
                f"{dependency!r}"
            )
            continue
        if dependency in seen:
            errors.append(f"{label}.dependencies contains duplicate id {dependency!r}")
        seen.add(dependency)
        if dependency not in gate_ids:
            errors.append(
                f"{label}.dependencies references unregistered gate {dependency!r}"
            )
    return errors


def _safe_invalidation_glob_parts(value: object, *, label: str) -> tuple[str, ...]:
    """Return path segments for one safe, repository-relative glob.

    Gate invalidation paths are data consumed by CI and must not be treated as
    Git pathspecs with magic, rooted paths, or platform-specific separators.
    ``**`` is supported only as a complete segment; matching is performed
    segment-by-segment below so ``*`` cannot silently cross a directory.
    """

    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty glob")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"{label} contains a control character")
    if "\\" in value:
        raise ValueError(f"{label} contains a backslash separator")
    if value.startswith(("/", ":", "!")):
        raise ValueError(f"{label} must be a relative non-magic glob")
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise ValueError(f"{label} must not use a drive-qualified path")
    parts = tuple(value.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} contains an unsafe path component")
    if any("**" in part and part != "**" for part in parts):
        raise ValueError(f"{label} uses ** outside a complete path segment")
    return parts


def _invalidation_glob_matches(path: str, pattern: str) -> bool:
    """Match one safe repository-relative path against one safe glob."""

    path_parts = _safe_invalidation_glob_parts(path, label="path")
    pattern_parts = _safe_invalidation_glob_parts(pattern, label="glob")

    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatchcase(path_parts[path_index], pattern_part)
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def invalidation_coverage_errors(
    gates: object, *, root: Path = ROOT
) -> list[str]:
    """Return errors when machine workflows/manifests lack gate coverage.

    The check deliberately covers the two mutable machine-truth surfaces that
    every gate review must notice: immediate ``.github/workflows`` YAML files
    and immediate ``manifests/*.json`` files.  Human README files are not
    targets of this generic check; gates may still list them explicitly.
    """

    errors: list[str] = []
    if not isinstance(gates, dict):
        return ["gate registry must be an object for invalidation coverage"]
    gate_entries = gates.get("gates")
    if not isinstance(gate_entries, list):
        return ["gate registry gates must be a list for invalidation coverage"]

    compiled: list[tuple[str, tuple[str, ...]]] = []
    for index, gate in enumerate(gate_entries):
        if not isinstance(gate, dict):
            errors.append(f"gate registry entry {index} is not an object")
            continue
        gate_id = gate.get("id")
        label = f"gate {gate_id!r} invalidation_paths"
        paths = gate.get("invalidation_paths")
        if not isinstance(gate_id, str) or GATE_ID.fullmatch(gate_id) is None:
            errors.append(f"gate registry entry {index} has an invalid id")
            continue
        if not isinstance(paths, list) or not paths:
            errors.append(f"{label} must be a non-empty list")
            continue
        for path_index, pattern in enumerate(paths):
            try:
                parts = _safe_invalidation_glob_parts(
                    pattern,
                    label=f"{label}[{path_index}]",
                )
            except ValueError as error:
                errors.append(str(error))
                continue
            compiled.append((gate_id, parts))

    targets: list[str] = []
    for directory, suffixes in (
        (root / ".github/workflows", {".yml", ".yaml"}),
        (root / "manifests", {".json"}),
    ):
        try:
            unsafe_directory = _has_symlink_component(directory) or directory.is_symlink()
        except OSError as error:
            errors.append(f"cannot inspect invalidation coverage directory {directory}: {error}")
            continue
        if unsafe_directory:
            errors.append(f"invalidation coverage directory contains a symlink: {directory}")
            continue
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            errors.append(f"cannot enumerate invalidation coverage directory {directory}: {error}")
            continue
        for path in entries:
            if path.is_symlink():
                errors.append(f"invalidation coverage target is a symlink: {path}")
                continue
            if path.suffix.lower() not in suffixes:
                continue
            if not path.is_file():
                errors.append(f"invalidation coverage target is not a regular file: {path}")
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                errors.append(f"invalidation coverage target escapes repository: {path}")
                continue
            targets.append(relative)

    for target in sorted(targets):
        if not any(
            _invalidation_glob_matches(target, "/".join(pattern_parts))
            for _gate_id, pattern_parts in compiled
        ):
            errors.append(
                f"machine input {target!r} is not covered by any gate invalidation glob"
            )
    return errors


def stale_metadata_errors(
    gates: object,
    docs: object,
    repository: object,
    *,
    root: Path = ROOT,
) -> list[str]:
    """Return errors for stale-evidence lifecycle and cross-record drift.

    d6 deliberately separates a bounded capability ``status`` from evidence
    freshness.  Once a gate is marked ``STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN``
    every machine projection must carry the same stale fields, while retaining
    its capability status.  This check keeps copied PASS snapshots from being
    mistaken for promotion evidence and catches a row/evidence reason drift.
    """

    errors: list[str] = []
    if not isinstance(gates, dict):
        return ["gate registry must be an object for stale metadata checks"]
    gate_entries = gates.get("gates")
    if not isinstance(gate_entries, list):
        return ["gate registry gates must be a list for stale metadata checks"]

    gate_by_id: dict[str, dict[str, Any]] = {}
    stale_gate_ids: set[str] = set()
    for index, gate in enumerate(gate_entries):
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("id")
        if not isinstance(gate_id, str):
            continue
        gate_by_id[gate_id] = gate
        lifecycle = gate.get("evidence_lifecycle")
        if lifecycle != STALE_EVIDENCE_LIFECYCLE:
            # A partial stale marker is ambiguous and therefore fail-closed.
            if gate.get("evidence_freshness") == STALE_EVIDENCE_FRESHNESS:
                errors.append(
                    f"gate {gate_id} has stale freshness without the exact-head rerun lifecycle"
                )
            continue
        stale_gate_ids.add(gate_id)
        label = f"gate {gate_id}"
        if gate.get("evidence_freshness") != STALE_EVIDENCE_FRESHNESS:
            errors.append(f"{label} stale lifecycle requires STALE_EVIDENCE freshness")
        if gate.get("merge_ready") is not False:
            errors.append(f"{label} stale lifecycle requires merge_ready=false")
        reason = gate.get("stale_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{label} stale lifecycle requires a non-empty stale_reason")
        if gate.get("status") == STALE_EVIDENCE_FRESHNESS:
            errors.append(
                f"{label} must retain its capability status instead of STALE_EVIDENCE"
            )

    def row_gate_id(value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        return value[4:] if value.startswith("TOS-") else value

    row_seen: set[str] = set()
    row_collections: list[tuple[str, object]] = []
    if isinstance(docs, dict):
        row_collections.append(
            ("docs manifest implementation_checkpoints", docs.get("implementation_checkpoints"))
        )
    if isinstance(repository, dict):
        row_collections.extend(
            [
                ("repository host_validated_work_packages", repository.get("host_validated_work_packages")),
                ("repository qualification_work_packages", repository.get("qualification_work_packages")),
            ]
        )

    for collection_label, collection in row_collections:
        if not isinstance(collection, list):
            continue
        for index, row in enumerate(collection):
            if not isinstance(row, dict):
                continue
            lifecycle = row.get("evidence_lifecycle")
            if lifecycle != STALE_EVIDENCE_LIFECYCLE:
                if row.get("evidence_freshness") == STALE_EVIDENCE_FRESHNESS:
                    errors.append(
                        f"{collection_label}[{index}] has stale freshness without the exact-head rerun lifecycle"
                    )
                continue
            gate_id = row_gate_id(row.get("id"))
            label = f"{collection_label}[{index}] ({row.get('id')!r})"
            if gate_id is None or gate_id not in stale_gate_ids:
                errors.append(f"{label} stale lifecycle has no matching stale gate")
                continue
            row_seen.add(gate_id)
            gate = gate_by_id[gate_id]
            if row.get("evidence_freshness") != STALE_EVIDENCE_FRESHNESS:
                errors.append(f"{label} stale lifecycle requires STALE_EVIDENCE freshness")
            if row.get("merge_ready") is not False:
                errors.append(f"{label} stale lifecycle requires merge_ready=false")
            if row.get("status") == STALE_EVIDENCE_FRESHNESS:
                errors.append(f"{label} must retain its capability status")
            if row.get("stale_reason") != gate.get("stale_reason"):
                errors.append(f"{label} stale_reason disagrees with gate {gate_id}")

            reference = row.get("machine_evidence") or row.get("evidence")
            if not isinstance(reference, str):
                continue
            if reference.startswith("evidence/"):
                relative = f"docs/{reference}"
            elif reference.startswith("docs/evidence/"):
                relative = reference
            else:
                continue
            if not relative.startswith("docs/evidence/generated/") or ".." in Path(relative).parts:
                continue
            path = root / relative
            try:
                generated_value = json.loads(_read_text_nofollow(path))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                errors.append(f"{label} generated evidence is unreadable: {error}")
                continue
            if not isinstance(generated_value, dict):
                errors.append(f"{label} generated evidence must be an object")
                continue
            generated_label = f"{label} -> {relative}"
            if generated_value.get("evidence_lifecycle") != STALE_EVIDENCE_LIFECYCLE:
                errors.append(f"{generated_label} lacks the exact-head rerun lifecycle")
            if generated_value.get("evidence_freshness") != STALE_EVIDENCE_FRESHNESS:
                errors.append(f"{generated_label} freshness is not STALE_EVIDENCE")
            if generated_value.get("merge_ready") is not False:
                errors.append(f"{generated_label} merge_ready must be false")
            if generated_value.get("stale_reason") != gate.get("stale_reason"):
                errors.append(f"{generated_label} stale_reason disagrees with gate {gate_id}")
            if generated_value.get("status") == STALE_EVIDENCE_FRESHNESS:
                errors.append(f"{generated_label} must retain its capability status")

    for gate_id in sorted(stale_gate_ids - row_seen):
        errors.append(f"stale gate {gate_id} has no stale docs/repository projection")

    # Contract snapshots are another machine projection.  Their nested
    # validation/host_validation object must carry the same freshness without
    # replacing the top-level capability status.
    contract_paths = {
        "D0C-02": "contracts/agent-transport.v1.json",
        "D0C-03": "contracts/browser-codec.v1.json",
        "D0C-04": "contracts/agent-port-bridge.v1.json",
        "D0C-05": "contracts/agent-port-custody.v1.json",
        "D0C-04-candidate": "manifests/d0c04-candidate.json",
    }
    for label_id, relative in contract_paths.items():
        try:
            value = json.loads(_read_text_nofollow(root / relative))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"{relative} stale metadata input is unreadable: {error}")
            continue
        if not isinstance(value, dict) or value.get("evidence_lifecycle") != STALE_EVIDENCE_LIFECYCLE:
            continue
        label = f"{relative} ({label_id})"
        gate_id = label_id.removesuffix("-candidate")
        gate = gate_by_id.get(gate_id)
        if value.get("evidence_freshness") != STALE_EVIDENCE_FRESHNESS:
            errors.append(f"{label} freshness is not STALE_EVIDENCE")
        if value.get("merge_ready") is not False:
            errors.append(f"{label} merge_ready must be false")
        if value.get("status") == STALE_EVIDENCE_FRESHNESS:
            errors.append(f"{label} must retain its capability status")
        if gate is not None and value.get("stale_reason") != gate.get("stale_reason"):
            errors.append(f"{label} stale_reason disagrees with gate {gate_id}")
        nested = value.get("validation") or value.get("host_validation")
        if not isinstance(nested, dict):
            errors.append(f"{label} lacks nested validation freshness")
            continue
        if nested.get("evidence_freshness") != STALE_EVIDENCE_FRESHNESS:
            errors.append(f"{label} nested freshness is not STALE_EVIDENCE")
        if nested.get("merge_ready") is not False:
            errors.append(f"{label} nested merge_ready must be false")
        if value.get("stale_reason") != nested.get("stale_reason"):
            errors.append(f"{label} top-level and nested stale_reason disagree")

    return errors


def _check_d0a02_stale_record(record: object, label: str) -> None:
    """Require an old D0A-02 artifact to advertise its stale lifecycle.

    The headed-host run is retained as provenance for PR #33, but its source
    head predates the active candidate.  Keeping this check in the canonical
    truth validator prevents a copied PASS result from being mistaken for
    current merge evidence.
    """

    if not isinstance(record, dict):
        fail(f"{label} must be an object")
        return
    if record.get("evidence_lifecycle") != D0A02_EVIDENCE_LIFECYCLE:
        fail(
            f"{label}.evidence_lifecycle must be "
            f"{D0A02_EVIDENCE_LIFECYCLE!r}"
        )
    reason = record.get("stale_reason")
    if reason != D0A02_STALE_REASON:
        fail(f"{label}.stale_reason must equal the canonical PR #33 exact-head rerun reason")
    promotion = record.get("promotion")
    if not isinstance(promotion, dict):
        fail(f"{label}.promotion must be an object with stale merge state")
        return
    if promotion.get("evidence_freshness") != "STALE_EVIDENCE":
        fail(f"{label}.promotion.evidence_freshness must be 'STALE_EVIDENCE'")
    if promotion.get("merge_ready") is not False:
        fail(f"{label}.promotion.merge_ready must be false for stale evidence")
    if promotion.get("superseded_by_pr") != 33:
        fail(f"{label}.promotion.superseded_by_pr must be PR #33")
    promotion_reason = promotion.get("stale_reason")
    if promotion_reason != D0A02_STALE_REASON:
        fail(f"{label}.promotion.stale_reason must equal the canonical exact-head rerun reason")


def check_d0a02_evidence_lifecycle(
    project: dict[str, Any], docs: dict[str, Any], repository: dict[str, Any]
) -> None:
    """Synchronize the historical D0A-02 artifact and active PR #33 claim.

    The old headed-host artifact remains useful, but only as stale provenance;
    the active candidate's module-closed claim is deliberately left intact.
    """

    for relative in (
        "docs/evidence/generated/d0a02-headed-runtime-evidence.json",
        "docs/evidence/generated/d0a02-headed-runtime-result.json",
    ):
        _check_d0a02_stale_record(load_json(relative), relative)

    repository_entries = repository.get("qualification_work_packages")
    if not isinstance(repository_entries, list):
        fail("repository-state qualification_work_packages must be a list")
    else:
        matches = [
            entry
            for entry in repository_entries
            if isinstance(entry, dict) and entry.get("id") == "D0A-02"
        ]
        if len(matches) != 1:
            fail("repository-state must contain exactly one D0A-02 qualification evidence entry")
        else:
            entry = matches[0]
            if entry.get("evidence_lifecycle") != D0A02_EVIDENCE_LIFECYCLE:
                fail("repository-state D0A-02 evidence lifecycle is not stale")
            if entry.get("merge_ready") is not False:
                fail("repository-state D0A-02 evidence must not be merge-ready")
            if entry.get("superseded_by_pr") != 33:
                fail("repository-state D0A-02 evidence must retain PR #33 supersession")
            reason = entry.get("stale_reason")
            if reason != D0A02_STALE_REASON:
                fail("repository-state D0A-02 entry lacks the canonical exact-head rerun reason")

    checkpoint_entries = docs.get("implementation_checkpoints")
    if not isinstance(checkpoint_entries, list):
        fail("docs manifest implementation_checkpoints must be a list")
    else:
        matches = [
            entry
            for entry in checkpoint_entries
            if isinstance(entry, dict) and entry.get("id") == "TOS-D0A-02"
        ]
        if len(matches) != 1:
            fail("docs manifest must contain exactly one TOS-D0A-02 checkpoint")
        else:
            entry = matches[0]
            if entry.get("evidence_lifecycle") != D0A02_EVIDENCE_LIFECYCLE:
                fail("docs manifest D0A-02 evidence lifecycle is not stale")
            if entry.get("merge_ready") is not False:
                fail("docs manifest D0A-02 evidence must not be merge-ready")
            if entry.get("superseded_by_pr") != 33:
                fail("docs manifest D0A-02 evidence must retain PR #33 supersession")
            reason = entry.get("stale_reason")
            if reason != D0A02_STALE_REASON:
                fail("docs manifest D0A-02 entry lacks the canonical exact-head rerun reason")

    # The active PR #33 source candidate is a separate claim record.  Keep its
    # module-closed claim ceiling while the old artifact is marked stale.
    candidates = project.get("source_candidate_work_packages")
    active = [
        entry
        for entry in candidates
        if isinstance(entry, dict) and entry.get("id") == "D0A-02"
    ] if isinstance(candidates, list) else []
    if len(active) != 1:
        fail("project-state must contain exactly one active D0A-02 source candidate")
    else:
        candidate = active[0]
        if candidate.get("status") != "MODULE_CLOSED_CANDIDATE":
            fail("active PR #33 D0A-02 candidate must retain MODULE_CLOSED_CANDIDATE status")
        claim = candidate.get("claim_ceiling")
        if not isinstance(claim, str) or not claim.startswith("headed_host_local_fixture_only"):
            fail("active D0A-02 candidate claim ceiling must remain headed-host/local-fixture-only")


def check_truth_alignment() -> None:
    project = load_json("manifests/project-state.v1.json")
    gates = load_json("manifests/gates.v1.json")
    docs = load_json("docs/MANIFEST.json")
    repository = load_json("manifests/repository-state.json")

    expected = {
        "active_plan": PLAN_PATH,
        "active_plan_revision": PLAN_REVISION,
        "integrated_implementation_stage": INTEGRATED_STAGE,
    }
    for key, value in expected.items():
        if project.get(key) != value:
            fail(f"project-state {key} must be {value!r}")

    # Keep the D3 live-activation blocker machine-readable and synchronized
    # across the normative project, repository, and rendered-doc snapshots.
    # A copied status that drifts from project-state must never look like a
    # live activation claim.
    for key, value in D3_ACTIVATION_TRUTH.items():
        if project.get(key) != value:
            fail(f"project-state {key} must be {value!r}")
        if repository.get(key) != value:
            fail(f"repository-state {key} must be {value!r}")
        if docs.get(key) != value:
            fail(f"docs manifest {key} must be {value!r}")

    check_d0a02_evidence_lifecycle(project, docs, repository)

    if docs.get("active_plan") != Path(PLAN_PATH).name:
        fail("docs manifest active_plan disagrees with project-state")
    if docs.get("active_plan_revision") != PLAN_REVISION:
        fail("docs manifest revision disagrees with project-state")
    if docs.get("implementation_stage") != INTEGRATED_STAGE:
        fail("docs manifest implementation_stage disagrees with project-state")
    if docs.get("project_state") != "../manifests/project-state.v1.json":
        fail("docs manifest does not point to project-state")
    if docs.get("gate_registry") != "../manifests/gates.v1.json":
        fail("docs manifest does not point to gate registry")

    if repository.get("active_plan") != PLAN_PATH:
        fail("repository-state active_plan disagrees with project-state")
    if repository.get("active_plan_revision") != PLAN_REVISION:
        fail("repository-state revision disagrees with project-state")
    if repository.get("implementation_stage") != INTEGRATED_STAGE:
        fail("repository-state implementation_stage disagrees with project-state")
    if repository.get("project_state") != "manifests/project-state.v1.json":
        fail("repository-state does not point to project-state")
    if repository.get("gate_registry") != "manifests/gates.v1.json":
        fail("repository-state does not point to gate registry")

    completed = project.get("integrated_completed_work_packages")
    if not isinstance(completed, list) or any(not isinstance(item, str) for item in completed):
        fail("project-state completed package set is invalid")
        completed = []
    if len(completed) != len(set(completed)):
        fail("project-state completed package set has duplicates")
    if set(repository.get("completed_work_packages", [])) != set(completed):
        fail("repository-state completed package set disagrees with project-state")

    if gates.get("plan_revision") != PLAN_REVISION:
        fail("gate registry revision disagrees with project-state")
    vocabulary = set(gates.get("status_vocabulary", []))
    gate_list = gates.get("gates", [])
    if not isinstance(gate_list, list):
        fail("gate registry gates is not a list")
        gate_list = []
    gate_ids: list[str] = []
    for entry in gate_list:
        if not isinstance(entry, dict):
            fail("gate registry contains a non-object gate")
            continue
        gate_id = entry.get("id")
        status = entry.get("status")
        if not isinstance(gate_id, str):
            fail("gate registry entry has no string id")
            continue
        gate_ids.append(gate_id)
        if status not in vocabulary:
            fail(f"gate {gate_id} has unknown status {status!r}")
        for key in (
            "evidence_tier",
            "prerequisites",
            "invalidation_paths",
            "claim_ceiling",
            "review_class",
        ):
            if key not in entry:
                fail(f"gate {gate_id} is missing {key}")
    if len(gate_ids) != len(set(gate_ids)):
        fail("gate registry contains duplicate ids")

    gate_id_set = set(gate_ids)
    for error in invalidation_coverage_errors(gates, root=ROOT):
        fail(error)
    for error in stale_metadata_errors(gates, docs, repository, root=ROOT):
        fail(error)

    for package in completed:
        if package not in gate_id_set:
            fail(f"completed package {package} is absent from gate registry")
    gate_status_by_id = {
        entry["id"]: entry.get("status")
        for entry in gate_list
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    d2i_contract = load_json("contracts/d2i-integrated-image.v1.json")
    for error in gate_contract_dependency_errors(
        d2i_contract,
        gate_ids=gate_id_set,
        label="contracts/d2i-integrated-image.v1.json",
    ):
        fail(error)

    for package in completed:
        if gate_status_by_id.get(package) != "INTEGRATED_AND_EXACT_MAIN_VALIDATED":
            fail(f"completed package {package} is not integrated-and-main-validated in gate registry")

    candidates = project.get("source_candidate_work_packages", [])
    if not isinstance(candidates, list):
        fail("project-state source candidates is not a list")
        candidates = []
    for duplicate in duplicate_candidate_ids(candidates):
        fail(f"project-state source candidates contain duplicate id {duplicate!r}")
    candidate_view: list[dict[str, Any]] = []
    for candidate in candidates:
        for error in candidate_validation_errors(
            candidate,
            gate_ids=gate_id_set,
            status_vocabulary=vocabulary,
            gate_status_by_id=gate_status_by_id,
            completed=set(completed),
        ):
            fail(error)
        if not isinstance(candidate, dict):
            continue
        package = candidate.get("id")
        status = candidate.get("status")
        candidate_view.append(
            {
                "id": package,
                "branch": candidate.get("branch"),
                "pr": candidate.get("pr"),
                "status": status,
            }
        )

    repository_candidates = repository.get("source_candidate_work_packages", [])
    if repository_candidates != candidates:
        fail("repository-state source candidates disagree with project-state")
    docs_candidates = docs.get("active_candidates", [])
    if docs_candidates != candidate_view:
        fail("docs manifest active candidates disagree with project-state")

    required_nonclaims = {
        "headed_servo_integrated",
        "debian_image_built",
        "qemu_pid1_wayland_boot",
        "browser_actor_dispatch",
        "external_navigation_or_effects",
        "production_release",
    }
    nonclaims = set(project.get("not_claimed", []))
    missing = sorted(required_nonclaims - nonclaims)
    if missing:
        fail(f"project-state is missing required non-claims: {missing}")
    if set(repository.get("not_claimed", [])) != nonclaims:
        fail("repository-state non-claims disagree with project-state")

    policy = project.get("evidence_binding_policy", {})
    if not isinstance(policy, dict) or not policy or any(value is not True for value in policy.values()):
        fail("project-state evidence binding policy is not fully fail-closed")

    require_text(PLAN_PATH, [PLAN_REVISION, INTEGRATED_STAGE, "D1", "D0A-02", "D9"])
    require_text("docs/DESKTOP_PLAN.md", [Path(PLAN_PATH).name, PLAN_REVISION, INTEGRATED_STAGE])
    require_text("docs/CURRENT_STATE.md", [PLAN_REVISION, INTEGRATED_STAGE, "PR #23", "PR #27"])
    require_text("README.md", [PLAN_REVISION, INTEGRATED_STAGE, "project-state.v1.json"])
    require_text("apps/hepta-browserd/src/lib.rs", [PLAN_REVISION, INTEGRATED_STAGE])


def check_upstream_boundary() -> None:
    boundary = load_json("manifests/product-boundary.json")
    review = load_json("manifests/upstream-reference-review.v1.json")
    mobile = boundary.get("mobile_reference", {})
    if not isinstance(mobile, dict):
        fail("product boundary mobile_reference is invalid")
        return
    if mobile.get("repository") != "TrillionniumFoundation/trillionnium-os":
        fail("product boundary points to the wrong sibling repository")
    if mobile.get("commit") != review.get("reviewed_company_main_sha"):
        fail("product boundary sibling commit disagrees with upstream review")
    if mobile.get("relationship") != "company_sibling_reference_not_build_dependency":
        fail("product boundary weakens the sibling/build boundary")
    if review.get("mobile_authority_imported") is not False:
        fail("upstream review imports mobile authority")
    rejected = set(review.get("explicitly_rejected_default_authorities", []))
    for authority in ("adb", "root_linux", "direct_shell", "owner_open_root_execution"):
        if authority not in rejected:
            fail(f"upstream review does not reject {authority}")


def check_workflow_action_pins() -> None:
    pins = load_json("manifests/ci-action-pins.v1.json").get("actions", {})
    if not isinstance(pins, dict):
        fail("CI action pin manifest is invalid")
        pins = {}
    for name, sha in pins.items():
        if (
            not isinstance(name, str)
            or not isinstance(sha, str)
            or ACTION_REPOSITORY.fullmatch(f"{name}@{sha}") is None
        ):
            fail(f"CI action pin manifest contains invalid binding {name!r}: {sha!r}")
    workflow_root = ROOT / ".github/workflows"
    if workflow_root.is_symlink() or not workflow_root.is_dir():
        fail("GitHub workflow directory is missing or symlinked")
        return
    # Walk the complete workflow tree.  A one-level ``glob`` silently omits
    # nested YAML files, allowing a newly added workflow to escape the pin
    # audit (the stricter governance validator also enforces the exact
    # inventory).  Keep symlinks visible so the no-follow reader below can
    # reject them instead of skipping an authority input.
    workflows: list[Path] = []
    for current, directory_names, file_names in os.walk(
        workflow_root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        for name in directory_names:
            path = current_path / name
            if path.is_symlink():
                fail(f"{_display_path(path)} workflow directory is symlinked")
        for name in file_names:
            path = current_path / name
            if path.suffix.lower() in {".yml", ".yaml"}:
                workflows.append(path)
    workflows.sort()
    if not workflows:
        fail("no GitHub workflows found")
        return
    for path in workflows:
        try:
            workflow_text = _read_text_nofollow(path)
        except (OSError, UnicodeError) as error:
            fail(f"{_display_path(path)} cannot be read safely: {error}")
            continue
        for line_number, line in workflow_action_lines(workflow_text):
            if ACTION_KEY.match(line) is None:
                continue
            try:
                action = validate_action_reference(parse_action_uses(line))
            except ValueError as error:
                fail(
                    f"{path.relative_to(ROOT)}:{line_number} has invalid uses "
                    f"declaration: {error}"
                )
                continue
            if LOCAL_ACTION.fullmatch(action):
                continue
            name, sha = action.rsplit("@", 1)
            expected = pins.get(name)
            if expected != sha:
                fail(
                    f"{path.relative_to(ROOT)}:{line_number} action {name!r} "
                    f"is not bound to the reviewed pin manifest"
                )


def check_command_baseline() -> None:
    makefile = require_text(
        "Makefile",
        [
            "python3 -m unittest tests.test_validate_project_truth -v",
            "python3 tools/validate_project_truth.py",
            "cargo check --workspace --all-targets --locked",
            "cargo clippy --workspace --all-targets --locked -- -D warnings",
            "cargo test --workspace --all-targets --locked",
            "cargo run --locked -p hepta-browserd -- --self-check",
        ],
    )
    ci = require_text(
        ".github/workflows/ci.yml",
        [
            "runs-on: ubuntu-24.04",
            "python3 -m unittest tests.test_validate_project_truth -v",
            "python3 tools/validate_project_truth.py",
            "cargo check --workspace --all-targets --locked",
            "cargo clippy --workspace --all-targets --locked -- -D warnings",
            "cargo test --workspace --all-targets --locked",
            "cargo run --locked -p hepta-browserd -- --self-check",
        ],
    )
    for text, label in ((makefile, "Makefile"), (ci, "CI")):
        if "cargo test --workspace\n" in text:
            fail(f"{label} contains an unlocked/non-all-targets workspace test")


def main() -> int:
    required = [
        "manifests/project-state.v1.json",
        "manifests/gates.v1.json",
        "manifests/upstream-reference-review.v1.json",
        "contracts/project-state.v1.schema.json",
        "contracts/gate-evidence-envelope.v1.schema.json",
        "contracts/d2i-integrated-image.v1.json",
        "manifests/ci-action-pins.v1.json",
        PLAN_PATH,
        "docs/plan/PROJECT_TRUTH_AND_EVIDENCE.md",
        "docs/plan/GATE_CONTRACTS_AND_INVALIDATION.md",
        "docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md",
        "docs/security/THREAT_MODEL_V2.md",
        "docs/security/SECURITY_CONTROL_MATRIX.md",
        "docs/release/RELEASE_SECURITY_AND_QUALIFICATION.md",
    ]
    for relative in required:
        try:
            _read_text_nofollow(ROOT / relative)
        except (OSError, UnicodeError) as error:
            fail(f"required d6 path is missing or unsafe: {relative}: {error}")

    check_truth_alignment()
    check_upstream_boundary()
    check_workflow_action_pins()
    check_command_baseline()

    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"project truth validation failed with {len(ERRORS)} error(s)", file=sys.stderr)
        return 1
    print("project truth validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
