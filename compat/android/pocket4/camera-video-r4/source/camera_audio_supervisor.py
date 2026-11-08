"""One root owner, one business worker, two sequential finite acoustic actors.

No Android command is admitted in the parent. Actor preparation, GO and final
receipts are separate once-only transitions. The listener never opens output.
The shared core is an exact source copy of the qualified WebView owner; only
its pipe, pidfd, signal and terminal primitives are inherited here.
"""
import copy
import fcntl
import hashlib
import os
from pathlib import Path
import select
import selectors
import signal
import socket
import stat
import subprocess
import time

CAPTURE_BYTES = 48000 * 2 * 21
ACTOR_STREAM_BOUND = 65536

def make_supervisor(core):
    class Supervisor(core.Supervisor):
        def __init__(self, c, plan_ref, prep_ref, components, request_ref, packet):
            self.c, self.plan_ref, self.prep_ref, self.components = c, plan_ref, prep_ref, components
            self.runtime = components['app_runtime.py']; self.channel_module = components['camera_audio_channel.py']
            self.plan = c.parse(c.read_ref(plan_ref)); self.request_ref, self.packet = request_ref, packet
            _, support = c.support(self.plan['support_manifest'])
            self.baseline = support['business_baseline.py'].BusinessBaseline(self.plan['baseline'], self.plan['qualification'])
            components['camera_plan.py'].validate(c, self.plan, self.baseline)
            self.task = components['camera_plan.py'].source_packet(c, self.plan, packet)['camera']
            c.need(c.parse(c.read_ref(request_ref)) == {'base_plan': plan_ref}, 'ONE_EXACT_VIDEO_EXECUTION_REQUEST')
            self.root = Path(self.plan['case_root']); c.need(not (self.root / 'execute-once.json').exists(), 'NO_VIDEO_CASE_REPLAY')
            self.out = c.private_dir(self.root / 'acoustic-supervisor', create=True)
            self.started = time.monotonic(); self.deadline = self.started + self.plan['limits']['supervisor_seconds'] - 30
            self.reaper = self.selector = self.channel = self.main_view = None
            self.actors = {}; self.pipe_map = {}; self.sequence = 0
            self.pending_reply = self.pending_reply_deadline = None
            self.actor_sources = {}; self.actor_gates = {}; self.actor_ready = {}; self.actor_final = {}
            self.actor_go = {}; self.actor_deadlines = {}; self.memory = self.executable = None
            self.channel_eof = False; self.retiring = self.committed = False
            self.signals = []; self.after_commit_signals = []; self.first = self.inner = None
            self.record = {'schema': 'pocket4-current-camera-acoustic-supervisor-result-v1', 'state': 'STARTING',
                'plan': plan_ref, 'preparation': prep_ref, 'kind': self.plan['kind'], 'nonce': self.plan['audio_nonce'],
                'limits': copy.deepcopy(self.plan['limits']), 'events': [], 'errors': [], 'received_signals': self.signals,
                'actors': {}, 'automatic_retry': False, 'Main_signals': 0, 'Android_UI_actions_by_supervisor': 0,
                'whole_app_business_accepted': False, 'raw_audio_persisted': False}

        def setup(self):
            c = self.c; c.need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'ROOT_VIDEO_ACOUSTIC_OWNER')
            life = c.module(core.LIFECYCLE, 'camera_unchanged_owned_lifecycle')
            self.reaper = life.OwnChildReaper(protected_pids=self.baseline.protected_pids)
            self.reaper.begin(); self.selector = selectors.DefaultSelector()
            journal = c.private_dir(self.out / 'held-main', create=True)
            def no_command(argv, timeout, root, private): raise RuntimeError('ACOUSTIC_PARENT_HAS_NO_ANDROID_ADMISSION')
            self.main_view = c.MainView(self.plan['baseline'], self.plan['qualification'], journal, no_command,
                support_ref=self.plan['support_manifest'])
            profile = self.components['camera_profiles.py']; raw = c.read_ref(profile.AUDIO_ACTOR, 8388608)
            build = c.parse(c.read_ref(profile.AUDIO_BUILD))
            c.need(build.get('runtime_qualified') is False and raw[:6] == b'\x7fELF\x02\x01'
                and int.from_bytes(raw[18:20], 'little') == 62, 'EXACT_COMPILED_CURRENT_ACOUSTIC_ACTOR')
            self.executable = os.memfd_create('p4-camera-audio-actor', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            done = 0
            while done < len(raw): done += os.write(self.executable, raw[done:])
            os.fchmod(self.executable, 0o555)
            seal = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
            fcntl.fcntl(self.executable, fcntl.F_ADD_SEALS, seal)
            c.need(fcntl.fcntl(self.executable, fcntl.F_GET_SEALS) == seal
                and os.pread(self.executable, len(raw) + 1, 0) == raw, 'SEALED_EXACT_ACOUSTIC_EXECUTABLE_COPY')
            parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET); self.channel = parent
            try:
                for sock in (parent, child): sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
                parent.setblocking(False)
                value = {'schema': 'pocket4-current-camera-acoustic-parent-v1', 'plan': self.plan_ref,
                    'preparation': self.prep_ref, 'case_root': str(self.root), 'parent': self.runtime.process(c, os.getpid()),
                    'boot_id': self.runtime.boot(), 'client_socket': self.channel_module.socket_identity(child.fileno()),
                    'limits': self.plan['limits'], 'nonce': self.plan['audio_nonce'], 'automatic_retry': False}
                self.parent_ref = c.write_new(self.out / 'parent.json', value, 0o400)
                entry = next(r for r in self.task['files'] if Path(r['path']).name == 'camera_entry.py')
                c.read_ref(entry); c.read_ref(self.request_ref)
                argv = ['/usr/bin/python3', '-I', '-B', entry['path'], '--preparation', self.prep_ref['path'],
                    '--expect-preparation-sha256', self.prep_ref['sha256'], 'execute-worker', '--request', self.request_ref['path'],
                    '--expect-request-sha256', self.request_ref['sha256'], '--acoustic-fd', str(child.fileno()),
                    '--acoustic-parent', self.parent_ref['path'], '--expect-acoustic-parent-sha256', self.parent_ref['sha256']]
                self.record['worker_argv'] = argv
                c.need(time.monotonic() < self.started + 10, 'BOUNDED_ACOUSTIC_SUPERVISOR_STARTUP')
                item = self.actor('business', argv, pass_fds=(child.fileno(),))
                item['identity'] = self.runtime.process(c, item['process'].pid)
                c.need(item['identity']['parent'] == os.getpid(), 'ACTUAL_DIRECT_VIDEO_WORKER')
                self.record['business_process'] = item['identity']
                self.selector.register(parent, selectors.EVENT_READ, ('control', None, None))
            finally: child.close()

        def verify_phase(self, value):
            c = self.c; c.need(set(value) in ({'active_plan', 'phase'}, {'active_plan', 'phase', 'playback_binding'}),
                'EXACT_CAMERA_ACOUSTIC_PHASE_REFERENCE')
            active = c.parse(c.read_ref(value['active_plan'])); phase = c.parse(c.read_ref(value['phase']))
            c.need(value['active_plan']['path'] == str(self.root / 'active-plan.json') and active['base_plan'] == self.plan_ref
                and {k: active[k] for k in self.plan if k != 'schema'} == {k: v for k, v in self.plan.items() if k != 'schema'},
                'ACTIVE_VIDEO_PLAN_SAME_FROZEN_BASE')
            self.components['camera_plan.py'].validate(c, active, self.baseline)
            lease = c.parse(c.read_ref(active['lease'])); owner = self.actors['business']['identity']; now = time.monotonic_ns()
            c.need(lease['schema'] == 'pocket4-final-camera-case-lease-v1' and lease['base_plan'] == self.plan_ref
                and lease['kind'] == 'camera_video' and lease['owner'] == owner and lease['boot_id'] == self.runtime.boot()
                and lease['automatic_retry'] is False and lease['cleanup_seconds'] == 60 and lease['business_seconds'] == 420
                and lease['business_deadline_monotonic_ns'] == lease['started_monotonic_ns'] + 420000000000
                and int(self.started * 1e9) <= lease['started_monotonic_ns'] <= now < lease['business_deadline_monotonic_ns'],
                'ACTUAL_VIDEO_WORKER_ABSOLUTE_LEASE')
            c.need(value['phase']['path'] == str(self.root / 'phase-business.json')
                and phase['schema'] == 'pocket4-final-camera-phase-lease-v1' and phase['phase'] == 'business'
                and phase['active_plan'] == value['active_plan'] and phase['lease'] == active['lease']
                and phase['owner'] == owner and phase['trigger'] is None and phase['automatic_retry'] is False
                and lease['started_monotonic_ns'] <= phase['started_monotonic_ns'] <= now
                and phase['deadline_monotonic_ns'] == lease['business_deadline_monotonic_ns'], 'ACTUAL_CURRENT_VIDEO_PHASE')
            once = c.parse(c.read_ref(c.regular(self.root / 'execute-once.json', contents=False)))
            c.need(once['plan'] == self.plan_ref and once['operator'] == owner, 'ACTUAL_ONCE_VIDEO_WORKER_ENTRY')
            return phase

        def actor(self, role, argv, *, pass_fds=(), alex=False):
            c = self.c; c.need(not self.retiring and not self.signals, 'NO_CAMERA_CHILD_AFTER_CANCEL_OR_RETIREMENT')
            c = self.c; c.need(role in ('business', 'emit', 'listen') and role not in self.actors,
                'ONCE_EXACT_CAMERA_SIBLING')
            c.need((role != 'business') == alex, 'ONLY_ACOUSTIC_ACTORS_RUN_AS_ALEX')
            item = {'process': None, 'pidfd': None, 'lifecycle': core.life_record(), 'streams': {},
                'bound': ACTOR_STREAM_BOUND if alex else 16777216, 'receipts': []}
            self.actors[role] = item; self.record['actors'][role] = item['lifecycle']
            for name in ('stdout', 'stderr'):
                item['streams'][name] = {'buffer': bytearray(), 'eof': False, 'closed': False, 'pipe': None,
                    'file': open(self.out / (role + '.' + name), 'xb'), 'bytes_observed': 0}
            env = dict(c.HOST_ENV)
            if alex: env.update(HOME='/home/alex', XDG_RUNTIME_DIR='/run/user/1000',
                DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
            # The fixed actor wrapper starts root only to drop all authority;
            # the sealed ELF refuses any UID/GID other than exactly 1000.
            process = subprocess.Popen(argv, stdin=subprocess.PIPE if alex else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, close_fds=True,
                pass_fds=tuple(pass_fds), env=env, user=0, group=0, extra_groups=())
            item['process'] = process
            item['lifecycle'].update(child_started=True, pid=process.pid, uid=1000 if alex else 0)
            if alex: self.actor_gates[role] = process.stdin
            for name in ('stdout', 'stderr'): item['streams'][name]['pipe'] = getattr(process, name)
            for name in ('stdout', 'stderr'):
                stream = item['streams'][name]; pipe = stream['pipe']; os.set_blocking(pipe.fileno(), False)
                self.selector.register(pipe, selectors.EVENT_READ, ('pipe', role, name)); self.pipe_map[pipe.fileno()] = (role, name)
            item['pidfd'] = os.pidfd_open(process.pid, 0); item['lifecycle']['pidfd_closed'] = False
            c.need(os.getpgid(process.pid) == process.pid and os.getsid(process.pid) == process.pid,
                'PRIVATE_CAMERA_SIBLING_SESSION')
            if alex: os.set_blocking(self.actor_gates[role].fileno(), False)
            self.record['events'].append({'event': role + '_spawned', 'pid': process.pid, 'monotonic_ns': time.monotonic_ns()})
            return item

        def lines(self, role):
            raw = bytes(self.actors[role]['streams']['stdout']['buffer'])
            return [self.c.parse(x) for x in raw.splitlines() if x] if raw.endswith(b'\n') else []

        def prepare_actor(self, role, value):
            self.c.need(not self.retiring and not self.signals, 'NO_AUDIO_PREPARATION_AFTER_CANCEL_OR_RETIREMENT')
            c = self.c; phase = self.verify_phase(value); self.main_view.guard()
            c.need(role not in self.actors and (role == 'emit' or set(self.actor_final) == {'emit'}),
                'EMITTER_ACTUALLY_RETIRED_BEFORE_LISTENER_PREPARATION')
            if role == 'listen':
                self.memory = os.memfd_create('p4-camera-playback', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
                os.ftruncate(self.memory, CAPTURE_BYTES)
                fcntl.fcntl(self.memory, fcntl.F_ADD_SEALS, fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK)
            deadline = min(time.monotonic_ns() + 23000000000, phase['deadline_monotonic_ns'])
            c.need(deadline - time.monotonic_ns() >= 5000000000, 'ENOUGH_CURRENT_PHASE_FOR_FINITE_AUDIO_ACTOR')
            argv = ['/proc/self/fd/' + str(self.executable), role, self.plan['audio_nonce'], str(deadline),
                str(os.getpid()), str(-1 if role == 'emit' else self.memory)]
            wrapper = ('import ctypes,os;lib=ctypes.CDLL(None,use_errno=True);'
                'assert lib.prctl(38,1,0,0,0)==0;os.setgroups([]);os.setgid(1000);os.setuid(1000);'
                'os.execve(' + repr(argv[0]) + ',' + repr(argv) + ',dict(os.environ))')
            descriptors = (self.executable,) if role == 'emit' else (self.executable, self.memory)
            c.need(time.monotonic_ns() < deadline, 'NO_ACTOR_SPAWN_AFTER_CURRENT_DEADLINE')
            item = self.actor(role, ['/usr/bin/python3', '-I', '-B', '-c', wrapper], pass_fds=descriptors, alex=True)
            self.actor_deadlines[role] = deadline / 1e9
            cutoff = min(time.monotonic() + 7, deadline / 1e9)
            while not self.lines(role):
                c.need(time.monotonic() < cutoff and self.terminal(role) is None, 'CURRENT_ACOUSTIC_READY_DEADLINE')
                self.verify_business(); self.pump(.03, control=False)
            rows = self.lines(role); c.need(len(rows) == 1 and not item['streams']['stderr']['buffer'], 'ONE_NATIVE_ACTOR_READY')
            ready = rows[0]; identity = self.channel_module.child_identity(item['process'].pid)
            event = 'camera_challenge_ready' if role == 'emit' else 'camera_playback_observer_ready'
            c.need(ready['event'] == event and ready['mode'] == role and ready['nonce'] == self.plan['audio_nonce']
                and ready['pid'] == item['process'].pid and ready['uid'] == ready['gid'] == 1000 and ready['started'] is False
                and identity['parent'] == os.getpid() and identity['uids'] == identity['gids'] == [1000] * 4
                and identity['groups'] == [] and identity['NoNewPrivs'] == '1'
                and all(identity[k] == '0000000000000000' for k in ('CapEff', 'CapPrm', 'CapAmb')),
                'ACTUAL_DROPPED_EXACT_ACOUSTIC_SIBLING')
            self.c.need(identity['executable_inode'] == {'device': os.fstat(self.executable).st_dev,
                'inode': os.fstat(self.executable).st_ino}, 'ACTUAL_EXECUTED_SEALED_ACTOR_ELF')
            if role == 'emit': c.need(ready['sink_name'] == self.components['camera_audio_binding.py'].SINK_NAME, 'FIXED_PHYSICAL_CHALLENGE_SINK')
            else:
                b = self.components['camera_audio_binding.py']
                c.need(ready['source_name'] == b.SOURCE_NAME and ready['bus_path'] == b.BUS_PATH
                    and ready['active_port'] == b.INPUT_PORT and ready['output_streams_created'] == 0,
                    'LISTENER_ONLY_EXACT_PHYSICAL_INPUT')
            self.actor_ready[role] = ready; self.actor_sources[role] = identity; self.main_view.guard()
            ref = c.write_new(self.out / (role + '-ready.json'), {'ready': ready, 'identity': identity,
                'parent': self.parent_ref, 'phase': value['phase'], 'deadline_monotonic_ns': deadline})
            return {'ready': ready, 'identity': identity, 'reference': ref}

        def go_actor(self, role, value):
            self.c.need(not self.retiring and not self.signals, 'NO_AUDIO_GO_AFTER_CANCEL_OR_RETIREMENT')
            self.verify_phase(value); self.main_view.guard(); c = self.c
            c.need(role in self.actor_ready and role not in self.actor_go and role not in self.actor_final,
                'ONCE_GO_AFTER_EXACT_ACTOR_READY')
            item = self.actors[role]; c.need(self.terminal(role) is None, 'LIVE_PREPARED_AUDIO_ACTOR')
            gate = self.actor_gates[role]; payload = ('GO ' + self.plan['audio_nonce'] + '\n').encode()
            now = time.monotonic_ns(); self.actor_go[role] = {'request_monotonic_ns': now, 'sent': False}
            c.need(os.write(gate.fileno(), payload) == len(payload), 'ATOMIC_ONCE_ACOUSTIC_GO')
            self.actor_go[role]['sent'] = True; cutoff = min(time.monotonic() + 3, self.actor_deadlines[role])
            while len(self.lines(role)) < 2:
                c.need(time.monotonic() < cutoff and self.terminal(role) is None, 'ACTUAL_AUDIO_GO_ACK_REQUIRED')
                self.verify_business(); self.pump(.02, control=False)
            row = self.lines(role)[1]; expected = 'camera_challenge_started' if role == 'emit' else 'camera_playback_observer_started'
            c.need(row['event'] == expected and row['nonce'] == self.plan['audio_nonce']
                and now <= row['monotonic_ns'] <= time.monotonic_ns(), 'THIS_CURRENT_ACTOR_GO_BOUNDARY')
            self.actor_go[role]['actual_started'] = row
            return c.parse(c.read_ref(c.write_new(self.out / (role + '-go.json'), self.actor_go[role])))

        def finish_actor(self, role, value):
            c = self.c; self.verify_phase(value); c.need(role in self.actor_go and role not in self.actor_final,
                'ONCE_FINISH_OF_ACTUALLY_STARTED_AUDIO_ACTOR')
            item = self.actors[role]
            if role == 'listen':
                c.need(set(self.actor_final) == {'emit'}, 'NO_HOST_CHALLENGE_EMISSION_DURING_GALLERY_PLAYBACK')
                payload = ('STOP ' + self.plan['audio_nonce'] + '\n').encode()
                c.need(os.write(self.actor_gates[role].fileno(), payload) == len(payload), 'ATOMIC_ONCE_LISTENER_STOP')
            cutoff = min(time.monotonic() + 8, self.actor_deadlines[role])
            while time.monotonic() < cutoff and (self.terminal(role) is None
                    or not all(s['eof'] for s in item['streams'].values())):
                self.verify_business(); self.pump(.03, control=False)
            self.reaper.retire_leader(item['process'], item['pidfd'], item['lifecycle'], self.remember, time.monotonic() + 3)
            c.need(item['lifecycle']['child_reaped'] and item['process'].returncode == 0,
                'ACOUSTIC_LEADER_MUST_EXIT_NORMALLY_AND_BE_REAPED')
            c.need(self.reaper.children() == [self.actors['business']['process'].pid],
                'ANY_ACOUSTIC_ADOPTEE_REQUIRES_GLOBAL_FAILURE_RETIREMENT')
            self.drain_available_pipes(); rows = self.lines(role)
            c.need(len(rows) == 3 and rows[0] == self.actor_ready[role]
                and rows[1] == self.actor_go[role]['actual_started']
                and not item['streams']['stderr']['buffer'] and all(s['eof'] for s in item['streams'].values()),
                'EXACT_NATIVE_READY_STARTED_CLOSED_AND_BOTH_EOF')
            closed = rows[2]; expected = 'camera_challenge_closed' if role == 'emit' else 'camera_playback_observer_closed'
            c.need(closed['event'] == expected and closed['mode'] == role and closed['nonce'] == self.plan['audio_nonce']
                and closed['stream_closed'] is True and closed['runtime_qualified'] is False
                and closed['pulse_stream_index'] == rows[0]['pulse_stream_index']
                and rows[1]['monotonic_ns'] < closed['monotonic_ns'] <= time.monotonic_ns(), 'EXACT_NATIVE_AUDIO_TERMINAL')
            gate = self.actor_gates.pop(role); gate.close()
            result = {'role': role, 'ready': rows[0], 'started': rows[1], 'closed': closed,
                'identity': self.actor_sources[role], 'parent': self.parent_ref, 'phase': value['phase'],
                'exit_code': item['process'].returncode, 'leader_reaped': True,
                'pipe_eof': {n: r['eof'] for n, r in item['streams'].items()}, 'automatic_retry': False}
            if role == 'emit':
                c.need(closed['submitted_frames'] == 133440 and closed['playback_phase_emit'] is False
                    and closed['sink_name'] == rows[0]['sink_name'] and closed['sink_index'] == rows[0]['sink_index'],
                    'EXACT_ONCE_COMPLETE_RECORD_CHALLENGE_DRAIN')
            else:
                c.need(closed['output_streams_created'] == 0 and closed['raw_audio_persisted'] is False
                    and (closed['rate'], closed['channels'], closed['format']) == (48000, 1, 's16le')
                    and all(closed[k] == rows[0][k] for k in ('source_name', 'source_index', 'bus_path', 'active_port')),
                    'LISTENER_NO_OUTPUT_AND_SAME_PHYSICAL_INPUT')
                size = closed['captured_bytes']; c.need(type(size) is int and 288000 <= size <= CAPTURE_BYTES and size % 2 == 0,
                    'FINITE_ACTUAL_CAPTURE_BYTE_COUNT')
                seal = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
                fcntl.fcntl(self.memory, fcntl.F_ADD_SEALS, seal)
                c.need(fcntl.fcntl(self.memory, fcntl.F_GET_SEALS) == seal, 'REAPED_LISTENER_ARTIFACT_IMMUTABLE')
                pcm = os.pread(self.memory, size, 0); c.need(len(pcm) == size, 'COMPLETE_HELD_LISTENER_BYTES')
                binding = self.playback_binding(value['playback_binding'], value)
                result['playback_binding'] = value['playback_binding']
                result['correlation'] = self.components['camera_audio_challenge.py'].analyze(pcm, self.plan['audio_nonce'],
                    tone_window_ms=binding['tone_window_ms'], baseline_end_ms=binding['baseline_end_ms'],
                    deadline=min(time.monotonic() + 8, self.deadline))
                result['sealed_capture'] = {'bytes': size, 'sha256': hashlib.sha256(pcm).hexdigest(),
                    'raw_audio_persisted': False, 'sealed_after_actual_child_reaped': True}
            ref = c.write_new(self.out / (role + '-final.json'), result); result['reference'] = ref
            self.actor_final[role] = result; self.main_view.guard(); return result

        def playback_binding(self, ref, value):
            c = self.c; c.need(Path(ref['path']).parent == self.root / 'evidence'
                and Path(ref['path']).name.endswith('-playback-acoustic-binding.json'), 'ONLY_THIS_WORKER_PLAYBACK_BINDING')
            b = c.parse(c.read_ref(ref)); c.need(set(b) == {'schema', 'plan', 'active_plan', 'phase', 'nonce',
                'uri', 'clip_sha256', 'clip_decode', 'view_request', 'view_result', 'listener_started_monotonic_ns',
                'tone_window_ms', 'baseline_end_ms', 'emitter_final', 'automatic_retry'}, 'EXACT_PLAYBACK_BINDING_FIELDS')
            c.need(b['schema'] == 'pocket4-current-camera-playback-acoustic-binding-v1' and b['plan'] == self.plan_ref
                and b['active_plan'] == value['active_plan'] and b['phase'] == value['phase']
                and b['nonce'] == self.plan['audio_nonce'] and b['automatic_retry'] is False
                and b['emitter_final'] == self.actor_final['emit']['reference']
                and b['listener_started_monotonic_ns'] == self.actor_go['listen']['actual_started']['monotonic_ns'],
                'SAME_CURRENT_NONCE_PHASE_AND_RETIRED_RECORD_EMITTER')
            decode = c.parse(c.read_ref(b['clip_decode'])); request = c.parse(c.read_ref(b['view_request']))
            result = c.parse(c.read_ref(b['view_result']))
            c.need(decode['uri'] == b['uri'] and decode['clip_sha256'] == b['clip_sha256']
                and decode['nonce'] == b['nonce'] and decode['full_video_decode'] is True
                and decode['current_nonce_audio_verified'] is True and request['uri'] == b['uri']
                and result['uri'] == b['uri'] and result['same_owned_task'] is True
                and request['started_monotonic_ns'] >= b['listener_started_monotonic_ns']
                and result['finished_monotonic_ns'] >= request['started_monotonic_ns'], 'EXACT_DECODED_URI_PLAYED_AFTER_LISTENER_START')
            origin = b['listener_started_monotonic_ns']; offset = decode['tone_offset_ms']
            c.need(type(offset) is int and offset >= 1500, 'ACTUAL_DECODED_CURRENT_CHALLENGE_POSITION')
            first = (request['started_monotonic_ns'] - origin) // 1000000 + offset - 250
            last = (result['finished_monotonic_ns'] - origin) // 1000000 + offset + 750
            c.need(b['tone_window_ms'] == [max(1500, first), last]
                and b['baseline_end_ms'] == min(1500, max(1280, first - 250)), 'NO_WIDE_OR_REPLAYED_PHYSICAL_MATCH_WINDOW')
            return b

        def control(self):
            self.c.need(not self.retiring and not self.signals, 'NO_ACOUSTIC_REQUEST_AFTER_CANCEL_OR_RETIREMENT')
            c = self.c; c.need(self.pending_reply is None, 'NO_REENTRANT_ACOUSTIC_REPLY'); self.verify_business()
            item = self.actors['business']
            try: row = self.channel_module.receive(self.channel, (item['process'].pid, 0, 0), c.parse)
            except BlockingIOError: return
            c.need(type(row) is dict and set(row) == self.channel_module.REQUEST_KEYS
                and row['schema'] == self.channel_module.SCHEMA and row['sequence'] == self.sequence + 1
                and row['parent'] == self.parent_ref and row['plan'] == self.plan_ref
                and self.sequence < 6 and row['kind'] == self.channel_module.ORDER[self.sequence]
                and type(row['value']) is dict, 'EXACT_ORDERED_CAMERA_ACOUSTIC_REQUEST')
            self.sequence += 1; role, action = row['kind'].split('_', 1)
            fn = {'prepare': self.prepare_actor, 'go': self.go_actor, 'finish': self.finish_actor}[action]
            result = fn(role, row['value'])
            raw = c.canonical({'schema': self.channel_module.SCHEMA, 'sequence': self.sequence,
                'kind': row['kind'], 'ok': True, 'value': result, 'error': None})
            c.need(len(raw) <= self.channel_module.MAX_PACKET, 'BOUNDED_AUDIO_REPLY')
            self.pending_reply = raw; self.pending_reply_deadline = time.monotonic() + 1
            self.selector.modify(self.channel, selectors.EVENT_WRITE, ('control', None, None))

        def pump(self, timeout, *, control=True):
            control = control and not self.retiring and not self.signals
            self.reaper.single_thread(); budget = 262144
            for key, mask in self.selector.select(max(0, min(.1, timeout))):
                kind, role, name = key.data
                if kind == 'pipe':
                    if key.fd in self.pipe_map and budget > 0: budget -= self.read_pipe(role, name, budget)
                elif control:
                    if self.pending_reply is None:
                        try: peek = self.channel.recv(1, socket.MSG_PEEK)
                        except BlockingIOError: continue
                        if not peek:
                            self.c.need(self.sequence == 6, 'WORKER_CHANNEL_CLOSED_BEFORE_FINITE_AUDIO_FINISH')
                            self.channel_eof = True; self.selector.unregister(self.channel); continue
                        self.control()
                    else: self.send_reply()
            if control and self.pending_reply is not None:
                self.c.need(time.monotonic() < self.pending_reply_deadline, 'ACOUSTIC_REPLY_STALLED')
            for role, deadline in self.actor_deadlines.items():
                if role not in self.actor_final and self.terminal(role) is None:
                    self.c.need(time.monotonic() < deadline, 'WHOLE_FINITE_AUDIO_ACTOR_DEADLINE')

        def close_owner(self):
            for role in list(self.actor_gates):
                gate = self.actor_gates.pop(role)
                try: gate.close()
                except BaseException as error: self.remember(error, role + '_gate_close')

        def retire_all(self):
            self.retiring = True
            if self.reaper is None: return
            if not self.reaper.record['begin_passed']:
                if self.reaper.original is not None:
                    try: self.reaper.finish()
                    except BaseException as error: self.remember(error, 'restore_failed_reaper_admission')
                self.record['subreaper'] = copy.deepcopy(self.reaper.record); return
            if self.terminal('business') is None and self.actors.get('business', {}).get('process') is not None:
                try: self.signal_exact('business', signal.SIGINT)
                except BaseException as error: self.remember(error, 'cancel_actual_video_worker')
                graceful = min(time.monotonic() + 60, self.deadline)
                while time.monotonic() < graceful and self.terminal('business') is None:
                    try: self.pump(.05, control=False)
                    except BaseException as error:
                        self.remember(error, 'worker_cleanup_pump'); break
            retirement = time.monotonic() + 30
            for role in ('emit', 'listen', 'business'):
                item = self.actors.get(role)
                if item is not None and item['process'] is not None and not item['lifecycle']['child_reaped']:
                    self.reaper.retire_leader(item['process'], item['pidfd'], item['lifecycle'], self.remember, retirement)
            adopted = {'descendants': [], 'owned_tree_cleanup_complete': False}
            if all(x['process'] is None or x['lifecycle']['child_reaped'] for x in self.actors.values()):
                self.reaper.retire_adopted(adopted, self.remember, retirement)
            self.record['adopted_retirement'] = adopted
            try:
                while self.pipe_map and time.monotonic() < retirement: self.pump(.02, control=False)
                self.c.need(not self.pipe_map, 'ACOUSTIC_ALL_PIPE_WRITERS_RETIRED'); self.reaper.finish()
            except BaseException as error: self.remember(error, 'final_owned_retirement')
            self.record['subreaper'] = copy.deepcopy(self.reaper.record)

        def assess(self):
            c = self.c; item = self.actors.get('business')
            c.need(item is not None and item['lifecycle']['child_reaped'], 'ACTUAL_VIDEO_WORKER_REAPED')
            raw, ref = c.regular(self.root / 'result.json'); value = c.parse(raw)
            c.need(value['schema'] == 'pocket4-current-camera-video-case-result-v1' and value['plan'] == self.plan_ref
                and value['source_preparation'] == self.prep_ref and value['kind'] == 'camera_video'
                and value['whole_app_business_accepted'] is False, 'EXACT_CURRENT_VIDEO_WORKER_TERMINAL')
            self.inner = value; self.record['inner_result'] = ref
            c.need(value['acoustic_results'] == self.actor_final and value['acoustic_channel_closed'] is True,
                'ACTUAL_WORKER_AND_PARENT_ACOUSTIC_TERMINALS_AGREE')
            c.need(item['process'].returncode == (0 if value['case_business_success_verified'] else 1), 'WORKER_RESULT_AND_EXIT_AGREE')
            c.need(self.record.get('subreaper', {}).get('restored') is True
                and self.record['subreaper']['final_children_empty'] is True
                and self.record.get('adopted_retirement', {}).get('owned_tree_cleanup_complete') is True
                and all(x['lifecycle']['child_reaped'] and x['lifecycle']['pidfd_closed']
                    and all(r['eof'] for r in x['streams'].values()) for x in self.actors.values()),
                'ALL_ACTUAL_CAMERA_OWNER_CHILDREN_AND_FDS_RETIRED')
            if value['case_business_success_verified']:
                c.need(self.record['adopted_retirement'].get('descendants') == [],
                    'NO_UNACCOUNTED_ADOPTED_SUBTREE_FOR_SUCCESS')
                c.need(set(self.actor_final) == {'emit', 'listen'} and self.sequence == 6,
                    'COMPLETE_DISTINCT_RECORD_AND_LISTEN_ACTORS_FOR_SUCCESS')
            self.baseline.guard(); self.components['camera_plan.py'].validate(c, self.plan, self.baseline)
            c.need(time.monotonic() <= self.started + self.plan['limits']['supervisor_seconds'], 'VIDEO_TOTAL_SUPERVISOR_BOUND')

        def close(self):
            self.close_owner(); super().close()
            for name in ('memory', 'executable'):
                fd = getattr(self, name); setattr(self, name, None)
                if fd is not None:
                    try: os.close(fd)
                    except BaseException as error: self.remember(error, name + '_close')
            self.record['audio_artifact_descriptors_closed'] = self.memory is self.executable is None

        def run(self):
            worker_result_verified = False
            for number in (signal.SIGINT, signal.SIGTERM): signal.signal(number, self.cancelled)
            try:
                self.setup()
                while self.terminal('business') is None:
                    self.c.need(time.monotonic() < self.deadline, 'VIDEO_WORKER_ABSOLUTE_SUPERVISOR_DEADLINE'); self.pump(.1)
            except BaseException as error: self.remember(error, 'supervisor_operation')
            finally:
                self.retiring = True
                try: self.close_owner(); self.retire_all()
                except BaseException as error: self.remember(error, 'supervisor_retirement')
                self.close()
                if self.main_view is not None:
                    try: self.main_view.close(); self.record['held_Main_closed'] = True
                    except BaseException as error: self.remember(error, 'held_Main_close')
                try: self.assess(); worker_result_verified = True
                except BaseException as error: self.remember(error, 'actual_video_worker_terminal')
                signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
                pending = sorted(signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
                if self.signals or pending: self.remember(core.SupervisorCancelled('CANCELLED_BEFORE_CAMERA_COMMIT'), 'terminal_cancel')
                success = bool(self.first is None and self.inner is not None and self.inner.get('case_business_success_verified') is True)
                self.record.update(state='CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN' if success else 'FAILED_OR_UNKNOWN_RETAINED',
                    case_business_success_verified=success, whole_app_business_accepted=False, error=self.first,
                    cancellation_commit={'pending_at_commit': pending, 'decision_after_all_context_close': True},
                    elapsed_seconds=time.monotonic() - self.started, acoustic_results=self.actor_final,
                    lifecycle_source=core.LIFECYCLE, worker_result_verified=worker_result_verified,
                    outcome_unknown=bool(not worker_result_verified or self.record.get('subreaper', {}).get('final_children_empty') is not True
                        or (self.inner or {}).get('outcome_unknown') is True), automatic_rollback=False)
                ref = self.c.write_new(self.out / 'result.json', self.record); self.committed = True
            return ref, self.record
    return Supervisor
