#!/usr/bin/env python3
"""Bind the frozen photo-only Camera case to one qualified normal display lease."""
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
PREPARED = ROOT / 'display-lease-prepared-20261107-r2/source'
QUALIFICATION = ROOT.parent / 'qualification'
PHOTO_PREPARED = QUALIFICATION / 'camera-app-photo-preparation-resume-20261107-r4'
PREPARATION_REF = {'path': '/home/alex/work/pocket4-android-final/qualification/camera-app-photo-preparation-resume-20261107-r4/preparation.json', 'bytes': 22598, 'sha256': '2279201a341ee941e7d733763ef17b9ab7e739d6aa2e2c03692de9bd9cc7cb32'}
SOURCES = {
    'holder': (PREPARED / 'display_holder.py', '68fef3e0a46ab2f1b5d783ab5640add6d2f6625c9655a803efb25409ad79917f', 16384),
    'lease': (PREPARED / 'display_lease.py', '81f34cdbc75a2cf4e092a961fe4dce5d23522842c0ec54cdcff4fc9c99e4dbfd', 32768),
    'camera': (PHOTO_PREPARED / 'source/camera_entry.py', '95a1fc750d47ebd5a31271a50d2a1e1859ae8829aa44089e9287eeb7c59e43c1', 65536),
    'preparation': (Path(PREPARATION_REF['path']), PREPARATION_REF['sha256'], 131072),
    'lifecycle': (ROOT.parent / 'framework/runtime_support/capture_lifecycle.py',
                  '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877', 32768),
}
MAX_PACKET = 65536
WRAPPER_SECONDS = 475
READY_SECONDS = 20
CAMERA_SECONDS = 400  # Original 360 second work + 40 second finally contract.
CAMERA_GRACE_SECONDS = 40
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


class Supervisor:
    """Two sibling principals; the frozen photo case owns only its own children."""
    def __init__(self, raw, output, sources=SOURCES):
        require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
                'root camera wrapper context required')
        self.raw, self.out, self.spec = raw, output, json.loads(raw)
        require(len(raw) <= 131072 and type(self.spec) is dict
                and set(self.spec) == {'schema', 'plan', 'source_preparation', 'automatic_retry', 'whole_app_business_accepted'}
                and self.spec['schema'] == 'pocket4-camera-photo-display-input-v1'
                and self.spec['source_preparation'] == PREPARATION_REF
                and self.spec['automatic_retry'] is False and self.spec['whole_app_business_accepted'] is False,
                'exact photo-only display request required')
        self.plan_ref = self.spec['plan']
        require(type(self.plan_ref) is dict and set(self.plan_ref) == {'path', 'bytes', 'sha256'}
                and type(self.plan_ref['bytes']) is int and 0 < self.plan_ref['bytes'] <= 131072
                and re.fullmatch('[0-9a-f]{64}', self.plan_ref['sha256']), 'exact reviewed photo plan reference required')
        plan_path = Path(self.plan_ref['path']); self.case_root = plan_path.parent
        require(plan_path.is_absolute() and plan_path.resolve() == plan_path and plan_path.name == 'plan.json'
                and self.case_root.parent == QUALIFICATION
                and re.fullmatch('business-camera-photo-plan-[0-9a-f]{32}', self.case_root.name),
                'only a newly factory-created photo plan can enter the display lease')
        fd, plan_raw, _ = held_file(plan_path, 131072, self.plan_ref['sha256'])
        try:
            require(len(plan_raw) == self.plan_ref['bytes'], 'photo plan size changed')
            self.plan = json.loads(plan_raw)
        finally:
            os.close(fd)
        require(self.plan.get('schema') == 'pocket4-final-camera-photo-plan-v1'
                and self.plan.get('kind') == 'camera_photo' and self.plan.get('case_root') == str(self.case_root)
                and self.plan.get('source_preparation') == PREPARATION_REF
                and self.plan.get('automatic_retry') is False and self.plan.get('whole_app_business_accepted') is False,
                'the request is not this frozen photo-only plan')
        require(not any((self.case_root / name).exists() for name in ('execute-once.json', 'result.json', 'evidence')),
                'photo execution already begun; no implicit retry')
        self.spec['transaction_id'] = 'photo-' + self.case_root.name.rsplit('-', 1)[1]
        self.sources = {**sources, 'plan': (plan_path, self.plan_ref['sha256'], 131072)}
        self.fds, self.logs, self.actors = [], [], {}
        self.channel = None
        self.reaper = None
        self.ready = None
        self.release = None
        self.last_heartbeat = None
        self.sequence = 0
        self.retiring = False
        self.committed = False
        self.after_commit_signals = []
        self.error = None
        self.inner_result = None
        self.record = {'schema': 'pocket4-camera-photo-display-supervision-v1',
            'started_monotonic_ns': time.monotonic_ns(), 'errors': [], 'signals': [],
            'sources': {}, 'events': [], 'ready_revoked': False, 'automatic_retry': False,
            'Main_lifecycle_actions': 0, 'USB_actions': 0, 'global_power_setting_changes': 0,
            'public_lifecycle_changed': False, 'principal_structure': 'root owns alex display holder and root photo case siblings'}
        self.started = time.monotonic()
        self.operation_deadline = self.started + READY_SECONDS + CAMERA_SECONDS
        self.deadline = self.started + WRAPPER_SECONDS
        self.record['budgets'] = {'wrapper_seconds': WRAPPER_SECONDS, 'ready_seconds': READY_SECONDS,
            'photo_with_cleanup_seconds': CAMERA_SECONDS, 'camera_cancellation_grace_seconds': CAMERA_GRACE_SECONDS,
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
        require(time.monotonic() <= self.started + READY_SECONDS, 'photo started after its full budget reserve')
        require(not any((self.case_root / name).exists() for name in ('execute-once.json', 'result.json', 'evidence')),
                'photo plan has already begun; never repeat or adopt a prior result')
        script = self.source_fds['camera']
        argv = ['/usr/bin/python3', '-I', '-B', '/proc/self/fd/%d' % script,
            '--preparation', PREPARATION_REF['path'], '--expect-preparation-sha256', PREPARATION_REF['sha256'],
            'execute', '--request', self.plan_ref['path'], '--expect-request-sha256', self.plan_ref['sha256']]
        item = self.actor('camera', argv, (script,))
        # The single owner has not reaped this direct child, so its PID/start
        # identity cannot be reused while it is bound to execute-once.json.
        pid = item['process'].pid
        raw = Path('/proc/%d/stat' % pid).read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        require(int(raw.split(' ', 1)[0]) == pid and int(fields[1]) == os.getpid(),
                'photo process is not this exact direct child')
        self.record['photo_operator'] = {'pid': pid, 'parent': int(fields[1]), 'start_ticks': int(fields[19])}
        self.record['photo_argv'] = argv
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
        fd, raw, reference = held_file(self.case_root / 'result.json', 2 * 1024 * 1024)
        self.fds.append(fd)
        result = json.loads(raw)
        self.inner_result = result
        self.record['camera_result'] = reference
        require(result.get('schema') == 'pocket4-final-camera-photo-result-v1'
                and result.get('plan') == self.plan_ref
                and result.get('state') == 'PHOTO_CAPTURE_PERSISTENCE_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING'
                and result.get('photo_capture_persistence_verified') is True
                and result.get('outcome_unknown') is False
                and result.get('pending_effects') == [] and result.get('owned_task_remaining') is None
                and result.get('native_launch_calls') == 2 and result.get('shutter_calls') == 1
                and result.get('own_task_remove_calls') == 2
                and result.get('whole_app_business_accepted') is False
                and result.get('camera_business_gates_complete') is False
                and result.get('visual_review_required') is True
                and result.get('video_audio_playback_qualified') is False
                and result.get('camera_recovery_qualified') is False
                and result.get('received_signals') == [] and result.get('secondary_errors') == [],
                'actual photo case did not return its exact narrow successful contract')
        required = ('own_task_cleanup_verified', 'current_Main_APIs_closed', 'whole_case_OFD_closed',
            'evidence_witness_closed', 'final_source_and_identity_chain_unchanged',
            'one_new_image', 'photo_persisted_after_close', 'photo_persisted_after_reopen',
            'other_tasks_preserved', 'installed_apk_and_data_identity_preserved',
            'provider_owner_preserved', 'original_photo_state_machine_completed')
        require(all(result.get(key) is True for key in required), 'photo lifecycle or original business gate incomplete')
        commit = result.get('cancellation_commit', {})
        require(commit.get('observed_before_commit') == [] and commit.get('pending_at_commit') == []
                and commit.get('decision_frozen_after_context_exit') is True,
                'photo cancellation or context-exit commit incomplete')
        fd, raw, claim_ref = held_file(self.case_root / 'execute-once.json', 131072)
        self.fds.append(fd); claim = json.loads(raw)
        require(claim.get('plan') == self.plan_ref and claim.get('automatic_retry') is False,
                'photo execute-once claim is for another plan')
        operator = claim.get('operator', {})
        require(all(operator.get(k) == v for k, v in self.record['photo_operator'].items())
                and operator.get('uids') == [0, 0, 0, 0], 'photo result was not created by the exact owned root child')
        self.record['execute_once_claim'] = claim_ref
        require(result.get('physical_device') == self.ready['physical_device'],
                'photo and display lease bind different physical devices')
        return result

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
                    # Holder release proceeds while the camera gets its full 40 s finally.
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
            and self.record.get('independent_release_observation', {}).get('current', {}).get('locked') is True)
        result = dict(self.inner_result or {'plan': self.plan_ref, 'action_attempted': 'camera' in self.actors})
        result.update({'schema': 'pocket4-final-camera-photo-display-result-v1', 'success': complete,
                       'photo_capture_persistence_verified': complete, 'display_lease_qualified': complete,
                       'inner_photo_state': result.get('state'),
                       'state': ('PHOTO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING'
                                 if complete else 'FAILED_OR_UNKNOWN_RETAINED'),
                       'whole_app_business_accepted': False, 'visual_review_required': True,
                       'video_audio_playback_qualified': False, 'camera_recovery_qualified': False,
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
                result.update(success=False, photo_capture_persistence_verified=False, display_lease_qualified=False, state='FAILED_OR_UNKNOWN_RETAINED', outcome_unknown=bool(self.actors))
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
    parser.add_argument('mode', choices=('inspect-source', 'execute'), nargs='?', default='inspect-source')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--expect-input-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'inspect-source':
        require(args.input is None and args.output is None and args.expect_input_sha256 is None,
                'photo wrapper inspection has no live input')
        refs = []
        for role, (path, sha, bound) in SOURCES.items():
            fd, raw, ref = held_file(path, bound, sha)
            try:
                refs.append({'role': role, **ref})
                if role == 'preparation':
                    prep = json.loads(raw)
                    require(len(raw) == PREPARATION_REF['bytes'], 'photo preparation size changed')
            finally:
                os.close(fd)
        for ref in prep['files']:
            fd, raw, _ = held_file(ref['path'], 262144, ref['sha256'])
            try:
                require(len(raw) == ref['bytes'], 'prepared photo source size changed')
            finally:
                os.close(fd)
        print(json.dumps({'schema': 'pocket4-camera-photo-display-source-inspection-v1',
            'sources': refs, 'photo_source_files': len(prep['files']), 'wrapper_seconds': WRAPPER_SECONDS,
            'photo_seconds': CAMERA_SECONDS, 'cleanup_grace_seconds': CAMERA_GRACE_SECONDS,
            'Main_actions': 0, 'DBus_actions': 0, 'Android_UI_actions': 0, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    require(args.input is not None and args.output is not None
            and re.fullmatch('[0-9a-f]{64}', args.expect_input_sha256 or ''),
            'explicit reviewed photo wrapper input and pin required')
    output = args.output.absolute()
    require(output == output.resolve() and output.parent == QUALIFICATION
            and re.fullmatch('camera-photo-display-[0-9a-f]{32}', output.name),
            'fresh private photo display output required')
    fd, raw, reference = held_file(args.input, 131072, args.expect_input_sha256)
    try:
        runner = Supervisor(raw, output)
        output.mkdir(mode=0o700)
        with (output / 'input.json').open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        runner.record['reviewed_input'] = reference
        code = runner.run()
        print(json.dumps({'result': str(output / 'result.json'), 'success': code == 0,
                          'photo_capture_persistence_verified': code == 0,
                          'whole_app_business_accepted': False, 'outcome_unknown': code == 4, 'exit_code': code}), flush=True)
        return code
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())
