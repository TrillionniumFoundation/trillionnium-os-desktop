#!/usr/bin/env python3
"""Negative tests for receipt acceptance; synthetic records never qualify runtime."""

import copy
from pathlib import Path
import unittest

import run_original_agentd as original
import run_original_objective as objective


def validator_fixture():
    """A small structurally valid record set for the validator, not Agentd output."""
    run = {"run_id": "run.desktop-compiled", "revision": 1, "phase": "admitted",
           "authority_epoch": 1, "generation": 2, "terminal_observed": False, "idempotent": False}
    receipt = {"run_id": run["run_id"], "response_generation": 2, "disposition": "compiled",
               "publication_digest": "1" * 64, "chain_digest": "2" * 64}
    abstain_receipt = {"run_id": "run.desktop-abstain", "response_generation": 2,
                       "disposition": "explicit_abstain", "publication_digest": "3" * 64,
                       "chain_digest": "4" * 64}
    identity = {"agent_id": "33333333-3333-4333-8333-333333333333", "spawn_generation": 1,
                "peer_pid": 3001, "objective_revision": 1, "authority_epoch": 1}
    old_owner = {"agent_id": identity["agent_id"], "spawn_generation": 1, "process_id": 3001,
                 "active": True, "healthy": True}
    new_owner = dict(old_owner, spawn_generation=4, process_id=3002)
    sample = dict(run, sampled_unix_ms=1000, observation_sequence=2)
    runtime = "/tmp/ho-validator-only/objective-ui"

    def phase(number, owner, instance, pid, tid, connection, attempted, sampled):
        run_projection = {"run_id": run["run_id"], "connection": connection,
                          "last_attempt_unix_ms": attempted, "error_code": None,
                          "last_observation": copy.deepcopy(sampled), "observation_gap": False}
        snapshot = {"type": "snapshot", "session_instance": instance, "tasks": [], "hepta": {
            "connection": "observed", "last_attempt_unix_ms": attempted,
            "last_observation": {"agent_id": owner["agent_id"], "spawn_generation": owner["spawn_generation"],
                                 "current_generation": owner["spawn_generation"] + 1,
                                 "health": {"process_id": owner["process_id"], "ready": True, "lifecycle": "running"}},
            "run": run_projection}}
        name = objective.SESSION_PHASES[number - 1]
        return {"event": "objective_session_phase_observed", "phase": name, "sequence": number,
                "session_pid": pid, "worker_tid": tid, "session_instance": instance,
                "runtime_dir": runtime, "session_socket_path": str(Path(runtime) / "trillionnium-ui/session.sock"),
                "recorded_unix_ms": attempted + 1, "original": copy.deepcopy(owner), "snapshot": snapshot,
                "ack": {"sequence": number, "phase": name, "session_instance": instance},
                "capture_ack_is_coordination_only": True, "evidence": {}}

    first = phase(1, old_owner, "a" * 32, 2001, 2002, "observed", 1000, sample)
    first["evidence"] = {"original_run": copy.deepcopy(run)}
    stale = phase(2, new_owner, "a" * 32, 2001, 2002, "stale", 1000, sample)
    stale["snapshot"]["hepta"]["connection"] = "stale"
    stale["snapshot"]["hepta"]["run"].update(error_code="generation_fenced", observation_gap=True)
    stale["snapshot"]["hepta"]["last_attempt_unix_ms"] = 2000
    stale["evidence"] = {"first_stale_snapshot": copy.deepcopy(stale["snapshot"]),
                         "retained_run_unchanged_across_failed_samples": True}
    stale["snapshot"]["hepta"]["last_attempt_unix_ms"] = 3000
    stale["recorded_unix_ms"] = 3001
    replacement = phase(3, new_owner, "b" * 32, 2010, 2011, "projection_missing", 4000, None)
    replacement["snapshot"]["hepta"]["run"]["error_code"] = "run_projection_missing"
    replacement["evidence"] = {"missing_projection_is_not_non_admission": True}

    def stop(phase):
        return dict({field: phase[field] for field in ["session_pid", "session_instance", "worker_tid"]},
                    event="objective_session_stopped", signal=9, exit_code=None)

    checks = [{"event": "objective_check", "check": name, "evidence": {}} for name in objective.CHECKS]
    checks[0]["evidence"] = {"receipt": receipt, "run": run}
    checks[2]["evidence"] = {"receipt": abstain_receipt}
    checks[6]["evidence"] = {"old_spawn": 1, "new_spawn": 4, "old_pid": 3001, "new_pid": 3002}
    post_owner = {"agent_id": identity["agent_id"], "spawn_generation": 4,
                  "health": {"process_id": 3002, "ready": True, "lifecycle": "running"}}
    checks[7]["evidence"] = {"transport_status": "submit_unknown", "issue": "objective_protocol_mismatch",
                             "bytes_written": 1024, "request_frame_bytes": 1024,
                             "post_request_owner": post_owner, "post_request_run": None,
                             "journal_unchanged": True}
    checks[8]["evidence"] = {
        "acknowledged_sequence": 2, "first_acknowledged_chain_digest": receipt["chain_digest"],
        "acknowledged_chain_digest": abstain_receipt["chain_digest"],
        "records": [{"run_id": value["run_id"], "publication_digest": value["publication_digest"],
                     "chain_digest": value["chain_digest"], "journal_sequence": number,
                     "publication_binding_checked": True, "changed_publication_digest_rejected": True}
                    for number, value in enumerate([receipt, abstain_receipt], 1)]}
    submissions = [{"event": "submission_observed", "result": {}} for _ in range(7)]
    submissions[0]["result"] = {"status": "admitted", "receipt": receipt, "identity": identity}
    submissions[2]["result"] = {"status": "admitted", "receipt": abstain_receipt}
    submissions[6]["result"] = {"status": "submit_unknown", "issue": "objective_protocol_mismatch",
                                 "bytes_written": 1024, "request_frame_bytes": 1024,
                                 "identity": dict(identity, peer_pid=3002)}
    result = []
    for index, check in enumerate(checks):
        if index < 6:
            result.append(submissions[index])
        if index == 7:
            result.append(submissions[6])
        result.append(check)
        if index == 5:
            result.append(first)
        if index == 7:
            result += [stale, stop(stale), replacement, stop(replacement)]
    result.append({"event": "acceptance_pass", "checks": objective.CHECKS,
                   "original_commit": original.PIN, "isolated_test_issuer": True,
                   "production_issuer": False, "model_turn": False, "operations_dispatch": False,
                   "device_effect": False, "canonical_intelligence": False,
                   "historical_run_resumed": False, "session_projection": True})
    return result


def phases(records):
    return [entry for entry in records if entry.get("event") == "objective_session_phase_observed"]


class ObjectiveReceiptValidation(unittest.TestCase):
    def test_explicit_scopes_accept_structural_reference_records(self):
        records = validator_fixture()
        objective.verify_records(records, True)
        records = [entry for entry in records if not entry["event"].startswith("objective_session_")]
        records[-1]["session_projection"] = False
        objective.verify_records(records, False)

    def test_no_session_cannot_claim_session_qualification(self):
        records = validator_fixture()
        records = [entry for entry in records if not entry["event"].startswith("objective_session_")]
        with self.assertRaises(original.GateError):
            objective.verify_records(records, True)

    def test_missing_phase_cannot_pass(self):
        records = validator_fixture()
        records.remove(phases(records)[1])
        with self.assertRaises(original.GateError):
            objective.verify_records(records, True)

    def test_silent_session_or_worker_replacement_cannot_pass(self):
        for field, value in [("session_pid", 9991), ("worker_tid", 9992), ("session_instance", "c" * 32)]:
            with self.subTest(field=field):
                records = validator_fixture()
                changed = phases(records)[1]
                changed[field] = value
                if field == "session_instance":
                    changed["snapshot"]["session_instance"] = value
                    changed["ack"]["session_instance"] = value
                with self.assertRaises(original.GateError):
                    objective.verify_records(records, True)

    def test_wrong_scope_or_renewed_run_history_cannot_pass(self):
        for field in ["production_issuer", "model_turn", "operations_dispatch", "device_effect",
                      "canonical_intelligence", "historical_run_resumed"]:
            with self.subTest(field=field):
                records = validator_fixture()
                records[-1][field] = True
                with self.assertRaises(original.GateError):
                    objective.verify_records(records, True)
        records = validator_fixture()
        phases(records)[1]["snapshot"]["hepta"]["run"]["last_attempt_unix_ms"] += 1
        with self.assertRaises(original.GateError):
            objective.verify_records(records, True)

    def test_changed_owner_or_run_receipt_cannot_pass(self):
        for mutation in [lambda phase: phase["original"].update(process_id=9999),
                         lambda phase: phase["snapshot"]["hepta"]["run"]["last_observation"].update(generation=99),
                         lambda phase: phase["snapshot"].update(tasks=[{"id": "unexpected-host-task"}])]:
            records = validator_fixture()
            mutation(phases(records)[0])
            with self.assertRaises(original.GateError):
                objective.verify_records(records, True)

    def test_missing_projection_is_not_non_admission(self):
        records = validator_fixture()
        phases(records)[2]["evidence"]["missing_projection_is_not_non_admission"] = False
        with self.assertRaises(original.GateError):
            objective.verify_records(records, True)

    def test_changed_publication_digest_cannot_pass_otherwise_matching_receipts(self):
        for submission_number, check_name in [(0, "compiled_original_admission"),
                                              (2, "explicit_abstain_durable_without_run")]:
            with self.subTest(check=check_name):
                records = validator_fixture()
                submissions = [entry for entry in records if entry["event"] == "submission_observed"]
                # The fixture shares this receipt with its check record, so
                # the same wrong valid digest still agrees across both records.
                submissions[submission_number]["result"]["receipt"]["publication_digest"] = "e" * 64
                check = next(entry for entry in records if entry.get("check") == check_name)
                self.assertEqual(check["evidence"]["receipt"], submissions[submission_number]["result"]["receipt"])
                with self.assertRaises(original.GateError):
                    objective.verify_records(records, True)

    def test_original_journal_negative_or_binding_cannot_be_omitted(self):
        for field in ["publication_binding_checked", "changed_publication_digest_rejected"]:
            records = validator_fixture()
            journal = next(entry for entry in records if entry.get("check") == "original_journal_matches_receipts")
            journal["evidence"]["records"][0][field] = False
            with self.subTest(field=field), self.assertRaises(original.GateError):
                objective.verify_records(records, True)

    def test_old_spawn_transport_failure_or_partial_write_cannot_qualify(self):
        cases = [("not_sent", "objective_unavailable_transport", 0, 1024),
                 ("submit_unknown", "objective_read_failed", 1024, 1024),
                 ("submit_unknown", "objective_protocol_mismatch", 1, 1024),
                 ("submit_unknown", "objective_protocol_mismatch", 0, 0)]
        for status, issue, written, frame in cases:
            with self.subTest(status=status, issue=issue, written=written):
                records = validator_fixture()
                last = [entry for entry in records if entry["event"] == "submission_observed"][-1]["result"]
                last.update(status=status, issue=issue, bytes_written=written, request_frame_bytes=frame)
                fence = next(entry for entry in records if entry.get("check") == "old_spawn_not_accepted")["evidence"]
                fence.update(transport_status=status, issue=issue, bytes_written=written, request_frame_bytes=frame)
                with self.assertRaises(original.GateError):
                    objective.verify_records(records, True)

    def test_old_spawn_requires_same_live_owner_and_no_current_run_projection(self):
        mutations = [lambda evidence: evidence["post_request_owner"]["health"].update(process_id=9999),
                     lambda evidence: evidence["post_request_owner"]["health"].update(ready=False),
                     lambda evidence: evidence.update(post_request_run={"run_id": "run.desktop-compiled"})]
        for mutation in mutations:
            records = validator_fixture()
            fence = next(entry for entry in records if entry.get("check") == "old_spawn_not_accepted")["evidence"]
            mutation(fence)
            with self.assertRaises(original.GateError):
                objective.verify_records(records, True)

    def test_wrong_stop_or_runtime_identity_cannot_pass(self):
        records = validator_fixture()
        next(entry for entry in records if entry["event"] == "objective_session_stopped")["session_pid"] = 9999
        with self.assertRaises(original.GateError):
            objective.verify_records(records, True)
        records = validator_fixture()
        phases(records)[2]["runtime_dir"] = "/tmp/different-runtime"
        with self.assertRaises(original.GateError):
            objective.verify_records(records, True)


if __name__ == "__main__":
    unittest.main()
