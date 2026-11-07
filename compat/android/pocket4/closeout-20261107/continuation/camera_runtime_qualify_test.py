#!/usr/bin/env python3
"""Camera evidence parser controls. No installation, service action, or Android entry."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest

path = Path(__file__).with_name('runtime_qualify.py')
if not path.is_file():
    path = Path(__file__).with_name('camera_runtime_qualify.py')
spec = importlib.util.spec_from_file_location('camera_runtime', path)
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


def android_fixture():
    cycles = []
    for cycle in (1, 2):
        cycles.append({'cycle': cycle, 'ok': True, 'camera_id': 'front-physical', 'width': 640,
                       'height': 480, 'frames': 8, 'session_closed': True, 'device_closed': True,
                       'worker_joined': True, 'pixel_files_created': 0,
                       'samples': [{'frame': frame, 'timestamp_ns': str(cycle * 10000 + frame * 100),
                                    'luma_bytes': 307200, 'luma_crc32': 'a53f1'} for frame in range(1, 9)]})
    return {'schema': 'pocket4-android-camera-frame-qualification-v1', 'ok': True,
            'started_elapsed_ns': '1', 'finished_elapsed_ns': '999999', 'pixel_files_created': 0, 'cycles': cycles}


def instrument(value):
    return ('INSTRUMENTATION_RESULT: qualification_json=' + json.dumps(value) + '\nINSTRUMENTATION_CODE: -1\n').encode()


def physical_fixture():
    events = []
    for cycle in (1, 2):
        events.extend([
            {'event': 'physical_camera_open', 'capture_pid': 5000 + cycle, 'peer_pid': 4999,
             'device': camera.DEVICE, 'journal_monotonic_us': cycle * 100},
            {'event': 'live_frames', 'frames': 1, 'age_ms': 30.2, 'journal_monotonic_us': cycle * 100 + 10},
            {'event': 'physical_camera_closed', 'frames': 9, 'exit': -15, 'journal_monotonic_us': cycle * 100 + 90},
        ])
    return events


def query_runner(directory, stdout=b'', stderr=b''):
    runner = object.__new__(camera.CameraRunner)
    runner.out = Path(directory)
    runner.r = types.SimpleNamespace(commands=[])
    runner.preflight_absent = False
    runner.query_argv = None
    def invoke(label, argv, seconds):
        runner.query_argv = argv
        actual_label = label + '_repeat_2'
        runner.r.commands.append({'label': actual_label, 'returncode': 0})
        (runner.out / (actual_label + '.stderr')).write_bytes(stderr)
        return stdout
    runner.invoke = invoke
    return runner


class CameraColdControls(unittest.TestCase):
    def test_global_absence_uses_known_all_users_and_owned_query_uses_user0(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = query_runner(directory)
            runner.require_absent()
            self.assertTrue(runner.preflight_absent)
            self.assertEqual(runner.query_argv, ['/system/bin/cmd', 'package', 'list', 'packages',
                '-a', '-u', '-U', '--user', 'all', camera.PACKAGE])
            runner.package_rows('owned_user0')
            self.assertEqual(runner.query_argv, ['/system/bin/cmd', 'package', 'list', 'packages',
                '-u', '-U', '--user', '0', camera.PACKAGE])

    def test_zero_exit_with_cross_user_error_cannot_prove_global_absence(self):
        for stderr in (b'Error: java.lang.SecurityException: user 10\n', b'warning\n', b'\n'):
            with self.subTest(stderr=stderr), tempfile.TemporaryDirectory() as directory:
                runner = query_runner(directory, b'', stderr)
                with self.assertRaisesRegex(RuntimeError, 'stderr is not empty'):
                    runner.require_absent()
                self.assertFalse(runner.preflight_absent)

    def test_retained_or_multi_user_target_refuses_global_absence(self):
        for uid_text in ('10032', '10032,1010032'):
            with self.subTest(uid_text=uid_text), tempfile.TemporaryDirectory() as directory:
                stdout = ('package:' + camera.PACKAGE + ' uid:' + uid_text + '\n').encode()
                runner = query_runner(directory, stdout)
                with self.assertRaisesRegex(RuntimeError, 'global known-package registry'):
                    runner.require_absent()
                self.assertFalse(runner.preflight_absent)
        rows = camera.exact_package_lines(('package:' + camera.PACKAGE + ' uid:10032,1010032\n').encode(), all_users=True)
        self.assertEqual(rows[0]['uids'], [10032, 1010032])

    def test_global_query_malformed_stdout_and_owned_multi_uid_refuse(self):
        for stdout in (b'Error: failed to list users\n', ('package:' + camera.PACKAGE + ' uid:10032,\n').encode()):
            with self.subTest(stdout=stdout), tempfile.TemporaryDirectory() as directory:
                runner = query_runner(directory, stdout)
                with self.assertRaisesRegex(RuntimeError, 'unexpected package-manager output'):
                    runner.require_absent()
                self.assertFalse(runner.preflight_absent)
        with tempfile.TemporaryDirectory() as directory:
            runner = query_runner(directory, ('package:' + camera.PACKAGE + ' uid:10032,1010032\n').encode())
            with self.assertRaisesRegex(RuntimeError, 'unexpected package-manager output'):
                runner.package_rows('owned_user0')

    def test_global_query_exact_name_and_owned_single_uid_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = query_runner(directory, ('package:' + camera.PACKAGE + '.other uid:10032,1010032\n').encode())
            runner.require_absent()
            self.assertTrue(runner.preflight_absent)
            runner = query_runner(directory, ('package:' + camera.PACKAGE + ' uid:10032\n').encode())
            self.assertEqual(runner.package_rows('owned_user0'), [{'package': camera.PACKAGE, 'uid': 10032}])

    def test_android_and_physical_two_cycle_fixtures_pass(self):
        self.assertTrue(camera.parse_instrumentation(instrument(android_fixture()))['ok'])
        self.assertEqual(len(camera.physical_cycles(physical_fixture(), 1, 1000)), 2)

    def test_android_only_or_fake_pixel_result_is_insufficient(self):
        self.assertTrue(camera.parse_instrumentation(instrument(android_fixture()))['ok'])
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            camera.physical_cycles([], 1, 1000)
        value = android_fixture()
        value['pixel_files_created'] = 1
        with self.assertRaisesRegex(RuntimeError, 'persisted pixels'):
            camera.parse_instrumentation(instrument(value))

    def test_repeated_timestamp_rejected(self):
        value = android_fixture()
        value['cycles'][1]['samples'][0]['timestamp_ns'] = value['cycles'][0]['samples'][-1]['timestamp_ns']
        with self.assertRaisesRegex(RuntimeError, 'strictly increasing'):
            camera.parse_instrumentation(instrument(value))

    def test_frame_count_and_device_close_required(self):
        value = android_fixture()
        value['cycles'][0]['frames'] = 7
        with self.assertRaisesRegex(RuntimeError, 'frame count'):
            camera.parse_instrumentation(instrument(value))
        value = android_fixture()
        value['cycles'][1]['device_closed'] = False
        with self.assertRaisesRegex(RuntimeError, 'resources did not close'):
            camera.parse_instrumentation(instrument(value))

    def test_physical_device_staleness_and_cleanup_required(self):
        events = physical_fixture()
        events[0]['device'] = '/dev/video-unrelated'
        with self.assertRaisesRegex(RuntimeError, 'identity/sequence'):
            camera.physical_cycles(events, 1, 1000)
        events = physical_fixture()
        events[1]['age_ms'] = 1001
        with self.assertRaisesRegex(RuntimeError, 'frame evidence'):
            camera.physical_cycles(events, 1, 1000)
        events = physical_fixture()
        events[-1]['exit'] = -9
        with self.assertRaisesRegex(RuntimeError, 'retirement'):
            camera.physical_cycles(events, 1, 1000)

    def test_extra_or_missing_physical_cycle_refuses(self):
        events = physical_fixture()
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            camera.physical_cycles(events[:-1], 1, 1000)
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            camera.physical_cycles(events + copy.deepcopy(events[:3]), 1, 1000)

    def test_journal_service_pid_boot_and_invocation_bound(self):
        value = {'_SYSTEMD_INVOCATION_ID': 'a' * 32, '_BOOT_ID': 'b' * 32, '_PID': '4998',
                 '__MONOTONIC_TIMESTAMP': '100', '__CURSOR': 'cursor-1',
                 'MESSAGE': json.dumps(physical_fixture()[0])}
        raw = (json.dumps(value) + '\n').encode()
        self.assertEqual(len(camera.journal_events(raw, 'a' * 32, 4998, 'b' * 32)), 1)
        with self.assertRaisesRegex(RuntimeError, 'another service invocation'):
            camera.journal_events(raw, 'c' * 32, 4998, 'b' * 32)
        with self.assertRaisesRegex(RuntimeError, 'another manager PID'):
            camera.journal_events(raw, 'a' * 32, 4999, 'b' * 32)
        with self.assertRaisesRegex(RuntimeError, 'boot differs'):
            camera.journal_events(raw, 'a' * 32, 4998, 'c' * 32)

    def test_physical_capture_failure_not_treated_as_normal_close(self):
        events = physical_fixture()
        events.append({'event': 'capture_ended', 'reason': 'stale_capture', 'journal_monotonic_us': 300})
        with self.assertRaisesRegex(RuntimeError, 'ended unexpectedly'):
            camera.physical_cycles(events, 1, 1000)

    def test_package_match_is_exact_and_ambiguous_status_refuses(self):
        raw = ('package:' + camera.PACKAGE + '-other uid:10020\n').encode()
        self.assertEqual(camera.exact_package_lines(raw), [])
        raw = ('package:' + camera.PACKAGE + ' uid:10021\n').encode()
        self.assertEqual(camera.exact_package_lines(raw), [{'package': camera.PACKAGE, 'uid': 10021}])
        with self.assertRaisesRegex(RuntimeError, 'unexpected package-manager'):
            camera.exact_package_lines(b'Error: permission denied\n')

    def test_duplicate_instrumentation_results_refuse(self):
        raw = instrument(android_fixture())
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            camera.parse_instrumentation(raw + raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
