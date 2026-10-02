from __future__ import annotations

import errno
import fcntl
import gc
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import validate_platform_mechanisms as inventory_gate

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observer = load("test_update_boot_observer_source", ROOT / "platform/update_boot_observer.py")
fixture = load("test_update_boot_observer_real_crypto_fixture", ROOT / "tests/test_durable_update_owner.py")
cli = load("test_update_boot_observer_cli", ROOT / "tools/inspect_pending_update.py")


def setUpModule():
    if sys.platform != "linux":
        raise RuntimeError("Linux procfs/flock/fork corpus is required, never skipped")
    fixture.setUpModule()


def tearDownModule():
    fixture.tearDownModule()


def snapshot(root):
    return {path.name: (path.lstat(), path.read_bytes()) for path in root.iterdir()}


def descriptor_inventory():
    return fixture.fd_inventory()


class UpdateBootObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="source-boot-observer-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.state, self.slots = self.parent / "state", self.parent / "slots"
        self.state.mkdir(mode=0o700); self.slots.mkdir(mode=0o700)
        fixture.private_file(self.slots / "slot-A.img", fixture.SOURCE)
        fixture.private_file(self.slots / "slot-B.img", b"previous-inactive-image")
        self.owners = []
        self.addCleanup(self.release_owners)
        self.owner = self.new_owner()
        self.owner.close()

    def release_owners(self):
        for value in self.owners:
            value._closed = True
            value._release_descriptors()

    def new_owner(self):
        verifier = fixture.s11.ExternalUpdateSignatureVerifier((fixture.TRUST,))
        value = fixture.owner.DurableUpdateOwner(self.state, self.slots,
            active_slot="A", current_version=10, current_image_sha256=fixture.SOURCE_DIGEST,
            signature_verifier=verifier, protected_rollback_floor=10, clock=lambda: fixture.NOW)
        self.owners.append(value)
        return value

    def observe(self):
        return observer.inspect_pending_update(self.state, self.slots)

    def private(self, value):
        return json.loads(value.private_json())

    def assert_unavailable(self, value, reason=None):
        self.assertIn(value.status, (observer.ObservationStatus.UNAVAILABLE, observer.ObservationStatus.RECOVERY_REQUIRED))
        self.assertFalse(json.loads(value.public_json())["continuation_authorized"])
        if reason is not None:
            self.assertIn(reason, value.reasons)

    def rewrite(self, name, change):
        path = self.state / name
        value = json.loads(path.read_bytes())
        change(value)
        fixture.private_file(path, observer._canonical(value))

    def pending(self):
        value = self.new_owner()
        payload, signature = fixture.manifest()
        operation = value.verify_manifest(payload, now_unix=fixture.NOW, signature=signature)
        source = self.parent / "signed-target-image"
        fixture.private_file(source, fixture.TARGET)
        value.stage_image_file(operation, source, now_unix=fixture.NOW)
        value.arm_first_boot(operation, now_unix=fixture.NOW)
        # Fixture-only descriptor retirement models the persisted unfinished
        # session without writing a recovery marker. It grants no boot facts.
        value._closed = True
        value._release_descriptors()
        return value

    def command(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "tools/inspect_pending_update.py"),
            "--state-root", str(self.state), "--slot-root", str(self.slots), *arguments],
            capture_output=True, timeout=10)

    def test_clean_history_observes_actual_proc_without_writing_authority(self):
        before = snapshot(self.state), snapshot(self.slots)
        inventory = descriptor_inventory()
        value = self.observe()
        self.assertEqual(value.status, observer.ObservationStatus.NO_PENDING_UPDATE)
        raw = self.private(value)
        kernel = raw["diagnostic"]["kernel"]
        self.assertEqual(kernel["boot_id"], Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        root = os.stat("/")
        self.assertEqual(kernel["root_device"], [os.major(root.st_dev), os.minor(root.st_dev)])
        namespace = os.stat(f"/proc/{os.getpid()}/ns/mnt")
        self.assertEqual(kernel["mount_namespace_identity"], [namespace.st_dev, namespace.st_ino])
        self.assertEqual(raw["diagnostic"]["history"]["record_count"], 2)
        self.assertTrue(raw["diagnostic"]["history"]["structural_validation_only"])
        self.assertEqual((snapshot(self.state), snapshot(self.slots)), before)
        self.assertEqual(descriptor_inventory(), inventory)

    def test_real_signature_pending_history_never_becomes_boot_or_crypto_authority(self):
        self.pending()
        before = snapshot(self.state), snapshot(self.slots)
        value = self.observe()
        self.assertEqual(value.status, observer.ObservationStatus.PENDING_IDENTITY_UNKNOWN)
        raw = self.private(value)
        self.assertEqual(raw["diagnostic"]["history"]["last_kind"], "boot_policy_armed")
        self.assertEqual(raw["signature_authority"], "unavailable")
        self.assertEqual(raw["signed_boot_image_mapping"], "unknown")
        for key in ("booted_image_verified", "production_activation_enabled", "bootloader_effect_performed", "continuation_authorized"):
            self.assertIs(raw[key], False)
        self.assertEqual((snapshot(self.state), snapshot(self.slots)), before)

    def test_actual_exclusive_owner_is_busy_with_zero_writes_and_no_fd_leak(self):
        value = self.new_owner()
        before = snapshot(self.state), snapshot(self.slots)
        inventory = descriptor_inventory()
        self.assert_unavailable(self.observe(), observer.ObservationReason.OWNER_BUSY)
        self.assertEqual((snapshot(self.state), snapshot(self.slots)), before)
        self.assertEqual(descriptor_inventory(), inventory)
        self.assertEqual(value.phase, "idle")

    def test_existing_lease_is_same_inode_and_substitution_is_refused(self):
        original = observer._Reader.lease
        def swap(reader, root):
            original(reader, root)
            if len(reader.files) == 1:
                lease = self.state / ".coordinator.lock"
                lease.rename(self.parent / "old-lease")
                fixture.private_file(lease, b"")
        with patch.object(observer._Reader, "lease", swap):
            self.assert_unavailable(self.observe(), observer.ObservationReason.CUSTODY_UNAVAILABLE)

    def test_missing_lease_is_not_created_or_repaired(self):
        (self.state / ".coordinator.lock").unlink()
        before = snapshot(self.state), snapshot(self.slots)
        self.assert_unavailable(self.observe())
        self.assertEqual((snapshot(self.state), snapshot(self.slots)), before)

    def test_nonexistent_root_is_not_created(self):
        missing = self.parent / "unprovisioned"
        self.assert_unavailable(observer.inspect_pending_update(missing, self.slots))
        self.assertFalse(missing.exists())

    def test_unfinished_owner_and_actual_recovery_marker_are_diagnostics_only(self):
        value = self.new_owner()
        value._closed = True; value._release_descriptors()
        result = self.observe()
        self.assertEqual(result.status, observer.ObservationStatus.RECOVERY_REQUIRED)
        self.assertIn(observer.ObservationReason.UNFINISHED_OWNER, result.reasons)
        reopened = self.new_owner()
        self.assertEqual(reopened.phase, "recovery_required")
        reopened._closed = True; reopened._release_descriptors()
        before = snapshot(self.state)
        result = self.observe()
        self.assertIn(observer.ObservationReason.RECOVERY_MARKER, result.reasons)
        self.assertEqual(snapshot(self.state), before)

    def test_bool_float_extra_fields_and_noncanonical_records_are_refused(self):
        path = self.state / "update-event-000001.json"
        original = path.read_bytes()
        mutations = [lambda v: v.update(sequence=True), lambda v: v.update(sequence=1.0),
            lambda v: v.update(production_activation_enabled=0), lambda v: v.update(extra="fake"),
            lambda v: v["configuration"].update(state_root_identity=[True, self.state.stat().st_ino]),
            lambda v: v.update(observed_unix=True)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                fixture.private_file(path, original)
                self.rewrite(path.name, mutate)
                self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)
        for data in (original + b"\n", b'{"schema":1,"schema":2}', b"{}", b"", b"x" * (observer.MAX_RECORD_BYTES + 1)):
            with self.subTest(data=len(data)):
                fixture.private_file(path, data)
                self.assert_unavailable(self.observe())

    def test_sequence_gap_unknown_file_and_chain_drift_are_refused(self):
        path = self.state / "update-event-000002.json"
        original = path.read_bytes()
        self.rewrite(path.name, lambda v: v.update(previous_sha256="f" * 64))
        self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)
        fixture.private_file(path, original)
        path.rename(self.state / "update-event-000003.json")
        self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)
        (self.state / "update-event-000003.json").rename(path)
        fixture.private_file(self.state / "unrecognized.json", b"{}")
        self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)

    def test_record_symlink_hardlink_and_fifo_refused_without_blocking(self):
        path = self.state / "update-event-000002.json"
        original = path.read_bytes()
        target = self.parent / "victim"
        fixture.private_file(target, original)
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == "symlink":
                    path.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, path)
                else:
                    os.mkfifo(path, 0o600)
                self.assert_unavailable(self.observe())
                self.assertEqual(target.read_bytes(), original)
                path.unlink(); fixture.private_file(path, original)

    def test_slots_are_private_regular_single_link_metadata_only(self):
        path = self.slots / "slot-B.img"
        original = path.read_bytes()
        for kind in ("mode", "fifo", "symlink", "hardlink", "empty"):
            with self.subTest(kind=kind):
                path.unlink()
                target = self.parent / "target"
                fixture.private_file(target, original)
                if kind == "mode":
                    fixture.private_file(path, original); path.chmod(0o644)
                elif kind == "fifo":
                    os.mkfifo(path, 0o600)
                elif kind == "symlink":
                    path.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, path)
                else:
                    fixture.private_file(path, b"")
                self.assert_unavailable(self.observe())
                path.unlink(); fixture.private_file(path, original)

    def test_ancestor_symlink_and_real_root_rename_refused(self):
        alias = self.parent / "alias"
        alias.symlink_to(self.parent, target_is_directory=True)
        self.assert_unavailable(observer.inspect_pending_update(alias / "state", self.slots))
        original = observer._Reader.record
        done = []
        def rename(reader, root, name):
            result = original(reader, root, name)
            if not done:
                self.state.rename(self.parent / "moved-state")
                self.state.mkdir(mode=0o700)
                done.append(True)
            return result
        with patch.object(observer._Reader, "record", rename):
            self.assert_unavailable(self.observe(), observer.ObservationReason.CUSTODY_UNAVAILABLE)

    def test_actual_predecessor_mutation_after_read_is_caught_at_complete_scan(self):
        original = observer._Reader.record
        def mutate(reader, root, name):
            result = original(reader, root, name)
            if name == "update-event-000002.json":
                self.rewrite("update-event-000001.json", lambda value: value.update(owner_id="f" * 64))
            return result
        with patch.object(observer._Reader, "record", mutate):
            self.assert_unavailable(self.observe(), observer.ObservationReason.CUSTODY_UNAVAILABLE)

    def test_actual_read_leaf_substitution_never_follows_replacement(self):
        raw = os.pread
        target = self.state / "update-event-000001.json"
        done = []
        victim = self.parent / "external"
        fixture.private_file(victim, b"private victim bytes")
        def swap(fd, count, offset):
            value = raw(fd, count, offset)
            if not done and os.readlink(f"/proc/self/fd/{fd}") == str(target):
                target.rename(self.parent / "old-record")
                target.symlink_to(victim)
                done.append(True)
            return value
        with patch.object(os, "pread", swap):
            self.assert_unavailable(self.observe())
        self.assertEqual(victim.read_bytes(), b"private victim bytes")

    def test_kernel_sampling_change_is_unknown_using_actual_proc_reads(self):
        original = observer._kernel
        calls = []
        def changed(reader):
            result = original(reader)
            calls.append(result)
            if len(calls) == 2:
                result["mountinfo_sha256"] = "f" * 64
            return result
        with patch.object(observer, "_kernel", changed):
            self.assert_unavailable(self.observe(), observer.ObservationReason.KERNEL_CHANGED)
        self.assertEqual(len(calls), 2)

    def test_procfs_zero_length_is_allowed_only_for_fixed_kernel_sources(self):
        self.assertEqual(os.stat("/proc/sys/kernel/random/boot_id").st_size, 0)
        self.assertEqual(self.observe().status, observer.ObservationStatus.NO_PENDING_UPDATE)
        fixture.private_file(self.state / "update-event-000001.json", b"")
        self.assert_unavailable(self.observe(), observer.ObservationReason.CUSTODY_UNAVAILABLE)

    def test_proc_self_pid_namespace_mismatch_is_unknown_not_another_process_fact(self):
        original = os.readlink
        def mismatch(path, *args, **kwargs):
            if path == "/proc/self":
                return str(os.getpid() + 1)
            return original(path, *args, **kwargs)
        inventory = descriptor_inventory()
        with patch.object(os, "readlink", mismatch):
            value = self.observe()
        self.assert_unavailable(value, observer.ObservationReason.KERNEL_UNAVAILABLE)
        self.assertIsNone(self.private(value)["diagnostic"])
        self.assertEqual(descriptor_inventory(), inventory)

    def test_fork_access_refused_child_descriptor_close_keeps_parent_lease(self):
        reader = observer._Reader()
        state, slots = reader.root(self.state), reader.root(self.slots)
        reader.lease(state); reader.lease(slots)
        read, write = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read)
            try:
                try:
                    reader.inventory(state, 258)
                    raise RuntimeError("inherited scan accepted")
                except observer._Refused:
                    pass
                reader.close()
                descriptor = os.open(self.state / ".coordinator.lock", os.O_RDONLY)
                try:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        raise RuntimeError("parent lease was unlocked")
                    except BlockingIOError:
                        pass
                finally:
                    os.close(descriptor)
                os.write(write, b"ok")
                os._exit(0)
            except BaseException:
                os.write(write, b"failure")
                os._exit(1)
        os.close(write)
        try:
            self.assertTrue(select.select([read], [], [], 5)[0])
            self.assertEqual(os.read(read, 16), b"ok")
            self.assertEqual(os.waitpid(pid, 0)[1], 0)
            reader.confirm((state, slots))
            self.assertEqual(self.observe().status, observer.ObservationStatus.NO_PENDING_UPDATE)
            descriptor = os.open(self.state / ".coordinator.lock", os.O_RDONLY)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
        finally:
            os.close(read); reader.close()
        self.assertEqual(self.observe().status, observer.ObservationStatus.NO_PENDING_UPDATE)

    def test_foreign_thread_scan_is_refused_before_any_new_descriptor(self):
        reader = observer._Reader()
        inventory = descriptor_inventory()
        result = []
        def run():
            try:
                reader.root(self.state)
            except observer._Refused:
                result.append("refused")
        thread = threading.Thread(target=run)
        thread.start(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["refused"])
        self.assertEqual(descriptor_inventory(), inventory)
        reader.close()

    def test_close_effect_then_interrupt_and_fd_reuse_never_retries_integer(self):
        reader = observer._Reader()
        root = reader.root(self.state)
        reader.lease(root)
        owned = [owner.fd for owner in reader.owners]
        original = os.close
        foreign, attempts = [], []
        def interrupted(fd):
            attempts.append(fd)
            original(fd)
            if not foreign:
                number = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                if number != fd:
                    os.dup2(number, fd, inheritable=False); original(number)
                foreign.append(fd)
                raise KeyboardInterrupt("actual close then descriptor reuse")
        try:
            with patch.object(os, "close", interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    reader.close()
            self.assertEqual(attempts, owned)
            del reader; gc.collect()
            self.assertTrue(stat.S_ISCHR(os.fstat(foreign[0]).st_mode))
            for fd in owned[1:]:
                with self.assertRaises(OSError) as context:
                    os.fstat(fd)
                self.assertEqual(context.exception.errno, errno.EBADF)
        finally:
            for fd in foreign:
                original(fd)

    def test_inventory_record_and_mountinfo_bounds_refuse(self):
        for number in range(observer.MAX_EVENTS + 1):
            fixture.private_file(self.state / f"unexpected-{number}", b"{}")
        self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)
        reader = observer._Reader()
        try:
            with self.assertRaises(observer._Refused):
                observer._proc_bytes(reader, f"/proc/{os.getpid()}/mountinfo", 1)
            with self.assertRaises(observer._Refused):
                observer._mount_root(b"1 1 0:1 / / rw - ext4 /dev/a rw\n" * (observer.MAX_MOUNTS + 1), (0, 1))
        finally:
            reader.close()

    def test_slot_image_bytes_are_never_hashed_or_read_as_signed_boot_image(self):
        raw = os.pread
        calls = []
        def read(fd, count, offset):
            name = os.readlink(f"/proc/self/fd/{fd}")
            calls.append(name)
            if name.endswith(("slot-A.img", "slot-B.img")):
                raise AssertionError("observer read image bytes")
            return raw(fd, count, offset)
        with patch.object(os, "pread", read):
            result = self.observe()
        self.assertEqual(result.status, observer.ObservationStatus.NO_PENDING_UPDATE)
        self.assertTrue(calls)
        for slot in self.private(result)["diagnostic"]["slot_files"].values():
            self.assertIs(slot["content_verified"], False)
            self.assertNotIn("sha256", slot)

    def test_observer_actual_syscalls_never_create_write_sync_or_unlock(self):
        original_open, original_flock = os.open, fcntl.flock
        opened, leases = [], []
        def opening(path, flags, *args, **kwargs):
            opened.append(flags)
            self.assertEqual(flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC), 0)
            return original_open(path, flags, *args, **kwargs)
        def locking(fd, operation):
            leases.append(operation)
            self.assertEqual(operation, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return original_flock(fd, operation)
        with patch.object(os, "open", opening), patch.object(fcntl, "flock", locking), \
                patch.object(os, "write", side_effect=AssertionError("observer attempted write")), \
                patch.object(os, "fsync", side_effect=AssertionError("observer attempted fsync")):
            self.assertEqual(self.observe().status, observer.ObservationStatus.NO_PENDING_UPDATE)
        self.assertTrue(opened)
        self.assertEqual(len(leases), 2)

    def test_default_unconfigured_owner_history_has_no_crypto_authority(self):
        state, slots = self.parent / "default-state", self.parent / "default-slots"
        state.mkdir(mode=0o700); slots.mkdir(mode=0o700)
        fixture.private_file(slots / "slot-A.img", fixture.SOURCE)
        fixture.private_file(slots / "slot-B.img", b"old")
        value = fixture.owner.DurableUpdateOwner(state, slots, active_slot="A",
            current_version=10, current_image_sha256=fixture.SOURCE_DIGEST, clock=lambda: fixture.NOW)
        value.close()
        result = observer.inspect_pending_update(state, slots)
        self.assertEqual(result.status, observer.ObservationStatus.NO_PENDING_UPDATE)
        self.assertEqual(self.private(result)["signature_authority"], "unavailable")
        self.assertIn(observer.ObservationReason.SIGNATURE_UNAVAILABLE, result.reasons)

    def test_real_marker_confirmed_prefix_digest_cannot_be_fabricated(self):
        value = self.new_owner()
        value._closed = True; value._release_descriptors()
        reopened = self.new_owner()
        reopened._closed = True; reopened._release_descriptors()
        path = self.state / observer._MARKER
        original = path.read_bytes()
        mutations = [lambda v: v.update(history_count=True), lambda v: v.update(history_count=100),
            lambda v: v.update(last_event_sha256="f" * 64), lambda v: v.update(operation_id="f" * 64),
            lambda v: v.update(bootloader_effect_performed=0), lambda v: v.update(extra="pretend")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                fixture.private_file(path, original)
                self.rewrite(path.name, mutation)
                self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)

    def test_private_root_or_existing_lease_custody_downgrade_is_refused(self):
        for path, mode in ((self.state, 0o755), (self.slots, 0o770),
                (self.state / ".coordinator.lock", 0o644), (self.slots / ".coordinator.lock", 0o660)):
            with self.subTest(path=path.name):
                old = stat.S_IMODE(path.stat().st_mode)
                path.chmod(mode)
                self.assert_unavailable(self.observe(), observer.ObservationReason.CUSTODY_UNAVAILABLE)
                path.chmod(old)

    def test_cli_stdout_is_redacted_private_output_is_exclusive_and_exact(self):
        output = self.parent / "private-diagnostic.json"
        result = self.command("--output", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        public = json.loads(result.stdout)
        self.assertEqual(set(public), {"schema", "status", "reason_codes", "signature_authority", "signed_boot_image_mapping", "booted_image_verified", "production_activation_enabled", "bootloader_effect_performed", "continuation_authorized"})
        raw = json.loads(output.read_bytes())
        kernel = raw["diagnostic"]["kernel"]
        self.assertNotIn(kernel["boot_id"].encode(), result.stdout)
        self.assertNotIn(str(self.state).encode(), result.stdout + result.stderr)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        before = output.read_bytes()
        self.assertEqual(self.command("--output", str(output)).returncode, 2)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(result.stderr, b"")

    def test_cli_output_symlink_hardlink_fifo_and_authority_root_refused(self):
        victim = self.parent / "victim"
        fixture.private_file(victim, b"unchanged private bytes")
        output = self.parent / "output"
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    output.symlink_to(victim)
                elif kind == "hardlink":
                    os.link(victim, output)
                else:
                    os.mkfifo(output, 0o600)
                self.assertEqual(self.command("--output", str(output)).returncode, 2)
                self.assertEqual(victim.read_bytes(), b"unchanged private bytes")
                output.unlink()
        before = snapshot(self.state)
        self.assertEqual(self.command("--output", str(self.state / "diagnostic.json")).returncode, 2)
        self.assertEqual(snapshot(self.state), before)

    def test_cli_no_recursive_creation_or_raw_argument_error(self):
        output = self.parent / "missing" / "diagnostic.json"
        result = self.command("--output", str(output))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.parent.exists())
        result = self.command("--unknown-identity", "sensitive-UID-1234")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"sensitive-UID-1234", result.stdout + result.stderr)

    def test_signed_pending_manifest_admission_and_receipt_mutations_refused(self):
        self.pending()
        path = self.state / "update-event-000008.json"
        original = path.read_bytes()
        mutations = [lambda v: v["operation"]["signature_admission"].update(signing_preimage_sha256="f" * 64),
            lambda v: v["operation"]["signature_admission"].update(verified_unix=True),
            lambda v: v["operation"].update(ticket_sequence=True),
            lambda v: v["operation"]["manifest"].update(target_slot="A"),
            lambda v: v["stage_receipt"].update(image_bytes=True),
            lambda v: v["stage_receipt"].update(signature_sha256="f" * 64),
            lambda v: v.update(kind="owner_clean", phase="closed")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                fixture.private_file(path, original)
                self.rewrite(path.name, mutation)
                self.assert_unavailable(self.observe(), observer.ObservationReason.JOURNAL_INVALID)

    def test_public_contract_api_limits_and_claims_match_source(self):
        contract = json.loads((ROOT / "contracts/update-boot-observer.v1.json").read_bytes())
        self.assertEqual(set(contract), {"schema", "status", "implementation", "api", "observation_schema", "public_fields", "status_codes", "reason_codes", "limits", "kernel_sources", "kernel_measurement", "custody", "cli", "claims", "remaining_installed_obligations"})
        self.assertEqual(contract["schema"], "trillionnium.desktop.update-boot-observer-contract.v1")
        self.assertEqual(contract["status"], "SOURCE_CANDIDATE")
        self.assertEqual(contract["implementation"], "platform/update_boot_observer.py")
        self.assertEqual(contract["observation_schema"], observer.SCHEMA)
        self.assertEqual(contract["api"], {"inspect_pending_update": str(inspect.signature(observer.inspect_pending_update)),
            "BootObservation.public_json": str(inspect.signature(observer.BootObservation.public_json)),
            "BootObservation.private_json": str(inspect.signature(observer.BootObservation.private_json))})
        self.assertEqual(contract["limits"], {"events": observer.MAX_EVENTS, "record_bytes": observer.MAX_RECORD_BYTES,
            "mountinfo_bytes": observer.MAX_MOUNTINFO_BYTES, "mounts": observer.MAX_MOUNTS,
            "private_diagnostic_bytes": observer.MAX_DIAGNOSTIC_BYTES, "absolute_path_components": observer.MAX_PATH_COMPONENTS})
        self.assertEqual(contract["status_codes"], [item.value for item in observer.ObservationStatus])
        self.assertEqual(contract["reason_codes"], [item.value for item in observer.ObservationReason])
        public = json.loads(self.observe().public_json())
        self.assertEqual(contract["public_fields"], sorted(public))
        self.assertEqual(contract["claims"], {"approved_roots": [], "signature_authority": "unavailable", "signed_boot_image_mapping": "unknown", "booted_image_verified": False, "continuation_authorized": False, "production_activation_enabled": False, "bootloader_effect_performed": False, "health_qualified": False, "installed_two_boot_qualified": False, "hardware_power_loss_qualified": False})
        self.assertEqual(contract["kernel_sources"], ["/proc/self", "/proc/sys/kernel/random/boot_id", "/proc/<creator-pid>/mountinfo", "/proc/<creator-pid>/ns/mnt", "/"])
        self.assertEqual(contract["kernel_measurement"]["filesystem_magic"], {"procfs": 0x9FA0, "nsfs": 0x6E736673})
        self.assertEqual(contract["cli"]["arguments"], ["--state-root", "--slot-root", "--output"])
        self.assertEqual(contract["cli"]["exit_codes"], {"no_pending_update": 0, "unknown_recovery_unavailable_output_or_argument_refusal": 2})
        for field in ("_EVENT_FIELDS", "_CONFIG_FIELDS", "_OP_FIELDS", "_ADMISSION_FIELDS", "_STAGE_FIELDS", "_MARKER_FIELDS", "_PHASES", "_NEXT"):
            self.assertEqual(getattr(observer, field), getattr(fixture.owner, field))

    def test_separate_source_index_is_closed_and_does_not_register_authority(self):
        value = json.loads((ROOT / "manifests/update-observation.v1.json").read_bytes())
        self.assertEqual(set(value), {"schema", "plan_revision", "requirements", "implementation", "entrypoint", "documentation", "contract", "tests", "workflow", "dependencies", "claim_ceiling", "authority_mechanism", "production_activation_enabled"})
        self.assertEqual(value["schema"], "trillionnium.desktop.update-observation-source-index.v1")
        self.assertEqual(value["plan_revision"], "2026-08-29-d6")
        self.assertEqual(value["requirements"], ["G6", "D7", "S11"])
        expected = {"implementation": "platform/update_boot_observer.py", "entrypoint": "tools/inspect_pending_update.py", "documentation": "docs/architecture/UPDATE_BOOT_OBSERVER.md", "contract": "contracts/update-boot-observer.v1.json", "tests": "tests/test_update_boot_observer.py", "workflow": ".github/workflows/update-boot-observer.yml"}
        for field, path in expected.items():
            self.assertEqual(value[field], path)
            self.assertTrue((ROOT / path).is_file())
            self.assertFalse((ROOT / path).is_symlink())
        self.assertEqual(value["dependencies"], ["platform/update_recovery.py", "platform/durable_update_owner.py"])
        self.assertIs(value["authority_mechanism"], False)
        self.assertIs(value["production_activation_enabled"], False)
        self.assertIn("no signing", value["claim_ceiling"])
        source = (ROOT / "platform/update_boot_observer.py").read_text()
        for forbidden in ("ExternalUpdateSignatureVerifier(", "AtomicStateStore(", "ImageSlotStore(", "DurableUpdateOwner(", "LOCK_UN", "os.O_CREAT", "os.write(", "os.fsync("):
            self.assertNotIn(forbidden, source.replace("# A fork child may only retire copied descriptors, never LOCK_UN.", ""))

    def inventory_copy(self):
        directory = tempfile.TemporaryDirectory(prefix="readonly-observer-inventory-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        paths = {inventory_gate.REGISTRY, "manifests/update-observation.v1.json"}
        registry = json.loads((ROOT / inventory_gate.REGISTRY).read_bytes())
        for module in registry["modules"]:
            paths.update(module[field] for field in ("implementation", "documentation", "contract", "tests"))
        index = json.loads((ROOT / "manifests/update-observation.v1.json").read_bytes())
        paths.update(index[field] for field in ("implementation", "entrypoint", "documentation", "contract", "tests", "workflow"))
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        return root

    def test_actual_inventory_guard_accepts_registered_readonly_source_and_rejects_partial(self):
        root = self.inventory_copy()
        result = inventory_gate.validate(root)
        self.assertEqual(result["registered_modules"], 6)
        self.assertIs(result["execution_observed"], False)
        self.assertIs(result["qualification_changed"], False)
        path = root / "manifests/update-observation.v1.json"
        path.unlink()
        with self.assertRaises((ValueError, OSError)):
            inventory_gate.validate(root)

    def test_actual_inventory_guard_rejects_wrong_paths_and_index_claim_aliases(self):
        root = self.inventory_copy()
        path = root / "manifests/update-observation.v1.json"
        original = path.read_bytes()
        mutations = [lambda v: v.update(implementation="platform/update_recovery.py"),
            lambda v: v.update(entrypoint="platform/durable_update_owner.py"),
            lambda v: v.update(authority_mechanism=True), lambda v: v.update(authority_mechanism=0),
            lambda v: v.update(production_activation_enabled=0.0), lambda v: v.update(extra="unchecked"),
            lambda v: v.update(requirements=["G6"])]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = json.loads(original); mutation(value)
                path.write_bytes(observer._canonical(value))
                with self.assertRaises(ValueError):
                    inventory_gate.validate(root, refresh=True)

    def test_actual_inventory_guard_rejects_public_argument_and_new_authority_export(self):
        root = self.inventory_copy()
        path = root / "platform/update_boot_observer.py"
        original = path.read_text()
        for source in (original.replace("slot_root: Path) -> BootObservation", "slot_root: Path, caller_health=True) -> BootObservation", 1),
                       original + "\ndef resume_update():\n    return True\n"):
            self.assertNotEqual(source, original)
            path.write_text(source)
            with self.assertRaisesRegex(ValueError, "observer public API"):
                inventory_gate.validate(root, refresh=True)

    def test_actual_inventory_guard_rejects_closed_contract_type_and_claim_mutations(self):
        root = self.inventory_copy()
        path = root / "contracts/update-boot-observer.v1.json"
        original = path.read_bytes()
        mutations = [lambda v: v["claims"].update(continuation_authorized=True),
            lambda v: v["claims"].update(booted_image_verified=0),
            lambda v: v["claims"].update(production_activation_enabled=0.0),
            lambda v: v["claims"].update(signature_authority="approved"),
            lambda v: v["claims"].update(approved_roots=["fabricated-root"]),
            lambda v: v["claims"].update(installed_two_boot_qualified=True),
            lambda v: v["claims"].update(hardware_power_loss_qualified=True),
            lambda v: v["api"].update(inspect_pending_update="(caller_health=True)"),
            lambda v: v["custody"].update(automatic_repair=True),
            lambda v: v.update(status="PRODUCTION_READY"), lambda v: v.update(extra="unchecked")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = json.loads(original); mutation(value)
                path.write_bytes(observer._canonical(value))
                with self.assertRaisesRegex(ValueError, "observer contract"):
                    inventory_gate.validate(root, refresh=True)


if __name__ == "__main__":
    unittest.main()
