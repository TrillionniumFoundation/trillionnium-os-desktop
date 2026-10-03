#!/usr/bin/env python3
"""Strict offline verifier for a D2I portable artifact directory."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from typing import Any

try:
    from .artifact_evidence import artifact_file, artifact_root, digest, load, open_file, open_managed_file, safe_relative, validate_role, verify_outputs, verify_workflow_binding, SHA256
    from .verify_d1_artifact import verify_artifact as verify_d1_artifact
except ImportError:
    from artifact_evidence import artifact_file, artifact_root, digest, load, open_file, open_managed_file, safe_relative, validate_role, verify_outputs, verify_workflow_binding, SHA256
    from verify_d1_artifact import verify_artifact as verify_d1_artifact

RECEIPT = "evidence/d2i-final-qualification.json"
MAX_SOURCE_ARCHIVE_BYTES = 64 * 1024 * 1024


def _same_typed_value(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (set(actual) == set(expected)
                and all(_same_typed_value(actual[key], value) for key, value in expected.items()))
    if isinstance(expected, list):
        return (len(actual) == len(expected)
                and all(_same_typed_value(left, right) for left, right in zip(actual, expected)))
    return actual == expected


def require(document: dict[str, Any], key: str, expected: object) -> None:
    actual = document.get(key)
    if not _same_typed_value(actual, expected):
        raise ValueError(f"D2I evidence field {key!r} must equal {expected!r}")


def verify_process_identity(root: Path, runtime: dict[str, Any]) -> None:
    selected = load(artifact_file(root, "d2i/qemu/content-process-identity.json"))
    signal = load(artifact_file(root, "d2i/qemu/content-sigkill-sent.json"))
    if set(selected) != {"generation", "pid", "start_time_ticks"} or set(signal) != {"generation", "pid", "start_time_ticks", "signal"}:
        raise ValueError("content process identity record fields differ")
    require(selected, "generation", 1)
    require(signal, "generation", 1)
    require(signal, "signal", "SIGKILL")
    old = {"pid": selected.get("pid"), "start_time_ticks": selected.get("start_time_ticks")}
    new = {"pid": runtime.get("replacement_content_process_pid"),
           "start_time_ticks": runtime.get("replacement_content_process_start_time_ticks")}
    for identity in (old, new):
        if type(identity["pid"]) is not int or identity["pid"] <= 1 or type(identity["start_time_ticks"]) is not int or identity["start_time_ticks"] <= 0:
            raise ValueError("content process identity is malformed")
    if old == new:
        raise ValueError("replacement content process reuses the terminated identity")
    for key, value in old.items():
        require(signal, key, value)
    require(runtime, "content_process_pid", old["pid"])
    require(runtime, "content_process_start_time_ticks", old["start_time_ticks"])
    embedder = None
    for phase, identities in (("pre-fault", [old]), ("post-termination", []), ("post-recovery", [new])):
        topology = load(artifact_file(root, f"d2i/qemu/process-topology-{phase}.json"))
        if set(topology) != {"active_process_count", "processes", "embedder_pid"}:
            raise ValueError("content process topology record fields differ")
        require(topology, "active_process_count", len(identities))
        require(topology, "processes", identities)
        if type(topology.get("embedder_pid")) is not int or topology["embedder_pid"] <= 1:
            raise ValueError("embedder identity is absent")
        if embedder is None:
            embedder = topology["embedder_pid"]
        require(topology, "embedder_pid", embedder)
        if any(identity["pid"] == embedder for identity in identities):
            raise ValueError("content process identity aliases the trusted embedder")


def _git_tree_oid(nodes: dict[str, Any]) -> bytes:
    """Rebuild Git's tracked tree, including executable mode and raw UTF-8 names."""
    payload = bytearray()
    for name, value in sorted(nodes.items(), key=lambda pair: pair[0].encode("utf-8") + (b"/" if isinstance(pair[1], dict) else b"")):
        if isinstance(value, dict):
            mode, oid = b"40000", _git_tree_oid(value)
        else:
            mode, oid = value
        payload.extend(mode + b" " + name.encode("utf-8") + b"\0" + oid)
    return hashlib.sha1(b"tree " + str(len(payload)).encode("ascii") + b"\0" + payload).digest()


def _read_source_archive(path: Path) -> bytes:
    """Parse and bind one bounded retained source archive without raw FD transfer."""
    with open_managed_file(path) as stream:
        before = stream.stat()
        if before.st_size > MAX_SOURCE_ARCHIVE_BYTES:
            raise ValueError("source archive exceeds its byte bound")
        data = stream.read(MAX_SOURCE_ARCHIVE_BYTES + 1)
        after = stream.stat()
        fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                                value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (len(data) > MAX_SOURCE_ARCHIVE_BYTES or len(data) != before.st_size
                or fields(before) != fields(after)):
            raise ValueError("source archive changed during retained read")
    return data


def verify_source(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    source_path = artifact_file(root, "source/source-input-digests.json")
    archive_path = artifact_file(root, "source/source.tar")
    source = load(source_path)
    require(source, "schema", "trillionnium.desktop.d2i-source-inputs.v1")
    require(source, "tree_sha", receipt.get("tree_sha"))
    entries = source.get("entries")
    if not isinstance(entries, list) or not entries or type(source.get("entry_count")) is not int or source["entry_count"] != len(entries):
        raise ValueError("source manifest count mismatch or empty source")
    expected: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}:
            raise ValueError("malformed source manifest entry")
        name = safe_relative(entry["path"]).as_posix()
        if name in expected or type(entry["bytes"]) is not int or entry["bytes"] < 0:
            raise ValueError("source path is duplicated or size is malformed")
        if not isinstance(entry["sha256"], str) or SHA256.fullmatch(entry["sha256"]) is None:
            raise ValueError("source digest is malformed")
        expected[name] = entry
    observed: set[str] = set()
    git_nodes: dict[str, Any] = {}
    archive_bytes = _read_source_archive(archive_path)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive:
            # Archives are inspected without extraction. Links and special files
            # cannot represent a tracked immutable source input.
            if member.isdir():
                safe_relative(member.name.rstrip("/"))
                continue
            name = safe_relative(member.name).as_posix()
            if not member.isfile() or name in observed or name not in expected:
                raise ValueError("source archive contains an unsafe, duplicate, or undeclared member")
            entry = expected[name]
            if member.size != entry["bytes"]:
                raise ValueError("source archive member size mismatch")
            parts = name.split("/")
            if len(name.encode("utf-8")) > 4096 or len(parts) > 128:
                raise ValueError("source archive path is over its bound")
            if member.mode not in {0o644, 0o664, 0o755, 0o775}:
                raise ValueError("source archive file has an unsupported Git mode")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("source archive member has no payload")
            value = hashlib.sha256()
            blob = hashlib.sha1(b"blob " + str(member.size).encode("ascii") + b"\0")
            with stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(chunk)
                    blob.update(chunk)
            if value.hexdigest() != entry["sha256"]:
                raise ValueError("source archive differs from tracked source manifest")
            observed.add(name)
            parent = git_nodes
            for part in parts[:-1]:
                child = parent.setdefault(part, {})
                if not isinstance(child, dict):
                    raise ValueError("source archive file/directory paths conflict")
                parent = child
            if parts[-1] in parent:
                raise ValueError("source archive file/directory paths conflict")
            parent[parts[-1]] = (b"100755" if member.mode & 0o111 else b"100644", blob.digest())
    if observed != set(expected):
        raise ValueError("source archive does not contain every declared source input")
    if _git_tree_oid(git_nodes).hex() != receipt["tree_sha"]:
        raise ValueError("source archive bytes and modes do not rebuild the declared Git tree")
    d1_source = load(artifact_file(root, "d1/evidence/source-input-digests.json"))
    if d1_source.get("files") != {name: entry["sha256"] for name, entry in expected.items()}:
        raise ValueError("D1 and D2I source input manifests differ")
    source_files = {name: entry["sha256"] for name, entry in expected.items()}
    verify_workflow_binding(receipt.get("producer_workflow"), source_files, producer=True,
                            tested_sha=receipt["tested_sha"])
    verify_workflow_binding({"path": ".github/workflows/d2i-integrated-image.yml",
                             "sha256": receipt.get("workflow_sha256")}, source_files, producer=False)
    binding = receipt.get("source")
    if not _same_typed_value(binding, {
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "manifest_sha256": digest(source_path),
        "entry_count": len(entries),
    }):
        raise ValueError("receipt source archive or manifest binding is inconsistent")
    return source


def verify_artifact(path: Path) -> dict[str, Any]:
    root = artifact_root(path)
    receipt = load(artifact_file(root, RECEIPT))
    require(receipt, "schema", "trillionnium.desktop.d2i-final-qualification.v1")
    require(receipt, "status", "PASS_D2I_EXACT_IMAGE_CANDIDATE")
    validate_role(receipt)
    require(receipt, "claims", {
        "same_exact_image_contains_d1_and_headed_servo": True,
        "systemd_pid1": True,
        "headless_wayland": True,
        "single_content_surface": True,
        "image_local_servo_input_dispatch": True,
        "native_host_input_inherited_from_d0a02_only": True,
        "popup_denied": True,
        "external_navigation_denied": True,
        "sigkill_exact_identity": True,
        "zero_process_intermediate": True,
        "distinct_replacement_identity": True,
        "crash_callback_required": False,
        "product_agent_port_default_disabled": True,
        "network_device_present": False,
    })
    require(receipt, "claim_ceiling", {
        "browser_actor": False,
        "product_agent_port_enabled": False,
        "external_effects": False,
        "secure_boot": False,
        "hardware_readiness": False,
        "signed_update": False,
        "release_readiness": False,
    })
    outputs = receipt.get("output_digests")
    verify_outputs(root, RECEIPT, outputs, sized=True)
    d1 = verify_d1_artifact(root / "d1")
    for key in ("repository", "event_name", "ref", "evidence_role", "promotion_authoritative", "base_sha", "candidate_head_sha", "tested_sha", "tree_sha", "producer_workflow"):
        require(receipt, key, d1.get(key))
    require(receipt, "d1_receipt_sha256", digest(artifact_file(root, "d1/evidence/d1-final-qualification.json")))
    verify_source(root, receipt)
    prep_a = load(artifact_file(root, "d2i/integrated/preparation-a.json"))
    prep_b = load(artifact_file(root, "d2i/integrated/preparation-b.json"))
    for prep in (prep_a, prep_b):
        require(prep, "schema", "trillionnium.desktop.d2i-image-preparation.v1")
        require(prep, "status", "PASS_DETERMINISTIC_INPUT_INJECTION")
        require(prep, "integrated_image_sha256", receipt.get("integrated_image_sha256"))
        require(prep, "servo_revision", receipt.get("servo_commit"))
    if prep_a != prep_b:
        raise ValueError("independent image preparation evidence differs")
    for name, key in (("runtime", "runtime_transformation_sha256"), ("boot-runner", "boot_runner_transformation_sha256")):
        transformation = artifact_file(root, f"d2i/runtime/{name}-transformation.json")
        require(receipt, key, digest(transformation))
        require(load(transformation), "callback_required", False)
    runtime = load(artifact_file(root, "d2i/qemu/runtime-ready.json"))
    guest = load(artifact_file(root, "d2i/qemu/guest-acceptance.json"))
    boot = load(artifact_file(root, "d2i/qemu/boot-result.json"))
    require(runtime, "status", "PASS_HEADED_SERVO_NATIVE_CHROME_SINGLE_CONTENT_RECOVERY")
    for key in (
        "actual_content_process_crash_proven", "signal_sent", "content_process_termination_observed",
        "zero_content_processes_after_termination", "replacement_process_distinct",
        "page_input_verified", "ime_path_exercised", "trusted_chrome_survived_recovery",
    ):
        require(runtime, key, True)
    # Twelve ordinary input events plus three submitted IME composition events.
    require(runtime, "input_events_sent", 15)
    require(runtime, "ime_composition_events_sent", 3)
    require(runtime, "simulated_content_process_recovery", False)
    if type(runtime.get("frame_count")) is not int or runtime["frame_count"] < 2:
        raise ValueError("runtime frame_count must be an integer of at least 2")
    if type(runtime.get("input_events_handled")) is not int or runtime["input_events_handled"] < 3:
        raise ValueError("runtime input_events_handled must be an integer of at least 3")
    require(runtime, "crash_callback_required", False)
    require(runtime, "external_network_used", False)
    require(runtime, "content_surface_limit", 1)
    require(runtime, "content_generation", 2)
    verify_process_identity(root, runtime)
    for key in ("popup_requests_denied", "external_navigation_requests_denied"):
        if type(runtime.get(key)) is not int or runtime[key] < 1:
            raise ValueError(f"runtime denial proof is absent: {key}")
    require(guest, "schema", "trillionnium.desktop.d2i-guest-acceptance.v2")
    require(guest, "status", "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE")
    for key in ("actual_content_process_crash_proven", "sigkill_delivered", "exact_old_identity_absent", "zero_process_intermediate", "replacement_identity_distinct", "popup_denied", "external_navigation_denied", "product_agent_port_default_disabled", "product_agent_port_socket_absent"):
        require(guest, key, True)
    for key in ("crash_callback_required", "network_enabled", "release_ready"):
        require(guest, key, False)
    for key in ("udev_active", "dbus_active", "logind_active", "headless_wayland_active",
                "headed_servo_runtime_completed", "trusted_chrome_survived_recovery",
                "page_input_verified", "ime_path_exercised"):
        require(guest, key, True)
    require(guest, "pid1", "systemd")
    require(guest, "content_surface_limit", 1)
    require(guest, "runtime_ready_sha256", digest(artifact_file(root, "d2i/qemu/runtime-ready.json")))
    require(guest, "recovery_screenshot_sha256", digest(artifact_file(root, "d2i/qemu/servo-content-recovered.png")))
    require(boot, "schema", "trillionnium.desktop.d2i-qemu-boot-result.v1")
    require(boot, "status", "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE")
    require(boot, "prepared_image_sha256", receipt.get("integrated_image_sha256"))
    require(boot, "network", "none")
    require(boot, "clean_poweroff", True)
    require(boot, "qemu_exit_status", 0)
    for key, relative in {
        "serial_log_sha256": "d2i/qemu/serial.log",
        "guest_acceptance_sha256": "d2i/qemu/guest-acceptance.json",
        "runtime_ready_sha256": "d2i/qemu/runtime-ready.json",
        "recovery_screenshot_sha256": "d2i/qemu/servo-content-recovered.png",
    }.items():
        require(boot, key, digest(artifact_file(root, relative)))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    receipt = verify_artifact(args.artifact)
    print(json.dumps({
        "status": "PASS",
        "verified_outputs": len(receipt["output_digests"]),
        "source_inputs": receipt["source"]["entry_count"],
        "tested_sha": receipt["tested_sha"],
        "image_sha256": receipt["integrated_image_sha256"],
        "promotion_authoritative": receipt["promotion_authoritative"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
