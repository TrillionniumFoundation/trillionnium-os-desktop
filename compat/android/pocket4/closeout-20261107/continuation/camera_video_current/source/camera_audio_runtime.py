"""Fresh Main audio attribution, exact helper generations and physical routes.

These read-only observations connect the real Camera/Gallery AudioFlinger row
to a held app PID, the current APEX HAL, helper SO_PEERPIDFD events and actual
Pulse stream/device. A source-qualified APEX alone is never a runtime proof.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import time

HELPERS = {'input': '/usr/lib/droidloom/runtime/pocket4/bin/droidloom-audio-capture',
           'output': '/usr/lib/droidloom/runtime/pocket4/bin/droidloom-audio-host'}
UNITS = {'input': 'droidloom-audio-capture.service', 'output': 'droidloom-audio-host.service'}
HAL = '/apex/com.android.hardware.audio.droidloom/bin/hw/android.hardware.audio.service-aidl.droidloom'
APEX = '/vendor/apex/com.android.hardware.audio.droidloom.apex'
HAL_MEMBER = '/bin/hw/android.hardware.audio.service-aidl.droidloom'
PROPERTIES = 'Id,LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup,InvocationID,FragmentPath,ExecStart'
PULSE_PREFIX = ['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--init-groups',
    '/usr/bin/env', 'XDG_RUNTIME_DIR=/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
    '/usr/bin/pactl', '--server=unix:/run/user/1000/pulse/native', '--format=json', 'list']
FLAGS = ('normal_complete_audio_apex_build', 'complete_apex_signature_and_payload_verified',
    'normal_same_source_four_host_cohort', 'actual_private_mount_controls', 'actual_input_output_protocol_controls',
    'actual_pulse_ffi_abi', 'actual_socket_service_lifecycle_controls', 'actual_deployment_extension_controls',
    'ordinary_source_projection_restored', 'all_owned_build_processes_retired', 'all_build_source_locks_released',
    'no_oom_or_swap_use', 'actual_fixed_group_creation_and_exact_rollback')

def need(value, why):
    if not value: raise RuntimeError(why)

def inode(info):
    return {'device': info.st_dev, 'inode': info.st_ino}

def file_identity(info):
    return {key: str(getattr(info, key)) if key.endswith('_ns') else getattr(info, key)
        for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}

def read_at(directory, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not part: break
            data.extend(part)
        need(len(data) <= maximum, 'BOUNDED_CURRENT_AUDIO_PROCESS_FIELD')
        return bytes(data)
    finally: os.close(fd)

def process_state(directory, pid):
    raw = read_at(directory, 'stat', 65536).decode('ascii', 'strict')
    fields = raw.rsplit(')', 1)[1].split()
    need(int(raw.split(' ', 1)[0]) == pid and len(fields) >= 20, 'ACTUAL_AUDIO_PROC_GENERATION')
    lines = read_at(directory, 'status', 131072).decode('ascii', 'strict').splitlines()
    selected = {x.split(':', 1)[0]: x.split(':', 1)[1].split() for x in lines
        if x.split(':', 1)[0] in ('Uid', 'Gid', 'NSpid', 'Groups')}
    need(set(selected) == {'Uid', 'Gid', 'NSpid', 'Groups'}, 'COMPLETE_CURRENT_AUDIO_PROCESS_UID_NAMESPACE_PIDS')
    return {'host_pid': pid, 'parent': int(fields[1]), 'start_ticks': int(fields[19]),
        'uids': [int(v) for v in selected['Uid']], 'gids': [int(v) for v in selected['Gid']],
        'namespace_pids': [int(v) for v in selected['NSpid']], 'groups': [int(v) for v in selected['Groups']],
        'namespaces': {n: os.readlink('ns/' + n, dir_fd=directory) for n in ('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup', 'user')},
        'cgroup': read_at(directory, 'cgroup', 65536).decode('ascii', 'strict').splitlines(),
        'command_sha256': hashlib.sha256(read_at(directory, 'cmdline', 131072)).hexdigest()}

def id_map(raw):
    """Parse the kernel's bounded, nonoverlapping user-namespace ID ranges."""
    need(type(raw) is bytes and 0 < len(raw) <= 16384, 'BOUNDED_CURRENT_GUEST_ID_MAP')
    lines = raw.splitlines(keepends=True)
    need(0 < len(lines) <= 340, 'BOUNDED_CURRENT_GUEST_ID_MAP_ROWS')
    rows = []
    for line in lines:
        match = re.fullmatch(rb'[ \t]*([0-9]{1,10})[ \t]+([0-9]{1,10})[ \t]+([0-9]{1,10})\n', line)
        need(match is not None, 'EXACT_KERNEL_GUEST_ID_MAP_ROW')
        inside, outside, count = map(int, match.groups())
        need(count > 0 and inside + count <= 4294967295 and outside + count <= 4294967295,
            'MAPPED_GUEST_IDS_MUST_NOT_OVERFLOW_OR_USE_UNMAPPED_SENTINEL')
        rows.append((inside, outside, count))
    for column in (0, 1):
        ordered = sorted(rows, key=lambda row: row[column])
        need(all(left[column] + left[2] <= right[column] for left, right in zip(ordered, ordered[1:])),
            'NONOVERLAPPING_CURRENT_GUEST_ID_MAP')
    return tuple(rows)

class GuestCredentials:
    """Bind Android IDs to the namespace observing /proc, stat and socket peers.

    The second column of uid_map/gid_map is relative to the opener when its
    namespace differs from the target's. In the same namespace it instead
    names the parent, so the observed ID is the original Android ID. Never
    guess a subordinate-ID offset or use overflowuid/overflowgid as a mapping.
    """
    def __init__(self, target):
        self.proc = self.pidfd = self.target_user = self.observer_user = None
        self.closed = False
        try:
            target.verify()
            # Camera/Player scopes retire their MainView independently. Own
            # these handles so a normal scope transition does not invalidate
            # the unchanged Main's credential map or silently adopt a new Main.
            self.proc = os.dup(target.proc_fd)
            self.proc_identity = inode(os.fstat(self.proc))
            raw = read_at(self.proc, 'stat', 65536).decode('ascii', 'strict')
            fields = raw.rsplit(')', 1)[1].split()
            need(len(fields) >= 20, 'COMPLETE_HELD_MAIN_CREDENTIAL_GENERATION')
            self.pid = int(raw.split(' ', 1)[0]); self.start_ticks = int(fields[19])
            self.pidfd = os.pidfd_open(self.pid, 0)
            self.target_user = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc)
            self.observer_user = os.open('/proc/thread-self/ns/user', os.O_RDONLY | os.O_CLOEXEC)
            self.target_identity = inode(os.fstat(self.target_user))
            self.observer_identity = inode(os.fstat(self.observer_user))
            self.raw = {kind: read_at(self.proc, kind + '_map', 16384) for kind in ('uid', 'gid')}
            self.rows = {kind: id_map(raw) for kind, raw in self.raw.items()}
            self.verify_for(target)
        except BaseException:
            self.close(); raise

    @property
    def receipt(self):
        return {'schema': 'pocket4-held-guest-credential-map-v1',
            'target_process': {'host_pid': self.pid, 'start_ticks': self.start_ticks,
                'proc_directory': dict(self.proc_identity)},
            'target_user_namespace': 'user:[' + str(self.target_identity['inode']) + ']',
            'observer_user_namespace': 'user:[' + str(self.observer_identity['inode']) + ']',
            'same_user_namespace': self.target_identity == self.observer_identity,
            'maps': {kind: {'raw': raw.decode('ascii'), 'sha256': hashlib.sha256(raw).hexdigest()}
                for kind, raw in self.raw.items()}}

    def verify(self):
        need(not self.closed, 'HELD_GUEST_CREDENTIAL_MAP_CLOSED')
        poll = select.poll(); poll.register(self.pidfd, select.POLLIN)
        need(not poll.poll(0), 'HELD_MAIN_CREDENTIAL_PROCESS_EXITED')
        raw = read_at(self.proc, 'stat', 65536).decode('ascii', 'strict')
        fields = raw.rsplit(')', 1)[1].split()
        need(int(raw.split(' ', 1)[0]) == self.pid and len(fields) >= 20 and int(fields[19]) == self.start_ticks
            and inode(os.fstat(self.proc)) == self.proc_identity, 'HELD_MAIN_CREDENTIAL_GENERATION_CHANGED')
        need(inode(os.fstat(self.target_user)) == self.target_identity
            == inode(os.stat('ns/user', dir_fd=self.proc))
            and inode(os.fstat(self.observer_user)) == self.observer_identity
            == inode(os.stat('/proc/thread-self/ns/user')), 'GUEST_OR_OBSERVER_USER_NAMESPACE_CHANGED')
        need(all(read_at(self.proc, kind + '_map', 16384) == raw
            for kind, raw in self.raw.items()), 'HELD_GUEST_CREDENTIAL_MAP_CHANGED')

    def verify_for(self, target):
        target.verify()
        need(inode(os.fstat(target.proc_fd)) == self.proc_identity, 'CURRENT_FLOW_MAIN_DIFFERS_FROM_HELD_CREDENTIAL_MAIN')
        self.verify(); target.verify()

    def observer_id(self, kind, guest_id):
        self.verify()
        need(kind in ('uid', 'gid') and type(guest_id) is int and 0 <= guest_id < 4294967295,
            'EXACT_ANDROID_CREDENTIAL_ID')
        rows = [row for row in self.rows[kind] if row[0] <= guest_id < row[0] + row[2]]
        need(len(rows) == 1, 'ANDROID_CREDENTIAL_NOT_MAPPED_IN_HELD_MAIN')
        inside, outside, _ = rows[0]
        return guest_id if self.target_identity == self.observer_identity else outside + guest_id - inside

    def close(self):
        first = None; mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            for name in ('observer_user', 'target_user', 'pidfd', 'proc'):
                fd = getattr(self, name, None); setattr(self, name, None)
                if fd is not None:
                    try: os.close(fd)
                    except BaseException as error:
                        if first is None: first = error
                        else: first.add_note('OTHER_GUEST_NAMESPACE_FD_CLOSE:' + str(error))
            self.closed = True
        finally: signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if first is not None: raise first

class HeldProcess:
    def __init__(self, pid, uid, expected_executable_inode, *, target=None, guest_pid=None, package=None, sha256=None):
        self.proc = self.pidfd = self.exe = self.root = None; self.closed = False
        self.credentials = None; self.guest_uid = uid if target is not None else None
        try:
            if target is not None: self.credentials = GuestCredentials(target)
            observer_uid = uid if self.credentials is None else self.credentials.observer_id('uid', uid)
            self.proc = os.open('/proc/' + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.pidfd = os.pidfd_open(pid, 0); self.identity = process_state(self.proc, pid)
            need(self.identity['uids'] == [observer_uid] * 4 and self.identity['namespace_pids'][0] == pid,
                'EXACT_REAL_AUDIO_PROCESS_UID_AND_HOST_PID')
            self.exe = os.open('exe', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc)
            self.exe_identity = file_identity(os.fstat(self.exe))
            need(inode(os.fstat(self.exe)) == expected_executable_inode, 'ACTUAL_PROCESS_EXECUTES_EXPECTED_CURRENT_ELF_INODE')
            self.root = os.open('root', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.proc)
            self.root_identity = inode(os.fstat(self.root))
            if target is not None:
                need(guest_pid is not None and self.identity['namespace_pids'][-1] == guest_pid
                    and len(self.identity['namespace_pids']) >= 2, 'ACTUAL_GUEST_TO_HOST_PID_MAPPING')
                target.verify()
                expected_user_namespace = self.credentials.receipt['target_user_namespace']
                need(self.identity['namespaces']['user'] == expected_user_namespace, 'AUDIO_PROCESS_NOT_IN_THIS_HELD_MAIN:user')
                for key in ('pid', 'uts', 'ipc', 'net', 'cgroup'):
                    need(self.identity['namespaces'][key] == key + ':[' + str(os.fstat(target.namespaces[key]).st_ino) + ']',
                        'AUDIO_PROCESS_NOT_IN_THIS_HELD_MAIN:' + key)
                need(self.root_identity == inode(os.fstat(target.root_fd)), 'AUDIO_PROCESS_ROOT_NOT_THIS_HELD_MAIN')
                target.verify()
                self.credentials.verify_for(target)
            if package is not None:
                cmd = read_at(self.proc, 'cmdline', 131072).split(b'\0')
                need(cmd[0].decode('ascii', 'strict') == package, 'NO_SHARED_UID_OR_OTHER_APP_PROCESS_ATTRIBUTION')
            if sha256 is not None:
                info = os.fstat(self.exe); need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 33554432,
                    'BOUNDED_CURRENT_EXECUTABLE_HASH')
                h = hashlib.sha256(); offset = 0
                while offset < info.st_size:
                    b = os.pread(self.exe, min(65536, info.st_size - offset), offset); need(b, 'SHORT_CURRENT_EXECUTABLE')
                    h.update(b); offset += len(b)
                need(os.pread(self.exe, 1, offset) == b'' and h.hexdigest() == sha256, 'ACTUAL_EXECUTED_AUDIO_BYTES_NOT_QUALIFIED_SOURCE')
            self.verify()
        except BaseException:
            self.close(); raise

    def verify(self):
        need(not self.closed and self.pidfd is not None, 'HELD_AUDIO_PROCESS_CLOSED')
        if self.credentials is not None: self.credentials.verify()
        poll = select.poll(); poll.register(self.pidfd, select.POLLIN)
        need(not poll.poll(0) and process_state(self.proc, self.identity['host_pid']) == self.identity,
            'HELD_AUDIO_PROCESS_EXITED_OR_CHANGED')
        need(file_identity(os.fstat(self.exe)) == self.exe_identity, 'HELD_AUDIO_EXECUTABLE_CHANGED')
        for name, expected, flags in (('exe', inode(os.fstat(self.exe)), os.O_PATH),
                ('root', self.root_identity, os.O_PATH | os.O_DIRECTORY)):
            fd = os.open(name, flags | os.O_CLOEXEC, dir_fd=self.proc)
            try: need(inode(os.fstat(fd)) == expected, 'ACTUAL_NAMED_AUDIO_PROCESS_HANDLE_CHANGED')
            finally: os.close(fd)
        return copy.deepcopy(self.identity)

    def close(self):
        first = None; mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            if self.credentials is not None:
                try: self.credentials.close()
                except BaseException as error: first = error
                self.credentials = None
            for name in ('root', 'exe', 'pidfd', 'proc'):
                fd = getattr(self, name, None); setattr(self, name, None)
                if fd is not None:
                    try: os.close(fd)
                    except BaseException as error:
                        if first is None: first = error
                        else: first.add_note('OTHER_AUDIO_PROCESS_FD_CLOSE:' + str(error))
            self.closed = True
        finally: signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if first is not None: raise first

def find_guest(target, uid, *, guest_pid=None, executable_inode=None, deadline):
    credentials = GuestCredentials(target)
    try:
        observer_uid = credentials.observer_id('uid', uid)
        wanted_user = credentials.receipt['target_user_namespace']
        wanted_namespace = 'pid:[' + str(os.fstat(target.namespaces['pid']).st_ino) + ']'
        names = [n for n in os.listdir('/proc') if n.isdecimal()]
        need(len(names) <= 65536, 'BOUNDED_HOST_PID_DIRECTORY'); found = []
        for name in names:
            need(time.monotonic() < deadline, 'CURRENT_MAIN_PROCESS_SCAN_DEADLINE')
            proc = None
            try:
                proc = os.open('/proc/' + name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                if os.readlink('ns/pid', dir_fd=proc) != wanted_namespace: continue
                row = process_state(proc, int(name))
                if (row['namespaces']['user'] != wanted_user or row['uids'] != [observer_uid] * 4
                        or (guest_pid is not None and row['namespace_pids'][-1] != guest_pid)): continue
                if executable_inode is not None:
                    fd = os.open('exe', os.O_PATH | os.O_CLOEXEC, dir_fd=proc)
                    try: match = inode(os.fstat(fd)) == executable_inode
                    finally: os.close(fd)
                    if not match: continue
                found.append(row)
            except (FileNotFoundError, ProcessLookupError): pass
            finally:
                if proc is not None: os.close(proc)
        credentials.verify_for(target)
        need(len(found) == 1, 'ONE_EXACT_CURRENT_MAIN_PROCESS_FOR_AUDIO_ATTRIBUTION')
        return found[0]
    finally: credentials.close()

class AudioRuntime:
    def __init__(self, session):
        self.s = session; self.c = session.c; self.binding = session.components['camera_audio_binding.py']
        self.handles = {}; self.units = {}; self.host_intent = None; self.preflight_result = None
        self.hardware_before = None; self.windows = {}; self.samples = {}; self.closed = False
        self.failure_cleanup_attempted = self.failure_cleanup_unknown = False
        self.guest_credentials = None

    def credentials(self):
        need(not self.closed, 'CURRENT_AUDIO_RUNTIME_CLOSED')
        if self.guest_credentials is None:
            self.guest_credentials = GuestCredentials(self.s.flow.view.target)
        self.guest_credentials.verify_for(self.s.flow.view.target)
        return self.guest_credentials

    def admit_host(self, label, argv, timeout):
        need(self.host_intent == (label, list(argv), timeout), 'ONLY_CURRENT_READONLY_AUDIO_HOST_QUERY')
        self.host_intent = None

    def host(self, label, argv, timeout=10):
        need(not self.closed and self.host_intent is None and timeout in (10, 15), 'NO_REENTRANT_AUDIO_HOST_READ')
        self.host_intent = (label, list(argv), timeout)
        try: return self.s.host_read(label, list(argv), timeout)
        finally: self.host_intent = None

    def preflight(self):
        need(self.preflight_result is None, 'ONCE_FRESH_AUDIO_SOURCE_ADMISSION')
        s, c = self.s, self.c; s.guard(); manifest = s.baseline.docs['deployment_manifest']; life = manifest['audio_lifecycle']
        credentials = self.credentials()
        hal_uid, hal_gid = credentials.observer_id('uid', 1041), credentials.observer_id('gid', 1041)
        need(life['schema'] == 'pocket4-final-audio-lifecycle-v1' and life['helper_paths'] == {UNITS[role]: path for role, path in HELPERS.items()}
            and life['peer_uid'] == hal_uid and life['peer_gid'] == life['socket_gid'] == hal_gid
            and life['peer_cgroup'] == '/system.slice/droidloomd.service'
            and life['guest_endpoints'] == ['/dev/socket/droidloom/audio', '/dev/socket/droidloom/audio-input'],
            'EXACT_DEPLOYED_AUDIO_APEX_AND_SOCKET_CONTRACT')
        packet = c.parse(c.read_ref(life['source_qualification']))
        need(packet['schema'] == 'pocket4-audio-complete-source-qualification-v1'
            and packet['state'] == 'ACTUAL_SOURCE_QUALIFIED_RUNTIME_PENDING'
            and packet['runtime_qualified'] is False and packet['candidate_deployed'] is False
            and packet['original45_whole_app_accepted'] == 0 and all(packet['qualified'][k] is True for k in FLAGS),
            'COMPLETE_REAL_AUDIO_SOURCE_PACKET_REQUIRED_BEFORE_CURRENT_VIDEO')
        proof = c.parse(c.read_ref(packet['evidence']['apex_qualification']))
        need(proof['state'] == 'AUDIO_APEX_QUALIFIED_PENDING_FORMAL_RUNTIME' and proof['artifact_qualified'] is True
            and proof['runtime_qualified'] is False, 'EXACT_COMPLETE_AUDIO_APEX_ARTIFACT_PROOF')
        self.lifecycle = life; self.packet = packet; self.hal_source = proof['payload_files'][HAL_MEMBER]['reference']
        payload = {r['install_target']: r for r in manifest['payload']}
        for role, path in HELPERS.items():
            row = payload[path]; c.read_ref({'path': path, 'bytes': row['bytes'], 'sha256': row['sha256']}, 33554432)
            need(row['bytes'] == packet['files'][path]['bytes'] and row['sha256'] == packet['files'][path]['sha256'],
                'CURRENT_INSTALLED_HOST_HELPER_DIFFERS_FROM_QUALIFIED_COHORT')
        raw, meta = s.flow.view.target.read_file(HAL, 33554432, single_link=True)
        need(len(raw) == self.hal_source['bytes'] and c.sha(raw) == self.hal_source['sha256'],
            'CURRENT_MOUNTED_AUDIO_APEX_HAL_BYTES_DIFFER')
        self.hardware_before = self.hardware('before')
        before_start = time.monotonic_ns()
        before_audio = s.android(['/system/bin/dumpsys', 'media.audio_flinger'], 15)
        before_finish = time.monotonic_ns()
        need(type(before_audio) is bytes and 0 < len(before_audio) <= 1048576, 'BOUNDED_ACTUAL_AUDIOFLINGER_DUMP')
        before_audio_ref = s.tx.write_new(s.evidence_root / 'audio-flinger-before.txt', before_audio)
        parsed_before = self.binding.flinger(before_audio)
        quiet_before = self.binding.quiescent(parsed_before)
        self.preflight_result = s.record('current-audio-source-admission', {'source_qualification': life['source_qualification'],
            'apex_qualification': packet['evidence']['apex_qualification'], 'hal_source': self.hal_source,
            'actual_guest_hal_file': meta, 'hardware': self.hardware_before, 'audio_before': before_audio_ref,
            'guest_credential_map': credentials.receipt,
            'android_tracks_before': quiet_before,
            'started_monotonic_ns': before_start, 'finished_monotonic_ns': before_finish,
            'runtime_qualified': False,
            'historical_physical_receipt_used': False, 'settings_writes': 0})
        s.guard(); return self.preflight_result

    def hardware(self, label):
        result = {}
        for role, kind, name, port, stream, media in (
                ('input', 'sources', self.binding.SOURCE_NAME, self.binding.INPUT_PORT, 'capture', 'Audio/Source'),
                ('output', 'sinks', self.binding.SINK_NAME, self.binding.OUTPUT_PORT, 'playback', 'Audio/Sink')):
            raw, ref = self.host('audio-' + label + '-' + kind, PULSE_PREFIX + [kind])
            values = json.loads(raw); need(type(values) is list and len(values) <= 128, 'BOUNDED_ACTUAL_PULSE_ENDPOINTS')
            rows = [r for r in values if r.get('name') == name]; need(len(rows) == 1, 'ONE_ACTUAL_FIXED_PHYSICAL_AUDIO_ENDPOINT')
            r = rows[0]; props = r.get('properties', {})
            expected = {'device.api': 'alsa', 'device.class': 'sound', 'device.bus': 'pci',
                'device.bus_path': self.binding.BUS_PATH, 'api.alsa.pcm.stream': stream, 'media.class': media}
            need(all(props.get(k) == v for k, v in expected.items()) and r.get('active_port') == port
                and r.get('mute') is False and type(r.get('index')) is int and r['index'] >= 0
                and r.get('volume') and all(type(v.get('value')) is int and v['value'] > 0 for v in r['volume'].values()),
                'REAL_EXISTING_UNMUTED_PHYSICAL_ALSA_ROUTE_NO_WRITES')
            if role == 'input':
                need(r.get('monitor_of_sink') in (None, 4294967295) and r.get('monitor_of_sink_name') in (None, ''),
                    'PHYSICAL_MICROPHONE_CANNOT_BE_A_SINK_MONITOR')
            result[role] = {'current': {k: r.get(k) for k in ('index', 'name', 'mute', 'volume', 'active_port', 'sample_specification')},
                'properties': expected, 'observation': ref}
        return result

    def bind_guest(self, key, uid, guest_pid=None):
        s = self.s; target = s.flow.view.target; need(key not in self.handles, 'ONCE_CURRENT_GUEST_PROCESS_GENERATION')
        path = HAL if key == 'hal' else '/system/bin/app_process64'
        fd = target.open_root(path, os.O_PATH | os.O_CLOEXEC)
        try: expected = inode(os.fstat(fd))
        finally: os.close(fd)
        row = find_guest(target, uid, guest_pid=guest_pid, executable_inode=expected,
            deadline=min(time.monotonic() + 4, s.deadline))
        package = None if key == 'hal' else ('com.android.camera2' if key == 'camera' else 'com.android.gallery3d')
        handle = HeldProcess(row['host_pid'], uid, expected, target=target, guest_pid=row['namespace_pids'][-1],
            package=package, sha256=self.hal_source['sha256'] if key == 'hal' else None)
        self.handles[key] = handle; need(handle.identity == row, 'SAME_GUEST_GENERATION_DURING_HELD_BINDING')
        credentials = self.credentials()
        need(handle.credentials.receipt == credentials.receipt, 'SAME_CURRENT_MAIN_CREDENTIAL_MAP_FOR_AUDIO')
        if key == 'hal': need(handle.identity['gids'] == [credentials.observer_id('gid', 1041)] * 4
            and handle.identity['cgroup'] == ['0::' + self.lifecycle['peer_cgroup']],
            'EXACT_HAL_UID_GID_AND_MANAGER_CGROUP_FOR_SO_PEERPIDFD')
        return handle

    def helper(self, role):
        raw, ref = self.host('audio-helper-' + role, ['/usr/bin/systemctl', 'show', UNITS[role], '--property=' + PROPERTIES])
        lines = raw.decode('utf-8', 'strict').splitlines(); pairs = [x.split('=', 1) for x in lines if x]
        need(all(len(p) == 2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs), 'COMPLETE_CURRENT_AUDIO_UNIT_FIELDS')
        v = dict(pairs); need(set(v) == set(PROPERTIES.split(',')) and v['Id'] == UNITS[role]
            and v['LoadState'] == 'loaded' and v['ActiveState'] == 'active' and v['SubState'] == 'running'
            and v['ControlPID'] == '0' and re.fullmatch('[1-9][0-9]+', v['MainPID'])
            and v['ControlGroup'] == '/system.slice/' + UNITS[role] and re.fullmatch('[0-9a-f]{32}', v['InvocationID'])
            and v['FragmentPath'] == '/usr/lib/systemd/system/' + UNITS[role] and HELPERS[role] in v['ExecStart'],
            'ACTUAL_CURRENT_AUDIO_HELPER_UNIT_GENERATION')
        if role in self.units:
            need(v == self.units[role]['value'], 'AUDIO_HELPER_RESTART_OR_UNIT_DRIFT')
            self.handles[role].verify()
        else:
            path = Path(HELPERS[role]); info = path.stat(); source = self.packet['files'][str(path)]
            handle = HeldProcess(int(v['MainPID']), 1000, inode(info), sha256=source['sha256'])
            self.handles[role] = handle
            need(handle.identity['gids'] == [1000] * 4 and handle.identity['cgroup'] == ['0::' + v['ControlGroup']],
                'CURRENT_HELPER_UID_GID_AND_EXACT_SERVICE_CGROUP')
            need(handle.identity['namespaces']['user'] == self.credentials().receipt['observer_user_namespace'],
                'AUDIO_HELPER_AND_PROCESS_OBSERVER_MUST_USE_SAME_CREDENTIAL_NAMESPACE')
            need(handle.identity['namespaces']['pid'] == os.readlink('/proc/thread-self/ns/pid'),
                'AUDIO_HELPER_AND_PROCESS_OBSERVER_MUST_USE_SAME_PID_NAMESPACE')
            self.units[role] = {'value': v, 'observation': ref, 'process': handle.identity}
        return v

    def snapshot(self, role, label):
        need(self.preflight_result is not None and role in ('input', 'output'), 'CURRENT_AUDIO_PREFLIGHT_REQUIRED')
        s = self.s; s.guard(); start = time.monotonic_ns()
        raw = s.android(['/system/bin/dumpsys', 'media.audio_flinger'], 15)
        finish = time.monotonic_ns()
        need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_ACTUAL_AUDIOFLINGER_DUMP')
        rawref = s.tx.write_new(s.evidence_root / (label + '-flinger.txt'), raw)
        dump = self.binding.flinger(raw)
        uid, key = (10062, 'camera') if role == 'input' else (10064, 'player')
        direction = 'Input' if role == 'input' else 'Output'
        candidates = [t for thread in dump['threads'] if thread['direction'] == direction for t in thread['tracks']
            if t['active'] and t['uid'] == uid]
        need(len(candidates) == 1, 'ONE_CURRENT_BUSINESS_APP_AUDIO_TRACK')
        guest = candidates[0]['pid']
        track = self.binding.owned_track(dump, direction=direction, uid=uid, pid=guest)
        if key not in self.handles: self.bind_guest(key, uid, guest)
        h = self.handles[key]; h.verify(); need(h.identity['namespace_pids'][-1] == guest, 'SAME_AUDIOFLINGER_APP_PID')
        if 'hal' not in self.handles: self.bind_guest('hal', 1041)
        self.handles['hal'].verify(); unit = self.helper(role)
        value = {'role': role, 'label': label, 'started_monotonic_ns': start, 'finished_monotonic_ns': finish,
            'flinger': dump, 'raw': rawref, 'selected': track, 'app': h.identity,
            'guest_credential_map': self.credentials().receipt,
            'activity_scope': 'one-active-android-track-all-uids-at-this-sample',
            'host_audio_quiescence_qualified': False, 'continuous_exclusivity_qualified': False,
            'hal': self.handles['hal'].identity, 'helper': self.units[role], 'scope': s.flow.scope_ref,
            'phase': s.phase_ref, 'runtime_qualified': False}
        value['reference'] = s.record(label + '-audio-runtime', value); s.guard(); return value

    def window(self, role, first, second):
        s = self.s; uid, direction = (10062, 'Input') if role == 'input' else (10064, 'Output')
        need(first['role'] == second['role'] == role and first['scope'] == second['scope'] == s.flow.scope_ref
            and first['phase'] == second['phase'] == s.phase_ref and first['app'] == second['app']
            and first['guest_credential_map'] == second['guest_credential_map'] == self.credentials().receipt
            and first['hal'] == second['hal'] and first['helper']['value'] == second['helper']['value'],
            'SAME_CURRENT_APP_HAL_HELPER_AND_SCOPE_DURING_AUDIO')
        live = self.binding.advancing(first['flinger'], second['flinger'], direction=direction, uid=uid,
            pid=first['app']['namespace_pids'][-1],
            elapsed_ns=second['finished_monotonic_ns'] - first['finished_monotonic_ns'])
        unit = self.helper(role); start = first['started_monotonic_ns']; end = second['finished_monotonic_ns']
        argv = ['/usr/bin/journalctl', '--no-pager', '-o', 'json', '-n', '8192',
            '_SYSTEMD_UNIT=' + UNITS[role], '_SYSTEMD_INVOCATION_ID=' + unit['InvocationID'],
            '_PID=' + unit['MainPID'], '_BOOT_ID=' + s.host.boot().replace('-', '')]
        raw, logref = self.host('audio-current-protocol-' + role, argv, 15)
        document = self.binding.journal(raw, unit=UNITS[role], invocation=unit['InvocationID'],
            manager_pid=int(unit['MainPID']), boot_id=s.host.boot())
        protocol = self.binding.protocol_window(document, role=role, hal_pid=self.handles['hal'].identity['host_pid'],
            hal_uid=self.credentials().observer_id('uid', 1041), hal_gid=self.credentials().observer_id('gid', 1041),
            hal_cgroup=self.lifecycle['peer_cgroup'], begin_ns=start, end_ns=end)
        stream = self.pulse_stream(role, protocol['stream_ready'], int(unit['MainPID']))
        value = {'schema': 'pocket4-current-camera-audio-runtime-window-v1', 'role': role,
            'source_admission': self.preflight_result, 'first': first['reference'], 'second': second['reference'],
            'scope': s.flow.scope_ref, 'phase': s.phase_ref, 'epoch_sha256': s.active['framework_epoch_sha256'],
            'actual_app_frames': live, 'actual_hal_helper_protocol': protocol, 'journal': logref,
            'actual_physical_stream': stream, 'host_nonce_or_old_runtime_receipt_used': False,
            'runtime_qualified': False, 'whole_app_business_accepted': False}
        ref = s.record(role + '-actual-audio-window', value); self.windows[role] = ref; return value, ref

    def pulse_stream(self, role, ready, pid):
        kind = 'source-outputs' if role == 'input' else 'sink-inputs'
        raw, ref = self.host('audio-current-' + kind, PULSE_PREFIX + [kind])
        values = json.loads(raw); need(type(values) is list and len(values) <= 256, 'BOUNDED_ACTUAL_PULSE_STREAMS')
        rows = [r for r in values if r.get('properties', {}).get('application.process.id') == str(pid)]
        need(len(rows) == 1, 'ONE_ACTUAL_HELD_HELPER_PULSE_STREAM')
        row = rows[0]; endpoint = 'source' if role == 'input' else 'sink'
        expected = self.hardware_before[role]['current']
        need(type(row.get('index')) is int and row.get(endpoint) == expected['index']
            and row.get('corked') is False and row.get('mute') is False,
            'ACTUAL_UNCORKED_UNMUTED_HELPER_ON_FIXED_PHYSICAL_DEVICE')
        if role == 'output': need(row['index'] == ready['pulse_stream_index'], 'PROTOCOL_OUTPUT_INDEX_AND_PULSE_ROUTE_DISAGREE')
        else: need(ready['source_index'] == row['source'], 'PROTOCOL_INPUT_SOURCE_AND_PULSE_ROUTE_DISAGREE')
        now = self.hardware('during-' + role)
        need(all(now[r]['current'] == self.hardware_before[r]['current'] and now[r]['properties'] == self.hardware_before[r]['properties']
            for r in ('input', 'output')), 'PHYSICAL_AUDIO_ROUTE_OR_EXISTING_VOLUME_CHANGED')
        return {'observation': ref, 'stream': row, 'hardware': now}

    def verify_final(self):
        s = self.s; need(set(self.windows) == {'input', 'output'}, 'BOTH_CURRENT_HAL_AUDIO_WINDOWS_REQUIRED')
        s.guard(); start = time.monotonic_ns()
        raw = s.android(['/system/bin/dumpsys', 'media.audio_flinger'], 15)
        finish = time.monotonic_ns()
        need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_ACTUAL_AUDIOFLINGER_DUMP')
        rawref = s.tx.write_new(s.evidence_root / 'audio-flinger-after.txt', raw)
        parsed = self.binding.flinger(raw); quiet_after = self.binding.quiescent(parsed)
        after = self.hardware('after')
        need(all(after[r]['current'] == self.hardware_before[r]['current'] and after[r]['properties'] == self.hardware_before[r]['properties']
            for r in ('input', 'output')), 'PRESERVE_PREEXISTING_PHYSICAL_AUDIO_ROUTING_AND_VOLUME')
        s.guard()
        return s.record('audio-final', {'source_admission': self.preflight_result, 'windows': self.windows,
            'audio_after': rawref, 'android_tracks_after': quiet_after,
            'started_monotonic_ns': start, 'finished_monotonic_ns': finish,
            'hardware_before': self.hardware_before, 'hardware_after': after,
            'settings_writes': 0, 'application_processes_signalled': 0, 'runtime_qualified': False})

    def verify_failure_cleanup(self):
        """One Android track sample after known task/host cleanup, never a window.

        Incomplete admission, pending effects, host UNKNOWN and unfinished
        acoustic actors admit no new query. Existing held transport/poison and
        absolute cleanup deadline gates remain authoritative.
        """
        s = self.s; driver = s.driver
        s.original_caller(['camera_video_driver.py'], {'finish'})
        need(not self.closed and self.preflight_result is not None
            and self.hardware_before is not None, 'COMPLETE_AUDIO_PREFLIGHT_BEFORE_FAILURE_QUIET')
        need(s.phase_name == 'final_cleanup' and s.active_api is None
            and s.ordinary_admission is None and s.ui_dispatch_admission is None,
            'ONLY_CURRENT_FINAL_CLEANUP_AUDIO_SAMPLE')
        need(driver is not None and driver.run_completed is False and driver.cleanup_verified is True
            and driver.owned is driver.pending is driver.close_pending is None
            and (driver.recording is None or driver.recording.pending is None)
            and driver.host_unknown is False
            and (driver.decoder is None or driver.decoder.unknown is False),
            'KNOWN_TASK_AND_HOST_RETIREMENT_BEFORE_FAILURE_QUIET')
        acoustic = s.acoustic; order = s.components['camera_audio_channel.py'].ORDER
        need(not acoustic.closed and acoustic.pending is None
            and tuple(acoustic.results) == order[:len(acoustic.results)]
            and acoustic.sequence == len(acoustic.results) in (0, 3, 6),
            'NO_PENDING_OR_UNFINISHED_ACOUSTIC_ACTOR_BEFORE_FAILURE_QUIET')
        retired = {}
        for role in ('emit', 'listen'):
            if role + '_prepare' not in acoustic.results: continue
            row = acoustic.results[role + '_finish']; ref = row['reference']
            need(Path(ref['path']) == s.root / 'acoustic-supervisor' / (role + '-final.json'),
                'ONLY_THIS_CASE_ACOUSTIC_RETIREMENT_RECORD')
            need(s.c.parse(s.c.read_ref(ref)) == {k: v for k, v in row.items() if k != 'reference'}
                and row['role'] == role and row['parent'] == acoustic.parent_ref
                and row['phase'] == driver.result['actual_business_phase']
                and row['leader_reaped'] is True and type(row['exit_code']) is int and row['exit_code'] == 0
                and row['pipe_eof'] == {'stdout': True, 'stderr': True}
                and all(v is True for v in row['pipe_eof'].values())
                and row['closed']['stream_closed'] is True and row['closed']['nonce'] == s.active['audio_nonce']
                and row['closed']['runtime_qualified'] is False and row['automatic_retry'] is False,
                'ACTUAL_RETIRED_CURRENT_ACOUSTIC_ACTOR_BEFORE_FAILURE_QUIET')
            retired[role] = ref
        need(not self.failure_cleanup_attempted, 'ONCE_FAILURE_PATH_AUDIO_SAMPLE_NO_RETRY')
        acoustic.verify(); s.guard()
        need(time.monotonic() + 15 < s.deadline, 'ORIGINAL_CLEANUP_BUDGET_FOR_FAILURE_AUDIO_SAMPLE')
        self.failure_cleanup_attempted = self.failure_cleanup_unknown = True
        start = time.monotonic_ns()
        raw = s.android(['/system/bin/dumpsys', 'media.audio_flinger'], 15)
        finish = time.monotonic_ns(); self.failure_cleanup_unknown = False
        need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_ACTUAL_AUDIOFLINGER_DUMP')
        rawref = s.tx.write_new(s.evidence_root / 'audio-flinger-failure-cleanup.txt', raw)
        parsed = self.binding.flinger(raw); quiet = self.binding.quiescent(parsed)
        acoustic.verify(); s.guard()
        return s.record('audio-failure-cleanup', {
            'source_admission': self.preflight_result, 'phase': s.phase_ref,
            'scope': s.flow.scope_ref, 'audio_after': rawref, 'android_tracks_after': quiet,
            'started_monotonic_ns': start, 'finished_monotonic_ns': finish,
            'owned_task_cleanup_verified': True, 'acoustic_retirement': retired,
            'business_audio_windows_observed': dict(self.windows),
            'failure_path_android_audio_quiet_verified': True,
            'host_audio_quiescence_qualified': False, 'continuous_exclusivity_qualified': False,
            'inactive_audio_session_preservation_qualified': False, 'audio_focus_preservation_qualified': False,
            'actual_full_dumpsys_ABI_qualified': False,
            'settings_writes': 0, 'application_processes_signalled': 0, 'automatic_retry': False,
            'runtime_qualified': False, 'whole_app_business_accepted': False})

    def close(self):
        errors = []
        for key, handle in reversed(list(self.handles.items())):
            try: handle.close()
            except BaseException as error: errors.append((key, error))
        if self.guest_credentials is not None:
            try: self.guest_credentials.close()
            except BaseException as error: errors.append(('guest_credentials', error))
            self.guest_credentials = None
        self.closed = True
        if errors:
            first = errors[0][1]
            for key, other in errors[1:]: first.add_note('OTHER_AUDIO_HANDLE_CLOSE:' + key + ':' + str(other))
            raise first
