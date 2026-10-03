"""Actual OpenSSL, private filesystem, fork and interruption update readback."""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


readback = load("test_authenticated_update_readback_source", ROOT / "platform/authenticated_update_observer.py")
signed = readback.signed
fixture = load("test_authenticated_update_real_crypto_fixture", ROOT / "tests/test_durable_update_owner.py")
s11 = signed.recovery


def setUpModule():
    if sys.platform != "linux":
        raise RuntimeError("actual Linux OpenSSL, flock, procfs and fork are required; no skipped qualification")
    fixture.setUpModule()


def tearDownModule():
    fixture.tearDownModule()


class AuthenticatedUpdateReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="source-authenticated-update-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.state, self.slots = self.parent / "state", self.parent / "slots"
        self.state.mkdir(mode=0o700); self.slots.mkdir(mode=0o700)
        fixture.private_file(self.slots / "slot-A.img", fixture.SOURCE)
        fixture.private_file(self.slots / "slot-B.img", b"old inactive image")
        self.candidate = self.parent / "candidate"
        fixture.private_file(self.candidate, fixture.TARGET)
        self.clock = [fixture.NOW]
        self.owners = []
        self.addCleanup(self.release)

    def release(self):
        for value in self.owners:
            value._closed = True
            value._release_descriptors()

    def verifier(self, root=None):
        return s11.ExternalUpdateSignatureVerifier((fixture.TRUST if root is None else root,))

    def owner(self, kind=signed.AuthenticatedUpdateOwner, **changes):
        arguments = dict(active_slot="A", current_version=10, current_image_sha256=fixture.SOURCE_DIGEST,
            signature_verifier=self.verifier(), clock=lambda: self.clock[0])
        arguments.update(changes)
        value = kind(self.state, self.slots, **arguments)
        self.owners.append(value)
        return value

    def pending(self, *, kind=signed.AuthenticatedUpdateOwner, phase="boot_policy_armed", whitespace=False):
        value = self.owner(kind)
        self.payload, self.signature = fixture.manifest()
        if whitespace:
            self.payload = json.dumps(json.loads(self.payload), indent=2).encode() + b"\n"
        operation = value.verify_manifest(self.payload, now_unix=fixture.NOW, signature=self.signature)
        if phase not in {"manifest_verified", "stage_intent"}:
            value.stage_image_file(operation, self.candidate, now_unix=fixture.NOW)
        if phase == "boot_policy_armed":
            value.arm_first_boot(operation, now_unix=fixture.NOW)
        value._closed = True
        value._release_descriptors()
        return value

    def observe(self, **changes):
        options = dict(signature_verifier=self.verifier(), clock=lambda: self.clock[0], protected_rollback_floor=10)
        options.update(changes)
        return readback.inspect_authenticated_update(self.state, self.slots, **options)

    def capsule(self):
        paths = list(self.state.glob("update-signature-*.json"))
        self.assertEqual(len(paths), 1)
        return paths[0]

    def snapshot(self):
        result = {}
        for root in (self.state, self.slots):
            for path in root.iterdir():
                data = path.read_bytes()
                metadata = path.lstat()
                result[str(path)] = (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns, data)
        return result

    def assert_refused(self, value):
        data = json.loads(value.public_json())
        self.assertFalse(data["signatures_verified"])
        self.assertFalse(data["stored_slot_images_verified"])
        self.assertFalse(data["continuation_authorized"])
        self.assertFalse(data["booted_image_verified"])
        self.assertIn(value.status, {"recovery_required", "observation_unavailable", "pending_identity_unknown"})

    def rebuild(self, capsule_change=None, event_change=None):
        capsule_path = self.capsule()
        capsule = json.loads(capsule_path.read_bytes())
        if capsule_change:
            capsule_change(capsule)
        capsule_bytes = readback.observer._canonical(capsule)
        fixture.private_file(capsule_path, capsule_bytes)
        digest = readback.observer._ZERO
        for path in sorted(self.state.glob("update-event-*.json")):
            event = json.loads(path.read_bytes())
            event["previous_sha256"] = digest
            if event_change:
                event_change(event, capsule)
            if event["operation"] is not None:
                reference = event["operation"]["signature_capsule"]
                reference["sha256"] = hashlib.sha256(capsule_bytes).hexdigest()
                reference["manifest_bytes_sha256"] = hashlib.sha256(base64.b64decode(capsule["manifest_bytes_b64"])).hexdigest()
                reference["signature_sha256"] = hashlib.sha256(base64.b64decode(capsule["signature_bytes_b64"])).hexdigest()
            data = readback.observer._canonical(event)
            fixture.private_file(path, data)
            digest = hashlib.sha256(data).hexdigest()

    def test_exact_noncanonical_manifest_and_actual_signature_survive_readonly_restart(self):
        self.pending(whitespace=True)
        before, descriptors = self.snapshot(), fixture.fd_inventory()
        capsule = json.loads(self.capsule().read_bytes())
        self.assertEqual(base64.b64decode(capsule["manifest_bytes_b64"]), self.payload)
        self.assertEqual(base64.b64decode(capsule["signature_bytes_b64"]), self.signature)
        actual = s11.subprocess.run
        calls = []
        def observed(*args, **kwargs):
            calls.append((args[0], kwargs["pass_fds"]))
            return actual(*args, **kwargs)
        with patch.object(s11.subprocess, "run", side_effect=observed):
            value = self.observe()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], "/usr/bin/openssl")
        self.assertEqual(len(calls[0][1]), 3)
        public = json.loads(value.public_json())
        self.assertTrue(public["signatures_verified"])
        self.assertTrue(public["stored_slot_images_verified"])
        for field in ("booted_image_verified", "health_qualified", "continuation_authorized", "production_activation_enabled", "bootloader_effect_performed"):
            self.assertIs(public[field], False)
        private = json.loads(value.private_json())["diagnostic"]
        self.assertEqual(private["signature_sha256"], hashlib.sha256(self.signature).hexdigest())
        self.assertEqual(private["manifest_bytes_sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(private["stored_slot_images"]["B"]["sha256"], fixture.TARGET_DIGEST)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(descriptors, fixture.fd_inventory())
        self.assertEqual(stat.S_IMODE(self.capsule().stat().st_mode), 0o600)

    def test_legacy_v1_signature_digests_never_become_crypto_authority(self):
        self.pending(kind=signed.durable.DurableUpdateOwner)
        with patch.object(s11.subprocess, "run", side_effect=AssertionError("legacy hashes must not reach verifier")):
            value = self.observe()
        self.assert_refused(value)
        self.assertIn("legacy_detached_signature_unavailable", value.reason_codes)

    def test_legacy_clean_history_allows_new_v2_owner_but_not_old_pending_resume(self):
        previous = self.owner(signed.durable.DurableUpdateOwner)
        previous.close()
        self.pending()
        self.assertTrue(self.observe().signatures_verified)
        restarted = self.owner()
        self.assertEqual(restarted.phase, "recovery_required")
        self.assertFalse(restarted.inspect()["resume_or_replay_available"])
        restarted.close()
        self.assertTrue(self.observe().signatures_verified)
        self.assertEqual(self.observe().status, "recovery_required")

    def test_v1_readonly_observer_refuses_new_profile_instead_of_promoting_it(self):
        self.pending()
        value = readback.observer.inspect_pending_update(self.state, self.slots)
        self.assertFalse(json.loads(value.public_json())["continuation_authorized"])
        self.assertIn(value.status.value, {"observation_unavailable", "recovery_required"})

    def test_current_external_root_policy_must_match_recorded_policy(self):
        self.pending()
        changed = replace(fixture.TRUST, valid_until_unix=fixture.NOW + 20000)
        self.assert_refused(self.observe(signature_verifier=self.verifier(changed)))

    def test_missing_or_arbitrary_verifier_and_clock_are_refused(self):
        self.pending()
        for changes in ({"signature_verifier": None}, {"signature_verifier": lambda *_: True}, {"clock": None}):
            with self.subTest(changes=changes):
                self.assert_refused(self.observe(**changes))

    def test_floor_expiration_regression_and_invalid_clock_values_are_refused(self):
        self.pending()
        for changes in ({"protected_rollback_floor": 9}, {"protected_rollback_floor": 11},
                        {"protected_rollback_floor": True}, {"clock": lambda: fixture.NOW - 1},
                        {"clock": lambda: fixture.NOW + 1000}, {"clock": lambda: float("nan")}, {"clock": lambda: True}):
            with self.subTest(changes=changes):
                self.assert_refused(self.observe(**changes))

    def test_real_signature_failure_survives_rehashed_forged_complete_chain(self):
        self.pending()
        def changed(capsule):
            signature = bytearray(base64.b64decode(capsule["signature_bytes_b64"]))
            signature[0] ^= 1
            digest = hashlib.sha256(signature).hexdigest()
            manifest = json.loads(base64.b64decode(capsule["manifest_bytes_b64"]))
            manifest["signature_sha256"] = digest
            capsule["manifest_bytes_b64"] = base64.b64encode(readback.observer._canonical(manifest)).decode()
            capsule["signature_bytes_b64"] = base64.b64encode(signature).decode()
            capsule["signature_admission"]["signature_sha256"] = digest
        def event_change(event, capsule):
            operation = event["operation"]
            if operation is not None:
                operation["manifest"] = json.loads(base64.b64decode(capsule["manifest_bytes_b64"]))
                operation["signature_admission"] = capsule["signature_admission"]
                if event["stage_receipt"] is not None:
                    event["stage_receipt"]["signature_sha256"] = capsule["signature_admission"]["signature_sha256"]
                    event["stage_receipt"]["manifest_sha256"] = hashlib.sha256(readback.observer._canonical(operation["manifest"])).hexdigest()
        self.rebuild(changed, event_change)
        value = self.observe()
        self.assert_refused(value)
        self.assertIn("persisted_signature_or_image_refused", value.reason_codes)

    def test_capsule_configuration_operation_and_owner_crossbinding_are_closed(self):
        self.pending()
        original = self.capsule().read_bytes()
        for field, changed in (("owner_id", "f" * 64), ("operation_id", "e" * 64),
                               ("configuration", {"state_root_identity": [1, 2]}),
                               ("signature_admission", {"trust_policy_sha256": "c" * 64})):
            with self.subTest(field=field):
                fixture.private_file(self.capsule(), original)
                self.rebuild(lambda value: value.__setitem__(field, changed))
                self.assert_refused(self.observe())
        fixture.private_file(self.capsule(), original)

    def test_capsule_missing_symlink_hardlink_fifo_permission_and_size_refuse(self):
        self.pending()
        path = self.capsule()
        data = path.read_bytes()
        outside = self.parent / "external"
        fixture.private_file(outside, data)
        for kind in ("missing", "symlink", "hardlink", "fifo", "mode", "size"):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == "symlink": path.symlink_to(outside)
                elif kind == "hardlink": os.link(outside, path)
                elif kind == "fifo": os.mkfifo(path, 0o600)
                elif kind == "mode": fixture.private_file(path, data); path.chmod(0o644)
                elif kind == "size": fixture.private_file(path, b" " * (s11.MAX_STATE_BYTES + 1))
                self.assert_refused(self.observe())
                if path.exists() or path.is_symlink(): path.unlink()
                fixture.private_file(path, data)

    def test_same_bytes_capsule_inode_substitution_during_verification_refuses(self):
        self.pending()
        path = self.capsule()
        data = path.read_bytes()
        actual = s11.subprocess.run
        def substitute(*args, **kwargs):
            fixture.private_file(self.state / "temporary", data)
            os.replace(self.state / "temporary", path)
            return actual(*args, **kwargs)
        with patch.object(s11.subprocess, "run", side_effect=substitute):
            self.assert_refused(self.observe())

    def test_slot_replacement_and_inplace_change_during_crypto_refuse(self):
        self.pending()
        actual = s11.subprocess.run
        for slot in ("A", "B"):
            original = (self.slots / f"slot-{slot}.img").read_bytes()
            def substitute(*args, **kwargs):
                fixture.private_file(self.slots / f"slot-{slot}.img", b"changed slot")
                return actual(*args, **kwargs)
            with self.subTest(slot=slot), patch.object(s11.subprocess, "run", side_effect=substitute):
                self.assert_refused(self.observe())
            fixture.private_file(self.slots / f"slot-{slot}.img", original)

    def test_active_or_target_content_wrong_before_readback_refuses(self):
        self.pending()
        for slot in ("A", "B"):
            path = self.slots / f"slot-{slot}.img"
            data = path.read_bytes()
            fixture.private_file(path, b"invalid")
            self.assert_refused(self.observe())
            fixture.private_file(path, data)

    def test_owner_busy_is_readonly_refusal(self):
        self.pending()
        active = self.owner()
        before = self.snapshot()
        value = self.observe()
        self.assert_refused(value)
        self.assertIn("owner_busy", value.reason_codes)
        self.assertEqual(before, self.snapshot())
        active._release_descriptors()

    def test_source_stage_without_armed_policy_is_authenticated_but_never_resumed(self):
        self.pending(phase="stage_completed")
        value = self.observe()
        self.assertTrue(value.signatures_verified)
        self.assertFalse(json.loads(value.public_json())["continuation_authorized"])

    def test_manifest_verified_only_never_claims_complete_slot_readback(self):
        self.pending(phase="manifest_verified")
        self.assert_refused(self.observe())

    def test_no_signature_capsule_can_be_orphaned_into_authority(self):
        self.pending()
        for path in self.state.glob("update-event-*.json"):
            event = json.loads(path.read_bytes())
            if event["operation"] is not None:
                path.unlink()
        self.assert_refused(self.observe())
        with self.assertRaises(signed.durable.DurableRecoveryRequired):
            self.owner()

    def test_capsule_link_reference_change_between_event_phases_refuses(self):
        self.pending()
        last = sorted(self.state.glob("update-event-*.json"))[-1]
        event = json.loads(last.read_bytes())
        event["operation"]["signature_capsule"]["manifest_bytes_sha256"] = "a" * 64
        fixture.private_file(last, readback.observer._canonical(event))
        self.assert_refused(self.observe())

    def test_capsule_publication_interruption_preserves_evidence_without_replay(self):
        value = self.owner()
        payload, signature = fixture.manifest()
        def fault(point):
            if point == "after_atomic_replace":
                raise KeyboardInterrupt("private test interruption")
        with self.assertRaises(signed.durable.DurableRecoveryRequired):
            value.verify_manifest(payload, signature=signature, now_unix=fixture.NOW, fault=fault)
        self.assertEqual(value.phase, "recovery_required")
        value._closed = True; value._release_descriptors()
        self.assertTrue(list(self.state.glob("update-signature-*.json")))
        self.assert_refused(self.observe())

    def test_exact_byte_envelope_limit_refuses_before_capsule_publication(self):
        value = self.owner()
        payload, signature = fixture.manifest()
        oversized = payload + b" " * signed.MAX_EXACT_BYTES
        with self.assertRaises(signed.durable.DurableRecoveryRequired):
            value.verify_manifest(oversized, signature=signature, now_unix=fixture.NOW)
        self.assertEqual(list(self.state.glob("update-signature-*.json")), [])
        self.assertEqual(value.phase, "recovery_required")

    def test_readback_interrupt_closes_every_acquired_fd_and_never_writes(self):
        self.pending()
        before, inventory = self.snapshot(), fixture.fd_inventory()
        actual = os.pread
        triggered = []
        def interrupted(fd, size, offset):
            if "update-signature-" in os.readlink(f"/proc/self/fd/{fd}") and not triggered:
                triggered.append(True)
                raise KeyboardInterrupt("private capsule read interruption")
            return actual(fd, size, offset)
        with patch.object(readback.os, "pread", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.observe()
        self.assertTrue(triggered)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(inventory, fixture.fd_inventory())

    def test_actual_kernel_snapshot_and_descriptor_bound_images_remain_distinct(self):
        self.pending()
        value = self.observe()
        private = json.loads(value.private_json())["diagnostic"]
        self.assertEqual(private["kernel"]["boot_id"], Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        self.assertEqual(json.loads(value.public_json())["signed_boot_image_mapping"], "unknown")

    def test_result_constructor_copy_and_foreign_thread_are_refused(self):
        self.pending()
        value = self.observe()
        with self.assertRaises(TypeError):
            readback.AuthenticatedUpdateReadback("ready", (), True, True)
        with self.assertRaises(TypeError):
            replace(value, signatures_verified=True)
        errors = []
        def foreign():
            try: value.public_json()
            except s11.StateRefused: errors.append(True)
        thread = threading.Thread(target=foreign); thread.start(); thread.join(timeout=5)
        self.assertEqual(errors, [True])

    def test_fork_copied_readback_cannot_deliver_fact_and_cannot_release_parent_lease(self):
        self.pending()
        value = self.observe()
        active = self.owner()
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            try:
                try: value.public_json(); outcome = b"failed"
                except s11.StateRefused: outcome = b"refused"
                active.close()
                os.write(write_fd, outcome)
            finally:
                os.close(write_fd)
                os._exit(0)
        os.close(write_fd)
        try:
            self.assertTrue(select.select([read_fd], [], [], 5)[0])
            self.assertEqual(os.read(read_fd, 64), b"refused")
        finally:
            os.close(read_fd); os.waitpid(pid, 0)
        self.assertIn("owner_busy", self.observe().reason_codes)

    def test_final_clock_callback_cannot_substitute_retained_capsule(self):
        self.pending()
        calls = []
        def clock():
            calls.append(True)
            if len(calls) == 2:
                path = self.capsule()
                fixture.private_file(self.state / "replacement", path.read_bytes())
                os.replace(self.state / "replacement", path)
            return fixture.NOW
        self.assert_refused(self.observe(clock=clock))

    def test_final_clock_progress_accepts_monotonic_time_and_refuses_expired_or_regressed(self):
        self.pending()
        for end, accepted in ((fixture.NOW + 1, True), (fixture.NOW - 1, False), (fixture.NOW + 1000, False)):
            values = iter((fixture.NOW, end))
            value = self.observe(clock=lambda: next(values))
            self.assertEqual(value.signatures_verified, accepted)

    def test_contract_claim_and_api_profiles_are_closed(self):
        from tools import validate_platform_mechanisms as gate
        result = gate.validate(ROOT)
        self.assertFalse(result["qualification_changed"])
        contract = json.loads((ROOT / "contracts/authenticated-update.v2.json").read_bytes())
        self.assertEqual(contract["domains"]["signature"], "trillionnium.desktop.update-manifest-signature.v1\\0")
        self.assertEqual(contract["limits"]["record_bytes"], 65536)
        self.assertEqual(contract["limits"]["exact_manifest_bytes"], 16384)
        self.assertIs(contract["claims"]["production_activation_enabled"], False)
        self.assertIs(contract["claims"]["whole_directory_rollback_protection"], False)

    def profile_fixture(self, destination):
        from tools import validate_platform_mechanisms as gate
        paths = {gate.REGISTRY}
        registry = json.loads((ROOT / gate.REGISTRY).read_bytes())
        for module in registry["modules"]:
            paths.update(module[field] for field in ("implementation", "documentation", "contract", "tests"))
        for name, profile in (("manifests/update-observation.v1.json", gate._READONLY_OBSERVER_INDEX),
                              ("manifests/authenticated-update.v2.json", gate._AUTHENTICATED_UPDATE_INDEX)):
            paths.add(name)
            paths.update(profile[field] for field in ("documentation", "contract", "tests", "workflow"))
            if "implementations" in profile: paths.update(profile["implementations"])
            else: paths.update((profile["implementation"], profile["entrypoint"]))
        for relative in paths:
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, path)
        return gate

    def test_profile_refresh_cannot_promote_claims_change_domains_or_expand_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate = self.profile_fixture(root)
            path = root / "contracts/authenticated-update.v2.json"
            original = path.read_bytes()
            for section, field, changed in (("claims", "production_activation_enabled", True),
                                           ("claims", "whole_directory_rollback_protection", True),
                                           ("domains", "signature", "unsigned"),
                                           ("limits", "exact_signature_bytes", 65536)):
                with self.subTest(section=section, field=field):
                    value = json.loads(original); value[section][field] = changed
                    path.write_bytes(readback.observer._canonical(value))
                    with self.assertRaisesRegex(ValueError, "authenticated update profile"):
                        gate.validate(root, refresh=True)
            path.write_bytes(original)
            self.assertFalse(gate.validate(root)["qualification_changed"])

    def test_profile_partial_package_unregistered_module_and_public_api_drift_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate = self.profile_fixture(root)
            path = root / "platform/authenticated_update_observer.py"
            original = path.read_bytes()
            path.write_bytes(original + b"\ndef unsafe_resume(caller_health): return True\n")
            with self.assertRaisesRegex(ValueError, "API inventory drift"):
                gate.validate(root)
            path.write_bytes(original)
            (root / "manifests/authenticated-update.v2.json").unlink()
            with self.assertRaises((OSError, ValueError)):
                gate.validate(root)

    def test_actual_candidate_workflow_uses_identical_live_ref_body_and_non_skipping_corpus(self):
        from test_ci_pr_ref_identities import identity_body
        new = (ROOT / ".github/workflows/authenticated-update-readback.yml").read_text()
        previous = (ROOT / ".github/workflows/update-boot-observer.yml").read_text()
        self.assertEqual(identity_body(new, "actual-host-corpus"), identity_body(previous, "actual-host-corpus"))
        self.assertIn("('test_authenticated_update_readback.py', 37)", new)
        self.assertIn("result.testsRun != expected or result.skipped", new)

    def test_result_public_fields_are_also_foreign_thread_refused(self):
        self.pending()
        value = self.observe()
        outcomes = []
        def foreign():
            try: outcomes.append(value.signatures_verified)
            except s11.StateRefused: outcomes.append("refused")
        thread = threading.Thread(target=foreign); thread.start(); thread.join(timeout=5)
        self.assertEqual(outcomes, ["refused"])

    def test_live_owner_refuses_same_bytes_replaced_signature_capsule(self):
        value = self.owner()
        payload, signature = fixture.manifest()
        operation = value.verify_manifest(payload, signature=signature, now_unix=fixture.NOW)
        path = self.capsule()
        fixture.private_file(self.state / "replacement", path.read_bytes())
        os.replace(self.state / "replacement", path)
        with self.assertRaises(signed.durable.DurableRecoveryRequired):
            value.stage_image_file(operation, self.candidate, now_unix=fixture.NOW)
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"old inactive image")

    def test_unavailable_crypto_cannot_claim_authentication_or_mutate_evidence(self):
        self.pending()
        before = self.snapshot()
        with patch.object(s11.subprocess, "run", side_effect=OSError("private verifier unavailable")):
            self.assert_refused(self.observe())
        self.assertEqual(before, self.snapshot())

    def test_unclean_idle_owner_and_recovery_marker_are_never_no_pending_success(self):
        value = self.owner()
        value._closed = True; value._release_descriptors()
        result = self.observe()
        self.assertEqual(result.status, "recovery_required")
        self.assertIn("unfinished_owner", result.reason_codes)
        reopened = self.owner()
        reopened.close()
        result = self.observe()
        self.assertEqual(result.status, "recovery_required")
        self.assertIn("recovery_marker_present", result.reason_codes)

    def test_copied_state_or_slot_roots_cannot_rebind_original_operation(self):
        self.pending()
        for name in ("state", "slots"):
            with self.subTest(root=name):
                path = getattr(self, name)
                retained = self.parent / (name + "-retained")
                path.rename(retained)
                path.mkdir(mode=0o700)
                for source in retained.iterdir():
                    fixture.private_file(path / source.name, source.read_bytes())
                self.assert_refused(self.observe())
                shutil.rmtree(path)
                retained.rename(path)

    def test_symlinked_root_ancestor_and_second_capsule_are_refused(self):
        self.pending()
        alias = self.parent / "alias"
        alias.symlink_to(self.parent, target_is_directory=True)
        self.assert_refused(readback.inspect_authenticated_update(alias / "state", self.slots,
            signature_verifier=self.verifier(), clock=lambda: fixture.NOW, protected_rollback_floor=10))
        fixture.private_file(self.state / ("update-signature-" + "f" * 64 + ".json"), self.capsule().read_bytes())
        self.assert_refused(self.observe())

    def test_capsule_descriptor_close_effect_then_raise_does_not_close_reused_foreign_fd(self):
        self.pending()
        original = fixture.fd_inventory()
        outside = self.parent / "foreign-cleanup-file"
        fixture.private_file(outside, b"foreign descriptor must survive")
        actual_pread, actual_close, actual_open = os.pread, os.close, os.open
        captured, reused = [], []
        def pread(fd, size, offset):
            if "update-signature-" in os.readlink(f"/proc/self/fd/{fd}") and not captured:
                captured.append(fd)
            return actual_pread(fd, size, offset)
        def close(fd):
            if captured and fd == captured[0] and not reused:
                actual_close(fd)
                foreign = actual_open(outside, os.O_RDONLY | os.O_CLOEXEC)
                if foreign != fd:
                    os.dup2(foreign, fd)
                    actual_close(foreign)
                reused.append(fd)
                raise OSError("actual close completed; caller delivery interrupted")
            return actual_close(fd)
        try:
            with patch.object(readback.os, "pread", side_effect=pread), patch.object(readback.os, "close", side_effect=close), self.assertRaises(OSError):
                self.observe()
            self.assertEqual(len(reused), 1)
            self.assertEqual(actual_pread(reused[0], 64, 0), b"foreign descriptor must survive")
            remaining = fixture.fd_inventory()
            self.assertEqual({key: value for key, value in remaining.items() if key != reused[0]}, original)
        finally:
            for fd in reused:
                actual_close(fd)
