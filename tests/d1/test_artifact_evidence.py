"""Adversarial checks for portable D1/D2I qualification evidence."""
from __future__ import annotations

import hashlib
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

SOURCE_FILES = {
    "src.txt": b"source",
    ".github/workflows/d1-final-qualification.yml": b"fixture D1 workflow\n",
    ".github/workflows/d2i-integrated-image.yml": b"fixture D2I workflow\n",
    ".github/workflows/s10-production-debian-qemu.yml": b"fixture manual S10 workflow\n",
}


def workflow_binding(name: str, *, tested_sha: str = "b" * 40) -> dict:
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
    files = {name: hashlib.sha256(payload).hexdigest() for name, payload in SOURCE_FILES.items()}
    aggregate = hashlib.sha256(json.dumps(files, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    manifest = write(root, "evidence/source-input-digests.json", {
        "schema": "trillionnium.desktop.source-input-digests.v1", "files": files,
        "file_count": len(files), "files_sha256": aggregate,
    })
    receipt = {
        "schema": "trillionnium.desktop.d1-final-qualification.v3", "status": "PASS",
        "repository": "TrillionniumFoundation/trillionnium-os-desktop",
        "event_name": "push", "ref": "refs/heads/main", "evidence_role": "exact_main_push",
        "promotion_authoritative": True, "base_sha": "a" * 40,
        "candidate_head_sha": "b" * 40, "tested_sha": "b" * 40, "tree_sha": "c" * 40,
        "source_input_manifest_sha256": evidence.digest(manifest),
        "source_input_files_sha256": aggregate, "source_input_count": len(files),
        "producer_workflow": workflow_binding(producer),
        "workflow": {key: value for key, value in workflow_binding("d1-final-qualification.yml").items() if key in {"path", "sha256"}},
        **documents,
    }
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
        "page_input_verified", "ime_path_exercised",
    )}
    runtime.update({"status": "PASS_HEADED_SERVO_NATIVE_CHROME_SINGLE_CONTENT_RECOVERY",
                    "crash_callback_required": False, "external_network_used": False,
                    "content_surface_limit": 1, "content_generation": 2,
                    "popup_requests_denied": 1, "external_navigation_requests_denied": 1,
                    "content_process_pid": 10, "content_process_start_time_ticks": 100,
                    "replacement_content_process_pid": 11, "replacement_content_process_start_time_ticks": 200})
    write(root, "d2i/qemu/runtime-ready.json", runtime)
    guest = {key: True for key in (
        "actual_content_process_crash_proven", "sigkill_delivered", "exact_old_identity_absent",
        "zero_process_intermediate", "replacement_identity_distinct", "popup_denied",
        "external_navigation_denied", "product_agent_port_default_disabled", "product_agent_port_socket_absent",
    )}
    guest.update({"schema": "trillionnium.desktop.d2i-guest-acceptance.v2",
                  "status": "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE", "crash_callback_required": False,
                  "network_enabled": False, "release_ready": False})
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
            real_open = evidence.open_regular_beneath

            def after_component(index: int, component: str, descriptor: int) -> None:
                if component == "evidence":
                    original.parent.rename(root / "saved")
                    original.parent.symlink_to(root / "outside", target_is_directory=True)

            def swapped_open(*args, **kwargs):
                return real_open(*args, **kwargs, after_component=after_component)

            with patch.object(evidence, "open_regular_beneath", swapped_open):
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
                expected = workflow_binding(name)
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
