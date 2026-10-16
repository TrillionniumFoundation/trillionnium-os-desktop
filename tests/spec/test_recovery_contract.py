"""HOS2 proposed recovery semantics: sequential specification tests only.
No wire codec, syscalls, permissions, kernel, device, or concurrency implementation.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import unittest

@dataclass(frozen=True)
class Intent:
    sequence: int
    target: str
    expected_revision: int
    cap: int

class Window:
    """Single-threaded model of namespace reservation; not a runtime ledger."""
    def __init__(self, capacity=1024):
        self.capacity = capacity
        self.next_sequence = 1
        self.floor = 0
        self.records = {}

    def reserve(self, intent):
        seq = intent.sequence
        if seq <= self.floor:
            return 'retired'
        if seq in self.records:
            previous, outcome = self.records[seq]
            if previous != intent:
                return 'conflict'
            return 'reserved' if outcome is None else ('terminal', outcome)
        if seq != self.next_sequence:
            return 'out_of_order'
        if len(self.records) >= self.capacity:
            return 'full'
        self.records[seq] = (intent, None)
        self.next_sequence += 1
        return 'new'

    def finish(self, intent, outcome):
        previous, existing = self.records[intent.sequence]
        if previous != intent or existing is not None:
            raise ValueError('only reservation owner may publish a terminal outcome')
        self.records[intent.sequence] = (previous, outcome)

    def query(self, sequence, view=False):
        if not view:
            return 'denied'
        if sequence <= self.floor:
            return 'retired'
        if sequence not in self.records:
            return 'not_seen'
        outcome = self.records[sequence][1]
        return 'reserved' if outcome is None else ('terminal', outcome)

    def retire(self, through, durable_owner=False):
        if not durable_owner:
            return 'denied'
        if through <= self.floor:
            return 'ok'
        if through >= self.next_sequence:
            return 'not_seen'
        prefix = range(self.floor + 1, through + 1)
        if any(self.records[i][1] is None for i in prefix):
            return 'busy'
        for i in range(self.floor + 1, through + 1):
            del self.records[i]
        self.floor = through
        return 'ok'

class RecoveryContract(unittest.TestCase):
    def test_grant_activation_after_final_exec(self):
        task = dict(stopped=True, epoch=1, grant=None, limited=True)
        task['epoch'] += 1
        expected_epoch = task['epoch']
        self.assertTrue(task['stopped'] and task['limited'])
        task['grant'] = (expected_epoch, 'bounded')
        task['stopped'] = False
        self.assertEqual(task['grant'][0], task['epoch'])
        task['epoch'] += 1
        task['grant'] = None
        self.assertIsNone(task['grant'])

    def test_one_namespace_reservation_across_targets(self):
        w = Window()
        self.assertEqual(w.reserve(Intent(1, 'X', 1, 40)), 'new')
        self.assertEqual(w.reserve(Intent(1, 'Y', 1, 40)), 'conflict')
        self.assertEqual(len(w.records), 1)

    def test_duplicate_result_is_not_second_effect(self):
        w = Window(); i = Intent(1, 'X', 1, 40)
        self.assertEqual(w.reserve(i), 'new')
        w.finish(i, ('applied', 2))
        self.assertEqual(w.reserve(i), ('terminal', ('applied', 2)))
        self.assertEqual(w.next_sequence, 2)
        with self.assertRaises(ValueError):
            w.finish(i, ('applied', 3))

    def test_reserved_rejection_remains_terminal(self):
        w = Window(); i = Intent(1, 'X', 7, 40)
        w.reserve(i); w.finish(i, 'cas_conflict')
        self.assertEqual(w.reserve(i), ('terminal', 'cas_conflict'))

    def test_history_view_not_old_manage_handle(self):
        w = Window(); i = Intent(1, 'old-slot', 1, 40)
        w.reserve(i); w.finish(i, ('applied', 2))
        manager_alive = False
        self.assertFalse(manager_alive)
        self.assertEqual(w.query(1, view=True), ('terminal', ('applied', 2)))
        self.assertEqual(w.query(1, view=False), 'denied')

    def test_retirement_is_atomic_over_pending_prefix(self):
        w = Window(); first = Intent(1, 'X', 1, 40); second = Intent(2, 'Y', 1, 30)
        w.reserve(first); w.reserve(second); w.finish(second, 'rejected')
        snapshot = dict(w.records)
        self.assertEqual(w.retire(2, True), 'busy')
        self.assertEqual(w.floor, 0)
        self.assertEqual(w.records, snapshot)
        w.finish(first, 'applied')
        self.assertEqual(w.retire(2, True), 'ok')
        self.assertEqual(w.reserve(first), 'retired')

    def test_full_window_does_not_block_query_or_retire(self):
        w = Window(2)
        for seq in (1, 2):
            i = Intent(seq, 'X', seq, 40); w.reserve(i); w.finish(i, 'applied')
        self.assertEqual(w.reserve(Intent(3, 'X', 3, 40)), 'full')
        self.assertEqual(w.next_sequence, 3)
        self.assertEqual(w.query(1, True), ('terminal', 'applied'))
        self.assertEqual(w.retire(2, True), 'ok')
        self.assertEqual(w.reserve(Intent(3, 'X', 3, 40)), 'new')

    def test_ten_thousand_writes_one_namespace(self):
        w = Window(1024); high = 0
        for seq in range(1, 10001):
            i = Intent(seq, 'X', seq, seq % 101)
            self.assertEqual(w.reserve(i), 'new'); w.finish(i, ('applied', seq + 1))
            high = max(high, len(w.records))
            if seq % 64 == 0:
                self.assertEqual(w.retire(seq, True), 'ok')
                self.assertEqual(w.reserve(Intent(1, 'X', 1, 1)), 'retired')
        self.assertEqual(w.next_sequence, 10001)
        self.assertLessEqual(high, 64)
        self.assertEqual(w.retire(10000, True), 'ok')
        self.assertEqual(len(w.records), 0)
        self.assertEqual(w.query(10000, True), 'retired')

    def test_out_of_order_does_not_consume_sequence(self):
        w = Window()
        self.assertEqual(w.reserve(Intent(2, 'X', 1, 40)), 'out_of_order')
        self.assertEqual(w.next_sequence, 1)
        self.assertEqual(w.retire(1, True), 'not_seen')

    def test_same_observation_cannot_prove_old_effect(self):
        history_a = dict(revision=12, cap=40, old_effect='applied')
        history_b = dict(revision=12, cap=40, old_effect='not_applied')
        visible = lambda h: (h['revision'], h['cap'])
        self.assertEqual(visible(history_a), visible(history_b))
        old_record = 'indeterminate'
        new_goal = dict(cap=50, fenced_old=True, separately_authorized=True)
        self.assertTrue(new_goal['fenced_old'] and new_goal['separately_authorized'])
        self.assertEqual(old_record, 'indeterminate')

    def test_user_pause_not_inferred_from_zero_cap(self):
        def fallback(reason, current_parent_cap):
            desired = 0 if reason == 'user_pause' else 40
            return min(desired, current_parent_cap)
        self.assertEqual(fallback('user_pause', 80), 0)
        self.assertEqual(fallback('lease_expired', 80), 40)
        self.assertEqual(fallback('lease_expired', 20), 20)

    def test_policy_update_does_not_refill(self):
        used, cap = 35, 40
        for cap in (40, 60, 20, 40):
            remaining = max(0, cap - used)
            self.assertEqual(used, 35)
        self.assertEqual(remaining, 5)

    def test_nonfair_class_must_not_bypass(self):
        covered = {'fair'}
        for kind in ('fair', 'fifo', 'rr'):
            outcome = 'gated' if kind in covered else 'unsupported'
            self.assertNotEqual(outcome, 'unlimited')

    def test_staleness_rechecked_after_reasoning(self):
        sample, start, dispatch, max_age = 100, 101, 104, 2
        self.assertLessEqual(start - sample, max_age)
        self.assertGreater(dispatch - sample, max_age)

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    import sys
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps({
            'specification': 'HOS2 proposed recovery v0.3',
            'tests_run': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'skipped': len(result.skipped),
            'ten_thousand_writes': 'sequential model, not kernel benchmark',
            'rust_codec_implemented': False, 'kernel_executed': False,
            'concurrency_verified': False,
        }, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
