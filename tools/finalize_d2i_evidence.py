#!/usr/bin/env python3
"""Build a portable, path-stable D2I evidence bundle and receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

CHUNK = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f"missing or unsafe evidence file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--d1-artifact", type=Path, required=True)
    parser.add_argument("--d2i-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve()
    d1_artifact = args.d1_artifact.resolve()
    d2i = args.d2i_root.resolve()
    artifact = args.artifact_root.resolve()
    if artifact.exists():
        shutil.rmtree(artifact)
    artifact.mkdir(parents=True)

    if not (d1_artifact / "evidence/d1-final-qualification.json").is_file():
        raise SystemExit("canonical D1 artifact is absent")
    shutil.copytree(d1_artifact, artifact / "d1", dirs_exist_ok=True)

    d2i_files = {
        "integrated/preparation-a.json": d2i / "integrated/preparation-a.json",
        "integrated/preparation-b.json": d2i / "integrated/preparation-b.json",
        "integrated/image-sha256.txt": d2i / "integrated/image-sha256.txt",
        "runtime/runtime-transformation.json": d2i / "evidence/runtime-transformation.json",
        "runtime/boot-runner-transformation.json": d2i / "evidence/boot-runner-transformation.json",
        "runtime/headed-runtime.sha256": d2i / "headed-runtime.sha256",
        "qemu/boot-result.json": d2i / "qemu/boot-result.json",
        "qemu/guest-acceptance.json": d2i / "qemu/guest-acceptance.json",
        "qemu/runtime-ready.json": d2i / "qemu/runtime-ready.json",
        "qemu/servo-content-recovered.png": d2i / "qemu/servo-content-recovered.png",
        "qemu/runtime-journal.txt": d2i / "qemu/runtime-journal.txt",
        "qemu/qemu-command.txt": d2i / "qemu/qemu-command.txt",
        "qemu/serial.log": d2i / "qemu/serial.log",
        "qemu/preparation.json": d2i / "evidence/qemu/preparation.json",
        "qemu/selection.json": d2i / "evidence/qemu/selection.json"
    }
    for relative, source in d2i_files.items():
        copy_file(source, artifact / "d2i" / relative)

    source_dir = artifact / "source"
    source_dir.mkdir(parents=True)
    source_tar = source_dir / "source.tar"
    with source_tar.open("wb") as stream:
        subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=repository,
            stdout=stream,
            check=True,
        )
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=repository).split(b"\0")
    entries = []
    for raw in paths:
        if not raw:
            continue
        relative = raw.decode("utf-8")
        path = repository / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"tracked source is absent or unsafe: {relative}")
        entries.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    source_manifest = {
        "schema": "trillionnium.desktop.d2i-source-inputs.v1",
        "tree_sha": os.environ["TESTED_TREE_SHA"],
        "entry_count": len(entries),
        "entries": entries,
    }
    source_manifest_path = source_dir / "source-input-digests.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    d1_receipt = load(artifact / "d1/evidence/d1-final-qualification.json")
    prep_a = load(artifact / "d2i/integrated/preparation-a.json")
    prep_b = load(artifact / "d2i/integrated/preparation-b.json")
    boot = load(artifact / "d2i/qemu/boot-result.json")
    guest = load(artifact / "d2i/qemu/guest-acceptance.json")
    runtime = load(artifact / "d2i/qemu/runtime-ready.json")
    transform = load(artifact / "d2i/runtime/runtime-transformation.json")
    runner_transform = load(artifact / "d2i/runtime/boot-runner-transformation.json")

    assert d1_receipt["status"] == "PASS_D1_FINAL_QUALIFICATION"
    assert prep_a["status"] == "PASS_DETERMINISTIC_INPUT_INJECTION"
    assert prep_b["status"] == "PASS_DETERMINISTIC_INPUT_INJECTION"
    assert prep_a["integrated_image_sha256"] == prep_b["integrated_image_sha256"]
    assert boot["status"] == "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE"
    assert guest["status"] == "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE"
    assert runtime["status"] == "PASS_HEADED_SERVO_NATIVE_CHROME_SINGLE_CONTENT_RECOVERY"
    assert runtime["actual_content_process_crash_proven"] is True
    assert runtime["crash_callback_required"] is False
    assert runtime["zero_content_processes_after_termination"] is True
    assert runtime["replacement_process_distinct"] is True
    assert transform["callback_required"] is False
    assert runner_transform["callback_required"] is False

    receipt_path = artifact / "evidence/d2i-final-qualification.json"
    receipt_path.parent.mkdir(parents=True)
    output_digests = {}
    for path in sorted(artifact.rglob("*")):
        if not path.is_file() or path == receipt_path:
            continue
        relative = path.relative_to(artifact).as_posix()
        output_digests[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    receipt = {
        "schema": "trillionnium.desktop.d2i-final-qualification.v1",
        "status": "PASS_D2I_EXACT_IMAGE_CANDIDATE",
        "repository": os.environ["GITHUB_REPOSITORY"],
        "event_name": os.environ["GITHUB_EVENT_NAME"],
        "ref": os.environ["GITHUB_REF"],
        "ref_name": os.environ["GITHUB_REF_NAME"],
        "evidence_role": os.environ["EVIDENCE_ROLE"],
        "promotion_authoritative": os.environ["PROMOTION_AUTHORITATIVE"] == "true",
        "base_sha": os.environ["BASE_SHA"],
        "candidate_head_sha": os.environ["CANDIDATE_HEAD_SHA"],
        "tested_sha": os.environ["TESTED_SHA"],
        "tree_sha": os.environ["TESTED_TREE_SHA"],
        "workflow_sha256": sha256(repository / ".github/workflows/d2i-integrated-image.yml"),
        "servo_commit": os.environ["SERVO_COMMIT"],
        "source": {
            "archive_sha256": sha256(source_tar),
            "manifest_sha256": sha256(source_manifest_path),
            "entry_count": len(entries),
        },
        "d1_receipt_sha256": sha256(artifact / "d1/evidence/d1-final-qualification.json"),
        "runtime_transformation_sha256": sha256(
            artifact / "d2i/runtime/runtime-transformation.json"
        ),
        "boot_runner_transformation_sha256": sha256(
            artifact / "d2i/runtime/boot-runner-transformation.json"
        ),
        "integrated_image_sha256": prep_a["integrated_image_sha256"],
        "output_digests": output_digests,
        "claims": {
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
        },
        "claim_ceiling": {
            "browser_actor": False,
            "product_agent_port_enabled": False,
            "external_effects": False,
            "secure_boot": False,
            "hardware_readiness": False,
            "signed_update": False,
            "release_readiness": False,
        },
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": receipt["status"],
        "outputs": len(output_digests),
        "source_inputs": len(entries),
        "image_sha256": receipt["integrated_image_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
