from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ab_update_reference import (  # noqa: E402
    UpdateEngine,
    UpdateError,
    build_recovery_manifest_fixture,
    build_update_manifest_fixture,
    fixture_engine,
    fixture_trust,
    signed_payload,
    verify_recovery_media,
)
from trusted_app_bundle import ed25519_public_from_seed, ed25519_sign_fixture  # noqa: E402

UPDATE_SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)
RECOVERY_SEED = bytes.fromhex(
    "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"
)


class ABUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = b"immutable update image v2"
        self.recovery_image = b"offline recovery image"
        self.update, self.update_public = build_update_manifest_fixture(
            UPDATE_SEED, self.image
        )
        self.recovery, self.recovery_public = build_recovery_manifest_fixture(
            RECOVERY_SEED, self.recovery_image, minimum_rollback_index=2
        )
        self.trust = fixture_trust(self.update_public, self.recovery_public)

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(UpdateError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def resign_update(self, manifest: dict) -> None:
        manifest["signature"]["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(UPDATE_SEED, signed_payload(manifest))
        ).decode()

    def resign_recovery(self, manifest: dict) -> None:
        manifest["signature"]["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(RECOVERY_SEED, signed_payload(manifest))
        ).decode()

    def test_valid_signed_inactive_slot_stage_and_health_commit(self) -> None:
        engine = fixture_engine()
        active_before = copy.deepcopy(engine.slots["A"])
        status = engine.stage(
            self.update,
            self.image,
            self.trust,
            now_epoch=100,
            available_bytes=4096,
        )
        self.assertEqual(status, "STAGED_AND_PENDING_BOOT")
        self.assertEqual(engine.active_slot, "A")
        self.assertEqual(engine.slots["A"], active_before)
        self.assertEqual(engine.pending_slot, "B")
        engine.boot_pending()
        self.assertEqual(engine.active_slot, "A")
        self.assertEqual(engine.secure_rollback_index, 1)
        engine.report_health(True)
        self.assertEqual(engine.active_slot, "B")
        self.assertEqual(engine.current_version(), 2)
        self.assertEqual(engine.secure_rollback_index, 2)
        self.assertEqual(engine.last_outcome, "update_committed_after_health")
        self.assertFalse(engine.snapshot()["active_slot_written_during_stage"])

    def test_signature_image_hardware_and_recovery_compatibility_rejected(self) -> None:
        manifest = copy.deepcopy(self.update)
        signature = bytearray(base64.b64decode(manifest["signature"]["value_base64"]))
        signature[0] ^= 1
        manifest["signature"]["value_base64"] = base64.b64encode(signature).decode()
        self.assert_rejected(
            "UPDATE_SIGNATURE_REJECTED",
            lambda: fixture_engine().stage(
                manifest, self.image, self.trust, now_epoch=100, available_bytes=4096
            ),
        )
        self.assert_rejected(
            "UPDATE_IMAGE_DIGEST_MISMATCH",
            lambda: fixture_engine().stage(
                self.update,
                self.image + b"tamper",
                self.trust,
                now_epoch=100,
                available_bytes=4096,
            ),
        )
        wrong_hardware = copy.deepcopy(self.update)
        wrong_hardware["hardware_profile"] = "other-hardware"
        self.resign_update(wrong_hardware)
        self.assert_rejected(
            "UPDATE_HARDWARE_PROFILE_MISMATCH",
            lambda: fixture_engine().stage(
                wrong_hardware,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=4096,
            ),
        )
        incompatible = copy.deepcopy(self.update)
        incompatible["recovery_compatible"] = False
        self.resign_update(incompatible)
        self.assert_rejected(
            "UPDATE_NOT_RECOVERY_COMPATIBLE",
            lambda: fixture_engine().stage(
                incompatible,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=4096,
            ),
        )

    def test_version_and_rollback_downgrade_rejected(self) -> None:
        old_version = copy.deepcopy(self.update)
        old_version["version"] = 1
        self.resign_update(old_version)
        self.assert_rejected(
            "UPDATE_VERSION_DOWNGRADE_REJECTED",
            lambda: fixture_engine().stage(
                old_version,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=4096,
            ),
        )
        old_index = copy.deepcopy(self.update)
        old_index["rollback_index"] = 1
        self.resign_update(old_index)
        self.assert_rejected(
            "ROLLBACK_INDEX_DOWNGRADE_REJECTED",
            lambda: fixture_engine().stage(
                old_index,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=4096,
            ),
        )

    def test_disk_full_before_stage_preserves_active_slot_and_journal(self) -> None:
        engine = fixture_engine()
        snapshot = engine.snapshot()
        records = copy.deepcopy(engine.journal.records)
        self.assert_rejected(
            "DISK_FULL_BEFORE_STAGE",
            lambda: engine.stage(
                self.update,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=len(self.image) - 1,
            ),
        )
        self.assertEqual(engine.snapshot(), snapshot)
        self.assertEqual(engine.journal.records, records)

    def test_disk_full_mid_stage_discards_partial_inactive_slot(self) -> None:
        engine = fixture_engine()
        active_digest = engine.slots["A"].image_sha256
        self.assert_rejected(
            "DISK_FULL_DURING_INACTIVE_SLOT_WRITE",
            lambda: engine.stage(
                self.update,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=4096,
                write_limit_bytes=len(self.image) // 2,
            ),
        )
        self.assertEqual(engine.active_slot, "A")
        self.assertEqual(engine.slots["A"].image_sha256, active_digest)
        action = engine.recover_after_power_loss()
        self.assertEqual(
            action, "RECOVERED_PREVIOUS_HEALTHY_SLOT_PARTIAL_DISCARDED"
        )
        self.assertEqual(engine.slots["B"].state, "empty")

    def test_power_loss_before_seal_preserves_active_slot(self) -> None:
        for point in ("stage_intent", "image_write"):
            engine = fixture_engine()
            engine.stage(
                self.update,
                self.image,
                self.trust,
                now_epoch=100,
                available_bytes=4096,
                stop_after=point,
            )
            self.assertEqual(engine.active_slot, "A")
            self.assertEqual(
                engine.recover_after_power_loss(),
                "RECOVERED_PREVIOUS_HEALTHY_SLOT_PARTIAL_DISCARDED",
            )
            self.assertEqual(engine.active_slot, "A")
            self.assertEqual(engine.current_version(), 1)

    def test_power_loss_after_seal_never_auto_activates(self) -> None:
        engine = fixture_engine()
        engine.stage(
            self.update,
            self.image,
            self.trust,
            now_epoch=100,
            available_bytes=4096,
            stop_after="slot_seal",
        )
        self.assertEqual(
            engine.recover_after_power_loss(),
            "PREVIOUS_HEALTHY_SLOT_ACTIVE_SEALED_SLOT_REQUIRES_EXPLICIT_PENDING",
        )
        self.assertEqual(engine.active_slot, "A")
        self.assertIsNone(engine.pending_slot)
        engine.explicitly_mark_sealed_pending()
        self.assertEqual(engine.pending_slot, "B")

    def test_power_loss_after_pending_marker_resumes_bounded_boot(self) -> None:
        engine = fixture_engine()
        engine.stage(
            self.update,
            self.image,
            self.trust,
            now_epoch=100,
            available_bytes=4096,
            stop_after="pending_marker",
        )
        self.assertEqual(
            engine.recover_after_power_loss(),
            "PREVIOUS_HEALTHY_SLOT_ACTIVE_PENDING_BOOT_MAY_RESUME",
        )
        self.assertEqual(engine.active_slot, "A")
        engine.boot_pending()
        engine.report_health(True)
        self.assertEqual(engine.active_slot, "B")

    def test_failed_health_rolls_back_without_advancing_counter(self) -> None:
        engine = fixture_engine()
        engine.stage(
            self.update,
            self.image,
            self.trust,
            now_epoch=100,
            available_bytes=4096,
        )
        engine.boot_pending()
        engine.report_health(False, "watchdog_failed")
        self.assertEqual(engine.active_slot, "A")
        self.assertEqual(engine.current_version(), 1)
        self.assertEqual(engine.secure_rollback_index, 1)
        self.assertEqual(engine.slots["B"].state, "failed")
        self.assertEqual(engine.last_outcome, "rolled_back_to_previous_healthy_slot")

    def test_power_loss_during_boot_retries_then_rolls_back_at_limit(self) -> None:
        engine = fixture_engine()
        engine.stage(
            self.update,
            self.image,
            self.trust,
            now_epoch=100,
            available_bytes=4096,
        )
        engine.boot_pending()
        self.assertEqual(
            engine.recover_after_power_loss(),
            "PREVIOUS_HEALTHY_SLOT_ACTIVE_PENDING_BOOT_MAY_RETRY",
        )
        self.assertEqual(engine.boot_attempts, 1)
        engine.boot_pending()
        self.assertEqual(
            engine.recover_after_power_loss(),
            "ROLLED_BACK_AFTER_BOOT_ATTEMPT_LIMIT",
        )
        self.assertEqual(engine.active_slot, "A")
        self.assertEqual(engine.secure_rollback_index, 1)
        self.assertEqual(engine.slots["B"].state, "failed")

    def test_update_journal_replay_and_torn_tail(self) -> None:
        engine = fixture_engine()
        engine.stage(
            self.update,
            self.image,
            self.trust,
            now_epoch=100,
            available_bytes=4096,
        )
        replayed = UpdateEngine.recover(engine.journal.serialize())
        self.assertEqual(replayed.snapshot(), engine.snapshot())
        torn = engine.journal.serialize() + b'{"schema":"trillionnium.desktop.update-journal-record.v1"'
        recovered = UpdateEngine.recover(torn)
        self.assertTrue(recovered.discarded_torn_tail)
        expected = engine.snapshot()
        actual = recovered.snapshot()
        expected["discarded_torn_tail"] = True
        self.assertEqual(actual, expected)

    def test_corrupt_journal_requires_recovery_media(self) -> None:
        engine = fixture_engine()
        records = copy.deepcopy(engine.journal.records)
        records[0]["record_sha256"] = "0" * 64
        corrupt = b"".join(
            (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for item in records
        )
        fail_closed = UpdateEngine.fail_closed_on_corrupt_journal(corrupt)
        self.assertTrue(fail_closed.recovery_media_required)
        self.assertEqual(fail_closed.phase, "recovery_required")
        self.assertEqual(fail_closed.last_outcome, "corrupt_update_journal")

    def test_update_journal_tamper_is_rejected(self) -> None:
        engine = fixture_engine()
        records = copy.deepcopy(engine.journal.records)
        records[0]["event"]["version"] = 999
        tampered = b"".join(
            (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for item in records
        )
        self.assert_rejected(
            "UPDATE_JOURNAL_RECORD_HASH_MISMATCH",
            lambda: UpdateEngine.recover(tampered),
        )

    def test_valid_separately_signed_offline_recovery_media(self) -> None:
        result = verify_recovery_media(
            self.recovery,
            self.recovery_image,
            self.trust,
            hardware_profile="trillionnium-x86_64-fixture-v1",
            secure_rollback_index=2,
            now_epoch=100,
        )
        self.assertEqual(result["status"], "PASS_OFFLINE_REFERENCE_VERIFICATION")
        self.assertFalse(result["automatic_destructive_recovery"])
        self.assertFalse(result["recovery_execution_performed"])

    def test_recovery_media_tamper_wrong_hardware_and_old_index_rejected(self) -> None:
        signature_tamper = copy.deepcopy(self.recovery)
        raw = bytearray(base64.b64decode(signature_tamper["signature"]["value_base64"]))
        raw[-1] ^= 1
        signature_tamper["signature"]["value_base64"] = base64.b64encode(raw).decode()
        self.assert_rejected(
            "RECOVERY_SIGNATURE_REJECTED",
            lambda: verify_recovery_media(
                signature_tamper,
                self.recovery_image,
                self.trust,
                hardware_profile="trillionnium-x86_64-fixture-v1",
                secure_rollback_index=2,
                now_epoch=100,
            ),
        )
        wrong_hardware = copy.deepcopy(self.recovery)
        wrong_hardware["hardware_profile"] = "other-hardware"
        self.resign_recovery(wrong_hardware)
        self.assert_rejected(
            "RECOVERY_HARDWARE_PROFILE_MISMATCH",
            lambda: verify_recovery_media(
                wrong_hardware,
                self.recovery_image,
                self.trust,
                hardware_profile="trillionnium-x86_64-fixture-v1",
                secure_rollback_index=2,
                now_epoch=100,
            ),
        )
        old = copy.deepcopy(self.recovery)
        old["minimum_rollback_index"] = 1
        self.resign_recovery(old)
        self.assert_rejected(
            "RECOVERY_ROLLBACK_INDEX_TOO_OLD",
            lambda: verify_recovery_media(
                old,
                self.recovery_image,
                self.trust,
                hardware_profile="trillionnium-x86_64-fixture-v1",
                secure_rollback_index=2,
                now_epoch=100,
            ),
        )
        destructive = copy.deepcopy(self.recovery)
        destructive["automatic_destructive_recovery"] = True
        self.resign_recovery(destructive)
        self.assert_rejected(
            "AUTOMATIC_DESTRUCTIVE_RECOVERY_FORBIDDEN",
            lambda: verify_recovery_media(
                destructive,
                self.recovery_image,
                self.trust,
                hardware_profile="trillionnium-x86_64-fixture-v1",
                secure_rollback_index=2,
                now_epoch=100,
            ),
        )

    def test_update_and_recovery_keys_are_distinct(self) -> None:
        self.assertNotEqual(self.update_public, self.recovery_public)
        self.assertEqual(
            self.update_public,
            ed25519_public_from_seed(UPDATE_SEED),
        )
        self.assertEqual(
            self.recovery_public,
            ed25519_public_from_seed(RECOVERY_SEED),
        )


if __name__ == "__main__":
    unittest.main()
