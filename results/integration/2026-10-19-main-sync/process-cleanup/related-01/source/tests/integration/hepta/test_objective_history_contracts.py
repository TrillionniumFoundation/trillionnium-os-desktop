#!/usr/bin/env python3
"""Synthetic validator regressions. These are not original-owner runtime evidence."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_objective_history as history


def synthetic_records():
    binding = {"commit": "d" * 40, "tree": "e" * 40}
    publications = []
    for sequence, disposition in [(1, "compiled"), (2, "explicit_abstain"), (3, "compiled"), (4, "compiled")]:
        publications.append({
            "run_id": f"run.{sequence}", "publication_sequence": sequence,
            "publication_digest": str(sequence) * 64, "chain_digest": str(sequence + 3) * 64,
            "signed_body_digest": "7" * 64, "profile_digest": "8" * 64,
            "expires_at_ms": 100_000,
            "outcome": {"type": disposition},
        })

    def result(index, *, anchor=None, issue=None, spawn=1):
        value = {"schema_version": 1, "status": "unknown" if issue else "historical_publication",
                 "bytes_written": 200, "request_frame_bytes": 200,
                 "identity": {"spawn_generation": spawn, "original_spawn_generation": 1,
                              "peer_uid": 1000, "peer_pid": 123}, "anchor": anchor}
        if issue:
            value["issue"] = issue
        else:
            value["publication"] = copy.deepcopy(publications[index])
            value["response_generation"] = spawn
        return value

    first = result(0)
    second = result(1)
    lost = result(2)
    capacity = result(3)
    covered = result(0, anchor={"sequence": 2, "chain_digest": publications[1]["chain_digest"]})
    all_results = [first, second, covered, lost, capacity, result(0, issue="anchor_mismatch"),
                   result(1, issue="publication_outside_anchor"), result(0, issue="no_matching_publication"),
                   result(2, spawn=5), result(1, spawn=5,
                       anchor={"sequence": 4, "chain_digest": publications[3]["chain_digest"]}),
                   result(0, issue="anchor_missing", spawn=9),
                   result(3, issue="anchor_missing", spawn=13), result(0, spawn=13)]
    submissions = []
    for value in [first, second]:
        publication = value["publication"]
        submissions.append({"status": "admitted", "bytes_written": 300, "request_frame_bytes": 300,
            "receipt": {"publication_digest": publication["publication_digest"],
                "chain_digest": publication["chain_digest"], "idempotent": False, "response_generation": 1}})
    for run in ["run.4", "run.5"]:
        submissions.append({"status": "submit_unknown", "issue": "objective_owner_request_rejected",
            "bytes_written": 300, "request_frame_bytes": 300, "identity": {"run_id": run}})
    loss = {"response_bytes_read": 0, "response_discarded_by_harness": True,
            "hepta_submit_cli_loss_case": False, "submission_outcome": "unknown", "bytes_written": 300,
            "request_frame_bytes": 300, "run_id": "run.3", "peer_pid": 123, "peer_uid": 1000}
    checks = [{"history": value} for value in all_results]
    checks[0]["submission"] = submissions[0]
    checks[1]["submission"] = submissions[1]
    checks[3].update({"loss": loss, "resubmission_count": 0})
    checks[4].update({"submission": submissions[2], "run_status": None, "resubmission_count": 0,
        "active_run_ids": ["run.1", "run.3"], "active_runs_before_submission": [
            {"phase": "admitted", "terminal_observed": False}, {"phase": "admitted", "terminal_observed": False}],
        "source_inference": "original_default_run_capacity_exhausted", "specific_original_error_bytes_observed": False})
    checks[8].update({"old_spawn": 1, "new_spawn": 5, "old_pid": 123, "new_pid": 456,
                      "run_status": None, "resubmission_count": 0})
    checks[9].update({"expires_at_ms": 100_000, "observed_at_ms": 100_001,
        "wait_elapsed_ms": 1, "wait_bound_ms": 30_000, "resubmission_count": 0})
    for index, old, new, before, injected, recovered in [(10, 5, 9, "d", "a", "a"), (11, 9, 13, "a", "e", "c")]:
        checks[index].update({"resubmission_count": 0, "fault": {
            "owner_confirmed_stopped_before_fault": True, "old_spawn": old, "new_spawn": new,
            "recovery_owner": "original_agentd", "before_sha256": before * 64,
            "injected_sha256": injected * 64, "recovered_sha256": recovered * 64}})
    checks[12].update({"issuer_revoked": True, "issuer_restored": False})
    checks += [{"submission": submissions[-1], "journal_unchanged": True}, {"active": False}]
    records = [{"event": "history_query_observed", "result": value,
                "exit_code": 12 if value["status"] == "unknown" else 0, "journal_unchanged": True,
                "journal_sha256": "abbcddddddacc"[index] * 64}
               for index, value in enumerate(all_results)]
    records += [{"event": "submission_observed", "result": value,
                 "exit_code": 0 if value["status"] == "admitted" else 12} for value in submissions]
    records += [{"event": "objective_response_discarded", "evidence": loss}]
    records += [{"event": "objective_history_check", "check": name, "evidence": evidence}
                for name, evidence in zip(history.CHECKS, checks, strict=True)]
    records += [{"event": "acceptance_pass", "checks": history.CHECKS, "source_binding": binding,
                 "isolated_test_issuer": True, "objective_request_attempts": 5,
                 "published_objective_requests": 4, "recovery_resubmissions": 0,
                 "not_executed": history.NOT_EXECUTED, **dict.fromkeys(history.FALSE_SCOPE, False)}]
    return records, binding


class ReceiptContracts(unittest.TestCase):
    def setUp(self):
        self.records, self.binding = synthetic_records()

    def core(self, index):
        return next(record["evidence"] for record in self.records
                    if record.get("check") == history.CHECKS[index])

    def reject(self):
        with self.assertRaises(history.original.GateError):
            history.verify_records(self.records, self.binding)

    def test_synthetic_positive_validator_only(self):
        history.verify_records(self.records, self.binding)

    def test_new_owner_source_is_required(self):
        self.binding = {"commit": "f" * 40}
        self.reject()

    def test_removed_real_cli_result_rejected(self):
        self.records.pop(0)
        self.reject()

    def test_changed_submission_publication_rejected(self):
        self.core(0)["submission"]["receipt"]["publication_digest"] = "f" * 64
        self.reject()

    def test_harness_loss_cannot_be_claimed_as_submit_cli_loss(self):
        self.core(3)["loss"]["hepta_submit_cli_loss_case"] = True
        self.reject()

    def test_partial_send_does_not_qualify_loss_after_full_send(self):
        self.core(3)["loss"]["bytes_written"] = 1
        self.reject()

    def test_recovery_resubmission_cannot_be_hidden_in_final_counts(self):
        self.core(8)["resubmission_count"] = 1
        self.reject()

    def test_old_spawn_on_replacement_query_is_rejected(self):
        self.core(8)["history"]["identity"]["spawn_generation"] = 1
        self.reject()

    def test_live_owner_file_mutation_cannot_be_marked_qualified(self):
        self.core(10)["fault"]["owner_confirmed_stopped_before_fault"] = False
        self.reject()

    def test_truncation_must_recover_exact_previously_observed_prefix(self):
        self.core(11)["fault"]["recovered_sha256"] = "f" * 64
        self.reject()

    def test_anchor_missing_cannot_be_promoted_to_publication(self):
        value = self.core(11)["history"]
        value["status"] = "historical_publication"
        value["publication"] = self.core(3)["history"]["publication"]
        self.reject()

    def test_issuer_restoration_does_not_prove_revoked_history_read(self):
        self.core(12)["issuer_restored"] = True
        self.reject()

    def test_postpublication_null_projection_is_required(self):
        self.core(4)["run_status"] = {"phase": "admitted"}
        self.reject()

    def test_postpublication_rejection_must_bind_same_run(self):
        self.core(4)["submission"]["identity"]["run_id"] = "different-run"
        self.reject()

    def test_capacity_inference_cannot_be_claimed_as_observed_error_bytes(self):
        self.core(4)["specific_original_error_bytes_observed"] = True
        self.reject()

    def test_unexpired_query_cannot_be_claimed_as_real_expiry(self):
        self.core(9)["observed_at_ms"] = self.core(9)["expires_at_ms"]
        self.reject()

    def test_unbounded_expiry_wait_cannot_be_qualified(self):
        self.core(9)["wait_elapsed_ms"] = 30_001
        self.reject()

    def test_effect_scope_cannot_be_promoted(self):
        self.records[-1]["operations_dispatch"] = True
        self.reject()


class SourceContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "contract.json"
        self.contract = {"schema_version": 1,
            "repository": "https://github.com/TrillionniumFoundation/hepta-private-ci",
            "base_commit": history.original.PIN, "commit": "d" * 40,
            "cargo_lock_sha256": "a" * 64, "control_schema_version": 2,
            "profile": "linux-local-known-objective-history",
            "read_method_allowlist": ["ObjectiveAdmission"],
            "max_control_frame_bytes_including_newline": 65_536,
            "files": [{"path": "codex-rs/hepta-agent-protocol/src/objective_history.rs", "sha256": "b" * 64}]}
        self.write_contract()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "contract.json"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Contract Test",
                        "-c", "user.email=contract-test@example.invalid", "commit", "-qm", "fixture"], check=True)

    def write_contract(self):
        self.path.write_text(json.dumps(self.contract) + "\n")

    def test_tracked_contract_is_read_without_changing_old_pin(self):
        original_pin = history.original.PIN
        contract, evidence = history.read_contract(self.path)
        self.assertEqual(contract, self.contract)
        self.assertEqual(evidence["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(history.original.PIN, original_pin)

    def test_uncommitted_pin_substitution_rejected(self):
        self.contract["commit"] = "e" * 40
        self.write_contract()
        with self.assertRaisesRegex(history.original.GateError, "not_committed_exactly"):
            history.read_contract(self.path)

    def test_source_exact_head_is_checked_before_files(self):
        with patch.object(history.original, "git", return_value="e" * 40):
            with self.assertRaisesRegex(history.original.GateError, "commit_mismatch"):
                history.verify_source(self.root, self.contract)

    def test_dirty_owner_checkout_rejected(self):
        with patch.object(history.original, "git", side_effect=["d" * 40, " M changed.rs"]):
            with self.assertRaisesRegex(history.original.GateError, "not_clean"):
                history.verify_source(self.root, self.contract)


if __name__ == "__main__":
    unittest.main()
