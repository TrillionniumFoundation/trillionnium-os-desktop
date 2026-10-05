"""Real offline Ed25519 and private-disk TaskFlow source regressions.

Test keys are generated only in temporary directories. No crypto case is skipped;
missing /usr/bin/openssl is a test failure, never approved authority.
"""
from __future__ import annotations

import base64
import copy
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
import select
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("taskflow_candidate", ROOT / "platform/taskflow.py")
assert SPEC and SPEC.loader
tf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tf
SPEC.loader.exec_module(tf)

NOW = 1_000_000
ZERO_SIGNATURE = base64.b64encode(bytes(64)).decode("ascii")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class Clock:
    def __init__(self):
        self.monotonic = 1_000_000_000
        self.unix = NOW

    def tick(self, milliseconds: int, *, wall: bool = True):
        self.monotonic += milliseconds * 1_000_000
        if wall:
            self.unix += milliseconds


class TaskFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory(prefix="taskflow-crypto-")
        cls.key_path = Path(cls.keys.name)
        for name in ("approved", "other"):
            subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "ED25519", "-out", str(cls.key_path / (name + ".private"))], check=True, capture_output=True, env=tf.OPENSSL_ENV)
            subprocess.run(["/usr/bin/openssl", "pkey", "-in", str(cls.key_path / (name + ".private")), "-pubout", "-outform", "DER", "-out", str(cls.key_path / (name + ".der"))], check=True, capture_output=True, env=tf.OPENSSL_ENV)
        public = (cls.key_path / "approved.der").read_bytes()
        cls.root = tf.PinnedIssuerRoot("approval-service", "approval-key:1", public, hashlib.sha256(public).hexdigest(), "hepta-browserd", "policy:source-v1", NOW - 1000, NOW + 600_000)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="taskflow-store-")
        self.path = Path(self.directory.name) / "store"
        self.path.mkdir(mode=0o700)
        self.store = tf.DurableGrantStore(self.path)
        self.addCleanup(self.store.close)
        self.addCleanup(self.directory.cleanup)
        self.clock = Clock()
        self.binding = tf.CurrentBinding("taskflow-principal", "native-session", 1, "https://example.com", "page", "native-page", 1, 2, 0)
        self.policy = tf.TaskPolicy("task:1", self.binding, "hepta-browserd", "policy:source-v1", max_actions=3)
        self.verifier = tf.ExternalPermitVerifier((self.root,))
        self.flow = self.coordinator(self.store)
        self.flow.create_task(self.policy)
        self.called = []

    def coordinator(self, store):
        return tf.TaskFlowCoordinator(self.verifier, store, monotonic_ns=lambda: self.clock.monotonic, unix_ms=lambda: self.clock.unix)

    def proposal(self, **updates):
        value = {
            "schema": tf.PROPOSAL_SCHEMA, "task_id": "task:1", "action_id": "action:1",
            "principal_id": self.binding.principal_id, "audience": self.policy.audience,
            "policy_revision": self.policy.policy_revision, "session_id": self.binding.session_id,
            "session_generation": 1, "origin": self.binding.origin, "operation": "page.observe",
            "resource": {"kind": "page", "target": "native-page", "document_generation": 1,
                         "semantic_snapshot_revision": 2, "mutation_epoch": 0},
            "arguments": {"mode": "semantic"}, "action_budget_ms": 20_000,
        }
        value.update(updates)
        return value

    def permit(self, proposal=None, **updates):
        proposal = self.proposal() if proposal is None else proposal
        resource = {
            "task_id": proposal["task_id"], "action_id": proposal["action_id"], "session_id": proposal["session_id"],
            "session_generation": proposal["session_generation"], "origin": proposal["origin"],
            "proposal_sha256": tf.proposal_sha256(canonical(proposal)), "target": copy.deepcopy(proposal["resource"]),
            "arguments_sha256": hashlib.sha256(canonical(proposal["arguments"])).hexdigest(),
            "action_budget_ms": proposal["action_budget_ms"],
        }
        value = {"schema": tf.PERMIT_SCHEMA, "permit_id": "permit:1", "issuer": self.root.issuer,
                 "subject": proposal["principal_id"], "audience": proposal["audience"], "operation": proposal["operation"],
                 "resource": resource, "issued_unix_ms": NOW, "expires_unix_ms": NOW + 60_000,
                 "nonce": "1" * 64, "policy_revision": proposal["policy_revision"],
                 "signature": {"algorithm": "ed25519", "key_id": self.root.key_id, "value": ZERO_SIGNATURE}}
        value.update(updates)
        return value

    def sign(self, value, signer="approved"):
        value = copy.deepcopy(value)
        with tempfile.TemporaryDirectory(prefix="taskflow-sign-") as directory:
            path = Path(directory)
            (path / "input").write_bytes(tf.permit_signing_bytes(canonical(value)))
            subprocess.run(["/usr/bin/openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.key_path / (signer + ".private")), "-in", str(path / "input"), "-out", str(path / "signature")], check=True, capture_output=True, env=tf.OPENSSL_ENV)
            value["signature"]["value"] = base64.b64encode((path / "signature").read_bytes()).decode("ascii")
        return canonical(value)

    def ready(self, **permit_updates):
        self.flow.propose("task:1", canonical(self.proposal()))
        return self.flow.approve("task:1", self.sign(self.permit(**permit_updates)))

    def adapter(self, payload, control):
        control.ensure_active(self.binding)
        self.assertEqual(json.loads(payload)["action_id"], "action:1")
        names = {path.name for path in self.path.glob("*.used")}
        self.assertEqual(len(names), 3, "all three durable consumptions precede adapter entry")
        self.called.append(payload)
        return tf.EffectOutcome.SUCCEEDED

    def test_real_signed_approval_consumes_before_single_dispatch(self):
        self.assertEqual(self.ready().state, tf.ActionState.APPROVED)
        view = self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertEqual(view.state, tf.ActionState.TERMINAL)
        with self.assertRaises(tf.ReplayRefused):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertEqual(len(self.called), 1)

    def test_default_configuration_cannot_approve_or_dispatch(self):
        flow = tf.TaskFlowCoordinator(monotonic_ns=lambda: self.clock.monotonic, unix_ms=lambda: NOW)
        flow.create_task(self.policy); flow.propose("task:1", canonical(self.proposal()))
        with self.assertRaises(tf.PermitRefused):
            flow.approve("task:1", self.sign(self.permit()))
        with self.assertRaises(tf.ReplayRefused):
            flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called)

    def test_verified_permit_without_concrete_store_cannot_dispatch(self):
        self.flow = self.coordinator(None); self.flow.create_task(self.policy); self.ready()
        with self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called)

    def test_model_self_signature_and_forged_approval_field_are_refused(self):
        self.flow.propose("task:1", canonical(self.proposal()))
        with self.assertRaises(tf.PermitRefused):
            self.flow.approve("task:1", self.sign(self.permit(), signer="other"))
        forged = json.loads(self.sign(self.permit())); forged["approved"] = True
        with self.assertRaises(tf.TaskFlowError):
            self.flow.approve("task:1", canonical(forged))
        self.assertEqual(self.flow.current("task:1").state, tf.ActionState.PROPOSED)

    def test_every_approved_binding_dimension_is_exact(self):
        self.flow.propose("task:1", canonical(self.proposal()))
        for field, replacement in {"subject": "different-principal", "audience": "different-service", "policy_revision": "different-policy"}.items():
            with self.subTest(field=field), self.assertRaises(tf.PermitRefused):
                self.flow.approve("task:1", self.sign(self.permit(**{field: replacement})))
        changes = {"task_id": "different-task", "action_id": "different-action", "session_id": "different-session",
                   "session_generation": 2, "origin": "https://other.example", "proposal_sha256": "a" * 64,
                   "arguments_sha256": "b" * 64, "action_budget_ms": 19_999}
        for field, replacement in changes.items():
            value = self.permit(); value["resource"][field] = replacement
            with self.subTest(field=field), self.assertRaises(tf.PermitRefused):
                self.flow.approve("task:1", self.sign(value))
        for field, replacement in {"target": "different-native-node", "document_generation": 2, "semantic_snapshot_revision": 3, "mutation_epoch": 1}.items():
            value = self.permit(); value["resource"]["target"][field] = replacement
            with self.subTest(field=field), self.assertRaises(tf.PermitRefused):
                self.flow.approve("task:1", self.sign(value))

    def test_crypto_preimage_binds_all_fields_except_signature_value(self):
        payload = self.sign(self.permit())
        value = json.loads(payload)
        changed_value = copy.deepcopy(value); changed_value["signature"]["value"] = ZERO_SIGNATURE
        self.assertEqual(tf.permit_signing_bytes(payload), tf.permit_signing_bytes(canonical(changed_value)))
        for field, replacement in {"permit_id": "permit:changed", "issuer": "other-issuer", "nonce": "2" * 64, "issued_unix_ms": NOW - 1}.items():
            changed = copy.deepcopy(value); changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(tf.PermitRefused):
                self.verifier.verify(canonical(changed), now_unix_ms=NOW)
        changed = copy.deepcopy(value); changed["signature"]["key_id"] = "other-key"
        with self.assertRaises(tf.PermitRefused):
            self.verifier.verify(canonical(changed), now_unix_ms=NOW)
        alias = replace(self.root, key_id="approval-key:2")
        changed["signature"]["key_id"] = alias.key_id
        with self.assertRaises(tf.PermitRefused):
            tf.ExternalPermitVerifier((self.root, alias)).verify(canonical(changed), now_unix_ms=NOW)
        changed = copy.deepcopy(value); changed["signature"]["algorithm"] = "rsa"
        with self.assertRaises(tf.PermitRefused):
            self.verifier.verify(canonical(changed), now_unix_ms=NOW)

    def test_expired_future_unknown_or_revoked_permit_never_admits(self):
        for issued, expires in [(NOW - 1000, NOW), (NOW + 1, NOW + 1000)]:
            with self.assertRaises(tf.PermitRefused):
                self.verifier.verify(self.sign(self.permit(issued_unix_ms=issued, expires_unix_ms=expires)), now_unix_ms=NOW)
        with self.assertRaises(tf.PermitRefused):
            self.verifier.verify(self.sign(self.permit(issuer="unknown-issuer")), now_unix_ms=NOW)
        self.ready(); self.verifier.revoke_permit("permit:1")
        with self.assertRaises(tf.PermitRefused):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called)

    def test_revoked_key_after_approval_is_checked_before_consumption(self):
        self.ready(); self.verifier.revoke_key(self.root.key_id)
        with self.assertRaises(tf.PermitRefused):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(list(self.path.glob("*.used")))

    def test_native_session_or_origin_drift_refuses_effect(self):
        self.ready()
        for binding in [replace(self.binding, session_generation=2), replace(self.binding, session_id="other-session"), replace(self.binding, principal_id="other-principal"), replace(self.binding, origin="https://other.example"),
                        replace(self.binding, resource_target="different-native-target"), replace(self.binding, document_generation=2),
                        replace(self.binding, semantic_snapshot_revision=3), replace(self.binding, mutation_epoch=1)]:
            with self.assertRaises(tf.PermitRefused):
                self.flow.dispatch("task:1", binding, self.adapter)
        self.assertFalse(self.called)

    def test_action_and_signed_expiry_use_original_monotonic_budget(self):
        self.ready(expires_unix_ms=NOW + 10)
        self.clock.tick(11, wall=False)
        with self.assertRaises(tf.DeadlineExceeded):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called)

    def test_approval_delay_does_not_renew_action_budget(self):
        self.flow.propose("task:1", canonical(self.proposal(action_budget_ms=1)))
        self.clock.tick(2)
        with self.assertRaises(tf.DeadlineExceeded):
            self.flow.approve("task:1", self.sign(self.permit(self.proposal(action_budget_ms=1))))

    def test_task_and_action_count_budgets_are_enforced(self):
        # This exercises counters with the injected clock, while approval still
        # performs real Ed25519 verification. A 5ms native-process requirement
        # made scheduler delay fail this case before either counter assertion.
        task_budget_ms = 2_000
        flow = self.coordinator(self.store); flow.create_task(replace(self.policy, task_id="bounded-task", max_actions=1, task_budget_ms=task_budget_ms))
        value = self.proposal(task_id="bounded-task")
        flow.propose("bounded-task", canonical(value))
        flow.approve("bounded-task", self.sign(self.permit(value)))
        flow.dispatch("bounded-task", self.binding, lambda payload, control: tf.EffectOutcome.SUCCEEDED)
        with self.assertRaises(tf.TaskFlowError):
            flow.propose("bounded-task", canonical({**value, "action_id": "second"}))
        self.clock.tick(task_budget_ms + 1)
        with self.assertRaises(tf.DeadlineExceeded):
            flow.propose("bounded-task", canonical({**value, "action_id": "third"}))

    def test_five_ms_task_expiry_refuses_approval_and_effect(self):
        flow = self.coordinator(self.store)
        flow.create_task(replace(self.policy, task_id="expired-task", task_budget_ms=5))
        value = self.proposal(task_id="expired-task")
        flow.propose("expired-task", canonical(value))
        signed = self.sign(self.permit(value))
        self.clock.tick(6)
        with self.assertRaises(tf.DeadlineExceeded):
            flow.approve("expired-task", signed)
        self.assertEqual(flow.current("expired-task").state, tf.ActionState.PROPOSED)
        with self.assertRaises(tf.ReplayRefused):
            flow.dispatch("expired-task", self.binding, self.adapter)
        self.assertFalse(list(self.path.glob("*.used")))
        self.assertFalse(self.called)

    def test_duplicate_json_unknown_fields_numbers_and_deep_input_refused(self):
        for payload in [b'{"schema":"x","schema":"y"}', b'{"n":' + b'1' * 5000 + b'}', b"{" + b'"a":[' * 9 + b"0" + b"]" * 9 + b"}", canonical({**self.proposal(), "approved": True}), canonical(self.proposal(session_generation=True)), canonical(self.proposal(action_budget_ms=1.5))]:
            with self.subTest(payload=payload[:40]), self.assertRaises(tf.TaskFlowError):
                self.flow.propose("task:1", payload)
        for resource in [{**self.proposal()["resource"], "selector": "#model-choice"}, {**self.proposal()["resource"], "kind": {}}]:
            with self.assertRaises(tf.TaskFlowError):
                self.flow.propose("task:1", canonical(self.proposal(resource=resource)))

    def test_closed_typed_operations_and_navigation_origin(self):
        for updates in [{"operation": "eval_js"}, {"arguments": {"mode": "semantic", "script": "anything"}}, {"origin": "https://EXAMPLE.com"}, {"origin": "https://example.com/path"}, {"origin": "hepta-app://signed-app"}, {"origin": "app://signed-app"}, {"resource": {**self.proposal()["resource"], "kind": "navigation"}}]:
            with self.subTest(updates=updates), self.assertRaises(tf.TaskFlowError):
                self.flow.propose("task:1", canonical(self.proposal(**updates)))
        target = {**self.proposal()["resource"], "kind": "navigation"}
        for url in ["https://other.example/path", "https://example.com.evil/path", "https://example.com:443/path"]:
            with self.assertRaises(tf.TaskFlowError):
                self.flow.propose("task:1", canonical(self.proposal(operation="page.navigate", resource=target, arguments={"url": url})))

    def test_cancel_before_dispatch_preserves_no_effect(self):
        self.ready(); self.assertEqual(self.flow.cancel("task:1").state, tf.ActionState.CANCELLED)
        with self.assertRaises(tf.ReplayRefused):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called); self.assertFalse(list(self.path.glob("*.used")))

    def test_human_handoff_before_dispatch_cannot_be_cleared_by_permit(self):
        self.ready(); self.assertEqual(self.flow.handoff_to_human("task:1").state, tf.ActionState.HUMAN_HANDOFF)
        with self.assertRaises(tf.TaskFlowError):
            self.flow.approve("task:1", self.sign(self.permit()))
        with self.assertRaises(tf.ReplayRefused):
            self.flow.dispatch("task:1", self.binding, self.adapter)

    def test_active_cancel_and_handoff_are_visible_to_adapter_control(self):
        for method in ("cancel", "handoff_to_human"):
            with self.subTest(method=method):
                self.flow = self.coordinator(self.store); self.flow.create_task(replace(self.policy, task_id="task:" + method))
                proposal = self.proposal(task_id="task:" + method)
                self.flow.propose(proposal["task_id"], canonical(proposal))
                self.flow.approve(proposal["task_id"], self.sign(self.permit(proposal, permit_id="permit:" + method, nonce=hashlib.sha256(method.encode()).hexdigest())))
                def cancelled_adapter(payload, control):
                    getattr(self.flow, method)(proposal["task_id"])
                    with self.assertRaises(tf.TaskFlowError):
                        control.ensure_active(self.binding)
                    return tf.EffectOutcome.SUCCEEDED
                with self.assertRaises(tf.TaskFlowError):
                    self.flow.dispatch(proposal["task_id"], self.binding, cancelled_adapter)
                self.assertEqual(self.flow.current(proposal["task_id"]).state, tf.ActionState.INDETERMINATE)

    def test_unknown_completion_exception_or_late_success_never_allows_retry(self):
        for outcome in ("exception", "late", "indeterminate", "untyped"):
            with self.subTest(outcome=outcome):
                task_id = "task:" + outcome; proposal = self.proposal(task_id=task_id)
                self.flow.create_task(replace(self.policy, task_id=task_id)); self.flow.propose(task_id, canonical(proposal))
                self.flow.approve(task_id, self.sign(self.permit(proposal, permit_id="permit:" + outcome, nonce=hashlib.sha256(outcome.encode()).hexdigest())))
                def adapter(payload, control):
                    control.ensure_active(self.binding)
                    if outcome == "exception":
                        raise RuntimeError("controlled adapter lost completion")
                    if outcome == "late":
                        self.clock.tick(20_001)
                    return tf.EffectOutcome.INDETERMINATE if outcome == "indeterminate" else tf.EffectOutcome.SUCCEEDED if outcome == "late" else True
                if outcome == "indeterminate":
                    self.assertEqual(self.flow.dispatch(task_id, self.binding, adapter).state, tf.ActionState.INDETERMINATE)
                else:
                    with self.assertRaises((tf.TaskFlowError, RuntimeError)):
                        self.flow.dispatch(task_id, self.binding, adapter)
                self.assertEqual(self.flow.current(task_id).state, tf.ActionState.INDETERMINATE)
                with self.assertRaises(tf.ReplayRefused):
                    self.flow.dispatch(task_id, self.binding, adapter)

    def test_durable_nonce_permit_and_request_replay_survive_service_reopen(self):
        self.ready(); self.flow.dispatch("task:1", self.binding, self.adapter)
        self.store.close(); self.store = tf.DurableGrantStore(self.path); self.addCleanup(self.store.close)
        self.flow = self.coordinator(self.store)
        with self.assertRaises(tf.RecoveryRequired):
            self.flow.create_task(self.policy)
        # A signed different task still cannot reuse the consumed nonce or permit.
        for task_id, permit_id, nonce in [("new-task:nonce", "new-permit", "1" * 64), ("new-task:permit", "permit:1", "2" * 64)]:
            self.flow.create_task(replace(self.policy, task_id=task_id)); proposal = self.proposal(task_id=task_id)
            self.flow.propose(task_id, canonical(proposal)); self.flow.approve(task_id, self.sign(self.permit(proposal, permit_id=permit_id, nonce=nonce)))
            with self.assertRaises(tf.ReplayRefused):
                self.flow.dispatch(task_id, self.binding, self.adapter)
        self.assertEqual(len(self.called), 1)

    def test_same_request_with_substituted_nonce_cannot_execute_twice(self):
        self.ready(); self.flow.dispatch("task:1", self.binding, self.adapter)
        record = json.loads(next(self.path.glob("nonce-*.used")).read_bytes())
        record.update(nonce="3" * 64, permit_id="substituted-permit")
        with self.assertRaises(tf.ReplayRefused):
            self.store._consume(record)
        self.assertEqual(len(self.called), 1)

    def test_file_sync_failure_latches_and_never_calls_adapter(self):
        self.ready()
        with patch.object(tf.os, "fsync", side_effect=OSError(errno.ENOSPC, "controlled full disk")), self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called)
        with self.assertRaises(tf.RecoveryRequired):
            self.store.refuses_task_resume("fresh")
        self.store.close()
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)
        self.assertTrue(list(self.path.glob("*.used")), "partial consumption evidence is retained")

    def test_directory_sync_failure_keeps_all_claims_and_closes_dispatch(self):
        self.ready(); original = os.fsync
        def fail_directory(descriptor):
            import stat
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError(errno.EIO, "controlled directory sync failure")
            return original(descriptor)
        with patch.object(tf.os, "fsync", side_effect=fail_directory), self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called); self.assertEqual(len(list(self.path.glob("*.used"))), 3)
        with self.assertRaises(tf.RecoveryRequired):
            self.store.refuses_task_resume("fresh")

    def test_partial_write_never_gets_repaired_or_dispatched(self):
        self.ready(); original = os.write; count = [0]
        def cut(descriptor, data):
            count[0] += 1
            if count[0] == 1:
                return original(descriptor, data[:5])
            raise OSError(errno.ENOSPC, "controlled partial write")
        with patch.object(tf.os, "write", side_effect=cut), self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called); self.store.close()
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)
        self.assertEqual(next(self.path.glob("*.used")).read_bytes(), b'{"act')

    def test_store_requires_private_mode_and_exclusive_safe_lease(self):
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)
        self.store.close(); os.chmod(self.path / ".taskflow.lock", 0o666)
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)
        os.chmod(self.path / ".taskflow.lock", 0o600); os.chmod(self.path, 0o755)
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)

    def test_symlink_root_or_ancestor_never_acquires_store(self):
        link = Path(self.directory.name) / "linked"; link.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(link)
        ancestor = Path(self.directory.name) / "linked-parent"; ancestor.symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(ancestor / "store")

    def test_parent_replacement_after_admission_blocks_actual_dispatch(self):
        self.ready(); previous = Path(self.directory.name) / "detached"
        self.path.rename(previous); self.path.mkdir(mode=0o700)
        with self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called); self.assertFalse(list(previous.glob("*.used")))

    def test_consumption_hardlink_in_place_corruption_and_missing_alias_refuse_reopen(self):
        self.ready(); self.flow.dispatch("task:1", self.binding, self.adapter)
        record = next(self.path.glob("*.used")); self.store.close()
        hardlink = Path(self.directory.name) / "second-link"; os.link(record, hardlink)
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)
        hardlink.unlink()
        data = bytearray(record.read_bytes()); data[-2] ^= 1; record.write_bytes(data)
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)
        record.unlink()
        with self.assertRaises(tf.RecoveryRequired):
            tf.DurableGrantStore(self.path)

    def test_backward_clock_hands_control_to_human_and_never_renews(self):
        self.ready(); self.clock.monotonic -= 1
        with self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        with self.assertRaises(tf.RecoveryRequired):
            self.flow.create_task(replace(self.policy, task_id="clock-restored-new-task"))
        self.clock.monotonic += 1
        with self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called)

    def test_pin_mismatch_invalid_key_and_noncanonical_signature_refuse(self):
        for updates in [{"public_key_sha256": "0" * 64}, {"public_key_der": b"unapproved"}, {"valid_until_unix_ms": self.root.valid_from_unix_ms}]:
            with self.assertRaises(tf.TaskFlowError):
                replace(self.root, **updates)
        payload = json.loads(self.sign(self.permit()))
        for value in ["A" * 87, "?" * 88, ZERO_SIGNATURE[:-3] + "B=="]:
            changed = copy.deepcopy(payload); changed["signature"]["value"] = value
            with self.assertRaises(tf.TaskFlowError):
                self.verifier.verify(canonical(changed), now_unix_ms=NOW)

    def test_canonical_proposal_digest_ignores_wire_order_but_binds_arguments(self):
        value = self.proposal(); wire = json.dumps(value, indent=2).encode()
        self.assertEqual(tf.proposal_sha256(wire), tf.proposal_sha256(canonical(value)))
        changed = self.proposal(action_budget_ms=19_999)
        self.assertNotEqual(tf.proposal_sha256(wire), tf.proposal_sha256(canonical(changed)))

    def test_real_openssl_inputs_are_sealed_and_environment_is_sanitized(self):
        payload = self.sign(self.permit()); original = subprocess.run; observed = []
        def inspect(command, **options):
            observed.append(command)
            self.assertEqual(command[0], "/usr/bin/openssl")
            self.assertEqual(options["env"], tf.OPENSSL_ENV)
            self.assertEqual(len(options["pass_fds"]), 3)
            for descriptor in options["pass_fds"]:
                seals = fcntl.fcntl(descriptor, fcntl.F_GET_SEALS)
                self.assertTrue(seals & fcntl.F_SEAL_WRITE)
                with self.assertRaises(OSError):
                    os.pwrite(descriptor, b"substituted", 0)
                with self.assertRaises(OSError):
                    os.ftruncate(descriptor, 0)
            return original(command, **options)
        with patch.object(tf.subprocess, "run", side_effect=inspect), patch.dict(os.environ, {"OPENSSL_CONF": "/untrusted-config", "LD_PRELOAD": "/untrusted-module", "TMPDIR": "/untrusted-temp"}):
            self.assertEqual(self.verifier.verify(payload, now_unix_ms=NOW), payload)
        self.assertEqual(len(observed), 1)

    def test_machine_contract_matches_actual_closed_source_profile(self):
        contract = json.loads((ROOT / "contracts/taskflow-execution.v1.json").read_bytes())
        permit_schema = json.loads((ROOT / "contracts/capability-permit.v1.schema.json").read_bytes())
        self.assertEqual(set(contract["proposal_fields"]), tf.PROPOSAL_FIELDS)
        self.assertEqual(set(contract["permit_resource_fields"]), tf.RESOURCE_FIELDS)
        self.assertEqual(set(contract["native_resource_fields"]), tf.TARGET_FIELDS)
        self.assertEqual(set(permit_schema["required"]), tf.PERMIT_FIELDS)
        self.assertEqual({name: entry["resource_kind"] for name, entry in contract["operations"].items()}, tf.OPERATIONS)
        self.assertEqual(contract["signing"]["permit_domain"].encode(), tf.PERMIT_DOMAIN)
        self.assertEqual(contract["signing"]["proposal_domain"].encode(), tf.PROPOSAL_DOMAIN)
        self.assertEqual(set(contract["states"]), {state.value for state in tf.ActionState})
        for key, constant in {"max_wire_bytes": "MAX_WIRE_BYTES", "max_roots": "MAX_ROOTS", "max_revocations": "MAX_REVOCATIONS", "max_tasks_per_coordinator": "MAX_TASKS", "max_actions_per_task": "MAX_TASK_ACTIONS", "max_task_budget_ms": "MAX_TASK_BUDGET_MS", "max_action_budget_ms": "MAX_ACTION_BUDGET_MS", "max_permit_lifetime_ms": "MAX_PERMIT_LIFETIME_MS", "max_consumptions_per_store": "MAX_HISTORY", "max_task_reservations_per_store": "MAX_TASK_RESERVATIONS"}.items():
            self.assertEqual(contract["budgets"][key], getattr(tf, constant))
        self.assertEqual(contract["default_authority"]["trust_roots"], [])
        self.assertIsNone(contract["default_authority"]["durable_store"])

    def test_unavailable_crypto_has_no_fallback_approval(self):
        payload = self.sign(self.permit()); self.flow.propose("task:1", canonical(self.proposal()))
        with patch.object(tf.subprocess, "run", side_effect=subprocess.TimeoutExpired("/usr/bin/openssl", 2)), self.assertRaises(tf.PermitRefused):
            self.flow.approve("task:1", payload)
        self.assertEqual(self.flow.current("task:1").state, tf.ActionState.PROPOSED)
        with patch.object(tf.os, "memfd_create", side_effect=OSError(errno.ENOSYS, "sealed snapshots unavailable")), self.assertRaises(tf.PermitRefused):
            self.flow.approve("task:1", payload)

    def test_budget_exhausted_during_durable_consumption_never_calls_adapter(self):
        self.ready(); original = os.fsync; advanced = [False]
        def expire_after_file_sync(descriptor):
            result = original(descriptor)
            if not advanced[0]:
                advanced[0] = True; self.clock.tick(20_001)
            return result
        with patch.object(tf.os, "fsync", side_effect=expire_after_file_sync), self.assertRaises(tf.DeadlineExceeded):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called); self.assertEqual(len(list(self.path.glob("*.used"))), 3)
        self.assertEqual(self.flow.current("task:1").state, tf.ActionState.HUMAN_HANDOFF)

    def test_retained_file_name_substitution_before_directory_sync_fails_closed(self):
        self.ready(); original = os.fsync; substituted = [False]
        def replace_consumption(descriptor):
            result = original(descriptor)
            import stat
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode) and not substituted[0]:
                substituted[0] = True
                record = next(self.path.glob("*.used")); data = record.read_bytes()
                record.rename(self.path.parent / "preserved-consumption")
                record.write_bytes(data); os.chmod(record, 0o600)
            return result
        with patch.object(tf.os, "fsync", side_effect=replace_consumption), self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch("task:1", self.binding, self.adapter)
        self.assertFalse(self.called); self.assertTrue((self.path.parent / "preserved-consumption").exists())

    def test_capacity_exhaustion_never_prunes_consumptions_or_dispatches(self):
        self.ready(); self.flow.dispatch("task:1", self.binding, self.adapter)
        task_id = "task:capacity"; proposal = self.proposal(task_id=task_id)
        self.flow.create_task(replace(self.policy, task_id=task_id)); self.flow.propose(task_id, canonical(proposal))
        self.flow.approve(task_id, self.sign(self.permit(proposal, permit_id="permit:capacity", nonce="f" * 64)))
        before = {path.name: path.read_bytes() for path in self.path.glob("*.used")}
        with patch.object(tf, "MAX_HISTORY", 1), self.assertRaises(tf.RecoveryRequired):
            self.flow.dispatch(task_id, self.binding, self.adapter)
        self.assertEqual({path.name: path.read_bytes() for path in self.path.glob("*.used")}, before)
        self.assertEqual(len(self.called), 1)

    def test_cancel_handoff_and_expired_predispatch_task_cannot_restart_budget(self):
        for closure in ("cancel", "handoff", "expired"):
            task_id = "task:restart:" + closure; proposal = self.proposal(task_id=task_id)
            self.flow.create_task(replace(self.policy, task_id=task_id)); self.flow.propose(task_id, canonical(proposal))
            payload = self.sign(self.permit(proposal, permit_id="permit:" + closure, nonce=hashlib.sha256(closure.encode()).hexdigest()))
            self.flow.approve(task_id, payload)
            if closure == "cancel":
                self.flow.cancel(task_id)
            elif closure == "handoff":
                self.flow.handoff_to_human(task_id)
            else:
                self.clock.tick(20_001)
                with self.assertRaises(tf.DeadlineExceeded):
                    self.flow.dispatch(task_id, self.binding, self.adapter)
            self.store.close(); self.store = tf.DurableGrantStore(self.path); self.addCleanup(self.store.close)
            self.flow = self.coordinator(self.store)
            with self.assertRaises(tf.RecoveryRequired):
                self.flow.create_task(replace(self.policy, task_id=task_id))
        self.assertFalse(self.called); self.assertFalse(list(self.path.glob("*.used")))

    def test_task_reservation_is_durable_before_any_proposal_and_never_reusable(self):
        self.assertEqual(len(list(self.path.glob("*.reserved"))), 1)
        self.assertFalse(list(self.path.glob("*.used")))
        self.store.close(); self.store = tf.DurableGrantStore(self.path); self.addCleanup(self.store.close)
        other = self.coordinator(self.store)
        with self.assertRaises(tf.RecoveryRequired):
            other.create_task(self.policy)

    def test_task_reservation_sync_failure_closes_admission_preserving_evidence(self):
        policy = replace(self.policy, task_id="task:reservation-cut")
        with patch.object(tf.os, "fsync", side_effect=OSError(errno.EIO, "controlled reservation sync cut")), self.assertRaises(tf.RecoveryRequired):
            self.flow.create_task(policy)
        with self.assertRaises(tf.TaskFlowError):
            self.flow.current(policy.task_id)
        self.assertTrue((self.path / tf._task_name(policy.task_id)).exists())
        with self.assertRaises(tf.RecoveryRequired):
            self.store.refuses_task_resume("fresh-task")

    def test_real_fork_cannot_reuse_inherited_approval_store_or_revocation_snapshot(self):
        self.ready()
        start_read, start_write = os.pipe(); result_read, result_write = os.pipe()
        process = os.fork()
        if process == 0:
            try:
                os.close(start_write); os.close(result_read); os.read(start_read, 1)
                results = []
                for operation in [lambda: self.flow.dispatch("task:1", self.binding, lambda payload, control: tf.EffectOutcome.SUCCEEDED),
                                  lambda: self.store.refuses_task_resume("task:1"),
                                  lambda: self.verifier.verify(self.sign(self.permit()), now_unix_ms=NOW)]:
                    try:
                        operation(); results.append("allowed")
                    except tf.TaskFlowError:
                        results.append("refused")
                os.write(result_write, ",".join(results).encode())
                os._exit(0)
            except BaseException:
                os._exit(1)
        os.close(start_read); os.close(result_write)
        try:
            self.flow.cancel("task:1"); self.verifier.revoke_key(self.root.key_id); os.write(start_write, b"x")
            ready, _, _ = select.select([result_read], [], [], 3)
            self.assertTrue(ready, "inherited mutex/authority must refuse promptly")
            self.assertEqual(os.read(result_read, 128), b"refused,refused,refused")
        finally:
            os.close(start_write); os.close(result_read)
            observed, status = os.waitpid(process, os.WNOHANG)
            if observed == 0:
                os.kill(process, 9); observed, status = os.waitpid(process, 0)
            self.assertEqual(observed, process)
        self.assertFalse(self.called); self.assertFalse(list(self.path.glob("*.used")))

    def test_concurrent_dispatch_has_one_irreversible_winner(self):
        self.ready(); entered = threading.Event(); release = threading.Event(); results = []
        def adapter(payload, control):
            control.ensure_active(self.binding); entered.set(); self.assertTrue(release.wait(2)); self.called.append(payload)
            return tf.EffectOutcome.SUCCEEDED
        worker = threading.Thread(target=lambda: results.append(self.flow.dispatch("task:1", self.binding, adapter)))
        worker.start(); self.assertTrue(entered.wait(2))
        with self.assertRaises(tf.ReplayRefused):
            self.flow.dispatch("task:1", self.binding, adapter)
        release.set(); worker.join(2); self.assertFalse(worker.is_alive())
        self.assertEqual(len(self.called), 1); self.assertEqual(results[0].state, tf.ActionState.TERMINAL)


if __name__ == "__main__":
    unittest.main()
