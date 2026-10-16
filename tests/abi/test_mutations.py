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

from test_golden_contract import read_frame


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
    """One CapSpace's canonical retry oracle, not an ordering/state model."""

    def __init__(self) -> None:
        self.records: dict[int, InstallBudget] = {}

    def reserve(self, request: InstallBudget) -> str:
        # The CapSpace supplies the namespace: a target is request content,
        # never an additional namespace permitting reuse of the same D.
        key = request.sequence
        previous = self.records.get(key)
        if previous is None:
            self.records[key] = request
            return "new"
        return "duplicate" if previous == request else "conflict"


class IgnoringCapLedger(ReservationLedger):
    def reserve(self, request: InstallBudget) -> str:
        key = request.sequence
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
        key = request.sequence
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


class PerTargetNamespaceLedger(ReservationLedger):
    """Known-bad mutant: incorrectly allocates a sequence once per target."""

    def __init__(self) -> None:
        self.per_target_records: dict[tuple[int, tuple[int, int]], InstallBudget] = {}

    def reserve(self, request: InstallBudget) -> str:
        key = (request.sequence, request.target)
        previous = self.per_target_records.get(key)
        if previous is None:
            self.per_target_records[key] = request
            return "new"
        return "duplicate" if previous == request else "conflict"


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
    if read_frame(frame, "request")[0] != 3:
        raise ValueError("not an InstallBudget frame")
    sequence = struct.unpack_from("<Q", frame, 24)[0]
    slot, generation = struct.unpack_from("<QQ", frame, 40)
    expected, period, cap, _ = struct.unpack_from("<4Q", frame, 64)
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
    if ledger.reserve(original) != "duplicate":
        raise AssertionError("conflict changed the original canonical reservation")


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

    def test_identical_retry_preserves_original_reservation(self) -> None:
        ledger = ReservationLedger()
        self.assertEqual(ledger.reserve(self.original), "new")
        self.assertEqual(ledger.reserve(self.original), "duplicate")
        self.assertEqual(ledger.records, {self.original.sequence: self.original})

    def test_same_sequence_different_target_conflicts_in_one_capspace(self) -> None:
        for field in ("target_slot", "target_generation"):
            with self.subTest(field=field):
                changed = replace(self.original, **{field: getattr(self.original, field) + 1})
                _assert_reuse_rejected(ReservationLedger(), self.original, changed)

    def test_mutant_with_per_target_sequence_namespace_is_caught(self) -> None:
        changed = replace(self.original, target_slot=self.original.target_slot + 1)
        with self.assertRaisesRegex(AssertionError, "incorrectly reused"):
            _assert_reuse_rejected(PerTargetNamespaceLedger(), self.original, changed)

    def test_mutant_ignoring_cap_is_caught(self) -> None:
        mutated = _decode_install_budget(_mutate(self.frame, cap_ns=self.original.cap_ns + 1))
        known_bad = IgnoringCapLedger()
        self.assertEqual(known_bad.reserve(self.original), "new")
        self.assertEqual(known_bad.reserve(mutated), "duplicate")
        with self.assertRaisesRegex(AssertionError, "mutated request was incorrectly reused"):
            _assert_reuse_rejected(IgnoringCapLedger(), self.original, mutated)

    def test_mutant_ignoring_revision_is_caught(self) -> None:
        mutated = _decode_install_budget(
            _mutate(self.frame, expected_revision=self.original.expected_revision + 1)
        )
        known_bad = IgnoringRevisionLedger()
        self.assertEqual(known_bad.reserve(self.original), "new")
        self.assertEqual(known_bad.reserve(mutated), "duplicate")
        with self.assertRaisesRegex(AssertionError, "mutated request was incorrectly reused"):
            _assert_reuse_rejected(IgnoringRevisionLedger(), self.original, mutated)

    def test_mutant_ignoring_revision_cas_is_caught(self) -> None:
        state = IgnoringRevisionState(revision=self.original.expected_revision)
        stale = replace(self.original, sequence=self.original.sequence + 1,
                        cap_ns=self.original.cap_ns + 1)
        with self.assertRaisesRegex(AssertionError, "stale revision was incorrectly accepted"):
            _assert_cas_rejected(state, self.original, stale)


if __name__ == "__main__":
    unittest.main(verbosity=2)
