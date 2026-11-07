"""Pure receipt binding and owned ordinary-file controls; no device calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import once
import prepare


class CoordinatorControls(unittest.TestCase):
    def binding(self):
        unit, invocation = 'p4-lmkd-relay-owned-test.service', '1' * 32
        status = {'ExecMainPID': '123', 'InvocationID': invocation,
                  'ExecMainStartTimestampMonotonic': '1000', 'ExecMainExitTimestampMonotonic': '2100',
                  'MemoryPeak': str(8 * 1024**2), 'MemorySwapPeak': '0'}
        first = {'invocation_id': invocation, 'cgroup_device': 30, 'cgroup_inode': 40,
                 'observed_monotonic_ns': 1_100_000}
        outer = {'observed_monotonic_ns': 2_000_000, 'memory_peak': 6 * 1024**2}
        q = {'outer_identity_for_external_unit_binding': {
            'unit': unit, 'driver_pid': 123, 'cgroup_device': 30, 'cgroup_inode': 40}}
        return [status, first, outer, q, unit, invocation]

    def test_external_identity_time_and_peaks(self):
        args = self.binding()
        self.assertEqual(once.bind_terminal(*args), args[3]['outer_identity_for_external_unit_binding'])
        changes = [(0, 'ExecMainPID', '124'), (0, 'InvocationID', '2' * 32),
                   (1, 'cgroup_device', 31), (1, 'cgroup_inode', 41), (1, 'invocation_id', '2' * 32),
                   (0, 'MemoryPeak', str(once.HARD)), (0, 'MemorySwapPeak', '1'),
                   (0, 'MemoryPeak', str(5 * 1024**2)), (0, 'ExecMainStartTimestampMonotonic', '2000'),
                   (0, 'ExecMainExitTimestampMonotonic', '1999'), (2, 'observed_monotonic_ns', 999_999),
                   (2, 'memory_peak', 9 * 1024**2)]
        for index, key, value in changes:
            with self.subTest(index=index, key=key):
                args = self.binding(); args[index][key] = value
                with self.assertRaises(RuntimeError): once.bind_terminal(*args)
        args = self.binding(); args[3]['outer_identity_for_external_unit_binding']['unit'] = 'another.service'
        with self.assertRaises(RuntimeError): once.bind_terminal(*args)

    def test_actual_owned_directory_identity_and_counter_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = dict(once.LIMITS, **{'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n',
                                        'memory.current': '32', 'memory.peak': '64', 'memory.swap.current': '0',
                                        'memory.swap.peak': '0', 'cgroup.events': 'populated 1\nfrozen 0\n'})
            for name, value in values.items(): (root / name).write_text(value)
            observed = once.resource_snapshot(root, '1' * 32)
            self.assertEqual((observed['cgroup_device'], observed['cgroup_inode']), (root.stat().st_dev, root.stat().st_ino))
            (root / 'memory.events').write_text(values['memory.events'].replace('max 0', 'max 1'))
            with self.assertRaises(RuntimeError): once.resource_snapshot(root, '1' * 32)

    def test_stale_requires_all_explicit_actual_critical_flags(self):
        q = {'qualification_status': 'pass', 'stale_actual_queue_zero_kill_verified': True,
             'stale_actual_critical_queue_zero_kill_verified': True, 'critical_event_observed_in_phase': True}
        once.require_phase_qualification('stale', 0, q)
        for key in list(q)[1:]:
            for value in (False, 1, None):
                changed = dict(q); changed[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                    once.require_phase_qualification('stale', 0, changed)
            changed = dict(q); del changed[key]
            with self.assertRaises(RuntimeError): once.require_phase_qualification('stale', 0, changed)

    def test_partial_is_only_positive_and_failed_qualifier_never_admitted(self):
        once.require_phase_qualification('pressure', 0, {'qualification_status': 'pass'})
        once.require_phase_qualification('pressure', 2, {'qualification_status': 'partial_medium_only'})
        for phase, code, status in [('stale', 2, 'partial_medium_only'), ('stale', 1, 'pass'),
                                    ('pressure', 0, 'partial_medium_only'), ('pressure', 2, 'pass'),
                                    ('pressure', 1, 'pass'), ('invalid', 0, 'pass')]:
            with self.subTest(phase=phase, code=code, status=status), self.assertRaises(RuntimeError):
                once.require_phase_qualification(phase, code, {'qualification_status': status})

    def test_predecessor_is_externally_pinned_and_new_source_bound(self):
        for module in (prepare, once):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'result.json'
                fixed = '/home/alex/work/pocket4-lmkd-pressure-r11-coordinator-04/02-pressure-once/result.json'
                original = {'phase': 'pressure', 'source_manifest_sha256': module.SOURCE,
                            'matching_build_receipt_sha256': module.BUILD, 'ok': True,
                            'external_unit_binding_verified': True, 'exact_owned_cleanup_verified': True,
                            'main_epoch_unchanged_after_cleanup': True, 'outcome_unknown': False,
                            'forced_teardown': False, 'pressure_qualified': True, 'partial_medium_only': False}
                def put(value):
                    raw = (json.dumps(value) + '\n').encode(); path.write_bytes(raw)
                    return hashlib.sha256(raw).hexdigest()
                with patch.object(module, 'P', lambda p: path if str(p) == fixed else Path(p)):
                    good_pin = put(original)
                    self.assertEqual(module.predecessor(good_pin)['sha256'], good_pin)
                    with self.assertRaises(RuntimeError): module.predecessor('0' * 64)
                    for key, value in [('phase', 'stale'), ('source_manifest_sha256', 'a' * 64),
                                       ('matching_build_receipt_sha256', 'b' * 64), ('ok', False),
                                       ('external_unit_binding_verified', False), ('exact_owned_cleanup_verified', False),
                                       ('main_epoch_unchanged_after_cleanup', False), ('outcome_unknown', True),
                                       ('forced_teardown', True), ('pressure_qualified', False)]:
                        changed = copy.deepcopy(original); changed[key] = value
                        with self.subTest(key=key), self.assertRaises(RuntimeError): module.predecessor(put(changed))


if __name__ == '__main__': unittest.main()
