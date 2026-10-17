"""Pure specification checks for the Organ control broker boundary.

These tests do not call a broker, Agentd, HOS2, or a device.  They freeze the
identity, replay, and state rules that a future implementation must satisfy.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from enum import Enum


class BrokerError(ValueError):
    """A proposal violates the pointer-free UI contract."""


class State(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    CANCEL_REQUESTED = "cancel_requested"
    TERMINAL_SUCCESS = "terminal_success"
    TERMINAL_FAILURE = "terminal_failure"
    INDETERMINATE = "indeterminate"
    RETIRED = "retired"


@dataclass(frozen=True)
class Intent:
    scope_id: str
    operation_id: str
    payload_digest: str
    expected_resource_revision: int
    body_generation: int
    authority_epoch: int
    client_request_id: str
    payload: dict

    @property
    def k(self) -> tuple[str, str]:
        # Hepta's durable primary key is scope_id + operation_id.  The
        # payload digest is a separate semantic/final-use binding.
        return (self.scope_id, self.operation_id)


@dataclass(frozen=True)
class Delivery:
    boot_id: str
    cap_space_id: str
    sequence: int

    @property
    def d(self) -> tuple[str, str, int]:
        return (self.boot_id, self.cap_space_id, self.sequence)


def validate_intent(intent: Intent) -> None:
    required = {
        "scope_id": intent.scope_id,
        "operation_id": intent.operation_id,
        "payload_digest": intent.payload_digest,
        "client_request_id": intent.client_request_id,
    }
    if any(not value for value in required.values()):
        raise BrokerError("identity fields must be non-empty")
    if intent.expected_resource_revision <= 0:
        raise BrokerError("resource revision must be positive")
    if intent.body_generation <= 0 or intent.authority_epoch <= 0:
        raise BrokerError("generation and authority epoch must be positive")
    forbidden = {
        "request_addr",
        "response_addr",
        "cap_space_id",
        "boot_id",
        "control_fd",
        "final_use",
        "signature",
    }
    if forbidden.intersection(intent.payload):
        raise BrokerError("UI payload must not contain local pointers or authority")


def record_intent(table: dict, intent: Intent) -> str:
    validate_intent(intent)
    previous = table.get(intent.k)
    if previous is None:
        table[intent.k] = intent
        return "accepted"
    if previous == intent:
        return "idempotent_replay"
    raise BrokerError("same K with different semantics must be rejected")


def can_publish_terminal_success(state: State, owner_confirmed: bool) -> bool:
    return state in {State.SUBMITTED, State.PARTIAL, State.CANCEL_REQUESTED} and owner_confirmed


class OrganControlBrokerContractTests(unittest.TestCase):
    def make_intent(self, **overrides) -> Intent:
        fields = dict(
            scope_id="scope-1",
            operation_id="op-1",
            payload_digest="sha256:abc",
            expected_resource_revision=3,
            body_generation=7,
            authority_epoch=11,
            client_request_id="nonce-1",
            payload={"kind": "observe"},
        )
        fields.update(overrides)
        return Intent(**fields)

    def test_k_and_d_are_different_namespaces(self) -> None:
        intent = self.make_intent()
        delivery = Delivery("boot-1", "cap-1", 1)
        self.assertNotEqual(intent.k, delivery.d)

    def test_same_k_and_digest_is_idempotent(self) -> None:
        table = {}
        intent = self.make_intent()
        self.assertEqual(record_intent(table, intent), "accepted")
        self.assertEqual(record_intent(table, intent), "idempotent_replay")

    def test_same_k_with_changed_digest_is_rejected(self) -> None:
        table = {}
        record_intent(table, self.make_intent())
        with self.assertRaises(BrokerError):
            record_intent(table, self.make_intent(payload_digest="sha256:changed"))

    def test_ui_cannot_submit_pointer_or_authority_fields(self) -> None:
        with self.assertRaises(BrokerError):
            record_intent(self._new_table(), self.make_intent(payload={"request_addr": 1}))
        with self.assertRaises(BrokerError):
            record_intent(self._new_table(), self.make_intent(payload={"final_use": True}))

    def test_generations_and_revision_are_positive(self) -> None:
        for field in ("expected_resource_revision", "body_generation", "authority_epoch"):
            with self.subTest(field=field), self.assertRaises(BrokerError):
                record_intent(self._new_table(), self.make_intent(**{field: 0}))

    def test_terminal_success_requires_original_owner_confirmation(self) -> None:
        for state in (State.SUBMITTED, State.PARTIAL, State.CANCEL_REQUESTED):
            self.assertFalse(can_publish_terminal_success(state, False))
            self.assertTrue(can_publish_terminal_success(state, True))

    def test_draft_never_becomes_terminal_success_directly(self) -> None:
        self.assertFalse(can_publish_terminal_success(State.DRAFT, True))

    def test_unknown_and_indeterminate_are_not_success(self) -> None:
        for state in (State.UNKNOWN, State.INDETERMINATE, State.RETIRED):
            self.assertFalse(can_publish_terminal_success(state, True))

    def test_delivery_sequence_must_be_positive(self) -> None:
        delivery = Delivery("boot-1", "cap-1", 1)
        self.assertGreater(delivery.sequence, 0)
        self.assertEqual(delivery.d[0:2], ("boot-1", "cap-1"))

    def test_client_nonce_is_not_k(self) -> None:
        first = self.make_intent(client_request_id="nonce-a")
        second = self.make_intent(client_request_id="nonce-b")
        self.assertEqual(first.k, second.k)
        self.assertNotEqual(first.client_request_id, second.client_request_id)

    @staticmethod
    def _new_table() -> dict:
        return {}


if __name__ == "__main__":
    unittest.main()
