#!/usr/bin/env python3
"""Offline fence control flow; Main snapshot and inner build are explicit seams."""
import builtins
import contextlib
import copy
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

HERE = Path(__file__).resolve().parent
raw = (HERE / 'fenced_build.py').read_bytes()
s = {'__name__': 'fence_review'}
exec(compile(raw, 'fenced_build.py', 'exec'), s, s)
checks = []


def check(name, value):
    if not value:
        raise RuntimeError(name)
    checks.append({'name': name, 'pass': True})


sample = {key: {'pin': 1} for key in ('activation_sha256', 'epoch_source_sha256',
          'framework_epoch_sha256', 'cell_sha256', 'host_processes', 'limits',
          'main_cgroup', 'main_cgroup_identity')}
sample.update(memory_events={'low': 0, 'high': 0, 'max': 0, 'oom': 0, 'oom_kill': 0,
                            'oom_group_kill': 0}, current_resources={'memory.current': 100,
                            'memory.swap.current': 0, 'pids.current': 5})
check('matching_observed_invariants', s['compare'](sample, copy.deepcopy(sample))['main_fence_pass'])
for key in ('activation_sha256', 'framework_epoch_sha256', 'host_processes', 'limits',
            'main_cgroup_identity'):
    altered = copy.deepcopy(sample); altered[key] = {'changed': True}
    check('reject_changed_' + key, not s['compare'](sample, altered)['main_fence_pass'])
for key in ('oom', 'oom_kill', 'oom_group_kill'):
    altered = copy.deepcopy(sample); altered['memory_events'][key] += 1
    check('reject_' + key + '_increase', not s['compare'](sample, altered)['main_fence_pass'])
altered = copy.deepcopy(sample); altered['memory_events']['high'] += 1
result = s['compare'](sample, altered)
check('pressure_increase_reported_without_zero_interference_claim', result['main_fence_pass'] and
      result['pressure_counter_increases_observed'] == {'high': 1} and
      not result['unobserved_transient_effects_excluded'])
altered = copy.deepcopy(sample); altered['memory_events']['oom'] -= 1
try:
    s['compare'](sample, altered)
except RuntimeError:
    check('counter_regression_rejected', True)
else:
    raise RuntimeError('counter regression accepted')

controller = (HERE.parent / 'fullbuild-plan-01/freeze-01/combined_build.py').read_text()
snapshot = (HERE / 'main_snapshot.py').read_text()
packet = {'controller_source': controller, 'snapshot_source': snapshot,
          'snapshot_sha256': hashlib.sha256(snapshot.encode()).hexdigest()}
real_exec = builtins.exec

for mode in ('success', 'before_error', 'inner_error', 'after_error', 'terminal_save_error'):
    with tempfile.TemporaryDirectory(prefix='p4-fence-offline-') as directory:
        root = Path(directory)
        prep = b'{"owned":"offline fixture only"}\n'
        (root / 'preparation.json').write_bytes(prep)
        calls = []; inner_calls = []
        def capture(label, source, source_sha):
            calls.append(label)
            if mode == label + '_error':
                raise RuntimeError(label + ' seam')
            return copy.deepcopy(sample)
        def inner(arguments):
            inner_calls.append(arguments)
            if mode == 'inner_error':
                raise RuntimeError('inner seam')
            return 0
        def intercept_exec(code, globals=None, locals=None, **kwargs):
            value = real_exec(code, globals, locals, **kwargs)
            if getattr(code, 'co_filename', None) == 'frozen_combined_build.py':
                globals['main'] = inner
            return value
        original_save = s['save']
        def save(name, value):
            if mode == 'terminal_save_error' and name == 'terminal.json':
                raise OSError(errno.ENOSPC, 'terminal seam')
            return original_save(name, value)
        changes = {'ROOT': root, 'FENCE_ROOT': root / 'fences', 'capture': capture,
                   'PREPARATION_SHA': hashlib.sha256(prep).hexdigest(), 'save': save}
        with mock.patch.dict(s, changes), mock.patch.object(os, 'getuid', return_value=1000), \
                mock.patch.object(os, 'geteuid', return_value=1000), \
                mock.patch.object(builtins, 'exec', side_effect=intercept_exec), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                result = s['run'](packet)
            except OSError as error:
                if mode != 'terminal_save_error' or error.errno != errno.ENOSPC:
                    raise
                result = 1
        check(mode + '_post_fence_attempted', calls == ['before', 'after'])
        check(mode + '_inner_admission', bool(inner_calls) == (mode != 'before_error'))
        check(mode + '_result', (result == 0) == (mode == 'success'))

plan = subprocess.run([sys.executable, '-I', str(HERE / 'fenced_build.py')], capture_output=True, timeout=10)
check('default_plan_no_packet_or_actions', plan.returncode == 0 and not plan.stderr and
      json.loads(plan.stdout)['state'] == 'PLAN_ONLY')
print(json.dumps({'schema': 1, 'all_pass': True, 'checks': checks,
                  'fenced_build_sha256': hashlib.sha256(raw).hexdigest(),
                  'main_snapshot_sha256': hashlib.sha256(snapshot.encode()).hexdigest(),
                  'Main_snapshot_executed': False, 'inner_fullbuild_executed': False,
                  'root_helper_executed': False,
                  'scope': 'Real outer control flow with explicit Main and inner-build seams; actual temporary receipt writes only.'}, indent=2))
