"""Adversarial tests for D7 journal byte and transaction boundaries."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import effect_reconciliation_reference as effect


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def requested() -> effect.EffectJournal:
    journal = effect.EffectJournal()
    journal.request("op-1", "key-1", "fixture-write", sha(b"payload"), sha(b"permit"), sha(b"subject"))
    return journal


class EffectJournalHardeningTests(unittest.TestCase):
    def assert_denied(self, raw: bytes, reason: str | None = None) -> None:
        with self.assertRaises(effect.EffectError) as caught:
            effect.EffectJournal.recover(raw)
        if reason is not None:
            self.assertEqual(caught.exception.reason, reason)

    def test_duplicate_outer_nested_and_escaped_keys_are_rejected(self) -> None:
        raw = requested().serialize()
        variants = (
            raw.replace(b'"sequence":1', b'"sequence":2,"sequence":1'),
            raw.replace(b'"operation_id":"op-1"', b'"operation_id":"other","operation_id":"op-1"'),
            raw.replace(b'"operation_id":"op-1"', b'"operation\\u005fid":"other","operation_id":"op-1"'),
        )
        for value in variants:
            with self.subTest(value=value[:80]):
                self.assert_denied(value, "EFFECT_JOURNAL_DUPLICATE_KEY")

    def test_sequence_requires_an_exact_integer(self) -> None:
        for value in (b"true", b"1.0", b"1e0", b'"1"', b"null", b"false", b"[]", b"{}"):
            with self.subTest(value=value):
                raw = requested().serialize().replace(b'"sequence":1', b'"sequence":' + value)
                self.assert_denied(raw, "EFFECT_JOURNAL_SEQUENCE_MISMATCH")

    def test_noncanonical_equivalent_bytes_are_rejected(self) -> None:
        raw = requested().serialize()
        variants = (
            json.dumps(requested().records[0]).encode() + b"\n",
            raw.replace(b'"sequence":1', b'"sequence" : 1'),
            raw.replace(b"\n", b"\r\n"),
            raw.replace(b"op-1", b"op-\\u0031"),
        )
        for value in variants:
            with self.subTest(value=value[:80]):
                self.assert_denied(value, "EFFECT_JOURNAL_NONCANONICAL_RECORD")

    def test_only_utf8_and_finite_json_numbers_are_accepted(self) -> None:
        text = requested().serialize().decode().rstrip("\n")
        for encoding in ("utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"):
            with self.subTest(encoding=encoding):
                self.assert_denied(text.encode(encoding) + b"\n")
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(value=value):
                raw = requested().serialize().replace(b'"sequence":1', b'"sequence":' + value)
                self.assert_denied(raw, "EFFECT_JOURNAL_NONFINITE_NUMBER")

    def test_failed_encoding_and_bad_outcome_do_not_mutate_state(self) -> None:
        journal = requested()
        before = copy.deepcopy(journal.snapshot())
        encoded = journal.serialize()
        with self.assertRaises(effect.EffectError):
            journal.cancel("op-1", "\ud800")
        self.assertEqual(journal.snapshot(), before)
        self.assertEqual(journal.serialize(), encoded)
        journal.prepare("op-1")
        journal.dispatch("op-1", sha(b"dispatch"))
        before = copy.deepcopy(journal.snapshot())
        for method, value in ((journal.terminal, []), (journal.reconcile, {})):
            with self.subTest(method=method.__name__), self.assertRaises(effect.EffectError):
                method("op-1", value, sha(b"provider"))
            self.assertEqual(journal.snapshot(), before)

    def test_resource_bounds_apply_before_state_change(self) -> None:
        raw = requested().serialize()
        with mock.patch.object(effect, "MAX_RECORD_BYTES", len(raw) - 1):
            self.assert_denied(raw, "EFFECT_JOURNAL_RECORD_TOO_LARGE")
        with mock.patch.object(effect, "MAX_JOURNAL_BYTES", len(raw) - 1):
            self.assert_denied(raw, "EFFECT_JOURNAL_TOO_LARGE")
        journal = requested()
        before = copy.deepcopy(journal.snapshot())
        with mock.patch.object(effect, "MAX_RECORDS", 1), self.assertRaises(effect.EffectError):
            journal.prepare("op-1")
        self.assertEqual(journal.snapshot(), before)
        with self.assertRaises(effect.EffectError):
            journal.cancel("op-1", "x" * (effect.MAX_REASON_BYTES + 1))
        self.assertEqual(journal.snapshot(), before)

    def test_torn_tail_is_bounded_but_complete_bad_line_fails(self) -> None:
        journal = requested()
        journal.cancel("op-1", "用户取消 🚀")
        raw = journal.serialize()
        recovered = effect.EffectJournal.recover(raw + b'{"event":')
        self.assertTrue(recovered.discarded_torn_tail)
        self.assertEqual(recovered.serialize(), raw)
        for tail in (b'{"event":\n', b"\n", b"not-json\n", b"[]\n"):
            with self.subTest(tail=tail):
                self.assert_denied(raw + tail)

    def test_independent_checkpoint_detects_suffix_deletion_and_rehashed_history(self) -> None:
        original = requested()
        original.prepare("op-1")
        original.dispatch("op-1", sha(b"dispatch"))
        count = len(original.records)
        head = original.records[-1]["record_sha256"]
        recovered = effect.EffectJournal.recover(
            original.serialize(),
            expected_record_count=count,
            expected_head_record_sha256=head,
        )
        self.assertEqual(recovered.snapshot(), original.snapshot())
        prefix = b"".join(original.serialize().splitlines(keepends=True)[:-1])
        with self.assertRaises(effect.EffectError):
            effect.EffectJournal.recover(prefix, expected_record_count=count, expected_head_record_sha256=head)
        forged = requested()
        forged.prepare("op-1")
        forged.cancel("op-1", "forged")
        with self.assertRaises(effect.EffectError):
            effect.EffectJournal.recover(
                forged.serialize(),
                expected_record_count=count,
                expected_head_record_sha256=head,
            )

    def test_checkpoint_pair_and_types_fail_closed(self) -> None:
        raw = requested().serialize()
        invalid = (
            {"expected_record_count": 1},
            {"expected_head_record_sha256": "0" * 64},
            {"expected_record_count": True, "expected_head_record_sha256": "0" * 64},
            {"expected_record_count": -1, "expected_head_record_sha256": "0" * 64},
            {"expected_record_count": 1, "expected_head_record_sha256": "bad"},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(effect.EffectError):
                effect.EffectJournal.recover(raw, **kwargs)

    def test_legacy_self_test_fields_and_nonclaims_are_preserved(self) -> None:
        result = effect.self_test()
        self.assertEqual(result["status"], "PASS_EFFECT_RECONCILIATION_REFERENCE")
        self.assertEqual(result["applied_state"], "RECONCILED_APPLIED")
        self.assertEqual(result["not_applied_state"], "RECONCILED_NOT_APPLIED")
        self.assertFalse(result["automatic_replay_after_dispatch"])
        self.assertFalse(result["external_effects_executed"])
        self.assertFalse(result["persistent_journal_integrated"])
        self.assertFalse(result["provider_reconciliation_integrated"])
        self.assertFalse(result["release_ready"])


if __name__ == "__main__":
    unittest.main()
