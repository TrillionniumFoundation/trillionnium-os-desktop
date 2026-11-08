#!/usr/bin/env python3
"""Bind one fresh Camera video/acoustic case to the owned normal display lease."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import time
import types

ROOT = Path('/home/alex/work/pocket4-android-final/camera')
PREPARED = Path(__file__).resolve().parent
QUALIFICATION = ROOT.parent / 'qualification'
PHOTO_PREPARED = None  # Historical photo preparation is never loaded.
PREPARATION_REF = None
SOURCES = {
    'holder': (PREPARED / 'display_holder.py', '3268c20caa9523525e3db90d9fd9b56d703cacfc58fbc43187b127dd87f51c11', 16384),
    'lease': (PREPARED / 'display_lease.py', '81f34cdbc75a2cf4e092a961fe4dce5d23522842c0ec54cdcff4fc9c99e4dbfd', 32768),
    'lifecycle': (ROOT.parent / 'framework/runtime_support/capture_lifecycle.py',
                  '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877', 32768),
}
VIDEO_CONTEXT = None
VIDEO_INVENTORY_SHA256 = '2444a7f3dcbeace9a3a9c5b86d2fc815a59ae965b626ddb80ba99b6f4d13520f'
VIDEO_ENTRY_PIN = (9807, 'ab929997fa08d5acda471cec6219fcbc2eb1edeed2a7b6c7bae189f7abb842a1')

MAX_PACKET = 65536
WRAPPER_SECONDS = 665
READY_SECONDS = 20
CAMERA_SECONDS = 510  # Includes acoustic owner retirement.
CAMERA_GRACE_SECONDS = 90  # Worker cleanup60 + acoustic retirement30.
# Drop to normal alex before interpreting the already-held, exact source. Reopen
# through /proc/self/fd is not available across the UID boundary on this host.
HELD_PYTHON_BOOTSTRAP = """import hashlib,os,stat,sys
fd,expected,bound=int(sys.argv[1]),sys.argv[2],int(sys.argv[3])
def ident(s):
 return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_gid,s.st_nlink)
before=os.fstat(fd)
assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=bound<=16384
raw=os.pread(fd,bound+1,0)
assert len(raw)==before.st_size and ident(os.fstat(fd))==ident(before)
assert hashlib.sha256(raw).hexdigest()==expected
os.close(fd)
sys.argv=['held_display_holder.py']+sys.argv[4:]
exec(compile(raw,'held_display_holder.py','exec'),{'__name__':'__main__','__file__':'held_display_holder.py'})
"""


def require(value, message):
    if not value:
        raise RuntimeError(message)


def metadata(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns,
            st.st_mode, st.st_uid, st.st_gid, st.st_nlink)


def held_file(path, bound, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= bound,
                'bounded single-link regular input required: ' + str(path))
        raw = os.pread(fd, bound + 1, 0)
        require(len(raw) == before.st_size and metadata(os.fstat(fd)) == metadata(before)
                and metadata(os.stat(path, follow_symlinks=False)) == metadata(before),
                'held input changed: ' + str(path))
        sha = hashlib.sha256(raw).hexdigest()
        require(expected is None or sha == expected, 'source/input SHA differs: ' + str(path))
        return fd, raw, {'path': str(path), 'bytes': len(raw), 'sha256': sha,
                         'device': before.st_dev, 'inode': before.st_ino,
                         'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns}
    except BaseException:
        os.close(fd)
        raise


def write_json(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def life_record():
    return {'child_started': False, 'child_reaped': False, 'pidfd_closed': True,
            'owned_tree_cleanup_complete': False, 'descendants': []}


def configure_video_preparation(path, expected):
    global PREPARATION_REF, VIDEO_CONTEXT
    require(PREPARATION_REF is None and re.fullmatch('[0-9a-f]{64}', expected or ''),
            'one externally reviewed video preparation required')
    fd, raw, observed = held_file(path, 131072, expected)
    try:
        packet = json.loads(raw)
    finally:
        os.close(fd)
    require(packet.get('schema') == 'pocket4-current-camera-video-preparation-v1'
            and packet.get('source_inventory_sha256') == VIDEO_INVENTORY_SHA256,
            'exact reviewed current video preparation required')
    refs = [row for row in packet['files'] if Path(row['path']).name == 'camera_entry.py']
    require(len(refs) == 1 and (refs[0]['bytes'], refs[0]['sha256']) == VIDEO_ENTRY_PIN,
            'exact current video entry required')
    fd, raw, _ = held_file(refs[0]['path'], 262144, refs[0]['sha256'])
    try:
        entry = types.ModuleType('outer_display_verified_video_entry')
        entry.__file__ = refs[0]['path']
        exec(compile(raw, entry.__file__, 'exec'), entry.__dict__)
    finally:
        os.close(fd)
    common, packet, preparation, planner = entry.bootstrap(argparse.Namespace(
        preparation=str(path), expect_preparation_sha256=expected))
    witness = common.EvidenceWitness([preparation])
    try:
        witness.verify()
    finally:
        witness.close()
    PREPARATION_REF = preparation
    VIDEO_CONTEXT = (common, packet, planner)
    SOURCES['camera'] = (Path(refs[0]['path']), refs[0]['sha256'], 262144)
    SOURCES['preparation'] = (Path(path), expected, 131072)
    for row in packet['files']:
        SOURCES['component_' + Path(row['path']).stem] = (Path(row['path']), row['sha256'], 262144)
    return packet


def validate_video_terminals(plan_ref, plan, preparation, direct_operator, ready_device,
                             parent, parent_ref, supervisor, worker, worker_ref, claim):
    """Strict consumer of unchanged actual producer schemas; no I/O or authority."""
    require(parent.get('schema') == 'pocket4-current-camera-acoustic-parent-v1'
            and parent.get('plan') == plan_ref and parent.get('preparation') == preparation
            and parent.get('case_root') == plan['case_root'] and parent.get('limits') == plan['limits']
            and parent.get('nonce') == plan['audio_nonce'] and parent.get('automatic_retry') is False,
            'actual acoustic parent has another plan/preparation/nonce')
    owner = parent.get('parent', {})
    require(all(owner.get(k) == v for k, v in direct_operator.items()) and owner.get('uids') == [0, 0, 0, 0],
            'acoustic receipt is not from the exact owned root child')
    require(supervisor.get('schema') == 'pocket4-current-camera-acoustic-supervisor-result-v1'
            and supervisor.get('plan') == plan_ref and supervisor.get('preparation') == preparation
            and supervisor.get('kind') == 'camera_video' and supervisor.get('nonce') == plan['audio_nonce']
            and supervisor.get('limits') == plan['limits'] and supervisor.get('inner_result') == worker_ref
            and supervisor.get('state') == 'CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN'
            and supervisor.get('case_business_success_verified') is True
            and supervisor.get('worker_result_verified') is True and supervisor.get('outcome_unknown') is False
            and supervisor.get('whole_app_business_accepted') is False
            and supervisor.get('automatic_retry') is False and supervisor.get('automatic_rollback') is False
            and supervisor.get('error') is None and supervisor.get('errors') == []
            and supervisor.get('received_signals') == [] and supervisor.get('Main_signals') == 0
            and supervisor.get('Android_UI_actions_by_supervisor') == 0,
            'acoustic supervisor did not return its exact successful terminal')
    commit = supervisor.get('cancellation_commit', {})
    require(commit.get('pending_at_commit') == [] and commit.get('decision_after_all_context_close') is True,
            'acoustic owner cancellation commit incomplete')
    reaper = supervisor.get('subreaper', {})
    require(all(reaper.get(k) is True for k in ('begin_passed', 'restored', 'final_children_empty'))
            and supervisor.get('adopted_retirement', {}).get('owned_tree_cleanup_complete') is True
            and supervisor['adopted_retirement'].get('descendants') == []
            and all(supervisor.get(k) is True for k in
                    ('control_fd_closed', 'selector_closed', 'audio_artifact_descriptors_closed', 'held_Main_closed')),
            'acoustic owner retained a child, descriptor or Main context')
    actors = supervisor.get('actors', {})
    require(set(actors) == {'business', 'emit', 'listen'} and
            len({row.get('pid') for row in actors.values()}) == 3 and
            all(type(row.get('pid')) is int and row['pid'] > 1 for row in actors.values()),
            'three distinct actual video principals required')
    for role, actor in actors.items():
        require(actor.get('uid') == (0 if role == 'business' else 1000)
                and all(actor.get(k) is True for k in ('child_started', 'child_reaped', 'pidfd_closed'))
                and actor.get('pipe_eof') == {'stdout': True, 'stderr': True}
                and actor.get('returncode') == 0,
                'video principal retirement or complete output missing:' + role)
    business = supervisor.get('business_process', {})
    require(business.get('pid') == actors['business']['pid'] and business.get('parent') == direct_operator['pid']
            and business.get('uids') == [0, 0, 0, 0] and type(business.get('start_ticks')) is int
            and business['start_ticks'] > 0 and claim.get('plan') == plan_ref
            and claim.get('operator') == business and claim.get('automatic_retry') is False,
            'execute-once claim must name the actual acoustic-owned business worker')
    require(worker.get('schema') == 'pocket4-current-camera-video-case-result-v1'
            and worker.get('plan') == plan_ref and worker.get('source_preparation') == preparation
            and worker.get('kind') == 'camera_video'
            and worker.get('state') == 'CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN'
            and worker.get('case_business_success_verified') is True and worker.get('outcome_unknown') is False
            and worker.get('secondary_errors') == [] and worker.get('error') is None
            and all(worker.get(k) is False for k in ('runtime_qualified', 'whole_app_business_accepted',
                                                   'camera_recovery_qualified', 'automatic_retry')),
            'actual worker did not return its narrow current video successful contract')
    require(all(worker.get(k) is True for k in ('owned_task_cleanup_verified', 'current_Main_APIs_closed',
            'whole_case_OFD_closed', 'evidence_witness_closed', 'acoustic_channel_closed',
            'owned_decoder_descriptor_closed', 'final_source_and_identity_chain_unchanged'))
            and all(k in worker and worker[k] is None for k in ('acoustic_pending', 'pending_business_action',
            'pending_owned_task_remove', 'owned_task_remaining', 'recording_pending')),
            'video worker has incomplete contexts or an unresolved action')
    commit = worker.get('cancellation_commit', {})
    require(commit.get('received_signals') == commit.get('pending_at_commit') == []
            and commit.get('decision_after_all_context_close') is True, 'video worker cancelled before commit')
    launches = worker.get('native_launches')
    require(type(launches) is list and len(launches) == len(set(launches)) == 3
            and launches == worker.get('exact_normal_closes') == worker.get('native_tasks') == worker.get('normal_closes'),
            'three actual distinct launches and exact normal closes required')
    recording = worker.get('recording', {})
    require(recording.get('state') == 'CAMERA_VIDEO_RECORD_AUDIO_PLAYBACK_VERIFIED'
            and recording.get('camera_video_verified') is True and recording.get('outcome_unknown') is False
            and recording.get('pending') is None and recording.get('nonce') == plan['audio_nonce']
            and recording.get('epoch_sha256') == plan['framework_epoch_sha256']
            and recording.get('original_mode') == recording.get('final_mode')
            and all(recording.get(k) is True for k in ('owned_task_closed', 'preserved_state', 'host_retired')),
            'recording/playback/state restoration terminal incomplete')
    acoustic = supervisor.get('acoustic_results', {})
    require(set(acoustic) == {'emit', 'listen'} and worker.get('acoustic_results') == acoustic,
            'actual worker and supervisor disagree on acoustic evidence')
    for role, row in acoustic.items():
        require(row.get('role') == role and row.get('parent') == parent_ref and row.get('exit_code') == 0
                and row.get('leader_reaped') is True and row.get('pipe_eof') == {'stdout': True, 'stderr': True}
                and row.get('automatic_retry') is False and all(row.get(k, {}).get('nonce') == plan['audio_nonce']
                                                             for k in ('ready', 'started', 'closed')),
                'actual finite acoustic receipt mismatch:' + role)
    require(worker.get('physical_device') == ready_device and ready_device is not None,
            'video and display lease bind different physical devices')
    return True


class Supervisor:
    """Two sibling principals; the frozen photo case owns only its own children."""
    def __init__(self, raw, output, sources=None):
        require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
                'root camera video wrapper context required')
        require(VIDEO_CONTEXT is not None, 'reviewed current video preparation not configured')
        self.common, self.packet, self.planner = VIDEO_CONTEXT
        self.raw, self.out, self.spec = raw, output, self.common.parse(raw)
        require(len(raw) <= 131072 and type(self.spec) is dict
                and set(self.spec) == {'schema', 'plan', 'source_preparation', 'automatic_retry', 'whole_app_business_accepted'}
                and self.spec['schema'] == 'pocket4-camera-video-display-input-v1'
                and self.spec['source_preparation'] == PREPARATION_REF
                and self.spec['automatic_retry'] is False and self.spec['whole_app_business_accepted'] is False,
                'exact current video display request required')
        self.plan_ref = self.spec['plan']
        require(type(self.plan_ref) is dict and set(self.plan_ref) == {'path', 'bytes', 'sha256'}
                and type(self.plan_ref['bytes']) is int and 0 < self.plan_ref['bytes'] <= 131072
                and re.fullmatch('[0-9a-f]{64}', self.plan_ref['sha256']), 'exact reviewed video plan reference required')
        plan_path = Path(self.plan_ref['path'])
        self.case_root = plan_path.parent
        require(plan_path.is_absolute() and plan_path.resolve() == plan_path and plan_path.name == 'plan.json'
                and self.case_root.parent == QUALIFICATION
                and re.fullmatch('business-camera-video-plan-[0-9a-f]{32}', self.case_root.name),
                'only a newly factory-created video plan can enter the display lease')
        self.plan = self.common.parse(self.common.read_ref(self.plan_ref))
        require(self.plan.get('schema') == 'pocket4-current-camera-video-plan-v1'
                and self.plan.get('kind') == 'camera_video' and self.plan.get('case_root') == str(self.case_root)
                and self.plan.get('source_preparation') == PREPARATION_REF
                and self.plan.get('automatic_retry') is False and self.plan.get('whole_app_business_accepted') is False,
                'the request is not this frozen video plan')
        profiles = self.planner.named(self.common, self.packet, 'camera_profiles.py')
        require(self.plan['limits'] == profiles.LIMITS and profiles.LIMITS['business_seconds'] == 420
                and profiles.LIMITS['cleanup_seconds'] == 60 and profiles.LIMITS['supervisor_seconds'] == CAMERA_SECONDS,
                'exact existing video worker and acoustic owner budgets required')
        self.planner.source_packet(self.common, self.plan, self.packet)
        require(not any((self.case_root / name).exists() for name in
                        ('execute-once.json', 'result.json', 'evidence', 'acoustic-supervisor')),
                'video execution already begun; no implicit retry')
        self.spec['transaction_id'] = 'video-' + self.case_root.name.rsplit('-', 1)[1]
        self.sources = {**(SOURCES if sources is None else sources),
                        'plan': (plan_path, self.plan_ref['sha256'], 131072)}
        self.fds, self.logs, self.actors = [], [], {}
        self.channel = self.reaper = self.ready = self.release = self.last_heartbeat = None
        self.sequence = 0
        self.retiring = self.committed = False
        self.after_commit_signals = []
        self.error = self.inner_result = None
        self.record = {'schema': 'pocket4-camera-video-display-supervision-v1',
            'started_monotonic_ns': time.monotonic_ns(), 'errors': [], 'signals': [],
            'sources': {}, 'events': [], 'ready_revoked': False, 'automatic_retry': False,
            'Main_lifecycle_actions': 0, 'USB_actions': 0, 'global_power_setting_changes': 0,
            'public_lifecycle_changed': False,
            'principal_structure': 'root owns alex display holder and root acoustic supervisor siblings'}
        self.started = time.monotonic()
        self.operation_deadline = self.started + READY_SECONDS + CAMERA_SECONDS
        self.deadline = self.started + WRAPPER_SECONDS
        self.record['budgets'] = {'wrapper_seconds': WRAPPER_SECONDS, 'ready_seconds': READY_SECONDS,
            'video_worker_business_seconds': 420, 'video_worker_cleanup_seconds': 60,
            'acoustic_supervisor_with_retirement_seconds': CAMERA_SECONDS,
            'acoustic_cancellation_grace_seconds': CAMERA_GRACE_SECONDS,
            'operation_deadline': self.operation_deadline, 'absolute_deadline': self.deadline}

    def remember(self, error, stage):
        self.record['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

    def cancelled(self, number, frame):
        if self.committed:
            # All work and retirement are complete; the durable terminal is now
            # a frozen record. Late cancellation cannot change its return code.
            if len(self.after_commit_signals) < 32:
                self.after_commit_signals.append({'signal': number, 'monotonic_ns': time.monotonic_ns()})
            return
        self.record['signals'].append({'signal': number, 'retiring': self.retiring,
                                       'monotonic_ns': time.monotonic_ns()})
        self.record['ready_revoked'] = True
        self.record['ready_revoked_ns'] = time.monotonic_ns()
        if not self.retiring:
            raise InterruptedError('camera wrapper cancellation')

    def load_sources(self):
        self.source_fds = {}
        for role, (path, expected, bound) in self.sources.items():
            fd, raw, reference = held_file(path, bound, expected)
            self.fds.append(fd)
            self.source_fds[role] = fd
            self.record['sources'][role] = reference
            if role == 'lifecycle':
                module = types.ModuleType('camera_wrapper_frozen_lifecycle')
                exec(compile(raw, str(path), 'exec'), module.__dict__)
                self.reaper = module.OwnChildReaper()
        self.reaper.begin()

    def actor(self, role, argv, pass_fds=(), alex=False):
        stdout = (self.out / (role + '.stdout')).open('xb')
        stderr = (self.out / (role + '.stderr')).open('xb')
        self.logs.extend((stdout, stderr))
        record = life_record()
        item = {'process': None, 'pidfd': None, 'lifecycle': record}
        self.actors[role] = item
        env = dict(os.environ)
        for key in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME'):
            env.pop(key, None)
        if alex:
            env.update({'XDG_RUNTIME_DIR': '/run/user/1000',
                        'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'})
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            start_new_session=True, close_fds=True, pass_fds=tuple(pass_fds), env=env,
            user=1000 if alex else 0, group=1000 if alex else 0, extra_groups=())
        item['process'] = process
        record.update({'child_started': True, 'pid': process.pid, 'uid': 1000 if alex else 0})
        item['pidfd'] = os.pidfd_open(process.pid, 0)
        record['pidfd_closed'] = False
        self.record['events'].append({'event': role + '_started', 'pid': process.pid,
                                      'monotonic_ns': time.monotonic_ns()})
        return item

    def holder_argv(self, arguments):
        return ['/usr/bin/python3', '-I', '-c', HELD_PYTHON_BOOTSTRAP,
                str(self.source_fds['holder']), self.record['sources']['holder']['sha256'],
                '16384'] + list(arguments)

    def launch_holder(self):
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.channel = parent
        parent.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        child.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        parent.setblocking(False)
        script, module = self.source_fds['holder'], self.source_fds['lease']
        transaction = 'camera-' + hashlib.sha256(self.spec['transaction_id'].encode()).hexdigest()[:48]
        try:
            return self.actor('holder', self.holder_argv(['--module-fd', str(module), '--control-fd', str(child.fileno()),
                '--parent-pid', str(os.getpid()), '--transaction', transaction, '--max-seconds', str(WRAPPER_SECONDS)]),
                (script, module, child.fileno()), alex=True)
        finally:
            child.close()

    def launch_camera(self):
        require(time.monotonic() <= self.started + READY_SECONDS, 'video started after its full budget reserve')
        require(not self.retiring and not self.record['signals'], 'no video child after cancellation')
        require(not any((self.case_root / name).exists() for name in
                        ('execute-once.json', 'result.json', 'evidence', 'acoustic-supervisor')),
                'video plan has already begun; never repeat or adopt a prior result')
        self.planner.source_packet(self.common, self.plan, self.packet)
        request = self.common.write_new(self.out / 'camera-execution-request.json', {'base_plan': self.plan_ref}, 0o400)
        self.record['video_execution_request'] = request
        script = self.source_fds['camera']
        argv = ['/usr/bin/python3', '-I', '-B', '/proc/self/fd/%d' % script,
            '--preparation', PREPARATION_REF['path'], '--expect-preparation-sha256', PREPARATION_REF['sha256'],
            'execute', '--request', request['path'], '--expect-request-sha256', request['sha256']]
        item = self.actor('camera', argv, (script,))
        pid = item['process'].pid
        raw = Path('/proc/%d/stat' % pid).read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        require(int(raw.split(' ', 1)[0]) == pid and int(fields[1]) == os.getpid(),
                'acoustic supervisor is not this exact direct child')
        self.record['camera_operator'] = {'pid': pid, 'parent': int(fields[1]), 'start_ticks': int(fields[19])}
        self.record['camera_argv'] = argv
        return item

    def terminal(self, role):
        item = self.actors.get(role)
        if item is None or item['process'] is None:
            return None
        return self.reaper.peek(item['process'].pid, item['pidfd'])

    def drain(self, fail_on_error=True):
        count = 0
        while self.channel is not None:
            try:
                raw, ancillary, flags, address = self.channel.recvmsg(MAX_PACKET + 1, socket.CMSG_SPACE(12))
            except BlockingIOError:
                return
            if not raw:
                self.record['control_link_eof'] = True
                return
            count += 1
            require(count <= 32 and len(raw) <= MAX_PACKET and flags == 0, 'display packet flood/truncation')
            pid = self.actors['holder']['process'].pid
            credentials = [struct.unpack('3i', value) for level, kind, value in ancillary
                           if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS]
            require(credentials == [(pid, 1000, 1000)], 'display packet credentials differ')
            row = json.loads(raw)
            require(set(row) == {'kind', 'sequence', 'value'} and row['sequence'] == self.sequence + 1,
                    'display packet sequence differs')
            self.sequence = row['sequence']
            kind, value = row['kind'], row['value']
            if kind == 'READY':
                require(self.ready is None and not self.actors.get('camera'), 'unexpected display ready')
                require(value['ready']['power_save_mode'] == 0 and value['ready']['locked'] is True,
                        'display did not become locked normal mode')
                identity = value['physical_device']
                require(identity['by_id'].endswith('usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0')
                        and identity['usb']['idVendor'] == '1e08' and identity['usb']['idProduct'] == '5520'
                        and identity['usb']['serial'] == 'JX20250923V2'
                        and identity['usb_path'].endswith('/usb3/3-4'), 'built-in display lease identity differs')
                self.ready = value
                self.last_heartbeat = time.monotonic()
                self.record['ready'] = value
                self.record['events'].append({'event': 'ready', 'monotonic_ns': time.monotonic_ns()})
            elif kind == 'HEARTBEAT':
                require(self.ready is not None and value['power_save_mode'] == 0 and value['locked'] is True,
                        'display heartbeat without live locked lease')
                require(type(value['monotonic_ns']) is int and
                        0 <= time.monotonic_ns() - value['monotonic_ns'] <= 4_000_000_000,
                        'display heartbeat is stale')
                self.last_heartbeat = time.monotonic()
                self.record['last_heartbeat'] = value
                self.record['heartbeat_count'] = self.record.get('heartbeat_count', 0) + 1
            elif kind == 'ERROR':
                self.record['holder_error'] = value
                if fail_on_error:
                    raise RuntimeError('display holder failed: ' + str(value))
            elif kind == 'RELEASE':
                require(self.release is None, 'duplicate display release')
                self.release = value
                self.record['release'] = value
            else:
                raise RuntimeError('unexpected display holder packet')

    def check_logs(self):
        for handle in self.logs:
            require(os.fstat(handle.fileno()).st_size <= 1024 * 1024, 'owned command log exceeded bound')

    def tick(self):
        self.check_logs()
        self.drain()
        require(time.monotonic() < self.operation_deadline, 'camera wrapper operation budget exhausted')
        require(not self.record.get('control_link_eof') and self.terminal('holder') is None,
                'display holder/link disappeared')
        if self.ready is not None:
            require(time.monotonic() - self.last_heartbeat <= 4, 'display lease heartbeat expired')

    def wait_ready(self):
        deadline = self.started + READY_SECONDS
        while self.ready is None:
            self.tick()
            require(time.monotonic() < deadline, 'display readiness deadline')
            time.sleep(0.05)

    def validate_camera_result(self):
        def read_document(path, bound=2 * 1024 * 1024):
            fd, raw, observed = held_file(path, bound)
            self.fds.append(fd)
            ref = {key: observed[key] for key in ('path', 'bytes', 'sha256')}
            return self.common.parse(raw), ref
        root = self.case_root
        worker, worker_ref = read_document(root / 'result.json')
        supervisor, supervisor_ref = read_document(root / 'acoustic-supervisor/result.json')
        parent, parent_ref = read_document(root / 'acoustic-supervisor/parent.json', 131072)
        claim, claim_ref = read_document(root / 'execute-once.json', 131072)
        validate_video_terminals(self.plan_ref, self.plan, PREPARATION_REF, self.record['camera_operator'],
                                 self.ready['physical_device'], parent, parent_ref,
                                 supervisor, worker, worker_ref, claim)
        runtime = self.planner.named(self.common, self.packet, 'app_runtime.py')
        require(parent['boot_id'] == runtime.boot(), 'acoustic receipt boot differs')
        for name in ('full_decode', 'current_audio', 'current_playback'):
            self.common.read_ref(worker[name])
        self.planner.source_packet(self.common, self.plan, self.packet)
        self.record.update(camera_result=worker_ref, acoustic_supervisor_result=supervisor_ref,
                           acoustic_parent=parent_ref, execute_once_claim=claim_ref)
        self.inner_result = worker
        return worker

    def release_request(self):
        if self.channel is not None and self.terminal('holder') is None:
            raw = json.dumps({'operation': 'release'}).encode()
            require(self.channel.send(raw) == len(raw), 'display release was partial')
            self.record['release_requested_ns'] = time.monotonic_ns()

    def wait_holder(self, seconds):
        deadline = min(time.monotonic() + seconds, self.deadline - 14)
        while self.terminal('holder') is None and time.monotonic() < deadline:
            self.drain(fail_on_error=False)
            time.sleep(0.05)
        self.drain(fail_on_error=False)

    def cancel_camera(self):
        item = self.actors.get('camera')
        if item is None or item['process'] is None or self.terminal('camera') is not None:
            return
        require(item['process'].pid in self.reaper.children(), 'camera cancellation child authority lost')
        self.reaper.signal_target(item['process'].pid)
        require(self.reaper.peek(item['process'].pid, item['pidfd']) is None,
                'camera changed state before cancellation')
        if item['pidfd'] is not None:
            signal.pidfd_send_signal(item['pidfd'], signal.SIGINT)
            self.record['camera_cancel_signal_authority'] = 'held_pidfd'
        else:
            # Kernel-listed, WNOWAIT-proven child of this single-threaded parent:
            # no other waiter can release this PID for reuse. Do not Popen.poll().
            os.kill(item['process'].pid, signal.SIGINT)
            self.record['camera_cancel_signal_authority'] = 'kernel_unreaped_direct_child'
        self.record['camera_cancelled_ns'] = time.monotonic_ns()
        deadline = min(time.monotonic() + CAMERA_GRACE_SECONDS, self.deadline - 14)
        self.record['camera_grace_deadline'] = deadline
        while self.terminal('camera') is None and time.monotonic() < deadline:
            try:
                self.drain(fail_on_error=False)
            except BaseException as error:
                self.remember(error, 'retiring_display_packet')
                # A display failure must not shorten the original camera finally.
            time.sleep(0.05)

    def retire_principals(self):
        deadline = min(time.monotonic() + 5, self.deadline - 9)
        # Retire each exact leader without retiring the other live sibling.
        for role in ('camera', 'holder'):
            item = self.actors.get(role)
            if item is None or item['process'] is None:
                continue
            self.reaper.retire_leader(item['process'], item['pidfd'], item['lifecycle'], self.remember, deadline)
            if item['pidfd'] is not None:
                os.close(item['pidfd'])
                item['pidfd'] = None
                item['lifecycle']['pidfd_closed'] = True
        adopted = {'descendants': [], 'owned_tree_cleanup_complete': False}
        self.reaper.retire_adopted(adopted, self.remember, deadline)
        self.record['adopted_retirement'] = adopted
        self.record['principal_lifecycles'] = {name: row['lifecycle'] for name, row in self.actors.items()}

    def observe_release(self):
        prior = self.ready or (self.release or {}).get('lease')
        if prior is None or not all(k in prior for k in ('owners', 'before', 'inhibitor')):
            self.record['release_observation_unavailable'] = True
            return
        self.reaper.before_command()
        path = self.out / 'lease-before-observer.json'
        write_json(path, prior)
        input_fd, _, _ = held_file(path, MAX_PACKET)
        self.fds.append(input_fd)
        script, module = self.source_fds['holder'], self.source_fds['lease']
        deadline = min(time.monotonic() + 15, self.deadline - 4)
        try:
            observer = self.actor('release_observer', self.holder_argv([
                '--module-fd', str(module), '--observe-fd', str(input_fd)]), (script, module, input_fd), alex=True)
            info = self.reaper.await_exit(observer['process'].pid, observer['pidfd'], deadline)
            require(info.si_code == os.CLD_EXITED and info.si_status == 0, 'release observer failed')
        finally:
            observer = self.actors.get('release_observer')
            if observer is not None and observer['process'] is not None:
                self.record['release_observer_lifecycle'] = observer['lifecycle']
                self.reaper.retire(observer['process'], observer['pidfd'], observer['lifecycle'], self.remember, deadline)
                if observer['pidfd'] is not None:
                    os.close(observer['pidfd'])
                observer['pidfd'] = None
                observer['lifecycle']['pidfd_closed'] = True
        fd, raw, ref = held_file(self.out / 'release_observer.stdout', MAX_PACKET)
        self.fds.append(fd)
        observation = json.loads(raw)
        self.record['independent_release_observation'] = observation
        require(observation['inhibitor_removed'] is True, 'owned DBus inhibitor remains after holder retirement')

    def run(self):
        previous = {number: signal.signal(number, self.cancelled)
                    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
        signal.setitimer(signal.ITIMER_REAL, max(0.001, self.operation_deadline - time.monotonic()))
        try:
            self.load_sources()
            self.launch_holder()
            self.wait_ready()
            self.launch_camera()
            while self.terminal('camera') is None:
                self.tick()
                time.sleep(0.05)
            self.tick()
            status = self.terminal('camera')
            self.record['camera_terminal_before_reap'] = self.reaper.observed(status)
            require(status.si_code == os.CLD_EXITED and status.si_status == 0, 'original camera process failed')
            self.validate_camera_result()
            self.release_request()
            self.wait_holder(15)
            status = self.terminal('holder')
            require(status is not None and status.si_code == os.CLD_EXITED and status.si_status == 0
                    and self.release is not None and self.release.get('success') is True,
                    'display normal release did not finish')
        except BaseException as error:
            self.error = error
            self.remember(error, 'supervision')
            self.record['ready_revoked'] = True
            self.record['ready_revoked_ns'] = time.monotonic_ns()
        finally:
            self.retiring = True
            signal.setitimer(signal.ITIMER_REAL, 0)
            if self.reaper is not None and self.reaper.active:
                if self.error is not None:
                    # Holder release proceeds while the camera gets its full 60 s worker finally and 30 s acoustic retirement.
                    try:
                        self.release_request()
                    except BaseException as error:
                        self.remember(error, 'holder_release_request')
                    try:
                        self.cancel_camera()
                    except BaseException as error:
                        self.remember(error, 'camera_graceful_retirement')
                    try:
                        self.wait_holder(15)
                    except BaseException as error:
                        self.remember(error, 'holder_graceful_retirement')
                try:
                    self.retire_principals()
                    self.observe_release()
                except BaseException as error:
                    self.remember(error, 'owned_retirement')
                try:
                    self.reaper.finish()
                except BaseException as error:
                    self.remember(error, 'owned_lifecycle_finish')
                self.record['subreaper'] = self.reaper.record
            if self.channel is not None:
                self.channel.close()
            for handle in self.logs:
                handle.close()
            for fd in reversed(self.fds):
                try:
                    os.close(fd)
                except OSError as error:
                    self.remember(error, 'held_descriptor_close')
        complete = (not self.record['errors'] and not self.record['signals'] and self.inner_result is not None
            and self.record.get('subreaper', {}).get('final_children_empty') is True
            and self.record.get('independent_release_observation', {}).get('inhibitor_removed') is True
            and self.record.get('independent_release_observation', {}).get('entry_mode_matches') is True
            and self.record.get('independent_release_observation', {}).get('owners_unchanged') is True
            and self.record.get('independent_release_observation', {}).get('current', {}).get('locked') is True
            and self.record.get('adopted_retirement', {}).get('owned_tree_cleanup_complete') is True
            and self.record['adopted_retirement'].get('descendants') == []
            and set(self.actors) == {'camera', 'holder', 'release_observer'}
            and all(all(item['lifecycle'].get(k) is True for k in ('child_reaped', 'pidfd_closed'))
                and item['lifecycle'].get('returncode') == 0 for item in self.actors.values()))
        result = dict(self.inner_result or {'plan': self.plan_ref, 'action_attempted': 'camera' in self.actors})
        result.update({'schema': 'pocket4-current-camera-video-display-result-v1', 'success': complete,
                       'camera_video_and_display_verified': complete, 'case_business_success_verified': complete, 'display_lease_qualified': complete,
                       'inner_video_state': result.get('state'),
                       'state': ('VIDEO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING'
                                 if complete else 'FAILED_OR_UNKNOWN_RETAINED'),
                       'whole_app_business_accepted': False, 'visual_review_required': True,
                       'video_audio_playback_qualified': complete, 'runtime_qualified': False, 'camera_recovery_qualified': False,
                       'outcome_unknown': not complete and bool(self.actors), 'automatic_retry': False})
        self.record['finished_monotonic_ns'] = time.monotonic_ns()
        self.record['success'] = complete
        result['display_lease_wrapper'] = self.record
        # Freeze cancellation only after all work and owned retirement. A signal
        # pending before this boundary fails; one arriving during terminal write
        # is after completion and cannot create success-file/failed-exit mismatch.
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, set(previous))
        try:
            pending = signal.sigpending() & set(previous)
            for number in sorted(pending):
                self.cancelled(number, None)
            if self.record['signals']:
                complete = False
                self.record['success'] = False
                result.update(success=False, camera_video_and_display_verified=False, case_business_success_verified=False, video_audio_playback_qualified=False, display_lease_qualified=False, state='FAILED_OR_UNKNOWN_RETAINED', outcome_unknown=bool(self.actors))
            self.record['cancellation_commit_boundary'] = {
                'monotonic_ns': time.monotonic_ns(),
                'scope': 'after work and owned retirement, before terminal serialization',
                'prior_cancellation_fails': True, 'later_cancellation_changes_result': False}
            self.committed = True
            write_json(self.out / 'result.json', result)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
            for number, old in previous.items():
                signal.signal(number, old)
        return 0 if complete else (4 if self.actors else 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True, type=Path)
    parser.add_argument('--expect-preparation-sha256', required=True)
    parser.add_argument('mode', choices=('inspect-source', 'execute'), nargs='?', default='inspect-source')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--expect-input-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    packet = configure_video_preparation(args.preparation, args.expect_preparation_sha256)
    if args.mode == 'inspect-source':
        require(args.input is None and args.output is None and args.expect_input_sha256 is None,
                'video wrapper inspection has no live input')
        refs = []
        for role, (path, digest, bound) in SOURCES.items():
            fd, _, ref = held_file(path, bound, digest)
            try:
                refs.append({'role': role, **ref})
            finally:
                os.close(fd)
        print(json.dumps({'schema': 'pocket4-camera-video-display-source-inspection-v1',
            'sources': refs, 'video_source_files': len(packet['files']), 'wrapper_seconds': WRAPPER_SECONDS,
            'acoustic_supervisor_seconds': CAMERA_SECONDS, 'cleanup_grace_seconds': CAMERA_GRACE_SECONDS,
            'Main_actions': 0, 'DBus_actions': 0, 'Android_UI_actions': 0,
            'runtime_qualified': False, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    require(args.input is not None and args.output is not None
            and re.fullmatch('[0-9a-f]{64}', args.expect_input_sha256 or ''),
            'explicit reviewed video wrapper input and pin required')
    output = args.output.absolute()
    require(output == output.resolve() and output.parent == QUALIFICATION
            and re.fullmatch('camera-video-display-[0-9a-f]{32}', output.name),
            'fresh private video display output required')
    fd, raw, reference = held_file(args.input, 131072, args.expect_input_sha256)
    try:
        runner = Supervisor(raw, output)
        output.mkdir(mode=0o700)
        with (output / 'input.json').open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        runner.record['reviewed_input'] = reference
        code = runner.run()
        print(json.dumps({'result': str(output / 'result.json'), 'success': code == 0,
                          'camera_video_and_display_verified': code == 0,
                          'whole_app_business_accepted': False, 'outcome_unknown': code == 4, 'exit_code': code}), flush=True)
        return code
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())
