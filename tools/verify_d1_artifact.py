#!/usr/bin/env python3
"""Strictly verify a staged or downloaded D1 qualification artifact.

The artifact is an untrusted transport. This verifier therefore checks the
complete canonical file set, every advertised digest, and the provenance
fields which bind a receipt to one GitHub event/object. It cannot establish
GitHub's signature on an artifact downloaded without the workflow service;
that limitation is intentionally reflected in the output message.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from gate_evidence_envelope import (
    load_and_validate,
    load_json_strict,
    validate_envelope,
)


RECEIPT_PATH = PurePosixPath("evidence/d1-final-qualification.json")
GATE_ENVELOPE_PATH = PurePosixPath("evidence/gate-evidence-envelope.json")
SOURCE_MANIFEST_PATH = PurePosixPath("evidence/source-input-digests.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
PR_REF_RE = re.compile(r"^refs/pull/([1-9][0-9]*)/merge$")
PR_REF_NAME_RE = re.compile(r"^[1-9][0-9]*/merge$")
REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"

# Raw logs are useful diagnostics, but cannot replace a required canonical
# result or digest-bearing file.
REQUIRED_OUTPUT_PATHS = frozenset(
    {
        "pipeline/pipeline-result.json",
        "reproducibility/reproducibility-result.json",
        "qemu/boot-result.json",
        "qemu/acceptance.json",
        "inputs/prepared-inputs.json",
        "inputs/expected-package-lock.tsv",
        "builds/build-a/build-result.json",
        "builds/build-a/package-lock.tsv",
        "builds/build-a/rootfs-content-manifest.json",
        "builds/build-b/build-result.json",
        "builds/build-b/package-lock.tsv",
        "builds/build-b/rootfs-content-manifest.json",
        "evidence/binary-digests.json",
        "evidence/e2fsprogs-host-tool-result.json",
        "evidence/host-toolchain.json",
        "evidence/product-cargo-tree.txt",
        "evidence/qualification-cargo-tree.txt",
        "evidence/product-daemon-self-check-host.json",
        "evidence/d1-qualification-self-check-host.json",
        GATE_ENVELOPE_PATH.as_posix(),
        SOURCE_MANIFEST_PATH.as_posix(),
    }
)

# Without this stable corpus check a forged manifest can describe a tiny,
# unrelated tree while retaining a valid aggregate hash.
REQUIRED_SOURCE_PATHS = frozenset(
    {
        ".github/workflows/d1-final-qualification.yml",
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
        "apps/hepta-agent-portd/Cargo.toml",
        "apps/hepta-agent-portd/src/main.rs",
        "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs",
        "manifests/debian-snapshot.lock.v1.json",
        "manifests/debian-d1.lock.v1.json",
        "manifests/debian-d1.requirements.v1.json",
        "manifests/debian-d1.selection.json",
        "manifests/e2fsprogs-host-toolchain.v1.json",
        "packaging/debian/hepta-agent-portd.install",
        "packaging/debian/image/build-d1-image.sh",
        "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
        "packaging/debian/systemd/hepta-browserd-agent.socket",
        "packaging/debian/systemd/hepta-browserd-agent@.service",
        "packaging/debian/sysusers.d/trillionnium-desktop.conf",
        "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
        "packaging/debian/image/rootfs-overlay/etc/systemd/system/hepta-agent.service",
        "packaging/debian/image/rootfs-overlay/etc/systemd/system/hepta-browserd-agent@.service.d/10-d1-qualification-server.conf",
        "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance",
        "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-agent-fixture-launcher",
        "tests/qemu/run-d1-pipeline.sh",
        "tests/qemu/run-d1-boot-test.sh",
        "tools/compare_d1_builds.py",
        "tools/d1_rootfs_manifest.py",
        "tools/build_pinned_e2fsprogs.sh",
        "tools/finalize_d1_evidence.py",
        "tools/gate_evidence_envelope.py",
        "tools/prepare_d1_inputs.py",
        "tools/resolve_debian_snapshot.py",
        "tools/resolve_debian_snapshot_with_pinned_keys.py",
        "tools/run_d1_final_qualification.sh",
        "tools/verify_d1_artifact.py",
    }
)

RECEIPT_KEYS = frozenset(
    {
        "acceptance",
        "base_sha",
        "boot",
        "candidate_head_sha",
        "claim_ceiling",
        "event_name",
        "evidence_role",
        "host_environment",
        "host_tool",
        "output_digests",
        "pipeline",
        "product_fixture_separation",
        "promotion_authoritative",
        "ref",
        "ref_name",
        "repository",
        "reproducibility",
        "reproducibility_scope",
        "runner_sha256",
        "schema",
        "source_input_count",
        "source_input_files_sha256",
        "source_input_manifest_sha256",
        "status",
        "tested_sha",
        "tested_topology",
        "tree_sha",
        "workflow",
        "workflow_run_attempt",
        "workflow_run_id",
    }
)

RESULT_SCHEMAS = {
    "pipeline/pipeline-result.json": "trillionnium.desktop.d1-pipeline-result.v2",
    "reproducibility/reproducibility-result.json": "trillionnium.desktop.d1-reproducibility-result.v3",
    "qemu/boot-result.json": "trillionnium.desktop.d1-qemu-boot-result.v2",
    "qemu/acceptance.json": "trillionnium.desktop.d1-acceptance.v2",
    "inputs/prepared-inputs.json": "trillionnium.desktop.d1-prepared-inputs.v2",
    "builds/build-a/build-result.json": "trillionnium.desktop.d1-build-result.v2",
    "builds/build-b/build-result.json": "trillionnium.desktop.d1-build-result.v2",
    "evidence/e2fsprogs-host-tool-result.json": "trillionnium.desktop.e2fsprogs-host-tool-result.v1",
    "evidence/host-toolchain.json": "trillionnium.desktop.d1-host-toolchain.v1",
    "evidence/product-daemon-self-check-host.json": "trillionnium.desktop.agent-portd-self-check.v2",
    "evidence/d1-qualification-self-check-host.json": "trillionnium.desktop.d1-agent-fixture-self-check.v1",
}

REPRO_ARTIFACT_NAMES = frozenset(
    {
        "initrd.img",
        "package-lock.tsv",
        "rootfs-content-manifest.json",
        "rootfs.tar",
        "trillionnium-d1.ext4",
        "vmlinuz",
    }
)
ROOTFS_MANIFEST_KEYS = frozenset(
    {"schema", "entry_count", "entries_sha256", "entries"}
)
BINARY_DIGEST_KEYS = frozenset({"schema", "product", "qualification"})
ROOTFS_BINARY_PATHS = {
    "product": "./usr/libexec/hepta-agent-portd",
    "qualification": "./usr/libexec/hepta-agent-d1-fixture",
}
PIPELINE_STAGE_NAMES = frozenset(
    {
        "build_first",
        "build_second",
        "compare_builds",
        "pipeline",
        "prepare_exact_inputs",
        "qemu_acceptance",
        "validate_committed_lock",
    }
)
PIPELINE_STAGE_NAMES_GENERATED = frozenset(
    {
        "build_first",
        "build_second",
        "compare_builds",
        "pipeline",
        "prepare_exact_inputs",
        "qemu_acceptance",
        "resolve_signed_d1_closure",
    }
)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _has_symlink_component(path: Path) -> bool:
    """Check a raw CLI path without first resolving away symlink components."""

    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "", "."}:
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
            raise ValueError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _open_regular(path: Path, label: str) -> int:
    """Open one artifact input without following a late symlink replacement."""

    if _has_symlink_component(path):
        raise ValueError(f"{label} path contains a symlink: {path}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
        )
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise FileNotFoundError(f"{label} is absent: {path}") from error
        raise ValueError(f"{label} is absent or unreadable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_text(path: Path, label: str) -> str:
    descriptor = _open_regular(path, label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular(path, "artifact")
    try:
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
    except BaseException:
        os.close(descriptor)
        raise
    try:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    finally:
        stream.close()
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    descriptor = _open_regular(path, label)
    try:
        stream = os.fdopen(descriptor, "r", encoding="utf-8", closefd=True)
        descriptor = -1
    except BaseException:
        os.close(descriptor)
        raise
    try:
        try:
            value = load_json_strict(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{label} is not valid UTF-8 JSON: {path}") from error
    finally:
        stream.close()
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical JSON encoding used by D1 evidence producers."""

    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def validate_rootfs_manifest(
    path: Path, label: str
) -> dict[str, dict[str, Any]]:
    """Validate a canonical rootfs manifest and index its entries by path.

    The portable artifact does not include the large rootfs tarball.  The
    manifest is therefore the only independently transported representation of
    the files which were installed into the image.  Checking its own aggregate
    and the two security-sensitive binary entries prevents a forged binary
    digest report from being detached from the recorded rootfs.
    """

    document = load_json(path, label)
    if set(document) != ROOTFS_MANIFEST_KEYS:
        raise ValueError(
            f"{label} field set is malformed "
            f"(expected={sorted(ROOTFS_MANIFEST_KEYS)}, actual={sorted(document)})"
        )
    if document["schema"] != "trillionnium.desktop.d1-rootfs-manifest.v1":
        raise ValueError(f"{label} has the wrong schema")
    entries = document["entries"]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{label} entries are empty or not a list")
    entry_count = document["entry_count"]
    if (
        isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count <= 0
        or entry_count != len(entries)
    ):
        raise ValueError(f"{label} entry_count is inconsistent")
    entries_sha = require_sha256(document["entries_sha256"], f"{label}.entries_sha256")
    if hashlib.sha256(canonical_json_bytes(entries)).hexdigest() != entries_sha:
        raise ValueError(f"{label} entries_sha256 does not bind entries")

    indexed: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"{label} entry {index} is not an object")
        entry_path = raw.get("path")
        if not isinstance(entry_path, str) or (
            entry_path != "." and not entry_path.startswith("./")
        ):
            raise ValueError(f"{label} entry {index} has a non-canonical path")
        if entry_path != "." and (
            "\\" in entry_path
            or "\x00" in entry_path
            or any(ord(char) < 0x20 for char in entry_path)
            or any(part in {"", ".", ".."} for part in entry_path[2:].split("/"))
        ):
            # All non-root names must have non-empty, non-dot path components
            # and may not escape the root.
            raise ValueError(f"{label} entry {index} has an unsafe path")
        if entry_path in indexed:
            raise ValueError(f"{label} contains duplicate path {entry_path!r}")
        indexed[entry_path] = raw

    for role, expected_path in ROOTFS_BINARY_PATHS.items():
        entry = indexed.get(expected_path)
        if entry is None:
            raise ValueError(f"{label} omits required {role} binary entry")
        # d1_rootfs_manifest.py calls this field ``type``/``size``.  The
        # fallback names keep the verifier useful for the early v1 fixture
        # while still requiring a regular-file digest and positive size.
        kind = entry.get("type", entry.get("kind"))
        size = entry.get("size", entry.get("bytes"))
        if kind != "file":
            raise ValueError(f"{label} {role} entry is not a regular file")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"{label} {role} entry has an invalid size")
        require_sha256(entry.get("sha256"), f"{label} {role} entry.sha256")
    return indexed


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} is not boolean")
    return value


def require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} is not a positive integer")
    return value


def require_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} is not a non-negative integer")
    return value


def require_exact_keys(value: Any, keys: set[str] | frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValueError(f"{label} field set is malformed (expected={sorted(keys)}, actual={actual})")
    return value


def require_fields(value: Any, fields: set[str] | frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not an object")
    missing = sorted(set(fields) - set(value))
    if missing:
        raise ValueError(f"{label} omits required fields: {missing}")
    return value


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is not a non-empty string")
    if any(ord(char) < 0x20 for char in value):
        raise ValueError(f"{label} contains a control character")
    return value


def require_sha256(value: Any, label: str) -> str:
    text = require_text(value, label)
    if SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    if set(text) == {"0"}:
        raise ValueError(f"{label} is the null SHA-256 digest")
    return text


def require_git_sha(value: Any, label: str) -> str:
    text = require_text(value, label)
    if GIT_SHA_RE.fullmatch(text) is None:
        raise ValueError(f"{label} is not a lowercase Git object id")
    if set(text) == {"0"}:
        raise ValueError(f"{label} is the null Git object id")
    return text


def safe_relative(value: Any, label: str) -> PurePosixPath:
    text = require_text(value, label)
    if "\\" in text or text != text.strip() or "\x00" in text:
        raise ValueError(f"{label} is not a portable relative path: {text!r}")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != text
    ):
        raise ValueError(f"{label} is not a portable relative path: {text!r}")
    return path


def regular_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        relative = safe_relative(path.relative_to(root).as_posix(), "artifact path")
        if path.is_symlink():
            raise ValueError(f"artifact contains a symlink: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"artifact contains a non-regular file: {relative}")
        files[relative.as_posix()] = path
    return files


def validate_receipt(receipt: dict[str, Any]) -> tuple[str, bool]:
    if set(receipt) != RECEIPT_KEYS:
        missing = sorted(RECEIPT_KEYS - set(receipt))
        extra = sorted(set(receipt) - RECEIPT_KEYS)
        raise ValueError(f"receipt field set mismatch (missing={missing}, extra={extra})")
    if receipt["schema"] != "trillionnium.desktop.d1-final-qualification.v3":
        raise ValueError("unexpected D1 qualification receipt schema")
    if receipt["status"] != "PASS":
        raise ValueError("D1 qualification receipt is not a pass")
    repository = require_text(receipt["repository"], "repository")
    if repository != REPOSITORY:
        raise ValueError(f"receipt is for an unexpected repository: {repository!r}")
    event = require_text(receipt["event_name"], "event_name")
    ref = require_text(receipt["ref"], "ref")
    ref_name = require_text(receipt["ref_name"], "ref_name")
    role = require_text(receipt["evidence_role"], "evidence_role")
    authoritative = require_bool(
        receipt["promotion_authoritative"], "promotion_authoritative"
    )
    topology = require_text(receipt["tested_topology"], "tested_topology")

    if event == "pull_request":
        match = PR_REF_RE.fullmatch(ref)
        if (
            role != "pr_synthetic_merge"
            or match is None
            or PR_REF_NAME_RE.fullmatch(ref_name) is None
            or ref_name != f"{match.group(1)}/merge"
            or topology != "pr_merge_commit"
            or authoritative
        ):
            raise ValueError("pull-request receipt has inconsistent role/ref provenance")
    elif event == "push":
        if (
            role != "exact_main_push"
            or ref != "refs/heads/main"
            or ref_name != "main"
            or topology != "exact_push_commit"
            or not authoritative
        ):
            raise ValueError("push receipt is not an authoritative exact-main result")
    elif event == "workflow_dispatch":
        if (
            role != "manual_non_authoritative"
            or not ref.startswith("refs/")
            or topology != "manual_checkout"
            or authoritative
        ):
            raise ValueError("manual receipt has inconsistent non-authoritative provenance")
    else:
        raise ValueError(f"unsupported receipt event: {event!r}")

    for key in ("base_sha", "candidate_head_sha", "tested_sha", "tree_sha"):
        require_git_sha(receipt[key], key)
    if role in {"exact_main_push", "manual_non_authoritative"} and receipt[
        "candidate_head_sha"
    ] != receipt["tested_sha"]:
        raise ValueError("single-commit receipt does not bind candidate to tested SHA")
    require_sha256(receipt["runner_sha256"], "runner_sha256")
    require_sha256(receipt["source_input_manifest_sha256"], "source_input_manifest_sha256")
    require_sha256(receipt["source_input_files_sha256"], "source_input_files_sha256")
    require_positive_int(receipt["source_input_count"], "source_input_count")
    run_id = require_text(receipt["workflow_run_id"], "workflow_run_id")
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError("workflow_run_id is not a positive decimal id")
    attempt = receipt["workflow_run_attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("workflow_run_attempt is not a positive integer")

    workflow = receipt["workflow"]
    if not isinstance(workflow, dict) or set(workflow) != {"path", "sha256"}:
        raise ValueError("workflow provenance object is malformed")
    if workflow["path"] != ".github/workflows/d1-final-qualification.yml":
        raise ValueError("receipt workflow path is not the permanent D1 gate")
    require_sha256(workflow["sha256"], "workflow.sha256")

    claim_ceiling = receipt["claim_ceiling"]
    expected_ceiling = {
        "network_enabled_during_acceptance",
        "product_agent_port_enabled",
        "product_release_authorized",
        "secure_boot_qualified",
        "servo_started",
        "visible_window_created",
    }
    if not isinstance(claim_ceiling, dict) or set(claim_ceiling) != expected_ceiling:
        raise ValueError("claim_ceiling field set is incomplete")
    if any(require_bool(claim_ceiling[key], f"claim_ceiling.{key}") for key in expected_ceiling):
        raise ValueError("D1 claim ceiling contains an unauthorized true claim")

    scope = receipt["reproducibility_scope"]
    expected_scope = {
        "same_run_two_build_byte_identity",
        "cross_run_identity_claimed",
        "hermetic_host_environment_claimed",
    }
    if not isinstance(scope, dict) or set(scope) != expected_scope:
        raise ValueError("reproducibility_scope field set is incomplete")
    for key in expected_scope:
        require_bool(scope[key], f"reproducibility_scope.{key}")
    if scope["same_run_two_build_byte_identity"] is not True:
        raise ValueError("receipt does not claim two-build byte identity")
    if scope["cross_run_identity_claimed"] is not False or scope[
        "hermetic_host_environment_claimed"
    ] is not False:
        raise ValueError("receipt exceeds the D1 reproducibility claim ceiling")

    separation = receipt["product_fixture_separation"]
    required_separation = {
        "product_default_graph_fixture_free",
        "qualification_feature",
        "qualification_binary",
        "qualification_server_exec",
        "product_handler_connected",
        "production_install_map_contains_qualification_binary",
    }
    if not isinstance(separation, dict) or set(separation) != required_separation:
        raise ValueError("product/qualification separation evidence is incomplete")
    for key in (
        "product_default_graph_fixture_free",
        "product_handler_connected",
        "production_install_map_contains_qualification_binary",
    ):
        require_bool(separation[key], f"product_fixture_separation.{key}")
    if separation["product_default_graph_fixture_free"] is not True:
        raise ValueError("product graph is not proven fixture-free")
    if separation["qualification_feature"] != "d1-qualification":
        raise ValueError("unexpected qualification feature")
    if separation["qualification_binary"] != "hepta-agent-d1-fixture":
        raise ValueError("unexpected qualification binary")
    if separation["qualification_server_exec"] != (
        "/usr/libexec/hepta-agent-d1-fixture --mode server"
    ):
        raise ValueError("unexpected qualification server command")
    if separation["product_handler_connected"] is not False or separation[
        "production_install_map_contains_qualification_binary"
    ] is not False:
        raise ValueError("product/qualification separation claim is unsafe")

    output_digests = receipt["output_digests"]
    if not isinstance(output_digests, dict) or not output_digests:
        raise ValueError("D1 receipt has no output digest map")
    return role, authoritative


def validate_source_manifest(
    root: Path,
    source_manifest: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, str]:
    if source_manifest.get("schema") != "trillionnium.desktop.source-input-digests.v1":
        raise ValueError("source input digest manifest has the wrong schema")
    source_digests = source_manifest.get("files")
    if not isinstance(source_digests, dict) or not source_digests:
        raise ValueError("source input digest manifest is empty")
    count = source_manifest.get("file_count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(source_digests):
        raise ValueError("source input digest count is inconsistent")
    if not REQUIRED_SOURCE_PATHS.issubset(source_digests):
        missing = sorted(REQUIRED_SOURCE_PATHS - set(source_digests))
        raise ValueError(f"source input digest manifest omits required files: {missing}")
    for relative, expected in source_digests.items():
        safe_relative(relative, "source input path")
        require_sha256(expected, f"source input digest {relative}")
    canonical = json.dumps(
        source_digests, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    aggregate = hashlib.sha256(canonical).hexdigest()
    if aggregate != source_manifest.get("files_sha256"):
        raise ValueError("source input aggregate digest is inconsistent")
    require_sha256(source_manifest.get("files_sha256"), "source manifest files_sha256")
    if receipt["source_input_files_sha256"] != aggregate:
        raise ValueError("receipt does not bind source input file aggregate")
    if receipt["source_input_count"] != count:
        raise ValueError("receipt source input count does not match manifest")
    source_tested_sha = require_git_sha(
        source_manifest.get("tested_sha"), "source manifest tested_sha"
    )
    source_tree_sha = require_git_sha(
        source_manifest.get("tree_sha"), "source manifest tree_sha"
    )
    if source_tested_sha != receipt["tested_sha"] or source_tree_sha != receipt["tree_sha"]:
        raise ValueError("source manifest is not bound to receipt tested SHA/tree")
    manifest_path = root / Path(*SOURCE_MANIFEST_PATH.parts)
    if receipt["source_input_manifest_sha256"] != sha256(manifest_path):
        raise ValueError("receipt does not bind the staged source input manifest")
    workflow = receipt["workflow"]
    if source_digests[workflow["path"]] != workflow["sha256"]:
        raise ValueError("receipt workflow digest is not bound to source manifest")
    if source_digests["tools/run_d1_final_qualification.sh"] != receipt[
        "runner_sha256"
    ]:
        raise ValueError("receipt runner digest is not bound to source manifest")
    return source_digests


def validate_gate_envelope(
    root: Path,
    envelope: dict[str, Any],
    receipt: dict[str, Any],
    source_digests: dict[str, str],
) -> None:
    """Bind the common envelope to the specialized D1 receipt and outputs."""

    validate_envelope(
        envelope,
        expected_gate_id="D1-01",
        expected_workflow_path=".github/workflows/d1-final-qualification.yml",
    )
    expected = {
        "status": receipt["status"],
        "repository": receipt["repository"],
        "base_sha": receipt["base_sha"],
        "candidate_head_sha": receipt["candidate_head_sha"],
        "tree_sha": receipt["tree_sha"],
        "workflow_path": receipt["workflow"]["path"],
        "workflow_sha256": receipt["workflow"]["sha256"],
        "input_digests": source_digests,
        "runner": receipt["host_environment"],
        "claim_ceiling": receipt["claim_ceiling"],
    }
    for field, value in expected.items():
        if envelope.get(field) != value:
            raise ValueError(f"gate envelope {field!r} is not bound to D1 receipt")

    event = receipt["event_name"]
    expected_tested_merge = receipt["tested_sha"] if event == "pull_request" else None
    expected_integrated_main = receipt["tested_sha"] if event == "push" else None
    for field, value in {
        "event_name": event,
        "ref": receipt["ref"],
        "ref_name": receipt["ref_name"],
        "evidence_role": receipt["evidence_role"],
        "promotion_authoritative": receipt["promotion_authoritative"],
        "tested_sha": receipt["tested_sha"],
        "tested_merge_sha": expected_tested_merge,
        "integrated_main_sha": expected_integrated_main,
        "workflow_run_id": receipt["workflow_run_id"],
        "workflow_run_attempt": receipt["workflow_run_attempt"],
    }.items():
        if envelope.get(field) != value:
            raise ValueError(f"gate envelope provenance field {field!r} is inconsistent")

    stages = receipt["pipeline"].get("stages")
    if not isinstance(stages, dict) or not stages:
        raise ValueError("D1 receipt pipeline stages are absent")
    expected_commands = {
        name: {
            "name": name,
            "status": stage.get("status"),
            "exit_code": stage.get("exit_code"),
        }
        for name, stage in stages.items()
        if isinstance(stage, dict)
    }
    commands = envelope.get("commands")
    if not isinstance(commands, list):
        raise ValueError("gate envelope commands are malformed")
    actual_commands = {command.get("name"): command for command in commands}
    if actual_commands != expected_commands:
        raise ValueError("gate envelope commands are not bound to D1 pipeline stages")

    output_digests = receipt["output_digests"]
    expected_artifacts = set(output_digests) - {GATE_ENVELOPE_PATH.as_posix()}
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("gate envelope artifacts are malformed")
    artifact_paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("gate envelope artifact entry is malformed")
        relative = artifact.get("path")
        if not isinstance(relative, str):
            raise ValueError("gate envelope artifact path is malformed")
        path = safe_relative(relative, "gate envelope artifact path")
        relative = path.as_posix()
        if relative in artifact_paths or relative not in expected_artifacts:
            raise ValueError(f"gate envelope artifact path is not canonical: {relative}")
        artifact_paths.add(relative)
        candidate = root / Path(*path.parts)
        if not candidate.is_file() or candidate.is_symlink():
            raise FileNotFoundError(f"gate envelope artifact is absent: {relative}")
        if artifact.get("sha256") != output_digests[relative] or sha256(candidate) != artifact["sha256"]:
            raise ValueError(f"gate envelope artifact digest is not bound: {relative}")
        if artifact.get("bytes") != candidate.stat().st_size:
            raise ValueError(f"gate envelope artifact byte count is not bound: {relative}")
    if artifact_paths != expected_artifacts:
        missing = sorted(expected_artifacts - artifact_paths)
        extra = sorted(artifact_paths - expected_artifacts)
        raise ValueError(f"gate envelope artifact coverage mismatch (missing={missing}, extra={extra})")


def validate_canonical_results(root: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for relative, schema in RESULT_SCHEMAS.items():
        document = load_json(root / Path(*PurePosixPath(relative).parts), relative)
        if document.get("schema") != schema:
            raise ValueError(f"{relative} has unexpected schema")
        results[relative] = document
    return results


def validate_binary_digests(root: Path) -> dict[str, dict[str, Any]]:
    document = load_json(root / "evidence/binary-digests.json", "binary digest manifest")
    if set(document) != BINARY_DIGEST_KEYS:
        raise ValueError("binary digest manifest field set is incomplete")
    if document["schema"] != "trillionnium.desktop.d1-binary-digests.v1":
        raise ValueError("binary digest manifest has the wrong schema")
    expected_paths = {
        "product": "target/release/hepta-agent-portd",
        "qualification": "target/release/hepta-agent-d1-fixture",
    }
    for name, expected_path in expected_paths.items():
        item = document[name]
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise ValueError(f"binary digest entry {name!r} is incomplete")
        if item["path"] != expected_path:
            raise ValueError(f"binary digest path for {name!r} is unexpected")
        require_sha256(item["sha256"], f"binary digest {name}.sha256")
        if (
            isinstance(item["bytes"], bool)
            or not isinstance(item["bytes"], int)
            or item["bytes"] <= 0
        ):
            raise ValueError(f"binary digest byte count for {name!r} is invalid")
    return {name: document[name] for name in expected_paths}


def validate_build_bindings(root: Path, results: dict[str, dict[str, Any]]) -> None:
    prepared_path = root / "inputs/prepared-inputs.json"
    prepared_sha = sha256(prepared_path)
    prepared = results["inputs/prepared-inputs.json"]
    expected_lock_path = root / "inputs/expected-package-lock.tsv"
    expected_lock_sha = sha256(expected_lock_path)
    expected_lock_lines = [
        line
        for line in _read_text(expected_lock_path, "expected package lock").splitlines()
        if line.strip()
    ]
    if not expected_lock_lines:
        raise ValueError("expected package lock is empty")
    expected_lock_count = len(expected_lock_lines)
    binary_digests = validate_binary_digests(root)
    if prepared.get("expected_package_lock_sha256") != expected_lock_sha:
        raise ValueError("prepared input does not bind expected package lock bytes")
    for relative, build_name in (
        ("builds/build-a/build-result.json", "build-a"),
        ("builds/build-b/build-result.json", "build-b"),
    ):
        result = results[relative]
        if result.get("build_name") != "candidate" or result.get("status") != "PASS_BUILD_ONLY":
            raise ValueError(f"{relative} is not a passing candidate build")
        if result.get("prepared_manifest_sha256") != prepared_sha:
            raise ValueError(f"{relative} is not bound to prepared inputs")
        if result.get("network_during_acceptance") is not False or result.get("qemu_booted") is not False:
            raise ValueError(f"{relative} exceeds build-only claim ceiling")
        if result.get("release_marker_present") is not False:
            raise ValueError(f"{relative} retains the release marker")
        package = result.get("package_lock")
        manifest = result.get("rootfs_manifest")
        if not isinstance(package, dict) or package.get("path") != "package-lock.tsv":
            raise ValueError(f"{relative} package lock binding is malformed")
        if not isinstance(manifest, dict) or manifest.get("path") != "rootfs-content-manifest.json":
            raise ValueError(f"{relative} rootfs manifest binding is malformed")
        if package.get("sha256") != sha256(root / f"builds/{build_name}/package-lock.tsv"):
            raise ValueError(f"{relative} package lock digest does not match bytes")
        package_path = root / f"builds/{build_name}/package-lock.tsv"
        package_sha = sha256(package_path)
        if package_sha != expected_lock_sha:
            raise ValueError(
                f"{relative} package lock bytes differ from expected-package-lock.tsv"
            )
        if package.get("sha256") != expected_lock_sha:
            raise ValueError(
                f"{relative} package lock digest is not bound to expected-package-lock.tsv"
            )
        package_lines = [
            line
            for line in _read_text(package_path, f"{relative} package lock").splitlines()
            if line.strip()
        ]
        if package.get("entries") != len(package_lines) or len(package_lines) != expected_lock_count:
            raise ValueError(f"{relative} package lock entry count is inconsistent")
        if manifest.get("sha256") != sha256(
            root / f"builds/{build_name}/rootfs-content-manifest.json"
        ):
            raise ValueError(f"{relative} rootfs manifest digest does not match bytes")
        require_sha256(package.get("sha256"), f"{relative}.package_lock.sha256")
        require_sha256(manifest.get("sha256"), f"{relative}.rootfs_manifest.sha256")
        image = result.get("image")
        if not isinstance(image, dict) or image.get("path") != "trillionnium-d1.ext4":
            raise ValueError(f"{relative} image binding is malformed")
        require_sha256(image.get("sha256"), f"{relative}.image.sha256")
        if image.get("format") != "ext4":
            raise ValueError(f"{relative} image is not ext4")
        for key in ("kernel", "initrd", "rootfs_tar"):
            item = result.get(key)
            if not isinstance(item, dict):
                raise ValueError(f"{relative} lacks {key} digest binding")
            require_sha256(item.get("sha256"), f"{relative}.{key}.sha256")

        manifest_path = root / f"builds/{build_name}/rootfs-content-manifest.json"
        entries = validate_rootfs_manifest(
            manifest_path, f"{relative} rootfs manifest"
        )
        manifest_document = load_json(manifest_path, f"{relative} rootfs manifest")
        if manifest.get("entries_sha256") != manifest_document.get("entries_sha256"):
            raise ValueError(f"{relative} rootfs entries digest is inconsistent")
        for role, binary in binary_digests.items():
            expected_path = ROOTFS_BINARY_PATHS[role]
            entry = entries[expected_path]
            if entry.get("sha256") != binary["sha256"]:
                raise ValueError(
                    f"{relative} {role} rootfs digest is not bound to binary digest"
                )
            entry_size = entry.get("size", entry.get("bytes"))
            if entry_size != binary["bytes"]:
                raise ValueError(
                    f"{relative} {role} rootfs size is not bound to binary digest"
                )


def validate_result_semantics(
    results: dict[str, dict[str, Any]],
    *,
    prepared_digest: str | None = None,
    artifact_root: Path | None = None,
) -> None:
    """Reject a digest-consistent artifact whose nested result claims fail."""

    pipeline = results["pipeline/pipeline-result.json"]
    reproducibility = results["reproducibility/reproducibility-result.json"]
    boot = results["qemu/boot-result.json"]
    acceptance = results["qemu/acceptance.json"]
    prepared = results["inputs/prepared-inputs.json"]
    host_tool = results["evidence/e2fsprogs-host-tool-result.json"]
    product = results["evidence/product-daemon-self-check-host.json"]
    qualification = results["evidence/d1-qualification-self-check-host.json"]

    require_fields(
        pipeline,
        {"status", "failed_stage", "started_unix", "finished_unix", "stages", "authority"},
        "pipeline result",
    )
    require_fields(
        reproducibility,
        {
            "status",
            "reproducible",
            "artifact_comparisons",
            "rootfs_manifest_diff",
            "invariant_mismatches",
            "claims",
            "package_count",
            "prepared_inputs_sha256",
            "signed_package_set_sha256",
        },
        "reproducibility result",
    )
    require_fields(
        boot,
        {
            "status",
            "network",
            "direct_kernel_boot",
            "machine",
            "acceleration",
            "qemu_exit_status",
            "serial_pass_marker",
            "release_marker_absent",
            "clean_poweroff",
            "memory_mib",
            "vcpus",
            "claims",
        },
        "QEMU boot result",
    )
    require_fields(
        acceptance,
        {
            "status",
            "network_enabled",
            "pid1",
            "systemd",
            "udev",
            "dbus",
            "logind",
            "wayland_compositor",
            "wayland_socket",
            "agent_port",
        },
        "acceptance result",
    )
    require_fields(prepared, {"status", "claims", "package_count"}, "prepared-input result")
    require_fields(host_tool, {"status"}, "host filesystem-tool result")
    require_fields(product, {"ok", "product_handler_connected", "fixture_handler_linked"}, "product self-check")
    require_fields(
        qualification,
        {"status", "qualification_only", "product_handler_connected"},
        "qualification self-check",
    )

    if pipeline.get("status") != "PASS" or pipeline.get("failed_stage") is not None:
        raise ValueError("canonical D1 pipeline result is not a pass")
    if prepared.get("status") not in {
        "PASS_COMMITTED_SIGNED_D1_PACKAGE_LOCK",
        "PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK",
    }:
        raise ValueError("canonical D1 prepared-input result is not a pass")
    expected_stage_names = (
        PIPELINE_STAGE_NAMES
        if prepared["status"] == "PASS_COMMITTED_SIGNED_D1_PACKAGE_LOCK"
        else PIPELINE_STAGE_NAMES_GENERATED
    )
    stages = require_exact_keys(
        pipeline.get("stages"), expected_stage_names, "pipeline stages"
    )
    for name, stage in stages.items():
        stage = require_exact_keys(stage, {"exit_code", "status"}, f"pipeline stage {name}")
        if stage["status"] != "PASS" or require_nonnegative_int(
            stage["exit_code"], f"pipeline stage {name}.exit_code"
        ) != 0:
            raise ValueError(f"pipeline stage is not a successful zero-exit pass: {name}")
    authority = require_exact_keys(
        pipeline.get("authority"),
        {
            "qemu_network_enabled",
            "release_qualified",
            "secure_boot_qualified",
            "servo_started",
            "visible_window_created",
        },
        "pipeline authority",
    )
    for key in authority:
        if require_bool(authority[key], f"pipeline authority.{key}") is not False:
            raise ValueError(f"pipeline authority contains an unauthorized claim: {key}")
    started = require_positive_int(pipeline.get("started_unix"), "pipeline.started_unix")
    finished = require_positive_int(pipeline.get("finished_unix"), "pipeline.finished_unix")
    if finished < started:
        raise ValueError("pipeline finished_unix precedes started_unix")

    if reproducibility.get("status") != "PASS_TWO_INDEPENDENT_BUILDS":
        raise ValueError("canonical D1 reproducibility result is not a pass")
    if reproducibility.get("reproducible") is not True:
        raise ValueError("canonical D1 reproducibility result is not reproducible")
    comparisons = require_exact_keys(
        reproducibility.get("artifact_comparisons"),
        REPRO_ARTIFACT_NAMES,
        "reproducibility artifact comparisons",
    )
    for name, comparison in comparisons.items():
        comparison = require_exact_keys(
            comparison,
            {"equal", "first_bytes", "first_sha256", "second_bytes", "second_sha256"},
            f"reproducibility comparison {name}",
        )
        if require_bool(comparison["equal"], f"comparison {name}.equal") is not True:
            raise ValueError(f"canonical D1 artifact comparison failed: {name}")
        first_bytes = require_positive_int(comparison["first_bytes"], f"comparison {name}.first_bytes")
        second_bytes = require_positive_int(comparison["second_bytes"], f"comparison {name}.second_bytes")
        first_sha = require_sha256(comparison["first_sha256"], f"comparison {name}.first_sha256")
        second_sha = require_sha256(comparison["second_sha256"], f"comparison {name}.second_sha256")
        if first_bytes != second_bytes or first_sha != second_sha:
            raise ValueError(f"equal comparison has mismatched size/digest: {name}")
    if reproducibility.get("invariant_mismatches") != []:
        raise ValueError("reproducibility invariant_mismatches is not empty")
    rootfs_diff = require_exact_keys(
        reproducibility.get("rootfs_manifest_diff"),
        {
            "changed",
            "changed_count",
            "difference_count",
            "equal",
            "first_entry_count",
            "missing_from_first",
            "missing_from_first_count",
            "missing_from_second",
            "missing_from_second_count",
            "report_truncated",
            "second_entry_count",
        },
        "reproducibility rootfs manifest diff",
    )
    if rootfs_diff["equal"] is not True or rootfs_diff["changed"] != []:
        raise ValueError("reproducibility rootfs manifest diff is not empty")
    for key in (
        "changed_count",
        "difference_count",
        "missing_from_first_count",
        "missing_from_second_count",
    ):
        if require_nonnegative_int(rootfs_diff[key], f"rootfs_manifest_diff.{key}") != 0:
            raise ValueError(f"reproducibility rootfs diff count is nonzero: {key}")
    if rootfs_diff["missing_from_first"] != [] or rootfs_diff["missing_from_second"] != []:
        raise ValueError("reproducibility rootfs manifest has missing entries")
    if rootfs_diff["report_truncated"] is not False:
        raise ValueError("reproducibility rootfs manifest diff is truncated")
    for key in ("first_entry_count", "second_entry_count"):
        require_positive_int(rootfs_diff[key], f"rootfs_manifest_diff.{key}")
    repro_claims = require_exact_keys(
        reproducibility.get("claims"),
        {
            "two_build_rootfs_manifest_match",
            "two_build_rootfs_match",
            "two_build_ext4_match",
            "two_build_kernel_match",
            "two_build_initrd_match",
            "qemu_booted",
            "servo_started",
            "product_ready",
        },
        "reproducibility claims",
    )
    comparison_claims = {
        "two_build_rootfs_manifest_match": "rootfs-content-manifest.json",
        "two_build_rootfs_match": "rootfs.tar",
        "two_build_ext4_match": "trillionnium-d1.ext4",
        "two_build_kernel_match": "vmlinuz",
        "two_build_initrd_match": "initrd.img",
    }
    for claim, artifact in comparison_claims.items():
        if require_bool(repro_claims[claim], f"reproducibility claims.{claim}") is not comparisons[artifact]["equal"]:
            raise ValueError(f"reproducibility claim does not match comparison: {claim}")
    for claim in ("qemu_booted", "servo_started", "product_ready"):
        if require_bool(repro_claims[claim], f"reproducibility claims.{claim}") is not False:
            raise ValueError(f"reproducibility claim exceeds D1 ceiling: {claim}")
    prepared_package_count = require_positive_int(
        prepared.get("package_count"), "prepared.package_count"
    )
    prepared_package_set_digest = require_sha256(
        prepared.get("package_set_sha256"), "prepared.package_set_sha256"
    )
    prepared_selection_digest = require_sha256(
        prepared.get("selection_sha256"), "prepared.selection_sha256"
    )
    prepared_source_epoch = require_positive_int(
        prepared.get("source_date_epoch"), "prepared.source_date_epoch"
    )
    reproducibility_package_count = require_positive_int(
        reproducibility.get("package_count"), "reproducibility.package_count"
    )
    if reproducibility_package_count != prepared_package_count:
        raise ValueError("reproducibility package count is not bound to prepared inputs")
    reproducibility_prepared_digest = require_sha256(
        reproducibility.get("prepared_inputs_sha256"),
        "reproducibility.prepared_inputs_sha256",
    )
    reproducibility_package_set_digest = require_sha256(
        reproducibility.get("signed_package_set_sha256"),
        "reproducibility.signed_package_set_sha256",
    )
    if reproducibility_package_set_digest != prepared_package_set_digest:
        raise ValueError(
            "reproducibility result is not bound to prepared package set"
        )
    if prepared_digest is not None:
        require_sha256(prepared_digest, "prepared input artifact digest")
        if reproducibility_prepared_digest != prepared_digest:
            raise ValueError("reproducibility result is not bound to prepared inputs")

    # The build records are metadata-only in the portable artifact (the large
    # image/tar/kernel bytes are intentionally not uploaded).  Their digest and
    # path claims therefore still need to agree with the independent comparison
    # record before the verifier can accept the transport.
    build_paths = {
        "image": "trillionnium-d1.ext4",
        "rootfs_tar": "rootfs.tar",
        "kernel": "vmlinuz",
        "initrd": "initrd.img",
        "package_lock": "package-lock.tsv",
        "rootfs_manifest": "rootfs-content-manifest.json",
    }
    build_results: dict[str, dict[str, Any]] = {}
    for build_name, comparison_side in (("build-a", "first"), ("build-b", "second")):
        build = results[f"builds/{build_name}/build-result.json"]
        build_results[build_name] = build
        require_fields(
            build,
            {
                "image",
                "rootfs_tar",
                "kernel",
                "initrd",
                "package_lock",
                "rootfs_manifest",
                "image_id",
                "selection_sha256",
                "signed_package_set_sha256",
                "source_date_epoch",
            },
            f"{build_name} result",
        )
        for field, artifact_name in build_paths.items():
            item = require_fields(
                build[field], {"path", "sha256"}, f"{build_name}.{field} binding"
            )
            if item["path"] != artifact_name:
                raise ValueError(f"{build_name}.{field} path is not canonical")
            digest = require_sha256(item["sha256"], f"{build_name}.{field}.sha256")
            compared = comparisons[artifact_name][f"{comparison_side}_sha256"]
            if digest != compared:
                raise ValueError(
                    f"{build_name}.{field} digest disagrees with reproducibility comparison"
                )
        image = build["image"]
        if image.get("format") != "ext4" or image.get("label") != "TOSD1":
            raise ValueError(f"{build_name} image metadata is not canonical")
        require_positive_int(image.get("bytes"), f"{build_name}.image.bytes")
        require_text(image.get("uuid"), f"{build_name}.image.uuid")
        for field in ("package_lock", "rootfs_manifest"):
            require_positive_int(
                build[field].get("entries"), f"{build_name}.{field}.entries"
            )
        require_sha256(
            build["rootfs_manifest"].get("entries_sha256"),
            f"{build_name}.rootfs_manifest.entries_sha256",
        )
        if build["package_lock"]["entries"] != prepared_package_count:
            raise ValueError(f"{build_name} package count is not bound to prepared inputs")
        if build.get("selection_sha256") != prepared_selection_digest:
            raise ValueError(f"{build_name} selection digest is not bound to prepared inputs")
        if build.get("signed_package_set_sha256") != prepared_package_set_digest:
            raise ValueError(f"{build_name} package-set digest is not bound to prepared inputs")
        if build.get("source_date_epoch") != prepared_source_epoch:
            raise ValueError(f"{build_name} source epoch is not bound to prepared inputs")
    build_a = build_results["build-a"]
    build_b = build_results["build-b"]
    if build_a["image_id"] != build_b["image_id"]:
        raise ValueError("independent build image identities differ")
    build_image_id = require_text(build_a["image_id"], "build-a.image_id")
    if acceptance.get("image_id") != build_image_id:
        raise ValueError("QEMU acceptance is not bound to the built image identity")
    package_lock_digest = build_a["package_lock"]["sha256"]
    package_set_digest = prepared_package_set_digest
    if acceptance.get("package_lock_sha256") != package_lock_digest:
        raise ValueError("QEMU acceptance package lock is not bound to build output")
    if acceptance.get("package_set_sha256") != package_set_digest:
        raise ValueError("QEMU acceptance package set is not bound to prepared inputs")
    if boot.get("package_lock_sha256") != package_lock_digest:
        raise ValueError("QEMU boot package lock is not bound to build output")
    if boot.get("pre_boot_image_sha256") != build_a["image"]["sha256"]:
        raise ValueError("QEMU boot pre-image digest is not bound to build output")
    if artifact_root is not None:
        acceptance_path = artifact_root / "qemu/acceptance.json"
        if boot.get("guest_acceptance_sha256") != sha256(acceptance_path):
            raise ValueError(
                "QEMU guest acceptance digest is not bound to canonical acceptance output"
            )

    if boot.get("status") != "PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT":
        raise ValueError("canonical D1 QEMU result is not a pass")
    if (
        boot.get("network") != "none"
        or boot.get("direct_kernel_boot") is not True
        or boot.get("machine") != "q35"
        or boot.get("acceleration") != "tcg"
        or require_nonnegative_int(boot.get("qemu_exit_status"), "boot.qemu_exit_status") != 0
        or boot.get("serial_pass_marker") is not True
    ):
        raise ValueError("canonical D1 QEMU topology is outside the claim ceiling")
    if boot.get("release_marker_absent") is not True or boot.get("clean_poweroff") is not True:
        raise ValueError("canonical D1 QEMU cleanup claims are not proven")
    require_positive_int(boot.get("memory_mib"), "boot.memory_mib")
    require_positive_int(boot.get("vcpus"), "boot.vcpus")
    for key in (
        "guest_acceptance_sha256",
        "serial_log_sha256",
        "wayland_info_sha256",
        "package_lock_sha256",
        "agent_port_journal_sha256",
        "pre_boot_image_sha256",
        "post_boot_image_sha256",
    ):
        require_sha256(boot.get(key), f"boot.{key}")
    boot_claims = boot.get("claims")
    boot_claims = require_exact_keys(
        boot_claims,
        {
            "systemd_booted",
            "udev_active",
            "dbus_active",
            "logind_active",
            "headless_wayland_active",
            "agent_port_default_disabled",
            "agent_port_pid1_activation_validated",
            "unauthorized_peer_denied",
            "authorized_fixture_request",
            "per_connection_teardown",
            "connection_kill_recovered",
            "network_enabled",
            "servo_started",
            "visible_window_created",
            "secure_boot_qualified",
        },
        "QEMU boot claims",
    )
    for key in (
        "systemd_booted",
        "udev_active",
        "dbus_active",
        "logind_active",
        "headless_wayland_active",
        "agent_port_default_disabled",
        "agent_port_pid1_activation_validated",
        "unauthorized_peer_denied",
        "authorized_fixture_request",
        "per_connection_teardown",
        "connection_kill_recovered",
    ):
        if require_bool(boot_claims[key], f"boot.claims.{key}") is not True:
            raise ValueError(f"canonical D1 QEMU claim is not proven: {key}")
    for key in ("network_enabled", "servo_started", "visible_window_created", "secure_boot_qualified"):
        if require_bool(boot_claims[key], f"boot.claims.{key}") is not False:
            raise ValueError(f"canonical D1 QEMU non-claim is not false: {key}")

    prepared_claims = require_exact_keys(
        prepared.get("claims"),
        {
            "rootfs_created",
            "disk_image_created",
            "qemu_booted",
            "wayland_started",
            "agent_port_activated",
            "servo_started",
            "product_ready",
        },
        "prepared-input claims",
    )
    for key in prepared_claims:
        if require_bool(prepared_claims[key], f"prepared.claims.{key}") is not False:
            raise ValueError(f"prepared-input claim exceeds preparation ceiling: {key}")
    if host_tool.get("status") != "PASS_PINNED_ISOLATED_HOST_TOOL":
        raise ValueError("canonical D1 host filesystem-tool result is not a pass")
    if product.get("ok") is not True or product.get("product_handler_connected") is not False:
        raise ValueError("canonical product self-check is not fixture-free")
    if product.get("fixture_handler_linked") is not False:
        raise ValueError("canonical product self-check links the qualification fixture")
    if qualification.get("status") != "PASS" or qualification.get("qualification_only") is not True:
        raise ValueError("canonical qualification self-check is not a pass")
    if qualification.get("product_handler_connected") is not False:
        raise ValueError("canonical qualification self-check links the product handler")

    if (
        acceptance.get("status") != "PASS"
        or acceptance.get("network_enabled") is not False
        or acceptance.get("pid1") != "systemd"
        or any(acceptance.get(key) != "active" for key in ("systemd", "udev", "dbus", "logind", "wayland_compositor"))
        or acceptance.get("wayland_socket") != "/run/hepta-desktop/wayland-0"
    ):
        raise ValueError("canonical D1 acceptance result is outside the claim ceiling")
    for key in (
        "package_lock_sha256",
        "package_set_sha256",
        "wayland_info_sha256",
        "weston_log_sha256",
    ):
        require_sha256(acceptance.get(key), f"acceptance.{key}")
    agent = acceptance.get("agent_port")
    agent = require_exact_keys(
        agent,
        {
            "default_disabled",
            "marker_created_at_runtime_only",
            "socket_identity",
            "unauthorized_peer_denied",
            "authorized_request_completed",
            "per_connection_service_observed",
            "per_connection_teardown",
            "connection_kill_recovered",
            "marker_removed_before_poweroff",
            "socket_removed_before_poweroff",
            "qualification_only_server",
            "qualification_server_exec",
            "product_daemon_fixture_free",
            "product_handler_connected",
            "product_daemon_exercised_for_requests",
            "initial_response_sha256",
            "recovery_response_sha256",
            "journal_sha256",
            "product_self_check_sha256",
            "qualification_unit_sha256",
        },
        "acceptance AgentPort evidence",
    )
    for key in (
        "default_disabled",
        "marker_created_at_runtime_only",
        "unauthorized_peer_denied",
        "authorized_request_completed",
        "per_connection_teardown",
        "connection_kill_recovered",
        "marker_removed_before_poweroff",
        "socket_removed_before_poweroff",
        "qualification_only_server",
        "product_daemon_fixture_free",
    ):
        if require_bool(agent[key], f"acceptance.agent_port.{key}") is not True:
            raise ValueError(f"canonical D1 AgentPort claim is not proven: {key}")
    for key in (
        "product_handler_connected",
        "product_daemon_exercised_for_requests",
    ):
        if require_bool(agent[key], f"acceptance.agent_port.{key}") is not False:
            raise ValueError(f"canonical D1 AgentPort non-claim is not false: {key}")
    if agent["socket_identity"] != "hepta-browserd:hepta-agent:660":
        raise ValueError("acceptance AgentPort socket identity is unexpected")
    require_text(agent["per_connection_service_observed"], "acceptance.agent_port.per_connection_service_observed")
    if not agent["per_connection_service_observed"].startswith("hepta-browserd-agent@"):
        raise ValueError("acceptance AgentPort service identity is unexpected")
    if agent["qualification_server_exec"] != "/usr/libexec/hepta-agent-d1-fixture --mode server":
        raise ValueError("acceptance qualification server command is unexpected")
    for key in (
        "initial_response_sha256",
        "recovery_response_sha256",
        "journal_sha256",
        "product_self_check_sha256",
        "qualification_unit_sha256",
    ):
        require_sha256(agent[key], f"acceptance.agent_port.{key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    if _has_symlink_component(args.artifact_root):
        raise SystemExit(f"artifact root path contains a symlink: {args.artifact_root}")
    root = args.artifact_root.absolute()
    if not root.is_dir():
        raise SystemExit(f"artifact root is missing or unsafe: {root}")

    files = regular_files(root)
    receipt_path = root / Path(*RECEIPT_PATH.parts)
    if RECEIPT_PATH.as_posix() not in files:
        raise FileNotFoundError(f"required receipt is absent: {receipt_path}")
    receipt = load_json(receipt_path, "D1 receipt")
    role, authoritative = validate_receipt(receipt)

    output_digests = receipt["output_digests"]
    output_paths: set[str] = set()
    for relative, expected in output_digests.items():
        path = safe_relative(relative, "D1 output path")
        if path == RECEIPT_PATH:
            raise ValueError("receipt must not self-advertise in output_digests")
        require_sha256(expected, f"D1 output digest {relative}")
        output_paths.add(path.as_posix())
        candidate = root / Path(*path.parts)
        try:
            candidate.resolve().relative_to(root)
        except ValueError as error:
            raise ValueError(f"output path escapes artifact root: {relative!r}") from error
        if not candidate.is_file() or candidate.is_symlink():
            raise FileNotFoundError(f"declared artifact output is absent: {relative}")
        actual = sha256(candidate)
        if actual != expected:
            raise ValueError(
                f"artifact digest mismatch for {relative}: expected {expected}, got {actual}"
            )

    actual_output_paths = set(files) - {RECEIPT_PATH.as_posix()}
    if output_paths != actual_output_paths:
        missing = sorted(actual_output_paths - output_paths)
        unbound = sorted(output_paths - actual_output_paths)
        raise ValueError(
            "output digest map does not cover artifact files "
            f"(missing={missing}, unbound={unbound})"
        )
    missing_required = sorted(REQUIRED_OUTPUT_PATHS - output_paths)
    if missing_required:
        raise ValueError(f"D1 output digest map omits canonical files: {missing_required}")

    source_manifest = load_json(
        root / Path(*SOURCE_MANIFEST_PATH.parts), "source input digest manifest"
    )
    source_digests = validate_source_manifest(root, source_manifest, receipt)
    envelope = load_and_validate(
        root / Path(*GATE_ENVELOPE_PATH.parts),
        expected_gate_id="D1-01",
        expected_workflow_path=".github/workflows/d1-final-qualification.yml",
    )
    validate_gate_envelope(root, envelope, receipt, source_digests)
    results = validate_canonical_results(root)
    for field, relative in {
        "pipeline": "pipeline/pipeline-result.json",
        "reproducibility": "reproducibility/reproducibility-result.json",
        "boot": "qemu/boot-result.json",
        "acceptance": "qemu/acceptance.json",
        "host_tool": "evidence/e2fsprogs-host-tool-result.json",
        "host_environment": "evidence/host-toolchain.json",
    }.items():
        if receipt[field] != results[relative]:
            raise ValueError(f"receipt {field!r} is not equal to its canonical output")
    validate_binary_digests(root)
    validate_build_bindings(root, results)
    validate_result_semantics(
        results,
        prepared_digest=sha256(root / "inputs/prepared-inputs.json"),
        artifact_root=root,
    )

    print(
        json.dumps(
            {
                "schema": "trillionnium.desktop.d1-artifact-verification.v2",
                "status": "PASS",
                "receipt": RECEIPT_PATH.as_posix(),
                "evidence_role": role,
                "promotion_authoritative": authoritative,
                "verified_output_count": len(output_paths),
                "source_input_count": len(source_digests),
                "authenticity": "transport_consistency_only",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
