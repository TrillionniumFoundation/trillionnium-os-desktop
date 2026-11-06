#!/usr/bin/env python3
"""Limited offline controls. No real DNS, curl, subprocess, host or Android."""
from pathlib import Path
import copy
import errno
import hashlib
import json
import os
import tempfile
import time
import types
import unittest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent


def worker():
    scope = {'__name__': 's41_offline_controls'}
    source = (HERE / 'continue_zbj_s41_once.py').read_text()
    exec(compile(source, '<S41-offline-control>', 'exec'), scope)
    return scope


def actual_s34():
    return json.loads((PROJECT / 'official_source_scripts/s34_zbj_tail/actual-r1/com.zhubajie.client-result.raw.json').read_bytes())


def bind_changed_dns(scope, value):
    first = scope['DNS_STDOUT_RAW'].splitlines()[0]
    raw = first + '\n' + json.dumps(value, sort_keys=True) + '\n'
    terminal = json.loads(scope['DNS_TERMINAL_RAW'])
    terminal['log_bytes']['stdout'] = {'seen': len(raw.encode()), 'stored': len(raw.encode())}
    traw = json.dumps(terminal, sort_keys=True)
    scope.update(DNS_STDOUT_RAW=raw, DNS_STDOUT_SHA256=hashlib.sha256(raw.encode()).hexdigest(),
                 DNS_TERMINAL_RAW=traw, DNS_TERMINAL_SHA256=hashlib.sha256(traw.encode()).hexdigest())


class LocalControls(unittest.TestCase):
    def test_actual_settled_failure_and_dns_evidence_gate(self):
        scope = worker()
        original = actual_s34()
        unchanged = copy.deepcopy(original)
        scope['s34_result_gate'](scope['CANDIDATES'][0], original)
        self.assertEqual(original, unchanged)
        result = scope['dns_observation_gate']()
        self.assertEqual(result['job_id'], '1a1b2983a9d-fc05-7ed3')
        self.assertFalse(result['addresses_used_as_override'])

    def test_old_failure_cannot_be_relabelled_success(self):
        scope = worker()
        changed = actual_s34()
        changed['status'] = 'STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION'
        with self.assertRaisesRegex(RuntimeError, 'EXACT_SETTLED_S34_FAILURE'):
            scope['s34_result_gate'](scope['CANDIDATES'][0], changed)

    def test_exact_finite_remainder(self):
        scope = worker()
        ranges = scope['tail_plan'](scope['CANDIDATES'][0])
        self.assertEqual(len(ranges), 38)
        self.assertEqual(ranges[0], (0, 127516672, 128565247))
        self.assertEqual(ranges[-1], (37, 166313984, 166873621))
        self.assertEqual(sum(end-start+1 for _, start, end in ranges), 39356950)
        self.assertTrue(all(end-start+1 <= 1048576 for _, start, end in ranges))
        self.assertTrue(all(ranges[i-1][2]+1 == ranges[i][1] for i in range(1, 38)))

    def test_undurable_dns_terminal_rejected_even_with_matching_hash(self):
        scope = worker()
        terminal = json.loads(scope['DNS_TERMINAL_RAW'])
        terminal['output_durable'] = False
        raw = json.dumps(terminal, sort_keys=True)
        scope['DNS_TERMINAL_RAW'] = raw
        scope['DNS_TERMINAL_SHA256'] = hashlib.sha256(raw.encode()).hexdigest()
        with self.assertRaisesRegex(RuntimeError, 'DURABLE_EXACT_PRIOR_OUTCOME'):
            scope['dns_observation_gate']()

    def test_empty_dns_answer_not_a_resolved_gate(self):
        scope = worker()
        value = json.loads(scope['DNS_STDOUT_RAW'].splitlines()[1])
        value['address_records'] = []
        bind_changed_dns(scope, value)
        with self.assertRaisesRegex(RuntimeError, 'EXACT_ACTUAL_NARROW_DNS_SUCCESS'):
            scope['dns_observation_gate']()

    def test_fresh_budget_rejects_before_any_spawn(self):
        scope = worker()
        calls = []
        def forbidden_spawn(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError('No spawn is authorized by insufficient budget')
        scope['subprocess'] = types.SimpleNamespace(Popen=forbidden_spawn,
                                                   TimeoutExpired=scope['subprocess'].TimeoutExpired)
        scope['DEADLINE'] = time.monotonic() + 5
        record = {}
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            with self.assertRaisesRegex(RuntimeError, 'FRESH_BUDGET_BEFORE_SPAWN'):
                scope['own_curl'](['synthetic-not-executed'], -1, folder/'metrics', folder/'stderr', record, 1)
        self.assertEqual(calls, [])
        self.assertNotIn('pid', record)

    def test_pidfd_acquisition_failure_retires_only_owned_child(self):
        scope = worker()
        instances = []
        class FakeOwnedProcess:
            def __init__(self, *args, **kwargs):
                self.pid = 999999
                self.returncode = None
                self.kill_count = 0
                self.wait_count = 0
                instances.append(self)
            def kill(self):
                self.kill_count += 1
                self.returncode = -9
            def wait(self, timeout):
                self.wait_count += 1
                self.assert_retired = self.returncode is not None
                return self.returncode
        class OSProxy:
            def __getattr__(self, name):
                return getattr(os, name)
            def pidfd_open(self, *args):
                raise OSError(errno.EMFILE, 'synthetic pidfd acquisition failure')
        scope['os'] = OSProxy()
        scope['subprocess'] = types.SimpleNamespace(Popen=FakeOwnedProcess,
                                                   TimeoutExpired=scope['subprocess'].TimeoutExpired)
        scope['DEADLINE'] = time.monotonic() + 60
        record = {}
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            with self.assertRaises(OSError):
                scope['own_curl'](['synthetic-not-executed'], -1, folder/'metrics', folder/'stderr', record, 1)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].kill_count, 1)
        self.assertEqual(instances[0].wait_count, 1)
        self.assertTrue(instances[0].assert_retired)
        self.assertTrue(record['joined'])
        self.assertFalse(record['outcome_unknown'])
        self.assertFalse(record['pidfd_acquired'])
        self.assertTrue(record['owned_object_fallback_used'])
        self.assertEqual(record['returncode'], -9)
        self.assertEqual(record['owned_curl_signal_count'], 1)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LocalControls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'schema': 'pocket4-zbj-s41-offline-controls-v1',
                      'tests_run': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'passed': result.wasSuccessful(),
                      'actual_DNS_calls': 0, 'actual_curl_or_child_spawns': 0,
                      'actual_remote_processes': 0, 'actual_Android_calls': 0,
                      'production_ready': False}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
