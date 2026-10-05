"""Adversarial checks for portable D1/D2I qualification evidence."""
from __future__ import annotations

import hashlib
from functools import lru_cache
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
import artifact_evidence as evidence
import verify_d1_artifact as d1
import verify_d2i_artifact as d2i
import finalize_d1_evidence as finalize_d1
import d1_source_provenance as provenance

SOURCE_FILES = {
    "src.txt": b"source",
    ".github/workflows/d1-final-qualification.yml": b"fixture D1 workflow\n",
    ".github/workflows/d2i-integrated-image.yml": b"fixture D2I workflow\n",
    ".github/workflows/s10-production-debian-qemu.yml": b"fixture manual S10 workflow\n",
}


@lru_cache(maxsize=1)
def fixture_git_tree() -> str:
    """Use Git itself as the independent oracle for fixture bytes and modes."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, payload in SOURCE_FILES.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            path.chmod(0o644)
        git = ["git", "-c", "user.name=Evidence test", "-c", "user.email=evidence@example.invalid"]
        subprocess.run([*git, "init", "-q"], cwd=root, check=True)
        subprocess.run([*git, "add", "--", *SOURCE_FILES], cwd=root, check=True)
        return subprocess.check_output([*git, "write-tree"], cwd=root, text=True).strip()


@lru_cache(maxsize=1)
def fixture_git_commit() -> tuple[str, bytes]:
    """Actual native Git commit fixture; no disk or guest qualification claim."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        payload = (f"tree {fixture_git_tree()}\n"
                   "author Evidence test <evidence@example.invalid> 1 +0000\n"
                   "committer Evidence test <evidence@example.invalid> 1 +0000\n\n"
                   "SOURCE_FIXTURE_ONLY\n").encode()
        result = subprocess.run(["git", "hash-object", "-t", "commit", "--stdin"], cwd=root,
                                input=payload, capture_output=True, check=True)
        return result.stdout.decode().strip(), payload


def fixture_d1_source_proof(root: Path, receipt: dict) -> None:
    (root / "source").mkdir(exist_ok=True)
    with tarfile.open(root / provenance.ARCHIVE, "w") as archive:
        for name, payload in SOURCE_FILES.items():
            member = tarfile.TarInfo(name)
            member.mode, member.size = 0o644, len(payload)
            archive.addfile(member, io.BytesIO(payload))
    (root / provenance.COMMIT).write_bytes(fixture_git_commit()[1])
    receipt["source_provenance"] = {
        "schema": "trillionnium.desktop.d1-source-provenance.v1",
        "archive_sha256": evidence.digest(root / provenance.ARCHIVE),
        "commit_sha256": evidence.digest(root / provenance.COMMIT),
    }


def workflow_binding(name: str, *, tested_sha: str | None = None) -> dict:
    if tested_sha is None:
        tested_sha = fixture_git_commit()[0]
    path = f".github/workflows/{name}"
    return {"path": path, "ref": f"TrillionniumFoundation/trillionnium-os-desktop/{path}@refs/heads/main",
            "workflow_sha": tested_sha,
            "sha256": hashlib.sha256(SOURCE_FILES[path]).hexdigest()}


def write(root: Path, relative: str, value: object) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def bind(root: Path, receipt: dict, relative: str, *, sized: bool) -> None:
    receipt["output_digests"] = {
        path.relative_to(root).as_posix(): (
            {"sha256": evidence.digest(path), "bytes": path.stat().st_size}
            if sized else evidence.digest(path)
        ) for path in root.rglob("*") if path.is_file() and path != root / relative
    }
    write(root, relative, receipt)


def complete_d1_metadata_fixture(root: Path, documents: dict) -> None:
    """Internally consistent source decoder metadata, never actual disk/guest evidence."""
    import d1_evidence_semantics as semantics
    lock = b"fixture-package\t1.0\tall\n"
    lock_sha = hashlib.sha256(lock).hexdigest()
    write(root, "inputs/prepared-inputs.json", {"schema": "trillionnium.desktop.d1-prepared-inputs.v2",
        "status": "PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK", "package_count": 1, "package_set_sha256": "d" * 64,
        "source_date_epoch": 1, "selection_sha256": "c" * 64, "expected_package_lock_sha256": lock_sha,
        "claims": {key: False for key in ("agent_port_activated", "disk_image_created", "product_ready", "qemu_booted",
            "rootfs_created", "servo_started", "wayland_started")}})
    (root / "inputs/expected-package-lock.tsv").write_bytes(lock)
    binary = {"schema": "trillionnium.desktop.d1-binary-digests.v1",
        "product": {"path": "target/release/hepta-agent-portd", "sha256": "a" * 64, "bytes": 10},
        "qualification": {"path": "target/release/examples/hepta-agent-d1-fixture", "sha256": "b" * 64, "bytes": 20}}
    write(root, "evidence/binary-digests.json", binary)
    (root / "evidence/product-cargo-tree.txt").write_text("hepta-agent-portd v0.1.0\nhepta-agent-transport v0.1.0\n")
    (root / "evidence/qualification-cargo-tree.txt").write_text("hepta-agent-portd v0.1.0\nhepta-agent-port v0.1.0\nhepta-browser-codec v0.1.0\n")
    (root / "raw-evidence").mkdir()
    (root / "raw-evidence/product-daemon.strings").write_bytes(b"SOURCE_FIXTURE_PRODUCT_STRINGS_ONLY\n")
    (root / "raw-evidence/qualification-fixture.strings").write_bytes(b"SOURCE_FIXTURE_ONLY qualification_only product_handler_connected\n")
    entries = [{"path": path, "type": "file", "mode": "0755", "uid": 0, "gid": 0,
        "nlink": 1, "size": binary[key]["bytes"], "sha256": binary[key]["sha256"], "mtime_ns": 1, "xattrs": {}}
        for key, path in (("product", "./usr/libexec/hepta-agent-portd"), ("qualification", "./usr/libexec/hepta-agent-d1-fixture"))]
    entries.extend({"path": path, "type": "directory", "mode": "0755", "uid": 0, "gid": 0,
        "nlink": 1, "size": 0, "mtime_ns": 1, "xattrs": {}}
        for path in (".", "./usr", "./usr/libexec"))
    manifest = {"schema": "trillionnium.desktop.d1-rootfs-manifest.v1", "entries": entries,
        "entry_count": len(entries), "entries_sha256": hashlib.sha256(semantics.canonical(entries)).hexdigest()}
    for build in ("build-a", "build-b"):
        prefix = f"builds/{build}/"
        manifest_path = write(root, prefix + "rootfs-content-manifest.json", manifest)
        (root / prefix / "package-lock.tsv").write_bytes(lock)
        result = {"schema": "trillionnium.desktop.d1-build-result.v2", "status": "PASS_BUILD_ONLY", "image_id": "SOURCE_FIXTURE_ONLY",
            "source_date_epoch": 1, "selection_sha256": "c" * 64, "signed_package_set_sha256": "d" * 64,
            "prepared_manifest_sha256": evidence.digest(root / "inputs/prepared-inputs.json"),
            "package_lock": {"path": "package-lock.tsv", "sha256": lock_sha, "entries": 1},
            "rootfs_manifest": {"path": "rootfs-content-manifest.json", "sha256": evidence.digest(manifest_path),
                "entries": len(entries), "entries_sha256": manifest["entries_sha256"]},
            "rootfs_tar": {"path": "rootfs.tar", "sha256": "f" * 64},
            "image": {"path": "trillionnium-d1.ext4", "sha256": "e" * 64, "bytes": 42},
            "kernel": {"path": "vmlinuz", "sha256": "1" * 64}, "initrd": {"path": "initrd.img", "sha256": "2" * 64},
            "release_marker_present": False, "network_during_acceptance": False, "qemu_booted": False}
        write(root, prefix + "build-result.json", result)
    comparisons = {}
    for index, name in enumerate(semantics.ARTIFACTS):
        field = {"package-lock.tsv": "package_lock", "rootfs-content-manifest.json": "rootfs_manifest", "rootfs.tar": "rootfs_tar",
            "trillionnium-d1.ext4": "image", "vmlinuz": "kernel", "initrd.img": "initrd"}[name]
        size = 42 if name == "trillionnium-d1.ext4" else 100 + index
        if name in {"package-lock.tsv", "rootfs-content-manifest.json"}: size = (root / "builds/build-a" / name).stat().st_size
        comparisons[name] = {"equal": True, "first_sha256": result[field]["sha256"], "second_sha256": result[field]["sha256"],
            "first_bytes": size, "second_bytes": size}
    documents["pipeline"].update(schema="trillionnium.desktop.d1-pipeline-result.v2", failed_stage=None,
        started_unix=1, finished_unix=2, stages={name: {"status": "PASS", "exit_code": 0} for name in semantics.STAGES},
        authority={key: False for key in ("qemu_network_enabled", "release_qualified", "secure_boot_qualified", "servo_started", "visible_window_created")})
    repro_claims = {key: True for key in ("two_build_rootfs_manifest_match", "two_build_rootfs_match", "two_build_ext4_match", "two_build_kernel_match", "two_build_initrd_match")}
    repro_claims.update(qemu_booted=False, servo_started=False, product_ready=False)
    documents["reproducibility"].update(schema="trillionnium.desktop.d1-reproducibility-result.v3", invariant_mismatches=[],
        package_count=1, prepared_inputs_sha256=result["prepared_manifest_sha256"], signed_package_set_sha256="d" * 64,
        claims=repro_claims, artifact_comparisons=comparisons, rootfs_manifest_diff={"equal": True,
            "first_entry_count": len(entries), "second_entry_count": len(entries), "missing_from_first_count": 0, "missing_from_second_count": 0,
            "changed_count": 0, "difference_count": 0, "report_truncated": False, "missing_from_first": [], "missing_from_second": [], "changed": []})
    documents["acceptance"].update(image_id="SOURCE_FIXTURE_ONLY", package_lock_sha256=lock_sha,
        package_set_sha256="d" * 64, network_enabled=False, pid1="systemd", systemd="active", udev="active",
        dbus="active", logind="active", wayland_compositor="active")
    documents["acceptance"]["agent_port"].update({key: True for key in ("default_disabled", "unauthorized_peer_denied",
        "authorized_request_completed", "per_connection_teardown", "connection_kill_recovered", "marker_created_at_runtime_only")})
    documents["acceptance"]["agent_port"]["product_self_check_sha256"] = evidence.digest(root / "evidence/product-daemon-self-check-host.json")
    acceptance_path = write(root, "qemu/acceptance.json", documents["acceptance"])
    documents["boot"].update(schema="trillionnium.desktop.d1-qemu-boot-result.v2", qemu_exit_status=0, network="none",
        pre_boot_image_sha256="e" * 64, package_lock_sha256=lock_sha, guest_acceptance_sha256=evidence.digest(acceptance_path))
    for key, name in (("pipeline", "pipeline/pipeline-result.json"), ("reproducibility", "reproducibility/reproducibility-result.json"),
                      ("boot", "qemu/boot-result.json")):
        write(root, name, documents[key])


def d1_fixture(root: Path, *, producer: str = "d1-final-qualification.yml") -> dict:
    claims = {key: True for key in (
        "systemd_booted", "udev_active", "dbus_active", "logind_active",
        "headless_wayland_active", "agent_port_default_disabled",
        "agent_port_pid1_activation_validated", "unauthorized_peer_denied",
        "authorized_fixture_request", "per_connection_teardown", "connection_kill_recovered",
    )}
    claims.update({key: False for key in (
        "network_enabled", "servo_started", "visible_window_created", "secure_boot_qualified",
    )})
    documents = {
        "pipeline": {"status": "PASS"},
        "reproducibility": {"status": "PASS_TWO_INDEPENDENT_BUILDS", "reproducible": True},
        "boot": {"status": "PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT", "claims": claims,
                 "release_marker_absent": True, "clean_poweroff": True},
        "acceptance": {"schema": "trillionnium.desktop.d1-acceptance.v2", "status": "PASS",
                       "agent_port": {"qualification_only_server": True,
                                      "product_daemon_fixture_free": True,
                                      "marker_removed_before_poweroff": True,
                                      "socket_removed_before_poweroff": True,
                                      "product_handler_connected": False,
                                      "product_daemon_exercised_for_requests": False,
                                      "qualification_server_exec": "/usr/libexec/hepta-agent-d1-fixture --mode server"}},
        "host_tool": {"status": "PASS_PINNED_ISOLATED_HOST_TOOL"},
        "host_environment": {"schema": "trillionnium.desktop.d1-host-toolchain.v1"},
    }
    paths = {
        "pipeline": "pipeline/pipeline-result.json",
        "reproducibility": "reproducibility/reproducibility-result.json",
        "boot": "qemu/boot-result.json", "acceptance": "qemu/acceptance.json",
        "host_tool": "evidence/e2fsprogs-host-tool-result.json",
        "host_environment": "evidence/host-toolchain.json",
    }
    for field, relative in paths.items():
        write(root, relative, documents[field])
    write(root, "evidence/product-daemon-self-check-host.json", {
        "ok": True, "product_handler_connected": False, "fixture_handler_linked": False,
    })
    write(root, "evidence/d1-qualification-self-check-host.json", {
        "status": "PASS", "qualification_only": True, "product_handler_connected": False,
    })
    complete_d1_metadata_fixture(root, documents)
    files = {name: hashlib.sha256(payload).hexdigest() for name, payload in SOURCE_FILES.items()}
    aggregate = hashlib.sha256(json.dumps(files, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    manifest = write(root, "evidence/source-input-digests.json", {
        "schema": "trillionnium.desktop.source-input-digests.v1", "files": files,
        "file_count": len(files), "files_sha256": aggregate,
    })
    receipt = {
        "schema": "trillionnium.desktop.d1-final-qualification.v4", "status": "PASS",
        "repository": "TrillionniumFoundation/trillionnium-os-desktop",
        "event_name": "push", "ref": "refs/heads/main", "evidence_role": "exact_main_push",
        "promotion_authoritative": True, "base_sha": "0" * 40,
        "candidate_head_sha": fixture_git_commit()[0], "tested_sha": fixture_git_commit()[0], "tree_sha": fixture_git_tree(),
        "source_input_manifest_sha256": evidence.digest(manifest),
        "source_input_files_sha256": aggregate, "source_input_count": len(files),
        "claim_ceiling": {key: False for key in (
            "servo_started", "visible_window_created", "network_enabled_during_acceptance",
            "secure_boot_qualified", "product_agent_port_enabled", "product_release_authorized",
        )},
        "producer_workflow": workflow_binding(producer),
        "workflow": {key: value for key, value in workflow_binding("d1-final-qualification.yml").items() if key in {"path", "sha256"}},
        **documents,
        "product_fixture_separation": {
            "product_default_graph_fixture_free": True, "qualification_feature": "fixture", "qualification_binary": "hepta-agent-d1-fixture",
            "qualification_server_exec": "/usr/libexec/hepta-agent-d1-fixture --mode server",
            "product_handler_connected": False, "production_install_map_contains_qualification_binary": False,
        },
        "reproducibility_scope": {"same_run_two_build_byte_identity": True, "cross_run_identity_claimed": False,
            "hermetic_host_environment_claimed": False},
    }
    fixture_d1_source_proof(root, receipt)
    bind(root, receipt, d1.RECEIPT_PATH.as_posix(), sized=False)
    return receipt


def d2i_fixture(root: Path) -> dict:
    d1_receipt = d1_fixture(root / "d1", producer="d2i-integrated-image.yml")
    receipt = {key: d1_receipt[key] for key in (
        "repository", "event_name", "ref", "evidence_role", "promotion_authoritative",
        "base_sha", "candidate_head_sha", "tested_sha", "tree_sha", "producer_workflow",
    )}
    receipt.update({"schema": "trillionnium.desktop.d2i-final-qualification.v1",
                    "status": "PASS_D2I_EXACT_IMAGE_CANDIDATE",
                    "servo_commit": "e" * 40, "integrated_image_sha256": "d" * 64,
                    "workflow_sha256": workflow_binding("d2i-integrated-image.yml")["sha256"]})
    receipt["claims"] = {key: True for key in (
        "same_exact_image_contains_d1_and_headed_servo", "systemd_pid1", "headless_wayland",
        "single_content_surface", "image_local_servo_input_dispatch",
        "native_host_input_inherited_from_d0a02_only", "popup_denied", "external_navigation_denied",
        "sigkill_exact_identity", "zero_process_intermediate", "distinct_replacement_identity",
        "product_agent_port_default_disabled",
    )}
    receipt["claims"].update({"crash_callback_required": False, "network_device_present": False})
    receipt["claim_ceiling"] = {key: False for key in (
        "browser_actor", "product_agent_port_enabled", "external_effects", "secure_boot",
        "hardware_readiness", "signed_update", "release_readiness",
    )}
    prep = {"schema": "trillionnium.desktop.d2i-image-preparation.v1",
            "status": "PASS_DETERMINISTIC_INPUT_INJECTION", "integrated_image_sha256": "d" * 64,
            "servo_revision": "e" * 40}
    write(root, "d2i/integrated/preparation-a.json", prep)
    write(root, "d2i/integrated/preparation-b.json", prep)
    for name, key in (("runtime", "runtime_transformation_sha256"), ("boot-runner", "boot_runner_transformation_sha256")):
        path = write(root, f"d2i/runtime/{name}-transformation.json", {"callback_required": False})
        receipt[key] = evidence.digest(path)
    runtime = {key: True for key in (
        "actual_content_process_crash_proven", "signal_sent", "content_process_termination_observed",
        "zero_content_processes_after_termination", "replacement_process_distinct",
        "page_input_verified", "ime_path_exercised", "trusted_chrome_survived_recovery",
    )}
    runtime.update({"status": "PASS_HEADED_SERVO_NATIVE_CHROME_SINGLE_CONTENT_RECOVERY",
                    "crash_callback_required": False, "external_network_used": False,
                    "content_surface_limit": 1, "content_generation": 2,
                    "frame_count": 2, "ime_composition_events_sent": 3,
                    "simulated_content_process_recovery": False,
                    "input_events_sent": 15, "input_events_handled": 3,
                    "popup_requests_denied": 1, "external_navigation_requests_denied": 1,
                    "content_process_pid": 10, "content_process_start_time_ticks": 100,
                    "replacement_content_process_pid": 11, "replacement_content_process_start_time_ticks": 200})
    write(root, "d2i/qemu/runtime-ready.json", runtime)
    guest = {key: True for key in (
        "actual_content_process_crash_proven", "sigkill_delivered", "exact_old_identity_absent",
        "zero_process_intermediate", "replacement_identity_distinct", "popup_denied",
        "external_navigation_denied", "product_agent_port_default_disabled", "product_agent_port_socket_absent",
        "udev_active", "dbus_active", "logind_active", "headless_wayland_active",
        "headed_servo_runtime_completed", "trusted_chrome_survived_recovery",
        "page_input_verified", "ime_path_exercised",
    )}
    guest.update({"schema": "trillionnium.desktop.d2i-guest-acceptance.v2",
                  "status": "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE", "crash_callback_required": False,
                  "network_enabled": False, "release_ready": False,
                  "pid1": "systemd", "content_surface_limit": 1})
    write(root, "d2i/qemu/guest-acceptance.json", guest)
    old = {"pid": 10, "start_time_ticks": 100}
    new = {"pid": 11, "start_time_ticks": 200}
    write(root, "d2i/qemu/content-process-identity.json", {"generation": 1, **old})
    write(root, "d2i/qemu/content-sigkill-sent.json", {"generation": 1, "signal": "SIGKILL", **old})
    for phase, identities in (("pre-fault", [old]), ("post-termination", []), ("post-recovery", [new])):
        write(root, f"d2i/qemu/process-topology-{phase}.json", {
            "embedder_pid": 5, "active_process_count": len(identities), "processes": identities,
        })
    for relative in ("d2i/qemu/serial.log", "d2i/qemu/servo-content-recovered.png"):
        path = root / relative
        path.write_bytes(b"fixture")
    guest["runtime_ready_sha256"] = evidence.digest(root / "d2i/qemu/runtime-ready.json")
    guest["recovery_screenshot_sha256"] = evidence.digest(root / "d2i/qemu/servo-content-recovered.png")
    write(root, "d2i/qemu/guest-acceptance.json", guest)
    boot = {"schema": "trillionnium.desktop.d2i-qemu-boot-result.v1",
            "status": "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE", "prepared_image_sha256": "d" * 64,
            "network": "none", "clean_poweroff": True, "qemu_exit_status": 0}
    for key, relative in {
        "serial_log_sha256": "d2i/qemu/serial.log", "guest_acceptance_sha256": "d2i/qemu/guest-acceptance.json",
        "runtime_ready_sha256": "d2i/qemu/runtime-ready.json", "recovery_screenshot_sha256": "d2i/qemu/servo-content-recovered.png",
    }.items():
        boot[key] = evidence.digest(root / relative)
    write(root, "d2i/qemu/boot-result.json", boot)
    source = write(root, "source/source-input-digests.json", {
        "schema": "trillionnium.desktop.d2i-source-inputs.v1", "tree_sha": receipt["tree_sha"], "entry_count": len(SOURCE_FILES),
        "entries": [{"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()} for name, payload in SOURCE_FILES.items()],
    })
    archive_path = root / "source/source.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name, payload in SOURCE_FILES.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    receipt["source"] = {"archive_sha256": evidence.digest(archive_path), "manifest_sha256": evidence.digest(source), "entry_count": len(SOURCE_FILES)}
    receipt["d1_receipt_sha256"] = evidence.digest(root / "d1/evidence/d1-final-qualification.json")
    bind(root, receipt, d2i.RECEIPT, sized=True)
    return receipt


def rebind_runtime_fixture(root: Path, receipt: dict, runtime: dict) -> None:
    """Rewrite source-only fixture bytes and every affected complete-pack hash."""
    runtime_path = write(root, "d2i/qemu/runtime-ready.json", runtime)
    guest = evidence.load(root / "d2i/qemu/guest-acceptance.json")
    guest["runtime_ready_sha256"] = evidence.digest(runtime_path)
    guest_path = write(root, "d2i/qemu/guest-acceptance.json", guest)
    boot = evidence.load(root / "d2i/qemu/boot-result.json")
    boot["runtime_ready_sha256"] = evidence.digest(runtime_path)
    boot["guest_acceptance_sha256"] = evidence.digest(guest_path)
    write(root, "d2i/qemu/boot-result.json", boot)
    bind(root, receipt, d2i.RECEIPT, sized=True)


class ArtifactEvidenceTests(unittest.TestCase):
    def test_current_d1_v3_and_complete_d2i_bundle_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            d2i_fixture(root)
            self.assertEqual(d1.verify_artifact(root / "d1")["status"], "PASS")
            self.assertEqual(d2i.verify_artifact(root)["status"], "PASS_D2I_EXACT_IMAGE_CANDIDATE")

    def test_digest_map_cannot_omit_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            del receipt["output_digests"]["d2i/qemu/runtime-ready.json"]
            write(root, d2i.RECEIPT, receipt)
            with self.assertRaisesRegex(ValueError, "inventory"):
                d2i.verify_artifact(root)

    def test_absolute_traversal_and_noncanonical_output_paths_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            payload.write_bytes(b"outside")
            for path in (str(payload), "../payload", "./payload", "a//payload", "a/../payload"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    evidence.verify_outputs(root, "receipt", {path: evidence.digest(payload)}, sized=False)

    def test_symlink_ancestors_and_receipt_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "real"
            d1_fixture(root)
            link = root.parent / "link"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                d1.verify_artifact(link)
            original = root / d1.RECEIPT_PATH
            target = original.with_name("saved.json")
            original.rename(target)
            original.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                d1.verify_artifact(root)

    def test_duplicate_json_fields_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt"
            path.write_text('{"status":"FAIL","status":"PASS"}')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                evidence.load(path)

    def test_nonfinite_json_numbers_and_oversized_json_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt"
            for payload in ('{"number":NaN}', '{"number":Infinity}', '{"number":1e999}'):
                path.write_text(payload)
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    evidence.load(path)
            with path.open("wb") as stream:
                stream.truncate(evidence.MAX_JSON_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "byte bound"):
                evidence.load(path)

    def test_nonregular_and_hardlinked_authority_files_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            original.write_text('{}')
            link = root / "hardlink"
            os.link(original, link)
            with self.assertRaisesRegex(ValueError, "hard link"):
                evidence.load(link)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, "regular file"):
                evidence.load(fifo)

    def test_unlisted_special_files_cannot_hide_from_the_artifact_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            d1_fixture(root)
            os.mkfifo(root / "undeclared-fifo")
            with self.assertRaisesRegex(ValueError, "special file"):
                d1.verify_artifact(root)

    def test_parent_symlink_swap_cannot_redirect_a_pinned_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = write(root, "bundle/evidence/receipt.json", {"status": "original"})
            write(root, "outside/receipt.json", {"status": "attacker"})
            real_open = evidence.open_managed_regular_beneath

            def after_component(index: int, component: str, descriptor: int) -> None:
                if component == "evidence":
                    original.parent.rename(root / "saved")
                    original.parent.symlink_to(root / "outside", target_is_directory=True)

            def swapped_open(*args, **kwargs):
                return real_open(*args, **kwargs, after_component=after_component)

            with patch.object(evidence, "open_managed_regular_beneath", swapped_open):
                self.assertEqual(evidence.load(original)["status"], "original")
            with self.assertRaisesRegex(ValueError, "symlinked"):
                evidence.load(original)

    def test_d2i_refuses_receipt_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            receipt["tested_sha"] = "f" * 40
            receipt["candidate_head_sha"] = "f" * 40
            write(root, d2i.RECEIPT, receipt)
            with self.assertRaisesRegex(ValueError, "candidate_head_sha"):
                d2i.verify_artifact(root)

    def test_d2i_refuses_nonzero_intermediate_with_rebound_digests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            write(root, "d2i/qemu/process-topology-post-termination.json", {
                "embedder_pid": 5, "active_process_count": 1, "processes": [{"pid": 10, "start_time_ticks": 100}],
            })
            bind(root, receipt, d2i.RECEIPT, sized=True)
            with self.assertRaisesRegex(ValueError, "active_process_count"):
                d2i.verify_artifact(root)

    def test_d2i_refuses_unproven_chrome_survival_with_rebound_digests(self) -> None:
        field = "trusted_chrome_survived_recovery"
        for replacement in ({}, {field: False}, {field: 0}, {field: 1}, {field: "true"}, {field: None}):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                runtime = evidence.load(root / "d2i/qemu/runtime-ready.json")
                runtime.pop(field)
                runtime.update(replacement)
                rebind_runtime_fixture(root, receipt, runtime)
                with self.assertRaisesRegex(ValueError, field):
                    d2i.verify_artifact(root)

    def test_d2i_refuses_wrong_sent_count_or_type_with_rebound_digests(self) -> None:
        field = "input_events_sent"
        for replacement in ({}, {field: 14}, {field: 16}, {field: True}, {field: 15.0}, {field: "15"}, {field: None}):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                runtime = evidence.load(root / "d2i/qemu/runtime-ready.json")
                runtime.pop(field)
                runtime.update(replacement)
                rebind_runtime_fixture(root, receipt, runtime)
                with self.assertRaisesRegex(ValueError, field):
                    d2i.verify_artifact(root)

    def test_d2i_refuses_insufficient_handled_count_or_type_with_rebound_digests(self) -> None:
        field = "input_events_handled"
        for replacement in ({}, {field: 0}, {field: 2}, {field: True}, {field: 3.0}, {field: "3"}, {field: None}):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                runtime = evidence.load(root / "d2i/qemu/runtime-ready.json")
                runtime.pop(field)
                runtime.update(replacement)
                rebind_runtime_fixture(root, receipt, runtime)
                with self.assertRaisesRegex(ValueError, field):
                    d2i.verify_artifact(root)

    def test_d2i_refuses_nested_float_process_identities_after_full_rebinding(self) -> None:
        for phase in ("pre-fault", "post-recovery"):
            for field in ("pid", "start_time_ticks"):
                with self.subTest(phase=phase, field=field), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    receipt = d2i_fixture(root)
                    relative = f"d2i/qemu/process-topology-{phase}.json"
                    topology = evidence.load(root / relative)
                    topology["processes"][0][field] = float(topology["processes"][0][field])
                    write(root, relative, topology)
                    bind(root, receipt, d2i.RECEIPT, sized=True)
                    with self.assertRaisesRegex(ValueError, "processes"):
                        d2i.verify_artifact(root)

    def test_d2i_refuses_unproved_ime_frames_and_simulated_recovery_after_full_rebinding(self) -> None:
        for field, values in (
            ("ime_composition_events_sent", (None, 0, True, 3.0, "3", 2, 4)),
            ("frame_count", (None, 0, 1, True, 2.0, "2")),
            ("simulated_content_process_recovery", (None, True, 0, "false")),
        ):
            for replacement in values:
                with self.subTest(field=field, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    receipt = d2i_fixture(root)
                    runtime = evidence.load(root / "d2i/qemu/runtime-ready.json")
                    runtime[field] = replacement
                    rebind_runtime_fixture(root, receipt, runtime)
                    with self.assertRaisesRegex(ValueError, field):
                        d2i.verify_artifact(root)

    def test_d2i_refuses_guest_fact_contradictions_after_full_rebinding(self) -> None:
        for field, replacement in (
            ("trusted_chrome_survived_recovery", False),
            ("headed_servo_runtime_completed", 1),
            ("page_input_verified", False),
            ("ime_path_exercised", False),
            ("pid1", "other"),
            ("content_surface_limit", 1.0),
            ("runtime_ready_sha256", "f" * 64),
            ("recovery_screenshot_sha256", "f" * 64),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                guest = evidence.load(root / "d2i/qemu/guest-acceptance.json")
                guest[field] = replacement
                guest_path = write(root, "d2i/qemu/guest-acceptance.json", guest)
                boot = evidence.load(root / "d2i/qemu/boot-result.json")
                boot["guest_acceptance_sha256"] = evidence.digest(guest_path)
                write(root, "d2i/qemu/boot-result.json", boot)
                bind(root, receipt, d2i.RECEIPT, sized=True)
                with self.assertRaisesRegex(ValueError, field):
                    d2i.verify_artifact(root)

    def test_d2i_refuses_fabricated_receipt_scope_even_with_complete_hashes(self) -> None:
        for section in ("claims", "claim_ceiling"):
            for operation in ("flip", "integer", "omit", "extra"):
                with self.subTest(section=section, operation=operation), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    receipt = d2i_fixture(root)
                    key = "release_readiness" if section == "claim_ceiling" else "systemd_pid1"
                    if operation == "flip":
                        receipt[section][key] = not receipt[section][key]
                    elif operation == "integer":
                        receipt[section][key] = int(receipt[section][key])
                    elif operation == "omit":
                        del receipt[section][key]
                    else:
                        receipt[section]["new_authority"] = True
                    bind(root, receipt, d2i.RECEIPT, sized=True)
                    with self.assertRaisesRegex(ValueError, section):
                        d2i.verify_artifact(root)

    def test_source_archive_must_match_manifest_even_after_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            archive_path = root / "source/source.tar"
            with tarfile.open(archive_path, "w") as archive:
                member = tarfile.TarInfo("src.txt")
                member.size = 6
                archive.addfile(member, io.BytesIO(b"tamper"))
            receipt["source"]["archive_sha256"] = evidence.digest(archive_path)
            bind(root, receipt, d2i.RECEIPT, sized=True)
            with self.assertRaisesRegex(ValueError, "archive differs"):
                d2i.verify_artifact(root)

    def test_source_tree_refuses_changed_bytes_with_all_inner_and_outer_digests_rebound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            entries = {name: payload + (b" altered" if name == "src.txt" else b"") for name, payload in SOURCE_FILES.items()}
            self._rewrite_source_archive_and_all_digests(root, receipt, entries)
            with self.assertRaisesRegex(ValueError, "declared Git tree"):
                d2i.verify_artifact(root)

    def test_source_tree_refuses_changed_executable_mode_with_complete_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            self._rewrite_source_archive_and_all_digests(root, receipt, SOURCE_FILES, executable="src.txt")
            with self.assertRaisesRegex(ValueError, "declared Git tree"):
                d2i.verify_artifact(root)

    def test_source_binding_refuses_nested_count_types_and_field_drift_after_complete_rebinding(self) -> None:
        for operation in ("float", "bool", "omit", "extra"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                if operation == "float":
                    receipt["source"]["entry_count"] = float(len(SOURCE_FILES))
                elif operation == "bool":
                    receipt["source"]["entry_count"] = True
                elif operation == "omit":
                    del receipt["source"]["entry_count"]
                else:
                    receipt["source"]["extra_authority"] = True
                bind(root, receipt, d2i.RECEIPT, sized=True)
                with self.assertRaisesRegex(ValueError, "source archive or manifest binding"):
                    d2i.verify_artifact(root)

    def test_d1_subreceipt_count_requires_exact_integer_after_complete_rebinding(self) -> None:
        for replacement in (float(len(SOURCE_FILES)), True, str(len(SOURCE_FILES)), None):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                nested = evidence.load(root / "d1" / d1.RECEIPT_PATH)
                nested["source_input_count"] = replacement
                self._rebind_d1_receipt(root, receipt, nested)
                with self.assertRaisesRegex(ValueError, "source aggregate or count"):
                    d1.verify_artifact(root / "d1")
                with self.assertRaisesRegex(ValueError, "source aggregate or count"):
                    d2i.verify_artifact(root)

    def test_d1_subreceipt_ceiling_is_closed_false_after_complete_rebinding(self) -> None:
        for field in ("servo_started", "visible_window_created", "network_enabled_during_acceptance",
                      "secure_boot_qualified", "product_agent_port_enabled", "product_release_authorized"):
            for replacement in (True, 0, None, "false"):
                with self.subTest(field=field, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    receipt = d2i_fixture(root)
                    nested = evidence.load(root / "d1" / d1.RECEIPT_PATH)
                    if replacement is None:
                        del nested["claim_ceiling"][field]
                    else:
                        nested["claim_ceiling"][field] = replacement
                    self._rebind_d1_receipt(root, receipt, nested)
                    with self.assertRaisesRegex(ValueError, "claim_ceiling"):
                        d1.verify_artifact(root / "d1")
                    with self.assertRaisesRegex(ValueError, "claim_ceiling"):
                        d2i.verify_artifact(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            nested = evidence.load(root / "d1" / d1.RECEIPT_PATH)
            nested["claim_ceiling"]["release_readiness"] = True
            self._rebind_d1_receipt(root, receipt, nested)
            with self.assertRaisesRegex(ValueError, "claim_ceiling"):
                d1.verify_artifact(root / "d1")
            with self.assertRaisesRegex(ValueError, "claim_ceiling"):
                d2i.verify_artifact(root)

    def test_d1_subreceipt_document_binding_preserves_nested_boolean_types(self) -> None:
        for field, replacement in (("systemd_booted", 1), ("network_enabled", 0)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = d2i_fixture(root)
                nested = evidence.load(root / "d1" / d1.RECEIPT_PATH)
                nested["boot"]["claims"][field] = replacement
                self._rebind_d1_receipt(root, receipt, nested)
                with self.assertRaisesRegex(ValueError, "bind staged boot"):
                    d1.verify_artifact(root / "d1")
                with self.assertRaisesRegex(ValueError, "bind staged boot"):
                    d2i.verify_artifact(root)

    @staticmethod
    def _rebind_d1_receipt(root: Path, receipt: dict, nested: dict) -> None:
        bind(root / "d1", nested, d1.RECEIPT_PATH.as_posix(), sized=False)
        receipt["d1_receipt_sha256"] = evidence.digest(root / "d1" / d1.RECEIPT_PATH)
        bind(root, receipt, d2i.RECEIPT, sized=True)

    @staticmethod
    def _rewrite_source_archive_and_all_digests(root: Path, receipt: dict, entries: dict[str, bytes], *, executable: str | None = None) -> None:
        archive_path = root / "source/source.tar"
        with tarfile.open(archive_path, "w") as archive:
            for name, payload in entries.items():
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                member.mode = 0o755 if name == executable else 0o644
                archive.addfile(member, io.BytesIO(payload))
        manifest = evidence.load(root / "source/source-input-digests.json")
        manifest["entries"] = [{"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()} for name, payload in entries.items()]
        manifest_path = write(root, "source/source-input-digests.json", manifest)
        d1_manifest = evidence.load(root / "d1/evidence/source-input-digests.json")
        d1_manifest["files"] = {name: hashlib.sha256(payload).hexdigest() for name, payload in entries.items()}
        d1_manifest["files_sha256"] = hashlib.sha256(json.dumps(d1_manifest["files"], separators=(",", ":"), sort_keys=True).encode()).hexdigest()
        d1_manifest_path = write(root, "d1/evidence/source-input-digests.json", d1_manifest)
        d1_receipt = evidence.load(root / "d1" / d1.RECEIPT_PATH)
        d1_receipt["source_input_manifest_sha256"] = evidence.digest(d1_manifest_path)
        d1_receipt["source_input_files_sha256"] = d1_manifest["files_sha256"]
        bind(root / "d1", d1_receipt, d1.RECEIPT_PATH.as_posix(), sized=False)
        receipt["d1_receipt_sha256"] = evidence.digest(root / "d1" / d1.RECEIPT_PATH)
        receipt["source"]["archive_sha256"] = evidence.digest(archive_path)
        receipt["source"]["manifest_sha256"] = evidence.digest(manifest_path)
        bind(root, receipt, d2i.RECEIPT, sized=True)

    def test_finalizer_never_deletes_overlapping_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            sentinel = source / "keep"
            sentinel.write_text("original")
            for destination in (source, source.parent, source / "bundle"):
                with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "overlaps"):
                    evidence.artifact_destination(destination, (source,))
            self.assertEqual(sentinel.read_text(), "original")

    def test_actual_producer_workflow_is_source_bound_for_all_three_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in SOURCE_FILES.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            source_files = {name: hashlib.sha256(payload).hexdigest() for name, payload in SOURCE_FILES.items()}
            for name in ("d1-final-qualification.yml", "d2i-integrated-image.yml", "s10-production-debian-qemu.yml"):
                expected = workflow_binding(name, tested_sha="b" * 40)
                with self.subTest(lane=name), patch.dict(os.environ, {"GITHUB_WORKFLOW_REF": expected["ref"], "GITHUB_WORKFLOW_SHA": "b" * 40, "TESTED_SHA": "b" * 40}):
                    actual = evidence.producer_workflow(root)
                    self.assertEqual(actual, expected)
                    evidence.verify_workflow_binding(actual, source_files, producer=True, tested_sha="b" * 40)
                    with self.assertRaisesRegex(ValueError, "source manifest"):
                        evidence.verify_workflow_binding({**actual, "sha256": "0" * 64}, source_files, producer=True, tested_sha="b" * 40)
                    with patch.dict(os.environ, {"GITHUB_WORKFLOW_SHA": "f" * 40}):
                        with self.assertRaisesRegex(ValueError, "executing workflow commit"):
                            evidence.producer_workflow(root)
                    malformed = {**actual, "ref": actual["ref"] + "@extra"}
                    with self.assertRaisesRegex(ValueError, "invalid workflow ref"):
                        evidence.verify_workflow_binding(malformed, source_files, producer=True, tested_sha="b" * 40)

    def test_semantic_refusal_survives_python_optimization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = d2i_fixture(root)
            receipt["promotion_authoritative"] = "true"
            write(root, d2i.RECEIPT, receipt)
            result = subprocess.run([sys.executable, "-O", str(TOOLS / "verify_d2i_artifact.py"), str(root)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("promotion_authoritative is not boolean", result.stderr)

    def test_installed_guest_numeric_checks_accept_complete_numbers(self) -> None:
        script = (TOOLS.parent / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance").read_text()
        helpers = "json_true() {" + script.split("json_true() {", 1)[1].split("\nsystemctl ", 1)[0]
        numeric_checks = "[[ $(json_uint content_surface_limit" + script.split("[[ $(json_uint content_surface_limit", 1)[1].split("\nfor key in", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime.json"
            command = ["bash", "-c", 'set -euo pipefail\nruntime=$1\nfail() { exit 9; }\n' + helpers + numeric_checks, "guest-check", str(runtime)]
            for frames in (2, 10, 19, 100):
                runtime.write_text(json.dumps({"content_surface_limit": 1, "content_generation": 2, "frame_count": frames}, indent=2))
                with self.subTest(frames=frames):
                    self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            for surface, generation, frames in ((10, 2, 10), (1, 20, 10), (1, 2, 1), (1.0, 2, 10)):
                runtime.write_text(json.dumps({"content_surface_limit": surface, "content_generation": generation, "frame_count": frames}, indent=2))
                with self.subTest(surface=surface, generation=generation, frames=frames):
                    self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_real_d2i_finalizer_accepts_current_d1_and_refuses_optimized_invalid_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            repository = workspace / "repository"
            repository.mkdir()
            for name, payload in SOURCE_FILES.items():
                path = repository / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "-c", "user.name=Evidence test", "-c", "user.email=evidence@example.invalid", "commit", "-qm", "fixture"], cwd=repository, check=True)
            tested = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True).strip()
            fixture = workspace / "fixture"
            d2i_fixture(fixture)
            canonical_d1 = fixture / "d1"
            receipt = evidence.load(canonical_d1 / d1.RECEIPT_PATH)
            source = finalize_d1.tracked_source_manifest(repository)
            source_path = write(canonical_d1, "evidence/source-input-digests.json", source)
            receipt.update({"tested_sha": tested, "candidate_head_sha": tested, "tree_sha": tree,
                            "source_input_manifest_sha256": evidence.digest(source_path),
                            "source_input_files_sha256": source["files_sha256"], "source_input_count": source["file_count"]})
            receipt["producer_workflow"]["workflow_sha"] = tested
            receipt["source_provenance"] = provenance.stage_source(repository, canonical_d1)
            bind(canonical_d1, receipt, d1.RECEIPT_PATH.as_posix(), sized=False)
            inputs = workspace / "inputs"
            shutil.copytree(fixture / "d2i", inputs)
            (inputs / "evidence").mkdir()
            for name in ("runtime", "boot-runner"):
                shutil.copyfile(inputs / f"runtime/{name}-transformation.json", inputs / f"evidence/{name}-transformation.json")
            for name in ("integrated/image-sha256.txt", "headed-runtime.sha256", "qemu/runtime-journal.txt", "qemu/qemu-command.txt", "evidence/qemu/preparation.json", "evidence/qemu/selection.json"):
                path = inputs / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n")
            artifact = workspace / "artifact"
            environment = {**os.environ, "TESTED_SHA": tested, "TESTED_TREE_SHA": tree,
                           "GITHUB_REPOSITORY": receipt["repository"], "GITHUB_EVENT_NAME": "push",
                           "GITHUB_REF": "refs/heads/main", "GITHUB_REF_NAME": "main",
                           "EVIDENCE_ROLE": "exact_main_push", "PROMOTION_AUTHORITATIVE": "true",
                           "BASE_SHA": receipt["base_sha"], "CANDIDATE_HEAD_SHA": tested,
                           "SERVO_COMMIT": "e" * 40,
                           "GITHUB_WORKFLOW_SHA": tested,
                           "GITHUB_WORKFLOW_REF": receipt["producer_workflow"]["ref"]}
            command = [sys.executable, str(TOOLS / "finalize_d2i_evidence.py"), "--repository", str(repository),
                       "--d1-artifact", str(canonical_d1), "--d2i-root", str(inputs), "--artifact-root", str(artifact)]
            for name, event, role, authoritative in (
                ("d2i-integrated-image.yml", "push", "exact_main_push", True),
                ("s10-production-debian-qemu.yml", "workflow_dispatch", "manual_non_authoritative", False),
            ):
                producer = workflow_binding(name, tested_sha=tested)
                receipt.update({"event_name": event, "evidence_role": role,
                                "promotion_authoritative": authoritative, "producer_workflow": producer})
                bind(canonical_d1, receipt, d1.RECEIPT_PATH.as_posix(), sized=False)
                environment.update({"GITHUB_EVENT_NAME": event, "EVIDENCE_ROLE": role,
                                    "PROMOTION_AUTHORITATIVE": str(authoritative).lower(),
                                    "GITHUB_WORKFLOW_REF": producer["ref"]})
                with self.subTest(lane=name):
                    completed = subprocess.run(command, env=environment, capture_output=True, text=True)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    verified = d2i.verify_artifact(artifact)
                    self.assertEqual(verified["tested_sha"], tested)
                    self.assertEqual(verified["producer_workflow"], producer)
            runtime = evidence.load(inputs / "qemu/runtime-ready.json")
            runtime["actual_content_process_crash_proven"] = False
            write(inputs, "qemu/runtime-ready.json", runtime)
            completed = subprocess.run([command[0], "-O", *command[1:]], env=environment, capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse((artifact / d2i.RECEIPT).exists())

    def test_finalization_source_identity_refuses_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.write_text("committed")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Evidence test", "-c", "user.email=evidence@example.invalid", "commit", "-qm", "fixture"], cwd=root, check=True)
            environment = {"TESTED_SHA": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                           "TESTED_TREE_SHA": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()}
            with patch.dict(os.environ, environment):
                evidence.validate_source_identity(root)
                source.write_text("changed")
                with self.assertRaisesRegex(ValueError, "differ from the tested Git tree"):
                    evidence.validate_source_identity(root)


if __name__ == "__main__":
    unittest.main()
