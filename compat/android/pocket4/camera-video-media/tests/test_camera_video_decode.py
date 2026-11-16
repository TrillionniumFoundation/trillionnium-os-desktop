"""Mandatory Linux synthetic controls; no Main/Session/device is created.

Run with /usr/bin/python3 -B. Missing Linux/proc/ffmpeg is a gate failure,
never a successful skip. Output is CI-runner evidence, not Pocket4 proof.
"""
import argparse
import copy
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
RUNS = []
NONCE = '0000000000000047'
EXPECTED_TESTS = 15


def load(name):
    spec = importlib.util.spec_from_file_location('camera_hostcontrol_' + name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


media = load('camera_video_media')
decode = load('camera_video_decode')
state = load('camera_video_state')
challenge = load('camera_audio_challenge')


def command(argv, bound=1048576):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, close_fds=True, pass_fds=(), timeout=15,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    RUNS.append({'argv': argv, 'returncode': result.returncode,
        'stdout_bytes': len(result.stdout), 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
        'stderr_bytes': len(result.stderr), 'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
        'inherited_fds': 0, 'local_synthetic_only': True})
    if result.returncode != 0 or result.stderr or len(result.stdout) > bound:
        raise RuntimeError('LOCAL_SYNTHETIC_CHILD_FAILED:' + result.stderr.decode('utf-8', 'replace')[:600])
    return result.stdout


class LocalOwnedFile:
    """A test file under TemporaryDirectory, never an Android target."""
    def __init__(self, path):
        self.path = str(path)

    def open_root(self, path, flags):
        if path != self.path or flags != os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC:
            raise RuntimeError('ONLY_THE_LOCAL_SYNTHETIC_FILE')
        return os.open(path, flags)


class DecoderHostControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='p4-camera-video-hostcontrol-')
        cls.root = Path(cls.temp.name)
        pcm = challenge.waveform(NONCE)
        pcm += bytes(4 * 48000 * 4 - len(pcm))
        raw = cls.root / 'synthetic-challenge.s16le'; raw.write_bytes(pcm)
        cls.video = cls.root / 'synthetic-owned.mp4'
        command(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=blue:s=32x32:r=5:d=4', '-f', 's16le', '-ar', '48000', '-ac', '2', '-i', str(raw),
            '-t', '4', '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(cls.video)])
        cls.fixture_sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def row(self, path=None):
        path = Path(path or self.video)
        return {'_id': 73, '_data': str(path), '_size': path.stat().st_size, 'width': 32,
            'height': 32, 'duration': 4000, 'mime_type': 'video/mp4', 'is_pending': 0,
            'owner_package_name': 'com.android.camera2', 'uri': media.URI + '/73'}

    def clip(self, path=None):
        row = self.row(path)
        return decode.SealedClip(LocalOwnedFile(row['_data']), row, NONCE, time.monotonic() + 30)

    def executor(self, clip, *, alter=None, expire_after_probe=False, calls=None):
        def execute(kind, argv, bound):
            clip.verify()
            self.assertEqual(argv, media.decoder_argv(kind, clip.path))
            self.assertIn('/proc/' + str(os.getpid()) + '/fd/', clip.path)
            if calls is not None:
                calls.append(kind)
            raw = command(argv, bound)
            clip.verify()
            if expire_after_probe and kind == 'probe':
                clip.deadline = time.monotonic() - 1
            return alter(kind, raw) if alter else raw
        return execute

    def test_complete_real_host_decode_and_nonce_match(self):
        before = len(os.listdir('/proc/self/fd')); calls = []
        with self.clip() as clip:
            value, pcm = decode._decode_outputs(media, clip, self.row(), self.executor(clip, calls=calls))
            self.assertEqual(calls, ['probe', 'video', 'audio'])
            self.assertEqual(value['video']['count'], 20)
            self.assertEqual(value['probe']['frame_count'], 20)
            self.assertLessEqual(abs(value['audio']['duration_seconds'] - 4), .25)
            positive = challenge.analyze(pcm, NONCE, tone_window_ms=[1500, 1650],
                baseline_end_ms=1300, deadline=time.monotonic() + 10)
            negative = challenge.analyze(pcm, '0000000000000048', tone_window_ms=[1500, 1650],
                baseline_end_ms=1300, deadline=time.monotonic() + 10)
            self.assertTrue(positive['matched']); self.assertFalse(negative['matched'])
            self.assertFalse(positive['Android_HAL_or_physical_source_qualification'])
            self.assertFalse(positive['whole_app_business_accepted'])
            self.assertEqual(clip.sha256, self.fixture_sha)
        self.assertTrue(clip.closed)
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def test_zero_inherited_fds_reads_same_controller_memfd(self):
        with self.clip() as clip:
            program = ('import hashlib,json,os,sys\n'
                'try: os.fstat(int(sys.argv[2])); inherited=True\n'
                'except OSError: inherited=False\n'
                'with open(sys.argv[1],"rb") as f: raw=f.read()\n'
                'print(json.dumps({"inherited":inherited,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}))')
            value = json.loads(command(['/usr/bin/python3', '-I', '-c', program, clip.path, str(clip.fd)]))
            self.assertFalse(value['inherited'])
            self.assertEqual((value['bytes'], value['sha256']), (clip.bytes, clip.sha256))
            self.assertFalse(os.get_inheritable(clip.fd))

    def test_all_seals_and_readonly_view_reject_writes_and_resizes(self):
        with self.clip() as clip:
            original = dict(clip.memfd_identity)

            def assert_sealed_content_and_guard():
                current = decode.identity(os.fstat(clip.fd))
                changed = {key for key in original if current[key] != original[key]}
                # Linux can update these timestamps before a sealed write is
                # rejected. No other metadata/content change is acceptable.
                self.assertLessEqual(changed, {'st_mtime_ns', 'st_ctime_ns'})
                self.assertEqual(current, decode.identity(os.stat(clip.path)))
                self.assertEqual(clip.memfd_identity, original)  # Never rebase production identity.
                self.assertEqual(os.readlink(clip.path), clip.label)
                self.assertEqual(fcntl.fcntl(clip.fd, fcntl.F_GET_SEALS), decode.SEALS)
                self.assertEqual(fcntl.fcntl(clip.fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
                self.assertFalse(os.get_inheritable(clip.fd))
                raw = os.pread(clip.fd, clip.bytes + 1, 0)
                self.assertEqual(len(raw), clip.bytes)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), clip.sha256)
                self.assertEqual(decode.identity(os.fstat(clip.source_fd)), clip.source_identity)
                clip.verify_named_source()
                self.assertLess(time.monotonic(), clip.deadline)
                if changed:
                    with self.assertRaisesRegex(RuntimeError, '^SAME_READONLY_SEALED_VIDEO_AND_HELD_ORIGINAL$'):
                        clip.verify()
                else:
                    clip.verify()
                return current, sorted(changed)

            def denied(name, operation, expected_errno):
                before = decode.identity(os.fstat(clip.fd))
                with self.assertRaises(OSError) as raised:
                    operation()
                self.assertEqual(raised.exception.errno, expected_errno)
                after, changed = assert_sealed_content_and_guard()
                RUNS.append({'kind': 'sealed_memfd_denied_operation', 'operation': name,
                    'errno': raised.exception.errno, 'before': before, 'after': after,
                    'metadata_changed_since_original': changed, 'unchanged_bytes': clip.bytes,
                    'unchanged_sha256': clip.sha256, 'seals': decode.SEALS,
                    'strict_guard_rejected_changed_identity': bool(changed), 'local_synthetic_only': True})

            assert_sealed_content_and_guard()
            denied('write_readonly', lambda: os.write(clip.fd, b'x'), errno.EBADF)
            writable_view = os.open(clip.path, os.O_RDWR | os.O_CLOEXEC)
            try:
                denied('shrink_sealed', lambda: os.ftruncate(writable_view, clip.bytes - 1), errno.EPERM)
                denied('grow_sealed', lambda: os.ftruncate(writable_view, clip.bytes + 1), errno.EPERM)
                denied('write_sealed', lambda: os.write(writable_view, b'x'), errno.EPERM)
            finally:
                os.close(writable_view)
            assert_sealed_content_and_guard()
        self.assertTrue(clip.closed)

    def test_foreign_pid_and_self_route_cannot_replace_production_path(self):
        with self.clip() as clip:
            with self.assertRaises(RuntimeError):
                media.decoder_argv('probe', '/proc/' + str(os.getpid() + 1) + '/fd/' + str(clip.fd))
            clip.path = '/proc/self/fd/' + str(clip.fd)
            with self.assertRaises(RuntimeError):
                clip.verify()

    def test_reused_descriptor_is_rejected_and_foreign_fd_is_not_closed(self):
        clip = self.clip(); old = clip.fd; os.close(old)
        foreign = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)
        if foreign != old:
            os.dup2(foreign, old, inheritable=False); os.close(foreign)
        try:
            with self.assertRaises(RuntimeError):
                clip.verify()
            with self.assertRaises(RuntimeError):
                clip.close()
            self.assertTrue(stat.S_ISCHR(os.fstat(old).st_mode))
            self.assertFalse(clip.closed)
        finally:
            os.close(old)

    def test_changed_or_replaced_source_is_rejected(self):
        path = self.root / 'changed.mp4'; shutil.copyfile(self.video, path)
        with self.clip(path) as clip:
            replacement = self.root / 'replacement.mp4'; shutil.copyfile(self.video, replacement)
            os.replace(replacement, path)
            with self.assertRaises(RuntimeError):
                clip.verify_named_source()
            with self.assertRaises(RuntimeError):
                clip.verify()

    def test_expired_phase_stops_before_second_command(self):
        calls = []
        with self.clip() as clip:
            with self.assertRaises(RuntimeError):
                decode._decode_outputs(media, clip, self.row(),
                    self.executor(clip, expire_after_probe=True, calls=calls))
        self.assertEqual(calls, ['probe']); self.assertTrue(clip.closed)

    def test_truncated_owned_mp4_never_completes_decode(self):
        path = self.root / 'truncated.mp4'; raw = self.video.read_bytes(); path.write_bytes(raw[:len(raw) // 2])
        with self.clip(path) as clip:
            with self.assertRaises(RuntimeError):
                decode._decode_outputs(media, clip, self.row(path), self.executor(clip))
        self.assertTrue(clip.closed)

    def test_missing_decoded_frame_is_rejected(self):
        def alter(kind, raw):
            if kind != 'video':
                return raw
            lines = raw.splitlines(True)
            last = max(i for i, line in enumerate(lines) if line.strip() and not line.startswith(b'#'))
            return b''.join(lines[:last] + lines[last + 1:])
        with self.clip() as clip:
            with self.assertRaises(RuntimeError):
                decode._decode_outputs(media, clip, self.row(), self.executor(clip, alter=alter))

    def test_short_pcm_and_odd_pcm_are_rejected(self):
        for change in [lambda raw: raw[:len(raw) // 2 // 2 * 2], lambda raw: raw[:-1]]:
            with self.subTest(change=change):
                with self.clip() as clip:
                    with self.assertRaises(RuntimeError):
                        decode._decode_outputs(media, clip, self.row(), self.executor(clip,
                            alter=lambda kind, raw: change(raw) if kind == 'audio' else raw))

    def test_unknown_child_retains_exact_fd_until_actual_child_exit(self):
        clip = self.clip(); held_fd = clip.fd; child = None
        program = ('import hashlib,json,os,sys\n'
            'sys.stdin.buffer.read(1)\n'
            'with open(sys.argv[1],"rb") as f: raw=f.read()\n'
            'print(json.dumps({"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}))')
        try:
            child = subprocess.Popen(['/usr/bin/python3', '-I', '-c', program, clip.path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                close_fds=True, pass_fds=(), env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            clip.retirement_unproved = True
            with self.assertRaisesRegex(RuntimeError, 'INJECTED_UNKNOWN_WITH_REAL_WAITING_CHILD'):
                with clip:
                    raise RuntimeError('INJECTED_UNKNOWN_WITH_REAL_WAITING_CHILD')
            self.assertIsNone(child.poll()); self.assertFalse(clip.closed)
            self.assertEqual(clip.fd, held_fd)
            with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_CHILD_RETAINS_ITS_EXACT_VIDEO_FD'):
                clip.close()
            unrelated = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)
            try:
                self.assertNotEqual(unrelated, held_fd)
                stdout, stderr = child.communicate(b'G', timeout=10)
            finally:
                os.close(unrelated)
            self.assertEqual(child.returncode, 0); self.assertEqual(stderr, b'')
            self.assertEqual(json.loads(stdout), {'bytes': clip.bytes, 'sha256': clip.sha256})
            RUNS.append({'kind': 'actual_delayed_reader_after_injected_unknown', 'returncode': child.returncode,
                'stdout_bytes': len(stdout), 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                'stderr_bytes': 0, 'inherited_fds': 0, 'actual_child_reaped_before_close': True,
                'local_synthetic_only': True})
            # This is explicit local test reconciliation of our actual child.
            # Production only clears the flag from its admitted recorder.
            clip.retirement_unproved = False; clip.close()
            self.assertTrue(clip.closed)
            with self.assertRaises(OSError):
                os.fstat(held_fd)
        finally:
            if child is not None:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)
            clip.retirement_unproved = False
            clip.close()


class PureControls(unittest.TestCase):
    def test_probe_duplicate_json_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_PROBE_JSON_FIELD'):
            media.parse_probe(b'{"streams":[],"streams":[],"format":{}}', {})

    def test_photo_session_is_rejected_before_io(self):
        photo = types.SimpleNamespace(kind='camera_photo', active={'kind': 'camera_photo'})
        with mock.patch.object(decode, 'SealedClip') as factory:
            with self.assertRaisesRegex(RuntimeError, 'ACTUAL_VIDEO_SESSION_REQUIRED'):
                decode.decode_owned(photo, object())
            factory.assert_not_called()

    def test_no_success_dictionary_api_and_unknown_decode_cannot_qualify(self):
        self.assertFalse(hasattr(state.Recording, 'saved'))
        reference = {'path': '/hostcontrol/inert', 'bytes': 1, 'sha256': 'a' * 64}
        recording = state.Recording(nonce=NONCE, scope=reference, phase=reference,
            epoch_sha256='b' * 64, task=7, emit=lambda *_: reference)
        recording.initial_mode = '1'; recording.state = 'PLAYBACK_VERIFIED'
        recording.media = recording.audio = recording.playback = reference
        recording.decode_outcome_unknown = True
        result = recording.terminal(final_mode='1', task_closed=True, preserved_state=True, host_retired=True)
        self.assertFalse(result['camera_video_verified']); self.assertTrue(result['outcome_unknown'])

    def test_hold_seals_known_failure_and_poison_survives_missing_receipt(self):
        # Negative fault injection at the fence only. No real/fake Session is
        # admitted and no production command is executed by these doubles.
        class Bridge:
            pass

        class Target:
            def __init__(self, events, fail):
                self.events, self.fail = events, fail

            def poison_unjoined_command(self):
                self.events.append('poison')
                if self.fail:
                    raise OSError('INJECTED_ADMISSION_FENCE_FAILURE')

            def seal_admission(self):
                self.events.append('seal')

        for unknown, fence_error, wrapped in [(False, False, False), (False, False, True),
                                              (True, False, True), (True, True, True)]:
            with self.subTest(unknown=unknown, fence_error=fence_error, wrapped=wrapped):
                events = []; error = RuntimeError('FIRST_FAILURE'); original_observation = {'marker': 'original'}
                if not unknown:
                    error.command_observation = original_observation
                binding = types.SimpleNamespace(poisoned=False, hold=lambda err: events.append(err))
                real = Bridge(); real.closed = False
                flow = types.SimpleNamespace(bound=binding, bridge=types.SimpleNamespace(real=real) if wrapped else real,
                    scope_module=types.SimpleNamespace(RecorderBridge=Bridge),
                    view=types.SimpleNamespace(target=Target(events, fence_error)))
                real.flow = flow; real.binding = binding
                decode._hold(types.SimpleNamespace(flow=flow),
                    types.SimpleNamespace(decode_outcome_unknown=unknown), error)
                self.assertTrue(binding.poisoned); self.assertTrue(real.closed)
                if wrapped:
                    self.assertNotIn('closed', vars(flow.bridge))  # Close the real wrapped bridge.
                self.assertEqual(events, ['poison' if unknown else 'seal', error])
                if not unknown:
                    self.assertIs(error.command_observation, original_observation)
                else:
                    self.assertFalse(hasattr(error, 'command_observation'))
        argv = ['/usr/bin/ffprobe', 'fixed-input']
        actual = {'schema': 'pocket4-business-host-result-v1', 'name': 'decode-probe',
            'argv': argv, 'host_retirement_proved': True}
        self.assertTrue(decode._retired(actual, 'decode-probe', argv))
        for wrong in [None, {}, {**actual, 'schema': 'different-receipt'}, {**actual, 'name': 'previous-command'},
                      {**actual, 'argv': ['different-input']}, {**actual, 'host_retirement_proved': False}]:
            self.assertFalse(decode._retired(wrong, 'decode-probe', argv))


def environment_refs():
    required = ('F_SEAL_WRITE', 'F_SEAL_GROW', 'F_SEAL_SHRINK', 'F_SEAL_SEAL', 'F_ADD_SEALS', 'F_GET_SEALS')
    missing = [name for name in required if not hasattr(fcntl, name)]
    proc = '/proc/' + str(os.getpid()) + '/fd'
    if not sys.platform.startswith('linux') or not hasattr(os, 'memfd_create'):
        missing.append('Linux_memfd_create')
    if not Path(proc).is_dir():
        missing.append('exact_getpid_proc_fd_directory')
    tools = []
    for name in ('ffmpeg', 'ffprobe'):
        path = Path('/usr/bin') / name
        if not path.is_file() or not os.access(path, os.X_OK):
            missing.append(str(path)); continue
        tools.append({'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'platform': sys.platform, 'python': sys.executable, 'pid': os.getpid(),
        'exact_proc_fd_directory': proc, 'requirements_missing': missing, 'tools': tools,
        'tool_refs_apply_to_this_CI_runner_only': True, 'Pocket4_tool_qualification': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    options = parser.parse_args(); environment = environment_refs()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        for cls in (DecoderHostControls, PureControls))
    if suite.countTestCases() != EXPECTED_TESTS:
        raise RuntimeError('ALL_ORIGINAL_AND_UNKNOWN_HOLD_CONTROLS_REQUIRED')
    result = None
    if not environment['requirements_missing']:
        result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    else:
        print('BLOCKED: required Linux controls cannot run: ' + ', '.join(environment['requirements_missing']))
    sources = [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size,
        'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(SOURCE.glob('*.py'))]
    passed = result is not None and result.wasSuccessful() and result.testsRun == EXPECTED_TESTS and not result.skipped
    report = {'schema': 'pocket4-camera-video-linux-synthetic-component-controls-v1',
        'passed': passed, 'status': ('passed' if passed else 'failed') if result is not None else 'environment_blocked',
        'required_tests': EXPECTED_TESTS, 'tests': 0 if result is None else result.testsRun,
        'failures': 0 if result is None else len(result.failures), 'errors': 0 if result is None else len(result.errors),
        'skipped': 0 if result is None else len(result.skipped),
        'sources': sources, 'environment': environment, 'commands': RUNS, 'production_Session_instances': 0,
        'Main_actions': 0, 'Android_actions': 0, 'real_audio_calls': 0,
        'synthetic_media_only': True, 'runtime_qualified': False,
        'camera_video_verified': False, 'code_entrypoints_complete': False}
    options.report.parent.mkdir(parents=True, exist_ok=True)
    options.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    raise SystemExit(0 if passed else 1)
