"""Host-only oracle mutation tests. Synthetic wrappers are not guest receipts."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import lifecycle_checker as checker

HERE = Path(__file__).resolve().parent
MUTATIONS = []


def records(name):
    return [json.loads(line) for line in (HERE / name).read_text().splitlines()]


def wrapped(values):
    return '\n'.join(json.dumps(v, separators=(',', ':')) for v in values) + '\nDUMPABLE_LIFECYCLE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'


def lifecycle_fixture(present=True):
    values = records('lifecycle-linux-reference-02.jsonl')
    for v in values:
        if 'reset_policy' in v:
            v['reset_policy'] = 0
            v['policy_sysctl_present'] = present
        if v.get('case', '').endswith('resets_to_policy'):
            v['actual'] = v['expected'] = 0
    if not present:
        values = [v for v in values if v.get('case') != 'explicit_reset_policy_equals_readonly_actual_sysctl']
    return values


class CheckerTests(unittest.TestCase):
    def test_positive_oracle_shapes_only(self):
        for values, suite, count in [(lifecycle_fixture(), 'lifecycle', 165),
                                     (lifecycle_fixture(False), 'lifecycle', 164),
                                     (records('lifecycle-linux-stat-reference-03.jsonl'), 'stat', 54)]:
            for raw in [wrapped(values), wrapped(values).encode()]:
                r = checker.check(raw, 33, False)
                self.assertTrue(r['passed'], r)
                self.assertEqual(r['suite'], suite)
                self.assertEqual(r['observations'], count)
                self.assertFalse(r['production_isolation_qualified'])

    def test_common_mutations(self):
        for suite, original in [('v2', lifecycle_fixture()), ('stat', records('lifecycle-linux-stat-reference-03.jsonl'))]:
            def change(index, key, value):
                modified = deepcopy(original)
                modified[index][key] = value
                return wrapped(modified)
            first_case = next(i for i, v in enumerate(original) if 'case' in v)
            summary = len(original) - 1
            missing = deepcopy(original); del missing[first_case]
            duplicate = deepcopy(original); duplicate.insert(first_case, deepcopy(duplicate[first_case]))
            reordered = deepcopy(original); reordered[first_case], reordered[first_case + 1] = reordered[first_case + 1], reordered[first_case]
            bad_permission = deepcopy(original)
            observer = next(v for v in bad_permission if 'observer_uid' in v)
            observer['observer_uid'] = 0
            common = [
                ('missing', wrapped(missing), 33, False),
                ('duplicate', wrapped(duplicate), 33, False),
                ('reordered', wrapped(reordered), 33, False),
                ('fake_reap', change(summary, 'all_children_reaped', False), 33, False),
                ('summary_only', wrapped([original[summary]]), 33, False),
                ('marker_only', 'DUMPABLE_LIFECYCLE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n', 33, False),
                ('non_raw_33', wrapped(original), 0, False),
                ('bool_exit', wrapped(original), True, False),
                ('timeout', wrapped(original), 33, True),
                ('missing_boot', wrapped(original).replace('TRILLIONNIUM_A01_BOOT_OK\n', ''), 33, False),
                ('duplicate_boot', wrapped(original) + 'TRILLIONNIUM_A01_BOOT_OK\n', 33, False),
                ('wrong_marker', wrapped(original).replace('DUMPABLE_LIFECYCLE_EXIT=0', 'DUMPABLE_LIFECYCLE_EXIT=42'), 33, False),
                ('extra_exit', wrapped(original) + 'DUMPABLE_LIFECYCLE_EXIT=0\n', 33, False),
                ('after_completion', wrapped(original) + json.dumps(original[summary]) + '\n', 33, False),
                ('bad_uid', wrapped(bad_permission), 33, False),
                ('false_pass', change(first_case, 'passed', False), 33, False),
                ('numeric_pass', change(first_case, 'passed', 1), 33, False),
                ('unknown_key', change(first_case, 'unexpected', True), 33, False),
                ('duplicate_json_key', wrapped(original).replace('"passed":true', '"passed":false,"passed":true', 1), 33, False),
            ]
            for name, raw, code, timeout in common:
                with self.subTest(suite=suite, mutation=name):
                    self.assertFalse(checker.check(raw, code, timeout)['passed'])
                    MUTATIONS.append(f'{suite}:{name}')

    def test_lifecycle_specific_mutations(self):
        original = lifecycle_fixture()
        for name, select, key, value in [
            ('bad_caps', lambda v: 'cap_eff' in v, 'cap_eff', 1),
            ('bad_nnp', lambda v: 'nnp' in v, 'nnp', 0),
            ('bad_policy', lambda v: 'reset_policy' in v, 'reset_policy', 1),
            ('fake_set_get', lambda v: v.get('case') == 'get_zero', 'actual', 1),
            ('fake_expected', lambda v: v.get('case') == 'get_zero', 'expected', 1),
            ('enosys_not_denial', lambda v: v.get('stage') == 'cross_child_set0', 'errno', 38),
            ('zero_not_positive', lambda v: v.get('stage') == 'cross_child_set1', 'rc', 0),
            ('old_env_leak', lambda v: v.get('operation') == 'old_environ_after_exec', 'read_bytes', 1),
            ('old_auxv_malformed', lambda v: v.get('operation') == 'old_auxv_after_exec', 'read_bytes', 1),
            ('fake_fixture_reap', lambda v: v.get('case') == 'credential_fixture_reaped', 'actual', 0),
        ]:
            values = deepcopy(original)
            next(v for v in values if select(v))[key] = value
            with self.subTest(mutation=name):
                self.assertFalse(checker.check_lifecycle(wrapped(values), 33, False)['passed'])
                MUTATIONS.append(f'v2:{name}')

    def test_stat_specific_mutations(self):
        original = records('lifecycle-linux-stat-reference-03.jsonl')
        for name, select, key, value in [
            ('leaked_code', lambda v: v.get('field') == 26, 'masked_value', 4198400),
            ('leaked_stack', lambda v: v.get('field') == 28, 'masked_value', 0x70000000),
            ('wrong_field', lambda v: v.get('field') == 45, 'field', 44),
            ('wrong_phase', lambda v: v.get('field') == 45, 'stage_dumpable', 1),
            ('bad_caps', lambda v: 'cap_eff' in v, 'cap_eff', 1),
            ('bad_nnp', lambda v: 'nnp' in v, 'nnp', 0),
        ]:
            values = deepcopy(original)
            next(v for v in values if select(v))[key] = value
            with self.subTest(mutation=name):
                self.assertFalse(checker.check_stat(wrapped(values), 33, False)['passed'])
                MUTATIONS.append(f'stat:{name}')

    def test_actual_old_native_failures_rejected(self):
        for directory in ['lifecycle-native-v2-6c26-negative-01', 'lifecycle-native-stat-0252-negative-01']:
            raw = (HERE / directory / 'serial.log').read_bytes()
            self.assertFalse(checker.check(raw, 33, False)['passed'])
            # Even replacing only the failure exit marker must not erase failed observations.
            self.assertFalse(checker.check(raw.replace(b'EXIT=42', b'EXIT=0'), 33, False)['passed'])
            MUTATIONS.extend([directory + ':original_failure', directory + ':marker_replacement_only'])


if __name__ == '__main__':
    program = unittest.main(exit=False, verbosity=2)
    print(json.dumps({'host_checker_tests': True, 'mutations_rejected': len(MUTATIONS),
                      'mutation_names': MUTATIONS, 'passed': program.result.wasSuccessful(),
                      'synthetic_shapes_are_not_guest_qualification': True}))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
