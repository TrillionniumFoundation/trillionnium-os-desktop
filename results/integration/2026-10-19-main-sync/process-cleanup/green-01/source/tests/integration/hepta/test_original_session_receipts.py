"""Negative receipt/parser cases only; these fixtures never qualify a daemon.

Actual Session lifecycle evidence comes from the original-linked Rust probe.
"""

from copy import deepcopy
import unittest

import run_original_agentd as gate


def cli_receipt():
    return {"event": "acceptance_pass", "checks": gate.EXPECTED_CHECKS,
            "objective_submission": False, "model_turn": False, "device_effect": False}


def session_receipts():
    records = []
    for index, phase in enumerate(gate.SESSION_PHASES):
        second = index >= 4
        instance = "b" * 32 if second else "a" * 32
        records.append({
            "event": "session_phase_observed", "sequence": index + 1, "phase": phase,
            "session_pid": 200 if second else 100,
            "worker_tid": 201 if second else 101,
            "session_instance": instance, "runtime_dir": "/fixture/runtime",
            "session_socket_path": "/fixture/runtime/trillionnium-ui/session.sock",
            "snapshot": {"session_instance": instance},
        })
        if index in (3, 5):
            records.append({"event": "session_stopped", "session_pid": records[-1]["session_pid"],
                            "worker_tid": records[-1]["worker_tid"], "session_instance": instance,
                            "signal": 9})
    records.append({
        "event": "session_acceptance_pass", "checks": gate.SESSION_CHECKS,
        "first_session_pid": 100, "first_session_instance": "a" * 32,
        "replacement_session_pid": 200, "replacement_session_instance": "b" * 32,
        "objective_submission": False, "model_turn": False, "device_effect": False,
        "shell_capture_qualified_by_this_record": False,
    })
    records.append(cli_receipt())
    return records


class OriginalSessionReceiptTests(unittest.TestCase):
    def test_legacy_eight_check_gate_cannot_claim_session(self):
        gate.validate_runtime_records([cli_receipt()], False)
        with self.assertRaisesRegex(gate.GateError, "session_acceptance_checks_incomplete"):
            gate.validate_runtime_records([cli_receipt()], True)
        with self.assertRaisesRegex(gate.GateError, "unexpected_session_qualification"):
            gate.validate_runtime_records(session_receipts(), False)

    def test_same_worker_and_instance_intervals_are_checked_independently(self):
        gate.validate_runtime_records(session_receipts(), True)
        for key, replacement in [("session_pid", 500), ("worker_tid", 600), ("session_instance", "c" * 32)]:
            with self.subTest(key=key):
                records = session_receipts()
                records[2][key] = replacement
                with self.assertRaisesRegex(gate.GateError, "session_identity_changed_within_continuous_interval"):
                    gate.validate_runtime_records(records, True)

    def test_missing_reordered_and_duplicated_phase_cannot_pass(self):
        for change in [lambda items: items.pop(2),
                       lambda items: items.insert(2, deepcopy(items[2])),
                       lambda items: items.__setitem__(slice(1, 3), list(reversed(items[1:3])))]:
            records = session_receipts()
            change(records)
            with self.assertRaisesRegex(gate.GateError, "session_phase_receipts_incomplete"):
                gate.validate_runtime_records(records, True)

    def test_snapshot_and_final_receipt_cannot_substitute_another_session(self):
        records = session_receipts()
        records[1]["snapshot"]["session_instance"] = "wrong-session"
        with self.assertRaisesRegex(gate.GateError, "session_snapshot_identity_disagrees"):
            gate.validate_runtime_records(records, True)
        records = session_receipts()
        records[-2]["first_session_pid"] = 999
        with self.assertRaisesRegex(gate.GateError, "session_final_receipt_identity_disagrees"):
            gate.validate_runtime_records(records, True)

    def test_missing_cleanup_or_worker_identity_fails(self):
        records = session_receipts()
        records.pop(4)
        with self.assertRaisesRegex(gate.GateError, "session_cleanup_receipts_incomplete"):
            gate.validate_runtime_records(records, True)
        records = session_receipts()
        del records[0]["worker_tid"]
        with self.assertRaisesRegex(gate.GateError, "session_process_or_worker_identity_missing"):
            gate.validate_runtime_records(records, True)

    def test_session_receipt_cannot_grant_shell_or_effect_qualification(self):
        for key in ["objective_submission", "model_turn", "device_effect", "shell_capture_qualified_by_this_record"]:
            with self.subTest(key=key):
                records = session_receipts()
                records[-2][key] = True
                with self.assertRaisesRegex(gate.GateError, "unexpected_session_effect_or_capture_claim"):
                    gate.validate_runtime_records(records, True)


if __name__ == "__main__":
    unittest.main()
