import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('high_profile_support', Path(__file__).with_name('ai395_build_support.py'))
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


def sample():
    return {'memory.max': str(24 * s.GIB), 'memory.high': str(22 * s.GIB),
            'memory.swap.max': '0', 'memory.swap.current': '0',
            'memory.peak': str(22 * s.GIB),
            'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n',
            'memory.stat': 'anon 100\nfile 200\npgscan 5\npgsteal 4\n'}


class EarlyReclaimControls(unittest.TestCase):
    def test_early_reclaim_keeps_the_hard_cap_and_zero_tolerance(self):
        old = sample(); new = sample()
        new['memory.events'] = new['memory.events'].replace('high 0', 'high 12').replace('max 0', 'max 1')
        new['memory.stat'] = 'anon 130\nfile 160\npgscan 15\npgsteal 9\n'
        result = s.validate_inner_resource_retirement(old, new)
        self.assertEqual(result['events_delta']['high'], 12)
        self.assertEqual(result['events_delta']['max'], 1)
        self.assertEqual(result['memory_stat_after']['file'], 160)
        self.assertEqual(result['reclaim_counters_delta'], {'pgscan': 10, 'pgsteal': 5})
        self.assertEqual(result['peak_tolerance_bytes'], 0)

    def test_recorded_r3_one_page_excess_still_fails(self):
        new = sample(); new['memory.peak'] = '25769807872'
        with self.assertRaisesRegex(RuntimeError, 'peak exceeded'):
            s.validate_inner_resource_retirement(sample(), new)

    def test_exact_hard_limit_is_accepted(self):
        new = sample(); new['memory.peak'] = str(24 * s.GIB)
        self.assertEqual(s.validate_inner_resource_retirement(sample(), new)['peak_tolerance_bytes'], 0)

    def test_missing_or_raised_high_is_rejected_at_both_boundaries(self):
        for index in (0, 1):
            for value in ('max', str(24 * s.GIB), str(22 * s.GIB + 4096)):
                rows = [sample(), sample()]; rows[index]['memory.high'] = value
                with self.subTest(index=index, value=value), self.assertRaises(RuntimeError):
                    s.validate_inner_resource_retirement(*rows)

    def test_hard_limit_and_swap_cannot_be_relaxed(self):
        for index in (0, 1):
            for key, value in [('memory.max', str(25 * s.GIB)), ('memory.swap.max', '4096'),
                               ('memory.swap.current', '4096')]:
                rows = [sample(), sample()]; rows[index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(RuntimeError):
                    s.validate_inner_resource_retirement(*rows)

    def test_each_oom_event_remains_fatal(self):
        for name in ('oom', 'oom_kill', 'oom_group_kill'):
            new = sample(); new['memory.events'] = new['memory.events'].replace(name + ' 0\n', name + ' 1\n')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'OOM'):
                s.validate_inner_resource_retirement(sample(), new)

    def test_counter_reset_or_shape_change_is_rejected(self):
        old = sample(); old['memory.events'] = old['memory.events'].replace('max 0', 'max 2')
        with self.assertRaises(RuntimeError): s.validate_inner_resource_retirement(old, sample())
        new = sample(); new['memory.events'] = new['memory.events'].replace('oom 0\n', '')
        with self.assertRaises(RuntimeError): s.validate_inner_resource_retirement(sample(), new)

    def test_anon_file_and_reclaim_are_actual_required_observations(self):
        for missing in ('anon', 'file', 'pgscan', 'pgsteal'):
            new = sample(); new['memory.stat'] = '\n'.join(x for x in new['memory.stat'].splitlines() if not x.startswith(missing + ' '))
            with self.subTest(missing=missing), self.assertRaises(RuntimeError):
                s.validate_inner_resource_retirement(sample(), new)

    def test_duplicate_or_negative_stat_counters_are_rejected(self):
        for text in (sample()['memory.stat'] + 'anon 100\n', sample()['memory.stat'].replace('file 200', 'file -1')):
            with self.assertRaises(RuntimeError): s.memory_stat_summary(text)

    def test_old_profile_cannot_be_silently_relabelled(self):
        value = copy.deepcopy(s.PROFILE); del value['build_memory_high_bytes']
        with self.assertRaises(RuntimeError): s.validate_profile(value)
        for bad in (True, float(22 * s.GIB), 24 * s.GIB):
            value = copy.deepcopy(s.PROFILE); value['build_memory_high_bytes'] = bad
            with self.subTest(value=bad), self.assertRaises(RuntimeError): s.validate_profile(value)


if __name__ == '__main__':
    unittest.main()
