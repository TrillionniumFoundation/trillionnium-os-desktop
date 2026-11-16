"""Full decoding of one owned clip through a sealed, identical private copy.

The unchanged bounded capture and OwnChildReaper own each real decoder child.
Only the read-only sealed clip FD and the held fixed decoder executable are
inherited. The root-only evidence file retains its owner and mode. Raw decoded
microphone PCM stays in memory; it is never published.
No Android operation, arbitrary command or additional media path is exposed.
"""
import copy
import ctypes
import fcntl
import hashlib
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import time

CAPTURE = {'path': '/home/alex/work/pocket4-android-final/qualification/bounded_host_capture.py',
    'bytes': 14933, 'sha256': 'bb6d818cbe68b6976da57a996d17b6333cdf5dae03fa743fd0cb7f27f89c2bf3'}
COMMAND_LIMIT = 35
DECODER_UID = DECODER_GID = 1000
INPUT_SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL

class DecodeOutcomeUnknown(RuntimeError):
    pass

def identity(info):
    return {k: str(getattr(info, k)) if k.endswith('_ns') else getattr(info, k) for k in
        ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}

def file_ref(c, fd, path, maximum, *, expected=None):
    info = os.fstat(fd)
    c.need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
        and not info.st_mode & 0o022 and 0 < info.st_size <= maximum, 'EXACT_HELD_DECODER_OR_OWNED_CLIP_FILE')
    before = identity(info); h = hashlib.sha256(); total = 0
    while total < info.st_size:
        block = os.pread(fd, min(65536, info.st_size - total), total)
        c.need(block, 'HELD_DECODER_INPUT_SHORT_READ'); h.update(block); total += len(block)
    c.need(os.pread(fd, 1, total) == b'' and identity(os.fstat(fd)) == before == identity(Path(path).lstat()),
        'HELD_DECODER_INPUT_CHANGED_OR_REPLACED')
    ref = {'path': str(path), 'bytes': total, 'sha256': h.hexdigest()}
    c.need(expected is None or ref == expected, 'HELD_OWNED_CLIP_NOT_APPROVED_COPY')
    return ref, before

def close_fds(descriptors):
    old = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM}); first = None
    try:
        for fd in descriptors:
            if fd is not None:
                try: os.close(fd)
                except BaseException as error:
                    if first is None: first = error
                    else: first.add_note('OTHER_HELD_DECODER_FD_CLOSE:' + str(error))
    finally: signal.pthread_sigmask(signal.SIG_SETMASK, old)
    if first is not None: raise first

def sealed_clip(c, source_fd, expected, deadline):
    """Copy exactly the held source into a sealed, decoder-readable memfd.

    Inheriting a root:0400 FD permits reads on that FD, but ffmpeg reopens its
    /proc/self/fd input and Linux checks the inode permissions again. A private
    anonymous copy permits that reopen after dropping privileges without
    granting access to the original evidence file or creating a readable path.
    """
    writer = reader = None
    try:
        writer = os.memfd_create('camera-owned-video', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        total = 0; digest = hashlib.sha256()
        while total < expected['bytes']:
            c.need(time.monotonic() < deadline, 'NO_SEALED_CLIP_COPY_AFTER_PHASE_DEADLINE')
            block = os.pread(source_fd, min(65536, expected['bytes'] - total), total)
            c.need(block, 'HELD_OWNED_CLIP_SHORT_READ_DURING_SEAL')
            digest.update(block); offset = 0
            while offset < len(block):
                c.need(time.monotonic() < deadline, 'NO_SEALED_CLIP_WRITE_AFTER_PHASE_DEADLINE')
                written = os.write(writer, block[offset:])
                c.need(written > 0, 'SEALED_CLIP_SHORT_WRITE'); offset += written
            total += len(block)
        c.need(os.pread(source_fd, 1, total) == b'' and digest.hexdigest() == expected['sha256']
            and os.fstat(writer).st_size == expected['bytes'], 'SEALED_CLIP_MUST_MATCH_HELD_OWNED_BYTES')
        os.fchown(writer, DECODER_UID, DECODER_GID); os.fchmod(writer, 0o400)
        fcntl.fcntl(writer, fcntl.F_ADD_SEALS, INPUT_SEALS)
        reader = os.open('/proc/self/fd/' + str(writer), os.O_RDONLY | os.O_CLOEXEC)
        closing, writer = writer, None; close_fds([closing])
        info = os.fstat(reader)
        c.need(stat.S_ISREG(info.st_mode) and info.st_nlink == 0
            and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (DECODER_UID, DECODER_GID, 0o400)
            and info.st_size == total and fcntl.fcntl(reader, fcntl.F_GET_SEALS) == INPUT_SEALS
            and fcntl.fcntl(reader, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            'EXACT_SEALED_READ_ONLY_DECODER_INPUT')
        return reader, identity(info)
    except BaseException as error:
        try: close_fds([reader, writer])
        except BaseException as cleanup: error.add_note('SEALED_CLIP_CLEANUP:' + str(cleanup))
        raise

class Decoder:
    def __init__(self, session, clip_ref, row):
        self.s, self.c, self.row = session, session.c, copy.deepcopy(row)
        self.media = session.components['camera_video_media.py']; self.commands = session.flow.modules['business_commands.py']
        self.fd = self.input_fd = None; self.closed = False; self.done = {}; self.unknown = False
        root = Path(session.active['case_root']) / 'evidence'
        self.c.need(clip_ref['path'] == str(root / 'owned-camera-video.mp4')
            and row['uri'] == session.owned_video['uri'] and row['is_pending'] == 0
            and clip_ref['bytes'] == row['_size'] and clip_ref['sha256'] == row['file_sha256'],
            'ONLY_THIS_FINALIZED_OWNED_VIDEO_COPY')
        self.path = Path(clip_ref['path']); self.ref = copy.deepcopy(clip_ref)
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            _, self.metadata = file_ref(self.c, self.fd, self.path, self.media.MAX_CLIP_BYTES, expected=self.ref)
            self.input_fd, self.input_metadata = sealed_clip(self.c, self.fd, self.ref,
                min(time.monotonic() + COMMAND_LIMIT, session.deadline))
            self.input_ref = {'kind': 'sealed-memfd', 'source': self.ref,
                'bytes': self.ref['bytes'], 'sha256': self.ref['sha256'],
                'metadata': self.input_metadata, 'seals': INPUT_SEALS, 'read_only': True,
                'original_owner_and_mode_unchanged': True, 'original_fd_inherited': False}
            self.c.need(identity(os.fstat(self.fd)) == self.metadata == identity(self.path.lstat()),
                'OWNED_VIDEO_CHANGED_DURING_PRIVATE_COPY')
            self.capture = self.c.module(CAPTURE, 'camera_decoder_unchanged_bounded_capture')
        except BaseException:
            self.close(); raise

    def verify(self):
        self.c.need(not self.closed and self.fd is not None
            and identity(os.fstat(self.fd)) == self.metadata == identity(self.path.lstat()),
            'SAME_HELD_OWNED_VIDEO_FOR_ALL_THREE_DECODES')
        self.verify_input()
        self.s.guard()

    def verify_input(self):
        self.c.need(self.input_fd is not None and identity(os.fstat(self.input_fd)) == self.input_metadata
            and fcntl.fcntl(self.input_fd, fcntl.F_GET_SEALS) == INPUT_SEALS
            and fcntl.fcntl(self.input_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            and not os.get_inheritable(self.input_fd), 'SAME_SEALED_READ_ONLY_INPUT_FOR_ALL_THREE_DECODES')

    def call(self, kind):
        c, s = self.c, self.s
        c.need(kind in ('probe', 'video', 'audio') and kind not in self.done
            and not self.unknown and s.phase_name == 'business', 'ONCE_FIXED_FULL_CLIP_DECODE')
        self.verify(); self.done[kind] = {'attempted': True, 'automatic_retry': False}
        argv = self.media.decoder_argv(kind, '/proc/self/fd/' + str(self.input_fd))
        executable = None; reaper = None; first = finish_error = None; began = False
        out = err = None; record = {}; cancel = self.commands.Cancellation()
        result = {'schema': 'pocket4-current-camera-owned-decode-command-v1', 'kind': kind,
            'argv': argv, 'clip': self.ref, 'sealed_input': self.input_ref,
            'scope': s.flow.scope_ref, 'phase': s.phase_ref,
            'capture': CAPTURE, 'errors': [], 'automatic_retry': False, 'raw_audio_persisted': False}
        def remember(stage, error):
            nonlocal first
            result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})
            if first is None: first = error
        try:
            executable = os.open(argv[0], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            decoder, executable_metadata = file_ref(c, executable, argv[0], 33554432)
            c.need(os.fstat(executable).st_mode & 0o111 and os.pread(executable, 6, 0) == b'\x7fELF\x02\x01',
                'ACTUAL_FIXED_X86_64_HOST_DECODER')
            deadline = min(time.monotonic() + COMMAND_LIMIT, s.deadline)
            bound = 2016000 if kind == 'audio' else 1048576
            result.update(decoder=decoder, decoder_metadata=executable_metadata,
                execution_deadline_monotonic=deadline, observation_deadline_monotonic=deadline + 8,
                phase_deadline_monotonic=s.deadline, output_bound_per_stream=bound,
                inherited_fds={'owned_clip': self.input_fd, 'held_decoder': executable},
                original_held_clip_metadata=self.metadata, sealed_owned_clip_metadata=self.input_metadata,
                sealed_owned_clip_seals=INPUT_SEALS)
            s.record('decode-' + kind + '-intent', result)
            c.need(time.monotonic() < deadline, 'NO_DECODER_DISPATCH_AFTER_PHASE_DEADLINE')
            reaper = self.capture.OwnChildReaper(protected_pids=tuple(s.baseline.protected_pids))
            cancel.begin(); reaper.begin(); began = True
            def factory(input_fd, output_fd, error_fd, output_bound):
                c.need(time.monotonic() < min(deadline, s.deadline), 'NO_DECODER_FACTORY_AFTER_CURRENT_DEADLINE')
                c.need(identity(os.fstat(self.fd)) == self.metadata == identity(self.path.lstat())
                    and identity(os.fstat(executable)) == executable_metadata == identity(Path(argv[0]).lstat()),
                    'DECODER_OR_CLIP_CHANGED_AT_ACTUAL_FACTORY')
                self.verify_input()
                def child_limits():
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    lib = ctypes.CDLL(None, use_errno=True)
                    if lib.prctl(38, 1, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), 'PR_SET_NO_NEW_PRIVS')
                return subprocess.Popen(argv, executable='/proc/self/fd/' + str(executable),
                    stdin=input_fd, stdout=output_fd, stderr=error_fd, close_fds=True,
                    pass_fds=(self.input_fd, executable), start_new_session=True,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/home/alex'},
                    user=DECODER_UID, group=DECODER_GID, extra_groups=(), preexec_fn=child_limits)
            # A dispatch may lose its reply. Keep that uncertainty before the
            # actual boundary; a later evidence-write error cannot erase it.
            self.unknown = True
            record, out, err, error = self.capture.invoke_owned(reaper, factory, b'', deadline, deadline + 8,
                output_bound=bound, cleanup_enter=cancel.enter_retirement, retirement_grace=5)
            if error is not None: remember('actual_owned_decoder', error)
            c.need(identity(os.fstat(executable)) == executable_metadata == identity(Path(argv[0]).lstat()),
                'HOST_DECODER_CHANGED_DURING_EXECUTION')
        except BaseException as error: remember('owned_decode', error)
        finally:
            cancel.enter_retirement()
            if began:
                try: reaper.finish()
                except BaseException as error: finish_error = error; remember('decode_reaper_finish', error)
            try: cancel.restore()
            except BaseException as error: finish_error = finish_error or error; remember('decode_signal_restore', error)
            try: close_fds([executable])
            except BaseException as error: finish_error = finish_error or error; remember('decode_executable_close', error)
        subreaper = {} if reaper is None else copy.deepcopy(reaper.record)
        retired = self.commands.retirement_complete(record, subreaper, finish_error)
        self.unknown = not retired or type(out) is not bytes or type(err) is not bytes
        result.update(lifecycle=record, subreaper=subreaper, host_retirement_proved=retired,
            cancellation={'signals': cancel.signals, 'count': cancel.count},
            returncode=record.get('returncode'), timed_out=record.get('timed_out', False))
        try:
            for name, raw in (('stdout', out), ('stderr', err)):
                if type(raw) is bytes:
                    result[name] = {'bytes': len(raw), 'sha256': c.sha(raw), 'persisted': False}
                    if kind != 'audio': result[name]['reference'] = c.write_new(s.evidence_root / ('decode-' + kind + '.' + name), raw)
            try: self.verify()
            except BaseException as error: remember('decode_post_guard', error)
            ref = s.record('decode-' + kind + '-result', result); self.done[kind] = {'result': result, 'reference': ref}
        except BaseException as error:
            if first is not None and error is not first:
                first.add_note('DECODER_EVIDENCE_FAILURE:' + repr(error))
                raise first from error
            raise
        if self.unknown:
            raise DecodeOutcomeUnknown('OWNED_DECODER_RETIREMENT_OR_OUTPUT_UNKNOWN') from first
        c.need(first is None and not result['errors'] and not cancel.signals and record['returncode'] == 0
            and not record['timed_out'] and err == b'' and record['descendants'] == [],
            'FULL_OWNED_CLIP_DECODE_MUST_COMPLETE_CLEANLY')
        return out, ref

    def run(self, *, tone_window_ms, baseline_end_ms):
        c, s = self.c, self.s
        probe_raw, probe_ref = self.call('probe'); probe = self.media.parse_probe(probe_raw, self.row)
        video_raw, video_ref = self.call('video'); video = self.media.parse_framemd5(video_raw, probe['frame_count'])
        pcm, audio_ref = self.call('audio')
        c.need(abs(len(pcm) / 96 - self.row['duration']) <= 1500, 'FULL_DECODED_AUDIO_DURATION_MATCHES_OWNED_CLIP')
        correlation = s.components['camera_audio_challenge.py'].analyze(pcm, s.active['audio_nonce'],
            tone_window_ms=tone_window_ms, baseline_end_ms=baseline_end_ms,
            deadline=min(time.monotonic() + 8, s.deadline))
        c.need(correlation['matched'], 'OWNED_CAMERA_AUDIO_MUST_CONTAIN_THIS_ONCE_CHALLENGE')
        value = {'schema': 'pocket4-current-camera-full-video-decode-v1', 'uri': self.row['uri'],
            'file_sha256': self.ref['sha256'], 'clip_sha256': self.ref['sha256'], 'file_bytes': self.ref['bytes'],
            'nonce': s.active['audio_nonce'], 'scope': s.flow.scope_ref, 'phase': s.phase_ref,
            'epoch_sha256': s.active['framework_epoch_sha256'], 'clip': self.ref,
            'probe': probe, 'full_frame_decode': video, 'commands': [probe_ref, video_ref, audio_ref],
            'full_video_decode': True, 'full_audio_decode': True, 'current_nonce_audio_verified': True,
            'tone_offset_ms': correlation['positive']['offset_blocks'] * 10, 'correlation': correlation,
            'raw_audio_persisted': False, 'outcome_unknown': False, 'runtime_qualified': False}
        # PCM bytes are no longer retained after this call; only exact hashes,
        # decoded frame evidence and the independently bounded correlation stay.
        del pcm; ref = s.record('full-owned-video-decode', value); self.verify(); return value, ref

    def close(self):
        fd, self.fd = self.fd, None
        input_fd, self.input_fd = self.input_fd, None
        self.closed = True; close_fds([input_fd, fd])
