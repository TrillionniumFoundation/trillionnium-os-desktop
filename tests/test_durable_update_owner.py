from __future__ import annotations

from dataclasses import fields, replace
import gc
import errno
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_durable_update_source", ROOT / "platform/durable_update_owner.py")
owner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = owner
spec.loader.exec_module(owner)
s11 = owner.recovery
SOURCE = b"durable-source-image"
TARGET = b"durable-target-image"
SOURCE_DIGEST = hashlib.sha256(SOURCE).hexdigest()
TARGET_DIGEST = hashlib.sha256(TARGET).hexdigest()
NOW = 1_000_000
KEYS = None
TRUST = None


def command(arguments):
    return subprocess.run(["/usr/bin/openssl", *arguments], capture_output=True, check=True, env=s11.OPENSSL_ENV)


def setUpModule():
    global KEYS, TRUST
    if not Path("/usr/bin/openssl").is_file():
        raise RuntimeError("actual OpenSSL is required; unavailable crypto is not a skipped pass")
    KEYS = tempfile.TemporaryDirectory(prefix="durable-update-test-only-keys-")
    directory = Path(KEYS.name)
    for name in ("approved", "wrong"):
        command(["genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(directory / name)])
    public = command(["pkey", "-in", str(directory / "approved"), "-pubout"]).stdout
    TRUST = s11.UpdateTrustRoot("test:update", public, hashlib.sha256(public).hexdigest(), 10, 1, NOW + 10000)


def tearDownModule():
    if KEYS is not None:
        KEYS.cleanup()


def manifest(*, signer="approved", **changes):
    value = {"schema": s11.MANIFEST_SCHEMA, "repository": s11.REPOSITORY,
        "source_version": 10, "source_image_sha256": SOURCE_DIGEST, "target_version": 11,
        "target_slot": "B", "target_image_sha256": TARGET_DIGEST, "target_image_bytes": len(TARGET),
        "rollback_floor": 10, "expires_unix": NOW + 1000, "signer_id": "test:update", "signature_sha256": "0" * 64}
    value.update(changes)
    directory = Path(KEYS.name)
    # Independent producer uses the documented literal domain and canonical form.
    unsigned = {key: data for key, data in value.items() if key != "signature_sha256"}
    preimage = b"trillionnium.desktop.update-manifest-signature.v1\0" + json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    (directory / "message").write_bytes(preimage)
    signature = command(["dgst", "-sha256", "-sign", str(directory / signer), str(directory / "message")]).stdout
    value["signature_sha256"] = hashlib.sha256(signature).hexdigest()
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode(), signature


def private_file(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


def fd_inventory():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            result[int(name)] = os.readlink(f"/proc/self/fd/{name}")
        except FileNotFoundError:
            pass  # The inventory directory's own descriptor already closed.
    return result


class DurableUpdateOwnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="durable-update-state-")
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.state, self.slots = root / "state", root / "slots"
        self.state.mkdir(mode=0o700); self.slots.mkdir(mode=0o700)
        private_file(self.slots / "slot-A.img", SOURCE)
        private_file(self.slots / "slot-B.img", b"previous-inactive-image")
        self.candidate = root / "candidate.img"
        private_file(self.candidate, TARGET)
        self.clock = [NOW]
        self.owners = []
        self.addCleanup(self.release)

    def release(self):
        for item in self.owners:
            item._release_descriptors()

    def create(self, *, trust=TRUST, disabled=False, **changes):
        verifier = None if disabled else s11.ExternalUpdateSignatureVerifier((TRUST if trust is None else trust,))
        options = {"active_slot": "A", "current_version": 10, "current_image_sha256": SOURCE_DIGEST,
            "signature_verifier": verifier, "protected_rollback_floor": 10, "clock": lambda: self.clock[0]}
        options.update(changes)
        item = owner.DurableUpdateOwner(self.state, self.slots, **options)
        self.owners.append(item)
        return item

    def admitted(self, item):
        payload, signature = manifest()
        return item.verify_manifest(payload, now_unix=NOW, signature=signature)

    def events(self):
        return [json.loads(path.read_bytes()) for path in sorted(self.state.glob("update-event-*.json"))]

    def _assert_private_image_consumer_detaches(self, item, invoke, *, source=False, slot="slot-A.img"):
        target = s11 if source else item._slots
        method = "_open_image" if source else "_open_slot"
        actual_open = getattr(target, method)
        actual_close, raw_open = os.close, os.open
        captured, foreign, closed = [], [], []
        def opened(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            if not captured and (source or args[1] == slot):
                captured.append(descriptor.fileno())
            return descriptor
        def close_reuse(number):
            number = int(number)
            name = os.readlink(f"/proc/self/fd/{number}")
            closed.append(name)
            actual_close(number)
            if captured and number == captured[0] and not foreign:
                replacement = raw_open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                if replacement != number:
                    os.dup2(replacement, number, inheritable=False)
                    actual_close(replacement)
                foreign.append(number)
        try:
            with patch.object(target, method, side_effect=opened), patch.object(os, "close", side_effect=close_reuse):
                result = invoke()
                gc.collect()
            # The old os.close(owner) call is also retained in a spy's argument
            # history; collect after removing that spy to expose its pending GC.
            gc.collect()
            self.assertEqual(len(captured), 1)
            self.assertEqual(foreign, captured)
            self.assertTrue(stat.S_ISCHR(os.fstat(foreign[0]).st_mode))
            self.assertNotIn("/dev/null", closed, "consumer left an owner armed after closing its number")
            return result
        finally:
            for number in foreign:
                try:
                    if stat.S_ISCHR(os.fstat(number).st_mode):
                        actual_close(number)
                except OSError:
                    pass

    def test_active_private_image_consumer_detaches_before_reuse_and_gc(self):
        item = self.create()
        self._assert_private_image_consumer_detaches(item, item._verify_active)
        self.assertEqual(item.phase, "idle")
        self.assertEqual((self.slots / "slot-A.img").read_bytes(), SOURCE)

    def test_staged_private_image_consumer_detaches_before_reuse_and_gc(self):
        item = self.create()
        operation = self.admitted(item)
        result = item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self._assert_private_image_consumer_detaches(item, item._verify_staged, slot="slot-B.img")
        self.assertIs(item.confirm_result(result), result)
        self.assertEqual(item.phase, "staged")

    def test_prehash_private_image_consumer_detaches_before_reuse_and_gc(self):
        item = self.create()
        operation = self.admitted(item)
        result = self._assert_private_image_consumer_detaches(item,
            lambda: item.stage_image_file(operation, self.candidate, now_unix=NOW), source=True)
        self.assertIs(item.confirm_result(result), result)
        self.assertEqual(item.phase, "staged")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), TARGET)

    def test_scan_owner_constructor_call_first_line_and_return_interruptions_do_not_leak(self):
        item = self.create()
        before_events = self.events()
        for event_kind in ("call", "line", "return"):
            with self.subTest(event=event_kind):
                before = fd_inventory()
                triggered = []
                prior = sys.gettrace()
                def interrupt_constructor(frame, event, _argument):
                    if frame.f_code is owner._ScanRecord.__init__.__code__ and event == event_kind:
                        triggered.append(True)
                        raise KeyboardInterrupt("actual scan constructor before caller record adoption")
                    return interrupt_constructor
                try:
                    sys.settrace(interrupt_constructor)
                    with self.assertRaises(KeyboardInterrupt):
                        item._load_history()
                finally:
                    sys.settrace(prior)
                gc.collect()
                self.assertEqual(triggered, [True])
                self.assertEqual(fd_inventory(), before)
                self.assertEqual(self.events(), before_events)
        self.assertEqual(item.inspect()["phase"], "idle")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"previous-inactive-image")

    def test_discarded_scan_owner_gc_closes_only_its_owned_descriptor(self):
        item = self.create()
        before = fd_inventory()
        record = owner._ScanRecord("update-event-000001.json")
        record._descriptors = [os.open(self.state / record.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)]
        descriptor = record.descriptor
        self.assertEqual(os.pread(descriptor, 1, 0), b"{")
        del record
        gc.collect()
        with self.assertRaises(OSError) as closed:
            os.fstat(descriptor)
        self.assertEqual(closed.exception.errno, errno.EBADF)
        self.assertEqual(fd_inventory(), before)
        self.assertEqual(item.phase, "idle")

    def test_scan_owner_close_detaches_before_actual_reuse_interruption_and_gc(self):
        item = self.create()
        actual_close, actual_open = os.close, os.open
        event_file = self.state / "update-event-000001.json"
        for replacement in (Path("/dev/null"), event_file):
            for interrupted in (False, True):
                with self.subTest(replacement=replacement, interrupted=interrupted):
                    before = fd_inventory()
                    record = owner._ScanRecord(event_file.name)
                    record._descriptors = [actual_open(event_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)]
                    descriptor = record.descriptor
                    closed = []
                    def close_reuse(number):
                        closed.append(number)
                        actual_close(number)
                        donor = actual_open(replacement, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                        if donor != number:
                            os.dup2(donor, number, inheritable=False)
                            actual_close(donor)
                        if interrupted:
                            raise KeyboardInterrupt("actual scan close released number before interruption")
                    try:
                        with patch.object(os, "close", side_effect=close_reuse):
                            if interrupted:
                                with self.assertRaises(KeyboardInterrupt):
                                    record.close()
                            else:
                                record.close()
                            self.assertEqual(record._descriptors, [])
                            del record
                            gc.collect()
                            self.assertEqual(closed, [descriptor])
                            metadata = os.fstat(descriptor)
                            if replacement == event_file:
                                self.assertEqual(metadata.st_ino, event_file.stat().st_ino)
                                self.assertEqual(os.pread(descriptor, 1, 0), b"{")
                            else:
                                self.assertTrue(stat.S_ISCHR(metadata.st_mode))
                    finally:
                        actual_close(descriptor)
                    self.assertEqual(fd_inventory(), before)

    def test_real_signature_full_image_and_source_boot_policy_are_durable(self):
        item = self.create()
        operation = self.admitted(item)
        def before_effect(point):
            if point == "before_temp_create":
                self.assertEqual(self.events()[-1]["kind"], "stage_intent")
                self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"previous-inactive-image")
        result = item.stage_image_file(operation, self.candidate, now_unix=NOW, slot_fault=before_effect)
        self.assertEqual(result.phase, "staged")
        self.assertEqual(result.event_sha256, hashlib.sha256((self.state / f"update-event-{result.event_sequence:06d}.json").read_bytes()).hexdigest())
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), TARGET)
        self.assertIs(item.confirm_result(result), result)
        armed = item.arm_first_boot(operation, now_unix=NOW)
        self.assertEqual(armed.phase, "boot_pending")
        self.assertEqual([event["kind"] for event in self.events()], ["owner_open", "manifest_verified", "stage_intent", "stage_completed", "arm_intent", "boot_policy_armed"])
        self.assertFalse(armed.production_activation_enabled)
        self.assertFalse(armed.bootloader_effect_performed)
        for unavailable in ("record_booted_image", "record_health", "commit", "rollback", "resume", "reconcile_possible_dispatch"):
            self.assertFalse(hasattr(item, unavailable))

    def test_default_admission_and_wrong_signer_never_issue_an_operation(self):
        item = self.create(disabled=True)
        payload, signature = manifest()
        with self.assertRaises(s11.ManifestRefused):
            item.verify_manifest(payload, now_unix=NOW, signature=signature)
        self.assertEqual(len(self.events()), 1)
        item.close()
        # A changed externally configured policy cannot silently reinterpret history.
        changed = self.create()
        self.assertEqual(changed.phase, "recovery_required")
        with self.assertRaises(owner.DurableRecoveryRequired):
            self.admitted(changed)

    def test_actual_wrong_key_expiry_revocation_and_floor_are_rejected(self):
        item = self.create()
        for payload, signature in (manifest(signer="wrong"), manifest(expires_unix=NOW), manifest(rollback_floor=9), manifest(target_version=9)):
            with self.subTest(payload=payload), self.assertRaises(s11.ManifestRefused):
                item.verify_manifest(payload, now_unix=NOW, signature=signature)
        self.assertEqual(len(self.events()), 1)
        operation = self.admitted(item)
        verifier = item._coordinator._signature_verifier
        verifier._roots[TRUST.signer_id] = replace(TRUST, revoked=True)
        with self.assertRaises(s11.ManifestRefused):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual(self.events()[-1]["kind"], "manifest_verified")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"previous-inactive-image")

    def test_complete_image_mismatch_precedes_intent_and_slot_write(self):
        item = self.create(); operation = self.admitted(item)
        private_file(self.candidate, TARGET + b"trailer")
        with self.assertRaises(s11.StateRefused):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual(self.events()[-1]["kind"], "manifest_verified")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"previous-inactive-image")

    def test_failed_durable_intent_prevents_every_slot_effect(self):
        item = self.create(); operation = self.admitted(item)
        before = (self.slots / "slot-B.img").read_bytes()
        def refuse(point):
            if point == "before_temp_create": raise OSError("state disk full")
        with patch.object(s11.ImageSlotStore, "_publish_verified_image", wraps=item._slots._publish_verified_image) as publication:
            with self.assertRaises(owner.DurableRecoveryRequired):
                item.stage_image_file(operation, self.candidate, now_unix=NOW, state_fault=refuse)
            self.assertFalse(publication.called)
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), before)
        self.assertEqual(item.phase, "recovery_required")
        self.assertTrue((self.state / owner.RECOVERY_FILE).is_file())

    def test_interrupted_slot_publication_is_durable_recovery_and_never_replayed(self):
        item = self.create(); operation = self.admitted(item)
        def interrupt(point):
            if point == "after_atomic_replace": raise KeyboardInterrupt("return interrupted")
        with self.assertRaises(owner.DurableRecoveryRequired):
            item.stage_image_file(operation, self.candidate, now_unix=NOW, slot_fault=interrupt)
        self.assertEqual(item.phase, "recovery_required")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), TARGET)
        with self.assertRaises(owner.DurableRecoveryRequired):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        item._release_descriptors()
        restarted = self.create()
        self.assertEqual(restarted.phase, "recovery_required")
        self.assertFalse(restarted.inspect()["resume_or_replay_available"])

    def test_durable_result_lost_return_does_not_mint_a_replacement_result(self):
        item = self.create(); operation = self.admitted(item)
        def interrupt(point):
            if point == "after_directory_fsync" and len(self.events()) == 4:
                raise SystemExit("result response interrupted")
        with self.assertRaises(owner.DurableRecoveryRequired):
            item.stage_image_file(operation, self.candidate, now_unix=NOW, state_fault=interrupt)
        self.assertEqual(self.events()[-1]["kind"], "stage_completed")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), TARGET)
        item._release_descriptors()
        restarted = self.create()
        self.assertEqual(restarted.phase, "recovery_required")
        self.assertIn("stage_completed", [event["kind"] for event in restarted.inspect()["events"]])
        self.assertIsNone(restarted._operation)

    def test_explicit_close_of_pending_update_cannot_mark_session_clean(self):
        item = self.create(); operation = self.admitted(item)
        item.stage_image_file(operation, self.candidate, now_unix=NOW)
        item.close()
        self.assertNotIn("owner_clean", [event["kind"] for event in self.events()])
        self.assertEqual(self.create().phase, "recovery_required")

    def test_idle_explicit_clean_close_can_reopen_without_rewriting_history(self):
        item = self.create(); item.close()
        original = (self.state / "update-event-000001.json").read_bytes()
        reopened = self.create()
        self.assertEqual(reopened.phase, "idle")
        self.assertEqual((self.state / "update-event-000001.json").read_bytes(), original)
        self.assertEqual([event["kind"] for event in self.events()], ["owner_open", "owner_clean", "owner_open"])

    def test_gc_only_closes_descriptors_and_unclean_reopen_is_quarantined(self):
        item = self.create()
        self.owners.remove(item)
        before = [path.read_bytes() for path in self.state.glob("update-event-*.json")]
        del item; gc.collect()
        self.assertEqual([path.read_bytes() for path in self.state.glob("update-event-*.json")], before)
        self.assertEqual(self.create().phase, "recovery_required")

    def test_actual_sigkill_cutpoints_preserve_intent_and_require_restart_recovery(self):
        for cutpoint in ("before_temp_create", "after_file_fsync", "after_atomic_replace", "after_directory_fsync"):
            with self.subTest(cutpoint=cutpoint):
                temporary = tempfile.TemporaryDirectory(prefix="durable-update-kill-")
                self.addCleanup(temporary.cleanup)
                root = Path(temporary.name)
                state, slots = root / "state", root / "slots"
                state.mkdir(mode=0o700); slots.mkdir(mode=0o700)
                private_file(slots / "slot-A.img", SOURCE); private_file(slots / "slot-B.img", b"old")
                candidate = root / "candidate.img"; private_file(candidate, TARGET)
                ready_read, ready_write = os.pipe(); wait_read, wait_write = os.pipe()
                pid = os.fork()
                if pid == 0:
                    try:
                        os.close(ready_read); os.close(wait_write)
                        item = owner.DurableUpdateOwner(state, slots, active_slot="A", current_version=10,
                            current_image_sha256=SOURCE_DIGEST, signature_verifier=s11.ExternalUpdateSignatureVerifier((TRUST,)),
                            protected_rollback_floor=10, clock=lambda: NOW)
                        payload, signature = manifest()
                        operation = item.verify_manifest(payload, now_unix=NOW, signature=signature)
                        def stop(point):
                            if point == cutpoint:
                                os.write(ready_write, b"r"); os.read(wait_read, 1)
                        item.stage_image_file(operation, candidate, now_unix=NOW, slot_fault=stop)
                        os._exit(90)
                    except BaseException:
                        os._exit(91)
                os.close(ready_write); os.close(wait_read)
                try:
                    self.assertTrue(select.select([ready_read], [], [], 10)[0], "actual child never reached cutpoint")
                    self.assertEqual(os.read(ready_read, 1), b"r")
                    os.kill(pid, signal.SIGKILL)
                    _, status = os.waitpid(pid, 0)
                    self.assertTrue(os.WIFSIGNALED(status)); self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
                    restarted = owner.DurableUpdateOwner(state, slots, active_slot="A", current_version=10,
                        current_image_sha256=SOURCE_DIGEST, signature_verifier=s11.ExternalUpdateSignatureVerifier((TRUST,)),
                        protected_rollback_floor=10, clock=lambda: NOW)
                    self.owners.append(restarted)
                    self.assertEqual(restarted.phase, "recovery_required")
                    self.assertTrue((state / owner.RECOVERY_FILE).is_file())
                    self.assertEqual(json.loads(sorted(state.glob("update-event-*.json"))[-1].read_bytes())["kind"], "stage_intent")
                    self.assertEqual((slots / "slot-A.img").read_bytes(), SOURCE)
                finally:
                    os.close(ready_read); os.close(wait_write)
                    try: os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    try: os.waitpid(pid, 0)
                    except ChildProcessError: pass

    def test_fork_cannot_use_facts_mutate_close_clean_or_unlock_parent(self):
        item = self.create(); operation = self.admitted(item)
        result = item.stage_image_file(operation, self.candidate, now_unix=NOW)
        before = {path.name: path.read_bytes() for path in self.state.iterdir()}
        pid = os.fork()
        if pid == 0:
            try:
                for action in (lambda: item.phase, lambda: operation.operation_id, lambda: result.event_sha256,
                               lambda: item.arm_first_boot(operation, now_unix=NOW), lambda: item.confirm_result(result), item.inspect):
                    try: action()
                    except owner.DurableUpdateError: pass
                    else: os._exit(92)
                item.close()
                try:
                    contender = s11.AtomicStateStore(self.state); contender.acquire()
                except s11.CoordinatorBusy:
                    os._exit(0)
                os._exit(93)
            except BaseException:
                os._exit(94)
        _, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFEXITED(status)); self.assertEqual(os.WEXITSTATUS(status), 0)
        self.assertEqual({path.name: path.read_bytes() for path in self.state.iterdir()}, before)
        self.assertIs(item.confirm_result(result), result)

    def test_foreign_thread_and_reentrant_callback_have_no_authority(self):
        item = self.create(); operation = self.admitted(item)
        failures = []
        def foreign():
            for action in (lambda: item.phase, lambda: operation.operation_id, item.close):
                try: action()
                except owner.DurableUpdateError: failures.append(True)
        thread = threading.Thread(target=foreign); thread.start(); thread.join(timeout=5)
        self.assertFalse(thread.is_alive()); self.assertEqual(len(failures), 3)
        def reenter(point):
            if point == "before_temp_create":
                with self.assertRaises(owner.DurableUpdateError): item.close()
                with self.assertRaises(owner.DurableUpdateError): item.arm_first_boot(operation, now_unix=NOW)
        item.stage_image_file(operation, self.candidate, now_unix=NOW, slot_fault=reenter)

    def test_copied_operations_and_results_are_not_live_owner_authority(self):
        item = self.create(); operation = self.admitted(item)
        with self.assertRaises(owner.DurableUpdateError):
            item.stage_image_file(replace(operation), self.candidate, now_unix=NOW)
        result = item.stage_image_file(operation, self.candidate, now_unix=NOW)
        with self.assertRaises(owner.DurableUpdateError): item.confirm_result(replace(result))
        with self.assertRaises(owner.DurableUpdateError): item.confirm_result("0" * 64)

    def test_another_live_owner_cannot_use_same_manifest_operations_or_results(self):
        first = self.create(); operation = self.admitted(first)
        result = first.stage_image_file(operation, self.candidate, now_unix=NOW)
        directory = Path(self.directory.name) / "other-owner"
        directory.mkdir(mode=0o700)
        state, slots = directory / "state", directory / "slots"
        state.mkdir(mode=0o700); slots.mkdir(mode=0o700)
        private_file(slots / "slot-A.img", SOURCE); private_file(slots / "slot-B.img", b"old")
        second = owner.DurableUpdateOwner(state, slots, active_slot="A", current_version=10,
            current_image_sha256=SOURCE_DIGEST, signature_verifier=s11.ExternalUpdateSignatureVerifier((TRUST,)),
            protected_rollback_floor=10, clock=lambda: NOW)
        self.owners.append(second)
        own_operation = self.admitted(second)
        self.assertEqual(own_operation.manifest_sha256, operation.manifest_sha256)
        with self.assertRaises(owner.DurableUpdateError):
            second.stage_image_file(operation, self.candidate, now_unix=NOW)
        own_result = second.stage_image_file(own_operation, self.candidate, now_unix=NOW)
        self.assertEqual(own_result.event_sequence, result.event_sequence)
        with self.assertRaises(owner.DurableUpdateError): second.confirm_result(result)
        self.assertIs(second.confirm_result(own_result), own_result)

    def test_same_bytes_new_record_inode_is_not_a_live_durable_fact(self):
        item = self.create(); operation = self.admitted(item)
        result = item.stage_image_file(operation, self.candidate, now_unix=NOW)
        path = self.state / f"update-event-{result.event_sequence:06d}.json"
        replacement = self.state / "same-bytes-copy"
        private_file(replacement, path.read_bytes())
        replacement.replace(path)
        with self.assertRaises(owner.DurableRecoveryRequired): item.confirm_result(result)
        self.assertEqual(item.phase, "recovery_required")

    def test_predecessor_change_during_complete_real_fsync_readback_prevents_slot_effect(self):
        item = self.create(); operation = self.admitted(item)
        real_fsync = os.fsync
        altered = []
        def mutate_predecessor(descriptor):
            descriptor = int(descriptor)
            real_fsync(descriptor)
            name = os.readlink(f"/proc/self/fd/{descriptor}")
            if not altered and len(item._history) == 3 and name.endswith("update-event-000003.json"):
                with (self.state / "update-event-000001.json").open("ab") as stream:
                    stream.write(b" "); stream.flush(); real_fsync(stream.fileno())
                altered.append(True)
        before = (self.slots / "slot-B.img").read_bytes()
        with patch.object(os, "fsync", side_effect=mutate_predecessor), patch.object(item._slots, "_publish_verified_image", wraps=item._slots._publish_verified_image) as publication:
            with self.assertRaises(owner.DurableRecoveryRequired):
                item.stage_image_file(operation, self.candidate, now_unix=NOW)
            self.assertFalse(publication.called)
        self.assertEqual(altered, [True])
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), before)
        self.assertEqual(item.phase, "recovery_required")

    def test_history_change_during_final_actual_image_readback_never_issues_a_result(self):
        item = self.create(); operation = self.admitted(item)
        real_fsync = os.fsync
        altered = []
        def mutate_history(descriptor):
            descriptor = int(descriptor)
            real_fsync(descriptor)
            if not altered and len(item._history) == 4 and os.readlink(f"/proc/self/fd/{descriptor}").endswith("slot-B.img"):
                with (self.state / "update-event-000001.json").open("ab") as stream:
                    stream.write(b" "); stream.flush(); real_fsync(stream.fileno())
                altered.append(True)
        with patch.object(os, "fsync", side_effect=mutate_history), self.assertRaises(owner.DurableRecoveryRequired):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual(altered, [True])
        self.assertEqual(item._results, {})
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), TARGET)
        self.assertEqual(item.phase, "recovery_required")

    def test_result_confirmation_rechecks_history_after_actual_image_sync(self):
        item = self.create(); operation = self.admitted(item)
        result = item.stage_image_file(operation, self.candidate, now_unix=NOW)
        real_fsync = os.fsync
        altered = []
        def mutate_history(descriptor):
            descriptor = int(descriptor)
            real_fsync(descriptor)
            if not altered and os.readlink(f"/proc/self/fd/{descriptor}").endswith("slot-B.img"):
                with (self.state / "update-event-000001.json").open("ab") as stream:
                    stream.write(b" "); stream.flush(); real_fsync(stream.fileno())
                altered.append(True)
        with patch.object(os, "fsync", side_effect=mutate_history), self.assertRaises(owner.DurableRecoveryRequired):
            item.confirm_result(result)
        self.assertEqual(altered, [True])
        self.assertEqual(item.phase, "recovery_required")

    def test_interrupted_scan_transfer_cannot_double_close_a_reused_descriptor(self):
        item = self.create(); self.admitted(item)
        lines, start = inspect.getsourcelines(owner.DurableUpdateOwner._read)
        transfer = next(start + index for index, line in enumerate(lines) if line.strip() == "record = None")
        real_close, real_open = os.close, os.open
        replacement = []
        closed_names = []
        triggered = []
        def trace(frame, event, _argument):
            if event == "line" and frame.f_code is owner.DurableUpdateOwner._read.__code__ and frame.f_lineno == transfer and not triggered:
                triggered.append(True)
                raise KeyboardInterrupt("interrupted after retained scan adoption")
            return trace
        def close_and_reuse(descriptor):
            name = os.readlink(f"/proc/self/fd/{descriptor}")
            closed_names.append(name)
            real_close(descriptor)
            if not replacement and name.endswith("update-event-000001.json"):
                foreign = real_open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                if foreign != descriptor:
                    os.dup2(foreign, descriptor); real_close(foreign)
                replacement.append(descriptor)
        prior = sys.gettrace()
        try:
            with patch.object(os, "close", side_effect=close_and_reuse):
                sys.settrace(trace)
                with self.assertRaises(KeyboardInterrupt): item._load_history()
                sys.settrace(prior)
            self.assertEqual(triggered, [True])
            self.assertEqual(len(replacement), 1)
            self.assertTrue(stat.S_ISCHR(os.fstat(replacement[0]).st_mode))
            self.assertNotIn("/dev/null", closed_names)
        finally:
            sys.settrace(prior)
            for descriptor in replacement: real_close(descriptor)

    def test_scan_cleanup_attempts_all_owned_closes_without_retrying_reused_integer(self):
        item = self.create(); self.admitted(item)
        real_close, real_open = os.close, os.open
        replacement = []
        closed_names = []
        before = len(os.listdir("/proc/self/fd"))
        def interrupted_close(descriptor):
            name = os.readlink(f"/proc/self/fd/{descriptor}")
            closed_names.append(name)
            real_close(descriptor)
            if not replacement and name.endswith("update-event-000001.json"):
                foreign = real_open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                if foreign != descriptor:
                    os.dup2(foreign, descriptor); real_close(foreign)
                replacement.append(descriptor)
                raise KeyboardInterrupt("actual first close completed before interruption")
        try:
            with patch.object(os, "close", side_effect=interrupted_close), self.assertRaises(KeyboardInterrupt):
                item._load_history()
            self.assertTrue(stat.S_ISCHR(os.fstat(replacement[0]).st_mode))
            self.assertTrue(any(name.endswith("update-event-000002.json") for name in closed_names))
            self.assertNotIn("/dev/null", closed_names)
            self.assertEqual(len(os.listdir("/proc/self/fd")), before + 1)
        finally:
            for descriptor in replacement: real_close(descriptor)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_history_gap_preserves_remaining_evidence(self):
        item = self.create(); self.admitted(item); item._release_descriptors()
        before = (self.state / "update-event-000002.json").read_bytes()
        (self.state / "update-event-000001.json").unlink()
        with self.assertRaises(owner.DurableRecoveryRequired): self.create()
        self.assertEqual((self.state / "update-event-000002.json").read_bytes(), before)
        self.assertTrue((self.state / owner.RECOVERY_FILE).exists())

    def test_unknown_file_preserves_evidence_and_quarantines_reopening(self):
        item = self.create(); item.close()
        private_file(self.state / "unknown.json", b"unrecognized-evidence")
        with self.assertRaises(owner.DurableRecoveryRequired): self.create()
        self.assertEqual((self.state / "unknown.json").read_bytes(), b"unrecognized-evidence")
        self.assertTrue((self.state / owner.RECOVERY_FILE).exists())

    def test_recovery_marker_cannot_assert_an_arbitrary_confirmed_digest(self):
        item = self.create(); self.admitted(item); item.close()
        marker = self.state / owner.RECOVERY_FILE
        data = json.loads(marker.read_bytes())
        data["last_event_sha256"] = "f" * 64
        private_file(marker, s11._canonical(data))
        before = marker.read_bytes()
        with self.assertRaises(owner.DurableRecoveryRequired): self.create()
        self.assertEqual(marker.read_bytes(), before)

    def test_marker_write_failure_keeps_recovery_without_claiming_marker_durability(self):
        item = self.create(); operation = self.admitted(item)
        actual_write = item._state.write
        def refuse_marker(name, value, **kwargs):
            if name == owner.RECOVERY_FILE: raise OSError("recovery storage unavailable")
            return actual_write(name, value, **kwargs)
        def stop(point):
            if point == "before_temp_create": raise OSError("slot storage unavailable")
        with patch.object(item._state, "write", side_effect=refuse_marker), self.assertRaises(OSError):
            item.stage_image_file(operation, self.candidate, now_unix=NOW, slot_fault=stop)
        diagnosis = item.inspect()
        self.assertEqual(diagnosis["phase"], "recovery_required")
        self.assertTrue(diagnosis["recovery_required"])
        self.assertFalse(diagnosis["recovery_marker_confirmed"])
        self.assertEqual(self.events()[-1]["kind"], "stage_intent")
        item._release_descriptors()
        restarted = self.create()
        self.assertEqual(restarted.phase, "recovery_required")
        self.assertTrue(restarted.inspect()["recovery_marker_confirmed"])

    def test_known_durable_stage_with_unavailable_result_keeps_knowledge_and_never_replays(self):
        item = self.create(); operation = self.admitted(item)
        with patch.object(item, "_result", side_effect=KeyboardInterrupt("caller response unavailable")), self.assertRaises(owner.DurableResultUnavailable):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual(item.phase, "staged")
        self.assertFalse(item.inspect()["recovery_required"])
        self.assertEqual(self.events()[-1]["kind"], "stage_completed")
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), TARGET)
        before = len(self.events())
        with self.assertRaises(owner.DurableUpdateError):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual(len(self.events()), before)
        item.close()
        self.assertEqual(self.create().phase, "recovery_required")

    def test_known_source_boot_policy_with_unavailable_result_claims_no_boot(self):
        item = self.create(); operation = self.admitted(item)
        item.stage_image_file(operation, self.candidate, now_unix=NOW)
        with patch.object(item, "_result", side_effect=SystemExit("response unavailable")), self.assertRaises(owner.DurableResultUnavailable):
            item.arm_first_boot(operation, now_unix=NOW)
        self.assertEqual(item.phase, "boot_pending")
        self.assertEqual(self.events()[-1]["kind"], "boot_policy_armed")
        self.assertFalse(item.inspect()["bootloader_effect_performed"])
        with self.assertRaises(owner.DurableUpdateError): item.arm_first_boot(operation, now_unix=NOW)

    def test_clock_regression_after_staging_permanently_refuses_authority(self):
        item = self.create(); operation = self.admitted(item)
        self.clock[0] = NOW + 100
        item.stage_image_file(operation, self.candidate, now_unix=self.clock[0])
        self.clock[0] = NOW + 50
        with self.assertRaises(owner.DurableRecoveryRequired): item.arm_first_boot(operation, now_unix=self.clock[0])
        self.clock[0] = NOW + 150
        with self.assertRaises(owner.DurableRecoveryRequired): item.arm_first_boot(operation, now_unix=self.clock[0])
        self.assertEqual(item.phase, "recovery_required")
        self.assertEqual(json.loads((self.state / owner.RECOVERY_FILE).read_bytes())["reason"], "trusted_clock_regressed")

    def test_current_expiry_revalidation_precedes_boot_policy_intent(self):
        item = self.create(); operation = self.admitted(item)
        item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.clock[0] = NOW + 1000
        with self.assertRaises(s11.ManifestRefused): item.arm_first_boot(operation, now_unix=self.clock[0])
        self.assertEqual(self.events()[-1]["kind"], "stage_completed")

    def test_clean_history_cannot_reopen_under_a_regressed_clock(self):
        item = self.create(); item.close()
        before = [path.read_bytes() for path in sorted(self.state.glob("update-event-*.json"))]
        self.clock[0] = NOW - 1
        with self.assertRaises(owner.DurableRecoveryRequired): self.create()
        self.assertEqual([path.read_bytes() for path in sorted(self.state.glob("update-event-*.json"))], before)
        self.clock[0] = NOW + 1
        self.assertEqual(self.create().phase, "recovery_required")

    def test_replaced_lease_cannot_supply_owner_authority(self):
        item = self.create(); operation = self.admitted(item)
        (self.state / ".coordinator.lock").rename(self.state / ".saved-lock")
        private_file(self.state / ".coordinator.lock", b"")
        with self.assertRaises(s11.StateRefused): item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"previous-inactive-image")

    def test_changed_actual_running_source_image_prevents_slot_publication(self):
        item = self.create(); operation = self.admitted(item)
        private_file(self.slots / "slot-A.img", b"different-running-image")
        with self.assertRaises(owner.DurableRecoveryRequired):
            item.stage_image_file(operation, self.candidate, now_unix=NOW)
        self.assertEqual((self.slots / "slot-B.img").read_bytes(), b"previous-inactive-image")
        self.assertEqual(item.phase, "recovery_required")

    def test_concrete_type_and_descriptor_failure_custody(self):
        class FakeVerifier(s11.ExternalUpdateSignatureVerifier): pass
        with self.assertRaises(s11.StateRefused): self.create(signature_verifier=FakeVerifier((TRUST,)))
        before = len(os.listdir("/proc/self/fd"))
        with patch.object(owner.secrets, "token_hex", side_effect=OSError("entropy unavailable")), self.assertRaises(OSError):
            self.create()
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        item = self.create()
        with self.assertRaises(s11.CoordinatorBusy): self.create()
        item.close()

    def test_close_interruption_clears_owner_authority_before_descriptor_cleanup(self):
        item = self.create()
        before = len(os.listdir("/proc/self/fd"))
        real_close = os.close
        closed = []
        retained = {int(descriptor) for descriptor in (item._state._root_fd, item._state._lease_fd,
                                                      item._slots._root_fd, item._slots._lease_fd)}
        def actual_close_then_interrupt(descriptor):
            real_close(descriptor)
            if descriptor in retained:
                closed.append(descriptor)
                if len(closed) == 1: raise KeyboardInterrupt("actual descriptor close already completed")
        with patch.object(os, "close", side_effect=actual_close_then_interrupt), self.assertRaises(KeyboardInterrupt):
            item.close()
        self.assertTrue(item._closed)
        self.assertFalse(item._busy)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before - 4)
        with self.assertRaises(owner.DurableUpdateError): _ = item.phase
        reopened = self.create()
        self.assertEqual(reopened.phase, "idle")


class DurableUpdateContractTests(unittest.TestCase):
    def test_contract_matches_public_source_api_and_closed_persistence_shapes(self):
        contract = json.loads((ROOT / "contracts/durable-update-owner.v1.json").read_bytes())
        self.assertEqual(contract["schema"], owner.SCHEMA)
        self.assertEqual(contract["status"], "source_and_host_candidate_only")
        self.assertTrue(all(value is False for value in contract["non_claims"].values()))
        for path in contract["artifacts"].values(): self.assertTrue((ROOT / path).is_file(), path)
        api = contract["public_api"]["DurableUpdateOwner"]
        self.assertEqual(api["constructor"], [name for name in inspect.signature(owner.DurableUpdateOwner.__init__).parameters if name != "self"])
        actual_methods = {name for name, value in vars(owner.DurableUpdateOwner).items() if not name.startswith("_") and callable(value)}
        self.assertEqual(set(api["methods"]), actual_methods)
        for name, parameters in api["methods"].items():
            self.assertEqual(parameters, [key for key in inspect.signature(getattr(owner.DurableUpdateOwner, name)).parameters if key != "self"])
        self.assertEqual(api["properties"], [name for name, value in vars(owner.DurableUpdateOwner).items() if not name.startswith("_") and isinstance(value, property)])
        for name, kind in (("operation_fields", owner.DurableUpdateOperation), ("result_fields", owner.DurableUpdateResult)):
            self.assertEqual(contract["public_api"][name], [field.name for field in fields(kind) if not field.name.startswith("_")])
        history = contract["history"]
        self.assertEqual(history["event_schema"], owner.EVENT_SCHEMA)
        self.assertEqual(history["maximum_events"], owner.MAX_EVENTS)
        self.assertEqual(history["maximum_record_bytes"], s11.MAX_STATE_BYTES)
        self.assertEqual(history["maximum_directory_entries"], owner.MAX_EVENTS + 2)
        self.assertEqual(history["maximum_retained_scan_record_descriptors"], owner.MAX_EVENTS + 1)
        self.assertEqual(history["event_phases"], owner._PHASES)
        self.assertEqual({None if name == "initial" else name: set(values) for name, values in history["transitions"].items()}, owner._NEXT)
        for key, expected in (("event_exact_fields", owner._EVENT_FIELDS), ("configuration_exact_fields", owner._CONFIG_FIELDS), ("operation_exact_fields", owner._OP_FIELDS), ("admission_exact_fields", owner._ADMISSION_FIELDS), ("stage_receipt_exact_fields", owner._STAGE_FIELDS)):
            self.assertEqual(len(history[key]), len(set(history[key])))
            self.assertEqual(set(history[key]), expected)
        self.assertEqual(contract["recovery"]["schema"], owner.RECOVERY_SCHEMA)
        self.assertEqual(contract["recovery"]["file"], owner.RECOVERY_FILE)
        self.assertEqual(set(contract["recovery"]["exact_fields"]), owner._MARKER_FIELDS)
        self.assertEqual(contract["staging"]["maximum_image_bytes"], s11.MAX_IMAGE_BYTES)
        self.assertIsNone(inspect.signature(owner.DurableUpdateOwner).parameters["signature_verifier"].default)
        self.assertFalse(contract["defaults"]["update_admission_enabled"])
        self.assertFalse(contract["staging"]["caller_boot_health_commit_rollback_api"])


if __name__ == "__main__":
    unittest.main()
