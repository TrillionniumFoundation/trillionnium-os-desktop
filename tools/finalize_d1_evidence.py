#!/usr/bin/env python3
"""Validate D1 results and stage one strict, portable evidence artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

CHUNK_BYTES = 1024 * 1024
MAX_RAW_EVIDENCE_BYTES = 4 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require_true(mapping: dict[str, Any], key: str) -> None:
    if mapping.get(key) is not True:
        raise ValueError(f"required true field {key!r} is absent: {mapping}")


def require_false(mapping: dict[str, Any], key: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"required false field {key!r} is absent: {mapping}")


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"required evidence file is absent or unsafe: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def copy_optional_bounded(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_size <= MAX_RAW_EVIDENCE_BYTES:
        shutil.copyfile(source, destination)
        return
    with source.open("rb") as stream:
        stream.seek(-MAX_RAW_EVIDENCE_BYTES, os.SEEK_END)
        data = stream.read()
    destination.with_suffix(destination.suffix + ".tail").write_bytes(data)


def tracked_source_manifest(repository: Path) -> dict[str, Any]:
    encoded = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=repository
    )
    names = sorted(
        (item.decode("utf-8") for item in encoded.split(b"\0") if item),
        key=os.fsencode,
    )
    files: dict[str, str] = {}
    for name in names:
        path = repository / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"tracked source input is absent or unsafe: {name}")
        files[name] = sha256(path)
    canonical = json.dumps(files, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return {
        "schema": "trillionnium.desktop.source-input-digests.v1",
        "file_count": len(files),
        "files_sha256": hashlib.sha256(canonical).hexdigest(),
        "files": files,
    }


def rootfs_entries(path: Path) -> dict[str, dict[str, Any]]:
    document = load_json(path)
    if document.get("schema") != "trillionnium.desktop.d1-rootfs-manifest.v1":
        raise ValueError(f"unexpected rootfs manifest schema: {path}")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"rootfs manifest entries are not a list: {path}")
    output: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"invalid rootfs manifest entry: {path}")
        name = entry["path"]
        if name in output:
            raise ValueError(f"duplicate rootfs path {name!r}: {path}")
        output[name] = entry
    if document.get("entry_count") != len(output):
        raise ValueError(f"rootfs manifest entry count is inconsistent: {path}")
    return output


def validate_results(root: Path) -> dict[str, Any]:
    evidence = root / "evidence"
    pipeline = load_json(root / "pipeline-result.json")
    reproducibility = load_json(root / "reproducibility-result.json")
    boot = load_json(root / "qemu/boot-result.json")
    acceptance = load_json(root / "qemu/acceptance.json")
    host_tool = load_json(evidence / "e2fsprogs-host-tool-result.json")
    product_check = load_json(evidence / "product-daemon-self-check-host.json")
    qualification_check = load_json(
        evidence / "d1-qualification-self-check-host.json"
    )
    host_environment = load_json(evidence / "host-toolchain.json")

    if pipeline.get("status") != "PASS":
        raise ValueError("D1 pipeline is not a pass")
    if reproducibility.get("status") != "PASS_TWO_INDEPENDENT_BUILDS":
        raise ValueError("D1 same-run reproducibility result is not a pass")
    require_true(reproducibility, "reproducible")
    if boot.get("status") != "PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT":
        raise ValueError("D1 QEMU boot result is not a pass")
    if acceptance.get("schema") != "trillionnium.desktop.d1-acceptance.v2":
        raise ValueError("D1 acceptance result has the wrong schema")
    if acceptance.get("status") != "PASS":
        raise ValueError("D1 acceptance result is not a pass")
    if host_tool.get("status") != "PASS_PINNED_ISOLATED_HOST_TOOL":
        raise ValueError("pinned e2fsprogs result is not a pass")
    require_true(product_check, "ok")
    require_false(product_check, "product_handler_connected")
    require_false(product_check, "fixture_handler_linked")
    if qualification_check.get("status") != "PASS":
        raise ValueError("D1 qualification fixture self-check is not a pass")
    require_true(qualification_check, "qualification_only")
    require_false(qualification_check, "product_handler_connected")
    if host_environment.get("schema") != "trillionnium.desktop.d1-host-toolchain.v1":
        raise ValueError("D1 host toolchain evidence has the wrong schema")

    claims = boot.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("D1 boot claims are absent")
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
        require_true(claims, key)
    for key in (
        "network_enabled",
        "servo_started",
        "visible_window_created",
        "secure_boot_qualified",
    ):
        require_false(claims, key)
    require_true(boot, "release_marker_absent")
    require_true(boot, "clean_poweroff")

    agent = acceptance.get("agent_port")
    if not isinstance(agent, dict):
        raise ValueError("D1 acceptance AgentPort evidence is absent")
    for key in (
        "qualification_only_server",
        "product_daemon_fixture_free",
        "marker_removed_before_poweroff",
        "socket_removed_before_poweroff",
    ):
        require_true(agent, key)
    require_false(agent, "product_handler_connected")
    require_false(agent, "product_daemon_exercised_for_requests")
    if agent.get("qualification_server_exec") != (
        "/usr/libexec/hepta-agent-d1-fixture --mode server"
    ):
        raise ValueError("D1 qualification server command is not exact")

    return {
        "pipeline": pipeline,
        "reproducibility": reproducibility,
        "boot": boot,
        "acceptance": acceptance,
        "host_tool": host_tool,
        "host_environment": host_environment,
        "product_check": product_check,
        "qualification_check": qualification_check,
    }


def validate_workflow(repository: Path) -> dict[str, str]:
    workflow = repository / ".github/workflows/d1-final-qualification.yml"
    text = workflow.read_text(encoding="utf-8")
    trigger = text.split("\npermissions:\n", 1)[0]
    if "paths:" in trigger or "paths-ignore:" in trigger:
        raise ValueError("permanent D1 promotion workflow must not use path filters")
    for marker in ("pull_request:", "push:", "branches: [main]"):
        if marker not in trigger:
            raise ValueError(f"permanent D1 workflow lacks trigger marker {marker!r}")
    if "permissions:\n  contents: read" not in text:
        raise ValueError("permanent D1 workflow is not read-only")
    if "git push" in text or "gh workflow run" in text:
        raise ValueError("permanent D1 workflow contains branch mutation")
    return {
        "path": str(workflow.relative_to(repository)),
        "sha256": sha256(workflow),
    }


def stage_artifact(
    repository: Path,
    root: Path,
    artifact: Path,
    results: dict[str, Any],
) -> None:
    if artifact.exists():
        shutil.rmtree(artifact)
    artifact.mkdir(parents=True)

    source_manifest = tracked_source_manifest(repository)
    source_manifest_path = artifact / "evidence/source-input-digests.json"
    source_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    canonical_files = {
        root / "pipeline-result.json": artifact / "pipeline/pipeline-result.json",
        root / "reproducibility-result.json": artifact
        / "reproducibility/reproducibility-result.json",
        root / "qemu/boot-result.json": artifact / "qemu/boot-result.json",
        root / "qemu/acceptance.json": artifact / "qemu/acceptance.json",
        root / "prepared/prepared-inputs.json": artifact
        / "inputs/prepared-inputs.json",
        root / "prepared/expected-package-lock.tsv": artifact
        / "inputs/expected-package-lock.tsv",
        root / "build-a/candidate/artifacts/build-result.json": artifact
        / "builds/build-a/build-result.json",
        root / "build-a/candidate/artifacts/package-lock.tsv": artifact
        / "builds/build-a/package-lock.tsv",
        root / "build-a/candidate/artifacts/rootfs-content-manifest.json": artifact
        / "builds/build-a/rootfs-content-manifest.json",
        root / "build-b/candidate/artifacts/build-result.json": artifact
        / "builds/build-b/build-result.json",
        root / "build-b/candidate/artifacts/package-lock.tsv": artifact
        / "builds/build-b/package-lock.tsv",
        root / "build-b/candidate/artifacts/rootfs-content-manifest.json": artifact
        / "builds/build-b/rootfs-content-manifest.json",
        root / "evidence/e2fsprogs-host-tool-result.json": artifact
        / "evidence/e2fsprogs-host-tool-result.json",
        root / "evidence/host-toolchain.json": artifact
        / "evidence/host-toolchain.json",
        root / "evidence/product-cargo-tree.txt": artifact
        / "evidence/product-cargo-tree.txt",
        root / "evidence/qualification-cargo-tree.txt": artifact
        / "evidence/qualification-cargo-tree.txt",
        root / "evidence/product-daemon-self-check-host.json": artifact
        / "evidence/product-daemon-self-check-host.json",
        root / "evidence/d1-qualification-self-check-host.json": artifact
        / "evidence/d1-qualification-self-check-host.json",
    }
    for source, destination in canonical_files.items():
        copy_file(source, destination)

    raw_root = root / "evidence"
    if raw_root.is_dir():
        for source in sorted(raw_root.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            if source.name == "d1-final-qualification.json":
                continue
            copy_optional_bounded(
                source,
                artifact / "raw-evidence" / source.relative_to(raw_root),
            )

    product_binary = repository / "target/release/hepta-agent-portd"
    qualification_binary = repository / "target/release/hepta-agent-d1-fixture"
    binary_digests = {
        "schema": "trillionnium.desktop.d1-binary-digests.v1",
        "product": {
            "path": "target/release/hepta-agent-portd",
            "sha256": sha256(product_binary),
            "bytes": product_binary.stat().st_size,
        },
        "qualification": {
            "path": "target/release/hepta-agent-d1-fixture",
            "sha256": sha256(qualification_binary),
            "bytes": qualification_binary.stat().st_size,
        },
    }
    for build in ("build-a", "build-b"):
        manifest_path = (
            root
            / build
            / "candidate/artifacts/rootfs-content-manifest.json"
        )
        entries = rootfs_entries(manifest_path)
        product_entry = entries.get("./usr/libexec/hepta-agent-portd")
        qualification_entry = entries.get("./usr/libexec/hepta-agent-d1-fixture")
        if product_entry is None or product_entry.get("sha256") != binary_digests[
            "product"
        ]["sha256"]:
            raise ValueError(f"{build} product binary digest is not bound to rootfs")
        if qualification_entry is None or qualification_entry.get(
            "sha256"
        ) != binary_digests["qualification"]["sha256"]:
            raise ValueError(
                f"{build} qualification binary digest is not bound to rootfs"
            )
    binary_path = artifact / "evidence/binary-digests.json"
    binary_path.write_text(
        json.dumps(binary_digests, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    workflow = validate_workflow(repository)
    role = os.environ.get("EVIDENCE_ROLE")
    ref = os.environ.get("SOURCE_REF")
    authoritative_text = os.environ.get("PROMOTION_AUTHORITATIVE")
    if role not in {"pr_synthetic_merge", "exact_main_push", "manual_non_authoritative"}:
        raise ValueError(f"invalid D1 evidence role: {role!r}")
    if authoritative_text not in {"true", "false"}:
        raise ValueError("PROMOTION_AUTHORITATIVE is not canonical boolean text")
    authoritative = authoritative_text == "true"
    if role == "exact_main_push":
        if ref != "refs/heads/main" or not authoritative:
            raise ValueError("exact-main role is not bound to authoritative main")
    elif authoritative:
        raise ValueError("non-main D1 evidence is marked authoritative")

    output_digests: dict[str, str] = {}
    receipt_relative = Path("evidence/d1-final-qualification.json")
    for path in sorted(artifact.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact)
        if relative == receipt_relative:
            continue
        output_digests[relative.as_posix()] = sha256(path)

    receipt = {
        "schema": "trillionnium.desktop.d1-final-qualification.v3",
        "status": "PASS",
        "repository": os.environ["GITHUB_REPOSITORY"],
        "event_name": os.environ["GITHUB_EVENT_NAME"],
        "ref": ref,
        "ref_name": os.environ.get("SOURCE_REF_NAME"),
        "evidence_role": role,
        "promotion_authoritative": authoritative,
        "tested_topology": os.environ["TESTED_TOPOLOGY"],
        "base_sha": os.environ["BASE_SHA"],
        "candidate_head_sha": os.environ["CANDIDATE_HEAD_SHA"],
        "tested_sha": os.environ["TESTED_SHA"],
        "tree_sha": os.environ["TESTED_TREE_SHA"],
        "workflow": workflow,
        "runner_sha256": sha256(
            repository / "tools/run_d1_final_qualification.sh"
        ),
        "workflow_run_id": os.environ["GITHUB_RUN_ID"],
        "workflow_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "source_input_manifest_sha256": sha256(source_manifest_path),
        "source_input_files_sha256": source_manifest["files_sha256"],
        "source_input_count": source_manifest["file_count"],
        "output_digests": output_digests,
        "product_fixture_separation": {
            "product_default_graph_fixture_free": True,
            "qualification_feature": "d1-qualification",
            "qualification_binary": "hepta-agent-d1-fixture",
            "qualification_server_exec": results["acceptance"]["agent_port"][
                "qualification_server_exec"
            ],
            "product_handler_connected": False,
            "production_install_map_contains_qualification_binary": False,
        },
        "host_tool": results["host_tool"],
        "host_environment": results["host_environment"],
        "pipeline": results["pipeline"],
        "reproducibility": results["reproducibility"],
        "reproducibility_scope": {
            "same_run_two_build_byte_identity": True,
            "cross_run_identity_claimed": False,
            "hermetic_host_environment_claimed": False,
        },
        "boot": results["boot"],
        "acceptance": results["acceptance"],
        "claim_ceiling": {
            "servo_started": False,
            "visible_window_created": False,
            "network_enabled_during_acceptance": False,
            "secure_boot_qualified": False,
            "product_agent_port_enabled": False,
            "product_release_authorized": False,
        },
    }
    receipt_path = artifact / receipt_relative
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()

    repository = args.repository.resolve()
    root = args.root.resolve()
    artifact = args.artifact_root.resolve()
    if not repository.is_dir() or not (repository / ".git").exists():
        raise SystemExit("repository path is not a Git worktree")
    if not root.is_dir() or root.is_symlink():
        raise SystemExit("D1 output root is missing or unsafe")
    results = validate_results(root)
    stage_artifact(repository, root, artifact, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
