"""One owned video, one sealed copy, three actual bounded host decoders.

This component does not create a Main, Session, plan, UI action or audio stream.
The video Session/typed MediaStore policy remains a separate required entry.
Only decode_owned(session, recording) is the production execution entry. It
derives all paths, runners, ownership and rows from the source-admitted Session.
"""
import copy
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import time

META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')
SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
MAX_CLIP_BYTES = 128 * 1024 * 1024
MAX_PCM_BYTES = 21 * 48000 * 2
AUDIO_DURATION_TOLERANCE_SECONDS = 0.25


def need(value, why):
    if not value:
        raise RuntimeError(why)


def identity(info):
    return {key: getattr(info, key) for key in META}


class SealedClip:
    """Host data handles only; never pass a Main authority FD to a decoder."""
    def __init__(self, target, row, nonce, deadline):
        self.target, self.row, self.deadline = target, copy.deepcopy(row), deadline
        self.owner = os.getpid(); self.source_fd = self.fd = None; self.closed = False
        self.retirement_unproved = False
        write_fd = None
        try:
            need(type(nonce) is str and re.fullmatch('[0-9a-f]{16}', nonce)
                and nonce != '0' * 16 and type(row['_size']) is int
                and 0 < row['_size'] <= MAX_CLIP_BYTES, 'ONE_BOUNDED_NONZERO_NONCE_OWNED_CLIP')
            self.source_fd = target.open_root(row['_data'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            source = os.fstat(self.source_fd); self.source_identity = identity(source)
            need(stat.S_ISREG(source.st_mode) and source.st_nlink == 1
                and source.st_size == row['_size'], 'EXACT_REGULAR_NEW_VIDEO_BYTES')
            write_fd = os.memfd_create('p4-camera-video-' + nonce, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            digest = hashlib.sha256(); offset = 0
            while offset < row['_size']:
                need(time.monotonic() < deadline, 'VIDEO_COPY_PHASE_EXPIRED')
                raw = os.pread(self.source_fd, min(1048576, row['_size'] - offset), offset)
                need(raw, 'OWNED_VIDEO_SHORT_READ')
                digest.update(raw); offset += len(raw); rest = memoryview(raw)
                while rest:
                    count = os.write(write_fd, rest)
                    need(count > 0, 'VIDEO_MEMFD_WRITE_NO_PROGRESS'); rest = rest[count:]
            need(identity(os.fstat(self.source_fd)) == self.source_identity, 'OWNED_VIDEO_CHANGED_DURING_COPY')
            self.sha256 = digest.hexdigest(); self.bytes = offset
            fcntl.fcntl(write_fd, fcntl.F_ADD_SEALS, SEALS)
            need(fcntl.fcntl(write_fd, fcntl.F_GET_SEALS) == SEALS, 'ALL_FOUR_VIDEO_MEMFD_SEALS_REQUIRED')
            self.fd = os.open('/proc/' + str(self.owner) + '/fd/' + str(write_fd), os.O_RDONLY | os.O_CLOEXEC)
            self.memfd_identity = identity(os.fstat(self.fd))
            self.path = '/proc/' + str(self.owner) + '/fd/' + str(self.fd)
            self.label = os.readlink(self.path)
            self.verify(); self.verify_named_source()
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup:
                error.add_note('VIDEO_FD_CLOSE:' + type(cleanup).__name__)
            raise
        finally:
            if write_fd is not None:
                os.close(write_fd)

    def verify(self):
        need(not self.closed and os.getpid() == self.owner and self.fd is not None
            and time.monotonic() < self.deadline, 'LIVE_VIDEO_OWNER_AND_PHASE_REQUIRED')
        need(self.path == '/proc/' + str(os.getpid()) + '/fd/' + str(self.fd)
            and not os.get_inheritable(self.fd)
            and identity(os.fstat(self.fd)) == self.memfd_identity == identity(os.stat(self.path))
            and os.readlink(self.path) == self.label
            and fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) == SEALS
            and fcntl.fcntl(self.fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            and identity(os.fstat(self.source_fd)) == self.source_identity,
            'SAME_READONLY_SEALED_VIDEO_AND_HELD_ORIGINAL')
        digest = hashlib.sha256(); offset = 0
        while offset < self.bytes:
            need(time.monotonic() < self.deadline, 'VIDEO_HASH_PHASE_EXPIRED')
            raw = os.pread(self.fd, min(1048576, self.bytes - offset), offset)
            need(raw, 'SEALED_VIDEO_SHORT_READ'); offset += len(raw); digest.update(raw)
        need(offset == self.bytes and digest.hexdigest() == self.sha256, 'SEALED_VIDEO_HASH_CHANGED')

    def verify_named_source(self):
        fd = self.target.open_root(self.row['_data'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(identity(os.fstat(fd)) == self.source_identity, 'OWNED_VIDEO_NAMED_FILE_REPLACED')
        finally:
            os.close(fd)

    def close(self):
        need(not self.retirement_unproved, 'UNKNOWN_CHILD_RETAINS_ITS_EXACT_VIDEO_FD')
        errors = []
        for name in ('fd', 'source_fd'):
            fd = getattr(self, name, None); setattr(self, name, None)
            if fd is not None:
                try:
                    expected = getattr(self, 'memfd_identity' if name == 'fd' else 'source_identity', None)
                    actual = os.fstat(fd)
                    need(expected is None or (actual.st_dev, actual.st_ino) ==
                        (expected['st_dev'], expected['st_ino']), 'DO_NOT_CLOSE_A_REPLACED_VIDEO_DESCRIPTOR')
                    os.close(fd)
                except BaseException as error:
                    errors.append(error)
        self.closed = not errors
        if errors:
            raise errors[0]

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if self.retirement_unproved:
            # A late child can still open argv's exact /proc/PID/fd/N. Closing
            # N would allow unrelated later evidence I/O to reuse that number.
            need(error is not None, 'UNKNOWN_VIDEO_CHILD_CANNOT_COMPLETE')
            error.add_note('UNKNOWN_CHILD_RETAINS_ITS_EXACT_VIDEO_FD_UNTIL_EXPLICIT_RECONCILIATION_OR_PROCESS_EXIT')
            return
        try:
            self.close()
        except BaseException as cleanup:
            if error is None:
                raise
            error.add_note('VIDEO_FD_CLOSE:' + type(cleanup).__name__)


def _recorder_bridge(flow):
    # CameraFlow wraps the real source-bound bridge in ImageRecorder, loaded
    # separately from session.components. No wrapper method grants admission.
    bridge = flow.bridge
    if type(bridge) is not flow.scope_module.RecorderBridge:
        bridge = getattr(bridge, 'real', None)
    need(type(bridge) is flow.scope_module.RecorderBridge and bridge.flow is flow
        and bridge.binding is flow.bound, 'SOURCE_BOUND_RECORDER_FAILURE_FENCE_REQUIRED')
    return bridge


def _admit(session, recording):
    """No photo Session fallback and no caller-supplied success dictionary."""
    need(session.kind == session.active['kind'] == 'camera_video', 'ACTUAL_VIDEO_SESSION_REQUIRED')
    modules = session.components
    need(type(session) is modules['camera_video_session.py'].Session
        and type(recording) is modules['camera_video_state.py'].Recording
        and modules['camera_video_decode.py'].decode_owned is decode_owned
        and recording is session.video_recording, 'SOURCE_BOUND_VIDEO_SESSION_AND_RECORDING')
    flow = session.flow
    need(not session.closed and session.phase_name == 'business' and session.active_api is None
        and recording.state == 'STOPPED_UNSAVED' and recording.pending is None
        and not recording.retired and recording.media is None
        and recording.start_ack and recording.stop_ack, 'KNOWN_RECORDING_AND_STOP_BEFORE_MEDIA_READ')
    need(recording.scope == flow.scope_ref == flow.bound.scope_ref
        and recording.phase == session.phase_ref == flow.phase_lease_ref
        and recording.epoch_sha256 == session.active['framework_epoch_sha256']
            == flow.scope['framework_epoch_sha256'] == session.baseline.value['framework_epoch']['sha256'],
        'SAME_CURRENT_VIDEO_SCOPE_PHASE_AND_EPOCH')
    session.verify_runtime(flow)
    current = session.guard(action_attempted=False)
    selected = flow.selected_task()
    need(selected['task'] == recording.task and selected['prelaunch_absent'] is True
        and selected['cleanup_allowed'] is True, 'REAL_CURRENT_OWNED_CAMERA_TASK')
    profile = session.active['target_profile']
    need(profile['package'] == 'com.android.camera2' and profile['uid'] == 10062,
        'ORIGINAL_CAMERA_IDENTITY_REQUIRED')
    for ref in (recording.start_ack, recording.stop_ack):
        ack = session.c.parse(session.c.read_ref(ref))
        need(ack['scope'] == recording.scope and ack['phase'] == recording.phase,
            'CURRENT_RECORDING_NATIVE_ACKS_REQUIRED')
    row = session.owned_video; media = modules['camera_video_media.py']
    need(type(row) is dict and row['is_pending'] == 0 and row['owner_package_name'] == media.PACKAGE
        and row['_id'] == session.video_id
        and media.one_new_video(session.video_ids_before, session.video_ids_after) == session.video_id
        and row['uri'] == media.URI + '/' + str(session.video_id)
        and session.c.parse(session.c.read_ref(session.owned_video_ref)) == row,
        'ONLY_THE_CURRENT_TYPED_POLICY_OWNED_VIDEO_ROW')
    commands = flow.bound.commands
    need(type(commands) is flow.host_runtime.PhaseCommands and commands.runtime is flow
        and commands.original is flow.bound.modules['business_commands.py'],
        'UNCHANGED_SOURCE_BOUND_PHASE_CROPPED_RECORDER_REQUIRED')
    need(not _recorder_bridge(flow).closed and not flow.bound.poisoned,
        'SOURCE_BOUND_OPEN_RECORDER_FAILURE_FENCE_REQUIRED')
    tools = session.active['video_decoder_tools']
    need(type(tools) is dict and set(tools) == {'ffprobe', 'ffmpeg'}, 'PLAN_BOUND_VIDEO_DECODER_TOOL_REFS_REQUIRED')
    for name, reference in tools.items():
        need(reference['path'] == '/usr/bin/' + name
            and session.c.regular(reference['path'], contents=False) == reference,
            'CURRENT_PLAN_BOUND_HOST_DECODER_BYTES_REQUIRED')
    return current


def _retired(observation, name, argv):
    """Only observations returned by the admitted recorder reach this check."""
    return (type(observation) is dict and observation.get('schema') == 'pocket4-business-host-result-v1'
        and observation.get('name') == name and observation.get('argv') == argv
        and observation.get('host_retirement_proved') is True)


def _hold(session, recording, error):
    """The existing bridge's failure fence, also covering a missing receipt."""
    flow = session.flow
    flow.bound.poisoned = True
    try:
        _recorder_bridge(flow).closed = True
    except BaseException as secondary:
        error.add_note('VIDEO_RECORDER_FENCE:' + type(secondary).__name__)
    try:
        if recording.decode_outcome_unknown:
            flow.view.target.poison_unjoined_command()
        else:
            flow.view.target.seal_admission()
    except BaseException as secondary:
        error.add_note('VIDEO_ADMISSION_FENCE:' + type(secondary).__name__)
    # ScopeBinding.hold preserves the first hold.json. Never replace the
    # original error/command_observation with a cleanup or evidence failure.
    try:
        flow.bound.hold(error)
    except BaseException as secondary:
        error.add_note('VIDEO_HOLD_EVIDENCE:' + type(secondary).__name__)


def _decode_outputs(media, clip, row, execute):
    """Pure orchestration of fixed commands; only the bound entry supplies execute."""
    probe = media.parse_probe(execute('probe', media.decoder_argv('probe', clip.path), 1048576), row)
    frames = media.parse_framemd5(execute('video', media.decoder_argv('video', clip.path), 1048576), probe['frame_count'])
    pcm = execute('audio', media.decoder_argv('audio', clip.path), MAX_PCM_BYTES)
    need(type(pcm) is bytes and 0 < len(pcm) <= MAX_PCM_BYTES and len(pcm) % 2 == 0,
        'COMPLETE_BOUNDED_MONO_S16LE_AUDIO_REQUIRED')
    duration = len(pcm) / (48000 * 2)
    need(abs(duration - probe['durations']['audio']) <= AUDIO_DURATION_TOLERANCE_SECONDS,
        'FULL_DECODED_AUDIO_DURATION_DIFFERS_FROM_PROBE')
    return {'probe': probe, 'video': frames, 'audio': {'bytes': len(pcm),
        'sha256': hashlib.sha256(pcm).hexdigest(), 'frames': len(pcm) // 2, 'duration_seconds': duration,
        'rate': 48000, 'channels': 1, 'sample_format': 's16le',
        'duration_tolerance_ms': int(AUDIO_DURATION_TOLERANCE_SECONDS * 1000)}}, pcm


def decode_owned(session, recording):
    """Decode only session.owned_video; return evidence and in-memory audio.

    Required future video Session fields: video_recording, video_ids_before,
    video_ids_after, video_id, owned_video and owned_video_ref; its admitted
    active plan must pin both video_decoder_tools. The typed
    MediaStore policy must set them from its actual before/start/stop/after
    reads. This component never invents those observations or creates a Session.
    """
    _admit(session, recording)
    need(not recording.decode_attempted, 'NO_REPLAYED_VIDEO_DECODE')
    c = session.c; row = copy.deepcopy(session.owned_video); row_ref = copy.deepcopy(session.owned_video_ref)
    root = c.private_dir(Path(session.evidence_root) / ('video-decode-' + recording.nonce), create=True)
    c.write_new(root / 'intent.json', {'schema': 'pocket4-owned-video-decode-intent-v1',
        'row': row_ref, 'nonce': recording.nonce, 'scope': recording.scope, 'phase': recording.phase,
        'epoch_sha256': recording.epoch_sha256, 'task': recording.task, 'automatic_retry': False})
    recording.decode_attempted = True; receipts = []; clip = None; observation = None
    try:
        with SealedClip(session.flow.view.target, row, recording.nonce, session.deadline) as clip:
            recording.decode_held_clip = clip

            def guard(*, action_attempted=False):
                need(action_attempted is False, 'VIDEO_DECODERS_HAVE_NO_ANDROID_ACTION_AUTHORITY')
                current = _admit(session, recording)
                need(session.owned_video == row and session.owned_video_ref == row_ref, 'OWNED_VIDEO_ROW_CHANGED')
                clip.verify()
                return {'current_Main': current, 'scope': recording.scope, 'phase': recording.phase,
                        'nonce': recording.nonce, 'owned_video_sha256': clip.sha256, 'Android_actions': 0}

            def execute(kind, argv, bound):
                nonlocal observation
                need(kind in ('probe', 'video', 'audio')
                    and argv == session.components['camera_video_media.py'].decoder_argv(kind, clip.path)
                    and clip.path.startswith('/proc/' + str(os.getpid()) + '/fd/'), 'FIXED_CURRENT_CONTROLLER_VIDEO_DECODER')
                guard(); observation = None
                recording.decode_outcome_unknown = clip.retirement_unproved = True
                name = 'decode-' + kind
                try:
                    result = session.flow.bound.commands.run_recorded(name, argv, 45, root, guard,
                        protected_pids=session.flow.bound.baseline.protected_pids, mutation=False, pass_fds=(),
                        host_env=c.HOST_ENV, check=False, output_bound=bound, deferred_post_guard=False,
                        private_output=True, input_bytes=b'', image_channel=False)
                except BaseException as error:
                    observation = getattr(error, 'command_observation', None)
                    if _retired(observation, name, argv):
                        recording.decode_outcome_unknown = clip.retirement_unproved = False
                    raise
                observation = value = result.command_observation
                if _retired(value, name, argv):
                    recording.decode_outcome_unknown = clip.retirement_unproved = False
                ref = c.regular(root / (name + '.result.json'), contents=False)
                need(c.parse(c.read_ref(ref)) == value and _retired(value, name, argv)
                    and value['evidence_complete'] is True and not value['errors'] and not result.recorder_errors
                    and value['post_guard_deferred_to_held_transport'] is False
                    and value['action_attempted'] is False and value['Android_outcome_unknown'] is False,
                    'ACTUAL_COMPLETE_RETIRED_VIDEO_DECODER_RECEIPT')
                for label, raw in (('stdout', result.stdout), ('stderr', result.stderr)):
                    need(type(raw) is bytes and len(raw) <= bound and value[label] == {
                        'bytes': len(raw), 'sha256': c.sha(raw), 'persisted': False}, 'EXACT_PRIVATE_DECODER_OUTPUT')
                need(result.returncode == value['returncode'] == 0 and not result.host_timed_out
                    and not value['timed_out'] and 'first_error' not in value and not result.stderr,
                    'FULL_VIDEO_DECODER_MUST_EXIT_ZERO_WITHOUT_DECODE_ERRORS')
                guard(); receipts.append({'kind': kind, 'result': ref}); return result.stdout

            decoded, pcm = _decode_outputs(session.components['camera_video_media.py'], clip, row, execute)
            guard(); clip.verify_named_source()
            bound_row = {**row, 'file_sha256': clip.sha256}
            binding = {'original_row': row_ref, 'source_file': clip.source_identity,
                'sealed_copy': clip.memfd_identity, 'controller_pid': clip.owner,
                'file_bytes': clip.bytes, 'file_sha256': clip.sha256, 'all_seals': SEALS,
                'host_decoder_tools': copy.deepcopy(session.active['video_decoder_tools']),
                'read_only': True, 'inherited_fds': 0, 'full_source_bytes_persisted': False}
        _admit(session, recording)
        row_proof = c.write_new(root / 'owned-row.json', bound_row)
        value = {'schema': 'pocket4-owned-video-full-decode-v1', 'nonce': recording.nonce,
            'scope': recording.scope, 'phase': recording.phase, 'epoch_sha256': recording.epoch_sha256,
            'task': recording.task, 'uri': row['uri'], 'file_bytes': binding['file_bytes'],
            'file_sha256': binding['file_sha256'], 'binding': binding, 'commands': receipts, **decoded,
            'full_video_decode': True, 'full_audio_decode': True, 'owned_descriptors_closed': clip.closed,
            'microphone_source_qualified': False, 'Android_same_URI_playback_qualified': False,
            'runtime_qualified': False, 'whole_app_business_accepted': False, 'automatic_retry': False}
        proof = c.write_new(root / 'result.json', value); _admit(session, recording)
        return bound_row, row_proof, value, proof, pcm
    except BaseException as error:
        if getattr(error, 'command_observation', None) is None and observation is not None:
            error.command_observation = observation
        _hold(session, recording, error)
        raise
    finally:
        if clip is not None and clip.closed:
            recording.decode_held_clip = None
