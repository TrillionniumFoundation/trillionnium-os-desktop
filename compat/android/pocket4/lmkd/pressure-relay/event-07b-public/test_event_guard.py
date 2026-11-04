#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Temporary-file guard controls; no proc discovery, cgroup or PSI writes."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest

import event_guard as guard


class Controls(unittest.TestCase):
    def setUp(self):
        self.prior = guard.load_module(Path(__file__).with_name('prior_run_fixture.py'),
                                      guard.PRIOR_SHA, 'pinned_old_guard_controls')

    def health(self):
        return {'host_available': 8 * 1024**3, 'host_swap_free': 2 * 1024**3,
                'main_current': 5_000_000_000, 'main_pids': 100,
                'host_psi': {'full': {'avg10': 0}}, 'main_psi': {'full': {'avg10': 0}},
                'main_events': dict(high=0, max=0, oom=0, oom_kill=0, oom_group_kill=0),
                'main_pids_events': {'max': 0}}

    def harness(self, output, health=None):
        value = guard.MainGuard.__new__(guard.MainGuard)
        value.prior = types.SimpleNamespace(health=lambda _: health or self.health(),
             guard_admission=self.prior.guard_admission, guard_health=self.prior.guard_health)
        value.pin = {'limits': {'memory.max': '6442450944', 'memory.high': '5368709120',
                                'pids.max': '12288'}}
        value.formal_guard = lambda: None
        value.output = output
        value.paths = None
        value.scope_baseline = None
        value.baseline = self.health()
        value.attempted = False
        value.index = 0
        return value

    def test_exact_old_guard_uses_max_not_high_with_integer_boundary(self):
        pin = {'limits': {'memory.max': '6442450944', 'memory.high': '5368709120', 'pids.max': '12288'}}
        current = self.health()
        self.prior.guard_admission(pin, current)
        # 5.0 GB is above 80% of high but below 80% of max. Preserve that rule.
        current['main_current'] = (int(pin['limits']['memory.max']) * 80 + 99) // 100
        with self.assertRaises(self.prior.Stop) as caught:
            self.prior.guard_admission(pin, current)
        self.assertEqual(caught.exception.observation['metric'], 'memory.current_bytes')
        self.assertEqual(caught.exception.observation['limit'], 6442450944)

    def test_rejected_health_frame_exists_before_threshold_judgment(self):
        current = self.health()
        current['host_psi']['full']['avg10'] = 10
        with tempfile.TemporaryDirectory() as directory:
            value = self.harness(Path(directory), current)
            actual_guard = value.prior.guard_admission
            def inspecting(pin, sample):
                persisted = json.loads((Path(directory) / 'health-0000.json').read_text())
                self.assertEqual(persisted['health'], current)
                actual_guard(pin, sample)
            value.prior.guard_admission = inspecting
            with self.assertRaises(self.prior.Stop) as caught:
                value.sample('negative-global-pressure')
            self.assertEqual(caught.exception.observation['value'], 10)
            self.assertEqual(caught.exception.observation['scope'], 'host')
            self.assertEqual(caught.exception.evidence, str(Path(directory) / 'health-0000.json'))

    def test_identity_failure_and_main_counter_increment_are_preserved(self):
        for identity_failure in (False, True):
            current = self.health()
            current['main_events']['high'] = 1
            with tempfile.TemporaryDirectory() as directory:
                value = self.harness(Path(directory), current)
                if identity_failure:
                    def reject():
                        raise RuntimeError('bound epoch changed')
                    value.formal_guard = reject
                with self.assertRaises(RuntimeError):
                    value.sample('negative-main-fence')
                frame = json.loads((Path(directory) / 'health-0000.json').read_text())
                self.assertEqual(frame['health']['main_events']['high'], 1)
                self.assertEqual('formal_identity_error' in frame, identity_failure)

    def test_child_high_is_allowed_but_parent_local_pressure_or_oom_is_not(self):
        item = {'identity': [1, 2], 'limits': {'memory.max': '1'},
                'memory_current': 1, 'memory_events': dict(high=0, max=0, oom=0, oom_kill=0, oom_group_kill=0),
                'memory_events_local': dict(high=0, max=0, oom=0, oom_kill=0, oom_group_kill=0), 'pids_events': {'max': 0}}
        baseline = {name: copy.deepcopy(item) for name in ('job', 'root', 'control', 'target', 'sibling')}
        now = copy.deepcopy(baseline)
        for name in ('target', 'root', 'job'):
            now[name]['memory_events']['high'] = 1
        now['target']['memory_events_local']['high'] = 1
        guard.owned_guard(now, baseline)
        for scope, field, event in (('job', 'memory_events_local', 'high'),
                                    ('target', 'memory_events', 'max'),
                                    ('root', 'memory_events', 'oom_kill')):
            bad = copy.deepcopy(now)
            bad[scope][field][event] += 1
            with self.assertRaises(guard.GuardFailure) as caught:
                guard.owned_guard(bad, baseline)
            self.assertEqual(caught.exception.observation['scope'], scope)
        now['target']['memory_current'] = 48 * 1024 * 1024
        with self.assertRaises(guard.GuardFailure) as caught:
            guard.owned_guard(now, baseline)
        self.assertEqual(caught.exception.observation['value'], 48 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main(verbosity=2)
