from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

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
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def coordinator() -> object:
    return s11.UpdateCoordinator(
        active_slot="A",
        current_version=10,
        current_image_sha256=SOURCE_DIGEST,
    )


class S11UpdateRecoveryTests(unittest.TestCase):
    def test_strict_manifest_and_source_binding(self) -> None:
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        self.assertEqual(ticket.manifest.target_slot, "B")
        for payload in (
            b'{"schema":"x","schema":"y"}',
            b'{"value":NaN}',
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
        c = coordinator()
        ticket = c.verify_manifest(manifest(), now_unix=1_000_000)
        c.mark_possible_dispatch(ticket)
        self.assertTrue(c.effect_reconciliation_required)
        with self.assertRaises(s11.StateRefused):
            c.verify_manifest(manifest(), now_unix=1_000_000)
        with self.assertRaises(s11.StateRefused):
            c.verify_journal_reconciliation(
                ticket, journal_record_sha256=JOURNAL, status="retry"
            )
        fact = c.verify_journal_reconciliation(
            ticket, journal_record_sha256=JOURNAL, status="indeterminate"
        )
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


if __name__ == "__main__":
    unittest.main()
