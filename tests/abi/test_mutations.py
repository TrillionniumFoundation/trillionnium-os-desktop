"""Adversarial InstallBudget identity/CAS tests.

The ledger and state classes are deliberately tiny reference models.  The
Ignoring* implementations are known-bad mutants; each must fail the same
oracle as the correct implementation so a test suite that ignores cap or
expected_revision cannot silently pass.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct
import unittest


_GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "hos2.json"
_PERIOD_NS = 100_000_000


@dataclass(frozen=True)
class InstallBudget:
    sequence: int
    target_slot: int
    target_generation: int
    expected_revision: int
    period_ns: int
    cap_ns: int

    @property
    def target(self) -> tuple[int, int]:
        return (self.target_slot, self.target_generation)


class ReservationLedger:
    def __init__(self) -> None:
        self.records: dict[tuple[int, tuple[int, int]], InstallBudget] = {}

    def reserve(self, request: InstallBudget) -> str:
        key = (request.sequence, request.target)
        previous = self.records.get(key)
        if previous is None:
            self.records[key] = request
            return "new"
        return "duplicate" if previous == request else "conflict"


class IgnoringCapLedger(ReservationLedger):
    def reserve(self, request: InstallBudget) -> str:
        key = (request.sequence, request.target)
        previous = self.records.get(key)
        if previous is None:
            self.records[key] = request
            return "new"
        return "duplicate" if (
            previous.sequence == request.sequence
            and previous.target == request.target
            and previous.expected_revision == request.expected_revision
            and previous.period_ns == request.period_ns
        ) else "conflict"


class IgnoringRevisionLedger(ReservationLedger):
    def reserve(self, request: InstallBudget) -> str:
        key = (request.sequence, request.target)
        previous = self.records.get(key)
        if previous is None:
            self.records[key] = request
            return "new"
        return "duplicate" if (
            previous.sequence == request.sequence
            and previous.target == request.target
            and previous.period_ns == request.period_ns
            and previous.cap_ns == request.cap_ns
        ) else "conflict"


@dataclass
class BudgetState:
    revision: int
    period_ns: int = _PERIOD_NS
    cap_ns: int = 0

    def apply(self, request: InstallBudget) -> str:
        if request.expected_revision != self.revision:
            return "conflict"
        if request.period_ns != self.period_ns or not 0 <= request.cap_ns <= request.period_ns:
            return "invalid_input"
        self.cap_ns = request.cap_ns
        self.revision += 1
        return "ok"


class IgnoringRevisionState(BudgetState):
    def apply(self, request: InstallBudget) -> str:
        if request.period_ns != self.period_ns or not 0 <= request.cap_ns <= request.period_ns:
            return "invalid_input"
        self.cap_ns = request.cap_ns
        self.revision += 1
        return "ok"


def _golden_install_budget() -> bytes:
    document = json.loads(_GOLDEN.read_text())
    vector = next(v for v in document["vectors"] if v["name"] == "install_budget")
    return bytes.fromhex(vector["hex"])


def _decode_install_budget(frame: bytes) -> InstallBudget:
    if len(frame) != 96 or frame[:4] != b"HOS2":
        raise ValueError("not an InstallBudget frame")
    sequence = struct.unpack_from("<Q", frame, 24)[0]
    if frame[32:40] != bytes(8):
        raise ValueError("non-zero InstallBudget request_id high half")
    slot, generation = struct.unpack_from("<QQ", frame, 40)
    expected, period, cap, reserved = struct.unpack_from("<4Q", frame, 64)
    if reserved:
        raise ValueError("reserved InstallBudget field")
    return InstallBudget(sequence, slot, generation, expected, period, cap)


def _mutate(frame: bytes, *, expected_revision: int | None = None,
            cap_ns: int | None = None) -> bytes:
    mutated = bytearray(frame)
    if expected_revision is not None:
        struct.pack_into("<Q", mutated, 64, expected_revision)
    if cap_ns is not None:
        struct.pack_into("<Q", mutated, 80, cap_ns)
    return bytes(mutated)


def _assert_reuse_rejected(ledger: ReservationLedger,
                           original: InstallBudget,
                           mutated: InstallBudget) -> None:
    if ledger.reserve(original) != "new":
        raise AssertionError("first reservation must be new")
    if ledger.reserve(mutated) != "conflict":
        raise AssertionError("mutated request was incorrectly reused")


def _assert_cas_rejected(state: BudgetState, first: InstallBudget,
                         stale: InstallBudget) -> None:
    if state.apply(first) != "ok":
        raise AssertionError("initial request must apply")
    if state.apply(stale) != "conflict":
        raise AssertionError("stale revision was incorrectly accepted")


class InstallBudgetMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = _golden_install_budget()
        cls.original = _decode_install_budget(cls.frame)

    def test_cap_mutation_same_sequence_and_target_conflicts(self) -> None:
        mutated = _decode_install_budget(_mutate(self.frame, cap_ns=self.original.cap_ns + 1))
        self.assertEqual(mutated.sequence, self.original.sequence)
        self.assertEqual(mutated.target, self.original.target)
        _assert_reuse_rejected(ReservationLedger(), self.original, mutated)

    def test_expected_revision_mutation_same_sequence_and_target_conflicts(self) -> None:
        mutated = _decode_install_budget(
            _mutate(self.frame, expected_revision=self.original.expected_revision + 1)
        )
        self.assertEqual(mutated.sequence, self.original.sequence)
        self.assertEqual(mutated.target, self.original.target)
        _assert_reuse_rejected(ReservationLedger(), self.original, mutated)

    def test_expected_revision_is_live_cas(self) -> None:
        state = BudgetState(revision=self.original.expected_revision)
        stale = replace(self.original, sequence=self.original.sequence + 1,
                        cap_ns=self.original.cap_ns + 1)
        _assert_cas_rejected(state, self.original, stale)
        self.assertEqual(state.revision, self.original.expected_revision + 1)

    def test_mutant_ignoring_cap_is_caught(self) -> None:
        mutated = _decode_install_budget(_mutate(self.frame, cap_ns=self.original.cap_ns + 1))
        with self.assertRaises(AssertionError):
            _assert_reuse_rejected(IgnoringCapLedger(), self.original, mutated)

    def test_mutant_ignoring_revision_is_caught(self) -> None:
        mutated = _decode_install_budget(
            _mutate(self.frame, expected_revision=self.original.expected_revision + 1)
        )
        with self.assertRaises(AssertionError):
            _assert_reuse_rejected(IgnoringRevisionLedger(), self.original, mutated)

    def test_mutant_ignoring_revision_cas_is_caught(self) -> None:
        state = IgnoringRevisionState(revision=self.original.expected_revision)
        stale = replace(self.original, sequence=self.original.sequence + 1,
                        cap_ns=self.original.cap_ns + 1)
        with self.assertRaises(AssertionError):
            _assert_cas_rejected(state, self.original, stale)


if __name__ == "__main__":
    unittest.main(verbosity=2)
