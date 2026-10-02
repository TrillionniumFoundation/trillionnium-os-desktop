from __future__ import annotations

import hashlib
import gc
import errno
import importlib.util
import json
import os
import select
import signal
import stat
import subprocess
import tempfile
import threading
import unittest
import weakref
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "platform/update_recovery.py"
spec = importlib.util.spec_from_file_location("s11_update_recovery", MODULE)
assert spec is not None and spec.loader is not None
s11 = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = s11
spec.loader.exec_module(s11)

SOURCE = b"source-image"
TARGET = b"target-image"
SOURCE_DIGEST = hashlib.sha256(SOURCE).hexdigest()
TARGET_DIGEST = hashlib.sha256(TARGET).hexdigest()
RECEIPT = hashlib.sha256(b"health-receipt").hexdigest()
JOURNAL = hashlib.sha256(b"journal-record").hexdigest()
NOW = 1_000_000
SIGNATURES: dict[bytes, bytes] = {}
TEST_KEYS = None
TRUST_ROOT = None
OTHER_ROOT = None


def setUpModule() -> None:
    global TEST_KEYS, TRUST_ROOT, OTHER_ROOT
    if not Path("/usr/bin/openssl").is_file():
        raise RuntimeError("real system OpenSSL is required for signed update admission; skipped crypto is not success")
    TEST_KEYS = tempfile.TemporaryDirectory(prefix="s11-test-keys-")
    root = Path(TEST_KEYS.name)
    for name in ("approved", "other"):
        subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(root / f"{name}.private")], capture_output=True, check=True, env=s11.OPENSSL_ENV)
        subprocess.run(["/usr/bin/openssl", "pkey", "-in", str(root / f"{name}.private"), "-pubout", "-out", str(root / f"{name}.public")], capture_output=True, check=True, env=s11.OPENSSL_ENV)
    public = (root / "approved.public").read_bytes()
    TRUST_ROOT = s11.UpdateTrustRoot("release-key:test", public, hashlib.sha256(public).hexdigest(), 10, 1, 3_000_000)
    public = (root / "other.public").read_bytes()
    OTHER_ROOT = s11.UpdateTrustRoot("release-key:test", public, hashlib.sha256(public).hexdigest(), 10, 1, 3_000_000)


def tearDownModule() -> None:
    if TEST_KEYS is not None:
        TEST_KEYS.cleanup()
    SIGNATURES.clear()


def signed_payload(value: dict[str, object], *, signer: str = "approved") -> bytes:
    root = Path(TEST_KEYS.name)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    (root / "manifest.bin").write_bytes(s11.manifest_signing_bytes(payload))
    subprocess.run(["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(root / f"{signer}.private"), "-out", str(root / "signature.bin"), str(root / "manifest.bin")], capture_output=True, check=True, env=s11.OPENSSL_ENV)
    signature = (root / "signature.bin").read_bytes()
    value = {**value, "signature_sha256": hashlib.sha256(signature).hexdigest()}
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    SIGNATURES[payload] = signature
    return payload


def manifest(**overrides: object) -> bytes:
    value: dict[str, object] = {
        "schema": s11.MANIFEST_SCHEMA,
        "repository": s11.REPOSITORY,
        "source_version": 10,
        "source_image_sha256": SOURCE_DIGEST,
        "target_version": 11,
        "target_slot": "B",
        "target_image_sha256": TARGET_DIGEST,
        "target_image_bytes": len(TARGET),
        "rollback_floor": 10,
        "expires_unix": 2_000_000,
        "signer_id": "release-key:test",
        "signature_sha256": hashlib.sha256(b"signature").hexdigest(),
    }
    value.update(overrides)
    return signed_payload(value)


class SignedTestCoordinator(s11.UpdateCoordinator):
    """Existing state corpus uses signatures made only by temporary test keys."""
    def verify_manifest(self, payload, *, now_unix, signature=None):
        return super().verify_manifest(payload, now_unix=now_unix,
                                       signature=SIGNATURES.get(payload, b"invalid") if signature is None else signature)

    def stage_image(self, ticket, image, *, now_unix=NOW):
        return super().stage_image(ticket, image, now_unix=now_unix)

    def arm_first_boot(self, ticket, *, now_unix=NOW):
        return super().arm_first_boot(ticket, now_unix=now_unix)


def coordinator(**overrides) -> object:
    return SignedTestCoordinator(
        active_slot="A",
        current_version=10,
        current_image_sha256=SOURCE_DIGEST,
        signature_verifier=s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,)),
        clock=lambda: NOW,
        **overrides,
    )


class S11UpdateRecoveryTests(unittest.TestCase):
    def test_strict_manifest_and_source_binding(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        self.assertEqual(ticket.manifest.target_slot, "B")
        for payload in (
            b'{"schema":"x","schema":"y"}',
            b'{"value":NaN}',
            b'{"value":1e999}',
            b"[]",
            b"\xef\xbb\xbf{}",
        ):
            with self.subTest(payload=payload), self.assertRaises(s11.ManifestRefused):
                coordinator().verify_manifest(payload, now_unix=1_000_000)
        for change in (
            {"repository": "attacker/repo"},
            {"source_version": 9},
            {"source_image_sha256": "0" * 64},
            {"target_slot": "A"},
            {"target_version": 10},
            {"rollback_floor": 11},
            {"expires_unix": 999_999},
            {"target_image_bytes": 0},
            {"unexpected": True},
        ):
            with self.subTest(change=change), self.assertRaises(s11.ManifestRefused):
                coordinator().verify_manifest(manifest(**change), now_unix=1_000_000)

    def test_whole_image_substitution_is_refused(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        with self.assertRaises(s11.StateRefused):
            c.stage_image(ticket, TARGET + b"x")
        with self.assertRaises(s11.StateRefused):
            c.stage_image(ticket, b"wrong-image")
        c.stage_image(ticket, TARGET)
        self.assertEqual(c.phase, s11.Phase.STAGED)

    def test_noninteger_and_nonfinite_health_windows_cannot_commit(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        c.arm_first_boot(ticket)
        c.record_booted_image(ticket, slot="B", image_sha256=TARGET_DIGEST)
        for stable in (float("nan"), float("inf"), 60.0, True, "60", None):
            with self.subTest(stable=stable), self.assertRaises(s11.StateRefused):
                c.record_health(ticket, stable_seconds=stable, health_receipt_sha256=RECEIPT)
        self.assertEqual(c.phase, s11.Phase.HEALTH_PENDING)

    def test_state_publication_cannot_replace_its_coordinator_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = s11.AtomicStateStore(root)
            second = s11.AtomicStateStore(root)
            try:
                first.acquire()
                for name in (".coordinator.lock", ".state.json.tmp", "state.json/", "./state.json"):
                    with self.subTest(name=name), self.assertRaises(s11.StateRefused):
                        first.write(name, {"phase": "verified"})
                with self.assertRaises(s11.CoordinatorBusy):
                    second.acquire()
            finally:
                first.close()
                second.close()

    def test_failed_exclusive_temp_creation_never_unlinks_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with s11.AtomicStateStore(root) as store:
                name = f".state.json.{os.getpid()}.{'a' * 32}.tmp"
                stale = root / name
                stale.write_bytes(b"preexisting")
                with patch.object(s11.secrets, "token_hex", return_value="a" * 32):
                    with self.assertRaises(FileExistsError):
                        store.write("state.json", {"phase": "verified"})
                self.assertEqual(stale.read_bytes(), b"preexisting")

    def test_state_store_refuses_lease_hardlinks_and_root_custody_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            root.mkdir(mode=0o700)
            unrelated = root / "original"
            unrelated.write_text("private")
            os.link(unrelated, root / ".coordinator.lock")
            store = s11.AtomicStateStore(root)
            try:
                with self.assertRaises(s11.StateRefused):
                    store.acquire()
                (root / ".coordinator.lock").unlink()
                store.acquire()
                root.chmod(0o777)
                with self.assertRaises(s11.StateRefused):
                    store.write("state.json", {"phase": "verified"})
                root.chmod(0o700)
                root.rename(root.with_name("saved"))
                root.mkdir(mode=0o700)
                with self.assertRaises(s11.StateRefused):
                    store.write("state.json", {"phase": "verified"})
            finally:
                store.close()

    def test_replaced_lease_cannot_leave_two_coordinators_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = s11.AtomicStateStore(root)
            second = s11.AtomicStateStore(root)
            try:
                first.acquire()
                (root / ".coordinator.lock").rename(root / ".saved-lock")
                second.acquire()
                with self.assertRaisesRegex(s11.StateRefused, "lease pathname was replaced"):
                    first.write("state.json", {"writer": "first"})
                second.write("state.json", {"writer": "second"})
                self.assertEqual(second.read("state.json"), {"writer": "second"})
            finally:
                first.close()
                second.close()

    def test_existing_unsafe_lease_mode_is_refused_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lease = root / ".coordinator.lock"
            lease.write_bytes(b"lease")
            lease.chmod(0o666)
            store = s11.AtomicStateStore(root)
            try:
                with self.assertRaises(s11.StateRefused):
                    store.acquire()
                self.assertEqual(stat.S_IMODE(lease.stat().st_mode), 0o666)
                lease.chmod(0o600)
                store.acquire()
            finally:
                store.close()

    def test_lease_replacement_before_publication_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with s11.AtomicStateStore(root) as store:
                def replace(point: str) -> None:
                    if point == "after_file_fsync":
                        (root / ".coordinator.lock").rename(root / ".saved-lock")
                        (root / ".coordinator.lock").write_bytes(b"replacement")
                with self.assertRaisesRegex(s11.StateRefused, "lease pathname was replaced"):
                    store.write("state.json", {"phase": "verified"}, fault=replace)
                self.assertFalse((root / "state.json").exists())
                self.assertFalse(any(path.name.endswith(".tmp") for path in root.iterdir()))

    def test_staged_path_substitution_never_promotes_a_symlink_or_deletes_foreign_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            root.mkdir(mode=0o700)
            outside = root.parent / "outside.json"
            outside.write_text('{"writer":"attacker"}')
            with s11.AtomicStateStore(root) as store:
                def substitute(point: str) -> None:
                    if point == "after_file_fsync":
                        temporary = next(root.glob(".state.json.*.tmp"))
                        temporary.unlink()
                        temporary.symlink_to(outside)
                with self.assertRaises(s11.StateRefused):
                    store.write("state.json", {"writer": "expected"}, fault=substitute)
                self.assertFalse((root / "state.json").exists())
                self.assertTrue(next(root.glob(".state.json.*.tmp")).is_symlink())
                self.assertEqual(outside.read_text(), '{"writer":"attacker"}')

    def test_post_replace_state_substitution_is_indeterminate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with s11.AtomicStateStore(root) as store:
                def substitute(point: str) -> None:
                    if point == "after_atomic_replace":
                        (root / "state.json").unlink()
                        (root / "state.json").write_text('{"writer":"attacker"}')
                with self.assertRaises(s11.PublicationIndeterminate):
                    store.write("state.json", {"writer": "expected"}, fault=substitute)

    def test_health_gated_commit_and_exact_boot_identity(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        c.arm_first_boot(ticket)
        with self.assertRaises(s11.RecoveryRequired):
            c.record_booted_image(ticket, slot="B", image_sha256="0" * 64)

        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        c.arm_first_boot(ticket)
        c.record_booted_image(ticket, slot="B", image_sha256=TARGET_DIGEST)
        with self.assertRaises(s11.StateRefused):
            c.record_health(ticket, stable_seconds=59, health_receipt_sha256=RECEIPT)
        permit = c.record_health(
            ticket, stable_seconds=60, health_receipt_sha256=RECEIPT
        )
        c.commit(permit)
        self.assertEqual((c.active_slot, c.current_version), ("B", 11))
        self.assertEqual(c.current_image_sha256, TARGET_DIGEST)

    def test_boot_failures_open_rollback_and_require_exact_source(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        c.arm_first_boot(ticket)
        self.assertEqual(c.record_boot_failure(ticket), s11.Phase.BOOT_PENDING)
        self.assertEqual(c.record_boot_failure(ticket), s11.Phase.ROLLBACK_PENDING)
        with self.assertRaises(s11.RecoveryRequired):
            c.rollback(ticket, recovered_image_sha256="0" * 64)

        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        c.arm_first_boot(ticket)
        c.record_boot_failure(ticket)
        c.record_boot_failure(ticket)
        c.rollback(ticket, recovered_image_sha256=SOURCE_DIGEST)
        self.assertEqual(c.phase, s11.Phase.IDLE)

    def test_possible_dispatch_never_replays_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as directory, s11.DurableUpdateJournal(Path(directory)) as journal:
            c = coordinator(journal_authority=journal)
            ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
            binding = c.mark_possible_dispatch(ticket)
            self.assertTrue(c.effect_reconciliation_required)
            with self.assertRaises(s11.StateRefused):
                c.verify_manifest(manifest(), now_unix=1_000_000)
            record_dispatch(journal, binding, status="retry")
            with self.assertRaises(s11.StateRefused):
                c.verify_journal_reconciliation(ticket)
            record_dispatch(journal, binding, status="indeterminate")
            fact = c.verify_journal_reconciliation(ticket)
            c.reconcile_possible_dispatch(fact)
            self.assertFalse(c.effect_reconciliation_required)
            self.assertEqual(c.phase, s11.Phase.ROLLBACK_PENDING)

    def test_startup_reconciliation_refuses_missing_or_substituted_slots(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        with self.assertRaises(s11.RecoveryRequired):
            c.reconcile_startup({"A": SOURCE_DIGEST})
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.stage_image(ticket, TARGET)
        with self.assertRaises(s11.RecoveryRequired):
            c.reconcile_startup({"A": SOURCE_DIGEST, "B": "0" * 64})

    def test_atomic_state_store_is_private_locked_and_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.chmod(root, 0o700)
            first = s11.AtomicStateStore(root)
            first.acquire()
            digest = first.write("state.json", {"phase": "verified", "sequence": 1})
            self.assertEqual(len(digest), 64)
            self.assertEqual(first.read("state.json")["sequence"], 1)
            self.assertEqual(stat.S_IMODE((root / "state.json").stat().st_mode), 0o600)
            second = s11.AtomicStateStore(root)
            with self.assertRaises(s11.CoordinatorBusy):
                second.acquire()
            second.close()
            first.close()

    def test_state_store_refuses_symlink_root_and_post_replace_uncertainty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            real = parent / "real"
            real.mkdir(mode=0o700)
            link = parent / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(s11.StateRefused):
                s11.AtomicStateStore(link)

            store = s11.AtomicStateStore(real)
            store.acquire()

            def fault(point: str) -> None:
                if point == "after_atomic_replace":
                    raise OSError("simulated power interruption")

            with self.assertRaises(s11.PublicationIndeterminate):
                store.write("state.json", {"phase": "staged"}, fault=fault)
            self.assertEqual(store.read("state.json")["phase"], "staged")
            store.close()

    def test_pre_replace_fault_leaves_no_promoted_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.chmod(root, 0o700)
            store = s11.AtomicStateStore(root)
            store.acquire()

            def fault(point: str) -> None:
                if point == "after_complete_write":
                    raise OSError("simulated interruption")

            with self.assertRaises(OSError):
                store.write("state.json", {"phase": "verified"}, fault=fault)
            self.assertFalse((root / "state.json").exists())
            self.assertFalse(any(path.name.endswith(".tmp") for path in root.iterdir()))
            store.close()


def configured_coordinator(**overrides):
    options = dict(active_slot="A", current_version=10, current_image_sha256=SOURCE_DIGEST,
                   signature_verifier=s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,)), clock=lambda: NOW)
    options.update(overrides)
    return s11.UpdateCoordinator(**options)


def admit(c, payload=None):
    payload = manifest() if payload is None else payload
    return c.verify_manifest(payload, now_unix=NOW, signature=SIGNATURES[payload])


def private_image(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    os.chmod(path, 0o600)


def record_dispatch(journal, binding, status="terminal", **changes):
    record = {"schema": "trillionnium.desktop.update-dispatch-journal.v1", **vars(binding), "status": status, **changes}
    journal.write(f"dispatch-{binding.operation_id}.json", record)


def fork_results(operations, *, before_release=None, cleanup=None):
    """Run inherited authority after an explicit parent-to-child barrier."""
    ready_read, ready_write = os.pipe()
    result_read, result_write = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(ready_write)
        os.close(result_read)
        try:
            if os.read(ready_read, 1) != b"x":
                os._exit(2)
            result = {}
            for name, operation in operations.items():
                try:
                    operation()
                    result[name] = "returned"
                except BaseException as error:
                    result[name] = type(error).__name__
            if cleanup is not None:
                cleanup()
            os.write(result_write, json.dumps(result).encode())
            os._exit(0)
        except BaseException:
            os._exit(3)
    os.close(ready_read)
    os.close(result_write)
    reaped = False
    try:
        if before_release is not None:
            before_release()
        os.write(ready_write, b"x")
        if not select.select([result_read], [], [], 10)[0]:
            raise AssertionError("forked authority probe did not return")
        result = json.loads(os.read(result_read, 65536))
        _, status = os.waitpid(child, 0)
        reaped = True
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise AssertionError(f"forked authority probe failed: {status}")
        return result
    finally:
        os.close(ready_write)
        os.close(result_read)
        if not reaped:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)


class S11OwnershipTests(unittest.TestCase):
    def test_discarded_store_gc_on_foreign_thread_closes_fds_and_releases_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            store = s11.AtomicStateStore(Path(directory))
            store.acquire()
            store.write("state.json", {"durable": True})
            descriptors = store._root_fd, store._lease_fd
            reference = weakref.ref(store)
            last_reference = [store]
            del store
            def collect():
                last_reference.clear()
                gc.collect()
            thread = threading.Thread(target=collect)
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertIsNone(reference())
            for descriptor in descriptors:
                with self.assertRaises(OSError) as refused:
                    os.fstat(descriptor)
                self.assertEqual(refused.exception.errno, errno.EBADF)
            with s11.AtomicStateStore(Path(directory)) as successor:
                self.assertEqual(successor.read("state.json"), {"durable": True})

    def test_failed_constructor_cleanup_cannot_close_reused_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.chmod(root, 0o755)
            retained, descriptors = [], []
            actual_open = s11.AtomicStateStore._open_root
            def capture(owner):
                retained.append(owner)
                descriptor = actual_open(owner)
                descriptors.append(descriptor)
                return descriptor
            with patch.object(s11.AtomicStateStore, "_open_root", capture), self.assertRaises(s11.StateRefused):
                s11.AtomicStateStore(root)
            self.assertEqual(len(retained), 1)
            self.assertIsNone(retained[0]._root_fd)
            self.assertIsNone(retained[0]._lease_fd)
            reused = descriptors[0]
            with self.assertRaises(OSError) as refused:
                os.fstat(reused)
            self.assertEqual(refused.exception.errno, errno.EBADF)
            source = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
            try:
                if source != reused:
                    os.dup2(source, reused, inheritable=False)
                retained.clear()
                gc.collect()
                self.assertTrue(stat.S_ISCHR(os.fstat(reused).st_mode))
            finally:
                os.close(source)
                if source != reused:
                    os.close(reused)

    def test_child_close_cannot_release_parent_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            with s11.AtomicStateStore(Path(directory)) as store:
                store.write("state.json", {"owner": "parent"})
                self.assertEqual(fork_results({"close": store.close}), {"close": "returned"})
                contender = s11.AtomicStateStore(Path(directory))
                try:
                    with self.assertRaises(s11.CoordinatorBusy):
                        contender.acquire()
                finally:
                    contender.close()
                self.assertEqual(store.read("state.json"), {"owner": "parent"})
            with s11.AtomicStateStore(Path(directory)) as reacquired:
                self.assertEqual(reacquired.read("state.json"), {"owner": "parent"})

    def test_inherited_health_permit_cannot_commit_after_parent_boot_failure(self):
        c = configured_coordinator()
        ticket = admit(c)
        c.stage_image(ticket, TARGET, now_unix=NOW)
        c.arm_first_boot(ticket, now_unix=NOW)
        c.record_booted_image(ticket, slot="B", image_sha256=TARGET_DIGEST)
        permit = c.record_health(ticket, stable_seconds=60, health_receipt_sha256=RECEIPT)
        result = fork_results({"commit": lambda: c.commit(permit)},
                              before_release=lambda: c.record_boot_failure(ticket))
        self.assertEqual(result, {"commit": "StateRefused"})
        self.assertEqual(c.phase, s11.Phase.BOOT_PENDING)
        self.assertEqual(c.active_slot, "A")
        with self.assertRaises(s11.StateRefused):
            c.commit(permit)

    def test_forked_verifier_store_staging_and_reconciliation_are_refused(self):
        payload = manifest()
        verifier = s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,))
        c = configured_coordinator()
        ticket = admit(c, payload)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slots = root / "slots"
            slots.mkdir(mode=0o700)
            journal_root = root / "journal"
            journal_root.mkdir(mode=0o700)
            image = root / "candidate.img"
            private_image(image, TARGET)
            private_image(slots / "slot-A.img", SOURCE)
            private_image(slots / "slot-B.img", b"old-inactive-image")
            with s11.ImageSlotStore(slots, active_slot="A") as store, s11.DurableUpdateJournal(journal_root) as journal:
                store.write("state.json", {"owner": "parent"})
                recovery = configured_coordinator(journal_authority=journal)
                recovery_ticket = admit(recovery, payload)
                binding = recovery.mark_possible_dispatch(recovery_ticket)
                record_dispatch(journal, binding)
                fact = recovery.verify_journal_reconciliation(recovery_ticket)
                result = fork_results({
                    "verify": lambda: verifier.verify(payload, SIGNATURES[payload], now_unix=NOW),
                    "revalidate": lambda: verifier.revalidate(ticket.signature_admission, now_unix=NOW),
                    "admit": lambda: c.verify_manifest(payload, signature=SIGNATURES[payload], now_unix=NOW),
                    "stage": lambda: c.stage_image_file(ticket, image, store, now_unix=NOW),
                    "slot_reconcile": lambda: store.reconcile_image(ticket),
                    "acquire": store.acquire,
                    "read": lambda: store.read("state.json"),
                    "write": lambda: store.write("child.json", {"owner": "child"}),
                    "confirm": lambda: journal.confirm_dispatch(binding),
                    "verify_reconcile": lambda: recovery.verify_journal_reconciliation(recovery_ticket),
                    "reconcile": lambda: recovery.reconcile_possible_dispatch(fact),
                    "startup": lambda: c.reconcile_startup({"A": SOURCE_DIGEST, "B": TARGET_DIGEST}),
                    "inherited_verifier_configuration": lambda: s11.UpdateCoordinator(active_slot="A", current_version=10, current_image_sha256=SOURCE_DIGEST, signature_verifier=verifier),
                    "inherited_journal_configuration": lambda: configured_coordinator(journal_authority=journal),
                }, cleanup=lambda: (store.close(), journal.close()))
                self.assertEqual(result, {name: "ManifestRefused" if name in {"verify", "revalidate", "inherited_verifier_configuration"} else "StateRefused" for name in result})
                self.assertEqual(len(result), 14)
                self.assertEqual((slots / "slot-B.img").read_bytes(), b"old-inactive-image")
                self.assertFalse((slots / "child.json").exists())
                self.assertEqual(store.read("state.json"), {"owner": "parent"})
                self.assertTrue(recovery.effect_reconciliation_required)
                recovery.reconcile_possible_dispatch(fact)
                self.assertEqual(recovery.phase, s11.Phase.ROLLBACK_PENDING)

    def test_authority_requires_creating_thread_before_crypto_or_storage(self):
        payload = manifest()
        verifier = s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,))
        c = configured_coordinator()
        ticket = admit(c, payload)
        with tempfile.TemporaryDirectory() as directory, s11.AtomicStateStore(Path(directory)) as store:
            store.write("state.json", {"owner": "parent"})
            result = {}
            def foreign_thread():
                for name, operation in {
                    "verify": lambda: verifier.verify(payload, SIGNATURES[payload], now_unix=NOW),
                    "stage": lambda: c.stage_image(ticket, TARGET, now_unix=NOW),
                    "read": lambda: store.read("state.json"),
                    "write": lambda: store.write("thread.json", {}),
                    "close": store.close,
                }.items():
                    try:
                        operation()
                        result[name] = "returned"
                    except BaseException as error:
                        result[name] = type(error).__name__
            thread = threading.Thread(target=foreign_thread)
            with patch.object(s11.subprocess, "run", side_effect=AssertionError("foreign thread reached crypto")):
                thread.start()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, {"verify": "ManifestRefused", "stage": "StateRefused", "read": "StateRefused", "write": "StateRefused", "close": "StateRefused"})
            self.assertFalse((Path(directory) / "thread.json").exists())
            self.assertEqual(c.phase, s11.Phase.VERIFIED)
            self.assertEqual(store.read("state.json"), {"owner": "parent"})


class S11SignedAdmissionTests(unittest.TestCase):
    def test_callback_verifier_and_root_subclasses_refused_before_authority(self):
        calls = []
        value = json.loads(manifest())
        payload = signed_payload(value, signer="other")
        # A callback can fabricate correctly shaped facts for a real wrong-key
        # signature. The coordinator must reject the callback itself.
        fake = s11.SignatureAdmission(TRUST_ROOT.signer_id, TRUST_ROOT.expected_public_key_sha256,
            hashlib.sha256(SIGNATURES[payload]).hexdigest(), hashlib.sha256(s11.manifest_signing_bytes(payload)).hexdigest(),
            s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,)).policy_sha256, 10, NOW, s11._SEAL)
        class CallbackVerifier(s11.ExternalUpdateSignatureVerifier):
            def verify(self, *args, **kwargs):
                calls.append("verify")
                return fake
        with self.assertRaises(s11.StateRefused):
            configured_coordinator(signature_verifier=CallbackVerifier((TRUST_ROOT,)))
        self.assertEqual(calls, [])
        with self.assertRaises(s11.ManifestRefused):
            s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,)).verify(payload, SIGNATURES[payload], now_unix=NOW)
        class CallbackRoot(s11.UpdateTrustRoot):
            pass
        alternate = CallbackRoot(**vars(TRUST_ROOT))
        with self.assertRaises(s11.ManifestRefused):
            s11.ExternalUpdateSignatureVerifier((alternate,))

    def test_sealed_inputs_refuse_actual_wrong_signer_key_substitution(self):
        payload = signed_payload(json.loads(manifest()), signer="other")
        verifier = s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,))
        actual_run = subprocess.run
        attempts = []
        def substitute_key(arguments, **kwargs):
            key_path = Path(arguments[arguments.index("-verify") + 1])
            self.assertTrue(str(key_path).startswith("/proc/self/fd/"))
            with self.assertRaises(OSError):
                key_path.write_bytes((Path(TEST_KEYS.name) / "other.public").read_bytes())
            attempts.append(True)
            return actual_run(arguments, **kwargs)
        with patch.object(s11.subprocess, "run", side_effect=substitute_key), self.assertRaises(s11.ManifestRefused):
            verifier.verify(payload, SIGNATURES[payload], now_unix=NOW)
        self.assertEqual(attempts, [True])

    def test_real_crypto_inputs_are_sealed_environment_fixed_and_fds_closed(self):
        payload = manifest()
        actual_run = subprocess.run
        descriptors = []
        def inspect_inputs(arguments, **kwargs):
            self.assertEqual(arguments[:4], ["/usr/bin/openssl", "dgst", "-sha256", "-verify"])
            self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"})
            self.assertEqual(len(kwargs["pass_fds"]), 3)
            for descriptor in kwargs["pass_fds"]:
                seals = s11.fcntl.fcntl(descriptor, s11.fcntl.F_GET_SEALS)
                required = s11.fcntl.F_SEAL_WRITE | s11.fcntl.F_SEAL_GROW | s11.fcntl.F_SEAL_SHRINK | s11.fcntl.F_SEAL_SEAL
                self.assertEqual(seals & required, required)
                with self.assertRaises(OSError):
                    os.write(descriptor, b"replace")
                with self.assertRaises(OSError):
                    os.ftruncate(descriptor, 0)
                descriptors.append(descriptor)
            return actual_run(arguments, **kwargs)
        c = configured_coordinator()
        with patch.object(s11.subprocess, "run", side_effect=inspect_inputs):
            ticket = admit(c, payload)
        self.assertEqual(ticket.signature_admission.public_key_sha256, TRUST_ROOT.expected_public_key_sha256)
        self.assertEqual(len(descriptors), 3)
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_snapshot_write_failure_closes_fds_and_never_verifies(self):
        payload = manifest()
        verifier = s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,))
        actual_create = os.memfd_create
        descriptors = []
        def create(*args):
            descriptor = actual_create(*args)
            descriptors.append(descriptor)
            return descriptor
        with patch.object(s11.os, "memfd_create", side_effect=create), patch.object(s11.os, "write", side_effect=OSError("snapshot unavailable")), patch.object(s11.subprocess, "run") as process:
            with self.assertRaises(s11.ManifestRefused):
                verifier.verify(payload, SIGNATURES[payload], now_unix=NOW)
        process.assert_not_called()
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])

    def test_permits_and_tickets_cannot_cross_coordinator_instances(self):
        first, second = configured_coordinator(), configured_coordinator()
        payload = manifest()
        first_ticket, second_ticket = admit(first, payload), admit(second, payload)
        with self.assertRaises(s11.StateRefused):
            second.stage_image(first_ticket, TARGET, now_unix=NOW)
        for c, ticket in ((first, first_ticket), (second, second_ticket)):
            c.stage_image(ticket, TARGET, now_unix=NOW)
            c.arm_first_boot(ticket, now_unix=NOW)
            c.record_booted_image(ticket, slot="B", image_sha256=TARGET_DIGEST)
        first_permit = first.record_health(first_ticket, stable_seconds=60, health_receipt_sha256=RECEIPT)
        with self.assertRaises(s11.StateRefused):
            second.commit(first_permit)
        self.assertEqual(second.phase, s11.Phase.HEALTH_PENDING)
        second_permit = second.record_health(second_ticket, stable_seconds=60, health_receipt_sha256=RECEIPT)
        with self.assertRaises(s11.StateRefused):
            second.commit(replace(second_permit))
        second.commit(second_permit)
        first.commit(first_permit)

    def test_health_permit_expires_on_boot_failure_and_cannot_commit_expired_admission(self):
        now = [NOW]
        c = configured_coordinator(clock=lambda: now[0])
        ticket = admit(c)
        c.stage_image(ticket, TARGET, now_unix=NOW)
        c.arm_first_boot(ticket, now_unix=NOW)
        c.record_booted_image(ticket, slot="B", image_sha256=TARGET_DIGEST)
        permit = c.record_health(ticket, stable_seconds=60, health_receipt_sha256=RECEIPT)
        c.record_boot_failure(ticket)
        c.record_booted_image(ticket, slot="B", image_sha256=TARGET_DIGEST)
        with self.assertRaises(s11.StateRefused):
            c.commit(permit)
        current = c.record_health(ticket, stable_seconds=60, health_receipt_sha256=RECEIPT)
        now[0] = ticket.manifest.expires_unix
        with self.assertRaises(s11.ManifestRefused):
            c.commit(current)
        self.assertEqual(c.phase, s11.Phase.HEALTH_PENDING)
        self.assertEqual(c.current_image_sha256, SOURCE_DIGEST)

    def test_real_signature_and_domain_separated_preimage(self):
        payload = manifest()
        c = configured_coordinator()
        ticket = admit(c, payload)
        self.assertEqual(ticket.signature_admission.public_key_sha256, TRUST_ROOT.expected_public_key_sha256)
        value = json.loads(payload)
        unsigned = {k: v for k, v in value.items() if k != "signature_sha256"}
        self.assertEqual(s11.manifest_signing_bytes(payload), s11.SIGNATURE_DOMAIN + json.dumps(unsigned, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
        value["signature_sha256"] = "0" * 64
        self.assertEqual(s11.manifest_signing_bytes(payload), s11.manifest_signing_bytes(json.dumps(value)))

    def test_unsigned_default_wrong_key_and_actual_signature_digest_refused(self):
        payload = manifest()
        unsigned = s11.UpdateCoordinator(active_slot="A", current_version=10, current_image_sha256=SOURCE_DIGEST, clock=lambda: NOW)
        with self.assertRaisesRegex(s11.ManifestRefused, "disabled"):
            admit(unsigned, payload)
        with self.assertRaisesRegex(s11.ManifestRefused, "failed"):
            admit(configured_coordinator(signature_verifier=s11.ExternalUpdateSignatureVerifier((OTHER_ROOT,))), payload)
        for signature in (None, b"", SIGNATURES[payload] + b"x", b"x" * (s11.MAX_SIGNATURE_BYTES + 1)):
            with self.subTest(signature_bytes=0 if signature is None else len(signature)), self.assertRaises(s11.ManifestRefused):
                configured_coordinator().verify_manifest(payload, signature=signature, now_unix=NOW)

    def test_every_authority_field_is_signed_even_with_valid_envelope_digest(self):
        payload = manifest()
        changes = {"target_version": 12, "target_slot": "A", "target_image_sha256": "0" * 64,
                   "target_image_bytes": 13, "rollback_floor": 9, "expires_unix": 2_000_001,
                   "source_version": 9, "source_image_sha256": "0" * 64,
                   "repository": "attacker/repo", "schema": "attacker", "signer_id": "other"}
        verifier = s11.ExternalUpdateSignatureVerifier((TRUST_ROOT,))
        for field, changed in changes.items():
            altered = {**json.loads(payload), field: changed}
            with self.subTest(field=field), self.assertRaises(s11.ManifestRefused):
                verifier.verify(json.dumps(altered), SIGNATURES[payload], now_unix=NOW)

    def test_unapproved_revoked_expired_or_unpinned_roots_refused(self):
        payload = manifest()
        roots = (replace(TRUST_ROOT, signer_id="unknown"), replace(TRUST_ROOT, revoked=True),
                 replace(TRUST_ROOT, valid_until_unix=NOW), replace(TRUST_ROOT, valid_from_unix=NOW + 1))
        for root in roots:
            with self.subTest(root=root.signer_id, revoked=root.revoked, validity=root.valid_until_unix), self.assertRaises(s11.ManifestRefused):
                admit(configured_coordinator(signature_verifier=s11.ExternalUpdateSignatureVerifier((root,))), payload)
        with self.assertRaises(s11.ManifestRefused):
            replace(TRUST_ROOT, expected_public_key_sha256="0" * 64)
        with self.assertRaises(s11.ManifestRefused):
            s11.ExternalUpdateSignatureVerifier((TRUST_ROOT, TRUST_ROOT))

    def test_floor_and_clock_cannot_be_weakened(self):
        for payload in (manifest(rollback_floor=9), manifest(expires_unix=NOW)):
            with self.subTest(payload=payload), self.assertRaises(s11.ManifestRefused):
                admit(configured_coordinator(), payload)
        with self.assertRaises(s11.ManifestRefused):
            admit(configured_coordinator(signature_verifier=s11.ExternalUpdateSignatureVerifier((replace(TRUST_ROOT, minimum_version=11),))))
        payload = manifest()
        with self.assertRaisesRegex(s11.ManifestRefused, "trusted clock"):
            configured_coordinator().verify_manifest(payload, signature=SIGNATURES[payload], now_unix=NOW - 10)

    def test_expiry_clock_regression_and_policy_change_rechecked_before_stage_and_boot(self):
        for operation in ("stage", "boot"):
            now = [NOW]
            c = configured_coordinator(clock=lambda: now[0])
            ticket = admit(c)
            if operation == "boot":
                c.stage_image(ticket, TARGET, now_unix=NOW)
            now[0] = ticket.manifest.expires_unix
            with self.subTest(operation=operation), self.assertRaises(s11.ManifestRefused):
                c.stage_image(ticket, TARGET, now_unix=now[0]) if operation == "stage" else c.arm_first_boot(ticket, now_unix=now[0])
        now = [NOW]
        c = configured_coordinator(clock=lambda: now[0])
        ticket = admit(c)
        now[0] -= 1
        with self.assertRaisesRegex(s11.ManifestRefused, "regressed"):
            c.stage_image(ticket, TARGET, now_unix=now[0])
        now[0] = NOW
        c._signature_verifier = s11.ExternalUpdateSignatureVerifier((replace(TRUST_ROOT, revoked=True),))
        with self.assertRaisesRegex(s11.ManifestRefused, "stale trust policy"):
            c.stage_image(ticket, TARGET, now_unix=NOW)

    def test_openssl_unavailable_or_timeout_is_not_signature_success(self):
        payload = manifest()
        for failure in (OSError("absent"), subprocess.TimeoutExpired("openssl", 15)):
            with self.subTest(failure=type(failure).__name__), patch.object(s11.subprocess, "run", side_effect=failure), self.assertRaises(s11.ManifestRefused):
                admit(configured_coordinator(), payload)


class S11ImagePublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.slot_root = self.root / "slots"
        self.slot_root.mkdir(mode=0o700)
        self.image = self.root / "candidate.img"
        private_image(self.image, TARGET)
        private_image(self.slot_root / "slot-A.img", SOURCE)
        private_image(self.slot_root / "slot-B.img", b"old-inactive-image")

    def tearDown(self):
        self.directory.cleanup()

    def test_callback_journal_and_slot_subclasses_refused_before_authority(self):
        calls = []
        class CallbackJournal(s11.DurableUpdateJournal):
            def confirm_dispatch(self, binding):
                calls.append("journal")
                return JOURNAL, "terminal", (1, 2, 3, 4)
        with CallbackJournal(self.root) as journal:
            with self.assertRaises(s11.StateRefused):
                configured_coordinator(journal_authority=journal)
        c = configured_coordinator()
        ticket = admit(c)
        fake = s11.ImageStageReceipt("B", TARGET_DIGEST, len(TARGET), ticket.manifest.manifest_sha256, ticket.manifest.signature_sha256)
        class CallbackSlots(s11.ImageSlotStore):
            def _publish_verified_image(self, *args, **kwargs):
                calls.append("stage")
                return fake
            def reconcile_image(self, *args, **kwargs):
                calls.append("reconcile")
                return fake
        with CallbackSlots(self.slot_root, active_slot="A") as slots:
            with self.assertRaises(s11.StateRefused):
                c.stage_image_file(ticket, self.image, slots, now_unix=NOW)
        self.assertEqual(c.phase, s11.Phase.VERIFIED)
        self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), b"old-inactive-image")
        def interrupt(point):
            if point == "after_atomic_replace":
                raise KeyboardInterrupt()
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as slots:
            with self.assertRaises(s11.ImagePublicationIndeterminate):
                c.stage_image_file(ticket, self.image, slots, now_unix=NOW, fault=interrupt)
        with CallbackSlots(self.slot_root, active_slot="A") as slots:
            with self.assertRaises(s11.StateRefused):
                c.reconcile_image_publication(ticket, slots, now_unix=NOW)
        self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
        self.assertEqual(calls, [])

    def test_streamed_real_signed_publication_is_durable_and_inactive_only(self):
        c = configured_coordinator()
        ticket = admit(c)
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
            with patch.object(s11.os, "pread", wraps=os.pread) as reader:
                receipt = c.stage_image_file(ticket, self.image, store, now_unix=NOW)
            self.assertTrue(reader.called)
            self.assertTrue(all(call.args[1] <= 1024 * 1024 for call in reader.call_args_list))
            self.assertEqual(receipt.image_sha256, TARGET_DIGEST)
            self.assertFalse(receipt.production_activation_enabled)
            with self.assertRaises(s11.StateRefused):
                store.write("slot-A.img", {"overwrite": True})
        self.assertEqual(c.phase, s11.Phase.STAGED)
        self.assertEqual((self.slot_root / "slot-A.img").read_bytes(), SOURCE)
        self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), TARGET)
        self.assertEqual(stat.S_IMODE((self.slot_root / "slot-B.img").stat().st_mode), 0o600)

    def test_bad_complete_image_or_active_slot_refused_before_any_write(self):
        for kind in ("trailer", "corrupt", "source"):
            private_image(self.image, TARGET + b"x" if kind == "trailer" else b"wrong-image" if kind == "corrupt" else TARGET)
            private_image(self.slot_root / "slot-A.img", b"wrong-source" if kind == "source" else SOURCE)
            c = configured_coordinator()
            ticket = admit(c)
            with s11.ImageSlotStore(self.slot_root, active_slot="A") as store, patch.object(s11.os, "write", wraps=os.write) as writer:
                with self.subTest(kind=kind), self.assertRaises(s11.StateRefused):
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW)
                self.assertFalse(writer.called)
            self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), b"old-inactive-image")

    def test_large_stream_and_partial_writes_preserve_complete_image(self):
        target = b"streamed-image-" * 160_000
        digest = hashlib.sha256(target).hexdigest()
        private_image(self.image, target)
        c = configured_coordinator()
        ticket = admit(c, manifest(target_image_sha256=digest, target_image_bytes=len(target)))
        original_write = os.write
        def short_write(descriptor, chunk):
            return original_write(descriptor, chunk[:max(1, len(chunk) // 2)])
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store, patch.object(s11.os, "write", side_effect=short_write) as writer, patch.object(s11.os, "pread", wraps=os.pread) as reader:
            c.stage_image_file(ticket, self.image, store, now_unix=NOW)
        self.assertGreater(writer.call_count, 3)
        self.assertTrue(any(call.args[1] == 1024 * 1024 for call in reader.call_args_list))
        self.assertTrue(all(call.args[1] <= 1024 * 1024 for call in reader.call_args_list))
        self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), target)

    def test_unsafe_images_slots_and_unleased_store_refused(self):
        c = configured_coordinator()
        ticket = admit(c)
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
            for mode in (0o644, 0o666):
                os.chmod(self.slot_root / "slot-B.img", mode)
                with self.subTest(mode=mode), self.assertRaises(s11.StateRefused):
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW)
            os.chmod(self.slot_root / "slot-B.img", 0o600)
            os.link(self.slot_root / "slot-B.img", self.root / "hardlink")
            with self.assertRaises(s11.StateRefused):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW)
            (self.root / "hardlink").unlink()
            link = self.root / "candidate-link"
            link.symlink_to(self.image)
            with self.assertRaises(s11.StateRefused):
                c.stage_image_file(ticket, link, store, now_unix=NOW)
        store = s11.ImageSlotStore(self.slot_root, active_slot="A")
        try:
            with self.assertRaises(s11.CoordinatorBusy):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW)
        finally:
            store.close()

    def test_pre_publication_faults_preserve_active_and_existing_inactive_images(self):
        for point in ("before_temp_create", "after_temp_create", "after_complete_write", "after_file_fsync"):
            c = configured_coordinator()
            ticket = admit(c)
            def fault(current):
                if current == point:
                    raise OSError("cutpoint interruption")
            with s11.ImageSlotStore(self.slot_root, active_slot="A") as store, self.subTest(point=point), self.assertRaises(OSError):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW, fault=fault)
            self.assertEqual(c.phase, s11.Phase.VERIFIED)
            self.assertEqual((self.slot_root / "slot-A.img").read_bytes(), SOURCE)
            self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), b"old-inactive-image")
            self.assertFalse(list(self.slot_root.glob("*.tmp")))

    def test_temp_substitution_and_source_growth_cannot_publish(self):
        for kind in ("temp", "source", "target", "lease"):
            c = configured_coordinator()
            ticket = admit(c)
            def fault(current):
                if current == "after_temp_create" and kind == "source":
                    with self.image.open("ab") as stream:
                        stream.write(b"trailer")
                if current == "after_file_fsync":
                    if kind == "temp":
                        temp = next(self.slot_root.glob("*.tmp"))
                        temp.unlink()
                        temp.symlink_to(self.image)
                    elif kind == "target":
                        (self.slot_root / "slot-B.img").rename(self.slot_root / "saved.img")
                        private_image(self.slot_root / "slot-B.img", b"foreign-new-image")
                    elif kind == "lease":
                        (self.slot_root / ".coordinator.lock").rename(self.slot_root / ".saved-lock")
            with s11.ImageSlotStore(self.slot_root, active_slot="A") as store, self.subTest(kind=kind), self.assertRaises(s11.StateRefused):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW, fault=fault)
            self.assertEqual(c.phase, s11.Phase.VERIFIED)
            self.assertEqual((self.slot_root / "slot-A.img").read_bytes(), SOURCE)
            if kind == "temp":
                temp = next(self.slot_root.glob("*.tmp"))
                self.assertTrue(temp.is_symlink())
                temp.unlink()
            if kind == "target":
                private_image(self.slot_root / "slot-B.img", b"old-inactive-image")
            if kind == "lease":
                (self.slot_root / ".saved-lock").rename(self.slot_root / ".coordinator.lock")
            private_image(self.image, TARGET)

    def test_expiry_during_copy_refuses_publication(self):
        now = [NOW]
        c = configured_coordinator(clock=lambda: now[0])
        ticket = admit(c)
        def fault(point):
            if point == "after_file_fsync":
                now[0] = ticket.manifest.expires_unix
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store, self.assertRaises(s11.ManifestRefused):
            c.stage_image_file(ticket, self.image, store, now_unix=NOW, fault=fault)
        self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), b"old-inactive-image")
        self.assertEqual(c.phase, s11.Phase.VERIFIED)

    def test_post_replace_uncertainty_requires_fsync_reconciliation_without_rewrite(self):
        for point in ("after_atomic_replace", "after_directory_fsync"):
            c = configured_coordinator()
            ticket = admit(c)
            def fault(current):
                if current == point:
                    raise OSError("cutpoint interruption")
            with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
                with self.subTest(point=point), self.assertRaises(s11.ImagePublicationIndeterminate):
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW, fault=fault)
                self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
                with patch.object(s11.os, "fsync", side_effect=OSError("durability unresolved")) as sync, self.assertRaises(s11.ImagePublicationIndeterminate):
                    c.reconcile_image_publication(ticket, store, now_unix=NOW)
                self.assertTrue(sync.called)
                self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
                with patch.object(s11.os, "write", side_effect=AssertionError("reconciliation must not rewrite")), patch.object(s11.os, "fsync", wraps=os.fsync) as sync:
                    receipt = c.reconcile_image_publication(ticket, store, now_unix=NOW)
                self.assertEqual(sync.call_count, 2)
                self.assertEqual(receipt.image_sha256, TARGET_DIGEST)
                self.assertEqual(c.phase, s11.Phase.STAGED)

    def test_approved_operator_rollback_binds_source_and_never_clears_dispatch_latch(self):
        source = self.root / "source.img"
        private_image(source, SOURCE)
        denied = configured_coordinator()
        with self.assertRaises(s11.StateRefused):
            denied.request_operator_rollback(admit(denied), source)
        journal_root = self.root / "journal"
        journal_root.mkdir(mode=0o700)
        journal = s11.DurableUpdateJournal(journal_root)
        journal.acquire()
        self.addCleanup(journal.close)
        c = configured_coordinator(recovery_operator_uids=frozenset({os.geteuid()}), journal_authority=journal)
        ticket = admit(c)
        private_image(source, b"substituted")
        with self.assertRaises(s11.RecoveryRequired):
            c.request_operator_rollback(ticket, source)
        private_image(source, SOURCE)
        binding = c.mark_possible_dispatch(ticket)
        with self.assertRaisesRegex(s11.StateRefused, "journal reconciliation"):
            c.request_operator_rollback(ticket, source)
        self.assertTrue(c.effect_reconciliation_required)
        record_dispatch(journal, binding)
        fact = c.verify_journal_reconciliation(ticket)
        c.reconcile_possible_dispatch(fact)
        decision = c.request_operator_rollback(ticket, source)
        self.assertEqual(decision.action, "rollback_only_no_replay")
        self.assertEqual(decision.operator_uid, os.geteuid())
        self.assertEqual(c.phase, s11.Phase.ROLLBACK_PENDING)

    def test_reconciliation_refuses_hardlinked_target_and_replaced_root(self):
        c = configured_coordinator()
        ticket = admit(c)
        def fault(point):
            if point == "after_atomic_replace":
                raise OSError("sync not observed")
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
            with self.assertRaises(s11.ImagePublicationIndeterminate):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW, fault=fault)
            os.link(self.slot_root / "slot-B.img", self.root / "target-hardlink")
            with self.assertRaises(s11.ImagePublicationIndeterminate):
                c.reconcile_image_publication(ticket, store, now_unix=NOW)
            (self.root / "target-hardlink").unlink()
            original_sync = os.fsync
            changed = [False]
            def change_root(descriptor):
                original_sync(descriptor)
                if not changed[0]:
                    self.slot_root.rename(self.root / "detached-slots")
                    self.slot_root.mkdir(mode=0o700)
                    changed[0] = True
            with patch.object(s11.os, "fsync", side_effect=change_root), self.assertRaises(s11.ImagePublicationIndeterminate):
                c.reconcile_image_publication(ticket, store, now_unix=NOW)
            self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
            self.assertFalse((self.slot_root / "slot-B.img").exists())

    def test_image_reconciliation_cannot_clear_unrelated_boot_failure(self):
        c = configured_coordinator()
        ticket = admit(c)
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
            c.stage_image_file(ticket, self.image, store, now_unix=NOW)
            c.arm_first_boot(ticket, now_unix=NOW)
            with self.assertRaises(s11.RecoveryRequired):
                c.record_booted_image(ticket, slot="B", image_sha256="0" * 64)
            with self.assertRaisesRegex(s11.StateRefused, "no indeterminate image publication"):
                c.reconcile_image_publication(ticket, store, now_unix=NOW)
            self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)

    def test_post_replace_interrupts_are_indeterminate_and_cannot_restaging(self):
        for error_type in (KeyboardInterrupt, SystemExit):
            c = configured_coordinator()
            ticket = admit(c)
            def fault(point):
                if point == "after_atomic_replace":
                    raise error_type("process interruption")
            with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
                with self.subTest(error_type=error_type.__name__), self.assertRaises(s11.ImagePublicationIndeterminate) as caught:
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW, fault=fault)
                self.assertIsInstance(caught.exception.cause, error_type)
                self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
                self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), TARGET)
                with self.assertRaises(s11.StateRefused):
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW)
                with patch.object(s11.os, "fsync", side_effect=error_type("reconciliation interrupted")), self.assertRaises(s11.ImagePublicationIndeterminate) as caught:
                    c.reconcile_image_publication(ticket, store, now_unix=NOW)
                self.assertIsInstance(caught.exception.cause, error_type)
                self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)

    def test_atomic_state_post_replace_interrupts_preserve_uncertainty(self):
        for error_type in (KeyboardInterrupt, SystemExit):
            def fault(point):
                if point == "after_atomic_replace":
                    raise error_type("process interruption")
            with s11.AtomicStateStore(self.slot_root) as store:
                with self.subTest(error_type=error_type.__name__), self.assertRaises(s11.PublicationIndeterminate) as caught:
                    store.write("state.json", {"phase": "staged"}, fault=fault)
                self.assertIsInstance(caught.exception.cause, error_type)
                self.assertEqual(store.read("state.json"), {"phase": "staged"})

    def test_replace_effect_then_interrupt_before_return_is_indeterminate(self):
        original_replace = os.replace
        for error_type in (KeyboardInterrupt, SystemExit):
            def effect_then_interrupt(*args, **kwargs):
                original_replace(*args, **kwargs)
                raise error_type("replacement happened before return")
            c = configured_coordinator()
            ticket = admit(c)
            with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
                with patch.object(s11.os, "replace", side_effect=effect_then_interrupt), self.subTest(error_type=error_type.__name__), self.assertRaises(s11.ImagePublicationIndeterminate) as caught:
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW)
                self.assertIsInstance(caught.exception.cause, error_type)
                self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), TARGET)
                self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
                with self.assertRaises(s11.StateRefused):
                    c.stage_image_file(ticket, self.image, store, now_unix=NOW)
                c.reconcile_image_publication(ticket, store, now_unix=NOW)
                self.assertEqual(c.phase, s11.Phase.STAGED)
            with s11.AtomicStateStore(self.slot_root) as store:
                with patch.object(s11.os, "replace", side_effect=effect_then_interrupt), self.assertRaises(s11.PublicationIndeterminate) as caught:
                    store.write("state.json", {"phase": "staged"})
                self.assertIsInstance(caught.exception.cause, error_type)
                self.assertEqual(store.read("state.json"), {"phase": "staged"})

    def test_publication_return_interrupt_still_retains_recovery_intent(self):
        c = configured_coordinator()
        ticket = admit(c)
        with s11.ImageSlotStore(self.slot_root, active_slot="A") as store:
            publish = store._publish_verified_image
            def completed_then_interrupt(*args, **kwargs):
                publish(*args, **kwargs)
                raise KeyboardInterrupt("interrupt before coordinator resumes")
            with patch.object(store, "_publish_verified_image", side_effect=completed_then_interrupt), self.assertRaises(s11.ImagePublicationIndeterminate):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW)
            self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)
            self.assertEqual((self.slot_root / "slot-B.img").read_bytes(), TARGET)
            with self.assertRaises(s11.StateRefused):
                c.stage_image_file(ticket, self.image, store, now_unix=NOW)
            c.reconcile_image_publication(ticket, store, now_unix=NOW)


class S11DurableJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.journal = s11.DurableUpdateJournal(self.root)
        self.journal.acquire()
        self.c = configured_coordinator(journal_authority=self.journal)
        self.ticket = admit(self.c)
        self.binding = self.c.mark_possible_dispatch(self.ticket)
        self.path = self.root / f"dispatch-{self.binding.operation_id}.json"

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def test_caller_hash_and_status_cannot_mint_reconciliation(self):
        c = configured_coordinator()
        ticket = admit(c)
        c.mark_possible_dispatch(ticket)
        with self.assertRaises(TypeError):
            c.verify_journal_reconciliation(ticket, journal_record_sha256="0" * 64, status="terminal")
        with self.assertRaisesRegex(s11.StateRefused, "configured durable journal authority"):
            c.verify_journal_reconciliation(ticket)
        self.assertTrue(c.effect_reconciliation_required)
        self.assertEqual(c.phase, s11.Phase.RECOVERY_REQUIRED)

    def test_complete_bound_durable_record_and_revalidation_clear_only_to_rollback(self):
        record_dispatch(self.journal, self.binding, status="indeterminate")
        with patch.object(s11.os, "write", side_effect=AssertionError("reconciliation must not write")), patch.object(s11.os, "fsync", wraps=os.fsync) as sync:
            fact = self.c.verify_journal_reconciliation(self.ticket)
            self.assertEqual(fact.journal_record_sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())
            self.assertEqual(fact.operation_id, self.binding.operation_id)
            self.c.reconcile_possible_dispatch(fact)
        self.assertEqual(sync.call_count, 4)
        self.assertFalse(self.c.effect_reconciliation_required)
        self.assertEqual(self.c.phase, s11.Phase.ROLLBACK_PENDING)

    def test_missing_malformed_wrong_operation_manifest_and_sequence_records_refused(self):
        with self.assertRaises(s11.StateRefused):
            self.c.verify_journal_reconciliation(self.ticket)
        for changes in ({"manifest_sha256": "0" * 64}, {"sequence": 2}, {"sequence": True},
                        {"operation_id": "0" * 64}, {"operation": "committed"}, {"target_slot": "A"},
                        {"image_sha256": "0" * 64}, {"status": "pending"}, {"status": []}, {"unexpected": True}):
            record_dispatch(self.journal, self.binding, **changes)
            with self.subTest(changes=changes), self.assertRaises(s11.StateRefused):
                self.c.verify_journal_reconciliation(self.ticket)
            self.assertTrue(self.c.effect_reconciliation_required)
        for data in (b'{"duplicate":1,"duplicate":2}', b'{"value":1e999}', b'{}', b'x' * (s11.MAX_STATE_BYTES + 1)):
            private_image(self.path, data)
            with self.subTest(data_size=len(data)), self.assertRaises(s11.StateRefused):
                self.c.verify_journal_reconciliation(self.ticket)

    def test_journal_custody_symlink_hardlink_and_unsafe_mode_refused(self):
        record_dispatch(self.journal, self.binding)
        os.chmod(self.path, 0o666)
        with self.assertRaises(s11.StateRefused):
            self.c.verify_journal_reconciliation(self.ticket)
        os.chmod(self.path, 0o600)
        linked = self.root / "extra-link"
        os.link(self.path, linked)
        with self.assertRaises(s11.StateRefused):
            self.c.verify_journal_reconciliation(self.ticket)
        linked.unlink()
        saved = self.root / "saved.json"
        self.path.rename(saved)
        self.path.symlink_to(saved)
        with self.assertRaises(s11.StateRefused):
            self.c.verify_journal_reconciliation(self.ticket)
        self.assertTrue(self.c.effect_reconciliation_required)

    def test_sync_failure_copied_fact_and_replaced_record_cannot_clear_latch(self):
        record_dispatch(self.journal, self.binding)
        with patch.object(s11.os, "fsync", side_effect=OSError("sync unresolved")), self.assertRaises(OSError):
            self.c.verify_journal_reconciliation(self.ticket)
        self.assertTrue(self.c.effect_reconciliation_required)
        fact = self.c.verify_journal_reconciliation(self.ticket)
        with self.assertRaises(s11.StateRefused):
            self.c.reconcile_possible_dispatch(replace(fact))
        record_dispatch(self.journal, self.binding)
        with self.assertRaisesRegex(s11.StateRefused, "changed before reconciliation"):
            self.c.reconcile_possible_dispatch(fact)
        self.assertTrue(self.c.effect_reconciliation_required)
        self.assertEqual(self.c.phase, s11.Phase.RECOVERY_REQUIRED)

    def test_replaced_journal_lease_cannot_confirm_operation(self):
        record_dispatch(self.journal, self.binding)
        (self.root / ".coordinator.lock").rename(self.root / ".saved-lock")
        with self.assertRaises(s11.StateRefused):
            self.c.verify_journal_reconciliation(self.ticket)
        self.assertTrue(self.c.effect_reconciliation_required)

    def test_journal_fact_cannot_cross_coordinator_instances(self):
        second = configured_coordinator(journal_authority=self.journal)
        second_ticket = admit(second)
        second_binding = second.mark_possible_dispatch(second_ticket)
        record_dispatch(self.journal, self.binding)
        record_dispatch(self.journal, second_binding)
        first_fact = self.c.verify_journal_reconciliation(self.ticket)
        second_fact = second.verify_journal_reconciliation(second_ticket)
        with self.assertRaises(s11.StateRefused):
            second.reconcile_possible_dispatch(first_fact)
        with self.assertRaises(s11.StateRefused):
            self.c.reconcile_possible_dispatch(second_fact)
        self.assertTrue(self.c.effect_reconciliation_required)
        self.assertTrue(second.effect_reconciliation_required)
        self.c.reconcile_possible_dispatch(first_fact)
        second.reconcile_possible_dispatch(second_fact)


if __name__ == "__main__":
    unittest.main()
