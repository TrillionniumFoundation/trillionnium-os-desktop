"""Focused r4 component controls, never a Main or physical-audio qualification.

Retirement tests inject responses at the capture boundary and use the unchanged
business_commands retirement predicate. Their decoder object starts at that
boundary; this does not exercise live Session admission or qualify a reaper.
Synthetic tests execute the runner's real ffprobe/ffmpeg through two inherited
FDs. They do not claim Pocket4 binary identity, UID 1000 or hardware acceptance.
"""
import argparse
import copy
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
COMMAND_PIN = 'cfe92077ebb75db4f7f0fd577fcd7e6d664afd9338128a05435512549ceeb1f3'
RUNS = []
EXPECTED_TESTS = 11


def load(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


commands_path = ROOT / 'tests/fixtures/business_commands.py'
if hashlib.sha256(commands_path.read_bytes()).hexdigest() != COMMAND_PIN:
    raise RuntimeError('EXACT_UNCHANGED_RETIREMENT_PREDICATE_FIXTURE')
commands = load(commands_path, 'camera_r4_fixture_business_commands')
decode = load(SOURCE / 'camera_decode.py', 'camera_r4_decode_under_test')
media = load(SOURCE / 'camera_video_media.py', 'camera_r4_media_under_test')
case = load(SOURCE / 'camera_case.py', 'camera_r4_case_under_test')


class InjectedFailure(RuntimeError):
    pass


class Common:
    """Local test storage only; supplies no live qualification or authority."""
    need = staticmethod(commands.need)
    sha = staticmethod(commands.digest)
    parse = staticmethod(commands.parse)

    def __init__(self, fail=None):
        self.fail = fail

    def write_new(self, path, value, mode=None):
        if self.fail == 'stdout' and str(path).endswith('.stdout'):
            raise OSError(errno.ENOSPC, 'INJECTED_STDOUT_PERSIST')
        return commands.write_new(path, value)

    def read_ref(self, ref):
        raw = Path(ref['path']).read_bytes()
        self.need(len(raw) == ref['bytes'] and self.sha(raw) == ref['sha256'], 'LOCAL_FIXTURE_PIN')
        return raw

    def private_dir(self, path, create=False):
        path = Path(path)
        if create: path.mkdir(mode=0o700)
        return path


class RetirementControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p4-r4-retirement-control-')
        self.root = Path(self.temp.name); self.decoders = []
        self.handlers = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGTERM)}

    def tearDown(self):
        for item in self.decoders:
            fds = [item.decode_fd, item.fd]; item.close()
            for fd in fds:
                if fd is not None:
                    with self.assertRaises(OSError) as caught: os.fstat(fd)
                    self.assertEqual(caught.exception.errno, errno.EBADF)
        self.assertEqual(self.handlers, {n: signal.getsignal(n) for n in self.handlers})
        self.temp.cleanup()

    def fixture(self, *, retired=False, fail=None, missing_output=False, capture_raises=False,
                post_guard=False, forged_true=False):
        # This starts at Decoder.call, not at the live Session constructor.
        d = object.__new__(decode.Decoder); c = Common(fail)
        raw = b'local negative-boundary bytes; not Camera media'
        d.path = self.root / 'owned-camera-video.mp4'; d.path.write_bytes(raw)
        d.fd = os.open(d.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        d.metadata = decode.identity(os.fstat(d.fd))
        d.ref = {'path': str(d.path), 'bytes': len(raw), 'sha256': c.sha(raw)}
        d.decode_fd = os.memfd_create('p4-r4-retirement-control', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        self.assertEqual(os.write(d.decode_fd, raw), len(raw)); os.fchmod(d.decode_fd, 0o444)
        d.seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        fcntl.fcntl(d.decode_fd, fcntl.F_ADD_SEALS, d.seals)
        d.decode_metadata = decode.identity(os.fstat(d.decode_fd))
        d.closed = d.unknown = False; d.done = {}; d.c = c; d.media = media; d.commands = commands
        self.decoders.append(d); calls = {'guards': 0, 'dispatch': 0, 'unknown_at_dispatch': None}

        def guard():
            calls['guards'] += 1
            if post_guard and calls['guards'] == 2: raise InjectedFailure('INJECTED_POST_GUARD')

        def record(label, value):
            if fail == 'result' and label.endswith('-result'):
                raise OSError(errno.ENOSPC, 'INJECTED_RESULT_PERSIST')
            return c.write_new(self.root / (label + '.json'), value)

        d.s = types.SimpleNamespace(c=c, phase_name='business', deadline=time.monotonic() + 15,
            flow=types.SimpleNamespace(scope_ref={'fixture': 'scope'}), phase_ref={'fixture': 'phase'},
            baseline=types.SimpleNamespace(protected_pids=(max(2, os.getpid()),)),
            evidence_root=self.root, guard=guard, record=record)

        class Reaper:
            def __init__(self, **kw): self.record = {'begin_passed': True, 'restored': True, 'final_children_empty': True}
            def begin(self): pass
            def finish(self): pass

        def invoke(*args, **kwargs):
            calls['dispatch'] += 1; calls['unknown_at_dispatch'] = d.unknown
            if capture_raises: raise InjectedFailure('INJECTED_CAPTURE_REPLY_LOST')
            record = {k: True for k in ('child_started', 'child_reaped', 'owned_tree_cleanup_complete',
                'all_acquired_fds_closed', 'retirement_within_deadline')}
            record.update(remaining_owned_children=[], returncode=0, timed_out=False, descendants=[])
            if not retired: record['child_reaped'] = False
            if forged_true: record['child_reaped'] = 1
            return record, None if missing_output else b'fixture output', b'', None

        d.capture = types.SimpleNamespace(OwnChildReaper=Reaper, invoke_owned=invoke)
        return d, calls

    def test_unknown_precedes_dispatch_and_failed_result_persistence(self):
        d, calls = self.fixture(fail='result')
        with self.assertRaisesRegex(OSError, 'INJECTED_RESULT_PERSIST'): d.call('probe')
        self.assertIs(calls['unknown_at_dispatch'], True); self.assertIs(d.unknown, True)
        with self.assertRaisesRegex(RuntimeError, '^ONCE_FIXED_FULL_CLIP_DECODE$'): d.call('audio')
        self.assertEqual(calls['dispatch'], 1)

    def test_unknown_survives_failed_stdout_persistence(self):
        d, calls = self.fixture(fail='stdout')
        with self.assertRaisesRegex(OSError, 'INJECTED_STDOUT_PERSIST'): d.call('probe')
        self.assertIs(d.unknown, True); self.assertIs(calls['unknown_at_dispatch'], True)

    def test_capture_primary_error_survives_later_evidence_error(self):
        d, calls = self.fixture(capture_raises=True, fail='result')
        with self.assertRaisesRegex(InjectedFailure, '^INJECTED_CAPTURE_REPLY_LOST$') as caught: d.call('probe')
        self.assertIs(d.unknown, True); self.assertIs(calls['unknown_at_dispatch'], True)
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertTrue(any('DECODER_EVIDENCE_FAILURE' in n for n in caught.exception.__notes__))

    def test_proved_retirement_is_not_falsified_by_evidence_failure(self):
        d, calls = self.fixture(retired=True, fail='stdout')
        with self.assertRaisesRegex(OSError, 'INJECTED_STDOUT_PERSIST'): d.call('probe')
        self.assertIs(calls['unknown_at_dispatch'], True); self.assertIs(d.unknown, False)

    def test_missing_output_remains_unknown_after_proved_retirement(self):
        d, _ = self.fixture(retired=True, missing_output=True)
        with self.assertRaisesRegex(decode.DecodeOutcomeUnknown, '^OWNED_DECODER_RETIREMENT_OR_OUTPUT_UNKNOWN$'):
            d.call('probe')
        self.assertIs(d.unknown, True)

    def test_numeric_one_cannot_supply_a_retirement_boolean(self):
        d, _ = self.fixture(retired=True, forged_true=True)
        with self.assertRaisesRegex(decode.DecodeOutcomeUnknown, '^OWNED_DECODER_RETIREMENT_OR_OUTPUT_UNKNOWN$'):
            d.call('probe')
        self.assertIs(d.unknown, True)

    def test_post_guard_primary_error_survives_later_evidence_error(self):
        d, _ = self.fixture(retired=True, post_guard=True, fail='result')
        with self.assertRaisesRegex(InjectedFailure, '^INJECTED_POST_GUARD$') as caught: d.call('probe')
        self.assertIs(d.unknown, False); self.assertIsInstance(caught.exception.__cause__, OSError)

    def test_case_propagates_latched_unknown_before_cleanup(self):
        # Pure orchestration harness. All admission/Main operations below are
        # explicit inert fixtures; only the production case exception path runs.
        c = Common(); root = self.root / 'case'; root.mkdir()
        base = {'support_manifest': {}, 'baseline': {}, 'qualification': {},
            'case_root': str(root), 'source_preparation': {'fixture': 'source'}}
        base_ref = c.write_new(root / 'fixture-base.json', base)
        active_ref = c.write_new(root / 'fixture-active.json', {})
        baseline = types.SimpleNamespace(guard=lambda: {'fixture': 'unchanged'})
        c.support = lambda ref: (None, {'business_baseline.py': types.SimpleNamespace(BusinessBaseline=lambda *a: baseline)})

        class Context:
            ref = {'fixture': 'context'}
            def __init__(self, *a): pass
            def close(self): pass

        class Session(Context):
            def begin_cleanup(self, ref): return {'fixture': 'cleanup-phase'}

        class Driver:
            def __init__(self, session, result):
                self.decoder = types.SimpleNamespace(unknown=True)
                self.host_unknown = self.run_completed = self.cleanup_verified = False
                self.pending = self.close_pending = self.owned = self.recording = None
                self.launches = []; self.closes = []
            def run(self): raise InjectedFailure('INJECTED_DIAGNOSTIC_ERROR_AFTER_UNKNOWN')
            def finish(self):
                if self.host_unknown is not True: raise InjectedFailure('UNKNOWN_NOT_SET_BEFORE_CLEANUP')
            def close_local(self): pass

        acoustic = types.SimpleNamespace(pending=None, parent_ref={}, results={}, verify=lambda: None,
            attach=lambda s: None, close=lambda: None)
        c.EvidenceWitness = Context
        components = {'camera_plan.py': types.SimpleNamespace(validate=lambda *a: None,
                activate=lambda *a: (active_ref, [])),
            'camera_runtime.py': types.SimpleNamespace(ActionLock=Context, create_lease=lambda *a: {}, phase=lambda *a: {}),
            'app_runtime.py': types.SimpleNamespace(process=lambda *a: {'fixture': 'process'}),
            'camera_session.py': types.SimpleNamespace(make_session=lambda base: Session),
            'camera_base_session.py': None, 'camera_video_driver.py': types.SimpleNamespace(Driver=Driver),
            'camera_decode.py': decode}
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        try:
            with mock.patch.object(case.os, 'getuid', return_value=0), mock.patch.object(case.os, 'geteuid', return_value=0):
                _, result = case.execute(c, base_ref, components, acoustic)
        finally:
            for number, handler in self.handlers.items(): signal.signal(number, handler)
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        self.assertIs(result['outcome_unknown'], True)
        self.assertEqual(result['secondary_errors'], [])
        self.assertEqual(result['error']['message'], 'INJECTED_DIAGNOSTIC_ERROR_AFTER_UNKNOWN')
        self.assertIs(result['case_business_success_verified'], False)
        self.assertIs(result['whole_app_business_accepted'], False)


def run(argv, *, pass_fds=(), executable=None, expect_success=True):
    value = subprocess.run(argv, executable=executable, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, close_fds=True,
        pass_fds=pass_fds, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    RUNS.append({'argv': argv, 'executable': executable, 'inherited_fd_count': len(pass_fds),
        'returncode': value.returncode, 'stdout_bytes': len(value.stdout),
        'stdout_sha256': hashlib.sha256(value.stdout).hexdigest(), 'stderr_bytes': len(value.stderr),
        'stderr_sha256': hashlib.sha256(value.stderr).hexdigest(), 'synthetic_runner_only': True})
    if len(value.stdout) > 2016000 or len(value.stderr) > 1048576:
        raise RuntimeError('SYNTHETIC_CONTROL_OUTPUT_BOUND')
    if expect_success and (value.returncode or value.stderr):
        raise RuntimeError('SYNTHETIC_HOST_COMMAND_FAILED:' + value.stderr.decode('utf-8', 'replace')[:300])
    return value


class MediaControls(unittest.TestCase):
    def test_probe_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for raw, message in ((b'{"streams":[],"streams":[]}', 'DUPLICATE_PROBE_JSON_FIELD'),
                (b'{"n":NaN}', 'NONFINITE_PROBE_JSON_NUMBER'),
                (b'{"n":Infinity}', 'NONFINITE_PROBE_JSON_NUMBER')):
            with self.subTest(raw=raw), self.assertRaisesRegex(RuntimeError, '^' + message + '$'):
                media.parse_probe(raw, {})

    def test_actual_two_fd_mov_probe_video_and_pcm(self):
        with tempfile.TemporaryDirectory(prefix='p4-r4-synthetic-media-') as tmp:
            path = Path(tmp) / 'synthetic.mp4'
            run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                'color=c=blue:s=32x32:r=5:d=2', '-f', 'lavfi', '-i', 'sine=frequency=800:sample_rate=48000:duration=2',
                '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-movflags', '+faststart', str(path)])
            raw = path.read_bytes(); fd = os.memfd_create('p4-r4-synthetic-media', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            try:
                self.assertEqual(os.write(fd, raw), len(raw)); os.fchmod(fd, 0o444)
                seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
                fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals); before = decode.identity(os.fstat(fd)); outputs = {}
                for kind in ('probe', 'video', 'audio'):
                    argv = media.decoder_argv(kind, '/proc/self/fd/' + str(fd))
                    self.assertEqual(argv[argv.index('-i') - 2:argv.index('-i')], ['-f', 'mov'])
                    tool = os.open(argv[0], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
                    try:
                        outputs[kind] = run(argv, executable='/proc/self/fd/' + str(tool), pass_fds=(fd, tool)).stdout
                    finally: os.close(tool)
                    self.assertEqual(decode.identity(os.fstat(fd)), before)
                    self.assertEqual(fcntl.fcntl(fd, fcntl.F_GET_SEALS), seals)
                    self.assertFalse(os.get_inheritable(fd)); self.assertEqual(os.pread(fd, len(raw), 0), raw)
                row = {'width': 32, 'height': 32, 'duration': 2000, '_size': len(raw)}
                probe = media.parse_probe(outputs['probe'], row)
                self.assertEqual(media.parse_framemd5(outputs['video'], probe['frame_count'])['count'], 10)
                self.assertLessEqual(abs(len(outputs['audio']) / 96000 - 2), .25)
            finally: os.close(fd)

    def test_actual_non_mov_input_is_rejected(self):
        fd = os.memfd_create('p4-r4-not-mov', os.MFD_CLOEXEC)
        try:
            os.write(fd, b'ffconcat version 1.0\nfile /an/unowned/path.mp4\n')
            value = run(media.decoder_argv('probe', '/proc/self/fd/' + str(fd)), pass_fds=(fd,), expect_success=False)
            self.assertNotEqual(value.returncode, 0)
            self.assertTrue(value.stderr); self.assertNotIn(b'/an/unowned/path', value.stderr)
        finally: os.close(fd)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--report', required=True)
    args = parser.parse_args(); suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() != EXPECTED_TESTS: raise RuntimeError('EXACT_R4_CONTROL_COUNT')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    refs = []
    for path in sorted(SOURCE.glob('*.py')):
        raw = path.read_bytes(); refs.append({'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    report = {'schema': 'pocket4-camera-r4-decoder-component-controls-v1', 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'failed_tests': [str(test) for test, _ in result.failures + result.errors],
        'passed': result.wasSuccessful(), 'source_files': refs, 'real_host_commands': RUNS,
        'retirement_faults_are_unit_fixtures': True, 'Main_actions': 0, 'Android_actions': 0,
        'physical_audio_actions': 0, 'live_session_admission_qualified': False,
        'actual_reaper_qualified': False, 'Pocket4_binary_qualified': False,
        'runtime_qualified': False, 'whole_app_business_accepted': False}
    report['runner_tools'] = [{'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for path in (Path('/usr/bin/ffmpeg'), Path('/usr/bin/ffprobe'), Path(sys.executable).resolve())
        if path.is_file() for raw in (path.read_bytes(),)]
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
