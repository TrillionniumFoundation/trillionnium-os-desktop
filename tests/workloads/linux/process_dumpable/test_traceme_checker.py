"""Synthetic transcript wrappers test the oracle, never qualify a guest."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import traceme_checker as checker

HERE = Path(__file__).resolve().parent
MUTATIONS = []


def wrapped(values):
    return '\n'.join(json.dumps(v, separators=(',', ':')) for v in values) + '\nDUMPABLE_LIFECYCLE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'


class CheckerTests(unittest.TestCase):
    def test_reference_shape_only(self):
        values = [json.loads(v) for v in (HERE / 'traceme-linux-reference-01.jsonl').read_text().splitlines()]
        result = checker.check(wrapped(values), 33, False)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['observations'], 15)
        self.assertFalse(result['production_isolation_qualified'])

    def test_mutations(self):
        original = [json.loads(v) for v in (HERE / 'traceme-linux-reference-01.jsonl').read_text().splitlines()]
        def changed(index, key, value):
            result = deepcopy(original); result[index][key] = value; return wrapped(result)
        missing = deepcopy(original); del missing[3]
        duplicate = deepcopy(original); duplicate.insert(3, duplicate[3])
        reorder = deepcopy(original); reorder[3], reorder[7] = reorder[7], reorder[3]
        cases = [
            ('missing', wrapped(missing), 33, False),
            ('duplicate', wrapped(duplicate), 33, False),
            ('reordered', wrapped(reorder), 33, False),
            ('fake_reap', changed(14, 'all_children_reaped', False), 33, False),
            ('fake_reap_case', changed(13, 'passed', False), 33, False),
            ('marker_only', 'DUMPABLE_LIFECYCLE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n', 33, False),
            ('raw_exit', wrapped(original), 0, False),
            ('timeout', wrapped(original), 33, True),
            ('lost_boot', wrapped(original).replace('TRILLIONNIUM_A01_BOOT_OK\n', ''), 33, False),
            ('duplicate_boot', wrapped(original) + 'TRILLIONNIUM_A01_BOOT_OK\n', 33, False),
            ('wrong_exit', wrapped(original).replace('EXIT=0', 'EXIT=42'), 33, False),
            ('bad_uid', changed(0, 'observer_uid', 0), 33, False),
            ('bad_caps', changed(0, 'cap_eff', 1), 33, False),
            ('bad_nnp', changed(0, 'nnp', 0), 33, False),
            ('fake_stop', changed(1, 'owned_child_stopped', False), 33, False),
            ('fake_traceme', changed(1, 'traceme_rc', -1), 33, False),
            ('unknown_denial', changed(3, 'errno', 38), 33, False),
            ('leaked_dump0', changed(3, 'rc', checker.PUBLIC_SENTINEL), 33, False),
            ('bad_public_value', changed(7, 'rc', 0), 33, False),
            ('failed_continue', changed(4, 'rc', -1), 33, False),
            ('numeric_pass', changed(2, 'passed', 1), 33, False),
        ]
        for name, raw, code, timeout in cases:
            with self.subTest(mutation=name):
                self.assertFalse(checker.check(raw, code, timeout)['passed'])
                MUTATIONS.append(name)

    def test_actual_old_guest_timeout_rejected(self):
        raw = (HERE / 'traceme-native-0252-negative-01/serial.log').read_bytes()
        for name, code, timeout in [('actual_timeout', None, True),
                                    ('timeout_not_marked', None, False),
                                    ('falsely_successful_exit', 33, False)]:
            with self.subTest(mutation=name):
                self.assertFalse(checker.check(raw, code, timeout)['passed'])
                MUTATIONS.append(name)


if __name__ == '__main__':
    program = unittest.main(exit=False, verbosity=2)
    print(json.dumps({'host_checker_tests': True, 'mutations_rejected': len(MUTATIONS),
                      'mutation_names': MUTATIONS, 'passed': program.result.wasSuccessful(),
                      'synthetic_shapes_are_not_guest_qualification': True}))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
