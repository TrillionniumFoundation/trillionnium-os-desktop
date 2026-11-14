#!/usr/bin/python3 -I
"""Finite host-only qualification of the exact r4 decoder and owned reaper.

No Main, Android, service, account, camera or audio-device operation exists here.
The normal Decoder class and both capture sources run unchanged. Session fields
are explicitly synthetic host fixtures and cannot qualify a live business case.
"""
import argparse
import ast
import copy
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import types

CONTROLS = ('normal_decoder_and_fresh_nonce', 'uid1000_and_exact_two_fds',
    'all_seals_and_denied_write_metadata', 'malformed_mov_known_failure',
    'actual_timeout_and_owned_retirement', 'actual_output_bound_and_retirement',
    'actual_adopted_descendant_retirement', 'actual_finish_fault_keeps_unknown')
CAPTURE_PATH = '/home/alex/work/pocket4-android-final/qualification/bounded_host_capture.py'
LIFECYCLE_PATH = '/home/alex/work/pocket4-android-final/framework/runtime_support/capture_lifecycle.py'
COMMANDS_PATH = '/home/alex/work/pocket4-android-final/qualification/business-support-host-20261108-r1/business_commands.py'
IDENTITY_KEYS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')

# All helper code is fixed in this externally pinned runner, never caller input.
# It executes only as the UID-1000 child of the real fixed capture implementation.
HELPER = r'''
import errno,fcntl,hashlib,json,os,resource,sys,time
mode, fd, tool = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
def digest():
 n=os.fstat(fd).st_size;raw=os.pread(fd,n,0)
 assert len(raw)==n and os.pread(fd,1,n)==b''
 return hashlib.sha256(raw).hexdigest()
def identity():
 s=os.fstat(fd)
 return {k:getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
def emit(value):os.write(1,(json.dumps(value,sort_keys=True)+'\n').encode())
if mode=='attest':
 fields={line.split(':',1)[0]:line.split(':',1)[1].split() for line in open('/proc/self/status') if ':' in line}
 descriptors=[]
 for name in os.listdir('/proc/self/fd'):
  try:os.fstat(int(name));descriptors.append(int(name))
  except OSError as error:
   if error.errno!=errno.EBADF:raise
 try:os.open(sys.argv[4],os.O_RDONLY|os.O_CLOEXEC);raise RuntimeError('ORIGINAL_ROOT_FILE_READABLE')
 except PermissionError as error:original_errno=error.errno
 ro=os.open('/proc/self/fd/'+str(fd),os.O_RDONLY|os.O_CLOEXEC)
 try:
  ro_mode=fcntl.fcntl(ro,fcntl.F_GETFL)&os.O_ACCMODE;assert ro_mode==os.O_RDONLY
  ro_hash=hashlib.sha256(os.pread(ro,os.fstat(ro).st_size,0)).hexdigest()
 finally:os.close(ro)
 emit({'uids':list(map(int,fields['Uid'])),'gids':list(map(int,fields['Gid'])),
  'groups':os.getgroups(),'no_new_privs':fields['NoNewPrivs'],
  'core_limit':list(resource.getrlimit(resource.RLIMIT_CORE)),'fds':sorted(descriptors),
  'expected_fds':sorted([0,1,2,fd,tool]),'clip_identity':identity(),'clip_sha256':digest(),
  'inherited_access_mode':fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE,'readonly_view_access_mode':ro_mode,
  'readonly_view_sha256':ro_hash,'seals':fcntl.fcntl(fd,fcntl.F_GET_SEALS),
  'original_root_file_errno':original_errno})
elif mode=='seals':
 before=identity();initial=digest();rows=[]
 ro=os.open('/proc/self/fd/'+str(fd),os.O_RDONLY|os.O_CLOEXEC)
 try:
  operations=(('readonly_write',lambda:os.write(ro,b'X'),errno.EBADF),
   ('shrink',lambda:os.ftruncate(fd,before['st_size']-1),errno.EPERM),
   ('grow',lambda:os.ftruncate(fd,before['st_size']+1),errno.EPERM),
   ('pwrite',lambda:os.pwrite(fd,b'X',0),errno.EPERM))
  for name,action,wanted in operations:
   old=identity()
   try:action();raise RuntimeError('SEALED_WRITE_SUCCEEDED:'+name)
   except OSError as error:assert error.errno==wanted;actual=error.errno
   after=identity();changed=[key for key in old if old[key]!=after[key]]
   assert set(changed)<=set(('st_mtime_ns','st_ctime_ns'))
   assert after['st_size']==before['st_size'] and digest()==initial
   assert fcntl.fcntl(fd,fcntl.F_GET_SEALS)==15
   rows.append({'operation':name,'errno':actual,'before':old,'after':after,'changed':changed,
    'sha256':digest(),'seals':fcntl.fcntl(fd,fcntl.F_GET_SEALS)})
 finally:os.close(ro)
 emit({'before':before,'after':identity(),'sha256':digest(),'operations':rows})
elif mode=='sleep':
 os.write(1,b'owned timeout child ready\n');time.sleep(10)
elif mode=='overflow':
 os.write(1,b'X'*1025);time.sleep(10)
elif mode=='descendant':
 r,w=os.pipe();child=os.fork()
 if child==0:
  os.close(r);os.setsid();os.write(w,b'R');os.close(w);time.sleep(30);os._exit(0)
 os.close(w);assert os.read(r,1)==b'R';os.close(r)
 emit({'owned_descendant':child});os._exit(0)
else:raise RuntimeError('NO_OTHER_FIXED_HOST_CONTROL')
'''


def need(value, message):
    if not value: raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {key: getattr(info, key) for key in IDENTITY_KEYS}


def parse(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'DUPLICATE_CONTROL_JSON_KEY'); out[key] = value
        return out
    def nonfinite(value): raise RuntimeError('NONFINITE_CONTROL_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def read(path, expected=None, maximum=33554432):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'CANONICAL_CONTROL_INPUT')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= maximum,
            'BOUNDED_REGULAR_SINGLE_LINK_CONTROL_INPUT')
        raw = bytearray()
        while len(raw) < before.st_size:
            block = os.read(fd, min(65536, before.st_size - len(raw)))
            need(block, 'SHORT_CONTROL_INPUT'); raw.extend(block)
        need(os.read(fd, 1) == b'' and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
            'CONTROL_INPUT_CHANGED_DURING_READ')
    finally: os.close(fd)
    value = {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
    need(expected is None or (value['bytes'], value['sha256']) == (expected['bytes'], expected['sha256']),
        'EXACT_CONTROL_SOURCE_PIN:' + path.name)
    return bytes(raw), value


def write_new(path, value, mode=0o600):
    path = Path(path)
    raw = value if type(value) is bytes else (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        rest = memoryview(raw)
        while rest:
            n = os.write(fd, rest); need(n > 0, 'CONTROL_WRITE_NO_PROGRESS'); rest = rest[n:]
        os.fsync(fd)
    finally: os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try: os.fsync(parent)
    finally: os.close(parent)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def load(raw, path, name):
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def fd_snapshot():
    values = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            info = os.fstat(int(name)); values[int(name)] = (info.st_dev, info.st_ino, info.st_mode)
        except OSError as error:
            if error.errno != errno.EBADF: raise
    return values


def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    lib = ctypes.CDLL(None, use_errno=True)
    if lib.prctl(38, 1, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), 'PR_SET_NO_NEW_PRIVS')


def cgroup_text(group, name):
    fd = os.open(group / name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        raw = bytearray()
        while True:
            block = os.read(fd, min(4096, 8193 - len(raw)))
            if not block: break
            raw.extend(block); need(len(raw) <= 8192, 'BOUNDED_OWN_CGROUP_FIELD:' + name)
        return raw.decode('ascii', 'strict').strip()
    finally: os.close(fd)


def resource_snapshot(expected_cgroup):
    need(Path('/proc/self/cgroup').read_text().splitlines() == ['0::' + expected_cgroup],
        'SELF_REMAINS_IN_THE_EXACT_CONTROL_CGROUP')
    group = Path('/sys/fs/cgroup') / expected_cgroup.lstrip('/')
    info = group.lstat(); need(stat.S_ISDIR(info.st_mode), 'ACTUAL_OWN_CGROUP_DIRECTORY')
    started = time.monotonic_ns()
    def number(name, optional=False):
        try: value = cgroup_text(group, name)
        except FileNotFoundError:
            if optional: return None
            raise
        need(value.isdecimal(), 'EXACT_NUMERIC_OWN_CGROUP_FIELD:' + name); return int(value)
    def events(name):
        rows = [line.split() for line in cgroup_text(group, name).splitlines()]
        need(rows and all(len(row) == 2 and row[1].isdecimal() for row in rows)
            and len({row[0] for row in rows}) == len(rows), 'EXACT_OWN_CGROUP_EVENTS:' + name)
        return {key: int(value) for key, value in rows}
    quota, period = cgroup_text(group, 'cpu.max').split()
    value = {'cgroup': expected_cgroup, 'directory_identity': {'device': info.st_dev, 'inode': info.st_ino},
        'cpu_max': [quota, period], 'cpu_affinity': sorted(os.sched_getaffinity(0)),
        'memory_max': number('memory.max'), 'memory_current': number('memory.current'),
        'memory_peak': number('memory.peak'), 'memory_events': events('memory.events'),
        'swap_max': number('memory.swap.max'), 'swap_current': number('memory.swap.current'),
        'swap_peak': number('memory.swap.peak', optional=True), 'swap_events': events('memory.swap.events'),
        'tasks_max': number('pids.max'), 'tasks_current': number('pids.current'),
        'tasks_peak': number('pids.peak', optional=True), 'tasks_events': events('pids.events'),
        'started_monotonic_ns': started, 'finished_monotonic_ns': time.monotonic_ns()}
    after = group.lstat()
    need((after.st_dev, after.st_ino) == (info.st_dev, info.st_ino), 'SAME_OWN_CGROUP_DURING_OBSERVATION')
    return value


def resource_valid(value, before=None):
    quota, period = value['cpu_max']
    need(quota.isdecimal() and period.isdecimal() and 0 < int(quota) <= int(period)
        and value['cpu_affinity'] == [2], 'MAXIMUM_ONE_CPU_ON_REVIEWED_CPU2')
    need(67108864 <= value['memory_max'] <= 536870912 and value['swap_max'] == 0
        and 8 <= value['tasks_max'] <= 128, 'BOUNDED_CONTROL_MEMORY_SWAP_AND_TASKS')
    need({'max', 'oom', 'oom_kill'} <= set(value['memory_events'])
        and all(n == 0 for n in value['memory_events'].values()), 'NO_CONTROL_MEMORY_MAX_PRESSURE_OR_OOM_EVENTS')
    need({'max', 'fail'} <= set(value['swap_events']) and all(n == 0 for n in value['swap_events'].values())
        and value['swap_current'] == 0 and value['swap_peak'] in (None, 0), 'NO_CONTROL_SWAP_USE_OR_EVENTS')
    need('max' in value['tasks_events'] and all(n == 0 for n in value['tasks_events'].values()), 'NO_CONTROL_PIDS_LIMIT_EVENTS')
    need(0 <= value['memory_current'] <= value['memory_peak'] <= value['memory_max']
        and 1 <= value['tasks_current'] <= value['tasks_max']
        and (value['tasks_peak'] is None or value['tasks_peak'] <= value['tasks_max']), 'ACTUAL_RESOURCE_PEAKS_WITHIN_LIMITS')
    if before is not None:
        need(all(value[key] == before[key] for key in ('cgroup', 'directory_identity', 'cpu_max', 'cpu_affinity',
            'memory_max', 'swap_max', 'tasks_max')), 'SAME_DEDICATED_CGROUP_AND_RESOURCE_LIMITS')


def resource_admission(expected_cgroup, record_to=None):
    need(sys.platform == 'linux' and os.getuid() == os.geteuid() == 0, 'ROOT_LINUX_HOST_COMPONENT_ONLY')
    pid = os.getpid(); task = Path('/proc/%d/task' % pid)
    need(task.is_dir() and [p.name for p in task.iterdir()] == [str(pid)], 'ACTUAL_SELF_PID_AND_SINGLE_THREAD_PROC')
    need(re.fullmatch(r'/system\.slice/p4-camera-r4-decoder-host-[a-zA-Z0-9_-]+\.service', expected_cgroup or ''),
        'DEDICATED_REVIEWED_HOST_CONTROL_UNIT_REQUIRED')
    observed = resource_snapshot(expected_cgroup)
    if record_to is not None: record_to['resource_admission_observation'] = observed
    resource_valid(observed)
    for name in ('F_ADD_SEALS', 'F_GET_SEALS', 'F_SEAL_WRITE', 'F_SEAL_GROW', 'F_SEAL_SHRINK', 'F_SEAL_SEAL'):
        need(hasattr(fcntl, name), 'REAL_LINUX_SEAL_API:' + name)
    need(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL, 'DEFAULT_SIGCHLD_OWNERSHIP')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    need(status.get('NoNewPrivs', '').strip() == '1', 'CONTROL_UNIT_NO_NEW_PRIVILEGES')
    return {'pid': pid, 'uid': os.geteuid(), 'cgroup': expected_cgroup, 'observation': observed}


class Common:
    need = staticmethod(need)
    sha = staticmethod(sha)

    def __init__(self, owner, capture):
        self.owner = owner; self.capture = capture

    def module(self, ref, name):
        need(ref == self.owner.packet['fixed_sources']['capture'], 'ONLY_REAL_PINNED_CAPTURE_IMPORT')
        read(ref['path'], ref); return self.capture

    def write_new(self, path, value, mode=0o600):
        path = Path(path)
        need(path.is_absolute() and path.parent.resolve() == path.parent and path.is_relative_to(self.owner.output),
            'ONLY_NEW_HOST_CONTROL_EVIDENCE')
        return write_new(path, value, mode)


class HostOnlySession:
    """Local temporary media/source guards. This is deliberately not a Main."""
    def __init__(self, owner, label, raw, nonce=None, capture=None):
        self.owner = owner; self.closed = False; self.sequence = 0
        self.c = Common(owner, capture or owner.capture)
        self.root = Path(tempfile.mkdtemp(prefix=label + '-', dir=owner.output))
        self.evidence_root = self.root / 'evidence'; self.evidence_root.mkdir(mode=0o700)
        self.phase_name = 'business'; self.deadline = min(time.monotonic() + 12, owner.deadline)
        self.components = {'camera_video_media.py': owner.media, 'camera_audio_challenge.py': owner.challenge}
        self.flow = types.SimpleNamespace(modules={'business_commands.py': owner.commands},
            scope_ref={'schema': 'host-synthetic-no-Main-scope', 'case': label})
        self.phase_ref = {'schema': 'host-synthetic-no-Main-phase', 'case': label}
        self.baseline = types.SimpleNamespace(protected_pids=owner.protected)
        self.active = {'case_root': str(self.root), 'audio_nonce': nonce or '0000000000000001',
            'framework_epoch_sha256': 'HOST_SYNTHETIC_NO_MAIN_EPOCH'}
        self.clip = self.c.write_new(self.evidence_root / 'owned-camera-video.mp4', raw, 0o400)
        self.owned_video = {'uri': 'content://media/external_primary/video/media/73', '_id': 73,
            '_size': len(raw), 'file_sha256': sha(raw), 'is_pending': 0, 'width': 32, 'height': 32,
            'duration': 4000, 'mime_type': 'video/mp4', 'owner_package_name': 'com.android.camera2'}
        self.decoder = None
        try:
            self.decoder = owner.decode.Decoder(self, self.clip, self.owned_video)
        except BaseException as primary:
            # The production constructor closes its own FDs. This controller
            # separately owns the temporary input it created before that call.
            self.closed = True
            try:
                read(self.clip['path'], self.clip); Path(self.clip['path']).unlink()
            except BaseException as secondary:
                primary.add_note('HOST_INPUT_CONSTRUCTION_CLEANUP:' + repr(secondary))
            raise

    def guard(self):
        need(not self.closed and time.monotonic() < self.owner.deadline, 'FINITE_OPEN_HOST_ONLY_SESSION')
        self.owner.sources_unchanged()
        return {'host_only_sources_unchanged': True, 'Main_actions': 0}

    def record(self, label, value):
        self.sequence += 1
        need(self.sequence <= 64 and re.fullmatch('[a-zA-Z0-9_-]{1,96}', label), 'FINITE_HOST_ONLY_RECORDS')
        return self.c.write_new(self.evidence_root / ('%03d-%s.json' % (self.sequence, label)), value)

    def close(self):
        first = None
        try:
            if self.decoder is not None: self.decoder.close()
        except BaseException as error: first = error
        self.closed = True
        # Synthetic inputs are not retained artifacts or usable runtime receipts.
        try:
            read(self.clip['path'], self.clip); Path(self.clip['path']).unlink()
        except BaseException as error:
            if first is None: first = error
            else: first.add_note('HOST_INPUT_CLOSE_CLEANUP:' + repr(error))
        if first is not None: raise first


class Qualification:
    def __init__(self, packet, sources, output, resource_record):
        self.packet, self.sources, self.output = packet, sources, output
        self.resource_record = resource_record; self.deadline = time.monotonic() + 65
        self.protected = tuple(sorted({1, os.getppid()} - {os.getpid()}))
        self.commands = load(*sources['commands'][:2], 'host_qualified_business_commands')
        self.capture = load(*sources['capture'][:2], 'host_qualified_bounded_capture')
        self.decode = load(*sources['camera_decode.py'][:2], 'host_qualified_camera_decode')
        self.media = load(*sources['camera_video_media.py'][:2], 'host_qualified_camera_media')
        self.challenge = load(*sources['camera_audio_challenge.py'][:2], 'host_qualified_camera_challenge')
        need(str(self.capture.SOURCE_LIFECYCLE_PATH) == LIFECYCLE_PATH
            and self.capture.SOURCE_LIFECYCLE_SHA == packet['fixed_sources']['lifecycle']['sha256'],
            'UNMODIFIED_CAPTURE_TRANSITIVE_LIFECYCLE_BINDING')
        self.lifecycle = self.capture.load_source_lifecycle()
        self.initial = self.capture.OwnChildReaper(protected_pids=self.protected)
        self.initial.empty(); self.initial_flag = self.initial.flag(); self.initial_fds = fd_snapshot()
        self.tools = {}; self.children = []; self.synthetic = None; self.nonce = secrets.token_hex(8)
        need(self.nonce != '0000000000000000', 'FRESH_NONZERO_HOST_NONCE_WITHOUT_RETRY')
        for path in ('/usr/bin/ffmpeg', '/usr/bin/ffprobe', str(Path('/usr/bin/python3').resolve())):
            raw, ref = read(path); info = Path(path).stat()
            need(info.st_uid == 0 and not info.st_mode & 0o022 and info.st_mode & 0o111 and raw[:6] == b'\x7fELF\x02\x01',
                'CURRENT_ROOT_OWNED_X86_64_HOST_TOOL')
            self.tools[path] = ref
        self.python = str(Path('/usr/bin/python3').resolve())

    def sources_unchanged(self):
        for raw, path, ref in self.sources.values(): read(path, ref)
        for path, ref in self.tools.items(): read(path, ref)

    def idle(self):
        self.initial.empty(); need(self.initial.flag() == self.initial_flag, 'ORIGINAL_SUBREAPER_STATE_RESTORED')
        need(fd_snapshot() == self.initial_fds, 'NO_CONTROL_DESCRIPTOR_LEAK')
        self.sources_unchanged()

    def held_factory(self, argv, clip_fd, tool_fd):
        need(argv[0] in self.tools and clip_fd != tool_fd and min(clip_fd, tool_fd) >= 3, 'EXACT_TWO_HOST_CONTROL_FDS')
        def factory(input_fd, stdout_fd, stderr_fd, output_bound):
            need(time.monotonic() < self.deadline, 'HOST_CONTROL_GLOBAL_DEADLINE')
            return subprocess.Popen(argv, executable='/proc/self/fd/' + str(tool_fd),
                stdin=input_fd, stdout=stdout_fd, stderr=stderr_fd, close_fds=True,
                pass_fds=(clip_fd, tool_fd), start_new_session=True,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/home/alex'},
                user=1000, group=1000, extra_groups=(), preexec_fn=limits)
        return factory

    def owned(self, label, factory, seconds=4, bound=65536):
        need(time.monotonic() + seconds + 3 < self.deadline, 'ROOM_FOR_BOUNDED_OWNED_RETIREMENT')
        reaper = self.capture.OwnChildReaper(protected_pids=self.protected); cancel = self.commands.Cancellation()
        before = fd_snapshot(); began = False; record = {}; out = err = None; error = finish_error = None
        try:
            cancel.begin(); reaper.begin(); began = True; now = time.monotonic()
            record, out, err, error = self.capture.invoke_owned(reaper, factory, b'', now + seconds, now + seconds + 3,
                output_bound=bound, cleanup_enter=cancel.enter_retirement, retirement_grace=3)
        finally:
            cancel.enter_retirement()
            if began:
                try: reaper.finish()
                except BaseException as caught: finish_error = caught
            try: cancel.restore()
            except BaseException as caught: finish_error = finish_error or caught
        subreaper = copy.deepcopy(reaper.record)
        retired = self.commands.retirement_complete(record, subreaper, finish_error)
        value = {'label': label, 'lifecycle': record, 'subreaper': subreaper, 'host_retirement_proved': retired,
            'capture_error': None if error is None else {'type': type(error).__name__, 'message': str(error)},
            'finish_error': None if finish_error is None else {'type': type(finish_error).__name__, 'message': str(finish_error)},
            'cancellation': cancel.signals, 'runtime_qualified': False, 'whole_app_business_accepted': False}
        for name, data in (('stdout', out), ('stderr', err)):
            value[name] = None if type(data) is not bytes else {'bytes': len(data), 'sha256': sha(data)}
        ref = write_new(self.output / (label + '-owned-capture.json'), value)
        self.children.append(ref)
        need(retired and finish_error is None and not cancel.signals, 'REAL_OWNED_CAPTURE_RETIREMENT_REQUIRED:' + label)
        need(fd_snapshot() == before, 'OWNED_CAPTURE_FD_LEAK:' + label)
        return record, out, err, error, ref

    def helper(self, label, mode, session, seconds=4, bound=65536):
        d = session.decoder; tool = os.open(self.python, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            argv = [self.python, '-I', '-B', '-c', HELPER, mode, str(d.decode_fd), str(tool), str(d.path)]
            return self.owned(label, self.held_factory(argv, d.decode_fd, tool), seconds, bound)
        finally: os.close(tool)

    def generate(self):
        pcm = self.challenge.waveform(self.nonce)
        need(len(pcm) <= 4 * 48000 * 4, 'FINITE_SYNTHETIC_CHALLENGE')
        pcm += bytes(4 * 48000 * 4 - len(pcm))
        fd = os.memfd_create('p4-host-synthetic-challenge', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        tool = None
        try:
            rest = memoryview(pcm)
            while rest:
                n = os.write(fd, rest); need(n > 0, 'SYNTHETIC_PCM_WRITE'); rest = rest[n:]
            os.fchmod(fd, 0o444); fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
            tool = os.open('/usr/bin/ffmpeg', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            argv = ['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-filter_threads', '1', '-filter_complex_threads', '1',
                '-f', 'lavfi', '-i', 'color=c=blue:s=32x32:r=5:d=4', '-f', 's16le', '-ar', '48000', '-ac', '2',
                '-i', '/proc/self/fd/' + str(fd), '-t', '4', '-c:v', 'libx264', '-preset', 'ultrafast',
                '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1']
            record, raw, err, error, ref = self.owned('synthetic-generation', self.held_factory(argv, fd, tool), 8, 2097152)
            need(error is None and record['returncode'] == 0 and err == b'' and type(raw) is bytes
                and 0 < len(raw) <= 2097152, 'REAL_FINITE_SYNTHETIC_CLIP_GENERATION')
            self.synthetic = raw; return ref
        finally:
            if tool is not None: os.close(tool)
            os.close(fd)

    def normal_decoder_and_fresh_nonce(self):
        generated = self.generate(); s = HostOnlySession(self, 'normal', self.synthetic, self.nonce)
        try:
            value, ref = s.decoder.run(tone_window_ms=[1500, 1750], baseline_end_ms=1300)
            need(value['full_video_decode'] is True and value['full_audio_decode'] is True
                and value['current_nonce_audio_verified'] is True and value['correlation']['matched'] is True
                and value['correlation']['baseline_negative_passed'] is True
                and value['correlation']['decoy_negative_passed'] is True and value['nonce'] == self.nonce
                and value['full_frame_decode']['count'] == 20 and value['runtime_qualified'] is False,
                'ACTUAL_FULL_SYNTHETIC_DECODER_AND_NONCE')
            need(set(s.decoder.done) == {'probe', 'video', 'audio'} and s.decoder.unknown is False, 'THREE_REAL_RETIRED_DECODES')
            for kind, item in s.decoder.done.items():
                result = item['result']
                need(result['host_retirement_proved'] is True and result['lifecycle']['returncode'] == 0
                    and result['lifecycle']['descendants'] == [] and not result['errors']
                    and set(result['inherited_fds']) == {'sealed_owned_clip', 'held_decoder'},
                    'EXACT_PRODUCTION_DECODER_RETIREMENT:' + kind)
            return {'generation': generated, 'decoder_result': ref, 'nonce': self.nonce,
                'production_decoder_class_unchanged': True, 'live_Session_admission_qualified': False}
        finally: s.close()

    def uid1000_and_exact_two_fds(self):
        s = HostOnlySession(self, 'uid-fds', b'finite synthetic FD attestation input\n')
        try:
            record, out, err, error, ref = self.helper('uid-two-fds', 'attest', s)
            need(error is None and err == b'' and record['returncode'] == 0, 'ACTUAL_UID_FD_CHILD_SUCCESS')
            value = parse(out)
            need(value['uids'] == value['gids'] == [1000] * 4 and value['groups'] == []
                and value['no_new_privs'] == ['1'] and value['core_limit'] == [0, 0]
                and value['fds'] == value['expected_fds'] and len(value['fds']) == 5
                and value['inherited_access_mode'] == os.O_RDWR and value['readonly_view_access_mode'] == os.O_RDONLY
                and value['seals'] == 15 and value['clip_sha256'] == value['readonly_view_sha256'] == s.clip['sha256']
                and value['original_root_file_errno'] == errno.EACCES, 'REAL_UID1000_TWO_FD_AND_PRIVATE_ORIGINAL_BOUNDARY')
            need(value['clip_identity'] == identity(os.fstat(s.decoder.decode_fd)), 'SAME_REAL_CHILD_MEMFD_IDENTITY')
            s.decoder.verify(); return {'capture': ref, 'actual_child': value}
        finally: s.close()

    def all_seals_and_denied_write_metadata(self):
        s = HostOnlySession(self, 'seals', b'finite synthetic sealed input\n' * 16)
        try:
            d = s.decoder; initial = identity(os.fstat(d.decode_fd)); original = identity(os.fstat(d.fd))
            record, out, err, error, ref = self.helper('seal-negative', 'seals', s)
            need(error is None and record['returncode'] == 0 and err == b'', 'ACTUAL_UID1000_SEAL_NEGATIVES')
            value = parse(out); after = identity(os.fstat(d.decode_fd)); changed = {k for k in initial if initial[k] != after[k]}
            need(value['before'] == initial and value['after'] == after and value['sha256'] == s.clip['sha256']
                and changed <= {'st_mtime_ns', 'st_ctime_ns'} and fcntl.fcntl(d.decode_fd, fcntl.F_GET_SEALS) == 15
                and identity(os.fstat(d.fd)) == original and sha(os.pread(d.fd, s.clip['bytes'], 0)) == s.clip['sha256'],
                'SEALED_NEGATIVES_PRESERVE_BYTES_SIZE_SEALS_AND_ORIGINAL')
            if changed:
                try: d.verify()
                except RuntimeError as caught: need(str(caught) == 'SAME_SEALED_VIDEO_DESCRIPTOR_FOR_ALL_DECODERS', 'EXACT_METADATA_REFUSAL')
                else: raise RuntimeError('DENIED_WRITE_METADATA_DRIFT_ACCEPTED')
            else: d.verify()
            return {'capture': ref, 'actual_negative_operations': value, 'changed_metadata_fields': sorted(changed),
                'original_identity_rebased': False}
        finally: s.close()

    def malformed_mov_known_failure(self):
        s = HostOnlySession(self, 'malformed', b'ffconcat version 1.0\nfile /unowned/forbidden.mp4\n')
        try:
            try: s.decoder.call('probe')
            except RuntimeError as caught:
                need(type(caught) is RuntimeError and str(caught) == 'FULL_OWNED_CLIP_DECODE_MUST_COMPLETE_CLEANLY',
                    'EXACT_KNOWN_DECODE_FAILURE')
            else: raise RuntimeError('MALFORMED_MOV_ACCEPTED')
            item = s.decoder.done['probe']; value = item['result']
            need(value['host_retirement_proved'] is True and value['returncode'] != 0
                and s.decoder.unknown is False and value['lifecycle']['descendants'] == [], 'KNOWN_RETIRED_DECODER_FAILURE')
            stderr, _ = read(value['stderr']['reference']['path'], value['stderr']['reference'])
            need(b'/unowned/forbidden.mp4' not in stderr, 'MOV_DEMUXER_MUST_NOT_FOLLOW_CONCAT_INPUT')
            return {'result': item['reference'], 'expected_failure': True, 'outcome_unknown': False}
        finally: s.close()

    def actual_timeout_and_owned_retirement(self):
        s = HostOnlySession(self, 'timeout', b'timeout control input')
        try:
            record, out, err, error, ref = self.helper('timeout', 'sleep', s, seconds=.25)
            need(isinstance(error, TimeoutError) and record['timed_out'] is True and record['returncode'] == -signal.SIGKILL
                and record['kill_attempted'] is True and record['remaining_owned_children'] == [], 'REAL_TIMEOUT_KILL_AND_REAP')
            return {'capture': ref, 'expected_failure': True, 'owned_retirement_proved': True}
        finally: s.close()

    def actual_output_bound_and_retirement(self):
        s = HostOnlySession(self, 'output-bound', b'output bound control input')
        try:
            record, out, err, error, ref = self.helper('output-bound', 'overflow', s, seconds=2, bound=1024)
            capture = record['output_capture']
            need(type(error) is RuntimeError and str(error) == 'stdout exceeded per-stream output bound'
                and capture['stored_bytes']['stdout'] == 1024 and capture['observed_bytes']['stdout'] == 1025
                and capture['limit_exceeded'] is True and capture['no_stream_reads_after_capture_failure'] is True
                and capture['prefix_only'] is True and out == b'X' * 1024, 'REAL_BOUNDED_PREFIX_AND_RETIRED_WRITER')
            return {'capture': ref, 'expected_failure': True, 'owned_retirement_proved': True}
        finally: s.close()

    def actual_adopted_descendant_retirement(self):
        s = HostOnlySession(self, 'descendant', b'owned descendant control input')
        try:
            record, out, err, error, ref = self.helper('descendant', 'descendant', s, seconds=.35)
            declared = parse(out)['owned_descendant']; rows = record['descendants']
            need(error is not None and record['returncode'] == 0 and len(rows) == 1 and rows[0]['pid'] == declared
                and rows[0]['reaped'] is True and rows[0]['pidfd_closed'] is True and rows[0]['kill_attempted'] is True
                and record['owned_tree_cleanup_complete'] is True and record['remaining_owned_children'] == []
                and record['qualified_success'] is False, 'REAL_OWNED_ESCAPED_DESCENDANT_RETIRED_NOT_SUCCESS')
            return {'capture': ref, 'expected_failure': True, 'actual_adopted_child': declared}
        finally: s.close()

    def actual_finish_fault_keeps_unknown(self):
        owner = self; actual = self.capture; tracked = []; fault_record = {}
        class FinishFault:
            @staticmethod
            def OwnChildReaper(*args, **kwargs):
                value = actual.OwnChildReaper(*args, **kwargs); tracked.append(value); return value
            @staticmethod
            def invoke_owned(reaper, *args, **kwargs):
                result = actual.invoke_owned(reaper, *args, **kwargs)
                record, out, err, error = result
                need(error is None and record['child_reaped'] is True and record['owned_tree_cleanup_complete'] is True
                    and record['all_acquired_fds_closed'] is True and record['remaining_owned_children'] == [],
                    'FAULT_ONLY_AFTER_REAL_CHILD_AND_FD_RETIREMENT')
                reaper.empty(); need(reaper.flag() == 1, 'ACTUAL_PRE_FAULT_SUBREAPER')
                fault_record.update(before_flag=1, original_flag=reaper.original, child=record['pid'],
                    child_reaped_before_fault=True, capture_record_sha256=sha(json.dumps(record, sort_keys=True).encode()))
                # Only this isolated controller's kernel flag changes. No source,
                # result field, child process, Main or external process is changed.
                fault_record['flag_change_attempted'] = True
                reaper.set_flag(0); fault_record['flag_change_returned'] = True
                need(reaper.flag() == 0, 'REAL_SELF_SUBREAPER_FAULT')
                return result
        s = HostOnlySession(self, 'unknown', self.synthetic, self.nonce, capture=FinishFault)
        original_ref = original_raw = late = primary = None
        def remember(error, stage):
            nonlocal primary
            if primary is None: primary = error
            else: primary.add_note(stage + ':' + repr(error))
        try:
            try: s.decoder.call('probe')
            except self.decode.DecodeOutcomeUnknown as caught:
                need(str(caught) == 'OWNED_DECODER_RETIREMENT_OR_OUTPUT_UNKNOWN'
                    and isinstance(caught.__cause__, RuntimeError)
                    and str(caught.__cause__) == 'own subreaper flag changed during commands', 'ACTUAL_FINISH_FAILURE_UNKNOWN')
            else: raise RuntimeError('ACTUAL_FINISH_FAULT_WAS_ACCEPTED')
            need(s.decoder.unknown is True and len(tracked) == 1, 'UNKNOWN_REMAINS_LATCHED')
            item = s.decoder.done['probe']; original_ref = item['reference']; original_raw, _ = read(original_ref['path'], original_ref)
            need(item['result']['host_retirement_proved'] is False
                and item['result']['subreaper']['restored'] is False, 'ORIGINAL_UNKNOWN_RECEIPT_PRESERVED')
            try: s.decoder.call('audio')
            except RuntimeError as caught: need(str(caught) == 'ONCE_FIXED_FULL_CLIP_DECODE', 'EXACT_UNKNOWN_REPLAY_REFUSAL')
            else: raise RuntimeError('UNKNOWN_DECODER_REPLAYED')
        except BaseException as error:
            remember(error, 'UNKNOWN_CONTROL_PRIMARY')
        finally:
            try:
                if tracked:
                    reaper = tracked[0]
                    if reaper.record['restored'] is True:
                        # A capture failure can precede fault injection while
                        # Decoder's original finally already restores the flag.
                        # Never set it to 1 again after changed becomes False.
                        reaper.empty(); need(reaper.flag() == reaper.original,
                            'ALREADY_RESTORED_SELF_FLAG_MUST_REMAIN_UNCHANGED')
                    elif fault_record.get('flag_change_attempted') is True:
                        # Only this explicitly attempted fault grants recovery
                        # authority. Its precondition proved ECHILD before the
                        # kernel flag operation; the original receipt stays held.
                        need(reaper.original is not None, 'FAULT_HAS_ACTUAL_ORIGINAL_SELF_FLAG')
                        reaper.empty(); reaper.set_flag(1); reaper.finish(); reaper.empty()
                        need(reaper.flag() == reaper.original, 'ORIGINAL_SELF_FLAG_RESTORED_AFTER_FAULT')
                    else:
                        need(reaper.original is None and not fault_record and reaper.flag() == owner.initial_flag,
                            'UNINJECTED_FAILURE_HAS_NO_FLAG_RECOVERY_AUTHORITY')
                    if reaper.record['restored'] is True:
                        late = {'actual_flag': reaper.flag(), 'original_flag': reaper.original,
                            'kernel_ECHILD_confirmed': True, 'original_unknown_cleared': False}
            except BaseException as error:
                remember(error, 'UNKNOWN_CONTROL_SELF_FLAG_RECOVERY')
            finally:
                try: s.close()
                except BaseException as error: remember(error, 'UNKNOWN_CONTROL_LOCAL_CLOSE')
        if primary is not None: raise primary
        need(original_ref is not None and read(original_ref['path'], original_ref)[0] == original_raw
            and s.decoder.unknown is True, 'LATE_LOCAL_CLEANUP_CANNOT_REWRITE_UNKNOWN')
        late_ref = write_new(self.output / 'unknown-separate-self-flag-recovery.json', late)
        return {'original_unknown_result': original_ref, 'kernel_fault': fault_record,
            'separate_self_flag_recovery': late_ref, 'outcome_unknown_preserved': True}


def inputs(args):
    raw, packet_ref = read(args.packet, maximum=131072)
    need(re.fullmatch('[0-9a-f]{64}', args.expect_packet_sha256 or '')
        and packet_ref['sha256'] == args.expect_packet_sha256, 'EXTERNAL_REVIEWED_HOST_CONTROL_PACKET_PIN')
    packet = parse(raw)
    need(packet['schema'] == 'pocket4-camera-r4-decoder-host-control-packet-v1'
        and packet['controls'] == list(CONTROLS) and packet['runtime_qualified'] is False
        and packet['whole_app_business_accepted'] is False, 'EXACT_HOST_COMPONENT_PACKET')
    read(Path(__file__).resolve(), packet['runner']); sources = {}
    for name, ref in packet['production_sources'].items():
        path = Path(args.source_dir) / name; raw, actual = read(path, ref)
        ast.parse(raw, filename=str(path)); sources[name] = (raw, path, actual)
    need(set(sources) == {'camera_decode.py', 'camera_video_media.py', 'camera_audio_challenge.py'}, 'EXACT_PRODUCTION_COMPONENT_SET')
    overrides = {'capture': args.inspect_capture, 'lifecycle': args.inspect_lifecycle, 'commands': args.inspect_commands}
    if args.mode == 'qualify-host': need(all(v is None for v in overrides.values()), 'NO_HOST_SOURCE_RELOCATION_DURING_QUALIFICATION')
    for name, ref in packet['fixed_sources'].items():
        path = Path(overrides[name] or ref['path']); raw, actual = read(path, ref)
        ast.parse(raw, filename=str(path)); sources[name] = (raw, path, actual)
    need(set(packet['fixed_sources']) == {'capture', 'lifecycle', 'commands'}
        and packet['fixed_sources']['capture']['path'] == CAPTURE_PATH
        and packet['fixed_sources']['lifecycle']['path'] == LIFECYCLE_PATH
        and packet['fixed_sources']['commands']['path'] == COMMANDS_PATH, 'EXACT_CANONICAL_TRANSITIVE_HOST_SOURCES')
    compile(HELPER, '<fixed-reviewed-host-child>', 'exec')
    return packet, packet_ref, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect-source', 'qualify-host'))
    parser.add_argument('--packet', required=True); parser.add_argument('--expect-packet-sha256', required=True)
    parser.add_argument('--source-dir', required=True); parser.add_argument('--output-root', required=True)
    parser.add_argument('--expected-cgroup')
    parser.add_argument('--inspect-capture'); parser.add_argument('--inspect-lifecycle'); parser.add_argument('--inspect-commands')
    args = parser.parse_args(); output = Path(args.output_root)
    need(output.is_absolute() and output.parent.resolve() == output.parent
        and re.fullmatch('camera-r4-decoder-host-qualification-[a-zA-Z0-9_-]+', output.name), 'EXCLUSIVE_NEW_HOST_CONTROL_OUTPUT_ROOT')
    output.mkdir(mode=0o700)
    report = {'schema': 'pocket4-camera-r4-decoder-host-qualification-v1', 'mode': args.mode,
        'expected_controls': list(CONTROLS), 'controls': [], 'not_run': list(CONTROLS),
        'host_component_qualified': False, 'Main_actions': 0, 'Android_actions': 0,
        'physical_audio_actions': 0, 'live_Session_admission_qualified': False,
        'runtime_qualified': False, 'whole_app_business_accepted': False,
        'source_changes': 0, 'source_only_Session_fixture': True, 'synthetic_media_only': True}
    first = None; owner = None
    try:
        packet, packet_ref, sources = inputs(args)
        report.update(packet=packet_ref, source_inputs=[value[2] for value in sources.values()], source_inspection_passed=True)
        if args.mode == 'qualify-host':
            resource_record = resource_admission(args.expected_cgroup, report)
            owner = Qualification(packet, sources, output, resource_record)
            report.update(resource_admission=resource_record, actual_tool_files=list(owner.tools.values()))
            for name in CONTROLS:
                need(time.monotonic() < owner.deadline, 'GLOBAL_CONTROL_DEADLINE')
                started = time.monotonic(); value = getattr(owner, name)(); owner.idle()
                report['controls'].append({'name': name, 'passed': True,
                    'elapsed_seconds': time.monotonic() - started, 'evidence': value})
                report['not_run'].remove(name)
            owner.idle()
            report.update(host_component_qualified=len(report['controls']) == len(CONTROLS),
                final_self_subreaper_flag=owner.initial_flag, final_kernel_ECHILD=True,
                final_fd_set_unchanged=True, synthetic_input_files_removed=True)
    except BaseException as error:
        first = error; report['error'] = {'type': type(error).__name__, 'message': str(error),
            'traceback': traceback.format_exc(limit=12)}
    finally:
        if owner is not None:
            owner.synthetic = None
            try: owner.idle(); report['final_host_idle_checked'] = True
            except BaseException as error:
                report['final_host_idle_checked'] = False; report['final_host_idle_error'] = {'type': type(error).__name__, 'message': str(error)}
                if first is None: first = error
            try:
                report['resource_final_observation'] = resource_snapshot(owner.resource_record['cgroup'])
                resource_valid(report['resource_final_observation'], owner.resource_record['observation'])
                report['no_memory_swap_or_pids_limit_events'] = True
            except BaseException as error:
                report['no_memory_swap_or_pids_limit_events'] = False
                report['resource_final_error'] = {'type': type(error).__name__, 'message': str(error)}
                if first is None: first = error
        if first is not None: report['host_component_qualified'] = False
        ref = write_new(output / 'qualification.json', report)
        print(json.dumps({'qualification': ref, 'host_component_qualified': report['host_component_qualified'],
            'controls_run': len(report['controls']), 'controls_not_run': report['not_run'],
            'runtime_qualified': False, 'whole_app_business_accepted': False}, sort_keys=True))
    return 0 if first is None and (args.mode == 'inspect-source' or report['host_component_qualified']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
