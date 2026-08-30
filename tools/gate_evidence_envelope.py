#!/usr/bin/env python3
"""Build and validate the portable gate-evidence envelope.

The specialised receipts emitted by the D1 and D2I gates intentionally keep
their gate-specific result corpus.  This module provides the small, common
identity envelope required by ``contracts/gate-evidence-envelope.v1`` without
trying to replace those receipts.  It is deliberately dependency-free so a
downloaded evidence bundle can be checked offline on a fresh Python install.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any, BinaryIO, Mapping


SCHEMA = "trillionnium.desktop.gate-evidence.v1"
REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
PR_REF_RE = re.compile(r"^refs/pull/([1-9][0-9]*)/merge$")
PR_REF_NAME_RE = re.compile(r"^[1-9][0-9]*/merge$")
WORKFLOW_SUFFIX_RE = re.compile(r"^[A-Za-z0-9._-]+\.(?:yml|yaml)$")
PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
EVENTS = frozenset({"pull_request", "push", "workflow_dispatch"})
ROLES = frozenset({"pr_synthetic_merge", "exact_main_push", "manual_non_authoritative"})
PROVENANCE_CORE_FIELDS = frozenset(
    {"event_name", "ref", "ref_name", "evidence_role", "promotion_authoritative"}
)
PROVENANCE_RUN_FIELDS = frozenset({"workflow_run_id", "workflow_run_attempt"})
PROVENANCE_FIELDS = PROVENANCE_CORE_FIELDS | {"tested_sha"} | PROVENANCE_RUN_FIELDS
REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "gate_id",
        "package_id",
        "status",
        "evidence_tier",
        "repository",
        "base_sha",
        "candidate_head_sha",
        "tested_merge_sha",
        "integrated_main_sha",
        "tree_sha",
        "workflow_path",
        "workflow_sha256",
        "input_digests",
        "runner",
        "commands",
        "artifacts",
        "claim_ceiling",
        "recorded_at",
    }
)

_HASH_CHUNK_SIZE = 1024 * 1024
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting ambiguous duplicate keys."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def load_json_strict(stream: Any) -> Any:
    """Decode JSON without silently folding duplicate object keys."""

    return json.load(stream, object_pairs_hook=_reject_duplicate_json_keys)


def _text(value: Any, label: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{label} must be a non-empty string")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} contains a control character")
    return value


def _nullable_sha(value: Any, label: str, pattern: re.Pattern[str]) -> None:
    if value is None:
        return
    text = _text(value, label)
    if pattern.fullmatch(text) is None or set(text) == {"0"}:
        raise ValueError(f"{label} is not a lowercase non-null digest")


def _safe_relative(value: Any, label: str) -> str:
    text = _text(value, label)
    if "\\" in text or text != text.strip() or "\x00" in text:
        raise ValueError(f"{label} is not a portable relative path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != text
    ):
        raise ValueError(f"{label} is not a portable relative path")
    return text


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical component of *path* is a symlink.

    ``Path.resolve()`` follows links, which is exactly what an evidence
    verifier must not do.  Walk the lexical path with ``lstat`` instead.  A
    missing trailing component is not itself a link; the caller will report
    it as missing when it attempts to open the required file.
    """

    # Preserve parent segments while walking. Normalising link/../file before
    # lstat would erase a symlink component and defeat this check.
    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component == lexical.anchor:
            continue
        if component == ".":
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError(f"cannot inspect evidence path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _open_artifact(root: Path, relative: str) -> BinaryIO:
    """Open one regular artifact after rejecting lexical symlink components."""

    # Keep this helper safe even when called directly by a verifier or a
    # future integration point.  ``validate_artifacts_on_disk`` validates the
    # envelope entries before reaching here, but relying on that outer call
    # would leave a path-traversal footgun for private/API callers.
    relative = _safe_relative(relative, "artifact path")
    path = root.joinpath(*PurePosixPath(relative).parts)
    if _has_symlink_component(path):
        raise ValueError(f"artifact path contains a symlink: {relative}")
    # O_NOFOLLOW prevents a final-component swap after the lexical check;
    # O_NONBLOCK ensures a FIFO cannot make verification hang before its type
    # is rejected.  Intermediate parents are checked lexically above.
    flags = os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"artifact is absent or not a regular file: {relative}") from error
    try:
        artifact_stat = os.fstat(descriptor)
        if not stat.S_ISREG(artifact_stat.st_mode):
            raise ValueError(f"artifact is not a regular file: {relative}")
        return os.fdopen(descriptor, "rb", closefd=True)
    except BaseException:
        os.close(descriptor)
        raise


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    """Hash a binary stream in bounded chunks and return digest plus bytes."""

    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(_HASH_CHUNK_SIZE), b""):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _validate_digest_map(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty object")
    result: dict[str, str] = {}
    for relative, digest in value.items():
        path = _safe_relative(relative, f"{label} path")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"{label}[{path!r}] is not a lowercase SHA-256 digest")
        if set(digest) == {"0"}:
            raise ValueError(f"{label}[{path!r}] is the null SHA-256 digest")
        result[path] = digest
    return result


def _validate_commands(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("commands must be a non-empty array")
    names: set[str] = set()
    for index, command in enumerate(value):
        if not isinstance(command, dict):
            raise ValueError(f"commands[{index}] must be an object")
        name = _text(command.get("name"), f"commands[{index}].name")
        if name in names:
            raise ValueError(f"commands contains duplicate name {name!r}")
        names.add(name)
        if "status" in command:
            _text(command["status"], f"commands[{index}].status", max_length=128)
        if "exit_code" in command:
            code = command["exit_code"]
            if isinstance(code, bool) or not isinstance(code, int) or code < 0:
                raise ValueError(f"commands[{index}].exit_code is invalid")


def _validate_artifacts(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("artifacts must be a non-empty array")
    paths: set[str] = set()
    for index, artifact in enumerate(value):
        if not isinstance(artifact, dict):
            raise ValueError(f"artifacts[{index}] must be an object")
        path = _safe_relative(artifact.get("path"), f"artifacts[{index}].path")
        if path in paths:
            raise ValueError(f"artifacts contains duplicate path {path!r}")
        paths.add(path)
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"artifacts[{index}].sha256 is invalid")
        if set(digest) == {"0"}:
            raise ValueError(f"artifacts[{index}].sha256 is the null digest")
        # Byte counts are part of the digest binding, not an optional hint.
        # Requiring them keeps the offline validator fail-closed and avoids an
        # unsafe implicit choice in validate_artifacts_on_disk().
        if "bytes" not in artifact:
            raise ValueError(f"artifacts[{index}].bytes is required")
        size = artifact["bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"artifacts[{index}].bytes is invalid")


def _validate_recorded_at(value: Any) -> None:
    text = _text(value, "recorded_at", max_length=128)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("recorded_at is not ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("recorded_at must include an explicit timezone")


def _validate_provenance(envelope: Mapping[str, Any]) -> None:
    """Validate the event/ref/authority tuple when provenance is supplied.

    The v1 JSON schema keeps provenance additive for compatibility with older
    gates.  Once any provenance field is present, however, accepting a partial
    tuple would let a caller omit the ref name or authority bit that gives the
    event its security meaning.  Require the core fields together and require
    workflow run identity as a pair when either run field is supplied.
    """

    present = PROVENANCE_FIELDS & set(envelope)
    if not present:
        return
    present_core = PROVENANCE_CORE_FIELDS & set(envelope)
    if present_core != PROVENANCE_CORE_FIELDS:
        missing = sorted(PROVENANCE_CORE_FIELDS - present_core)
        raise ValueError(f"provenance core fields are incomplete: missing {missing}")
    present_run = PROVENANCE_RUN_FIELDS & set(envelope)
    if present_run and present_run != PROVENANCE_RUN_FIELDS:
        missing = sorted(PROVENANCE_RUN_FIELDS - present_run)
        raise ValueError(f"provenance run fields are incomplete: missing {missing}")

    event = _text(envelope["event_name"], "event_name", max_length=64)
    role = _text(envelope["evidence_role"], "evidence_role", max_length=64)
    ref = _text(envelope["ref"], "ref", max_length=512)
    ref_name = _text(envelope["ref_name"], "ref_name", max_length=512)
    authoritative = envelope["promotion_authoritative"]
    if not isinstance(authoritative, bool):
        raise ValueError("promotion_authoritative must be boolean")
    if event not in EVENTS:
        raise ValueError(f"unsupported event_name: {event!r}")
    if role not in ROLES:
        raise ValueError(f"unsupported evidence_role: {role!r}")
    if event == "pull_request":
        match = PR_REF_RE.fullmatch(ref)
        if (
            role != "pr_synthetic_merge"
            or match is None
            or ref_name != f"{match.group(1)}/merge"
            or authoritative
        ):
            raise ValueError("pull-request envelope has inconsistent role/ref")
        if PR_REF_NAME_RE.fullmatch(ref_name) is None:
            raise ValueError("pull-request envelope has inconsistent ref_name")
        if envelope.get("tested_merge_sha") is None:
            raise ValueError("pull-request envelope lacks tested_merge_sha")
        if envelope.get("integrated_main_sha") is not None:
            raise ValueError("pull-request envelope cannot claim integrated main")
    elif event == "push":
        if (
            role != "exact_main_push"
            or ref != "refs/heads/main"
            or ref_name != "main"
            or not authoritative
        ):
            raise ValueError("push envelope is not an exact-main identity")
        if envelope.get("integrated_main_sha") is None:
            raise ValueError("push envelope lacks integrated_main_sha")
    else:
        if role != "manual_non_authoritative" or authoritative:
            raise ValueError("manual envelope has inconsistent role/ref")
        if ref.startswith("refs/heads/"):
            suffix = ref[len("refs/heads/") :]
        elif ref.startswith("refs/tags/"):
            suffix = ref[len("refs/tags/") :]
        else:
            suffix = ""
        if not suffix or ref_name != suffix:
            raise ValueError("manual envelope has inconsistent ref_name")
        if envelope.get("integrated_main_sha") is not None:
            raise ValueError("manual envelope cannot claim integrated main")

    tested_sha = envelope.get("tested_sha")
    if tested_sha is not None:
        _nullable_sha(tested_sha, "tested_sha", GIT_SHA_RE)
        if (
            envelope.get("tested_merge_sha") is not None
            and tested_sha != envelope["tested_merge_sha"]
        ):
            raise ValueError("tested_sha does not match tested_merge_sha")
        if (
            envelope.get("integrated_main_sha") is not None
            and event == "push"
            and tested_sha != envelope["integrated_main_sha"]
        ):
            raise ValueError("tested_sha does not match integrated_main_sha")
    if present_run:
        run_id = _text(envelope["workflow_run_id"], "workflow_run_id", max_length=64)
        if RUN_ID_RE.fullmatch(run_id) is None:
            raise ValueError("workflow_run_id is not a positive decimal id")
        attempt = envelope["workflow_run_attempt"]
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("workflow_run_attempt is not a positive integer")


def validate_envelope(
    envelope: Mapping[str, Any],
    *,
    expected_gate_id: str | None = None,
    expected_workflow_path: str | None = None,
    expected_repository: str = REPOSITORY,
) -> None:
    """Validate one common evidence envelope against the v1 contract.

    Unknown fields remain allowed exactly as the published JSON schema permits;
    known fields are checked strictly, and callers can pin gate/workflow
    identity when validating a downloaded bundle.
    """

    if not isinstance(envelope, Mapping):
        raise ValueError("gate evidence envelope must be an object")
    missing = sorted(REQUIRED_FIELDS - set(envelope))
    if missing:
        raise ValueError(f"gate evidence envelope omits required fields: {missing}")
    if envelope.get("schema") != SCHEMA:
        raise ValueError("unexpected gate evidence envelope schema")
    gate_id = _text(envelope.get("gate_id"), "gate_id", max_length=128)
    if expected_gate_id is not None and gate_id != expected_gate_id:
        raise ValueError(f"envelope gate_id is not {expected_gate_id!r}")
    _text(envelope.get("package_id"), "package_id", max_length=128)
    if PACKAGE_ID_RE.fullmatch(envelope["package_id"]) is None:
        raise ValueError("package_id contains unsafe characters")
    _text(envelope.get("status"), "status", max_length=256)
    _text(envelope.get("evidence_tier"), "evidence_tier", max_length=128)
    if envelope.get("repository") != expected_repository:
        raise ValueError("envelope repository is not the canonical repository")
    for field in ("base_sha", "candidate_head_sha", "tested_merge_sha", "integrated_main_sha", "tree_sha"):
        _nullable_sha(envelope.get(field), field, GIT_SHA_RE)
    workflow_path = _safe_relative(envelope.get("workflow_path"), "workflow_path")
    workflow_parts = PurePosixPath(workflow_path).parts
    if (
        len(workflow_parts) < 3
        or workflow_parts[0] != ".github"
        or workflow_parts[1] != "workflows"
        or WORKFLOW_SUFFIX_RE.fullmatch(workflow_parts[-1]) is None
    ):
        raise ValueError("workflow_path is not a safe GitHub workflow path")
    if expected_workflow_path is not None and workflow_path != expected_workflow_path:
        raise ValueError(f"envelope workflow_path is not {expected_workflow_path!r}")
    _nullable_sha(envelope.get("workflow_sha256"), "workflow_sha256", SHA256_RE)
    _validate_digest_map(envelope.get("input_digests"), "input_digests")
    if not isinstance(envelope.get("runner"), dict):
        raise ValueError("runner must be an object")
    _validate_commands(envelope.get("commands"))
    _validate_artifacts(envelope.get("artifacts"))
    if not isinstance(envelope.get("claim_ceiling"), dict):
        raise ValueError("claim_ceiling must be an object")
    _validate_recorded_at(envelope.get("recorded_at"))
    _validate_provenance(envelope)


def build_envelope(
    *,
    gate_id: str,
    package_id: str,
    status: str,
    evidence_tier: str,
    base_sha: str | None,
    candidate_head_sha: str | None,
    tested_merge_sha: str | None,
    integrated_main_sha: str | None,
    tree_sha: str | None,
    workflow_path: str,
    workflow_sha256: str | None,
    input_digests: Mapping[str, str],
    runner: Mapping[str, Any],
    commands: list[Mapping[str, Any]],
    artifacts: list[Mapping[str, Any]],
    claim_ceiling: Mapping[str, Any],
    repository: str = REPOSITORY,
    recorded_at: str | None = None,
    **provenance: Any,
) -> dict[str, Any]:
    """Construct and validate one envelope, preserving optional provenance."""

    envelope: dict[str, Any] = {
        "schema": SCHEMA,
        "gate_id": gate_id,
        "package_id": package_id,
        "status": status,
        "evidence_tier": evidence_tier,
        "repository": repository,
        "base_sha": base_sha,
        "candidate_head_sha": candidate_head_sha,
        "tested_merge_sha": tested_merge_sha,
        "integrated_main_sha": integrated_main_sha,
        "tree_sha": tree_sha,
        "workflow_path": workflow_path,
        "workflow_sha256": workflow_sha256,
        "input_digests": dict(input_digests),
        "runner": dict(runner),
        "commands": [dict(command) for command in commands],
        "artifacts": [dict(artifact) for artifact in artifacts],
        "claim_ceiling": dict(claim_ceiling),
        "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    for key, value in provenance.items():
        if value is not None:
            envelope[key] = value
    validate_envelope(envelope)
    return envelope


def write_envelope(path: Path, envelope: Mapping[str, Any]) -> None:
    """Validate and atomically write an envelope JSON file."""

    validate_envelope(envelope)
    target = Path(os.fspath(path))
    if not target.is_absolute():
        target = Path.cwd() / target
    if _has_symlink_component(target):
        raise ValueError(f"refusing to write through a symlink: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(target.parent):
        raise ValueError(f"refusing to write through a symlinked parent: {target.parent}")
    temporary_path: Path | None = None
    temporary_descriptor: int | None = None
    try:
        # mkstemp combines a random name with O_EXCL, so a concurrent writer
        # cannot redirect the temporary file through a pre-existing symlink.
        temporary_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary_path = Path(temporary_name)
        if _has_symlink_component(temporary_path):
            raise ValueError(f"temporary envelope path contains a symlink: {temporary_path}")
        with os.fdopen(temporary_descriptor, "w", encoding="utf-8", closefd=True) as stream:
            temporary_descriptor = None
            stream.write(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                # Atomic rename still protects readers when the filesystem
                # does not support fsync (for example, some test filesystems).
                pass

        # Never follow an existing destination link.  os.replace atomically
        # swaps directory entries, so even a late destination swap cannot
        # write through the link; the post-check turns it into a failed call.
        if _has_symlink_component(target):
            raise ValueError(f"refusing to overwrite symlink: {target}")
        os.replace(temporary_path, target)
        temporary_path = None
        if _has_symlink_component(target):
            raise ValueError(f"envelope destination became a symlink: {target}")
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def validate_artifacts_on_disk(envelope: Mapping[str, Any], root: Path) -> None:
    """Verify every artifact entry against regular files below ``root``.

    This is intentionally separate from :func:`validate_envelope`: the latter
    can validate a transported JSON object without access to its bundle, while
    gate runners should also bind each advertised digest to bytes on disk.
    """

    validate_envelope(envelope)
    if _has_symlink_component(root) or not root.is_dir():
        raise ValueError(f"artifact root is missing or unsafe: {root}")
    for artifact in envelope["artifacts"]:
        relative = _safe_relative(artifact["path"], "artifact path")
        stream = _open_artifact(root, relative)
        with stream:
            digest, observed_size = _hash_stream(stream)
        if digest != artifact["sha256"]:
            raise ValueError(f"artifact digest mismatch: {relative}")
        if observed_size != artifact["bytes"]:
            raise ValueError(f"artifact byte count mismatch: {relative}")


def load_and_validate(path: Path, **kwargs: Any) -> dict[str, Any]:
    target = Path(os.fspath(path))
    if not target.is_absolute():
        target = Path.cwd() / target
    if _has_symlink_component(target):
        raise FileNotFoundError(f"gate evidence envelope is absent or unsafe: {path}")
    descriptor: int | None = None
    try:
        # Recheck the final component in the kernel after the lexical walk so
        # a late replacement with a symlink cannot redirect the read.
        descriptor = os.open(
            target,
            os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
        )
        envelope_stat = os.fstat(descriptor)
        if not stat.S_ISREG(envelope_stat.st_mode):
            raise ValueError(f"gate evidence envelope is not a regular file: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = None
            value = load_json_strict(stream)
    except FileNotFoundError as error:
        # Preserve the historical API for an absent envelope so callers can
        # distinguish a missing bundle from malformed or inaccessible bytes.
        raise FileNotFoundError(f"gate evidence envelope is absent: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid gate evidence envelope JSON: {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(value, dict):
        raise ValueError("gate evidence envelope JSON must be an object")
    validate_envelope(value, **kwargs)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--gate-id")
    parser.add_argument("--workflow-path")
    args = parser.parse_args()
    load_and_validate(
        args.path,
        expected_gate_id=args.gate_id,
        expected_workflow_path=args.workflow_path,
    )
    print(json.dumps({"schema": SCHEMA, "status": "PASS", "path": str(args.path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
