"""Protocol/namespace negative cases, not Android or production qualification."""

import base64
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from support.android.receiver import build_receiver


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def payload():
    return {
        'schema_version': 1, 'action': 'set_text', 'operation_id': 'original:operation-1',
        'destination_id': 'fixture-only', 'value': '中文输入😀\n第二行', 'expires_elapsed_ms': 105000,
        'observation': {
            'generation': {'boot_id': 'a'},
            'window': {'package': 'com.android.settings'},
            'target': {'resource_id': 'com.android.settings:id/search_src_text'},
        },
    }


def request(value=None, op='organ-set-text'):
    raw = canonical(payload() if value is None else value)
    return {'op': op, 'payload_base64': base64.b64encode(raw).decode(),
            'payload_sha256': hashlib.sha256(raw).hexdigest()}


class BoundReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.output, cls.record = build_receiver.sources(Path(cls.directory.name) / 'candidate')
        loader = importlib.machinery.SourceFileLoader('bound_receiver_fixture', str(cls.output / 'android-digitalis-observe-helper'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.receiver = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.receiver)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_upstream_source_bytes_and_legacy_cli_remain_pinned(self):
        for name, sha in build_receiver.PREIMAGES.items():
            self.assertEqual(build_receiver.sha(build_receiver.ROOT / 'upstream' / name), sha)
        original = (build_receiver.ROOT / 'upstream/android_app.py').read_text()
        generated = (self.output / 'android-digitalis-observe-helper').read_text()
        self.assertEqual(original[original.index('def client():'):], generated[generated.index('def client():'):])
        self.assertEqual(self.record['reviewed_helper_derivation']['frozen_input_sha256'],
                         build_receiver.PREIMAGES['android_app.py'])
        self.assertEqual(self.record['reviewed_helper_derivation']['intermediate_sha256'],
                         build_receiver.REVIEWED_LIVE_HELPER_SHA256)

    def test_reviewed_legacy_home_back_enter_commands_use_only_mock_transport(self):
        expected = {
            'home': ['/system/bin/input', 'keyevent', 'KEYCODE_HOME'],
            'back': ['/system/bin/input', 'keyevent', 'KEYCODE_BACK'],
            'enter': ['/system/bin/input', 'keyboard', 'keyevent', 'KEYCODE_ENTER'],
        }
        for operation, argv in expected.items():
            with self.subTest(operation=operation), patch.object(self.receiver, 'arun') as arun:
                result = self.receiver.dispatch({'op': operation})
                arun.assert_called_once_with(argv)
                self.assertEqual(result, {'ok': True, 'performed': operation, 'visual_verified': False})


    def test_reviewed_restoration_is_required_before_success_or_failure(self):
        for ok in (True, False):
            for restored in (None, False, 'true'):
                reply = {'ok': ok, 'error': 'ORIGINAL_FAILURE', 'outcome_unknown': False,
                         'automatic_retry': False, 'accessibility_mode_restoration_verified': restored}
                raw = b'INSTRUMENTATION_RESULT: sidecar_result_base64=' + base64.b64encode(canonical(reply)) + b'\n'
                with self.subTest(ok=ok, restored=restored), \
                        patch.object(self.receiver, 'arun', return_value=raw) as arun, \
                        self.assertRaises(self.receiver.ControlError) as failed:
                    self.receiver.ui({'op': 'find'})
                self.assertEqual(str(failed.exception), 'ACCESSIBILITY_MODE_RESTORATION_UNVERIFIED')
                self.assertTrue(failed.exception.details['outcome_unknown'])
                self.assertFalse(failed.exception.details['automatic_retry'])
                arun.assert_called_once()

    def test_reviewed_original_failure_retains_confirmed_restoration(self):
        reply = {'ok': False, 'error': 'ORIGINAL_FAILURE', 'outcome_unknown': False,
                 'automatic_retry': False, 'accessibility_mode_restoration_verified': True}
        raw = b'INSTRUMENTATION_RESULT: sidecar_result_base64=' + base64.b64encode(canonical(reply)) + b'\n'
        with patch.object(self.receiver, 'arun', return_value=raw) as arun, \
                self.assertRaises(self.receiver.ControlError) as failed:
            self.receiver.ui({'op': 'find'})
        self.assertEqual(str(failed.exception), 'ORIGINAL_FAILURE')
        self.assertTrue(failed.exception.details['accessibility_mode_restoration_verified'])
        self.assertFalse(failed.exception.details['outcome_unknown'])
        self.assertFalse(failed.exception.details['automatic_retry'])
        arun.assert_called_once()

    def test_reviewed_launch_acknowledgement_requires_one_foreground_observation(self):
        observed = {'package': 'com.example', 'activity': '.Main', 'window_token': 'a1'}
        with patch.object(self.receiver, 'foreground', return_value=observed) as foreground:
            result = self.receiver.launch_receipt('com.example/.Main', 'com.example', 'Status: ok\n')
        foreground.assert_called_once_with()
        self.assertTrue(result['launch_accepted'])
        self.assertTrue(result['foreground_verified'])
        self.assertFalse(result['outcome_unknown'])
        self.assertFalse(result['automatic_retry'])
        self.assertFalse(result['business_success_verified'])
        self.assertFalse(result['visual_verified'])
        self.assertEqual(result['foreground'], observed)

    def test_reviewed_launch_ambiguous_or_timed_out_acknowledgement_never_relaunches(self):
        cases = [('Status: timeout\n', 'LAUNCH_WAIT_TIMEOUT', True),
                 ('Status: ok\nStatus: ok\n', 'LAUNCH_STATUS_UNVERIFIED', None),
                 ('Starting: Intent\n', 'LAUNCH_STATUS_UNVERIFIED', None),
                 ('Status: ok\nError: failure\n', 'LAUNCH_FAILED', False)]
        for output, code, accepted in cases:
            with self.subTest(output=output), \
                    patch.object(self.receiver, 'foreground') as foreground, \
                    patch.object(self.receiver, 'arun') as arun, \
                    self.assertRaises(self.receiver.ControlError) as failed:
                self.receiver.launch_receipt('com.example/.Main', 'com.example', output)
            self.assertEqual(str(failed.exception), code)
            self.assertIs(failed.exception.details['launch_accepted'], accepted)
            self.assertTrue(failed.exception.details['outcome_unknown'])
            self.assertFalse(failed.exception.details['automatic_retry'])
            foreground.assert_not_called()
            arun.assert_not_called()

    def test_reviewed_launch_foreground_drift_or_failure_retains_unknown_outcome(self):
        for observed in ({'package': 'com.other'}, {}, RuntimeError('unavailable')):
            with self.subTest(observed=observed), \
                    patch.object(self.receiver, 'foreground') as foreground, \
                    patch.object(self.receiver, 'arun') as arun, \
                    self.assertRaises(self.receiver.ControlError) as failed:
                if isinstance(observed, Exception):
                    foreground.side_effect = observed
                else:
                    foreground.return_value = observed
                self.receiver.launch_receipt('com.example/.Main', 'com.example', 'Status: ok\n')
            self.assertTrue(failed.exception.details['launch_accepted'])
            self.assertTrue(failed.exception.details['outcome_unknown'])
            self.assertFalse(failed.exception.details['automatic_retry'])
            self.assertFalse(failed.exception.details['foreground_verified'])
            foreground.assert_called_once_with()
            arun.assert_not_called()

    def test_reviewed_launch_transport_failure_preserves_one_attempt(self):
        cases = [(subprocess.TimeoutExpired('fixture-only', 35), 'LAUNCH_RESPONSE_TIMEOUT'),
                 (RuntimeError('fixture-only'), 'LAUNCH_RESPONSE_UNAVAILABLE')]
        for error, code in cases:
            with self.subTest(code=code), \
                    patch.object(self.receiver, 'arun', side_effect=[b'com.example/.Main\n', error]) as arun, \
                    patch.object(self.receiver, 'foreground') as foreground, \
                    self.assertRaises(self.receiver.ControlError) as failed:
                self.receiver.dispatch({'op': 'launch', 'package': 'com.example'})
            self.assertEqual(str(failed.exception), code)
            self.assertTrue(failed.exception.details['outcome_unknown'])
            self.assertFalse(failed.exception.details['automatic_retry'])
            self.assertIsNone(failed.exception.details['launch_accepted'])
            self.assertEqual(arun.call_count, 2)
            self.assertEqual(arun.call_args.args[0],
                             ['/system/bin/am', 'start', '-W', '-n', 'com.example/.Main'])
            foreground.assert_not_called()

    def test_reviewed_delta_rejects_changed_context_and_changed_postimage(self):
        import shutil
        for field in ('old', 'new'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'reviewed'
                shutil.copytree(build_receiver.ROOT, root)
                path = root / 'reviewed-live-helper-delta-v1.json'
                delta = json.loads(path.read_text())
                delta['patches'][0][field] += '# unreviewed fixture drift\n'
                path.write_text(json.dumps(delta))
                with patch.object(build_receiver, 'ROOT', root), self.assertRaises(ValueError):
                    build_receiver.sources(Path(directory) / 'rejected-candidate')

    def test_unknown_fields_and_nonexact_resource_fail_before_discovery(self):
        cases = [
            {'op': 'organ-observe', 'package': 'com.android.settings', 'resource_id': 'editable'},
            {'op': 'organ-observe', 'package': 'com.android.settings', 'resource_id': 'com.android.settings:id/search', 'index': 0},
            {'op': 'organ-observe', 'package': 'com.android.settings', 'resource_id': 'com.other:id/search'},
            {**request(), 'grant': 'caller-claimed-authority'},
        ]
        with patch.object(self.receiver, 'discover') as discover:
            for value in cases:
                with self.subTest(value=value), self.assertRaises(self.receiver.ControlError):
                    self.receiver.dispatch(value)
        discover.assert_not_called()

    def test_same_exact_payload_and_utf8_pass_through_to_receiver(self):
        original = request()
        actual = self.receiver._organ_request(original)
        self.assertEqual(actual['organ']['payload_base64'], original['payload_base64'])
        self.assertEqual(actual['organ']['payload_sha256'], original['payload_sha256'])
        self.assertEqual(actual['value'], payload()['value'])
        self.assertEqual(actual['selector'], {'id': 'com.android.settings:id/search_src_text', 'package': 'com.android.settings'})
        self.assertNotIn('index', actual)

    def test_payload_hash_and_duplicate_json_are_rejected(self):
        changed = request()
        changed['payload_sha256'] = '0' * 64
        duplicate = b'{"action":"set_text","action":"set_text"}'
        cases = [changed, {'op': 'organ-set-text', 'payload_base64': base64.b64encode(duplicate).decode(),
                           'payload_sha256': hashlib.sha256(duplicate).hexdigest()}]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(self.receiver.ControlError):
                self.receiver._organ_request(value)

    def test_noncanonical_floats_boolean_deadline_and_text_bounds_reject(self):
        variants = [('expires_elapsed_ms', True), ('value', '中' * 1366), ('value', 'a\0b'),
                    ('operation_id', 'space is not an operation')]
        for name, value in variants:
            changed = payload()
            changed[name] = value
            with self.subTest(name=name), self.assertRaises(self.receiver.ControlError):
                self.receiver._organ_request(request(changed))
        with self.assertRaises(self.receiver.ControlError):
            self.receiver._organ_json(b'{"extra":NaN}')
        with self.assertRaises(self.receiver.ControlError):
            self.receiver._organ_json(b'{ "extra":1}')

    def test_readback_is_a_find_and_carries_no_text_mutation(self):
        actual = self.receiver._organ_request(request(op='organ-readback'))
        self.assertEqual(actual['op'], 'find')
        self.assertEqual(actual['organ']['mode'], 'readback')
        self.assertNotIn('value', actual)

    def test_generation_change_prevents_readback_runner_submission(self):
        cell = types.SimpleNamespace(generation={'boot_id': 'b'}, deadline=155,
                                     run=lambda *a, **k: None, close=lambda: None)
        with patch.object(self.receiver, '_OrganCell', return_value=cell), \
                patch.object(self.receiver.time, 'clock_gettime', return_value=100), \
                patch.object(self.receiver, 'ui') as ui:
            with self.assertRaises(self.receiver.ControlError) as failed:
                self.receiver.dispatch(request(op='organ-readback'))
        self.assertEqual(str(failed.exception), 'CELL_GENERATION_CHANGED')
        ui.assert_not_called()

    def test_helper_cannot_synthesize_receiver_success_or_rebind_operation(self):
        cell = types.SimpleNamespace(generation={'boot_id': 'a'}, deadline=155,
                                     run=lambda *a, **k: None, close=lambda: None)
        good = {'ok': True, 'organ_protocol': 'pocket4-bound-text-v1', 'receiver_generation': cell.generation,
                'operation_id': payload()['operation_id'], 'payload_sha256': request()['payload_sha256']}
        for missing in ('organ_protocol', 'receiver_generation', 'operation_id', 'payload_sha256'):
            reply = copy.deepcopy(good)
            del reply[missing]
            with self.subTest(missing=missing), \
                    patch.object(self.receiver, '_OrganCell', return_value=cell), \
                    patch.object(self.receiver.time, 'clock_gettime', return_value=100), \
                    patch.object(self.receiver, 'ui', return_value=reply) as ui:
                with self.assertRaises(self.receiver.ControlError) as failed:
                    self.receiver.dispatch(request(op='organ-readback'))
            self.assertFalse(failed.exception.details['outcome_unknown'])
            self.assertEqual(ui.call_args.args[0]['op'], 'find')

    def test_namespace_descriptors_pin_original_cell_across_every_command(self):
        generation = {'mount_namespace': 'mnt:[11]', 'pid_namespace': 'pid:[12]'}
        with patch.object(self.receiver, 'discover', return_value=(123, {}, {})) as discover, \
                patch.object(self.receiver, '_organ_generation', return_value=generation), \
                patch.object(self.receiver.os, 'open', side_effect=[21, 22, 23, 24]), \
                patch.object(self.receiver.os, 'readlink', side_effect=['mnt:[11]', 'pid:[12]']), \
                patch.object(self.receiver.os, 'close'), \
                patch.object(self.receiver.time, 'clock_gettime', return_value=100), \
                patch.object(self.receiver, '_organ_run_bounded', return_value=types.SimpleNamespace(returncode=0, stdout=b'fixed')) as run:
            cell = self.receiver._OrganCell()
            try:
                cell.run(['/system/bin/getprop'])
                cell.run(['/system/bin/getprop'])
            finally:
                cell.close()
        discover.assert_called_once()
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertIn('--mount=/proc/self/fd/21', argv)
            self.assertIn('--pid=/proc/self/fd/22', argv)
            self.assertNotIn('-t', argv)
            self.assertEqual(call.kwargs['pass_fds'], (21, 22, 23, 24))
            self.assertEqual(call.kwargs['deadline'], 130)

    def test_expired_cell_budget_never_starts_a_late_instrumentation(self):
        cell = self.receiver._OrganCell.__new__(self.receiver._OrganCell)
        cell.init, cell.env, cell.fds, cell.generation, cell.deadline = 123, {}, {}, {'a': 'b'}, 105
        with patch.object(self.receiver, '_organ_generation', return_value=cell.generation), \
                patch.object(self.receiver.time, 'clock_gettime', return_value=106), \
                patch.object(self.receiver, '_organ_run_bounded') as run:
            with self.assertRaises(self.receiver.ControlError):
                cell.run(['/system/bin/getprop'])
        run.assert_not_called()

    def test_real_transport_retains_utf8_and_exact_output_bounds(self):
        value = '中文输入😀'.encode('utf-8')
        reply = self.receiver._organ_run_bounded(
            [sys.executable, '-c',
             "import os; os.write(1, " + repr(value) + "); os.write(2, b'0123456789abcdef')"],
            deadline=time.clock_gettime(time.CLOCK_BOOTTIME) + 5,
            stdout_limit=len(value), stderr_limit=16)
        self.assertEqual(reply.returncode, 0)
        self.assertEqual(reply.stdout, value)
        self.assertEqual(reply.stderr, b'0123456789abcdef')

    def test_real_transport_bounds_both_streams_and_reaps_its_child(self):
        popen = subprocess.Popen
        for fd, limit in ((1, 64), (2, 16)):
            children = []

            def start(*args, **kwargs):
                child = popen(*args, **kwargs)
                children.append(child)
                return child

            with self.subTest(fd=fd), patch.object(self.receiver.subprocess, 'Popen', side_effect=start), \
                    self.assertRaises(self.receiver.ControlError) as failed:
                self.receiver._organ_run_bounded(
                    [sys.executable, '-c',
                     f"import os,time; os.write({fd}, b'x' * {limit + 1}); time.sleep(2)"],
                    deadline=time.clock_gettime(time.CLOCK_BOOTTIME) + 5,
                    stdout_limit=64, stderr_limit=16)
            self.assertEqual(str(failed.exception), 'ORGAN_OUTPUT_LIMIT_EXCEEDED')
            self.assertTrue(failed.exception.details['outcome_unknown'])
            self.assertFalse(failed.exception.details['automatic_retry'])
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].returncode)
            self.assertTrue(children[0].stdout.closed)
            self.assertTrue(children[0].stderr.closed)

    def test_real_transport_deadline_reaps_without_retry(self):
        popen = subprocess.Popen
        children = []

        def start(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            return child

        with patch.object(self.receiver.subprocess, 'Popen', side_effect=start), \
                self.assertRaises(self.receiver.ControlError) as failed:
            self.receiver._organ_run_bounded(
                [sys.executable, '-c', 'import time; time.sleep(2)'],
                deadline=time.clock_gettime(time.CLOCK_BOOTTIME) + 0.2)
        self.assertEqual(str(failed.exception), 'ORGAN_DEADLINE_EXCEEDED')
        self.assertFalse(failed.exception.details['automatic_retry'])
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)

    def test_interrupted_transport_cleans_only_its_own_process_group(self):
        popen = subprocess.Popen
        children = []
        killpg = os.killpg
        groups = []

        def start(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            return child

        def stop(group, sig):
            groups.append(group)
            return killpg(group, sig)

        with patch.object(self.receiver.subprocess, 'Popen', side_effect=start), \
                patch.object(self.receiver.os, 'killpg', side_effect=stop), \
                patch.object(self.receiver.selectors.DefaultSelector, 'select', side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            self.receiver._organ_run_bounded(
                [sys.executable, '-c', 'import time; time.sleep(2)'],
                deadline=time.clock_gettime(time.CLOCK_BOOTTIME) + 5)
        self.assertEqual(groups, [children[0].pid])
        self.assertIsNotNone(children[0].returncode)
        self.assertTrue(children[0].stdout.closed)
        self.assertTrue(children[0].stderr.closed)

    def test_late_result_never_signals_an_already_reaped_process_group(self):
        popen, clock = subprocess.Popen, time.clock_gettime
        deadline = clock(time.CLOCK_BOOTTIME) + 5
        reaped = False

        def start(*args, **kwargs):
            child = popen(*args, **kwargs)
            wait = child.wait

            def finish(*args, **kwargs):
                nonlocal reaped
                result = wait(*args, **kwargs)
                reaped = True
                return result

            child.wait = finish
            return child

        def observed_time(kind):
            return deadline + 1 if reaped else clock(kind)

        with patch.object(self.receiver.subprocess, 'Popen', side_effect=start), \
                patch.object(self.receiver.time, 'clock_gettime', side_effect=observed_time), \
                patch.object(self.receiver.os, 'killpg') as killpg, \
                self.assertRaises(self.receiver.ControlError) as failed:
            self.receiver._organ_run_bounded([sys.executable, '-c', 'pass'], deadline=deadline)
        self.assertTrue(reaped)
        self.assertEqual(str(failed.exception), 'ORGAN_DEADLINE_EXCEEDED')
        killpg.assert_not_called()

    def test_wait_interruption_after_owned_child_reap_never_signals_old_group(self):
        # Popen.wait can reap the child and still re-raise KeyboardInterrupt.
        # Use one normally exiting owned child and intercept all group signals;
        # no PID reuse or unrelated process is involved in this regression.
        popen = subprocess.Popen
        children = []
        wait_completed = False

        def start(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            wait = child.wait

            def interrupted_wait(*args, **kwargs):
                nonlocal wait_completed
                result = wait(*args, **kwargs)
                if not wait_completed:
                    wait_completed = True
                    raise KeyboardInterrupt
                return result

            child.wait = interrupted_wait
            return child

        with patch.object(self.receiver.subprocess, 'Popen', side_effect=start), \
                patch.object(self.receiver.os, 'killpg') as killpg, \
                self.assertRaises(KeyboardInterrupt):
            self.receiver._organ_run_bounded(
                [sys.executable, '-c', 'pass'],
                deadline=time.clock_gettime(time.CLOCK_BOOTTIME) + 5)

        self.assertTrue(wait_completed)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertTrue(children[0].stdout.closed)
        self.assertTrue(children[0].stderr.closed)
        killpg.assert_not_called()


if __name__ == '__main__':
    unittest.main()
