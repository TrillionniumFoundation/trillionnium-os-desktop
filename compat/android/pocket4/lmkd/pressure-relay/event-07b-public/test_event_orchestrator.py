#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Actual owned-child/pipe failure controls. No cgroup, PSI, pressure or Main.

The helper is deliberately a mock protocol process, never a PSI event source.
Tests assert that its output cannot qualify a real event. The optional old
driver branch is a precise source negative control; its leaked owned children
and journal FDs are reclaimed by the outer test harness before it exits.
"""
import contextlib
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import event_guard

source = Path(os.environ.get('P4_NEGATIVE_EVENT_DRIVER', Path(__file__).with_name('owned_event_fixture.py')))
if os.environ.get('P4_NEGATIVE_EVENT_DRIVER'):
    assert hashlib.sha256(source.read_bytes()).hexdigest() == '516b55426cb1c708e545bc3fa4a1947a0ca5a22ae89d51a9c5c4eca51c31868e'
spec = importlib.util.spec_from_file_location('owned_driver_under_test', source)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

HELPER = '''#!/usr/bin/python3
import os,sys
os.write(2,b'MOCK_STDERR_READY\\n')
os.write(1,b'EVENT_READY mock_protocol_only=true\\n')
data=os.read(0,9)
os.write(1,b'MOCK_INPUT_HEX='+data.hex().encode()+b'\\n')
os.write(2,b'MOCK_STDERR_FINAL\\n')
'''


class FakeGuardian:
    def __init__(self, output):
        self.output = output
        self.index = 0
        self.attempted = False

    def sample(self, label):
        now = time.monotonic_ns()
        frame = {'label': label, 'started_monotonic_ns': now, 'completed_monotonic_ns': now,
                 'owned_scope': {'target': {'memory_current': 0}}, 'mock_health_for_ipc_test': True}
        event_guard.save(self.output / ('health-%04d.json' % self.index), frame)
        self.index += 1
        return frame


class Controls(unittest.TestCase):
    def run_case(self, failure=None, delay=None):
        children = []
        owned_fds = []
        child_stdout = None
        originals = {'popen': subprocess.Popen, 'open': os.open, 'read': os.read,
                     'save': driver.save, 'selector': driver.selectors.DefaultSelector}
        before_fds = len(os.listdir('/proc/self/fd'))
        result = None
        raised = None

        def spawn(*args, **kwargs):
            nonlocal child_stdout
            child = originals['popen'](*args, **kwargs)
            children.append(child)
            child_stdout = child.stdout.fileno()
            return child

        def opened(path, *args, **kwargs):
            name = Path(path).name if isinstance(path, (str, bytes, os.PathLike)) else None
            if failure in ('journal-stdout', 'journal-stderr', 'drain-stdout') and name == ('test.stdout' if failure == 'journal-stdout' else 'test.stderr'):
                raise OSError('injected exact owned journal setup failure')
            fd = originals['open'](path, *args, **kwargs)
            if name in ('test.stdout', 'test.stderr'):
                stat = os.fstat(fd)
                owned_fds.append((fd, stat.st_dev, stat.st_ino))
            return fd

        def read(fd, *args, **kwargs):
            if failure == 'drain-stdout' and fd == child_stdout:
                raise OSError('injected one-stream drain failure')
            return originals['read'](fd, *args, **kwargs)

        def saved(path, value):
            if delay == 'intent' and Path(path).name == 'arm-intent.json':
                time.sleep(0.12)
            return originals['save'](path, value)

        class Pin:
            def verify(self, _):
                if delay == 'pin':
                    time.sleep(0.12)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / 'mock-owned-helper'
            helper.write_text(HELPER)
            helper.chmod(0o700)
            target = root / 'mock-target'; target.mkdir()
            output = root / 'output'; output.mkdir()
            try:
                with contextlib.ExitStack() as stack:
                    stack.enter_context(mock.patch.object(driver.subprocess, 'Popen', spawn))
                    stack.enter_context(mock.patch.object(driver.os, 'open', opened))
                    stack.enter_context(mock.patch.object(driver.os, 'read', read))
                    stack.enter_context(mock.patch.object(driver, 'save', saved))
                    if failure == 'pidfd':
                        stack.enter_context(mock.patch.object(driver.os, 'pidfd_open', side_effect=OSError('injected pidfd setup failure')))
                    if failure == 'selector':
                        stack.enter_context(mock.patch.object(driver.selectors, 'DefaultSelector', side_effect=OSError('injected selector setup failure')))
                    if failure == 'selector-register':
                        class BrokenSelector:
                            def __init__(self):
                                self.actual = originals['selector']()
                            def register(self, *args, **kwargs):
                                raise OSError('injected selector registration failure')
                            def close(self):
                                self.actual.close()
                        stack.enter_context(mock.patch.object(driver.selectors, 'DefaultSelector', BrokenSelector))
                    try:
                        result = driver.run_event(helper, target, 'mock-membership-no-cgroup-action', output, FakeGuardian(output), [Pin()])
                    except Exception as error:
                        raised = error
                # These assertions happen before the harness rescues an old
                # failed driver. Rescue cannot make a failed branch pass.
                self.assertIsNone(raised, 'owned driver must return a failed receipt after setup failure')
                self.assertTrue(children and all(child.returncode is not None for child in children), 'driver must reap its actual child')
                self.assertTrue(result['owned_child_reaped'])
                self.assertFalse(result['real_event_and_child_cleanup_pass'], 'mock protocol is never a genuine PSI gate')
                if failure:
                    self.assertFalse(result['armed_exactly_once'])
                    self.assertIn('MOCK_STDERR_FINAL', result['test_stderr'], 'other stream must survive one-stream setup/drain failure')
                if failure == 'drain-stdout':
                    self.assertTrue(any('stdout-drain' in item for item in result['owned_ipc_cleanup_errors']))
                if delay:
                    self.assertFalse(result['armed_exactly_once'], 'expired health must not write any ARM bytes')
                    self.assertFalse(result['arm_write_attempted'])
                    self.assertIn('MOCK_INPUT_HEX=71', result['test_stdout'])
                    stop = json.loads((output / 'first-stop.json').read_text())
                    self.assertIn('HEALTH_EXPIRED_BEFORE_ARM', stop['error'])
                    self.assertFalse(stop['armed'])
                if not failure and not delay:
                    self.assertTrue(result['armed_exactly_once'])
                    wire = next(line.split('=', 1)[1] for line in result['test_stdout'].splitlines() if line.startswith('MOCK_INPUT_HEX='))
                    self.assertEqual(len(bytes.fromhex(wire)), 9)
                    self.assertTrue(wire.startswith('61'))
                self.assertEqual(len(os.listdir('/proc/self/fd')), before_fds, 'driver leaked a held descriptor')
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=3)
                    for stream in (child.stdin, child.stdout, child.stderr):
                        if stream is not None and not stream.closed:
                            stream.close()
                for fd, device, inode in owned_fds:
                    try:
                        actual = os.fstat(fd)
                        if (actual.st_dev, actual.st_ino) == (device, inode):
                            os.close(fd)
                    except OSError:
                        pass
                gc.collect()

    def test_pidfd_setup_failure_reaps_actual_owned_child(self):
        self.run_case(failure='pidfd')

    def test_selector_setup_and_register_failures_reap_actual_owned_child(self):
        for failure in ('selector', 'selector-register'):
            with self.subTest(failure=failure):
                self.run_case(failure=failure)

    def test_partial_journal_setup_and_one_stream_drain_do_not_skip_cleanup(self):
        for failure in ('journal-stdout', 'journal-stderr', 'drain-stdout'):
            with self.subTest(failure=failure):
                self.run_case(failure=failure)

    def test_expired_health_after_pin_io_never_arms(self):
        self.run_case(delay='pin')

    def test_expired_health_after_intent_fsync_never_arms(self):
        self.run_case(delay='intent')

    def test_fresh_arm_carries_original_absolute_deadline_but_mock_cannot_pass(self):
        self.run_case()


if __name__ == '__main__':
    unittest.main(verbosity=2)
