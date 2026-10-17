"""Pure specification checks for the Organ control broker boundary.

These tests do not call a broker, Agentd, HOS2, or a device.  They freeze the
identity, replay, and state rules that a future implementation must satisfy.
"""

from __future__ import annotations

import copy
import math
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
    # This is a specification fixture, not a running broker. All wire inputs
    # must be scalar, bounded, and structurally JSON-safe before admission.
    allowed_id = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:")
    for value in (intent.scope_id, intent.operation_id, intent.client_request_id):
        if (not isinstance(value, str) or not 1 <= len(value) <= 128
                or any(char not in allowed_id for char in value)):
            raise BrokerError("invalid bounded stable ID/client nonce")
    digest = intent.payload_digest
    if (not isinstance(digest, str) or not digest.startswith("sha256:")
            or len(digest) != 71
            or any(char not in "0123456789abcdef" for char in digest[7:])):
        raise BrokerError("a full immutable SHA256 digest is required")
    for value in (intent.expected_resource_revision, intent.body_generation,
                  intent.authority_epoch):
        if type(value) is not int or not 0 < value < 2**64:
            raise BrokerError("revision and generations must be positive u64")
    if not isinstance(intent.payload, dict):
        raise BrokerError("UI payload must be a bounded object")

    forbidden = {
        "requestaddr", "responseaddr", "capspaceid", "bootid",
        "controlfd", "devicefd", "finaluse", "signature", "agentduds",
        "rawioctl",
    }
    stack = [(intent.payload, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > 256 or depth > 8:
            raise BrokerError("UI payload exceeds bounded structure")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > 128:
                    raise BrokerError("UI keys must be bounded strings")
                normalized = key.replace("_", "").replace("-", "").lower()
                if normalized in forbidden:
                    raise BrokerError("nested UI pointer or authority field")
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif value is None or type(value) in (bool, int, str, float):
            if type(value) is float and not math.isfinite(value):
                raise BrokerError("non-finite UI scalar")
            if type(value) is int and not -(2**63) <= value < 2**63:
                raise BrokerError("UI integer outside bounded wire range")
            if isinstance(value, str) and len(value.encode("utf-8")) > 4096:
                raise BrokerError("unbounded UI string")
        else:
            raise BrokerError("not a JSON scalar or container")


def record_intent(table: dict, intent: Intent) -> str:
    validate_intent(intent)
    previous = table.get(intent.k)
    if previous is None:
        # Freeze the ingress payload: a mutable caller dict must not mutate a
        # prior operation while the original Hepta owner records intent.
        table[intent.k] = copy.deepcopy(intent)
        return "accepted"
    # The client retry nonce is NOT part of durable K. Verify every semantic
    # field, including revision and owner generations, before reusing receipt.
    def semantic_fields(value: Intent) -> tuple:
        return (value.payload_digest, value.expected_resource_revision,
                value.body_generation, value.authority_epoch, value.payload)
    if semantic_fields(previous) == semantic_fields(intent):
        return "idempotent_replay"
    raise BrokerError("same K with different semantics must be rejected")


def can_publish_terminal_success(state: State, owner_confirmed: bool) -> bool:
    return state in {State.SUBMITTED, State.PARTIAL, State.CANCEL_REQUESTED} and owner_confirmed


class OrganControlBrokerContractTests(unittest.TestCase):
    def make_intent(self, **overrides) -> Intent:
        fields = dict(
            scope_id="scope-1",
            operation_id="op-1",
            payload_digest="sha256:" + "a" * 64,
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
            record_intent(table, self.make_intent(payload_digest="sha256:" + "b" * 64))

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

    def test_changed_retry_nonce_same_semantics_is_idempotent(self) -> None:
        table = {}
        first = self.make_intent(client_request_id="nonce-a")
        retry = self.make_intent(client_request_id="nonce-b")
        self.assertEqual(record_intent(table, first), "accepted")
        self.assertEqual(record_intent(table, retry), "idempotent_replay")
        self.assertEqual(table[first.k].client_request_id, "nonce-a")

    def test_same_k_and_digest_changed_authority_or_payload_is_not_replay(self) -> None:
        table = {}
        record_intent(table, self.make_intent())
        for change in (dict(authority_epoch=12),
                       dict(expected_resource_revision=4),
                       dict(payload={"kind": "stop"})):
            with self.subTest(change=change), self.assertRaises(BrokerError):
                record_intent(table, self.make_intent(**change))

    def test_nested_or_variant_pointer_and_authority_fields_are_rejected(self) -> None:
        for payload in ({"wrapper": {"request_addr": 1}},
                        {"items": [{"capSpaceId": "forged"}]},
                        {"inner": {"final-use": True}},
                        {"device_fd": 4}):
            with self.subTest(payload=payload), self.assertRaises(BrokerError):
                validate_intent(self.make_intent(payload=payload))

    def test_unbounded_or_non_json_payloads_and_integer_generations_fail(self) -> None:
        for payload in ({"items": [[[[[[[[[0]]]]]]]]]},
                        {"raw": object()}, {"value": float("nan")},
                        {"items": [0] * 257}):
            with self.subTest(payload_type=str(type(payload))), self.assertRaises(BrokerError):
                validate_intent(self.make_intent(payload=payload))
        for change in (dict(authority_epoch=True), dict(body_generation=-1),
                       dict(expected_resource_revision=2**64),
                       dict(payload_digest="sha256:abc")):
            with self.subTest(change=change), self.assertRaises(BrokerError):
                validate_intent(self.make_intent(**change))

    def test_mutating_caller_payload_cannot_rewrite_original_operation(self) -> None:
        payload = {"kind": "proposal", "nested": {"cap": 10}}
        table = {}
        intent = self.make_intent(payload=payload)
        self.assertEqual(record_intent(table, intent), "accepted")
        payload["nested"]["cap"] = 900
        self.assertEqual(table[intent.k].payload["nested"]["cap"], 10)
        self.assertEqual(
            record_intent(table, self.make_intent(payload={"kind": "proposal", "nested": {"cap": 10}},
                                                  client_request_id="retry")),
            "idempotent_replay",
        )

    @staticmethod
    def _new_table() -> dict:
        return {}


if __name__ == "__main__":
    unittest.main()
