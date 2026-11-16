#!/usr/bin/python3
"""Offline source controls; fixture media is not Android/runtime evidence.

Run as root on Pocket4 to exercise the production uid-1000 decoder factory,
fixed bounded capture and original owned-child reaper. Opens no sound device,
camera, Main, or Android transport. Only synthetic media under --work is used.
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
import stat
import subprocess
import sys
import time
import types
import unittest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate', required=True)
parser.add_argument('--original', required=True)
parser.add_argument('--work', required=True)
args = parser.parse_args()
CANDIDATE, ORIGINAL, WORK = map(Path, (args.candidate, args.original, args.work))
if os.getuid() != 0: raise SystemExit('actual root-to-uid1000 controls require root')
if WORK.exists(): raise SystemExit('fresh controls work directory required')
WORK.mkdir(mode=0o700)
os.sched_setaffinity(0, {max(os.sched_getaffinity(0))})

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

c = load(CANDIDATE / 'app_common.py', 'decoder_controls_common')
media = load(CANDIDATE / 'camera_video_media.py', 'decoder_controls_media')
challenge = load(CANDIDATE / 'camera_audio_challenge.py', 'decoder_controls_challenge')
fixed = load(CANDIDATE / 'camera_decode.py', 'decoder_controls_fixed')
original = load(ORIGINAL / 'camera_decode.py', 'decoder_controls_original')
commands_ref = {'path': '/home/alex/work/pocket4-android-final/qualification/business-support-frozen-resume-20261107-r9/business_commands.py',
    'bytes': 12813, 'sha256': 'cfe92077ebb75db4f7f0fd577fcd7e6d664afd9338128a05435512549ceeb1f3'}
commands = c.module(commands_ref, 'decoder_controls_original_commands')
NONCE = '6acfa31412672d51'
REPORT = {'scope': 'synthetic-media-source-host-controls-only', 'Main_actions': 0,
    'Android_UI_actions': 0, 'physical_audio_stream_actions': 0, 'camera_actions': 0,
    'runtime_qualified': False, 'whole_app_business_accepted': False, 'cases': {},
    'capture': fixed.CAPTURE, 'commands': commands_ref,
    'original_decoder': c.regular(ORIGINAL / 'camera_decode.py', contents=False),
    'candidate_decoder': c.regular(CANDIDATE / 'camera_decode.py', contents=False)}

def fds():
    observed = {}
    for path in Path('/proc/self/fd').iterdir():
        try: observed[int(path.name)] = os.readlink(path)
        except FileNotFoundError: pass
    return observed

def identity(path):
    return fixed.identity(path.stat())

class HostFixtureSession:
    def __init__(self, root, raw, nonce=NONCE):
        root.mkdir(mode=0o700)
        self.c = c
        self.active = {'case_root': str(root), 'audio_nonce': nonce, 'framework_epoch_sha256': 'a' * 64}
        self.evidence_root = root / 'evidence'; self.evidence_root.mkdir(mode=0o700)
        self.phase_name = 'business'; self.deadline = time.monotonic() + 40
        self.components = {'camera_video_media.py': media, 'camera_audio_challenge.py': challenge}
        scope = c.write_new(root / 'host-fixture-scope.json', {'fixture_only': True, 'runtime_qualified': False})
        self.phase_ref = c.write_new(root / 'host-fixture-phase.json', {'fixture_only': True, 'runtime_qualified': False})
        self.flow = types.SimpleNamespace(scope_ref=scope, modules={'business_commands.py': commands})
        self.baseline = types.SimpleNamespace(protected_pids=(os.getpid(), os.getppid()))
        self.clip_ref = c.write_new(self.evidence_root / 'owned-camera-video.mp4', raw, 0o400)
        self.owned_video = {'uri': 'content://media/external_primary/video/media/1', 'is_pending': 0,
            '_size': len(raw), 'file_sha256': c.sha(raw), 'width': 64, 'height': 48, 'duration': 4000}
        self.events = []; self.sequence = 0

    def guard(self):
        c.need(time.monotonic() < self.deadline, 'HOST_FIXTURE_PHASE_EXPIRED')

    def record(self, label, value):
        self.sequence += 1
        ref = c.write_new(self.evidence_root / ('%03d-%s.json' % (self.sequence, label)), value)
        self.events.append((label, copy.deepcopy(value), ref))
        return ref

class DecoderHostControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pcm = challenge.waveform(NONCE)
        pcm += bytes(48000 * 2 * 2 * 4 - len(pcm))
        raw_pcm = WORK / 'synthetic-tone.s16le'; raw_pcm.write_bytes(pcm); raw_pcm.chmod(0o400)
        fixture = WORK / 'synthetic-video.mp4'
        argv = ['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-xerror',
            '-f', 'lavfi', '-i', 'testsrc2=size=64x48:rate=10:duration=4',
            '-f', 's16le', '-ar', '48000', '-ac', '2', '-i', str(raw_pcm),
            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'mpeg4', '-q:v', '4',
            '-c:a', 'aac', '-b:a', '128k', '-threads', '1', '-shortest', '-movflags', '+faststart', str(fixture)]
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, start_new_session=True)
        if result.returncode != 0: raise RuntimeError('SYNTHETIC_FIXTURE_GENERATION_FAILED:' + result.stderr.decode())
        cls.raw = fixture.read_bytes(); fixture.chmod(0o400)
        REPORT['fixture'] = {'source': 'locally generated lavfi video and finite synthetic nonce waveform',
            'sha256': c.sha(cls.raw), 'bytes': len(cls.raw), 'duration_ms': 4000,
            'microphone_recording': False, 'Android_MediaStore_row': False}

    def session(self, raw=None, nonce=NONCE):
        return HostFixtureSession(WORK / self._testMethodName, self.raw if raw is None else raw, nonce)

    def assert_retired(self, decoder, kinds):
        for kind in kinds:
            result = decoder.done[kind]['result']
            self.assertTrue(result['host_retirement_proved'])
            self.assertTrue(result['lifecycle']['all_acquired_fds_closed'])
            self.assertTrue(result['lifecycle']['child_reaped'])
            self.assertTrue(result['lifecycle']['owned_tree_cleanup_complete'])
            self.assertEqual(result['lifecycle']['remaining_owned_children'], [])
            self.assertEqual(result['lifecycle']['descendants'], [])
            self.assertEqual(result['cancellation']['count'], 0)

    def test_original_root0400_probe_fails_with_eacces(self):
        s = self.session(); before = fds(); d = original.Decoder(s, s.clip_ref, s.owned_video)
        try:
            self.assertEqual((Path(s.clip_ref['path']).stat().st_uid, stat.S_IMODE(Path(s.clip_ref['path']).stat().st_mode)), (0, 0o400))
            with self.assertRaisesRegex(RuntimeError, 'FULL_OWNED_CLIP_DECODE_MUST_COMPLETE_CLEANLY'):
                d.call('probe')
            result = d.done['probe']['result']
            self.assertNotEqual(result['returncode'], 0)
            stderr = c.read_ref(result['stderr']['reference'])
            self.assertIn(b'Permission denied', stderr)
            self.assert_retired(d, ['probe'])
            REPORT['cases'][self._testMethodName] = {'returncode': result['returncode'],
                'permission_denied_observed': True, 'host_retired': True, 'result': d.done['probe']['reference']}
        finally: d.close()
        self.assertEqual(fds(), before)

    def test_full_decode_same_bytes_sealed_and_no_fd_leak(self):
        s = self.session(); before = fds(); path = Path(s.clip_ref['path']); original_identity = identity(path)
        d = fixed.Decoder(s, s.clip_ref, s.owned_video)
        held_fds = (d.fd, d.input_fd)
        try:
            self.assertEqual(c.sha(os.pread(d.input_fd, len(self.raw), 0)), s.clip_ref['sha256'])
            self.assertEqual(fcntl.fcntl(d.input_fd, fcntl.F_GET_SEALS), fixed.INPUT_SEALS)
            self.assertEqual(fcntl.fcntl(d.input_fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
            self.assertEqual(os.fstat(d.input_fd).st_nlink, 0)
            # Denied truncate operations can still change inode timestamps.
            # Attack a separate identical sealed copy so the positive decoder
            # case does not deliberately invalidate its own strict identity.
            attack_fd, _ = fixed.sealed_clip(c, d.fd, s.clip_ref, s.deadline)
            writable = None
            try:
                writable = os.open('/proc/self/fd/' + str(attack_fd), os.O_RDWR | os.O_CLOEXEC)
                for action in (lambda: os.pwrite(writable, b'X', 0), lambda: os.ftruncate(writable, 0),
                        lambda: os.ftruncate(writable, len(self.raw) + 1),
                        lambda: fcntl.fcntl(writable, fcntl.F_ADD_SEALS, 0)):
                    with self.assertRaises(OSError) as failure: action()
                    self.assertEqual(failure.exception.errno, errno.EPERM)
                self.assertEqual(c.sha(os.pread(attack_fd, len(self.raw), 0)), s.clip_ref['sha256'])
                self.assertEqual(fcntl.fcntl(attack_fd, fcntl.F_GET_SEALS), fixed.INPUT_SEALS)
            finally: fixed.close_fds([writable, attack_fd])
            # Observe actual uid-1000 reopen and inherited descriptors before
            # exercising all three unchanged production decoder factories.
            code = '''import os,sys,json,hashlib
fd=int(sys.argv[1]); raw=open('/proc/self/fd/'+str(fd),'rb').read(); links={}
for n in os.listdir('/proc/self/fd'):
 try: links[n]=os.readlink('/proc/self/fd/'+n)
 except FileNotFoundError: pass
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'fds':links}))
'''
            observed = subprocess.run(['/usr/bin/python3', '-I', '-c', code, str(d.input_fd)],
                pass_fds=(d.input_fd,), user=1000, group=1000, extra_groups=(),
                stdin=subprocess.DEVNULL, capture_output=True, timeout=10, start_new_session=True, check=True)
            actual = json.loads(observed.stdout)
            self.assertEqual((actual['uid'], actual['gid'], actual['bytes'], actual['sha256']),
                (1000, 1000, len(self.raw), s.clip_ref['sha256']))
            self.assertNotIn(str(path), actual['fds'].values())
            self.assertEqual(set(map(int, actual['fds'])), {0, 1, 2, d.input_fd})
            value, ref = d.run(tone_window_ms=[1500, 1600], baseline_end_ms=1400)
            self.assertEqual(set(d.done), {'probe', 'video', 'audio'})
            self.assertTrue(value['full_video_decode'] and value['full_audio_decode'])
            self.assertTrue(value['current_nonce_audio_verified'])
            self.assertFalse(value['runtime_qualified'])
            self.assertEqual(value['probe']['frame_count'], 40)
            self.assertEqual(value['full_frame_decode']['count'], 40)
            self.assertTrue(value['correlation']['baseline_negative_passed'])
            self.assertTrue(value['correlation']['decoy_negative_passed'])
            self.assertEqual(identity(path), original_identity)
            self.assertEqual(c.sha(path.read_bytes()), s.clip_ref['sha256'])
            self.assert_retired(d, ['probe', 'video', 'audio'])
            self.assertTrue(all(d.done[k]['result']['returncode'] == 0 for k in d.done))
            self.assertNotIn('reference', d.done['audio']['result']['stdout'])
            self.assertNotIn('reference', d.done['audio']['result']['stderr'])
            with self.assertRaisesRegex(RuntimeError, 'ONCE_FIXED_FULL_CLIP_DECODE'): d.call('probe')
            REPORT['cases'][self._testMethodName] = {'full_decode': ref, 'observed_reader': actual,
                'identical_sealed_bytes': True, 'sealed_write_grow_shrink_reseal_rejected': True,
                'sealed_attack_fixture_distinct_from_decode_input': True,
                'canonical_identity_and_sha256_unchanged': True, 'all_three_real_children_retired': True,
                'all_three_command_results': [d.done[k]['reference'] for k in ('probe', 'video', 'audio')]}
        finally: d.close()
        self.assertEqual(fds(), before)
        for fd in held_fds:
            with self.assertRaises(OSError) as failure: os.fstat(fd)
            self.assertEqual(failure.exception.errno, errno.EBADF)

    def test_corrupt_clip_fails_cleanly_without_retry(self):
        s = self.session(b'not a media container'); before = fds(); d = fixed.Decoder(s, s.clip_ref, s.owned_video)
        try:
            with self.assertRaisesRegex(RuntimeError, 'FULL_OWNED_CLIP_DECODE_MUST_COMPLETE_CLEANLY'): d.call('probe')
            self.assert_retired(d, ['probe']); self.assertNotEqual(d.done['probe']['result']['returncode'], 0)
            with self.assertRaisesRegex(RuntimeError, 'ONCE_FIXED_FULL_CLIP_DECODE'): d.call('probe')
            REPORT['cases'][self._testMethodName] = {'result': d.done['probe']['reference'],
                'corrupt_input_rejected': True, 'no_retry': True, 'host_retired': True}
        finally: d.close()
        self.assertEqual(fds(), before)

    def test_changed_source_after_seal_is_rejected(self):
        s = self.session(); before = fds(); d = fixed.Decoder(s, s.clip_ref, s.owned_video)
        try:
            with open(s.clip_ref['path'], 'r+b') as out: out.write(b'X')
            with self.assertRaisesRegex(RuntimeError, 'SAME_HELD_OWNED_VIDEO_FOR_ALL_THREE_DECODES'): d.call('probe')
            self.assertEqual(d.done, {})
            REPORT['cases'][self._testMethodName] = {'rejected_before_child_dispatch': True}
        finally: d.close()
        self.assertEqual(fds(), before)

    def test_source_hash_mismatch_closes_constructor_fds(self):
        s = self.session(); before = fds(); bad_ref = dict(s.clip_ref, sha256='b' * 64)
        row = dict(s.owned_video, file_sha256=bad_ref['sha256'])
        with self.assertRaisesRegex(RuntimeError, 'HELD_OWNED_CLIP_NOT_APPROVED_COPY'): fixed.Decoder(s, bad_ref, row)
        self.assertEqual(fds(), before)
        REPORT['cases'][self._testMethodName] = {'rejected_before_child_dispatch': True, 'no_fd_leak': True}

    def test_expired_copy_deadline_closes_both_fds(self):
        s = self.session(); s.deadline = time.monotonic() - 1; before = fds()
        with self.assertRaisesRegex(RuntimeError, 'NO_SEALED_CLIP_COPY_AFTER_PHASE_DEADLINE'):
            fixed.Decoder(s, s.clip_ref, s.owned_video)
        self.assertEqual(fds(), before)
        REPORT['cases'][self._testMethodName] = {'expired_phase_rejected': True, 'no_fd_leak': True}

    def test_sealed_copy_hash_guard_cleans_partial_memfd(self):
        s = self.session(); fd = os.open(s.clip_ref['path'], os.O_RDONLY | os.O_CLOEXEC)
        try:
            before = fds()
            with self.assertRaisesRegex(RuntimeError, 'SEALED_CLIP_MUST_MATCH_HELD_OWNED_BYTES'):
                fixed.sealed_clip(c, fd, dict(s.clip_ref, sha256='b' * 64), time.monotonic() + 5)
            self.assertEqual(fds(), before)
        finally: os.close(fd)
        REPORT['cases'][self._testMethodName] = {'copy_hash_mismatch_rejected': True, 'no_fd_leak': True}

    def test_wrong_nonce_cannot_qualify_decoded_audio(self):
        wrong = f'{int(NONCE, 16) ^ challenge.DECOY_XOR:016x}'
        s = self.session(nonce=wrong); before = fds(); d = fixed.Decoder(s, s.clip_ref, s.owned_video)
        try:
            with self.assertRaisesRegex(RuntimeError, 'OWNED_CAMERA_AUDIO_MUST_CONTAIN_THIS_ONCE_CHALLENGE'):
                d.run(tone_window_ms=[1500, 1600], baseline_end_ms=1400)
            self.assert_retired(d, ['probe', 'video', 'audio'])
            self.assertNotIn('full-owned-video-decode', [label for label, _, _ in s.events])
            REPORT['cases'][self._testMethodName] = {'wrong_current_nonce_rejected': True,
                'all_three_real_children_retired': True, 'success_receipt_absent': True}
        finally: d.close()
        self.assertEqual(fds(), before)

suite = unittest.defaultTestLoader.loadTestsFromTestCase(DecoderHostControls)
result = unittest.TextTestRunner(verbosity=2).run(suite)
REPORT.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skipped=len(result.skipped), passed=result.wasSuccessful(), finished_unix_ns=time.time_ns())
report_path = WORK / 'result.json'; report_path.write_text(json.dumps(REPORT, sort_keys=True, indent=2) + '\n')
print(json.dumps({'result': str(report_path), 'sha256': c.sha(report_path.read_bytes()),
    'tests_run': result.testsRun, 'passed': result.wasSuccessful(), 'runtime_qualified': False}))
raise SystemExit(0 if result.wasSuccessful() else 1)
