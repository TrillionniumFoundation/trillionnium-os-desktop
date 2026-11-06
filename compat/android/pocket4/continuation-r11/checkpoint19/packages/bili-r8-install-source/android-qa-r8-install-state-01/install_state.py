#!/usr/bin/env python3
"""One frozen owned APK install and one no-UiAutomation state observation.

Default PLAN is inert. Production requires the exact external source manifest,
the fixed actual r8 build01/stage receipts and signed APK, the frozen R4 recorder,
a fresh flow/step, and its original Main fences and action lock. No UI, v2
fallback, permission grant, install replacement, task or commercial data action.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r8-install-state-01')
SOURCE = ROOT / 'source'
NONCE = 'fd9784f9e464119899726c3b583243a8'
STATE_NONCE = 'c296619272cb68fddb8923891ff0dff9'
FLOW = Path('/home/alex/work/pocket4-bilibili-owned-qa-r8-flow-' + NONCE)
STEP = 'install-state-r8-01'
SELF = 'org.droidloom.qa.bili.r8'
QA_ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r8-source-01/source')
QA_MANIFEST = '8e3454bcc9ebe1ff55dcaf62706ce1176cfa1d0f0ede7099cbbfa46f4ad53f1e'
BUILD = Path('/home/alex/work/pocket4-owned-bili-qa-r8-build-01/build-result.json')
BUILD_SHA = '8954a0b50093ed2110bac1e493cc2a847dfe326cb69f7fe03091aaa91d878b3c'
BUILD_BYTES = 29232
STAGE = Path('/home/alex/work/pocket4-owned-bili-qa-r8-source-01/stage-result.json')
STAGE_SHA = '8eaadc3544d9b2a535ec3713120c053c40cc4eb5c16fd83736aad4c0e4d51438'
STAGE_BYTES = 1939
APK = Path('/home/alex/work/pocket4-owned-bili-qa-r8-build-01/owned-bili-qa.apk')
APK_SHA = 'b576afe56b97160dc341fe15973f5afe23db03dc2961aedaa500f1527ec13122'
APK_BYTES = 37008
SIGNER_SHA = 'b1ec4d840f5dd85513d3b3c08fbf97d829b580d4c718d6bf30cce5a8270a457d'
RECORDER_ROOT = SOURCE / 'recorder-r4'
RECORDER_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
REFERENCE_SHA = 'e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'
GUEST_DIR_NAME = 'pocket4-owned-bili-qa-' + NONCE
GUEST_DIR = '/data/local/tmp/' + GUEST_DIR_NAME
GUEST_APK = GUEST_DIR + '/owned-bili-qa.apk'
PACKAGE_LIST = ['/system/bin/cmd', 'package', 'list', 'packages', '-u', '-U', '--user', 'all', SELF]
INSTALLED_ALL_USERS = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', 'all', SELF]
INSTALL = ['/system/bin/cmd', 'package', 'install', '-R', '-t', '--user', '0', '--pkg', SELF, GUEST_APK]
ACTION_LOCK_WAIT_SECONDS = 5.0
ACTION_LOCK_POLL_SECONDS = 0.05
EXPECTED_SOURCE_FILES = {'install_state.py', 'stage_execute.py', 'make_request.py',
                         'references/readonly_r3_coordinator.py', 'INPUTS.json', 'README.md',
                         'references/R3-SOURCE-MANIFEST.json', 'r4/source-manifest.json',
                         'r4/bound_android_transport.py', 'session_binding.py'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=1048576, expected=None, size=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                0 <= before.st_size <= maximum, 'INPUT_SHAPE_OR_BOUND: ' + str(path))
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
            require(count <= maximum, 'INPUT_GREW: ' + str(path))
        after = os.fstat(fd)
        fields = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(before, k) == getattr(after, k) for k in fields) and count == before.st_size,
                'INPUT_CHANGED: ' + str(path))
        raw = b''.join(chunks)
        require(expected is None or digest(raw) == expected, 'INPUT_SHA_CHANGED: ' + str(path))
        require(size is None or len(raw) == size, 'INPUT_SIZE_CHANGED: ' + str(path))
        return raw
    finally:
        os.close(fd)


def module(path, expected, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(read(path, expected=expected), str(path), 'exec'), value.__dict__)
    return value


def verify_source(expected):
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'EXTERNAL_SOURCE_SHA_REQUIRED')
    manifest = json.loads(read(HERE/'SOURCE_PINS.json', 131072, expected))
    require(set(manifest['files']) == EXPECTED_SOURCE_FILES, 'EXACT_SOURCE_CLOSURE_REQUIRED')
    for name, row in manifest['files'].items():
        read(HERE/name, expected=row['sha256'], size=row['bytes'])
    return manifest


def references():
    return module(HERE/'references/readonly_r3_coordinator.py', REFERENCE_SHA, 'qa_install_prior_r3')


def qualified_inputs():
    # The QA adapter validates the real complete 13-command build plus 22 Java and 32 protocol controls, all source
    # and tool pins, manifest permissions/components, exact APK and one signer.
    source_raw = read(QA_ROOT/'SOURCE_PINS.json', 131072, QA_MANIFEST)
    source = json.loads(source_raw)
    adapter = module(QA_ROOT/'qa_adapter.py', source['files']['qa_adapter.py']['sha256'], 'qa_install_adapter')
    manifest = adapter.own_source(QA_MANIFEST)
    qa = adapter.load(QA_ROOT/'qa_contract.py', manifest['files']['qa_contract.py']['sha256'], 'qa_install_contract')
    builder = adapter.load(QA_ROOT/'build_candidate.py', manifest['files']['build_candidate.py']['sha256'], 'qa_install_builder')
    read(BUILD, expected=BUILD_SHA, size=BUILD_BYTES)
    args = types.SimpleNamespace(build_receipt=BUILD, build_receipt_sha256=BUILD_SHA,
        source_manifest_sha256=QA_MANIFEST, apk_sha256=APK_SHA, signer_certificate_sha256=SIGNER_SHA)
    proof = adapter.qualified_build(args, manifest, builder)
    require(proof['APK'] == {'path':str(APK), 'bytes':APK_BYTES, 'sha256':APK_SHA}, 'FIXED_ACTUAL_APK_REQUIRED')
    stage = json.loads(read(STAGE, expected=STAGE_SHA, size=STAGE_BYTES))
    require(stage.get('state') == 'OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN' and
            stage.get('source_manifest_sha256') == QA_MANIFEST and stage.get('build_returncode') == 0 and
            stage.get('error') is None and stage.get('secondary_errors') == [] and
            stage.get('build_result') == {'path':str(BUILD),'bytes':BUILD_BYTES,'sha256':BUILD_SHA},
            'ACTUAL_STAGE_RECEIPT_REQUIRED')
    data = read(APK, APK_BYTES, APK_SHA, APK_BYTES)
    proof['stage_receipt_sha256'] = STAGE_SHA
    return adapter, qa, proof, data


def acquire_action_lock(path, observation):
    """Wait only for the original exclusive lock; return one owned FD."""
    start = time.monotonic()
    deadline = start + ACTION_LOCK_WAIT_SECONDS
    observation.update({'path':str(path),'wait_limit_seconds':ACTION_LOCK_WAIT_SECONDS,
        'phase':'open','attempts':0,'busy_attempts':0,'acquired':False,
        'fd_closed_on_error':False,'Android_actions_attempted':0})
    fd = None
    first_busy = None
    try:
        fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600)
        observation['phase'] = 'validate_opened_inode'
        initial = os.fstat(fd)
        require(stat.S_ISREG(initial.st_mode) and initial.st_nlink == 1 and initial.st_uid == 0,
                'UNSAFE_ACTION_LOCK')
        observation['opened_identity'] = {'device':initial.st_dev,'inode':initial.st_ino,
            'mode':initial.st_mode,'uid':initial.st_uid,'gid':initial.st_gid,'nlink':initial.st_nlink}
        while True:
            observation['elapsed_seconds'] = time.monotonic()-start
            if time.monotonic() >= deadline:
                observation['phase'] = 'lock_deadline'
                if first_busy is not None:
                    raise first_busy
                raise TimeoutError(errno.ETIMEDOUT, 'ACTION_LOCK_ADMISSION_DEADLINE')
            observation['phase'] = 'flock_exclusive_nonblocking'
            observation['attempts'] += 1
            try:
                fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:
                observation['last_errno'] = error.errno
                if error.errno != errno.EAGAIN:
                    raise
                if first_busy is None:
                    first_busy = error
                observation['busy_attempts'] += 1
                observation['phase'] = 'waiting_same_open_inode'
                remaining = deadline-time.monotonic()
                if remaining > 0:
                    time.sleep(min(ACTION_LOCK_POLL_SECONDS,remaining))
                continue
            observation['phase'] = 'verify_locked_inode'
            held = os.fstat(fd)
            named = os.stat(path, follow_symlinks=False)
            require(all(stat.S_ISREG(row.st_mode) and row.st_nlink == 1 and row.st_uid == 0 and
                        (row.st_dev,row.st_ino) == (initial.st_dev,initial.st_ino)
                        for row in (held,named)), 'ACTION_LOCK_NAME_OR_HELD_INODE_CHANGED')
            require(time.monotonic() < deadline, 'ACTION_LOCK_ADMISSION_EXCEEDED_DEADLINE')
            observation.update({'phase':'acquired','acquired':True,
                'elapsed_seconds':time.monotonic()-start,'same_inode_confirmed':True})
            return fd
    except BaseException as original:
        observation['error_type'] = type(original).__name__
        observation['errno'] = getattr(original,'errno',None)
        observation['elapsed_seconds'] = time.monotonic()-start
        if fd is not None:
            try:
                os.close(fd)
                observation['fd_closed_on_error'] = True
            except BaseException as secondary:
                observation['close_error'] = {'type':type(secondary).__name__,
                    'errno':getattr(secondary,'errno',None),'message':str(secondary)}
                original.add_note('action lock FD close failed: '+repr(secondary))
        raise


def recorder_module():
    manifest = json.loads(read(RECORDER_ROOT/'source-manifest.json', 131072, RECORDER_MANIFEST))
    return module(RECORDER_ROOT/'recorder.py', manifest['files']['recorder.py']['sha256'], 'qa_install_recorder')


def error_record(phase, error):
    value = {'phase':phase, 'type':type(error).__name__, 'message':str(error)}
    if isinstance(error, OSError):
        value['errno'] = error.errno
    for name in ('command_observation', 'details', '__notes__'):
        if hasattr(error, name):
            value[name] = getattr(error, name)
    return value


def remember(result, phase, error):
    value = error_record(phase, error)
    if result['error'] is None:
        result['error'] = value
    else:
        result['secondary_errors'].append(value)
    result['ok'] = False


def command(flow, argv, timeout=8, mutation=False):
    # This returns only after the real frozen command joined, the lease exited
    # and the mandatory post guard succeeded. Preserve all original failures.
    index = flow.command_index
    out = flow.android(argv, timeout, mutation=mutation)
    require(flow.command_index == index + 1, 'ONE_ACTUAL_COMMAND_REQUIRED')
    stem = flow.step / ('command-%03d' % flow.command_index)
    raw = read(str(stem)+'.result.json', 65536); row = json.loads(raw)
    err = read(str(stem)+'.stderr', 1048576)
    require(row.get('returncode') == 0 and row.get('spawned') is True and
            row.get('owned_command_joined') is True and row.get('timed_out') is False and
            row.get('errors') == [] and row.get('stdout_sha256') == digest(out) and
            row.get('stderr_sha256') == digest(err) and err == b'', 'EXACT_JOINED_QUIET_COMMAND_REQUIRED')
    return out, {'command':stem.name, 'result_sha256':digest(raw),
                 'stdout_sha256':digest(out), 'stderr_sha256':digest(err)}


def uid_from(raw):
    text = raw.decode('utf-8', 'strict')
    match = re.fullmatch(re.escape('package:'+SELF+' uid:') + r'([0-9]+)\n', text)
    require(match is not None, 'ONE_EXACT_NEW_PACKAGE_UID_REQUIRED')
    uid = int(match[1])
    require(10000 <= uid < 100000 and uid not in (10117,10125,10164,10165,10166,10169,10170,10175,10184,10202), 'NEW_APP_UID_REQUIRED')
    return uid


class OwnedApk:
    """Only a fresh own directory/file below the held Main root; no recursion."""
    def __init__(self, target):
        self.target = target
        self.parent = self.directory = self.file = -1
        self.directory_created = False
        self.file_created = False
        self.identity = self.directory_identity = None

    @staticmethod
    def identity_of(fd):
        s = os.fstat(fd)
        return {'device':s.st_dev, 'inode':s.st_ino, 'mode':s.st_mode,
                'uid':s.st_uid, 'gid':s.st_gid, 'nlink':s.st_nlink, 'bytes':s.st_size}

    def stage(self, data):
        require(len(data) == APK_BYTES and digest(data) == APK_SHA, 'ACTUAL_APK_BYTES_REQUIRED')
        self.parent = self.target.open_root('/data/local/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.mkdir(GUEST_DIR_NAME, 0o711, dir_fd=self.parent)
        self.directory_created = True
        self.directory = os.open(GUEST_DIR_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=self.parent)
        self.directory_identity = self.identity_of(self.directory)
        require(self.directory_identity['uid'] == 0, 'OWNED_DIRECTORY_UID_CHANGED')
        os.fchmod(self.directory, 0o711)
        self.directory_identity = self.identity_of(self.directory)
        self.file = os.open('owned-bili-qa.apk', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                            0o600, dir_fd=self.directory)
        self.file_created = True
        count = 0
        while count < len(data):
            wrote = os.write(self.file, data[count:])
            require(wrote > 0, 'OWNED_APK_WRITE_STALLED'); count += wrote
        os.fsync(self.file)
        os.fchmod(self.file, 0o444)
        self.identity = self.identity_of(self.file)
        require(self.identity['uid'] == 0 and self.identity['nlink'] == 1 and
                stat.S_ISREG(self.identity['mode']) and self.identity['bytes'] == APK_BYTES,
                'OWNED_STAGED_APK_SHAPE_CHANGED')
        os.fsync(self.directory); os.fsync(self.parent)
        raw, meta = self.target.read_file(GUEST_APK, APK_BYTES, single_link=True)
        require(digest(raw) == APK_SHA and
                (meta['device'],meta['inode'],meta['bytes']) ==
                (self.identity['device'],self.identity['inode'],APK_BYTES), 'STAGED_PATH_NOT_OWNED_APK')
        return {'path':GUEST_APK, 'sha256':APK_SHA, 'file':self.identity, 'directory':self.directory_identity}

    def close(self):
        # Evidence/read/guard errors cannot skip independent FD closure. An
        # ambiguous name is retained, never recursively removed or overwritten.
        errors = []
        try:
            if self.file_created:
                require(self.directory >= 0 and self.file >= 0, 'OWNED_FILE_FDS_REQUIRED')
                expected = os.fstat(self.file)
                current = os.stat('owned-bili-qa.apk', dir_fd=self.directory, follow_symlinks=False)
                require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
                        (current.st_dev,current.st_ino) == (expected.st_dev,expected.st_ino),
                        'OWNED_APK_CLEANUP_IDENTITY_CHANGED')
                os.unlink('owned-bili-qa.apk', dir_fd=self.directory)
                os.fsync(self.directory)
        except BaseException as error:
            errors.append(error_record('owned_staged_file_retire',error))
        try:
            if self.directory_created:
                require(self.parent >= 0 and self.directory >= 0, 'OWNED_DIRECTORY_FDS_REQUIRED')
                expected = os.fstat(self.directory)
                current = os.stat(GUEST_DIR_NAME, dir_fd=self.parent, follow_symlinks=False)
                require(stat.S_ISDIR(current.st_mode) and
                        (current.st_dev,current.st_ino) == (expected.st_dev,expected.st_ino),
                        'OWNED_DIRECTORY_CLEANUP_IDENTITY_CHANGED')
                require(os.listdir(self.directory) == [], 'OWNED_DIRECTORY_NOT_EMPTY')
                os.rmdir(GUEST_DIR_NAME, dir_fd=self.parent)
                os.fsync(self.parent)
        except BaseException as error:
            errors.append(error_record('owned_staged_directory_retire',error))
        for name in ('file','directory','parent'):
            fd = getattr(self,name); setattr(self,name,-1)
            if fd >= 0:
                try:
                    os.close(fd)
                except BaseException as error:
                    errors.append(error_record('owned_fd_close_'+name,error))
        if errors:
            error = RuntimeError('OWNED_STAGING_RETIREMENT_FAILED')
            error.details = errors
            raise error
        return {'staged_apk_created':self.file_created, 'staged_directory_created':self.directory_created,
                'staged_apk_removed':self.file_created, 'staged_directory_removed':self.directory_created,
                'authority_fds_closed':True, 'recursive_cleanup':False}


def worker(expected):
    runtime_manifest = verify_source(expected)
    require(os.getuid() == os.geteuid() == 0 and HERE == SOURCE and ROOT.is_dir(), 'EXACT_ROOT_WORKER_REQUIRED')
    adapter, qa, proof, apk = qualified_inputs()
    recorder = recorder_module()
    flow_args = types.SimpleNamespace(operation='owned-qa-install-state', adapter_manifest_sha256=RECORDER_MANIFEST,
        flow_dir=FLOW, epoch_module=RECORDER_ROOT/'references/framework_epoch.py',
        task_source=RECORDER_ROOT/'references/task_scope_baseline.py', step=STEP,
        request={'nonce':NONCE, 'state_nonce':STATE_NONCE, 'package':SELF, 'build':proof,
                 'install':INSTALL, 'retention':'retain_exact_owned_package_for_separately_admitted_UI'},
        unknown_step=None, observation_step=None, postcondition=None)
    result = {'schema':1, 'ok':False, 'error':None, 'secondary_errors':[],
        'package':SELF, 'nonce':NONCE, 'state_nonce':STATE_NONCE, 'build':proof,
        'install_attempted':False, 'install_success_observed':False, 'state_attempted':False,
        'package_retained':False, 'UI_actions':0, 'audio_actions':0,
        'UiAutomation_connection_requested':False, 'permission_grants':0,
        'old_v2_helper_called':False, 'automatic_retry':False, 'whole_app_production_ready':False}
    flow = stage = None; action_lock = None
    try:
        result['admission_phase'] = 'flow_constructor'
        flow = recorder.Flow(flow_args)
        result['admission_phase'] = 'flow_begin'
        flow.begin(flow_args, mutation=True)
        result['admission_phase'] = 'action_lock_acquisition'
        result['action_lock_admission'] = {}
        action_lock = acquire_action_lock(recorder.ACTION_LOCK, result['action_lock_admission'])
        result['admission_phase'] = 'post_lock_Main_guard'
        flow.guard()
        result['admission_phase'] = 'locked_install_and_state'
        binding = flow.bind()
        absence, absence_command = command(flow, PACKAGE_LIST)
        require(absence == b'', 'NEW_PACKAGE_OR_RETAINED_RECORD_ALREADY_EXISTS')
        result['absence'] = {'all_users':True,'include_uninstalled':True,'command':absence_command}
        stage = OwnedApk(binding.target)
        result['staged_apk'] = stage.stage(apk)
        del apk
        # Installation is one exact command. -R is explicit: newer PM defaults
        # to replacement even when -r is omitted. No unsupported-option retry.
        result['install_attempted'] = True
        installed, install_command = command(flow, INSTALL, 40, mutation=True)
        require(installed == b'Success\n', 'INSTALL_DID_NOT_REPORT_EXACT_SUCCESS')
        result['install_success_observed'] = True
        result['install_command'] = install_command
        uid_raw, uid_command = command(flow, ['/system/bin/cmd','package','list','packages','-U','--user','0',SELF])
        uid = uid_from(uid_raw)
        session_module = module(HERE/'session_binding.py',
            runtime_manifest['files']['session_binding.py']['sha256'], 'qa_owned_r4_session')
        session = session_module.new_session(adapter, flow, recorder, qa, proof, uid)
        result['runtime_recorder_manifest_sha256'] = RECORDER_MANIFEST
        result['runtime_session_binding_sha256'] = runtime_manifest['files']['session_binding.py']['sha256']
        result['installed_before_state'] = session.installed()
        result['uid_command'] = uid_command
        request = {'protocol':qa.PROTOCOL, 'nonce':STATE_NONCE, 'op':'state'}
        result['state_attempted'] = True
        result['state'] = session.instrument(request)
        require(result['state']['helper']['ui_automation_connected'] is False and
                result['state']['helper']['op'] == 'state', 'STATE_CANNOT_CONNECT_UIAUTOMATION')
        result['installed_after_state'] = session.installed()
        require(result['installed_before_state'] == result['installed_after_state'],
                'NEW_PACKAGE_IDENTITY_CHANGED_DURING_STATE')
        all_rows, row_command = command(flow, INSTALLED_ALL_USERS)
        require(uid_from(all_rows) == uid, 'NEW_PACKAGE_APPEARED_FOR_ANOTHER_USER_OR_UID')
        result['all_users_after'] = row_command
        result['package_retained'] = True
        result['owned_package_uid'] = uid
        result['ok'] = True
    except BaseException as error:
        remember(result,'install_or_state',error)
    finally:
        # No automatic uninstall/reinstall follows a failed or unknown install.
        # Only our held-inode staging file/directory is retired here. Retained
        # package evidence is handed to root for any separate cleanup decision.
        if stage is not None:
            try:
                result['staging_cleanup'] = stage.close()
            except BaseException as error:
                remember(result,'staging_cleanup',error)
        if flow is not None:
            try:
                flow.guard(attempted=flow.action_attempted)
                result['final_Main_guard_passed'] = True
            except BaseException as error:
                remember(result,'final_Main_guard',error)
            try:
                flow.close()
                result['held_binding_released'] = True
            except BaseException as error:
                remember(result,'held_binding_release',error)
        if action_lock is not None:
            try:
                os.close(action_lock)
                result['action_lock_released'] = True
            except BaseException as error:
                remember(result,'action_lock_release',error)
    result['action_attempted'] = bool(flow is not None and flow.action_attempted)
    result['outcome_unknown'] = bool(result['action_attempted'] and not result['ok'])
    result['possible_owned_package_retained'] = result['install_attempted'] and not result['ok']
    result['ended_utc'] = recorder.now()
    if flow is not None and flow.step is not None:
        recorder.write_new(flow.step/'result.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['ok'] else 2


def owned_resources():
    lines = Path('/proc/self/cgroup').read_text().splitlines()
    require(len(lines) == 1 and re.fullmatch(
        r'0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-[0-9a-f-]+\.service',
        lines[0]), 'OWNED_MANAGED_CGROUP_REQUIRED')
    path = Path('/sys/fs/cgroup'+lines[0][3:])
    require(path.resolve() == path, 'OWNED_CGROUP_LINK_REJECTED')
    values = {name:(path/name).read_text().strip() for name in (
        'memory.max','memory.swap.max','cpu.max','pids.max','memory.events',
        'memory.current','memory.peak','memory.swap.current','memory.swap.peak')}
    require(values['memory.max'] == '536870912' and values['cpu.max'] == '100000 100000',
            'EXACT_MANAGED_REQUEST_LIMITS_REQUIRED')
    info = path.stat()
    return {'path':str(path),'device':info.st_dev,'inode':info.st_ino,**values}


def prepare_owned_limits():
    before = owned_resources()
    path = Path(before['path'])
    # Only the caller's exact current managed job; never any Main cgroup.
    for name,value in (('memory.swap.max','0'),('pids.max','128')):
        fd = os.open(path/name,os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            require(os.write(fd,value.encode()) == len(value),'OWNED_LIMIT_WRITE_INCOMPLETE')
        finally:
            os.close(fd)
    after = owned_resources()
    require((before['device'],before['inode']) == (after['device'],after['inode']) and
            after['memory.swap.max'] == '0' and after['pids.max'] == '128','OWNED_LIMIT_IDENTITY_CHANGED')
    return after


def resources_qualified(before, after):
    require((before['path'],before['device'],before['inode']) ==
            (after['path'],after['device'],after['inode']), 'OWNED_CGROUP_CHANGED')
    for key in ('memory.max','memory.swap.max','cpu.max','pids.max'):
        require(before[key] == after[key], 'OWNED_LIMIT_CHANGED:'+key)
    for row in (before,after):
        counters = dict(line.split() for line in row['memory.events'].splitlines())
        require(all(counters.get(key) == '0' for key in ('max','oom','oom_kill','oom_group_kill')),
                'OWNED_MEMORY_LIMIT_OR_OOM_EVENT')
    return True


def execute(expected):
    verify_source(expected)
    require(os.getuid() == os.geteuid() == 0 and HERE == SOURCE, 'ROOT_EXACT_STAGED_SOURCE_REQUIRED')
    ref = references()
    require(not os.path.lexists(FLOW), 'FRESH_FLOW_REQUIRED_NO_PARTIAL_RETRY')
    claim = json.loads(read(ROOT/'once.claim.json',65536))
    require(claim.get('nonce') == NONCE and claim.get('source_manifest_sha256') == expected and
            claim.get('automatic_retry') is False, 'EXACT_ONCE_CLAIM_REQUIRED')
    evidence = ROOT/'evidence'; evidence.mkdir(mode=0o700)
    result = {'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'source_manifest_sha256':expected,'package':SELF,'nonce':NONCE,
        'flow':str(FLOW),'automatic_retry':False,'UI_actions':0,'audio_actions':0,
        'whole_app_production_ready':False,'old_v2_helper_called':False,'install_state_worker_requested':False}
    activation = epoch = resource_before = None
    try:
        resource_before = prepare_owned_limits()
        result['owned_before'] = resource_before
        qualified_inputs()
        activation = json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
        epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'qa_state_epoch')
        guard = lambda: ref.main_guard(activation,epoch)
        result['Main_before'] = guard()
        recorder = recorder_module()
        source, contract = recorder.source_contract(RECORDER_MANIFEST)
        common = ['/usr/bin/python3','-I',str(RECORDER_ROOT/'recorder.py')]
        initial = ref.run_cli('01-init',common+['init','--adapter-manifest-sha256',RECORDER_MANIFEST,
            '--flow-dir',str(FLOW),'--activation-after',str(ref.ACTIVATION),
            '--activation-sha256',ref.ACTIVATION_SHA,'--package',ref.PACKAGE,'--component',ref.COMPONENT],
            25,evidence,guard)
        require(initial.get('ok') is True and initial.get('scope_initialized') is True and
                initial.get('epoch_sha256') == ref.EPOCH,'FRESH_ORIGINAL_FLOW_INIT_FAILED')
        result['install_state_worker_requested'] = True
        observed = ref.run_cli('02-install-state',['/usr/bin/python3','-I',str(HERE/'install_state.py'),
            '--worker-once','--source-manifest-sha256',expected],190,evidence,guard)
        durable_raw = read(FLOW/'steps'/STEP/'result.json')
        durable = json.loads(durable_raw)
        require(observed == durable and durable.get('ok') is True and
                durable.get('package') == SELF and durable.get('state_attempted') is True and
                durable.get('install_success_observed') is True and
                durable.get('package_retained') is True and durable.get('outcome_unknown') is False,
                'INSTALL_STATE_DURABLE_SCOPE_MISMATCH')
        result['owned_package_uid'] = durable['owned_package_uid']
        result['worker_result'] = {'path':str(FLOW/'steps'/STEP/'result.json'),
                                  'bytes':len(durable_raw),'sha256':digest(durable_raw)}
        result['state_wire_sha256'] = durable['state']['wire_sha256']
        result['owned_package_retained_for_separate_UI_admission'] = True
        contract.verify()
        result['ok'] = True
    except BaseException as error:
        remember(result,'coordinator',error)
    finally:
        if result['install_state_worker_requested'] and 'worker_result' not in result:
            try:
                path = FLOW/'steps'/STEP/'result.json'
                if path.exists():
                    raw = read(path)
                    result['failed_worker_result'] = {'path':str(path),'bytes':len(raw),'sha256':digest(raw)}
                result['package_outcome_requires_exact_worker_reconciliation'] = True
            except BaseException as error:
                remember(result,'failed_worker_evidence',error)
        if activation is not None and epoch is not None:
            try:
                result['Main_after'] = ref.main_guard(activation,epoch)
            except BaseException as error:
                remember(result,'coordinator_final_Main',error)
        try:
            verify_source(expected)
            qualified_inputs()
            recorder_module().source_contract(RECORDER_MANIFEST)[1].verify()
            result['source_and_artifact_unchanged'] = True
        except BaseException as error:
            remember(result,'final_source_and_artifact',error)
        if resource_before is not None:
            try:
                result['owned_after'] = owned_resources()
                resources_qualified(resource_before,result['owned_after'])
            except BaseException as error:
                remember(result,'owned_resources_after',error)
        try:
            pin = ref.write_new(ROOT/'result.json',result)
        except BaseException as error:
            remember(result,'final_result_write',error)
            pin = None
        print(json.dumps({'ok':result['ok'],'result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'package':SELF,
            'UI_actions':0,'audio_actions':0,'whole_app_production_ready':False}),flush=True)
    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--execute-once',action='store_true')
    modes.add_argument('--worker-once',action='store_true')
    parser.add_argument('--source-manifest-sha256')
    args = parser.parse_args()
    if not args.execute_once and not args.worker_once:
        print(json.dumps({'state':'PLAN_ONLY','package':SELF,'root':str(ROOT),'flow':str(FLOW),
            'actual_build_sha256':BUILD_SHA,'APK_sha256':APK_SHA,'signer_certificate_sha256':SIGNER_SHA,
            'install_argv':INSTALL,'state_nonce':STATE_NONCE,'UiAutomation_connection_requested':False,
            'permission_grants':0,'UI_actions':0,'old_v2_helper_called':False,
            'retention':'exact owned helper retained; no automatic uninstall/reinstall on unknown outcomes'}))
        return 0
    os.umask(0o077)
    require(re.fullmatch('[0-9a-f]{32}',NONCE) and re.fullmatch('[0-9a-f]{32}',STATE_NONCE)
            and NONCE != STATE_NONCE,'EXACT_DISTINCT_NONCES_REQUIRED')
    return worker(args.source_manifest_sha256) if args.worker_once else execute(args.source_manifest_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
