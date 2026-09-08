from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from effect_reconciliation_reference import EffectError, EffectJournal  # noqa: E402


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class EffectReconciliationTests(unittest.TestCase):
    def journal_with_request(self) -> EffectJournal:
        journal = EffectJournal()
        journal.request(
            "operation-1",
            "idempotency-1",
            "fixture-write",
            sha(b"payload"),
            sha(b"permit"),
            sha(b"subject"),
        )
        return journal

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(EffectError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def test_requested_and_prepared_are_pre_effect(self) -> None:
        journal = self.journal_with_request()
        self.assertEqual(
            journal.recovery_action("operation-1"),
            "PRE_EFFECT_SAFE_TO_CANCEL_OR_REPREPARE",
        )
        journal.prepare("operation-1")
        self.assertEqual(
            journal.recovery_action("operation-1"),
            "PRE_EFFECT_SAFE_TO_CANCEL_OR_REPREPARE",
        )
        self.assertFalse(journal.snapshot()["journal_executes_operations"])

    def test_dispatch_and_indeterminate_are_reconciliation_only(self) -> None:
        journal = self.journal_with_request()
        journal.prepare("operation-1")
        journal.dispatch("operation-1", sha(b"dispatch-token"))
        self.assertEqual(
            journal.recovery_action("operation-1"),
            "RECONCILE_ONLY_NEVER_AUTOMATICALLY_REPLAY",
        )
        journal.indeterminate("operation-1", "connection_lost")
        self.assertEqual(
            journal.recovery_action("operation-1"),
            "RECONCILE_ONLY_NEVER_AUTOMATICALLY_REPLAY",
        )
        self.assertFalse(journal.snapshot()["automatic_replay_after_dispatch"])
        self.assertFalse(hasattr(journal, "execute"))
        self.assertFalse(hasattr(journal, "replay_effect"))

    def test_provider_applied_and_not_applied_reconciliation(self) -> None:
        applied = self.journal_with_request()
        applied.prepare("operation-1")
        applied.dispatch("operation-1", sha(b"dispatch"))
        applied.reconcile("operation-1", "applied", sha(b"provider-applied"))
        self.assertEqual(applied.operations["operation-1"].state, "reconciled_applied")
        self.assertEqual(applied.recovery_action("operation-1"), "NO_ACTION_TERMINAL")

        not_applied = self.journal_with_request()
        not_applied.prepare("operation-1")
        not_applied.dispatch("operation-1", sha(b"dispatch"))
        not_applied.indeterminate("operation-1", "timeout")
        not_applied.reconcile(
            "operation-1", "not_applied", sha(b"provider-not-applied")
        )
        operation = not_applied.operations["operation-1"]
        self.assertEqual(operation.state, "reconciled_not_applied")
        self.assertTrue(operation.retry_requires_new_authorization)
        self.assertFalse(hasattr(not_applied, "retry"))

    def test_unknown_reconciliation_requires_manual_action(self) -> None:
        journal = self.journal_with_request()
        journal.prepare("operation-1")
        journal.dispatch("operation-1", sha(b"dispatch"))
        journal.reconcile("operation-1", "unknown", sha(b"provider-unknown"))
        self.assertEqual(journal.operations["operation-1"].state, "manual_required")
        self.assertEqual(journal.recovery_action("operation-1"), "MANUAL_ACTION_REQUIRED")

    def test_terminal_success_and_failure_are_not_replayed(self) -> None:
        for outcome in ("success", "failure"):
            journal = self.journal_with_request()
            journal.prepare("operation-1")
            journal.dispatch("operation-1", sha(b"dispatch"))
            journal.terminal("operation-1", outcome, sha(outcome.encode()))
            self.assertEqual(
                journal.operations["operation-1"].state,
                f"terminal_{outcome}",
            )
            self.assertEqual(journal.recovery_action("operation-1"), "NO_ACTION_TERMINAL")

    def test_cancel_is_allowed_only_before_dispatch(self) -> None:
        journal = self.journal_with_request()
        journal.cancel("operation-1", "user_cancelled")
        self.assertEqual(
            journal.operations["operation-1"].state,
            "cancelled_before_dispatch",
        )
        dispatched = self.journal_with_request()
        dispatched.prepare("operation-1")
        dispatched.dispatch("operation-1", sha(b"dispatch"))
        self.assert_rejected(
            "CANCEL_AFTER_DISPATCH_FORBIDDEN",
            lambda: dispatched.cancel("operation-1", "too_late"),
        )

    def test_duplicate_operation_and_idempotency_key_rejected(self) -> None:
        journal = self.journal_with_request()
        self.assert_rejected(
            "DUPLICATE_OPERATION_ID",
            lambda: journal.request(
                "operation-1",
                "idempotency-2",
                "fixture-write",
                sha(b"payload2"),
                sha(b"permit2"),
                sha(b"subject2"),
            ),
        )
        self.assert_rejected(
            "DUPLICATE_IDEMPOTENCY_KEY",
            lambda: journal.request(
                "operation-2",
                "idempotency-1",
                "fixture-write",
                sha(b"payload2"),
                sha(b"permit2"),
                sha(b"subject2"),
            ),
        )

    def test_invalid_transitions_rejected(self) -> None:
        journal = self.journal_with_request()
        self.assert_rejected(
            "INVALID_EFFECT_TRANSITION",
            lambda: journal.dispatch("operation-1", sha(b"dispatch")),
        )
        journal.prepare("operation-1")
        self.assert_rejected(
            "INVALID_EFFECT_TRANSITION",
            lambda: journal.prepare("operation-1"),
        )
        self.assert_rejected(
            "RECONCILIATION_NOT_ALLOWED",
            lambda: journal.reconcile(
                "operation-1", "applied", sha(b"provider")
            ),
        )

    def test_journal_replay_is_identical(self) -> None:
        journal = self.journal_with_request()
        journal.prepare("operation-1")
        journal.dispatch("operation-1", sha(b"dispatch"))
        journal.indeterminate("operation-1", "timeout")
        recovered = EffectJournal.recover(journal.serialize())
        self.assertEqual(recovered.snapshot(), journal.snapshot())
        self.assertEqual(recovered.records, journal.records)

    def test_torn_final_record_is_discarded_only(self) -> None:
        journal = self.journal_with_request()
        journal.prepare("operation-1")
        complete = journal.serialize()
        torn = complete + b'{"schema":"trillionnium.desktop.effect-journal-record.v1"'
        recovered = EffectJournal.recover(torn)
        self.assertTrue(recovered.discarded_torn_tail)
        self.assertEqual(recovered.records, journal.records)
        self.assertEqual(recovered.operations["operation-1"].state, "prepared")

    def test_middle_corruption_is_rejected(self) -> None:
        journal = self.journal_with_request()
        journal.prepare("operation-1")
        journal.dispatch("operation-1", sha(b"dispatch"))
        lines = journal.serialize().splitlines(keepends=True)
        record = json.loads(lines[1])
        record["event"]["kind"] = "forged"
        lines[1] = (
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        self.assert_rejected(
            "EFFECT_JOURNAL_RECORD_HASH_MISMATCH",
            lambda: EffectJournal.recover(b"".join(lines)),
        )

    def test_receipt_tamper_and_sequence_tamper_rejected(self) -> None:
        journal = self.journal_with_request()
        records = copy.deepcopy(journal.records)
        records[0]["record_sha256"] = "0" * 64
        payload = b"".join(
            (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for item in records
        )
        self.assert_rejected(
            "EFFECT_JOURNAL_RECORD_HASH_MISMATCH",
            lambda: EffectJournal.recover(payload),
        )


if __name__ == "__main__":
    unittest.main()
