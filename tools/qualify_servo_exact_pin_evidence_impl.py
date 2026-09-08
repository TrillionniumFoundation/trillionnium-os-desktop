#!/usr/bin/env python3
"""Emit and validate the generic d6 envelope for D0A-01.

The Servo-specific result remains the detailed qualification record.  This
adapter binds that result to the desktop Git identities exported by
``qualify_servo_exact_pin_identity.py`` and to the exact downloadable files.
It reuses the repository-wide dependency-free envelope validator so all gates
share one schema and one offline verification path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVO_PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
PR_REF_RE = re.compile(r"^refs/pull/([1-9][0-9]*)/merge$")
PR_REF_NAME_RE = re.compile(r"^[1-9][0-9]*/merge$")
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
REQUIRED_COMPILE_RESULTS = frozenset(
    {
        "cargo_metadata_locked",
        "official_winit_minimal",
        "trillionnium_embedder_probe",
        "official_servoshell",
    }
)
REQUIRED_CLAIMS = frozenset(
    {
        "servo_started",
        "window_created",
        "frame_rendered",
        "native_input_forwarded",
        "ime_forwarded",
        "network_navigation_performed",
        "web_driver_listener_started",
        "debian_image_built",
        "product_ready",
    }
)
sys.path.insert(0, str(ROOT / "tools"))

from gate_evidence_envelope import (  # noqa: E402
    REPOSITORY,
    build_envelope,
    load_and_validate,
    load_json_strict,
    validate_artifacts_on_disk,
    write_envelope,
)


def sha256(path: Path) -> str:
    digest, _ = _digest_and_size(path, "hashed evidence file")
    return digest


def _digest_and_size(path: Path, label: str) -> tuple[str, int]:
    descriptor = _open_regular(path, label)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return digest.hexdigest(), size


def _open_regular(path: Path, label: str):
    """Open a regular file while rejecting lexical and late symlinks."""

    if _has_symlink_component(path):
        raise ValueError(f"{label} path contains a symlink: {path}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK,
        )
    except OSError as error:
        raise ValueError(f"{label} is absent or unsafe: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing component of *path* is a symlink.

    ``Path.resolve()`` erases the very property we need to reject, so this
    helper deliberately walks lexical components with ``lstat``.  Missing
    trailing components are allowed for output paths, while an inaccessible
    component fails closed.
    """

    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for component in absolute.parts:
        if component == absolute.anchor:
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


def source_inputs() -> list[Path]:
    paths: set[Path] = {
        ROOT / ".github/workflows/servo-exact-pin.yml",
        ROOT / "contracts/gate-evidence-envelope.v1.schema.json",
        ROOT / "tools/gate_evidence_envelope.py",
        ROOT / "tools/validate_project_truth.py",
        ROOT / "tools/validate_repository.py",
        ROOT / "manifests/gates.v1.json",
        ROOT / "manifests/project-state.v1.json",
        # The workflow watches these claim-bearing documents; bind their
        # bytes too so a documentation-only ceiling change invalidates an
        # otherwise identical envelope.
        ROOT / "docs/architecture/SERVO_EMBEDDER_COMPATIBILITY.md",
        ROOT / "docs/evidence/2026-08-29-d0a01-servo-exact-pin.md",
    }
    paths.update((ROOT / "manifests").glob("servo*.json"))
    paths.update((ROOT / "experiments/servo-embedder-probe").rglob("*"))
    paths.update(
        path
        for path in (ROOT / "tools").glob("qualify_servo_exact_pin*")
        if path.is_file()
    )
    selected: list[Path] = []
    for path in sorted(paths):
        if _has_symlink_component(path):
            raise ValueError(f"D0A-01 source input is a symlink: {path}")
        if not path.exists():
            raise ValueError(f"D0A-01 source input is missing: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"D0A-01 source input is not a regular file: {path}")
        selected.append(path)
    return selected


def required_servo_input_paths() -> frozenset[str]:
    """Load the immutable Servo input list used by the producing qualifier."""

    requirements_path = ROOT / "manifests/servo-api-requirements.v2.json"
    try:
        with os.fdopen(
            _open_regular(requirements_path, "D0A-01 Servo requirements manifest"),
            "r",
            encoding="utf-8",
            closefd=True,
        ) as stream:
            document = load_json_strict(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("D0A-01 Servo requirements manifest is unreadable") from error
    if not isinstance(document, dict) or document.get("servo_commit") != SERVO_PIN:
        raise ValueError("D0A-01 Servo requirements manifest has the wrong pin")
    values = document.get("required_inputs")
    if not isinstance(values, list) or not values or any(not isinstance(item, str) for item in values):
        raise ValueError("D0A-01 Servo requirements manifest has no valid input list")
    normalized: set[str] = set()
    for item in values:
        path = PurePosixPath(item)
        if (
            not item
            or "\\" in item
            or path.is_absolute()
            or path.as_posix() != item
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError(f"D0A-01 Servo requirements path is unsafe: {item!r}")
        normalized.add(item)
    if len(normalized) != len(values):
        raise ValueError("D0A-01 Servo requirements contain duplicate input paths")
    return frozenset(normalized)


def artifact_records(artifact_root: Path, output_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(artifact_root.rglob("*")):
        if _has_symlink_component(path):
            raise ValueError(f"D0A-01 artifact tree contains a symlink: {path}")
        if not path.is_file():
            continue
        if path.absolute() == output_path.absolute():
            continue
        digest, size = _digest_and_size(path, "D0A-01 artifact")
        records.append(
            {
                "path": path.relative_to(artifact_root).as_posix(),
                "sha256": digest,
                "bytes": size,
            }
        )
    if not records:
        raise ValueError("D0A-01 qualification produced no downloadable artifacts")
    return records


def validate_qualification_result(result: dict[str, Any]) -> None:
    """Re-check the specialized result before wrapping it generically.

    The workflow assertion is intentionally duplicated here: a downloaded
    envelope must not become a green D0A record merely because a producer
    supplied an arbitrary status string or a claim-bearing result.
    """

    if result.get("schema") != "trillionnium.desktop.servo-qualification-result.v2":
        raise ValueError("D0A-01 qualification result has the wrong schema")
    if result.get("status") != "PASS_COMPILE_COMPATIBILITY_ONLY":
        raise ValueError("D0A-01 qualification result is not compile-only PASS")
    servo = result.get("servo")
    if not isinstance(servo, dict):
        raise ValueError("D0A-01 qualification result lacks Servo identity")
    if servo.get("commit") != SERVO_PIN:
        raise ValueError("D0A-01 qualification result has the wrong Servo commit")
    if servo.get("repository") != "https://github.com/servo/servo":
        raise ValueError("D0A-01 qualification result has the wrong Servo repository")
    patch_count = servo.get("patch_count")
    if (
        servo.get("clean_checkout") is not True
        or isinstance(patch_count, bool)
        or patch_count != 0
    ):
        raise ValueError("D0A-01 Servo checkout is not clean and unpatched")
    source_hashes = servo.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("D0A-01 source hash set is empty")
    required_sources = required_servo_input_paths()
    if set(source_hashes) != set(required_sources):
        raise ValueError("D0A-01 source hash set does not match the locked Servo inputs")
    for path, digest in source_hashes.items():
        relative = PurePosixPath(path) if isinstance(path, str) else None
        if (
            relative is None
            or not path
            or "\\" in path
            or relative.is_absolute()
            or relative.as_posix() != path
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            or set(digest) == {"0"}
        ):
            raise ValueError("D0A-01 source hash entry is malformed")
    compile_results = result.get("compile_results")
    if not isinstance(compile_results, dict) or set(compile_results) != set(
        REQUIRED_COMPILE_RESULTS
    ):
        raise ValueError("D0A-01 compile result set is incomplete or contains extras")
    for name in sorted(REQUIRED_COMPILE_RESULTS):
        item = compile_results[name]
        if not isinstance(item, dict) or item.get("status") != "PASS":
            raise ValueError(f"D0A-01 compile result {name!r} is not PASS")
        log_digest = item.get("log_sha256")
        if (
            not isinstance(log_digest, str)
            or SHA256_RE.fullmatch(log_digest) is None
            or set(log_digest) == {"0"}
        ):
            raise ValueError(f"D0A-01 compile result {name!r} lacks a valid log digest")
    claims = result.get("claims")
    if not isinstance(claims, dict) or set(claims) != set(REQUIRED_CLAIMS):
        raise ValueError("D0A-01 claim ceiling field set is incomplete or contains extras")
    for name in sorted(REQUIRED_CLAIMS):
        value = claims[name]
        if not isinstance(value, bool) or value:
            raise ValueError(f"D0A-01 claim {name!r} is not an explicit false")
    if result.get("next_gate") != "D0A-02 product-owned headed local-fixture runtime":
        raise ValueError("D0A-01 next gate is not the canonical D0A-02 gate")


def identity_from_environment() -> dict[str, str]:
    names = (
        "EVENT_NAME",
        "SOURCE_REF",
        "SOURCE_REF_NAME",
        "TESTED_SHA",
        "TESTED_TREE_SHA",
        "BASE_SHA",
        "CANDIDATE_HEAD_SHA",
        "TESTED_MERGE_SHA",
        "INTEGRATED_MAIN_SHA",
        "EVIDENCE_ROLE",
        "PROMOTION_AUTHORITATIVE",
    )
    return {name: os.environ.get(name, "") for name in names}


def _require_identity_text(identity: dict[str, str], name: str) -> str:
    value = identity.get(name, "")
    if not isinstance(value, str) or not value or any(ord(char) < 0x20 for char in value):
        raise ValueError(f"D0A-01 identity field {name} is missing or malformed")
    return value


def _require_identity_sha(identity: dict[str, str], name: str) -> str:
    value = _require_identity_text(identity, name)
    if GIT_SHA_RE.fullmatch(value) is None or value == "0" * 40:
        raise ValueError(f"D0A-01 identity field {name} is not a non-zero Git SHA")
    return value


def _optional_identity_sha(identity: dict[str, str], name: str) -> str:
    value = identity.get(name, "")
    if value == "":
        return ""
    if (
        not isinstance(value, str)
        or GIT_SHA_RE.fullmatch(value) is None
        or value == "0" * 40
    ):
        raise ValueError(f"D0A-01 identity field {name} is not a non-zero Git SHA")
    return value


def validate_identity_environment(identity: dict[str, str]) -> dict[str, str]:
    """Validate the identity exported by the preceding GitHub step.

    The generic envelope validator checks shape when fields are present, but a
    missing identity export could otherwise be converted to ``null`` and still
    produce a transport-valid record.  D0A-01 always runs in one of three
    event topologies, so require the complete tuple and enforce its
    event-specific SHA/authority relationships before constructing the envelope.
    """

    event = _require_identity_text(identity, "EVENT_NAME")
    source_ref = _require_identity_text(identity, "SOURCE_REF")
    source_ref_name = _require_identity_text(identity, "SOURCE_REF_NAME")
    for name in ("TESTED_SHA", "TESTED_TREE_SHA", "BASE_SHA", "CANDIDATE_HEAD_SHA"):
        _require_identity_sha(identity, name)
    tested_sha = identity["TESTED_SHA"]
    candidate_head_sha = identity["CANDIDATE_HEAD_SHA"]
    tested_merge_sha = _optional_identity_sha(identity, "TESTED_MERGE_SHA")
    integrated_main_sha = _optional_identity_sha(identity, "INTEGRATED_MAIN_SHA")
    role = _require_identity_text(identity, "EVIDENCE_ROLE")
    authoritative = _require_identity_text(identity, "PROMOTION_AUTHORITATIVE")
    if authoritative not in {"true", "false"}:
        raise ValueError("D0A-01 PROMOTION_AUTHORITATIVE must be true or false")

    if event == "pull_request":
        match = PR_REF_RE.fullmatch(source_ref)
        if (
            match is None
            or PR_REF_NAME_RE.fullmatch(source_ref_name) is None
            or source_ref_name != f"{match.group(1)}/merge"
            or role != "pr_synthetic_merge"
            or authoritative != "false"
            or not tested_merge_sha
            or tested_merge_sha != tested_sha
            or integrated_main_sha
        ):
            raise ValueError("D0A-01 pull-request identity tuple is inconsistent")
    elif event == "push":
        if (
            source_ref != "refs/heads/main"
            or source_ref_name != "main"
            or role != "exact_main_push"
            or authoritative != "true"
            or tested_merge_sha
            or not integrated_main_sha
            or integrated_main_sha != tested_sha
            or candidate_head_sha != tested_sha
        ):
            raise ValueError("D0A-01 push identity tuple is inconsistent")
    elif event == "workflow_dispatch":
        if (
            role != "manual_non_authoritative"
            or authoritative != "false"
            or tested_merge_sha
            or integrated_main_sha
            or candidate_head_sha != tested_sha
            or not any(
                source_ref.startswith(prefix) and source_ref_name == source_ref[len(prefix) :]
                for prefix in ("refs/heads/", "refs/tags/")
            )
        ):
            raise ValueError("D0A-01 manual identity tuple is inconsistent")
    else:
        raise ValueError(f"D0A-01 identity event is unsupported: {event!r}")

    return identity


def validate_run_environment() -> tuple[str, int, str]:
    """Require the GitHub repository and immutable workflow-run identity.

    These values are part of the evidence provenance.  Falling back to the
    canonical repository name or omitting a run id makes a locally forged
    envelope indistinguishable from a workflow-produced record, so the D0A
    adapter requires the exact GitHub-provided values.
    """

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if repository != REPOSITORY:
        raise ValueError("D0A-01 GITHUB_REPOSITORY is not the canonical repository")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError("D0A-01 GITHUB_RUN_ID must be a positive decimal id")
    attempt_text = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if RUN_ID_RE.fullmatch(attempt_text) is None:
        raise ValueError("D0A-01 GITHUB_RUN_ATTEMPT must be a positive decimal id")
    return repository, int(attempt_text), run_id


def run(args: argparse.Namespace) -> int:
    raw_qualification = Path(args.qualification_result)
    raw_output = Path(args.output)
    if _has_symlink_component(raw_qualification) or not raw_qualification.is_file():
        raise ValueError("D0A-01 qualification result is missing or unsafe")
    if _has_symlink_component(raw_output):
        raise ValueError("D0A-01 output path is unsafe")
    qualification = raw_qualification.absolute()
    output = raw_output.absolute()
    artifact_root = qualification.parent
    if _has_symlink_component(artifact_root) or not artifact_root.is_dir():
        raise ValueError("D0A-01 qualification artifact root is missing or unsafe")
    descriptor = _open_regular(qualification, "D0A-01 qualification result")
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            result = load_json_strict(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(result, dict) or not isinstance(result.get("status"), str):
        raise ValueError("Servo qualification result is not an object with status")
    validate_qualification_result(result)

    identity = validate_identity_environment(identity_from_environment())
    event_name = identity["EVENT_NAME"]
    source_ref = identity["SOURCE_REF"]
    source_ref_name = identity["SOURCE_REF_NAME"]
    authoritative_text = identity["PROMOTION_AUTHORITATIVE"]

    repository, attempt, run_id = validate_run_environment()
    workflow = ROOT / ".github/workflows/servo-exact-pin.yml"
    inputs = {
        path.relative_to(ROOT).as_posix(): sha256(path) for path in source_inputs()
    }
    compile_results = result.get("compile_results", {})
    commands = [
        {
            "name": "qualify_servo_exact_pin_v3.py",
            "status": result["status"],
            "exit_code": 0,
        },
    ]
    for name in (
        "cargo_metadata_locked",
        "official_winit_minimal",
        "trillionnium_embedder_probe",
        "official_servoshell",
    ):
        item = compile_results.get(name, {})
        commands.append(
            {"name": name, "status": item.get("status", "MISSING"), "exit_code": 0}
        )

    envelope = build_envelope(
        gate_id="D0A-01",
        package_id="TOS-D0A-01",
        status=result["status"],
        evidence_tier="host",
        base_sha=identity["BASE_SHA"] or None,
        candidate_head_sha=identity["CANDIDATE_HEAD_SHA"] or None,
        tested_merge_sha=identity["TESTED_MERGE_SHA"] or None,
        integrated_main_sha=identity["INTEGRATED_MAIN_SHA"] or None,
        tree_sha=identity["TESTED_TREE_SHA"] or None,
        workflow_path=".github/workflows/servo-exact-pin.yml",
        workflow_sha256=sha256(workflow),
        input_digests=inputs,
        runner={
            "os": os.environ.get("RUNNER_OS", ""),
            "name": os.environ.get("RUNNER_NAME", ""),
            "arch": os.environ.get("RUNNER_ARCH", ""),
        },
        commands=commands,
        artifacts=artifact_records(artifact_root, output),
        claim_ceiling={
            "compile_compatibility_only": True,
            "no_visible_frame": True,
            "claims": result.get("claims", {}),
        },
        repository=repository,
        event_name=event_name,
        ref=source_ref,
        ref_name=source_ref_name,
        evidence_role=identity["EVIDENCE_ROLE"],
        promotion_authoritative=authoritative_text == "true",
        tested_sha=identity["TESTED_SHA"] or None,
        workflow_run_id=run_id,
        workflow_run_attempt=attempt,
    )
    validate_artifacts_on_disk(envelope, artifact_root)
    write_envelope(output, envelope)
    loaded = load_and_validate(
        output,
        expected_gate_id="D0A-01",
        expected_workflow_path=".github/workflows/servo-exact-pin.yml",
    )
    validate_artifacts_on_disk(loaded, artifact_root)
    print(json.dumps(loaded, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification-result", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return run(parser.parse_args())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - fail-closed CLI boundary
        print(f"D0A-01 evidence envelope failed: {error}", file=sys.stderr)
        raise
